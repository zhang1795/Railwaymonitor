"""Independent source-stream segments and durable shared-storage registration."""
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urlsplit
import ssl
from media_budget import recording_budget

def iso(stamp):return datetime.fromtimestamp(stamp,timezone.utc).isoformat(timespec='milliseconds')

class VideoManifestOutbox:
    def __init__(self,root,worker,url,key,ca=None,opener=urlopen,max_rows=100000):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True);self.root.chmod(0o700)
        self.budget=recording_budget(self.root)
        parsed=urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','localhost','::1')):raise ValueError('secure recording endpoint required')
        if len(key)<32:raise ValueError('recording service identity required')
        self.worker,self.url,self.key,self.opener,self.max_rows=worker,url.rstrip('/'),key,opener,max_rows
        self.context=ssl.create_default_context(cafile=ca or None)
        path=self.root/'manifests.sqlite3';self.db=sqlite3.connect(str(path),check_same_thread=False);path.chmod(0o600)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('CREATE TABLE IF NOT EXISTS owner(worker TEXT PRIMARY KEY); CREATE TABLE IF NOT EXISTS pending(id TEXT PRIMARY KEY,body TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,due REAL NOT NULL DEFAULT 0); CREATE TABLE IF NOT EXISTS failed(id TEXT PRIMARY KEY,error TEXT NOT NULL);')
        self.db.execute('CREATE TABLE IF NOT EXISTS cursor(name TEXT PRIMARY KEY,offset INTEGER NOT NULL)')
        owner=self.db.execute('SELECT worker FROM owner').fetchone()
        if owner and owner[0]!=worker:self.db.close();raise ValueError('recording spool belongs to another worker')
        self.db.execute('INSERT OR IGNORE INTO owner VALUES(?)',(worker,));self.db.commit()
        self.lock=threading.RLock();self.closed=threading.Event();self.thread=None;self.error=''
    def enqueue(self,value):
        body=json.dumps(value,sort_keys=True,separators=(',',':'))
        with self.lock,self.db:
            old=self.db.execute('SELECT body FROM pending WHERE id=?',(value['id'],)).fetchone()
            if old and old[0]!=body:raise ValueError('recording identity conflict')
            if not old and self.db.execute('SELECT COUNT(*) FROM pending').fetchone()[0]>=self.max_rows:raise OSError('recording manifest spool full')
            self.db.execute('INSERT OR IGNORE INTO pending(id,body) VALUES(?,?)',(value['id'],body))
    def upload_once(self):
        with self.lock:row=self.db.execute('SELECT id,body,attempts FROM pending WHERE due<=? ORDER BY rowid LIMIT 1',(time.time(),)).fetchone()
        if not row:return False
        try:
            if time.time()-self.budget.last_prune>=60:
                self.budget.prune();self.budget.last_prune=time.time()
            request=Request(self.url+'/_evidence/recordings',row[1].encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.key,'X-Worker-Id':self.worker},method='POST')
            with self.opener(request,timeout=5,context=self.context) as response:
                result=json.loads(response.read(8192));assert response.status==200 and result.get('code')==200 and result.get('data',{}).get('registered') is True
            with self.lock,self.db:self.db.execute('DELETE FROM pending WHERE id=?',(row[0],))
            self.error=''
        except Exception as error:
            code=getattr(error,'code',None);self.error='recording_http_'+str(code) if code else type(error).__name__
            with self.lock,self.db:
                if code in (400,403,409,410):
                    self.db.execute('INSERT OR REPLACE INTO failed VALUES(?,?)',(row[0],self.error));self.db.execute('DELETE FROM pending WHERE id=?',(row[0],))
                    self.db.execute('DELETE FROM failed WHERE rowid NOT IN (SELECT rowid FROM failed ORDER BY rowid DESC LIMIT 1000)')
                else:self.db.execute('UPDATE pending SET attempts=attempts+1,due=? WHERE id=?',(time.time()+min(60,2**min(row[2],6)),row[0]))
        return True
    def metrics(self):
        with self.lock:return {'recordingPending':self.db.execute('SELECT COUNT(*) FROM pending').fetchone()[0],'recordingFailed':self.db.execute('SELECT COUNT(*) FROM failed').fetchone()[0],'recordingRegistrationError':self.error}
    def position(self,name):
        with self.lock:
            row=self.db.execute('SELECT offset FROM cursor WHERE name=?',(name,)).fetchone();return row[0] if row else 0
    def advance(self,name,offset):
        with self.lock,self.db:self.db.execute('INSERT OR REPLACE INTO cursor VALUES(?,?)',(name,offset))
    def recover_once(self):
        with self.lock:registered={row[0] for row in self.db.execute("SELECT name FROM cursor WHERE name LIKE 'analysis:%'")}
        for path in self.root.glob('*.analysis.json'):
            if self.closed.is_set():break
            try:
                if 'analysis:'+path.name.replace('.analysis.json','.mp4') in registered:continue
                if path.is_symlink() or path.stat().st_size>3*1024*1024:continue
                envelope=json.loads(path.read_text());value=envelope['registration'];name=value['file']
                if value['workerId']!=self.worker or value['kind']!='DETECTION_SAMPLES' or not re.fullmatch(r'[A-Za-z0-9_-]+\.mp4',name) or path.name!=Path(name).with_suffix('.analysis.json').name:continue
                with self.lock:
                    if self.position('analysis:'+name):continue
                    self.enqueue(value);self.advance('analysis:'+name,1)
            except Exception:self.error='analysis_recovery_incomplete'
        for path in self.root.glob('*.session.json'):
            if self.closed.is_set():break
            try:
                session=json.loads(path.read_text())
                if session['workerId']!=self.worker:continue
                recorder=SourceRecorder({'videoId':session['cameraId']},session['sessionId'],self)
                recorder.prefix=session['prefix'];recorder.list=self.root/(recorder.prefix+'.csv');recorder.started=session['started']
                recorder.seconds=session.get('segmentSeconds',30)
                # Registration and cursor advancement share one local lock
                # with live writers, including recovery after spool-full.
                with self.lock:recorder._register_closed()
            except Exception:self.error='recording_recovery_incomplete'
    def start(self):
        def run():
            recovered=0.
            while not self.closed.wait(.25):
                try:
                    if time.monotonic()-recovered>=30:self.recover_once();recovered=time.monotonic()
                    self.upload_once()
                except Exception:self.error='recording_spool_error'
        self.thread=threading.Thread(target=run,name='recording-manifests',daemon=True);self.thread.start()
    def close(self):
        self.closed.set()
        if self.thread:self.thread.join(6)
        if self.thread and self.thread.is_alive():raise RuntimeError('recording registration shutdown incomplete')
        self.db.close()

class SourceRecorder:
    def __init__(self,message,session,outbox,ffmpeg=None,segment_seconds=30):
        self.message,self.session,self.outbox=message,session,outbox
        if not 5<=segment_seconds<=300:raise ValueError('invalid recording segment duration')
        self.seconds=segment_seconds;self.ffmpeg=ffmpeg;self.stop=threading.Event();self.thread=None;self.process=None
        self.state='STARTING';self.completed=set();self.error='';self.prefix=str(message['videoId'])+'_'+session
        if not re.fullmatch(r'[A-Za-z0-9_-]+',self.prefix):raise ValueError('invalid recording identity')
        self.root=outbox.root;self.budget=recording_budget(self.root)
        self.prefix+='_'+os.urandom(6).hex()
        self.list=self.root/(self.prefix+'.csv');self.started=time.time()
    def _register_closed(self):
        if not self.list.exists():return
        with self.list.open(newline='') as source:
            source.seek(self.outbox.position(self.prefix))
            rows=[]
            while True:
                line=source.readline()
                if not line or not line.endswith('\n'):break
                rows.append((next(csv.reader([line])),source.tell()))
        for row,offset in rows:
            if len(row)!=3:continue
            name=Path(row[0]).name
            if not re.fullmatch(re.escape(self.prefix)+r'_\d{6,12}\.mp4',name) or name in self.completed:continue
            path=self.root/name
            if path.is_symlink() or not path.is_file():continue
            size=path.stat().st_size
            if not 0<size<=64*1024**2:raise OSError('recording segment too large')
            begin,end=float(row[1]),float(row[2])
            if not 0<=begin<=end or end-begin>self.seconds+300:raise ValueError('invalid recording clock')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            clip=hashlib.sha256((self.outbox.worker+'\n'+self.session+'\n'+name+'\n'+digest).encode()).hexdigest()
            value={'id':clip,'workerId':self.outbox.worker,'cameraId':str(self.message['videoId']),'sessionId':self.session,'file':name,'sha256':digest,'bytes':size,'startedAt':iso(self.started+begin),'endedAt':iso(self.started+end),'clockSource':'RECORDER_WALL_CLOCK_ESTIMATE','kind':'FULL_SOURCE'}
            self.outbox.enqueue(value);self.completed.add(name);path.chmod(0o600)
            with self.budget.lock:
                self.budget.observe(name);self.budget.active.discard(name)
                if self.process is not None and self.process.poll() is None:self.budget.active.add(self.prefix+'_%06d.mp4'%(int(name.rsplit('_',1)[1][:-4])+1))
            # Sidecar records only app-owned closed segments, no source URL.
            manifest=path.with_suffix('.full-source.json');manifest.write_text(json.dumps(value));manifest.chmod(0o600)
            self.outbox.advance(self.prefix,offset)
    def _run(self):
        try:
            if time.time()-self.budget.last_prune>=60:
                self.budget.prune();self.budget.last_prune=time.time()
            if self.ffmpeg is None:
                import imageio_ffmpeg
                self.ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            if not self.budget.allow(64*1024**2):self.state='BUDGET_EXHAUSTED';return
            metadata=self.root/(self.prefix+'.session.json')
            metadata.write_text(json.dumps({'workerId':self.outbox.worker,'cameraId':str(self.message['videoId']),'sessionId':self.session,'prefix':self.prefix,'started':self.started,'segmentSeconds':self.seconds}));metadata.chmod(0o600)
            # Linux parent-death signal prevents orphan recorders after a hard kill.
            bootstrap="import ctypes,os,signal,sys; ctypes.CDLL(None).prctl(1,signal.SIGTERM); os.getppid()==int(sys.argv[1]) or sys.exit(1); os.execv(sys.argv[2],sys.argv[2:])"
            args=[sys.executable,'-c',bootstrap,str(os.getpid()),str(self.ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-rtsp_transport','tcp','-stimeout','5000000','-i',self.message['videoUrl'],'-map','0:v:0','-an','-c','copy','-f','segment','-segment_time',str(self.seconds),'-segment_list_type','csv','-segment_list',str(self.list),'-segment_list_size','0','-reset_timestamps','1','-segment_format_options','movflags=+frag_keyframe+empty_moov+default_base_moof',str(self.root/(self.prefix+'_%06d.mp4'))]
            self.budget.active.add(self.prefix+'_000000.mp4')
            self.process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.state='RECORDING'
            while not self.stop.wait(.5) and self.process.poll() is None:
                if not self.budget.allow(64*1024**2):self.state='BUDGET_EXHAUSTED';break
                with self.outbox.lock:self._register_closed()
            if not self.stop.is_set() and self.state=='RECORDING':self.state='ERROR';self.error='source_recording_interrupted'
        except Exception as error:self.state='ERROR';self.error=type(error).__name__
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            try:
                with self.outbox.lock:self._register_closed()
            except Exception as error:self.error=type(error).__name__;self.state='ERROR'
            with self.budget.lock:
                for name in tuple(self.budget.active):
                    if name.startswith(self.prefix+'_'):self.budget.observe(name);self.budget.active.discard(name)
            if self.state=='RECORDING':self.state='STOPPED'
    def start(self):
        def run():
            attempt=0
            while not self.stop.is_set():
                self._run()
                if self.stop.is_set():break
                attempt+=1
                if self.stop.wait(min(60,2**min(attempt,6))):break
                self.prefix=str(self.message['videoId'])+'_'+self.session+'_'+os.urandom(6).hex()
                self.list=self.root/(self.prefix+'.csv');self.started=time.time();self.completed.clear()
        self.thread=threading.Thread(target=run,name='source-recorder',daemon=True);self.thread.start()
    def metrics(self):return dict(self.outbox.metrics(),sourceRecordingState=self.state,sourceRecordingError=self.error)
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(7)
        if self.thread and self.thread.is_alive():raise RuntimeError('source recorder shutdown incomplete')
