import sys,tempfile,unittest,hashlib
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_outbox import EvidenceOutbox

class Response:
    status=200
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,limit):return b'{"code":200,"data":{"stored":true}}'

class EvidenceTests(unittest.TestCase):
    def make(self,path,**kw):return EvidenceOutbox(path,'detector-1','http://127.0.0.1:18090/api','e'*40,**kw)
    def test_durable_retry_after_backend_or_metadata_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'evidence.sqlite3'
            def fail(*args,**kwargs):raise HTTPError('http://127.0.0.1:18090',425,'wait',{},None)
            queue=self.make(path,opener=fail);queue.enqueue('a'*32,b'jpeg');queue.upload_once()
            for file in (path,Path(str(path)+'-wal'),Path(str(path)+'-shm')):
                if file.exists():self.assertEqual(file.stat().st_mode & 0o777,0o600)
            self.assertEqual(queue.metrics()['evidencePending'],1);queue.close()
            received=[]
            def upload(req,**kwargs):received.append(req);return Response()
            queue=self.make(path,opener=upload);queue.db.execute('UPDATE images SET due=0');queue.db.commit();queue.upload_once()
            self.assertEqual(queue.metrics()['evidencePending'],0)
            self.assertEqual(received[0].data,b'jpeg');self.assertEqual(received[0].headers['X-worker-id'],'detector-1');queue.close()
    def test_bytes_and_row_budgets_are_independent_of_critical_events(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=self.make(Path(folder)/'e.sqlite3',max_rows=2,max_bytes=8)
            self.assertTrue(queue.enqueue('a'*32,b'12345'));self.assertFalse(queue.enqueue('b'*32,b'12345'))
            self.assertEqual(queue.metrics()['evidencePending'],1);self.assertEqual(queue.metrics()['evidenceSkipped'],1);queue.close()
    def test_identity_conflicts_and_cross_worker_reuse_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'e.sqlite3';queue=self.make(path);queue.enqueue('a'*32,b'one')
            with self.assertRaises(ValueError):queue.enqueue('a'*32,b'two')
            queue.close()
            with self.assertRaises(ValueError):EvidenceOutbox(path,'detector-2','http://localhost:18090/api','e'*40)
    def test_invalid_picture_rejection_is_bounded_and_does_not_retry_forever(self):
        with tempfile.TemporaryDirectory() as folder:
            def fail(*args,**kwargs):raise HTTPError('http://localhost',400,'invalid',{},None)
            queue=self.make(Path(folder)/'e.sqlite3',opener=fail);queue.enqueue('a'*32,b'bad');queue.upload_once()
            self.assertEqual(queue.metrics()['evidencePending'],0)
            self.assertEqual(queue.db.execute('SELECT reason FROM failures').fetchone()[0],'evidence_http_400');queue.close()
    def test_remote_plaintext_credentials_and_embedded_passwords_are_refused(self):
        for url in ('http://remote.invalid/api','https://user:password@example.com/api'):
            with self.assertRaises(ValueError):EvidenceOutbox('/tmp/not-created-evidence.sqlite3','detector-1',url,'e'*40)
    def test_capture_saves_a_real_resized_jpeg(self):
        import cv2,numpy as np
        with tempfile.TemporaryDirectory() as folder:
            queue=self.make(Path(folder)/'e.sqlite3')
            queue.capture({'state':'ACTIVE','sessionId':'b'*32,'trackId':'1','eventId':'a'*32,'bbox':[10,20,200,300],'className':'worker','confidence':.8},np.zeros((1080,1920,3),dtype=np.uint8))
            body=queue.db.execute('SELECT body FROM images').fetchone()[0]
            image=cv2.imdecode(np.frombuffer(body,dtype=np.uint8),cv2.IMREAD_COLOR)
            self.assertLessEqual(image.shape[1],640);self.assertLessEqual(image.shape[0],480);queue.close()

if __name__=='__main__':unittest.main()
