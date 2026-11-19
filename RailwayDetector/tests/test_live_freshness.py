import os,struct,sys,threading,time,unittest,tempfile,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_capture import BoundedCapture,_latest_loop
from inference_gate import FairInferenceGate
from media_budget import MediaBudget
from event_recorder import EventRecorder
from detections import TrackResult

class LiveSource:
    def __init__(self):self.number=0
    def read(self):
        time.sleep(.01);self.number+=1
        return True,np.full((16,16,3),self.number%255,dtype=np.uint8)
    def get(self,key):return self.number*10.
    def release(self):pass

def latest(connection,url):
    connection.send((True,{}));_latest_loop(connection,LiveSource())

def partial(connection,url):
    connection.send((True,{}));connection.recv()
    os.write(connection.fileno(),struct.pack('!i',8_000_000)+b'abc')
    time.sleep(60)

class FreshnessTests(unittest.TestCase):
    def test_legacy_preview_receives_the_original_three_field_reply(self):
        import multiprocessing
        context=multiprocessing.get_context('spawn');parent,child=context.Pipe()
        process=context.Process(target=latest,args=(child,'unused'),daemon=True);process.start();child.close()
        try:
            self.assertTrue(parent.poll(5));self.assertTrue(parent.recv()[0])
            parent.send('read');self.assertTrue(parent.poll(3));self.assertEqual(len(parent.recv()),3)
        finally:process.terminate();process.join(2);parent.close()
    def test_slow_consumer_gets_latest_and_reports_skipped_frames(self):
        capture=BoundedCapture('unused',target=latest)
        try:
            self.assertTrue(capture.read()[0]);first=capture.decoded_frames
            time.sleep(.2);self.assertTrue(capture.read()[0])
            self.assertGreater(capture.decoded_frames-first,5)
            self.assertGreater(capture.skipped_frames,4)
            self.assertLess(time.time()-capture.frame_received_at,.15)
        finally:capture.release()
    def test_partially_written_ipc_frame_cannot_defeat_timeout(self):
        capture=BoundedCapture('unused',target=partial);capture.timeout=.15
        start=time.monotonic()
        try:
            with self.assertRaises(TimeoutError):capture.read()
        finally:capture.release()
        self.assertLess(time.monotonic()-start,3)
        self.assertFalse(capture._receiver.is_alive())
    def test_model_gate_is_fifo_and_a_cancelled_waiter_does_not_block_others(self):
        gate=FairInferenceGate();order=[];threads=[];cancel=threading.Event()
        def work(index):
            try:
                with gate.hold(cancel if index==1 else None):order.append(index)
            except InterruptedError:order.append('cancelled')
        with gate.hold():
            for index in range(4):
                thread=threading.Thread(target=work,args=(index,));thread.start();threads.append(thread)
                deadline=time.monotonic()+1
                while len(gate.waiters)<index+1 and time.monotonic()<deadline:time.sleep(.005)
            cancel.set();time.sleep(.1)
        for thread in threads:thread.join(2);self.assertFalse(thread.is_alive())
        self.assertEqual([item for item in order if item!='cancelled'],[0,2,3])
        self.assertIn('cancelled',order)

class RecordingBudgetTests(unittest.TestCase):
    def test_full_budget_stops_optional_recording(self):
        with tempfile.TemporaryDirectory() as folder:
            budget=MediaBudget(folder,max_bytes=1,min_free_bytes=0)
            recorder=EventRecorder(str(Path(folder)/'camera_session'),25,(32,32),budget=budget)
            with self.assertLogs('event_recorder',level='ERROR'):
                recorder.frame(np.zeros((32,32,3),np.uint8),[TrackResult((1,1,20,20),1,12,'worker',.9,0)])
            self.assertEqual(recorder.state,'BUDGET_EXHAUSTED');self.assertTrue(recorder.failed)
    def test_wall_clock_rotates_slow_inference_clips_and_keeps_sample_times(self):
        with tempfile.TemporaryDirectory() as folder:
            clock=[0.];budget=MediaBudget(folder,min_free_bytes=0)
            recorder=EventRecorder(str(Path(folder)/'camera_session'),25,(32,32),budget=budget,clock=lambda:clock[0])
            image=np.zeros((32,32,3),np.uint8);detected=[TrackResult((1,1,20,20),1,12,'worker',.9,0)]
            recorder.frame(image,detected,'2026-11-11T00:00:00Z');clock[0]=61
            recorder.frame(image,detected,'2026-11-11T00:01:01Z');recorder.close()
            manifests=list(Path(folder).glob('*.railway-clip.json'));self.assertEqual(len(manifests),2)
            for path in manifests:
                value=json.loads(path.read_text());self.assertEqual(value['kind'],'SAMPLED_DETECTIONS')
                self.assertEqual(value['frameCount'],1);self.assertEqual(len(value['sampleTimes']),1)
    def test_retention_never_deletes_unmanaged_or_active_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);budget=MediaBudget(root,retention_days=30,min_free_bytes=0)
            for name in ('closed.mp4','active.mp4','unmanaged.mp4'):(root/name).write_bytes(b'owned-test')
            for name in ('closed.mp4','active.mp4'):(root/name).with_suffix('.railway-clip.json').write_text(json.dumps({'ownedBy':'railway-event-recorder-v1','file':name,'closedAt':1}))
            budget.active.add('active.mp4');self.assertEqual(budget.prune(now=31*86400),1)
            self.assertTrue((root/'active.mp4').exists());self.assertTrue((root/'unmanaged.mp4').exists())

if __name__=='__main__':unittest.main()
