"""Guarded local MediaMTX queue update and adoption of local sample publishers."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from stop_managed import process,expected,stop

ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/'workspace/runtime'

def apply(user_pid):
    os.umask(0o077);folder=RUNTIME/'p1-rollout'/time.strftime('%Y%m%d-%H%M%S-media-queue');folder.mkdir(parents=True,mode=0o700)
    container=json.loads(subprocess.check_output(['docker','inspect','railway-mediamtx']))[0]
    labels=container['Config']['Labels'];assert labels['com.docker.compose.service']=='mediamtx'
    assert Path(labels['com.docker.compose.project.working_dir']).resolve() in (ROOT,ROOT/'deploy')
    before=json.loads((RUNTIME/'managed-services.json').read_text());specs=json.loads(json.dumps(before));sources={}
    for name,pid in [('demo_stream',int((RUNTIME/'pids/demo_stream.pid').read_text())),('user_stream',user_pid)]:
        current=process(pid);assert current and expected(name,ROOT,current[1],current[2]),'publisher identity mismatch'
        sources[name]={'pid':pid,'args':current[1],'cwd':str(current[2]),'birth':current[0]}
    client=['/data/anaconda3/bin/mysql','--no-defaults','--protocol=socket','--socket='+str(RUNTIME/'mysql/run/mysql.sock'),'-uroot','--batch','--skip-column-names','railway_monitoring']
    def query(sql):return subprocess.check_output(client+['-e',sql],text=True).strip()
    assert query('SELECT @@port')=='3307'
    assert sources['user_stream']['args'][-1]==query('SELECT rtsp_url FROM camera WHERE id=22')
    intention=query('SELECT camera_id,enabled FROM monitoring_task ORDER BY camera_id')
    (folder/'container-before.json').write_text(json.dumps(container));(folder/'publishers-before.json').write_text(json.dumps(sources))
    envfile=ROOT/'deploy/.env.p0';(folder/'.env.p0.before').write_bytes(envfile.read_bytes());(folder/'managed-services.before.json').write_text(json.dumps(before))
    lines=[line for line in envfile.read_text().splitlines() if line.partition('=')[0]!='MEDIA_WRITE_QUEUE_SIZE'];tmp=envfile.with_suffix('.queue-tmp');tmp.write_text('\n'.join(lines+['MEDIA_WRITE_QUEUE_SIZE=8192'])+'\n');tmp.chmod(0o600);tmp.replace(envfile)
    # The existing user-upload source was previously an unmanaged fixture.
    alias=RUNTIME/'pids/user_stream.pid'
    if alias.exists():assert int(alias.read_text())==user_pid
    else:alias.write_text(str(user_pid)+'\n')
    command=['docker','compose','--project-name',labels['com.docker.compose.project'],'--env-file',str(ROOT/'deploy/.env'),'--env-file',str(envfile),'-f',str(ROOT/'deploy/compose.yaml'),'up','-d','--no-deps','mediamtx']
    def restart_guardian():
        with (RUNTIME/'logs/guardian.log').open('ab',buffering=0) as log:child=subprocess.Popen([sys.executable,str(ROOT/'deploy/guardian.py'),'--root',str(ROOT)],cwd=ROOT,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (RUNTIME/'pids/guardian.pid').write_text(str(child.pid)+'\n')
    started=time.monotonic();stop('guardian',ROOT)
    for name in sources:stop(name,ROOT)
    success=False
    try:
        with (folder/'compose.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
        after=json.loads(subprocess.check_output(['docker','inspect','railway-mediamtx']))[0]
        assert after['State']['Running'] and 'MTX_WRITEQUEUESIZE=8192' in after['Config']['Env']
        assert after['Image']==container['Image'],'image changed unexpectedly'
        success=True
    finally:
        if not success:
            envfile.write_bytes((folder/'.env.p0.before').read_bytes());envfile.chmod(0o600)
            with (folder/'rollback.log').open('w') as log:subprocess.run(command,env=dict(os.environ,MEDIA_WRITE_QUEUE_SIZE='512'),stdout=log,stderr=subprocess.STDOUT,check=True)
        for name,spec in sources.items():
            args=spec['args'].copy()
            if '-nostats' not in args:args[1:1]=['-nostats','-loglevel','warning']
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
            with (RUNTIME/'logs'/(name+'.log')).open('ab',buffering=0) as log:child=subprocess.Popen(args,cwd=spec['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            (RUNTIME/'pids'/(name+'.pid')).write_text(str(child.pid)+'\n')
            if success:specs[name]={'args':args,'cwd':spec['cwd'],'env':env,'startupGrace':30}
        manifest=RUNTIME/'managed-services.json';tmp=manifest.with_suffix('.tmp');tmp.write_text(json.dumps(specs if success else before));tmp.chmod(0o600);tmp.replace(manifest);restart_guardian()
    assert success and intention==query('SELECT camera_id,enabled FROM monitoring_task ORDER BY camera_id')
    result={'configuredQueue':8192,'imageUnchanged':True,'intentPreserved':True,'localPublishersSupervised':list(sources),'relayAndPublishersRestartSeconds':round(time.monotonic()-started,3)}
    (folder/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--user-publisher-pid',type=int,required=True);args=parser.parse_args();apply(args.user_publisher_pid)
