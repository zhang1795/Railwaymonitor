import paho.mqtt.client as mqtt
import time
import datetime
import json
import os
import threading
from json import dumps
from queue import Queue


HOST = os.getenv("MQTT_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT", "1883"))


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
_client_lock = threading.Lock()
_connection_started = False


def connect():
    global _connection_started
    with _client_lock:
        if not _connection_started:
            client.connect(HOST, PORT, 60)
            client.loop_start()
            _connection_started = True
            print("告警 MQTT 客户端连接已启动")


def send(msg):
    connect()
    client.publish('/UAV/videoAlarmTopic/post', msg, qos=0)
    #client.publish('videoData', msg, qos=0)

def send2(msg):
    connect()
    client.publish('/VIDEO/videoAlarmTopic/post', msg, qos=0)


# client = mqtt.Client()
# client.on_connect = on_connect
# client.connect(HOST, PORT)
# client.on_connect = on_connect# 60为keepalive的时间间隔
