"""Video worker: durable track events and best-effort, bounded recording."""
import json
import logging
import math
import os
import signal
import threading
import time
from collections import deque
import uuid
from pathlib import Path
from datetime import datetime, timezone

import cv2
from tracker import Sort
from frame_clock import FrameClock, parse_start
from task_manager import TaskManager
from video_capture import BoundedCapture,FrameDecodeError,SourceUnavailableError
from track_events import TrackEvents, CLASS_NAMES, CLASS_LABELS
from event_recorder import EventRecorder

log = logging.getLogger(__name__)
DETECTOR_OUTPUT_DIR = os.path.abspath(os.getenv('DETECTOR_OUTPUT_DIR',
    os.path.join(os.path.dirname(__file__), '..', 'workspace', 'runtime', 'detector-output')))


def generateName(name):
    return CLASS_LABELS[CLASS_NAMES.index(name)] if name in CLASS_NAMES else '未知类别'


def make_result(payload, *, task=None, detector=None, capture_factory=None,
                writer_factory=None, tracker_factory=None, publish=None, now=None,
                output_dir=None, event_clock=None, evidence=None, recordings=None,sampled_recording=True,recording_init_state='NOT_CONFIGURED',live_results=None,analysis_enabled=False):
    from model_init import process_frame,_default
    stop = task.stop if task is not None else threading.Event()
    session = task.session_id if task is not None else uuid.uuid4().hex
    now = now or (lambda: datetime.now(timezone.utc))
    if publish is None:
        raise RuntimeError('a durable event sink is required')
    message = dict(payload) if isinstance(payload, dict) else json.loads(payload)
    output_dir = output_dir or DETECTOR_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    capture_factory = capture_factory or (lambda url: BoundedCapture(url, stop,
        timeout=float(os.getenv('VIDEO_READ_TIMEOUT', '5'))))
    tracker = (tracker_factory or Sort)(max_age=1, min_hits=5, iou_threshold=.3,
        max_idle_seconds=float(message.get('trackGraceSeconds',3)))
    current_frame=[None]
    events = TrackEvents(message, session, publish,
        on_snapshot=(lambda event:evidence.capture(event,current_frame[0])) if evidence else None,
        **({'clock':event_clock} if event_clock else {}))
    cap = recorder = source_recorder = result_frames = analysis_recorder = None
    recording_state='DISABLED'
    interrupted = False
    try:
        start = parse_start(message.get('startTime'), legacy=message.get('protocolVersion', 1) == 1)
        if stop.is_set():
            return
        cap = capture_factory(message['videoUrl'])
        if not cap.isOpened():
            raise RuntimeError('cannot open video')
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        fps = fps if math.isfinite(fps) and fps > 0 else 25.
        source_fps=fps
        timeline = FrameClock(start, message['videoUrl'], fps)
        size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        prefix = ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(message['videoId']))
        if sampled_recording:
            try:recorder = EventRecorder(os.path.join(output_dir, prefix+'_'+session), fps, size,factory=writer_factory or cv2.VideoWriter)
            except Exception:recording_state='ERROR';log.warning('Optional sampled recorder unavailable; detection continues')
        if timeline.live and recordings is not None:
            try:
                from source_recording import SourceRecorder
                source_recorder=SourceRecorder(message,session,recordings,segment_seconds=int(os.getenv('SOURCE_SEGMENT_SECONDS','30')));source_recorder.start()
            except Exception:source_recorder=None;recording_init_state='ERROR';log.warning('Optional source recorder unavailable; detection continues')
        if timeline.live and (live_results is not None or analysis_enabled and recordings is not None):
            try:
                from detection_views import ResultFrames,model_hash
                result_frames=ResultFrames(message,session,model_hash(detector or _default))
                if analysis_enabled and recordings is not None:
                    from analysis_recording import AnalysisRecorder
                    analysis_recorder=AnalysisRecorder(message,session,recordings,max_fps=float(os.getenv('ANALYSIS_MAX_SAMPLE_FPS','2')));analysis_recorder.start()
            except Exception:
                result_frames=None;log.warning('Optional detection views unavailable; critical events continue')
        if task is not None:
            task.progress=dict(task.progress,sourceRecordingState=recording_init_state)
            task.mark_running()
        index = 0
        completed=deque(maxlen=120);durations=deque(maxlen=120)
        while cap.isOpened() and not stop.is_set():
            try:
                ok, frame = cap.read()
            except InterruptedError:
                if stop.is_set():
                    break
                raise
            if not ok or frame is None:
                if timeline.live and not stop.is_set():
                    raise ConnectionError('live video stream ended unexpectedly')
                break
            received=getattr(cap,'frame_received_at',None)
            received=datetime.fromtimestamp(received,timezone.utc) if received is not None else now()
            frame_time, source = timeline.at(index, float(cap.get(cv2.CAP_PROP_POS_MSEC)), received)
            index += 1
            started=time.monotonic()
            if task is not None:task.progress=dict(task.progress,lastFrameAt=received.isoformat())
            try:
                observations, results = process_frame(frame, tracker, detector, stop,frame_time.timestamp())
            except InterruptedError:
                if stop.is_set():
                    break
                raise
            finished=time.monotonic();completed.append(finished);durations.append((finished-started)*1000)
            if task is not None:
                valid=[tick for tick in completed if finished-tick<=30]
                fps=(len(valid)-1)/(valid[-1]-valid[0]) if len(valid)>1 and valid[-1]>valid[0] else 0.
                measured=getattr(detector or _default,'metrics',lambda:{})()
                task.progress=dict(task.progress,**measured,sourceFps=source_fps,
                    effectiveFps=round(fps,3),processedFrames=index,decodedFrames=getattr(cap,'decoded_frames',index),
                    skippedFrames=getattr(cap,'skipped_frames',0),lastInferenceAt=now().isoformat(),
                    frameAgeMs=max(0,round((now()-received).total_seconds()*1000,3)),
                    processingP95Ms=round(sorted(durations)[max(0,math.ceil(len(durations)*.95)-1)],3),
                    sourceQuality='DECODE_CHECKED' if getattr(cap,'decode_checked',False) else 'UNVERIFIED',
                    decodeErrors=getattr(cap,'decode_errors',0),
                    decoderRelativeLagMs=round(getattr(cap,'relative_lag_ms',0.),3),
                    sourceTimestampVerified=False)
            # Commit critical metadata BEFORE any optional media operation.
            current_frame[0]=frame
            events.update(results, [t.id for t in tracker.trackers], frame_time, source, now(), frame.shape,observations)
            if result_frames is not None:
                try:
                    metadata,image=result_frames.build(frame,observations,results,index,getattr(cap,'decoded_frames',index),received,now(),getattr(cap,'decode_checked',False))
                    if live_results is not None:live_results.offer(metadata,image)
                    if analysis_recorder is not None:analysis_recorder.offer(metadata,image)
                except Exception:
                    result_frames=None
                    if task is not None:task.progress=dict(task.progress,liveResultState='ERROR')
                    log.warning('Optional detection views failed; critical events continue')
            if recorder is not None:recorder.frame(frame, results,frame_time.isoformat())
            if task is not None:
                task.progress=dict(task.progress,recordingState=recorder.state if recorder else recording_state)
                if source_recorder is not None:task.progress.update(source_recorder.metrics())
                if live_results is not None and result_frames is not None:task.progress.update(live_results.metrics())
                if analysis_recorder is not None:task.progress.update(analysis_recorder.metrics())
    except BaseException as error:
        interrupted = True
        if task is not None and isinstance(error,FrameDecodeError):
            task.progress=dict(task.progress,sourceQuality='CORRUPT',decodeErrors=max(1,getattr(cap,'decode_errors',0)))
        if task is not None and isinstance(error,SourceUnavailableError):task.progress=dict(task.progress,sourceQuality='UNAVAILABLE')
        raise
    finally:
        try:
            try:
                events.finish(now(), interrupted or bool(getattr(task, 'stop_reason', '')))
            except Exception:
                if not interrupted:
                    raise
                log.exception('Could not persist final track state; prior events remain durable')
        finally:
            try:
                if recorder is not None:
                    recorder.close()
                if source_recorder is not None:source_recorder.close()
                if analysis_recorder is not None:analysis_recorder.close()
            finally:
                if cap is not None:
                    cap.release()


def main():
    from event_outbox import EventOutbox
    from mqtt_service import DetectorService
    logging.basicConfig(level=logging.INFO)
    worker_id = os.getenv('DETECTOR_WORKER_ID', 'detector-1')
    path = os.getenv('DETECTOR_OUTBOX_PATH', os.path.join(DETECTOR_OUTPUT_DIR, 'events.sqlite3'))
    outbox = EventOutbox(path, worker_id,
        max_events=int(os.getenv('DETECTOR_MAX_PENDING', '10000')),
        max_bytes=int(os.getenv('DETECTOR_MAX_PENDING_BYTES', str(64*1024*1024))))
    evidence=None
    if os.getenv('EVIDENCE_SERVICE_KEY'):
        from evidence_outbox import EvidenceOutbox
        try:
            evidence=EvidenceOutbox(os.path.join(DETECTOR_OUTPUT_DIR,'evidence.sqlite3'),worker_id,
                os.getenv('EVIDENCE_INGEST_URL','http://127.0.0.1:8080/api'),os.environ['EVIDENCE_SERVICE_KEY'],os.getenv('EVIDENCE_CA_FILE'))
            evidence.start()
        except Exception:log.exception('Evidence transport unavailable; critical event delivery continues')
    recordings=None;recording_init_state='NOT_CONFIGURED'
    if os.getenv('EVIDENCE_SERVICE_KEY') and os.getenv('SOURCE_RECORDING_ENABLED','true')=='true':
        try:
            from source_recording import VideoManifestOutbox
            recording_root=os.getenv('FULL_RECORDING_ROOT',os.path.join(os.path.dirname(DETECTOR_OUTPUT_DIR),'full-recordings'))
            if not os.path.isabs(recording_root):recording_root=os.path.join(os.getenv('RAILWAY_PROJECT_ROOT',str(Path(DETECTOR_OUTPUT_DIR).parents[2])),recording_root)
            recordings=VideoManifestOutbox(recording_root,worker_id,
                os.getenv('EVIDENCE_INGEST_URL','http://127.0.0.1:8080/api'),os.environ['EVIDENCE_SERVICE_KEY'],os.getenv('EVIDENCE_CA_FILE'))
            recordings.start()
        except Exception:
            recordings=None;recording_init_state='ERROR';log.exception('Source recording unavailable; critical event delivery continues')
    elif os.getenv('SOURCE_RECORDING_ENABLED','true')!='true':recording_init_state='DISABLED'
    live_results=None
    if os.getenv('EVIDENCE_SERVICE_KEY') and os.getenv('LIVE_RESULTS_ENABLED','true')=='true':
        try:
            from detection_views import LiveResults
            live_results=LiveResults(worker_id,os.getenv('EVIDENCE_INGEST_URL','http://127.0.0.1:8080/api'),os.environ['EVIDENCE_SERVICE_KEY'],os.getenv('EVIDENCE_CA_FILE'),max_fps=float(os.getenv('LIVE_RESULTS_MAX_FPS','2')));live_results.start()
        except Exception:log.warning('Optional live-result uploader unavailable')
    manager = TaskManager(lambda task: make_result(task.message, task=task, publish=outbox.enqueue,evidence=evidence,recordings=recordings,sampled_recording=os.getenv('SAMPLED_RECORDING_ENABLED','false')=='true',recording_init_state=recording_init_state,live_results=live_results,analysis_enabled=os.getenv('ANALYSIS_RECORDING_ENABLED','true')=='true'),
        max_tasks=int(os.getenv('DETECTOR_MAX_TASKS', '9')),
        lease_seconds=float(os.getenv('DETECTOR_LEASE_SECONDS', '30')))
    service = DetectorService(worker_id, outbox, manager,evidence=evidence)
    manager.status_sink = service.status
    def shutdown(*args):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, shutdown)
    manager.start_reaper()
    try:
        service.start()
        heartbeat=Path(DETECTOR_OUTPUT_DIR)/'heartbeat.json'
        while True:
            temporary=heartbeat.with_suffix('.tmp')
            temporary.write_text(json.dumps(manager.health(float(os.getenv('DETECTOR_STALL_SECONDS','120')))))
            temporary.chmod(0o600);temporary.replace(heartbeat)
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        manager.close(timeout=15)
        service.close()
        if evidence:evidence.close()
        if recordings:recordings.close()
        if live_results:live_results.close()
        outbox.close()


if __name__ == '__main__':
    main()
