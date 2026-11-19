import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sendMsg

class Client:
    def __init__(self):
        self.connects=self.starts=self.stops=self.disconnects=self.sent=0
        self.on_connect=self.on_disconnect=None
    def connect(self,*args):
        self.connects+=1
        self.on_connect(self,None,None,0,None)
    def loop_start(self):self.starts+=1
    def loop_stop(self):self.stops+=1
    def disconnect(self):
        self.disconnects+=1
        self.on_disconnect(self,None,None,0,None)
    def publish(self,*args,**kwargs):
        self.sent+=1
        return Mock(rc=0)

class PublisherTests(unittest.TestCase):
    def publisher(self):
        client=Client()
        with patch('sendMsg.mqtt.Client',return_value=client):
            publisher=sendMsg.Publisher()
        self.addCleanup(publisher.close)
        return publisher,client

    def test_connects_once_under_concurrent_send(self):
        publisher,client=self.publisher()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _:publisher.send('{}'),range(12)))
        self.assertEqual((client.connects,client.starts,client.sent),(1,1,12))
        publisher.close();publisher.close()
        self.assertEqual((client.disconnects,client.stops),(1,1))

    def test_publish_failure_is_visible(self):
        publisher,client=self.publisher()
        client.publish=lambda *args,**kwargs:Mock(rc=4)
        with self.assertRaises(ConnectionError):publisher.send('{}')

    def test_status_delivery_never_waits_for_offline_connection(self):
        publisher,client=self.publisher()
        with self.assertRaises(ConnectionError):
            publisher.send('{}',ready_only=True)
        self.assertEqual(client.connects,0)

    def test_connection_failure_can_retry(self):
        publisher,client=self.publisher()
        with patch.object(client,'connect',side_effect=OSError('connect')):
            with self.assertRaises(OSError):publisher.send('{}')
        publisher.send('{}')
        self.assertEqual((client.starts,client.sent),(1,1))

    def test_disconnect_wait_is_bounded_and_reconnect_recovers(self):
        publisher,client=self.publisher()
        publisher.send('{}')
        client.on_disconnect(client,None,None,1,None)
        with patch.object(publisher._connected,'wait',return_value=False):
            with self.assertRaises(ConnectionError):publisher.send('{}')
        client.on_connect(client,None,None,0,None)
        publisher.send('{}')
        self.assertEqual(client.connects,1)
