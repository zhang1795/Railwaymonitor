"""Opt-in broker ACL and certificate checks using only isolated test settings."""
import json
import os
import ssl
import socket
import threading
from unittest.mock import patch
import paho.mqtt.client as mqtt


def client(username=None,password=None,trust=True,client_id=''):
    value=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=client_id)
    if username:value.username_pw_set(username,password)
    value.tls_set(ca_certs=os.getenv('MQTT_CA_FILE') if trust else None)
    return value


def rejected_login(username=None,password=None):
    c=client(username,password);done=threading.Event();result=[]
    c.on_connect=lambda a,b,d,reason,p:(result.append(reason==0),done.set())
    try:
        c.connect('localhost',18884,10);c.loop_start()
        assert done.wait(5) and result==[False], 'unauthorized login accepted'
    finally:c.disconnect();c.loop_stop()


def denied_publish(topic,backend=False):
    prefix='MQTT_BACKEND_' if backend else 'MQTT_'
    c=client(os.environ[prefix+'USERNAME'],os.environ[prefix+'PASSWORD'])
    connected=threading.Event();disconnected=threading.Event()
    c.on_connect=lambda a,b,d,reason,p:connected.set() if reason==0 else None
    c.on_disconnect=lambda *args:disconnected.set()
    try:
        c.connect('localhost',18884,10);c.loop_start();assert connected.wait(5)
        c.publish(topic,'{}',qos=1)
        assert disconnected.wait(5), 'forbidden publication was not denied'
    finally:c.disconnect();c.loop_stop()


def denied_subscription(topic):
    c=client(os.environ['MQTT_USERNAME'],os.environ['MQTT_PASSWORD'])
    connected=threading.Event();denied=threading.Event();grants=[]
    c.on_connect=lambda a,b,d,reason,p:connected.set() if reason==0 else None
    c.on_disconnect=lambda *args:denied.set() if connected.is_set() else None
    def subscribed(a,b,mid,codes,properties):
        grants.extend(not code.is_failure for code in codes);denied.set()
    c.on_subscribe=subscribed
    try:
        c.connect('localhost',18884,10);c.loop_start();assert connected.wait(5)
        c.subscribe(topic,qos=1)
        assert denied.wait(5) and not any(grants),'forbidden subscription granted'
    finally:c.disconnect();c.loop_stop()


def client_id_cannot_evict_backend():
    backend=client(os.environ['MQTT_BACKEND_USERNAME'],os.environ['MQTT_BACKEND_PASSWORD'])
    worker=client(os.environ['MQTT_USERNAME'],os.environ['MQTT_PASSWORD'],client_id='railway-backend')
    a=threading.Event();b=threading.Event();lost=threading.Event()
    backend.on_connect=lambda c,u,f,reason,p:a.set() if reason==0 else None
    backend.on_disconnect=lambda *args:lost.set()
    worker.on_connect=lambda c,u,f,reason,p:b.set() if reason==0 else None
    try:
        backend.connect('localhost',18884,10);backend.loop_start();assert a.wait(5)
        worker.connect('localhost',18884,10);worker.loop_start();assert b.wait(5)
        assert not lost.wait(.5) and backend.is_connected(),'worker impersonated backend client ID'
    finally:
        worker.disconnect();worker.loop_stop();backend.disconnect();backend.loop_stop()


def wrong_hostname_is_rejected():
    c=client();lookup=socket.getaddrinfo
    def local(host,*args,**kwargs):return lookup('127.0.0.1' if host=='p0-wrong-host.invalid' else host,*args,**kwargs)
    try:
        # Only DNS is redirected; this remains a real Paho TLS handshake and
        # must validate the original hostname against the trusted certificate.
        with patch('socket.getaddrinfo',side_effect=local):
            try:c.connect('p0-wrong-host.invalid',18884,10)
            except ssl.SSLCertVerificationError:pass
            else:raise AssertionError('trusted certificate with wrong hostname accepted')
    finally:c.disconnect()


if __name__=='__main__':
    rejected_login();rejected_login('detector-1','invalid-password')
    for topic in ('railway/v3/detector-1/ack','railway/v3/detector-1/control','railway/v3/other/events'):
        denied_publish(topic)
    denied_publish('railway/v3/detector-1/events',backend=True)
    denied_subscription('railway/v3/other/ack')
    denied_subscription('railway/v3/#')
    client_id_cannot_evict_backend()
    wrong_hostname_is_rejected()
    c=client(trust=False)
    try:
        try:c.connect('localhost',18884,10)
        except ssl.SSLCertVerificationError:pass
        else:raise AssertionError('untrusted TLS certificate accepted')
    finally:c.disconnect()
    print(json.dumps({'anonymousDenied':True,'badPasswordDenied':True,'forgedAckDenied':True,
                      'forgedControlDenied':True,'crossWorkerPublishDenied':True,'untrustedCertificateDenied':True,
                      'backendWorkerPublishDenied':True,'crossWorkerSubscribeDenied':True,'wildcardSubscribeDenied':True,
                      'clientIdImpersonationDenied':True,'trustedCaWrongHostnameDenied':True},indent=2))
