"""Authenticated service transport with disk replay and application ACKs."""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from frame_clock import parse_start

log = logging.getLogger(__name__)


class DetectorService:
    def __init__(self, worker_id, outbox, manager,evidence=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', worker_id):
            raise ValueError('invalid worker ID')
        self.worker_id, self.outbox, self.manager = worker_id, outbox, manager
        self.evidence=evidence
        self.prefix = 'railway/v3/' + worker_id
        self.closed, self.connected = threading.Event(), threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=worker_id, clean_session=False)
        self.client.max_inflight_messages_set(16)
        self.client.max_queued_messages_set(64)
        username, password = os.getenv('MQTT_USERNAME'), os.getenv('MQTT_PASSWORD')
        if not username or not password:
            raise ValueError('MQTT_USERNAME and MQTT_PASSWORD are required')
        if username != worker_id:
            raise ValueError('MQTT username must equal the assigned worker ID')
        self.client.username_pw_set(username, password)
        self.host = os.getenv('MQTT_HOST', '127.0.0.1')
        tls = os.getenv('MQTT_CA_FILE')
        if tls:
            self.client.tls_set(ca_certs=tls)
        elif self.host not in ('localhost', '127.0.0.1', '::1') or os.getenv('MQTT_ALLOW_LOCAL_PLAINTEXT') != 'true':
            raise ValueError('TLS is required except explicitly allowed loopback development')
        self.port = int(os.getenv('MQTT_PORT', '8883' if tls else '1883'))
        self.client.on_connect, self.client.on_message = self._connect, self._message
        self.client.on_disconnect = lambda *args: self.connected.clear()
        self.client.reconnect_delay_set(1, 30)
        self.thread = None

    def _connect(self, client, userdata, flags, reason, properties):
        if reason == 0:
            client.subscribe([(self.prefix+'/ack', 1), (self.prefix+'/control', 1)])
            self.connected.set()
        else:
            log.error('Broker authentication/connect rejected: %s', reason)

    def _message(self, client, userdata, message):
        try:
            if len(message.payload) > 16384:
                raise ValueError('service message exceeds limit')
            data = json.loads(message.payload.decode('utf-8'))
            if message.topic == self.prefix+'/ack':
                if self.outbox.acknowledge(data) and data.get('status') == 'REJECTED':
                    log.error('Event rejected by backend: %s %s', data.get('eventId'), data.get('reason'))
            elif message.topic == self.prefix+'/control':
                self.control(data)
        except Exception:
            log.exception('Rejected service message')

    def control(self, command):
        if command.get('protocolVersion') != 3 or command.get('workerId') != self.worker_id:
            raise ValueError('wrong control identity/version')
        expiry = parse_start(command.get('expiresAt'))
        now = datetime.now(timezone.utc)
        if not 0 < (expiry-now).total_seconds() <= 60:
            raise ValueError('expired control or excessive validity')
        camera = str(command.get('cameraId', ''))
        generation = command.get('generation')
        session = command.get('sessionId', '')
        enabled = command.get('enabled')
        if (not camera.isdigit() or not isinstance(generation, int) or isinstance(generation, bool)
            or generation < 1 or not re.fullmatch(r'[a-f0-9]{32}', session)
            or not isinstance(enabled, bool)):
            raise ValueError('invalid control contract')
        if not self.outbox.fence(camera, generation, session, enabled):
            return
        current = self.manager.snapshot(camera)
        common = dict(protocolVersion=2, videoId=camera, clientId='backend',
                      requestId=command.get('commandId'))
        if not enabled or (current and current['sessionId'] != session and
                           current['state'] in ('STARTING','RUNNING','STOPPING')):
            status = self.manager.handle(dict(common, action='stop',
                sessionId=current['sessionId'] if current else session))
            status.setdefault('revision', 0)
        else:
            url = command.get('videoUrl', '')
            if not isinstance(url, str) or not url.lower().startswith(('rtsp://', 'rtsps://')):
                raise ValueError('only backend-configured RTSP sources are accepted')
            live = current and current['sessionId'] == session and current['state'] in ('STARTING','RUNNING','STOPPING')
            if not live and not self.outbox.claim_session(camera, session):
                # A process/task restart resets local SORT IDs. Request a NEW
                # server session rather than silently reusing business keys.
                self.status(dict(videoId=camera, sessionId=session, state='FAILED', revision=0,
                    lostSession=True, error='worker session ended; new server session required', generation=generation))
                return
            status = self.manager.handle(dict(common, action='start', videoUrl=url,
                startTime=now.isoformat(), sessionId=session, workerId=self.worker_id,
                generation=generation,trackGraceSeconds=command.get('trackGraceSeconds',3)), server_control=True)
        self.status(dict(status, generation=generation, commandId=command.get('commandId')))

    def status(self, value):
        if not self.connected.is_set():
            return
        message = dict(value, protocolVersion=3, workerId=self.worker_id,
                       pendingEvents=self.outbox.count())
        message.update(self.evidence.metrics() if self.evidence else {'evidencePending':0,'evidenceSkipped':0,'evidenceError':'not_configured'})
        self.client.publish(self.prefix+'/status', json.dumps(message), qos=1)

    def _send(self):
        while not self.closed.wait(.1):
            if not self.connected.is_set():
                continue
            for row in self.outbox.due(16):
                if self.closed.is_set():
                    return
                try:
                    info = self.client.publish(self.prefix+'/events', row['body'], qos=1)
                    if info.rc != mqtt.MQTT_ERR_SUCCESS:
                        raise ConnectionError('publish not queued')
                    deadline = time.monotonic()+2
                    while not self.closed.is_set() and not info.is_published() and time.monotonic()<deadline:
                        info.wait_for_publish(timeout=.1)
                except Exception:
                    log.warning('Event delivery deferred; durable event retained', exc_info=True)
                finally:
                    self.outbox.attempted(row['event_id'])

    def start(self):
        self.client.connect_async(self.host, self.port, 30)
        self.client.loop_start()
        self.thread = threading.Thread(target=self._send, name='durable-events', daemon=True)
        self.thread.start()

    def close(self):
        self.closed.set()
        if self.thread is not None:
            self.thread.join(5)
            if self.thread.is_alive():
                raise RuntimeError('sender shutdown incomplete; keep outbox open for process recovery')
        self.client.disconnect()
        self.client.loop_stop()
