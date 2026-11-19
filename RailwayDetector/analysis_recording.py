"""Unannotated inference samples + immutable, exactly correlated frame results.

This is an additional sampled view, never a replacement for full source video.
Encoding and spool writes run on a bounded optional-media worker.
"""
from collections import deque
from datetime import datetime
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import time

from media_budget import recording_budget
from source_recording import iso


class AnalysisRecorder:
    MAX_SAMPLES = 64
    MAX_SIDECAR = 2 * 1024 * 1024

    def __init__(self, message, session, outbox, *, max_fps=2., budget=None):
        self.message, self.session, self.outbox = message, session, outbox
        self.root = outbox.root; self.budget = budget or recording_budget(self.root)
        self.period = 1. / max(.1, min(5., float(max_fps)))
        self.queue = queue.Queue(maxsize=4); self.stop = threading.Event(); self.thread = None
        self.state = 'WAITING'; self.error = ''; self.dropped = 0; self.offered = None
        self.pre = deque(maxlen=12); self.container = None; self.entries = []; self.pending_packet = None
        self.active_until = 0.; self.last_stamp = None; self.file = None

    def offer(self, metadata, image):
        stamp = datetime.fromisoformat(metadata['observedAt']).timestamp()
        if self.offered is not None and 0 <= stamp - self.offered < self.period:
            return
        self.offered = stamp
        try:
            self.queue.put_nowait((metadata, image))
        except queue.Full:
            # Latest available inference samples matter more than an unbounded
            # backlog. The persisted clip reports the missing samples.
            try:
                self.queue.get_nowait(); self.dropped += 1
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait((metadata, image))
            except queue.Full:
                self.dropped += 1

    def _open(self, metadata, image):
        import av
        if not self.budget.allow(8 * 1024 * 1024):
            self.state = 'BUDGET_EXHAUSTED'; return False
        name = str(self.message['videoId']) + '_' + self.session + '_analysis_' + os.urandom(6).hex() + '.mp4'
        self.file = self.root / name; self.budget.active.add(name)
        self.started = datetime.fromisoformat(metadata['observedAt']).timestamp()
        self.base = {key: metadata[key] for key in ('cameraId', 'sessionId', 'generation', 'modelSha256', 'width', 'height', 'sourceWidth', 'sourceHeight')}
        marker = self.file.with_suffix('.analysis.writing.json')
        marker.write_text(json.dumps({'ownedBy': 'railway-analysis-v1', 'file': name, 'started': self.started})); marker.chmod(0o600)
        self.container = av.open(str(self.file), mode='w', format='mp4')
        self.stream = self.container.add_stream('libx264', rate=24)
        self.stream.width, self.stream.height = image.shape[1], image.shape[0]
        self.stream.pix_fmt = 'yuv420p'; self.stream.time_base = Fraction(1, 1000)
        self.stream.codec_context.time_base = Fraction(1, 1000); self.stream.codec_context.max_b_frames = 0
        self.stream.codec_context.thread_count = 1
        self.stream.options = {'preset': 'veryfast', 'crf': '23', 'tune': 'zerolatency'}
        self.entries = []; self.pending_packet = None; self.clip_dropped = self.dropped
        self.state = 'RECORDING'; return True

    def _packet(self, packet):
        if self.pending_packet is not None:
            delta = packet.pts * packet.time_base - self.pending_packet.pts * self.pending_packet.time_base
            self.pending_packet.duration = max(1, round(delta / self.pending_packet.time_base))
            self.container.mux(self.pending_packet)
        self.pending_packet = packet

    def _append(self, metadata, image):
        import av
        offset = round((datetime.fromisoformat(metadata['observedAt']).timestamp() - self.started) * 1000)
        if self.entries and offset <= self.entries[-1]['offsetMs']:
            return
        frame = av.VideoFrame.from_ndarray(image, format='bgr24'); frame.pts = offset; frame.time_base = Fraction(1, 1000)
        for packet in self.stream.encode(frame):
            self._packet(packet)
        self.entries.append({key: metadata[key] for key in ('frameSeq', 'sourceFrameSeq', 'observedAt', 'processedAt', 'quality', 'objects', 'totalObjects', 'truncated')})
        self.entries[-1]['offsetMs'] = offset

    def consume(self, metadata, image):
        stamp = datetime.fromisoformat(metadata['observedAt']).timestamp()
        if self.last_stamp is not None and (stamp <= self.last_stamp or stamp - self.last_stamp > 3):
            self._close_clip(); self.pre.clear(); self.active_until = 0
        self.last_stamp = stamp
        if self.container and (stamp - self.started >= 30 or len(self.entries) >= self.MAX_SAMPLES or stamp > self.active_until and not metadata['objects']):
            self._close_clip()
        while self.pre and stamp - datetime.fromisoformat(self.pre[0][0]['observedAt']).timestamp() > 2:
            self.pre.popleft()
        if metadata['objects']:
            self.active_until = stamp + 2
        if self.container is None and metadata['objects']:
            first = self.pre[0] if self.pre else (metadata, image)
            if self._open(*first):
                for earlier in self.pre:
                    self._append(*earlier)
                self.pre.clear()
        if self.container:
            self._append(metadata, image)
        else:
            self.pre.append((metadata, image))

    def _close_clip(self):
        if self.container is None:
            return
        container, path = self.container, self.file
        try:
            for packet in self.stream.encode(None):
                self._packet(packet)
            tail_ms = round(self.period * 1000)
            if self.pending_packet is not None:
                self.pending_packet.duration = max(1, round(Fraction(tail_ms, 1000) / self.pending_packet.time_base))
                container.mux(self.pending_packet)
            container.close(); self.container = None
            size = path.stat().st_size
            if not 0 < size <= 64 * 1024 * 1024:
                raise OSError('sample recording size invalid')
            duration = self.entries[-1]['offsetMs'] + tail_ms
            manifest = dict(self.base, version=1, kind='DETECTION_SAMPLES', timeSource='DECODER_RECEIVED_AT',
                sourceTimestampVerified=False, maxSampleFps=1 / self.period, durationMs=duration, frameCount=len(self.entries),
                droppedSamples=self.dropped - self.clip_dropped, frames=self.entries)
            raw = json.dumps(manifest, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            if len(raw) > self.MAX_SIDECAR:
                raise OSError('sample metadata too large')
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            name = path.name
            clip = hashlib.sha256((self.outbox.worker + '\n' + self.session + '\n' + name + '\n' + sha).encode()).hexdigest()
            value = dict(id=clip, workerId=self.outbox.worker, cameraId=str(self.message['videoId']), sessionId=self.session,
                file=name, sha256=sha, bytes=size, startedAt=iso(self.started), endedAt=iso(self.started + duration / 1000),
                kind='DETECTION_SAMPLES', clockSource='INFERENCE_SAMPLES_RECEIVED_AT', analysisSha256=hashlib.sha256(raw).hexdigest(), analysisBytes=len(raw))
            sidecar = path.with_suffix('.analysis.json'); temp = sidecar.with_suffix('.tmp')
            # Metadata contains the media checksum. Registration is separately
            # recoverable even after the in-memory optional writer disappears.
            envelope = {'registration': value, 'analysisJson': raw.decode('utf-8')}
            encoded = json.dumps(envelope, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            with temp.open('wb') as output:
                output.write(encoded); output.flush(); os.fsync(output.fileno())
            temp.chmod(0o600); temp.replace(sidecar); path.chmod(0o600)
            with path.open('rb') as source:
                os.fsync(source.fileno())
            descriptor = os.open(str(self.root), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self.outbox.enqueue(value); self.outbox.advance('analysis:' + name, 1)
            path.with_suffix('.analysis.writing.json').unlink(missing_ok=True)
            self.budget.observe(sidecar.name); self.state = 'WAITING'
        finally:
            if self.container is not None:
                self.container.close(); self.container = None
            self.pending_packet = None; self.budget.observe(path.name); self.budget.active.discard(path.name)

    def metrics(self):
        return {'analysisRecordingState': self.state, 'analysisDroppedSamples': self.dropped}

    def start(self):
        def run():
            try:
                while not self.stop.is_set() or not self.queue.empty():
                    try:
                        item = self.queue.get(timeout=.1)
                    except queue.Empty:
                        continue
                    self.consume(*item)
                self._close_clip()
            except Exception as error:
                self.error = type(error).__name__; self.state = 'ERROR'
                if self.container is not None:
                    try:
                        self.container.close()
                    except Exception:
                        pass
                    self.container = None
                if self.file:
                    self.budget.observe(self.file.name); self.budget.active.discard(self.file.name)
        self.thread = threading.Thread(target=run, name='analysis-samples', daemon=True); self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(5)
            if self.thread.is_alive():
                self.state = 'ERROR'; self.error = 'sample_encoder_shutdown_timeout'
