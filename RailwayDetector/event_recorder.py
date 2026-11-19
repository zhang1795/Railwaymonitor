"""Bounded pre-roll recording. Media errors never retract durable events."""
from collections import deque
import logging
import os
import time
import json
import hashlib
from datetime import datetime
from pathlib import Path
from media_budget import recording_budget
import cv2

log = logging.getLogger(__name__)


class EventRecorder:
    def __init__(self, prefix, fps, size, factory=cv2.VideoWriter, max_bytes=64*1024*1024,budget=None,clock=time.time):
        self.prefix, self.fps, self.size, self.factory = prefix, fps, size, factory
        self.max_bytes, self.buffer = max_bytes, deque()
        self.buffer_bytes, self.tail, self.writer, self.index, self.frames = 0, 0, None, 0, 0
        self.failed = False
        self.clock=clock;self.budget=budget or recording_budget(Path(prefix).parent)
        scale=min(1.,1280/max(1,size[0]),720/max(1,size[1]))
        self.scale=scale;self.size=(max(1,round(size[0]*scale)),max(1,round(size[1]*scale)))
        self.path=None;self.opened_at=None;self.sample_times=[];self.state='READY'
        self.last_detected=None

    def _finish(self):
        if self.writer is None:return
        path=self.path
        try:
            self.writer.release()
            if Path(path).is_file():
                os.chmod(path,0o600)
                manifest=Path(path).with_suffix('.railway-clip.json')
                value={'ownedBy':'railway-event-recorder-v1','file':Path(path).name,'kind':'SAMPLED_DETECTIONS',
                    'closedAt':self.clock(),'frameCount':self.frames,'playbackFps':self.fps,'sampleTimes':self.sample_times,
                    'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                manifest.write_text(json.dumps(value));manifest.chmod(0o600)
        finally:
            self.budget.observe(Path(path).name);self.budget.active.discard(Path(path).name);self.writer=None;self.sample_times=[]

    def _write(self, frame, observed=None):
        with self.budget.lock:
            if self.clock()-self.budget.last_prune>=60:
                self.budget.prune(self.clock());self.budget.last_prune=self.clock()
            if self.writer is not None and (self.clock()-self.opened_at>=60 or self.frames>=round(self.fps*60) or (Path(self.path).exists() and Path(self.path).stat().st_size+frame.nbytes+65536>16*1024**2)):
                self._finish()
            if not self.budget.allow(frame.nbytes+65536):
                self.state='BUDGET_EXHAUSTED';raise OSError('recording budget exhausted')
            self._write_frame(frame,observed)

    def _write_frame(self, frame,observed):
        if self.writer is None:
            self.index += 1
            self.path=self.prefix+'_'+str(self.index)+'.mp4'
            self.budget.active.add(Path(self.path).name)
            self.writer = self.factory(self.path,
                cv2.VideoWriter_fourcc(*'mp4v'), self.fps, self.size)
            if not self.writer.isOpened():
                raise RuntimeError('cannot open video writer')
            self.frames = 0
            self.opened_at=self.clock()
            if Path(self.path).exists():os.chmod(self.path,0o600)
        self.writer.write(frame)
        self.frames += 1
        if observed is not None:self.sample_times.append(str(observed))
        self.state='ACTIVE'

    def frame(self, image, results, observed=None):
        if self.failed:
            return
        try:
            at=datetime.fromisoformat(observed.replace('Z','+00:00')).timestamp() if observed else self.clock()
            while self.buffer and at-self.buffer[0][2]>2:
                self.buffer_bytes-=self.buffer.popleft()[0].nbytes
            if self.scale<1:image=cv2.resize(image,self.size)
            detected = bool(results)
            if detected:
                image = image.copy()
                for result in results:
                    x1,y1,x2,y2 = (round(value*self.scale) for value in result.bbox)
                    cv2.rectangle(image,(x1,y1),(x2,y2),(0,0,255),2)
                    cv2.putText(image,str(result.track_id)+':'+result.class_name+' '+format(result.confidence,'.2f'),
                                (x1,max(15,y1-5)),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,255),1)
            if detected:
                self.last_detected=at
                while self.buffer:
                    frame,observed_at,_=self.buffer.popleft();self._write(frame,observed_at)
                self.buffer_bytes = 0
                self.tail = max(1, round(2*self.fps))
            if detected or (self.last_detected is not None and at-self.last_detected<=2):
                self._write(image,observed)
                self.tail = max(0, self.tail-1)
                if not self.tail and self.writer is not None:
                    self._finish()
            else:
                if self.writer is not None:self._finish()
                while self.buffer and (len(self.buffer) >= max(1, round(2*self.fps)) or
                                       self.buffer_bytes+image.nbytes > self.max_bytes):
                    self.buffer_bytes -= self.buffer.popleft()[0].nbytes
                if image.nbytes <= self.max_bytes:
                    self.buffer.append((image.copy(),observed,at))
                    self.buffer_bytes += image.nbytes
        except Exception:
            self.failed = True
            if self.state!='BUDGET_EXHAUSTED':self.state='ERROR'
            log.exception('Event recording unavailable; detection continues')
            self.close()

    def close(self):
        self.buffer.clear()
        self.buffer_bytes = 0
        if self.writer is not None:
            try:
                self._finish()
            except Exception:
                log.exception('Recorder release failed')
            finally:
                self.writer = None
