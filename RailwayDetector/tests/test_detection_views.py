import sys,json,tempfile,unittest,threading,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
import av,numpy as np
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from detection_views import ResultFrames,LiveResults
from analysis_recording import AnalysisRecorder
from source_recording import VideoManifestOutbox
from media_budget import MediaBudget
from detections import Detection,TrackResult


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.start=datetime.now(timezone.utc)-timedelta(seconds=4)
        self.image=np.full((96,192,3),80,np.uint8)
        self.builder=ResultFrames({'videoId':'1','generation':3},'a'*32,'f'*64)
    def frame(self,index,seconds,detected=True,score=.8):
        detected=[Detection((10,20,80,70),12,'worker',score,0)] if detected else []
        tracks=[TrackResult((10,20,80,70),7,12,'worker',.99,0)] if detected else []
        observed=self.start+timedelta(seconds=seconds)
        return self.builder.build(self.image,detected,tracks,index,index*10,observed,observed+timedelta(milliseconds=100),True)
    def queue(self,folder):return VideoManifestOutbox(folder,'detector-1','http://localhost:18090/api','e'*40)
    def test_snapshot_keeps_current_score_not_historical_track_peak(self):
        meta,image=self.frame(1,0,score=.42)
        self.assertEqual(meta['objects'][0]['confidence'],.42);self.assertEqual(meta['objects'][0]['trackId'],'7')
        self.assertEqual(meta['objects'][0]['label'],'工人');self.assertEqual(image.shape,(96,192,3))
        self.assertEqual(meta['quality'],'DECODE_CHECKED')
    def test_trails_are_bounded_and_never_inherited_by_new_session(self):
        for index in range(60):meta,_=self.frame(index+1,index*.1)
        self.assertEqual(len(meta['trails'][0]['points']),30)
        other=ResultFrames({'videoId':'1'},'b'*32,'f'*64)
        empty,_=other.build(self.image,[],[],1,1,self.start,self.start,True)
        self.assertEqual(empty['trails'],[])
    def test_live_queue_is_bounded_per_camera_and_replaces_old_frames(self):
        uploader=LiveResults('detector-1','http://localhost/api','e'*40,max_cameras=2)
        for index in range(100):
            meta,image=self.frame(index+1,0);uploader.offer(meta,image)
        self.assertEqual(len(uploader.pending),1);self.assertEqual(uploader.dropped,99)
        for camera in ('2','3'):
            value=dict(meta,cameraId=camera);uploader.offer(value,image)
        self.assertEqual(len(uploader.pending),2)
    def test_live_upload_failure_is_disposable_and_not_a_critical_retry(self):
        def fail(*args,**kwargs):raise TimeoutError()
        uploader=LiveResults('detector-1','http://localhost/api','e'*40,opener=fail)
        uploader.offer(*self.frame(1,3));self.assertTrue(uploader.upload_once())
        self.assertEqual(len(uploader.pending),0);self.assertEqual(uploader.metrics()['liveResultState'],'ERROR')
    def test_live_rate_limit_preserves_the_latest_frame_without_more_inference(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'{"code":200}'
        sent=[]
        def post(request,**kwargs):sent.append(json.loads(request.data)['frameSeq']);return Response()
        uploader=LiveResults('detector-1','http://localhost/api','e'*40,opener=post,max_fps=2)
        with patch('detection_views.time.monotonic',return_value=10):
            uploader.offer(*self.frame(1,3));self.assertTrue(uploader.upload_once())
        with patch('detection_views.time.monotonic',return_value=10.1):
            uploader.offer(*self.frame(2,3));uploader.offer(*self.frame(3,3));self.assertFalse(uploader.upload_once())
        with patch('detection_views.time.monotonic',return_value=10.5):self.assertTrue(uploader.upload_once())
        self.assertEqual(sent,[1,3])
    def test_vfr_video_has_exact_sample_pts_and_real_elapsed_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            spool=self.queue(folder);budget=MediaBudget(folder,min_free_bytes=0)
            recorder=AnalysisRecorder({'videoId':'1'},'a'*32,spool,budget=budget)
            for index,seconds in enumerate((0,.75,2.25)):recorder.consume(*self.frame(index+1,seconds))
            recorder._close_clip()
            path=next(Path(folder).glob('*.mp4'))
            with av.open(str(path)) as clip:
                frames=list(clip.decode(video=0));self.assertEqual([round(frame.time,3) for frame in frames],[0.,.75,2.25]);self.assertAlmostEqual(clip.duration/1e6,2.75,places=2)
            envelope=json.loads(path.with_suffix('.analysis.json').read_text());manifest=json.loads(envelope['analysisJson'])
            self.assertEqual([frame['offsetMs'] for frame in manifest['frames']],[0,750,2250]);self.assertEqual(manifest['durationMs'],2750)
            self.assertEqual(spool.metrics()['recordingPending'],1)
            self.assertEqual(budget.used(),path.stat().st_size+path.with_suffix('.analysis.json').stat().st_size)
            spool.close()
    def test_empty_scene_does_not_create_sample_archive_but_target_includes_pre_roll(self):
        with tempfile.TemporaryDirectory() as folder:
            spool=self.queue(folder);recorder=AnalysisRecorder({'videoId':'1'},'a'*32,spool,budget=MediaBudget(folder,min_free_bytes=0))
            recorder.consume(*self.frame(1,0,False));recorder.consume(*self.frame(2,.75,False));self.assertFalse(list(Path(folder).glob('*.mp4')))
            recorder.consume(*self.frame(3,1.5));recorder._close_clip()
            manifest=json.loads(json.loads(next(Path(folder).glob('*.analysis.json')).read_text())['analysisJson'])
            self.assertEqual(manifest['frameCount'],3);self.assertEqual(manifest['frames'][0]['objects'],[]);spool.close()
    def test_restart_recovers_closed_samples_without_mutating_the_media(self):
        with tempfile.TemporaryDirectory() as folder:
            spool=self.queue(folder);recorder=AnalysisRecorder({'videoId':'1'},'a'*32,spool,budget=MediaBudget(folder,min_free_bytes=0))
            recorder.consume(*self.frame(1,0));recorder._close_clip()
            spool.db.execute('DELETE FROM pending');spool.db.execute('DELETE FROM cursor');spool.db.commit();spool.close()
            spool=self.queue(folder);spool.recover_once();self.assertEqual(spool.metrics()['recordingPending'],1)
            self.assertEqual(json.loads(spool.db.execute('SELECT body FROM pending').fetchone()[0])['kind'],'DETECTION_SAMPLES')
            spool.recover_once();self.assertEqual(spool.metrics()['recordingPending'],1);spool.close()
    def test_gap_splits_instead_of_stretching_the_last_picture_across_an_outage(self):
        with tempfile.TemporaryDirectory() as folder:
            spool=self.queue(folder);recorder=AnalysisRecorder({'videoId':'1'},'a'*32,spool,budget=MediaBudget(folder,min_free_bytes=0))
            recorder.consume(*self.frame(1,0));recorder.consume(*self.frame(2,5));recorder._close_clip()
            self.assertEqual(len(list(Path(folder).glob('*.analysis.json'))),2);spool.close()
    def test_archive_budget_failure_does_not_consume_critical_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            spool=self.queue(folder);recorder=AnalysisRecorder({'videoId':'1'},'a'*32,spool,budget=MediaBudget(folder,max_bytes=1,min_free_bytes=0))
            recorder.consume(*self.frame(1,0));self.assertEqual(recorder.state,'BUDGET_EXHAUSTED');self.assertEqual(spool.metrics()['recordingPending'],0);spool.close()

if __name__=='__main__':unittest.main()
