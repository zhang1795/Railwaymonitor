import json,sys,tempfile,unittest
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_recording import VideoManifestOutbox,SourceRecorder

class Response:
    status=200
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,limit):return b'{"code":200,"data":{"registered":true}}'

class RecordingSpoolTests(unittest.TestCase):
    def queue(self,root,**changes):return VideoManifestOutbox(root,'detector-1','http://127.0.0.1:18090/api','e'*40,**changes)
    def closed(self,queue,newline=True):
        recorder=SourceRecorder({'videoId':'1','videoUrl':'rtsp://user:supersecret@localhost/stream'},'a'*32,queue)
        name=recorder.prefix+'_000000.mp4';(queue.root/name).write_bytes(b'local-closed-segment')
        recorder.list.write_text(name+',0,5'+('\n' if newline else ''))
        return recorder
    def test_registration_retry_and_process_restart_keep_the_same_video(self):
        with tempfile.TemporaryDirectory() as folder:
            def unavailable(*args,**kwargs):raise HTTPError('local',425,'wait',{},None)
            queue=self.queue(folder,opener=unavailable);recorder=self.closed(queue);recorder._register_closed();queue.upload_once()
            self.assertEqual(queue.metrics()['recordingPending'],1);queue.close()
            sent=[]
            def post(request,**kwargs):sent.append(request);return Response()
            queue=self.queue(folder,opener=post);queue.db.execute('UPDATE pending SET due=0');queue.db.commit();queue.upload_once()
            self.assertEqual(queue.metrics()['recordingPending'],0)
            self.assertEqual(json.loads(sent[0].data)['kind'],'FULL_SOURCE')
            self.assertNotIn('supersecret',sent[0].data.decode());queue.close()
    def test_partial_segment_list_is_not_registered_and_cursor_prevents_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=self.queue(folder);recorder=self.closed(queue,newline=False);recorder._register_closed()
            self.assertEqual(queue.metrics()['recordingPending'],0)
            with recorder.list.open('a') as stream:stream.write('\n')
            recorder._register_closed();self.assertEqual(queue.metrics()['recordingPending'],1)
            queue.db.execute('DELETE FROM pending');queue.db.commit();recorder._register_closed()
            self.assertEqual(queue.metrics()['recordingPending'],0);queue.close()
    def test_full_spool_refuses_new_metadata_instead_of_silently_dropping_it(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=self.queue(folder,max_rows=1);value={'id':'a'*64};queue.enqueue(value);queue.enqueue(value)
            with self.assertRaises(OSError):queue.enqueue({'id':'b'*64})
            self.assertEqual(queue.metrics()['recordingPending'],1);queue.close()
    def test_recording_identity_and_remote_plaintext_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=self.queue(folder);queue.enqueue({'id':'a'*64,'bytes':1})
            with self.assertRaises(ValueError):queue.enqueue({'id':'a'*64,'bytes':2})
            queue.close()
            with self.assertRaises(ValueError):VideoManifestOutbox(folder,'detector-2','http://remote.invalid','e'*40)
    def test_closed_segment_recovers_after_spool_full_and_restart_without_replaying_committed_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=self.queue(folder,max_rows=1,opener=lambda *args,**kwargs:Response())
            recorder=self.closed(queue)
            (queue.root/(recorder.prefix+'.session.json')).write_text(json.dumps({'workerId':'detector-1','cameraId':'1','sessionId':recorder.session,'prefix':recorder.prefix,'started':recorder.started,'segmentSeconds':5}))
            queue.enqueue({'id':'occupied'});queue.recover_once();self.assertEqual(queue.metrics()['recordingPending'],1)
            queue.upload_once();queue.close()
            sent=[]
            def post(request,**kwargs):sent.append(json.loads(request.data));return Response()
            queue=self.queue(folder,opener=post);queue.recover_once();queue.upload_once();queue.recover_once()
            self.assertEqual(len(sent),1);self.assertEqual(sent[0]['kind'],'FULL_SOURCE');self.assertEqual(queue.metrics()['recordingPending'],0);queue.close()

if __name__=='__main__':unittest.main()
