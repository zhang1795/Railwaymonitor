"""Single-host service recovery. Private manifest, PID identity and one owner lock.

No application commands/secrets are written to public diagnostics. Dependencies
are not restarted for a database/Broker outage. An OS service should supervise
this guardian itself; see systemd/railway-guardian.service.example.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from urllib.request import urlopen
from stop_managed import process,expected

class Guardian:
    def __init__(self,root):
        self.root=Path(root).resolve();self.runtime=self.root/'workspace/runtime'
        self.folder=self.runtime/'pids';self.folder.mkdir(parents=True,exist_ok=True)
        self.lock=(self.folder/'guardian.lock').open('a')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:self.lock.close();raise
        manifest=self.runtime/'managed-services.json'
        if manifest.stat().st_mode & 0o077:raise RuntimeError('manifest must be private')
        self.specs=json.loads(manifest.read_text());self.states={};self.stop=threading.Event();self.children={}
    def health(self,name,pid,age,spec):
        if age<spec.get('startupGrace',180):return True
        try:
            if name=='detector':
                value=json.loads((self.runtime/'detector-output/heartbeat.json').read_text())
                return value['pid']==pid and time.time()-value['at']<30 and not value['stalledCameras']
            if name in ('backend','flask'):
                with urlopen(spec['health'],timeout=2) as response:return response.status==200
            return True
        except Exception:return False
    def tick(self,now=None):
        for pid,child in tuple(self.children.items()):
            if child.poll() is not None:del self.children[pid]
        now=time.monotonic() if now is None else now
        for name,spec in self.specs.items():
            if name not in ('backend','flask','detector','demo_stream','user_stream'):continue
            state=self.states.setdefault(name,{'failures':0,'due':0,'since':now,'unhealthy':0})
            path=self.folder/(name+'.pid');pid=int(path.read_text()) if path.exists() else 0
            current=process(pid) if pid>1 else None
            if current:
                birth,args,cwd=current
                matches=expected(name,self.root,args,cwd) and cwd==Path(spec['cwd']).resolve()
                if matches and name=='backend':matches=args[args.index('-jar')+1]==spec['args'][spec['args'].index('-jar')+1]
                if not matches:state['error']='pid_identity_mismatch';continue
                if state.get('birth')!=birth:state.update(birth=birth,since=now,unhealthy=0)
                if now-state['since']>300:state['failures']=0
                if self.health(name,pid,now-state['since'],spec):state['unhealthy']=0;state['error']='';continue
                state['unhealthy']+=1
                if state['unhealthy']<3:continue
                # Remember the birth identity. A replaced PID must never be killed.
                if state.get('terminating')!=birth:
                    os.kill(pid,signal.SIGTERM);state['terminating']=birth;state['terminateAt']=now;state['error']='health_stalled';continue
                if now-state['terminateAt']>30 and process(pid) and process(pid)[0]==birth:os.kill(pid,signal.SIGKILL)
                continue
            if now<state['due']:continue
            output=self.runtime/'logs'/(name+'.log');output.parent.mkdir(exist_ok=True)
            with output.open('ab',buffering=0) as log:
                child=subprocess.Popen(spec['args'],cwd=spec['cwd'],env=spec['env'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.children[child.pid]=child
            path.write_text(str(child.pid)+'\n')
            state.update(since=now,unhealthy=0,failures=state['failures']+1,error='restarted')
            state['due']=now+min(60,5*2**min(state['failures']-1,4))
        public={name:{key:value for key,value in state.items() if key in ('failures','error','unhealthy')} for name,state in self.states.items()}
        file=self.runtime/'guardian-status.json';temp=file.with_suffix('.tmp');temp.write_text(json.dumps({'pid':os.getpid(),'at':time.time(),'services':public}));temp.replace(file)
    def run(self):
        signal.signal(signal.SIGTERM,lambda *args:self.stop.set());signal.signal(signal.SIGINT,lambda *args:self.stop.set())
        while not self.stop.is_set():
            try:self.tick()
            except Exception as error:print('guardian check failed: '+type(error).__name__,flush=True)
            self.stop.wait(2)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    Guardian(args.root).run()
