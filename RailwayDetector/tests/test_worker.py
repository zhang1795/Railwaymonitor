import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ui
from detections import Detection
from tracker import Sort
from task_manager import TaskManager

class Capture:
    def __init__(self, frames=8, on_read=None):
        self.index=0
        self.frames=frames
        self.releases=0
        self.on_read=on_read
    def isOpened(self): return not self.releases
    def get(self,key):
        return {cv2.CAP_PROP_FPS:25, cv2.CAP_PROP_FRAME_WIDTH:64,
                cv2.CAP_PROP_FRAME_HEIGHT:48,
                cv2.CAP_PROP_POS_MSEC:(self.index-1)*40}.get(key,0.)
    def read(self):
        if self.index==self.frames: return False,None
        self.index+=1
        if self.on_read is not None: self.on_read(self.index)
        return True,np.zeros((48,64,3),np.uint8)
    def release(self): self.releases+=1

class Writer:
    def __init__(self,*args):
        self.path=args[0]
        self.releases=0
        self.frames=0
    def isOpened(self): return True
    def write(self,frame): self.frames+=1
    def release(self): self.releases+=1

class Detector:
    def __init__(self,fail=None):
        self.calls=0
        self.fail=fail
    def detect(self,frame,stop):
        self.calls+=1
        if self.fail: raise self.fail
        if self.calls in (6,7): return []
        return [Detection((5.,5.,25.,25.),12,'worker',.699,0)]

def message():
    return dict(videoId='test',videoUrl='file.mp4',deviceName='test',
                protocolVersion=2,clientId='test-client',startTime='2026-10-15T15:00:00Z')

class WorkerTests(unittest.TestCase):
    def run_worker(self, **changes):
        cap=changes.pop('cap',Capture())
        detector=changes.pop('detector',Detector())
        writers=[];messages=[]
        def writer(*args):
            value=Writer(*args);writers.append(value);return value
        with tempfile.TemporaryDirectory() as folder:
            ui.make_result(message(), detector=detector, capture_factory=lambda _:cap,
                writer_factory=writer, publish=messages.append, output_dir=folder, **changes)
        return cap,detector,writers,messages

    def test_import_does_not_connect_or_load_model(self):
        import subprocess
        code="from unittest.mock import patch; import sys; from paho.mqtt.client import Client; "+\
             "patch.object(Client,'connect',side_effect=AssertionError('network')).start(); import ui; assert 'model_init' not in sys.modules"
        subprocess.run([sys.executable,'-c',code],cwd=str(Path(ui.__file__).parent),check=True,timeout=15)

    def test_one_detection_per_frame_empty_aging_and_media_time(self):
        cap,detector,writers,messages=self.run_worker()
        self.assertEqual(detector.calls,8)
        first=json.loads(messages[0]);last=json.loads(messages[-1])
        self.assertEqual(first['confidence'],.699)
        self.assertEqual(first['firstSeen'],'2026-10-15T15:00:00.160+00:00')
        self.assertEqual(first['timeSource'],'media_time')
        self.assertEqual(last['state'],'ENDED')
        self.assertEqual(cap.releases,1)
        self.assertTrue(all(w.releases==1 for w in writers))
        self.assertEqual(writers[0].frames,8)

    def test_continuous_target_publishes_before_eof_and_updates_are_bounded(self):
        messages=[];counts=[]
        class Continuous(Detector):
            def detect(self,frame,stop):
                self.calls+=1
                return [Detection((5.,5.,25.,25.),12,'worker',.8,0)]
        cap=Capture(frames=300,on_read=lambda index:counts.append(len(messages)))
        with tempfile.TemporaryDirectory() as folder:
            ui.make_result(message(),detector=Continuous(),capture_factory=lambda _:cap,
                writer_factory=Writer,publish=messages.append,output_dir=folder,event_clock=lambda:0.)
        self.assertGreater(counts[5],0)
        self.assertEqual(len(messages),2) # first confirmed snapshot + final snapshot
        self.assertEqual(json.loads(messages[-1])['classEvidence']['12']['count'],296)

    def test_inference_failure_after_persistence_retains_event_and_marks_interrupted(self):
        messages=[];cap=Capture(frames=30)
        class Failing(Detector):
            def detect(self,frame,stop):
                self.calls+=1
                if self.calls==11:raise RuntimeError('inference')
                return [Detection((5.,5.,25.,25.),12,'worker',.8,0)]
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError,'inference'):
                ui.make_result(message(),detector=Failing(),capture_factory=lambda _:cap,
                    writer_factory=Writer,publish=messages.append,output_dir=folder)
        self.assertEqual(json.loads(messages[0])['state'],'ACTIVE')
        self.assertEqual(json.loads(messages[-1])['state'],'INTERRUPTED')
        self.assertEqual(cap.releases,1)

    def test_media_write_failure_does_not_stop_event_handoff(self):
        cap=Capture();messages=[];writers=[]
        def writer(*args):
            value=Writer(*args);writers.append(value)
            value.write=lambda frame:(_ for _ in ()).throw(RuntimeError('disk full'))
            return value
        with tempfile.TemporaryDirectory() as folder,self.assertLogs('event_recorder',level='ERROR'):
            ui.make_result(message(),detector=Detector(),capture_factory=lambda _:cap,
                writer_factory=writer,publish=messages.append,output_dir=folder)
        self.assertTrue(messages)
        self.assertEqual(json.loads(messages[-1])['state'],'ENDED')
        self.assertEqual(cap.releases,1)
        self.assertTrue(all(w.releases==1 for w in writers))

    def test_handoff_failure_is_visible_and_capture_released(self):
        cap=Capture()
        with tempfile.TemporaryDirectory() as folder,self.assertLogs('ui',level='ERROR'):
            with self.assertRaisesRegex(RuntimeError,'outbox full'):
                ui.make_result(message(),detector=Detector(),capture_factory=lambda _:cap,
                    writer_factory=Writer,publish=lambda _:(_ for _ in ()).throw(RuntimeError('outbox full')),output_dir=folder)
        self.assertEqual(cap.releases,1)

    def test_stop_flushes_pending_track_without_waiting_for_media(self):
        stop=threading.Event();cap=Capture(frames=20,on_read=lambda index:stop.set() if index==6 else None)
        from task_manager import Task
        task=Task(message(),stop=stop);task._running=lambda _:None
        _,_,_,messages=self.run_worker(cap=cap,task=task)
        self.assertEqual(json.loads(messages[-1])['state'],'ENDED')

    def test_unexpected_live_eof_fails_and_releases_capture(self):
        cap=Capture(frames=0);value=message();value['videoUrl']='rtsp://test'
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ConnectionError,'ended unexpectedly'):
                ui.make_result(value,detector=Detector(),capture_factory=lambda _:cap,
                    writer_factory=Writer,publish=lambda _:None,output_dir=folder)
        self.assertEqual(cap.releases,1)

    def test_corrupt_input_never_reaches_model_and_does_not_clear_a_target(self):
        from strict_capture import FrameDecodeError
        from task_manager import Task
        def damaged(index):
            if index==9:raise FrameDecodeError()
        class Continuous(Detector):
            def detect(self,frame,stop):
                self.calls+=1
                return [Detection((5.,5.,25.,25.),12,'worker',.8,0)]
        cap=Capture(frames=12,on_read=damaged);model=Continuous();events=[]
        task=Task(message());task._running=lambda _:None
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FrameDecodeError):
                ui.make_result(message(),task=task,detector=model,capture_factory=lambda _:cap,
                    writer_factory=Writer,publish=events.append,output_dir=folder)
        self.assertEqual(model.calls,8);self.assertEqual(cap.releases,1)
        self.assertEqual(json.loads(events[-1])['state'],'INTERRUPTED')
        self.assertEqual(task.progress['sourceQuality'],'CORRUPT')

    def test_optional_live_view_failure_cannot_discard_confirmed_events(self):
        value=message();value['videoUrl']='rtsp://test';cap=Capture();events=[]
        class BrokenView:
            def offer(self,*args):raise OSError('optional view failed')
        with tempfile.TemporaryDirectory() as folder,patch('detection_views.model_hash',return_value='f'*64),self.assertLogs('ui',level='WARNING'):
            with self.assertRaises(ConnectionError):
                ui.make_result(value,detector=Detector(),capture_factory=lambda _:cap,publish=events.append,
                    sampled_recording=False,output_dir=folder,live_results=BrokenView())
        self.assertEqual(json.loads(events[0])['state'],'ACTIVE');self.assertEqual(json.loads(events[-1])['state'],'INTERRUPTED');self.assertEqual(cap.releases,1)
