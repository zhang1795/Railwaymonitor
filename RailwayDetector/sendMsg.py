"""Lazy MQTT publisher. Importing this module does not open a connection."""
import os
import threading
import paho.mqtt.client as mqtt

HOST = os.getenv('MQTT_HOST','127.0.0.1')
PORT = int(os.getenv('MQTT_PORT','1883'))
ALARM_TOPIC = os.getenv('MQTT_ALARM_TOPIC','/UAV/videoAlarmTopic/post')
STATUS_TOPIC = os.getenv('MQTT_STATUS_TOPIC','/UAV/videoTaskStatus/post')

class Publisher:
    def __init__(self, host=HOST, port=PORT):
        self.host, self.port = host,port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.connect_timeout = 5
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = lambda *args: self._connected.clear()
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._started = False

    def _on_connect(self,client,userdata,flags,reason,properties):
        if reason == 0:
            self._connected.set()

    def connect(self):
        with self._lock:
            if not self._started:
                self.client.connect(self.host,self.port,60)
                self.client.loop_start()
                self._started = True
        if not self._connected.wait(5):
            raise ConnectionError('MQTT publisher is not connected')

    def send(self,message,topic=ALARM_TOPIC,ready_only=False):
        if ready_only:
            if not self._connected.is_set():
                raise ConnectionError('MQTT status publisher is offline')
        else:
            self.connect()
        result = self.client.publish(topic,message,qos=0)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError('MQTT publish failed: '+str(result.rc))

    def close(self):
        with self._lock:
            if self._started:
                self.client.disconnect()
                self.client.loop_stop()
                self._started = False
                self._connected.clear()

_publisher = Publisher()
connect = _publisher.connect
send = _publisher.send

def send2(message):
    _publisher.send(message,'/VIDEO/videoAlarmTopic/post')

def send_status(message):
    # Task cleanup must not wait for a broken network connection. Controllers
    # can query/retry through their existing lease heartbeat after reconnect.
    _publisher.send(message,STATUS_TOPIC,ready_only=True)

def close():
    _publisher.close()
