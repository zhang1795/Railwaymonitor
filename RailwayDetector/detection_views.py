"""Frame-correlated results. Optional media never enters the critical outbox."""
import base64
import hashlib
import json
import math
import ssl
import threading
import time
from collections import OrderedDict
from datetime import timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import cv2
from track_events import CLASS_LABELS, CLASS_NAMES

_hashes = {}
_hash_lock = threading.Lock()


def model_hash(model):
    path = Path(model.weights).resolve()
    with _hash_lock:
        if str(path) not in _hashes:
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            _hashes[str(path)] = digest.hexdigest()
        return _hashes[str(path)]


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='milliseconds')


class ResultFrames:
    """One builder per task/session; current detections keep their own score."""
    def __init__(self, message, session, model_id):
        self.camera = str(message['videoId'])
        self.session, self.generation, self.model = session, int(message.get('generation', 1)), model_id
        self.trails = OrderedDict()

    def build(self, frame, observations, tracks, sequence, source_sequence, observed, processed, checked):
        height, width = frame.shape[:2]
        scale = min(640 / width, 480 / height, 1.)
        image = cv2.resize(frame, (max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)), interpolation=cv2.INTER_AREA)
        matches = {track.detection_index: str(track.track_id) for track in tracks}
        objects = []
        for detection in observations[:64]:
            if not detection.valid():
                continue
            x1, y1, x2, y2 = detection.bbox
            box = [max(0., min(1., x1 / width)), max(0., min(1., y1 / height)), max(0., min(1., x2 / width)), max(0., min(1., y2 / height))]
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            track_id = matches.get(detection.detection_index)
            label = CLASS_LABELS[CLASS_NAMES.index(detection.class_name)] if detection.class_name in CLASS_NAMES else detection.class_name
            objects.append({'bbox': [round(n, 6) for n in box], 'classId': detection.class_id,
                'className': detection.class_name, 'label': label, 'confidence': round(detection.confidence, 6), 'trackId': track_id})
            if track_id:
                self.trails.setdefault(track_id, []).append((observed.timestamp(), round((box[0] + box[2]) / 2, 6), round((box[1] + box[3]) / 2, 6)))
                self.trails.move_to_end(track_id)
        cutoff = observed.timestamp() - 10
        for key in list(self.trails):
            self.trails[key] = [point for point in self.trails[key][-30:] if point[0] >= cutoff]
            if not self.trails[key]:
                del self.trails[key]
        while len(self.trails) > 128:
            self.trails.popitem(last=False)
        visible = {obj['trackId'] for obj in objects if obj['trackId']}
        metadata = {'version': 1, 'cameraId': self.camera, 'sessionId': self.session, 'generation': self.generation,
            'frameSeq': sequence, 'sourceFrameSeq': source_sequence, 'observedAt': iso(observed), 'processedAt': iso(processed),
            'modelSha256': self.model, 'sourceWidth': width, 'sourceHeight': height, 'width': image.shape[1], 'height': image.shape[0],
            'quality': 'DECODE_CHECKED' if checked else 'UNVERIFIED', 'timeSource': 'DECODER_RECEIVED_AT',
            'objects': objects, 'totalObjects': len(observations), 'truncated': len(observations) > 64,
            'trails': [{'trackId': key, 'points': [[x, y] for _, x, y in self.trails[key]]} for key in visible]}
        return metadata, image


class LiveResults:
    """Bounded per-camera latest results; viewers do not cause inference work."""
    def __init__(self, worker, url, key, ca=None, opener=urlopen, max_cameras=9, max_fps=2.):
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('secure live-result endpoint required')
        if len(key) < 32:
            raise ValueError('live-result service identity required')
        self.worker, self.url, self.key, self.opener, self.limit = worker, url.rstrip('/'), key, opener, max_cameras
        self.context = ssl.create_default_context(cafile=ca or None)
        self.lock = threading.Lock(); self.pending = OrderedDict(); self.closed = threading.Event(); self.thread = None
        self.dropped = 0; self.error = ''; self.last_sent = OrderedDict(); self.period = 1 / max(.2, min(10., float(max_fps)))

    def offer(self, metadata, image):
        with self.lock:
            camera = metadata['cameraId']
            if camera in self.pending:
                self.dropped += 1
            self.pending[camera] = (metadata, image)
            if len(self.pending) > self.limit:
                self.pending.popitem(last=False); self.dropped += 1

    def upload_once(self):
        with self.lock:
            if not self.pending:
                return False
            now = time.monotonic()
            camera = next((key for key in self.pending if now - self.last_sent.get(key, -1e9) >= self.period), None)
            if camera is None:
                return False
            metadata, image = self.pending.pop(camera)
            self.last_sent[camera] = now; self.last_sent.move_to_end(camera)
            while len(self.last_sent) > self.limit:
                self.last_sent.popitem(last=False)
        if time.time() - __import__('datetime').datetime.fromisoformat(metadata['observedAt']).timestamp() > 5:
            self.dropped += 1; return True
        try:
            ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if not ok:
                raise ValueError('result image encoding failed')
            value = dict(metadata, workerId=self.worker, jpeg=base64.b64encode(encoded).decode('ascii'))
            body = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
            if len(body) > 512 * 1024:
                raise ValueError('result image too large')
            request = Request(self.url + '/_evidence/live-frame', body,
                {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key, 'X-Worker-Id': self.worker}, method='POST')
            with self.opener(request, timeout=2, context=self.context) as response:
                result = json.loads(response.read(4096))
                if response.status != 200 or result.get('code') != 200:
                    raise OSError('live-result rejected')
            self.error = ''
        except Exception as error:
            # Stale live pictures are disposable. Critical event delivery has
            # its own durable protocol and is never delayed by this uploader.
            self.error = 'live_http_' + str(error.code) if hasattr(error, 'code') else type(error).__name__
        return True

    def metrics(self):
        return {'liveResultState': 'ERROR' if self.error else 'ACTIVE', 'liveResultDropped': self.dropped}

    def start(self):
        def run():
            while not self.closed.wait(.05):
                self.upload_once()
        self.thread = threading.Thread(target=run, name='live-results', daemon=True); self.thread.start()

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(3)
