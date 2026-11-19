import json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from guardian import Guardian
from stop_managed import stop,process,expected
from stage_detector import stage_source_tree

class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runtime=self.root/'workspace/runtime';self.pids=self.runtime/'pids';self.pids.mkdir(parents=True)
        (self.runtime/'logs').mkdir();release=self.runtime/'releases/backend/example';release.mkdir(parents=True)
        script=self.root/'child.py';script.write_text('import time\ntime.sleep(600)\n')
        self.spec={'args':[sys.executable,str(script),'-jar',str(release/'backend.jar')],'cwd':str(self.root),'env':dict(os.environ),'startupGrace':9999}
        manifest=self.runtime/'managed-services.json';manifest.write_text(json.dumps({'backend':self.spec}));manifest.chmod(0o600)
        self.guardian=Guardian(self.root);self.addCleanup(self.guardian.lock.close)
        self.addCleanup(self.cleanup)
    def cleanup(self):
        path=self.pids/'backend.pid'
        if path.exists():
            pid=int(path.read_text())
            if pid==os.getpid():return
            try:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            except (ProcessLookupError,ChildProcessError):pass
        for child in self.guardian.children.values():child.poll()
    def test_killed_child_recovers_once_and_second_owner_is_refused(self):
        self.guardian.tick(1);first=int((self.pids/'backend.pid').read_text())
        with self.assertRaises(BlockingIOError):Guardian(self.root)
        self.guardian.tick(3);self.assertEqual(int((self.pids/'backend.pid').read_text()),first)
        os.kill(first,signal.SIGKILL);os.waitpid(first,0)
        self.guardian.tick(8);self.assertNotEqual(int((self.pids/'backend.pid').read_text()),first)
        self.assertEqual(self.guardian.states['backend']['failures'],2)
    def test_stop_refuses_unrelated_pid_and_keeps_file(self):
        path=self.pids/'backend.pid';path.write_text(str(os.getpid()))
        with self.assertRaisesRegex(RuntimeError,'identity mismatch'):stop('backend',self.root,seconds=.1)
        self.assertTrue(path.exists());self.assertIsNotNone(process(os.getpid()));path.unlink()
    def test_stop_waits_for_real_exit_and_removes_only_matching_pid(self):
        self.guardian.tick(1);pid=int((self.pids/'backend.pid').read_text())
        self.assertEqual(stop('backend',self.root,seconds=3),'stopped')
        self.assertFalse((self.pids/'backend.pid').exists());os.waitpid(pid,0)
    def test_gateway_source_stage_preserves_running_release(self):
        source=self.root/'gateway';source.mkdir();(source/'app.py').write_text('version=1')
        first=stage_source_tree(source,self.root/'releases',required=('app.py',));(source/'app.py').write_text('version=2')
        second=stage_source_tree(source,self.root/'releases',required=('app.py',))
        self.assertNotEqual(first,second);self.assertEqual((first/'app.py').read_text(),'version=1')
    def test_stalled_service_is_terminated_only_after_three_bad_checks(self):
        self.guardian.tick(1);pid=int((self.pids/'backend.pid').read_text())
        self.guardian.health=lambda *args:False
        self.guardian.tick(3);self.guardian.tick(5);self.assertIsNotNone(process(pid))
        self.guardian.tick(7)
        deadline=time.monotonic()+2
        while process(pid) is not None and time.monotonic()<deadline:time.sleep(.01)
        self.assertIsNone(process(pid));self.guardian.tick(10)
        self.assertNotEqual(int((self.pids/'backend.pid').read_text()),pid)
    def test_a_different_release_is_not_adopted_or_killed(self):
        self.guardian.tick(1);pid=int((self.pids/'backend.pid').read_text())
        self.guardian.specs['backend']['args'][-1]=str(self.runtime/'releases/backend/another/backend.jar')
        self.guardian.tick(5);self.assertEqual(self.guardian.states['backend']['error'],'pid_identity_mismatch');self.assertIsNotNone(process(pid))
    def test_local_demo_source_identity_cannot_match_other_projects_or_remote_publishers(self):
        args=[str(self.runtime/'tools/ffmpeg'),'-i',str(self.root/'worker.mp4'),'-f','rtsp','rtsp://127.0.0.1:8554/user_example']
        self.assertTrue(expected('user_stream',self.root,args,self.root))
        args[-1]='rtsp://remote.invalid:8554/user_example';self.assertFalse(expected('user_stream',self.root,args,self.root))
        args[-1]='rtsp://127.0.0.1:8554/user_example';args[2]='/other-project/video.mp4';self.assertFalse(expected('user_stream',self.root,args,self.root))

if __name__=='__main__':unittest.main()
