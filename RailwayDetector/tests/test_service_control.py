import copy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from event_outbox import EventOutbox
from mqtt_service import DetectorService
from task_manager import TaskManager


class ServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.box=EventOutbox(self.folder.name+'/box.db','w1');self.addCleanup(self.box.close)
        self.started=[]
        self.ready=threading.Event()
        def worker(task):
            self.started.append(task.session_id);self.ready.set();task.mark_running();task.stop.wait(3)
        self.manager=TaskManager(worker,lease_seconds=30);self.addCleanup(self.manager.close)
        self.service=DetectorService.__new__(DetectorService)
        self.service.worker_id='w1';self.service.outbox=self.box;self.service.manager=self.manager
        self.statuses=[];self.service.status=self.statuses.append
        self.command=dict(protocolVersion=3,workerId='w1',cameraId='1',generation=1,
            sessionId='a'*32,enabled=True,videoUrl='rtsp://trusted/test',commandId='first',
            expiresAt=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat())

    def test_repeated_desired_command_shares_task_and_stale_start_cannot_revive(self):
        self.service.control(self.command)
        self.assertTrue(self.ready.wait(1))
        self.service.control(dict(self.command,commandId='renew'))
        self.assertEqual(self.manager.snapshot('1')['sessionId'],'a'*32)
        self.assertEqual(len(self.started),1)
        self.service.control(dict(self.command,enabled=False,generation=2,commandId='stop'))
        self.assertTrue(self.manager.wait('1'))
        self.service.control(dict(self.command,commandId='late-old-start'))
        self.assertEqual(self.manager.snapshot('1')['state'],'STOPPED')
        self.assertEqual(len(self.started),1)

    def test_ended_session_cannot_restart_with_reused_local_track_ids(self):
        self.service.control(self.command)
        self.assertTrue(self.ready.wait(1))
        self.manager.handle(dict(protocolVersion=2,action='stop',videoId='1',clientId='backend'))
        self.manager.wait('1')
        self.service.control(dict(self.command,commandId='renew-after-expiry'))
        self.assertTrue(self.statuses[-1]['lostSession'])
        self.assertEqual(len(self.started),1)
        self.service.control(dict(self.command,generation=2,sessionId='b'*32,commandId='new-session'))
        self.assertEqual(self.manager.snapshot('1')['sessionId'],'b'*32)

    def test_expired_commands_are_rejected_before_launch(self):
        value=dict(self.command,expiresAt=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
        with self.assertRaises(ValueError):self.service.control(value)
        self.assertEqual(self.started,[])
