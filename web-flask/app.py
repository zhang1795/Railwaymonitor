"""Authenticated RTSP preview gateway. Detection runs independently."""
import base64
import json
import logging
import os
from pathlib import Path
import ssl
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import cv2
from flask import Flask, jsonify, request
from flask_sock import Sock

project_root=Path(os.getenv('RAILWAY_PROJECT_ROOT',str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, os.getenv('DETECTOR_CODE_ROOT',str(project_root / 'RailwayDetector')))
from video_capture import BoundedCapture,FrameDecodeError

log = logging.getLogger(__name__)
app = Flask(__name__)
app.config['SOCK_SERVER_OPTIONS'] = {'ping_interval': 20, 'max_message_size': 4096}
sock = Sock(app)
stream_tasks = {}  # key=(connection,camera); never camera alone
ws_tasks = {}
lock = threading.RLock()
MAX_STREAMS = int(os.getenv('PREVIEW_MAX_STREAMS', '32'))


def resolve_grant(grant, camera_id=None):
    backend = os.getenv('BACKEND_INTERNAL_URL', 'http://127.0.0.1:8080/api')
    key = os.getenv('PREVIEW_SERVICE_KEY', '')
    url = urlsplit(backend)
    if len(key) < 32 or (url.scheme != 'https' and url.hostname not in ('127.0.0.1', 'localhost', '::1')):
        raise PermissionError('preview service is not securely configured')
    body = json.dumps({'grant': grant, 'cameraId': camera_id}).encode()
    query = Request(backend+'/_internal/preview/resolve', body,
        headers={'Content-Type':'application/json', 'Authorization':'Bearer '+key}, method='POST')
    context = ssl.create_default_context(cafile=os.getenv('BACKEND_CA_FILE') or None)
    with urlopen(query, timeout=3, context=context) as response:
        if response.status != 200:
            raise PermissionError('preview grant rejected')
        result = json.loads(response.read(8192))
    if result.get('code') != 200:
        raise PermissionError('preview grant rejected')
    return result['data']


def allowed_origin():
    allowed = {value.strip() for value in os.getenv('PREVIEW_ALLOWED_ORIGINS',
               'http://localhost:3000,http://127.0.0.1:3000').split(',')}
    return request.headers.get('Origin') in allowed


def safe_send(context, kind, data):
    if context['closed'].is_set():
        return False
    try:
        with context['send_lock']:
            context['ws'].send(json.dumps({'type':kind, 'data':data}))
        return True
    except Exception:
        context['closed'].set()
        return False


def stop_camera(context, camera):
    with lock:
        task = stream_tasks.get((context['id'], camera))
        if task:
            task['stop'].set()


def cleanup_ws_tasks(ws_id):
    with lock:
        context = ws_tasks.get(ws_id)
        if context:
            context['closed'].set()
        for (owner, camera), task in list(stream_tasks.items()):
            if owner == ws_id:
                task['stop'].set()
        ws_tasks.pop(ws_id, None)


def process_stream(context, camera, task):
    capture = None
    key = (context['id'], camera)
    try:
        source = resolve_grant(context['grant'], camera)['videoUrl']
        capture = BoundedCapture(source, task['stop'], timeout=5)
        if not capture.isOpened():
            raise RuntimeError('camera unavailable')
        last_auth = 0.
        ready = False
        while not task['stop'].is_set() and not context['closed'].is_set():
            tick = time.monotonic()
            if tick-last_auth >= 15:
                resolve_grant(context['grant'], camera)
                last_auth = tick
            ok, frame = capture.read()
            if not ok or frame is None:
                raise ConnectionError('camera stream ended')
            h, w = frame.shape[:2]
            scale = min(1., 640/w, 480/h)
            if scale < 1:
                frame = cv2.resize(frame, (max(1, round(w*scale)), max(1, round(h*scale))))
            ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                raise RuntimeError('frame encoding failed')
            if not safe_send(context, 'video_frame', {'cameraId':camera,
                'frame':'data:image/jpeg;base64,'+base64.b64encode(encoded).decode()}):
                break
            if not ready:
                ready = True
                safe_send(context, 'camera_status', {'cameraId':camera, 'status':1})
                safe_send(context, 'stream_ready', {'cameraId':camera, 'status':1})
            task['stop'].wait(max(0, .2-(time.monotonic()-tick)))
    except FrameDecodeError:
        safe_send(context,'source_quality',{'cameraId':camera,'state':'CORRUPT'})
    except InterruptedError:
        pass
    except Exception:
        # Do not log tokens, source URLs or camera credentials.
        log.warning('Preview unavailable for camera %s', camera)
        safe_send(context, 'camera_status', {'cameraId':camera, 'status':0})
    finally:
        if capture is not None:
            capture.release()
        with lock:
            if stream_tasks.get(key) is task:
                del stream_tasks[key]
        safe_send(context, 'stream_stopped', {'cameraId':camera})


@app.get('/api/health')
def health():
    with lock:
        return jsonify(status='ok', activeStreams=len(stream_tasks))


def handle_websocket(ws):
    if not allowed_origin():
        ws.close(reason=1008, message='origin rejected')
        return
    context = {'id':str(id(ws)), 'ws':ws, 'closed':threading.Event(),
               'send_lock':threading.Lock(), 'grant':''}
    try:
        initial = json.loads(ws.receive(timeout=5) or '{}')
        if initial.get('type') != 'authenticate':
            raise PermissionError('authentication required')
        context['grant'] = initial.get('data', {}).get('grant', '')
        resolve_grant(context['grant'])
        with lock:
            if len(ws_tasks) >= 64:
                raise RuntimeError('connection capacity reached')
            ws_tasks[context['id']] = context
        safe_send(context, 'authenticated', {'cameraId':0})
        while not context['closed'].is_set():
            raw = ws.receive(timeout=1)
            if raw is None:
                continue
            message = json.loads(raw)
            data = message.get('data', {})
            camera = data.get('cameraId')
            if not isinstance(camera, int) or isinstance(camera, bool) or camera < 1:
                raise ValueError('camera ID required')
            # Every command rechecks a server-issued grant. Client URLs ignored.
            source = resolve_grant(context['grant'], camera)['videoUrl']
            if message.get('type') == 'start_stream':
                with lock:
                    key = (context['id'], camera)
                    existing = stream_tasks.get(key)
                    if existing:
                        if existing['stop'].is_set():
                            safe_send(context, 'stream_stopped', {'cameraId':camera})
                        continue
                    if len(stream_tasks) >= MAX_STREAMS:
                        safe_send(context, 'camera_status', {'cameraId':camera, 'status':0})
                        continue
                    task = {'stop':threading.Event()}
                    stream_tasks[key] = task
                    thread = threading.Thread(target=process_stream,args=(context,camera,task),daemon=True)
                    task['thread'] = thread
                    thread.start()
            elif message.get('type') == 'stop_stream':
                stop_camera(context, camera)
            elif message.get('type') == 'check_camera':
                stop = threading.Event()
                capture = None
                try:
                    capture = BoundedCapture(source, stop, timeout=5)
                    ok, frame = capture.read() if capture.isOpened() else (False, None)
                    safe_send(context, 'camera_status', {'cameraId':camera,'status':int(ok and frame is not None)})
                finally:
                    if capture is not None:
                        capture.release()
            else:
                raise ValueError('unsupported command')
    except Exception:
        try:
            ws.close(reason=1008, message='preview authorization or command rejected')
        except Exception:
            pass
    finally:
        cleanup_ws_tasks(context['id'])


sock.route('/ws')(handle_websocket)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Loopback by default; production exposes the same-origin reverse proxy.
    app.run(host=os.getenv('FLASK_HOST', '127.0.0.1'), port=int(os.getenv('FLASK_PORT', '5000')))
