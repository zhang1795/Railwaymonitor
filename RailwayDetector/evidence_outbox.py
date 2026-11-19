"""Independent, bounded JPEG spool. Media failures never retract track events."""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import ssl
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import cv2

log=logging.getLogger(__name__)

class EvidenceOutbox:
    def __init__(self,path,worker,url,key,ca=None,max_rows=500,max_bytes=64*1024*1024,opener=None):
        parsed=urlsplit(url)
        if (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1'))) or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('HTTPS or loopback evidence endpoint required')
        if len(key)<32 or not re.fullmatch('[A-Za-z0-9_-]{1,64}',worker):raise ValueError('valid evidence identity required')
        if max_rows<1 or max_bytes<1:raise ValueError('positive evidence budget required')
        self.worker,self.url,self.key=worker,url.rstrip('/'),key
        self.max_rows,self.max_bytes=max_rows,max_bytes
        self.context=ssl.create_default_context(cafile=ca or None)
        self.opener=opener or urlopen
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),check_same_thread=False,timeout=5)
        os.chmod(path,0o600)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS owner(worker TEXT PRIMARY KEY); CREATE TABLE IF NOT EXISTS images(event TEXT PRIMARY KEY,body BLOB NOT NULL,sha TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,due REAL NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS failures(event TEXT PRIMARY KEY,reason TEXT NOT NULL);')
        owner=self.db.execute('SELECT worker FROM owner').fetchone()
        if owner and owner[0]!=worker:self.db.close();raise ValueError('evidence spool belongs to another worker')
        self.db.execute('INSERT OR IGNORE INTO owner VALUES(?)',(worker,));self.db.commit()
        for suffix in ('-wal','-shm'):
            if os.path.exists(str(path)+suffix):os.chmod(str(path)+suffix,0o600)
        self.lock=threading.RLock();self.closed=threading.Event();self.thread=None
        self.last={};self.skipped=0;self.error=''
    def enqueue(self,event,body):
        if not re.fullmatch('[a-f0-9]{32}',event) or len(body)>2*1024*1024:raise ValueError('invalid evidence')
        digest=hashlib.sha256(body).hexdigest()
        with self.lock,self.db:
            old=self.db.execute('SELECT sha FROM images WHERE event=?',(event,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('evidence identity reused')
                return True
            count,total=self.db.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(body)),0) FROM images').fetchone()
            if count>=self.max_rows or total+len(body)>self.max_bytes:
                self.skipped+=1;self.error='evidence_spool_full';return False
            self.db.execute('INSERT INTO images(event,body,sha) VALUES(?,?,?)',(event,body,digest));return True
    def capture(self,event,frame):
        if frame is None or event.get('state')!='ACTIVE':return
        source=(event['sessionId'],event['trackId']);tick=time.monotonic()
        if tick-self.last.get(source,float('-inf'))<2:return
        if len(self.last)>=600:self.last.pop(next(iter(self.last)))
        self.last[source]=tick
        h,w=frame.shape[:2];scale=min(1.,640/w,480/h)
        image=cv2.resize(frame,(max(1,round(w*scale)),max(1,round(h*scale)))) if scale<1 else frame.copy()
        x1,y1,x2,y2=[round(v*scale) for v in event['bbox']]
        cv2.rectangle(image,(x1,y1),(x2,y2),(0,0,255),2)
        cv2.putText(image,event['className']+' '+format(event['confidence'],'.2f'),(x1,max(15,y1-5)),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,255),1)
        ok,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,75])
        if ok:self.enqueue(event['eventId'],encoded.tobytes())
    def upload_once(self):
        with self.lock:
            row=self.db.execute('SELECT event,body,attempts FROM images WHERE due<=? ORDER BY rowid LIMIT 1',(time.time(),)).fetchone()
        if not row:return False
        event,body,attempts=row
        try:
            request=Request(self.url+'/_evidence/'+event,body,headers={'Content-Type':'image/jpeg','Authorization':'Bearer '+self.key,'X-Worker-Id':self.worker},method='POST')
            with self.opener(request,timeout=3,context=self.context) as response:
                if response.status!=200:raise RuntimeError('unexpected evidence response')
                result=json.loads(response.read(8192))
                if result.get('code')!=200:raise RuntimeError('evidence rejected')
            with self.lock,self.db:self.db.execute('DELETE FROM images WHERE event=?',(event,))
            self.error=''
        except HTTPError as error:
            self.error='evidence_http_'+str(error.code)
            if error.code in (400,409,413,415):
                with self.lock,self.db:
                    self.db.execute('INSERT OR IGNORE INTO failures VALUES(?,?)',(event,self.error))
                    self.db.execute('DELETE FROM failures WHERE rowid NOT IN (SELECT rowid FROM failures ORDER BY rowid DESC LIMIT 500)')
                    self.db.execute('DELETE FROM images WHERE event=?',(event,))
            else:self._retry(event,attempts)
        except Exception as error:
            self.error=type(error).__name__;self._retry(event,attempts)
        return True
    def _retry(self,event,attempts):
        with self.lock,self.db:self.db.execute('UPDATE images SET attempts=attempts+1,due=? WHERE event=?',(time.time()+min(30,2**min(attempts,5)),event))
    def metrics(self):
        with self.lock:return {'evidencePending':self.db.execute('SELECT COUNT(*) FROM images').fetchone()[0],'evidenceSkipped':self.skipped,'evidenceError':self.error}
    def start(self):
        def run():
            while not self.closed.wait(.25):
                try:self.upload_once()
                except Exception:log.exception('Evidence spool unavailable; metadata transport independent')
        self.thread=threading.Thread(target=run,name='evidence-upload',daemon=True);self.thread.start()
    def close(self):
        self.closed.set()
        if self.thread:self.thread.join(5)
        if self.thread and self.thread.is_alive():raise RuntimeError('Evidence shutdown incomplete; retain spool for recovery')
        with self.lock:self.db.close()
