import hashlib
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import sqlite3
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_outbox import EventOutbox, OutboxFull


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = self.folder.name+'/outbox.db'
        self.clock = [100.]
        self.box = EventOutbox(self.path, 'w1', max_events=2, clock=lambda:self.clock[0])
        self.addCleanup(lambda: self.box.close())
        self.body = json.dumps(dict(workerId='w1',eventId='event-1'))

    def ack(self, **changes):
        return dict(workerId='w1',eventId='event-1',status='APPLIED',
            payloadHash=hashlib.sha256(self.body.encode()).hexdigest(), **changes)

    def test_reopen_retains_unacknowledged_and_fences(self):
        self.box.enqueue(self.body)
        self.assertTrue(self.box.fence('1',3,'session3',False))
        self.box.close()
        self.box = EventOutbox(self.path,'w1',clock=lambda:self.clock[0])
        self.assertEqual(self.box.count(),1)
        self.assertFalse(self.box.fence('1',2,'session2',True))
        self.assertFalse(self.box.fence('1',3,'session3',True))
        self.assertTrue(self.box.acknowledge(self.ack()))
        self.assertEqual(self.box.count(),0)

    def test_protocol_publish_does_not_remove_and_backoff_is_bounded(self):
        self.box.enqueue(self.body)
        self.box.attempted('event-1')
        self.assertEqual(self.box.count(),1)
        self.assertEqual(self.box.due(),[])
        self.clock[0] += 1
        self.assertEqual(len(self.box.due()),1)
        for _ in range(20):
            self.box.attempted('event-1')
        self.clock[0] += 30
        self.assertEqual(len(self.box.due()),1)

    def test_wrong_ack_cannot_delete_and_rejection_is_audited(self):
        self.box.enqueue(self.body)
        value=self.ack();value['payloadHash']='wrong'
        self.assertFalse(self.box.acknowledge(value))
        value=self.ack();value['workerId']='other'
        self.assertFalse(self.box.acknowledge(value))
        value=self.ack();value['status']='REJECTED';value['reason']='bad score'
        self.assertTrue(self.box.acknowledge(value))
        self.assertEqual(self.box.db.execute('SELECT reason FROM rejected').fetchone()[0],'bad score')

    def test_capacity_and_event_id_conflict_preserve_existing(self):
        self.box.enqueue(self.body);self.box.enqueue(self.body)
        with self.assertRaises(ValueError):
            self.box.enqueue(json.dumps(dict(workerId='w1',eventId='event-1',changed=True)))
        self.box.enqueue(json.dumps(dict(workerId='w1',eventId='event-2')))
        with self.assertRaises(OutboxFull):
            self.box.enqueue(json.dumps(dict(workerId='w1',eventId='event-3')))
        self.assertEqual(self.box.count(),2)

    def test_process_exit_after_commit_replays_on_reopen(self):
        self.box.close()
        script="from event_outbox import EventOutbox; import os; b=EventOutbox("+repr(self.path)+",'w1'); b.enqueue("+repr(self.body)+"); os._exit(17)"
        result=subprocess.run([sys.executable,'-c',script],cwd=str(Path(__file__).resolve().parents[1]))
        self.assertEqual(result.returncode,17)
        self.box=EventOutbox(self.path,'w1')
        self.assertEqual(self.box.count(),1)
        self.assertEqual(self.box.due()[0]['body'],self.body)

    def test_duplicate_live_worker_cannot_share_outbox(self):
        with self.assertRaisesRegex(RuntimeError,'already owned'):
            EventOutbox(self.path,'w1')

    def test_sqlite_disk_full_rolls_back_new_event_and_preserves_previous(self):
        self.box.enqueue(self.body)
        pages=self.box.db.execute('PRAGMA page_count').fetchone()[0]
        self.box.db.execute('PRAGMA max_page_count='+str(pages))
        large=json.dumps(dict(workerId='w1',eventId='event-2',padding='x'*15000))
        with self.assertRaisesRegex(sqlite3.OperationalError,'full'):
            self.box.enqueue(large)
        self.assertEqual(self.box.count(),1)
        self.assertEqual(self.box.due()[0]['body'],self.body)
        self.box.db.execute('PRAGMA max_page_count=100000')
        self.assertTrue(self.box.acknowledge(self.ack()))

    def test_byte_budget_and_cross_worker_event_fail_without_evicting_pending(self):
        self.box.enqueue(self.body)
        self.box.max_bytes=len(self.body.encode())
        with self.assertRaises(OutboxFull):
            self.box.enqueue(json.dumps(dict(workerId='w1',eventId='event-2')))
        with self.assertRaises(ValueError):
            self.box.enqueue(json.dumps(dict(workerId='w2',eventId='event-2')))
        self.assertEqual(self.box.count(),1)
