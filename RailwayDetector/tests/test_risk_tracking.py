import json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tracker import Sort
from detections import Detection,TrackResult
from track_events import TrackEvents

class TimeTrackingTests(unittest.TestCase):
    def test_same_three_second_grace_at_different_fps(self):
        detection=Detection((10,20,100,120),12,'worker',.8)
        for fps in (2,10,25):
            tracker=Sort(min_hits=1,max_idle_seconds=3)
            first=tracker.update_detections([detection],timestamp=0)[0].track_id
            for frame in range(1,2*fps+1):tracker.update_detections([],timestamp=frame/fps)
            self.assertEqual(tracker.update_detections([detection],timestamp=2.1)[0].track_id,first)
            tracker.update_detections([],timestamp=5.2)
            self.assertNotEqual(tracker.update_detections([detection],timestamp=5.3)[0].track_id,first)
    def test_malformed_or_regressed_clock_rejected(self):
        tracker=Sort(max_idle_seconds=3);tracker.update_detections([],timestamp=5)
        for stamp in (4,float('nan'),float('inf')):
            with self.assertRaises(ValueError):tracker.update_detections([],timestamp=stamp)

class RiskSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.output=[];self.time=0
        self.start=datetime(2026,11,10,tzinfo=timezone.utc)
        self.events=TrackEvents({'videoId':1,'generation':1,'trackGraceSeconds':3},'a'*32,
            lambda data:self.output.append(json.loads(data)),clock=lambda:self.time)
        self.result=TrackResult((10,20,100,120),1,12,'worker',.8,0)
    def update(self,t,results=(),alive=(),raw=()):
        self.time=t;at=self.start+timedelta(seconds=t)
        self.events.update(results,alive,at,'received_at',at,(480,640,3),raw)
    def test_missing_resume_then_verified_absence(self):
        self.update(0,[self.result],[1]);self.update(.1,[],[1]);self.update(2,[self.result],[1])
        self.assertEqual([row['state'] for row in self.output],['ACTIVE','MISSING','ACTIVE'])
        self.update(3,[],[]);self.update(5.9,[],[])
        self.assertNotEqual(self.output[-1]['state'],'ENDED')
        self.update(6,[],[])
        self.assertEqual((self.output[-1]['state'],self.output[-1]['reason']),('ENDED','confirmed_absence'))
        self.assertEqual(self.output[-1]['observedThrough'],'2026-11-10T00:00:06.000+00:00')
    def test_one_observation_after_long_processing_gap_does_not_prove_clearance(self):
        self.update(0,[self.result],[1]);self.update(20,[],[])
        self.assertEqual(self.output[-1]['state'],'MISSING')
        self.update(22,[],[]);self.assertEqual(self.output[-1]['state'],'MISSING')
    def test_unconfirmed_nearby_detection_marks_identity_uncertain(self):
        self.update(0,[self.result],[1]);self.update(1,[],[])
        self.update(4,[],[],[Detection(self.result.bbox,12,'worker',.8)])
        self.assertEqual(self.output[-1]['state'],'INTERRUPTED')
        self.assertEqual(self.output[-1]['reason'],'identity_uncertain')
    def test_evidence_failure_never_retracts_durable_metadata(self):
        self.events.on_snapshot=lambda event:(_ for _ in ()).throw(OSError('full'))
        with self.assertLogs('track_events',level='ERROR'):self.update(0,[self.result],[1])
        self.assertEqual(len(self.output),1)
        self.assertEqual(self.output[0]['protocolVersion'],4)

if __name__=='__main__':unittest.main()
