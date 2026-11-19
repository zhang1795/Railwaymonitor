"""Camera-keyed task lifecycle. No MQTT or camera work occurs on import."""
from collections import OrderedDict
from dataclasses import dataclass, field
import logging
import threading
import time
import uuid

log = logging.getLogger(__name__)

@dataclass
class Task:
    message: dict
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    stop: threading.Event = field(default_factory=threading.Event)
    state: str = 'STARTING'
    revision: int = 0
    error: str = ''
    stop_reason: str = ''
    owners: dict = field(default_factory=dict)
    listeners: object = field(default_factory=OrderedDict)
    thread: object = None
    progress: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    _running: object = None

    @property
    def video_id(self):
        return str(self.message['videoId'])

    def mark_running(self):
        self._running(self)

class TaskManager:
    def __init__(self, worker, status_sink=None, max_tasks=9, lease_seconds=20,
                 clock=time.monotonic):
        self.worker = worker
        self.status_sink = status_sink or (lambda status: None)
        self.max_tasks = max_tasks
        self.lease_seconds = lease_seconds
        self.clock = clock
        self._tasks = {}
        self._history = OrderedDict()
        self._requests = OrderedDict()
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._reaper = None
        if max_tasks < 1 or lease_seconds <= 0:
            raise ValueError('task capacity and lease must be positive')

    def _status(self, task, message=None):
        message = message or {}
        return {'protocolVersion':2, 'videoId':task.video_id,
                'metrics':dict(task.progress),
                'sessionId':task.session_id, 'state':task.state, 'error':task.error,
                'owners':len(task.owners), 'revision':task.revision,
                'action':message.get('action'), 'requestId':message.get('requestId'),
                'clientId':message.get('clientId')}

    def _emit(self, status):
        try:
            self.status_sink(status)
            return True
        except Exception:
            log.exception('Task status delivery failed')
            return False

    def _notifications(self, task):
        # Correlate even fast failures with each owner's start request. A task
        # can fail before the caller has received its STARTING acknowledgement.
        return [self._status(task, {'clientId':owner, 'requestId':request_id})
                for owner, request_id in task.listeners.items()]

    def _mark_running(self, task):
        with self._lock:
            if task.stop.is_set() or self._tasks.get(task.video_id) is not task:
                raise InterruptedError('task stopped before startup finished')
            task.state = 'RUNNING'
            task.revision += 1
            statuses = self._notifications(task)
        for status in statuses:
            if not self._emit(status):
                break

    def handle(self, message, server_control=False):
        if not isinstance(message, dict):
            raise ValueError('expected a task object')
        version = message.get('protocolVersion', 1)
        if version not in (1, 2):
            raise ValueError('unsupported protocolVersion')
        if version == 2 and (not isinstance(message.get('clientId'), str)
                             or not message['clientId'].strip()
                             or message['clientId'] == 'legacy'):
            raise ValueError('v2 control requires a nonempty clientId')
        video_id = str(message.get('videoId', '')).strip()
        client_id = str(message.get('clientId') or 'legacy')
        action = message.get('action', 'start')
        if not video_id or len(video_id) > 128 or len(client_id) > 128:
            raise ValueError('invalid videoId/clientId')
        if action not in ('start','stop','heartbeat'):
            raise ValueError('unsupported task action')
        request_id = message.get('requestId')
        if request_id is not None and (not isinstance(request_id,str) or len(request_id)>200):
            raise ValueError('invalid requestId')
        key = (client_id, video_id, action, request_id)
        start_thread = None
        with self._lock:
            if self._closed.is_set():
                raise RuntimeError('task manager is closed')
            if request_id and key in self._requests:
                status = dict(self._requests[key])
                current = self._tasks.get(video_id) or self._history.get(video_id)
                if current is not None and current.session_id == status.get('sessionId'):
                    status = self._status(current,message)
                status['duplicate'] = True
                return status
            task = self._tasks.get(video_id)
            if action == 'start':
                if not isinstance(message.get('videoUrl'),str) or not message['videoUrl'].strip():
                    raise ValueError('missing videoUrl')
                if task is not None and task.message['videoUrl'] != message['videoUrl']:
                    raise ValueError('camera already has a task with a different URL')
                if task is None:
                    from frame_clock import parse_start
                    parse_start(message.get('startTime'), legacy=message.get('protocolVersion',1)==1)
                    if len(self._tasks) >= self.max_tasks:
                        raise ValueError('camera task limit reached')
                    task = Task(dict(message), **({'session_id': message['sessionId']}
                                if server_control and message.get('sessionId') else {}))
                    task._running = self._mark_running
                    self._tasks[video_id] = task
                    start_thread = threading.Thread(target=self._run, args=(task,),
                                                    name='camera-'+video_id, daemon=True)
                    task.thread = start_thread
                if task.state != 'STOPPING':
                    if client_id not in task.owners and len(task.owners) >= 256:
                        raise ValueError('camera holder limit reached')
                    task.owners[client_id] = None if client_id == 'legacy' else self.clock()+self.lease_seconds
                    task.listeners[client_id] = request_id
                    task.listeners.move_to_end(client_id)
                    if len(task.listeners) > 512:
                        for old_owner in list(task.listeners):
                            if old_owner not in task.owners:
                                del task.listeners[old_owner]
                                if len(task.listeners) <= 512:
                                    break
                task.revision += 1
                status = self._status(task,message)
            elif task is None:
                status = {'protocolVersion':2, 'videoId':video_id, 'state':'STOPPED',
                          'action':action,
                          'sessionId':message.get('sessionId'), 'requestId':request_id,
                          'clientId':client_id, 'owners':0, 'error':''}
            elif message.get('sessionId') and message['sessionId'] != task.session_id:
                status = self._status(task,message)
                status['stale'] = True
            else:
                if action == 'heartbeat' and client_id in task.owners and client_id != 'legacy':
                    task.owners[client_id] = self.clock()+self.lease_seconds
                elif action == 'stop':
                    task.owners.pop(client_id,None)
                    if not task.owners:
                        task.state = 'STOPPING'
                        task.stop.set()
                task.revision += 1
                status = self._status(task,message)
            if request_id:
                self._requests[key] = dict(status)
                while len(self._requests) > 1024:
                    self._requests.popitem(last=False)
            # Starting under the lock guarantees close()/stop() cannot join an
            # unstarted thread. Worker callbacks acquire the lock after release.
            if start_thread is not None:
                try:
                    start_thread.start()
                except Exception:
                    self._tasks.pop(video_id,None)
                    raise
        return status

    def _run(self, task):
        state, error_text = 'STOPPED', ''
        try:
            self.worker(task)
        except InterruptedError:
            state = 'STOPPED' if task.stop.is_set() else 'FAILED'
            if not task.stop.is_set():
                error_text = 'InterruptedError'
        except Exception as error:
            error_text = type(error).__name__ + ': ' + str(error)
            state = 'FAILED'
            log.exception('Camera %s task failed',task.video_id)
        finally:
            with self._lock:
                task.state, task.error = state, error_text
                task.revision += 1
                if self._tasks.get(task.video_id) is task:
                    del self._tasks[task.video_id]
                task.owners.clear()
                self._history[task.video_id] = task
                self._history.move_to_end(task.video_id)
                while len(self._history)>128:
                    self._history.popitem(last=False)
                statuses = self._notifications(task)
            for status in statuses:
                if not self._emit(status):
                    break

    def snapshot(self, video_id):
        with self._lock:
            task = self._tasks.get(str(video_id)) or self._history.get(str(video_id))
            return None if task is None else self._status(task)

    def health(self,stall_seconds=120):
        from datetime import datetime
        now=time.time();stalled=[]
        with self._lock:
            for task in self._tasks.values():
                try:last=datetime.fromisoformat(task.progress['lastInferenceAt'].replace('Z','+00:00')).timestamp()
                except (KeyError,ValueError,TypeError):last=task.created_at
                if now-last>stall_seconds:stalled.append(task.video_id)
        return {'pid':__import__('os').getpid(),'at':now,'stalledCameras':stalled}

    def sweep(self):
        statuses = []
        with self._lock:
            for task in list(self._tasks.values()):
                for owner, expiry in list(task.owners.items()):
                    if expiry is not None and expiry <= self.clock():
                        del task.owners[owner]
                if not task.owners and not task.stop.is_set():
                    task.state = 'STOPPING'
                    task.stop_reason = 'control_lease_expired'
                    task.revision += 1
                    task.stop.set()
                    statuses.extend(self._notifications(task))
        for status in statuses:
            if not self._emit(status):
                break

    def start_reaper(self):
        if self._reaper is not None:
            return
        def run():
            while not self._closed.wait(1):
                self.sweep()
        self._reaper = threading.Thread(target=run,name='camera-leases',daemon=True)
        self._reaper.start()

    def wait(self, video_id, timeout=7):
        with self._lock:
            task = self._tasks.get(str(video_id)) or self._history.get(str(video_id))
        if task is not None and task.thread is not None:
            task.thread.join(timeout)
            return not task.thread.is_alive()
        return True

    def close(self, timeout=7):
        self._closed.set()
        with self._lock:
            tasks = list(self._tasks.values())
            for task in tasks:
                task.state = 'STOPPING'
                task.stop_reason = 'service_shutdown'
                task.stop.set()
        deadline = time.monotonic()+timeout
        for task in tasks:
            task.thread.join(max(0,deadline-time.monotonic()))
        if self._reaper is not None:
            self._reaper.join(max(0,deadline-time.monotonic()))
