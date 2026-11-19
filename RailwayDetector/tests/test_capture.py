import sys
import threading
import time
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
import os,subprocess,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_capture import BoundedCapture

def hung_reader(connection,url):
    connection.send((True,{}))
    time.sleep(60)

def never_ready(connection,url):
    time.sleep(60)

class CaptureTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'),'Linux parent-death contract')
    def test_hard_killed_parent_does_not_leave_native_decoder_running(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ready=root/'child.json';script=root/'parent.py'
            script.write_text("import sys,time,json\nfrom pathlib import Path\nsys.path.insert(0,"+repr(str(Path(__file__).resolve().parents[1]))+")\nsys.path.insert(0,"+repr(str(Path(__file__).resolve().parent))+")\nfrom video_capture import BoundedCapture\nfrom test_capture import hung_reader\nif __name__=='__main__':\n cap=BoundedCapture('unused',target=hung_reader)\n Path("+repr(str(ready))+").write_text(json.dumps({'pid':cap._process.pid}))\n time.sleep(60)\n")
            parent=subprocess.Popen([sys.executable,str(script)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+8
                while not ready.exists() and parent.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(ready.exists());pid=json.loads(ready.read_text())['pid']
                parent.kill();parent.wait(3)
                def stopped():
                    try:return (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[0]=='Z'
                    except FileNotFoundError:return True
                deadline=time.monotonic()+3
                while not stopped() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(stopped(),'native decoder survived its hard-killed parent')
            finally:
                if parent.poll() is None:parent.kill();parent.wait(3)
    def test_startup_timeout_reaps_child(self):
        import multiprocessing
        before={p.pid for p in multiprocessing.active_children()}
        with self.assertRaises(TimeoutError):
            BoundedCapture('unused',timeout=.15,target=never_ready)
        self.assertEqual({p.pid for p in multiprocessing.active_children()},before)

    def test_hung_read_is_bounded_and_process_reaped(self):
        capture = BoundedCapture('unused',timeout=5,target=hung_reader)
        capture.timeout = .15
        start = time.monotonic()
        try:
            with self.assertRaises(TimeoutError): capture.read()
        finally:
            capture.release()
        self.assertLess(time.monotonic()-start,3)
        capture.release()
        self.assertFalse(capture.isOpened())

    def test_stop_interrupts_waiting_read(self):
        stop = threading.Event()
        capture = BoundedCapture('unused',stop_event=stop,timeout=5,target=hung_reader)
        stop.set()
        try:
            with self.assertRaises(InterruptedError): capture.read()
        finally: capture.release()

    def test_real_video_read_and_eof(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'input.mp4')
            writer = cv2.VideoWriter(path,cv2.VideoWriter_fourcc(*'mp4v'),25,(32,32))
            self.assertTrue(writer.isOpened())
            for _ in range(3): writer.write(np.zeros((32,32,3),np.uint8))
            writer.release()
            capture = BoundedCapture(path,timeout=5)
            try:
                self.assertTrue(capture.isOpened())
                self.assertEqual(capture.get(cv2.CAP_PROP_FPS),25)
                for _ in range(3): self.assertTrue(capture.read()[0])
                self.assertFalse(capture.read()[0])
            finally: capture.release()
