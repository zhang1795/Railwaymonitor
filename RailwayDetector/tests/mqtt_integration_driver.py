"""Opt-in integration worker: real outbox/TLS/MQTT/control, synthetic tracks.

No YOLO model or real camera; started by P0MqttIntegrationTest only.
"""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from detections import TrackResult
from event_outbox import EventOutbox
from mqtt_service import DetectorService
from task_manager import TaskManager
from track_events import TrackEvents


def main(folder):
    folder=Path(folder);folder.mkdir(exist_ok=True)
    box=EventOutbox(str(folder/'events.db'),'detector-1')
    acknowledge=box.acknowledge
    def fault_injected_ack(value):
        # Simulate a lost business ACK after the real backend has committed.
        return False if (folder/'drop-acks').exists() else acknowledge(value)
    box.acknowledge=fault_injected_ack
    def worker(task):
        events=TrackEvents(task.message,task.session_id,box.enqueue)
        task.mark_running();started=time.monotonic()
        try:
            while not task.stop.is_set():
                now=datetime.now(timezone.utc)
                changed=time.monotonic()-started>=1
                result=TrackResult((10.,20.,100.,120.),1,2 if changed else 12,'cow' if changed else 'worker',.95 if changed else .3,0)
                events.update([result],[1],now,'received_at',now,(480,640,3))
                task.stop.wait(.1)
        finally:
            events.finish(datetime.now(timezone.utc),bool(task.stop_reason))
    manager=TaskManager(worker,max_tasks=1,lease_seconds=30)
    service=DetectorService('detector-1',box,manager);manager.status_sink=service.status
    control_seen={'at':0.}
    control=service.control
    def observe_control(value):
        control(value);control_seen['at']=time.time()
    service.control=observe_control
    closed=threading.Event()
    signal.signal(signal.SIGTERM,lambda *args:closed.set())
    try:
        manager.start_reaper();service.start()
        while not closed.wait(.2):
            temp=folder/'metrics.tmp'
            with box.lock:
                attempts=box.db.execute('SELECT COALESCE(MAX(attempts),0) FROM pending').fetchone()[0]
            temp.write_text(json.dumps({'pending':box.count(),'maxAttempts':attempts,'lastControlAt':control_seen['at'],'at':time.time()}));temp.replace(folder/'metrics.json')
    finally:
        manager.close();service.close();box.close()


if __name__=='__main__':main(sys.argv[1])
