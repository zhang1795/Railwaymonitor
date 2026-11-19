import importlib
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
gateway=importlib.import_module('app')


class Socket:
    def __init__(self,messages=()):self.messages=iter(messages);self.closed=False;self.sent=[]
    def receive(self,timeout=None):return next(self.messages)
    def send(self,value):self.sent.append(value)
    def close(self,**kwargs):self.closed=True


class PreviewSecurityTests(unittest.TestCase):
    def tearDown(self):gateway.stream_tasks.clear();gateway.ws_tasks.clear()

    def test_origin_is_required_and_cross_origin_is_rejected(self):
        for origin in (None,'https://attacker.invalid'):
            headers={'Origin':origin} if origin else {}
            ws=Socket()
            with gateway.app.test_request_context('/ws',headers=headers):gateway.handle_websocket(ws)
            self.assertTrue(ws.closed)

    def test_first_frame_must_authenticate_and_invalid_grant_cannot_start(self):
        for message in ('{"type":"start_stream","data":{"cameraId":1}}',
                        '{"type":"authenticate","data":{"grant":"invalid"}}'):
            ws=Socket([message])
            with gateway.app.test_request_context('/ws',headers={'Origin':'http://localhost:3000'}),\
                 patch.object(gateway,'resolve_grant',side_effect=PermissionError('revoked')):
                gateway.handle_websocket(ws)
            self.assertTrue(ws.closed);self.assertEqual(len(gateway.stream_tasks),0)

    def test_one_viewer_cannot_stop_or_delete_another_viewer(self):
        a={'closed':threading.Event(),'id':'a'};b={'closed':threading.Event(),'id':'b'}
        gateway.ws_tasks.update(a=a,b=b)
        first={'stop':threading.Event()};second={'stop':threading.Event()}
        gateway.stream_tasks.update({('a',1):first,('b',1):second})
        gateway.cleanup_ws_tasks('a')
        self.assertTrue(first['stop'].is_set());self.assertFalse(second['stop'].is_set())
        self.assertIs(gateway.stream_tasks[('b',1)],second)
        self.assertFalse(b['closed'].is_set())

    def test_revoked_grant_stops_stream_and_releases_decoder(self):
        class Capture:
            released=False
            def isOpened(self):return True
            def release(self):self.released=True
        cap=Capture();ws=Socket()
        context={'id':'a','closed':threading.Event(),'ws':ws,'send_lock':threading.Lock(),'grant':'test'}
        task={'stop':threading.Event()};gateway.stream_tasks[('a',1)]=task
        with patch.object(gateway,'resolve_grant',side_effect=[{'videoUrl':'rtsp://trusted'},PermissionError('revoked')]),\
             patch.object(gateway,'BoundedCapture',return_value=cap):
            gateway.process_stream(context,1,task)
        self.assertTrue(cap.released);self.assertNotIn(('a',1),gateway.stream_tasks)

    def test_missing_service_secret_fails_closed(self):
        with patch.dict('os.environ',{'PREVIEW_SERVICE_KEY':''}):
            with self.assertRaises(PermissionError):gateway.resolve_grant('anything',1)
