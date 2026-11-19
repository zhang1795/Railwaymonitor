import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task_manager import TaskManager

def request(action='start', owner='a', **changes):
    value = dict(action=action, videoId='1', videoUrl='camera', clientId=owner,
                 protocolVersion=2, startTime='2026-10-15T15:00:00Z')
    value.update(changes)
    return value

def waiting(task):
    task.mark_running()
    task.stop.wait(3)

class TaskTests(unittest.TestCase):
    def manager(self, worker=waiting, **kwargs):
        manager = TaskManager(worker, **kwargs)
        self.addCleanup(manager.close)
        return manager

    def test_concurrent_duplicate_start_has_one_worker(self):
        entered = []
        def worker(task):
            entered.append(task.session_id)
            waiting(task)
        manager = self.manager(worker)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _:manager.handle(request()), range(20)))
        self.assertEqual(len({r['sessionId'] for r in results}), 1)
        self.assertEqual(len(entered), 1)

    def test_owner_reference_count_and_stale_stop(self):
        manager = self.manager()
        a = manager.handle(request())
        manager.handle(request(owner='b'))
        manager.handle(request('stop', sessionId='old'))
        self.assertNotEqual(manager.snapshot('1')['state'], 'STOPPING')
        manager.handle(request('stop', sessionId=a['sessionId']))
        self.assertEqual(manager.snapshot('1')['owners'], 1)
        manager.handle(request('stop', owner='b', sessionId=a['sessionId']))
        self.assertTrue(manager.wait('1'))
        self.assertEqual(manager.snapshot('1')['state'], 'STOPPED')
        self.assertEqual(manager.handle(request('stop'))['state'], 'STOPPED')

    def test_expiry_and_heartbeat(self):
        clock = [0.]
        manager = self.manager(clock=lambda:clock[0], lease_seconds=20)
        manager.handle(request())
        clock[0] = 19
        manager.handle(request('heartbeat'))
        clock[0] = 21
        manager.sweep()
        self.assertEqual(manager.snapshot('1')['owners'], 1)
        clock[0] = 40
        manager.sweep()
        self.assertTrue(manager.wait('1'))
        self.assertEqual(manager.snapshot('1')['state'], 'STOPPED')

    def test_legacy_request_can_restart_after_failure(self):
        calls = []
        def worker(task):
            calls.append(task.session_id)
            raise RuntimeError('injected')
        manager = self.manager(worker)
        old = dict(videoId='1', videoUrl='camera', startTime='2026-10-15 15:00:00')
        with self.assertLogs('task_manager',level='ERROR'):
            first = manager.handle(old)
            manager.wait('1')
            self.assertEqual(manager.snapshot('1')['state'], 'FAILED')
            second = manager.handle(old)
            manager.wait('1')
        self.assertNotEqual(first['sessionId'], second['sessionId'])
        self.assertEqual(len(calls), 2)

    def test_request_replay_does_not_restart_completed_task(self):
        manager = self.manager(lambda task:None)
        first = manager.handle(request(requestId='r'))
        manager.wait('1')
        replay = manager.handle(request(requestId='r'))
        self.assertEqual(replay['state'],'STOPPED')
        self.assertEqual(replay['sessionId'],first['sessionId'])
        self.assertTrue(replay['duplicate'])
        next_task = manager.handle(request(requestId='next'))
        self.assertNotEqual(next_task['sessionId'],first['sessionId'])

    def test_url_conflict_limit_and_input_validation(self):
        manager = self.manager(max_tasks=1)
        manager.handle(request())
        with self.assertRaises(ValueError): manager.handle(request(videoUrl='other'))
        with self.assertRaises(ValueError): manager.handle(request(videoId='2'))
        with self.assertRaises(ValueError): manager.handle(request(action='unknown'))
        with self.assertRaises(ValueError): manager.handle(request(videoId=''))
        with self.assertRaises(ValueError): manager.handle(request(videoUrl=None))
        with self.assertRaises(ValueError): manager.handle(request(videoId='3',startTime='bad'))

    def test_terminal_revision_is_newer_than_stop(self):
        manager = self.manager()
        manager.handle(request())
        stop = manager.handle(request('stop'))
        manager.wait('1')
        final = manager.snapshot('1')
        self.assertEqual(final['state'], 'STOPPED')
        self.assertGreater(final['revision'],stop['revision'])

    def test_reaper_closes_cleanly(self):
        manager = self.manager()
        manager.start_reaper()
        manager.close()
        self.assertFalse(manager._reaper.is_alive())
        with self.assertRaises(RuntimeError): manager.handle(request())

    def test_fast_terminal_status_correlates_with_start_before_ack(self):
        statuses=[]
        manager=self.manager(lambda task:None,status_sink=statuses.append)
        manager.handle(request(requestId='initial-start'))
        manager.wait('1')
        terminal=[s for s in statuses if s['state']=='STOPPED']
        self.assertEqual(len(terminal),1)
        self.assertEqual((terminal[0]['clientId'],terminal[0]['requestId']),
                         ('a','initial-start'))

    def test_all_holders_receive_correlated_terminal_status(self):
        statuses=[]
        manager=self.manager(status_sink=statuses.append)
        manager.handle(request(requestId='start-a'))
        manager.handle(request(owner='b',requestId='start-b'))
        manager.handle(request('stop'))
        manager.handle(request('stop',owner='b'))
        manager.wait('1')
        terminal=[s for s in statuses if s['state']=='STOPPED']
        self.assertEqual({(s['clientId'],s['requestId']) for s in terminal},
                         {('a','start-a'),('b','start-b')})

    def test_new_protocol_cannot_create_an_unleased_legacy_owner(self):
        manager=self.manager()
        for client_id in [None, '', 'legacy', []]:
            with self.assertRaises(ValueError):
                manager.handle(request(clientId=client_id))

    def test_status_network_failure_does_not_prevent_cleanup(self):
        def fail(_):raise ConnectionError('status unavailable')
        manager=self.manager(status_sink=fail)
        with self.assertLogs('task_manager',level='ERROR'):
            manager.handle(request())
            manager.handle(request('stop'))
            self.assertTrue(manager.wait('1'))
        self.assertEqual(manager.snapshot('1')['state'],'STOPPED')
