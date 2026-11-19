"""Prepare/clean disposable P0 services; never use the business database.

Requires Docker, OpenSSL and the repository's local MySQL runtime. All state and
secrets stay under workspace/runtime/p0-reaudit (ignored by Git).
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
MYSQL=Path('/data/anaconda3')
LABEL='railway.p0.test.directory'


def wait_for(predicate,seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            if predicate():return
        except Exception:pass
        time.sleep(.25)
    raise RuntimeError('isolated service readiness timed out')


def prepare(folder):
    if len(os.fsencode(str(folder/'mysql.sock')))>107:
        raise RuntimeError('Test directory is too long for a MySQL Unix socket; use a shorter directory name')
    state_file=folder/'test-services.json'
    if state_file.exists():raise RuntimeError('test resources already recorded; cleanup first')
    for name in ('railway-p0-test','railway-p0-preview'):
        if subprocess.run(['docker','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
            raise RuntimeError('refusing to replace existing container '+name)
    state={'directory':str(folder),'containers':{},'network':None,'mysqlPid':None}
    def save():state_file.write_text(json.dumps(state,indent=2))
    save()
    with (folder/'environment-setup.log').open('a') as log:
        def run(args,env=None):
            return subprocess.run(args,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=P0-Reaudit-CA',
             '-keyout',str(folder/'ca.key'),'-out',str(folder/'ca.crt')])
        run(['openssl','req','-newkey','rsa:2048','-nodes','-subj','/CN=localhost',
             '-keyout',str(folder/'server.key'),'-out',str(folder/'server.csr')])
        (folder/'server.ext').write_text('subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth\n')
        run(['openssl','x509','-req','-days','1','-in',str(folder/'server.csr'),'-CA',str(folder/'ca.crt'),
             '-CAkey',str(folder/'ca.key'),'-CAcreateserial','-out',str(folder/'server.crt'),'-extfile',str(folder/'server.ext')])
        values={
            'DETECTOR_WORKER_ID':'detector-1','MQTT_USERNAME':'detector-1','MQTT_PASSWORD':secrets.token_urlsafe(32),
            'MQTT_BACKEND_USERNAME':'railway-backend','MQTT_BACKEND_PASSWORD':secrets.token_urlsafe(32),
            'EMQX_DASHBOARD_PASSWORD':secrets.token_urlsafe(32),'RAILWAY_EMQX_COOKIE':secrets.token_urlsafe(32),
            'EVIDENCE_SERVICE_KEY':secrets.token_urlsafe(48),'PREVIEW_SERVICE_KEY':secrets.token_urlsafe(48),'MQTT_HOST':'localhost','MQTT_PORT':'18884',
            'P0_RTSP_USERNAME':'p0_camera','P0_RTSP_PASSWORD':secrets.token_urlsafe(24),
            'MQTT_CA_FILE':str(folder/'ca.crt'),'MQTT_BACKEND_URI':'ssl://localhost:18884',
            'EMQX_ADMIN_URL':'http://127.0.0.1:28083','P0_MQTT_URI':'ssl://localhost:18884',
            'P0_MQTT_PERSISTENCE':str(folder/'backend-persistence'),'P0_MANAGE_TEST_BROKER':'true',
            'P0_TEST_DB_URL':'jdbc:mysql://127.0.0.1:13317/railway_p0_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC',
        }
        (folder/'services.env').write_text('\n'.join(k+'='+v for k,v in values.items())+'\n')
        env=os.environ.copy();env.update(values);env['EMQX_NODE__COOKIE']=values['RAILWAY_EMQX_COOKIE']
        env['EMQX_DASHBOARD__DEFAULT_PASSWORD']=values['EMQX_DASHBOARD_PASSWORD']
        run(['python3','deploy/prepare_p0_broker.py','--output',str(folder)],env)
        shutil.copyfile(ROOT/'deploy/emqx/emqx-tls.conf',folder/'emqx.conf')
        # These individual test-only bind mounts must be readable by container
        # uid 1000. Their containing host directory remains private (0700).
        for name in ('acl.conf','emqx.conf','server.key','server.crt'):(folder/name).chmod(0o644)
        network='railway-p0-acceptance-'+secrets.token_hex(4)
        run(['docker','network','create','--label',LABEL+'='+str(folder),network]);state['network']=network;save()
        configs=[('base.conf','railway-base.conf'),('emqx.conf','emqx.conf'),('acl.conf','railway-acl.conf'),
                 ('server.crt','railway-server.crt'),('server.key','railway-server.key')]
        command=['docker','run','-d','--name','railway-p0-test','--network',network,'--label',LABEL+'='+str(folder),
                 '-e','EMQX_NODE__COOKIE','-e','EMQX_DASHBOARD__DEFAULT_PASSWORD',
                 '-p','127.0.0.1:11883:1883','-p','127.0.0.1:18884:8883','-p','127.0.0.1:28083:18083']
        for source,target in configs:command+=['-v',str(folder/source)+':/opt/emqx/etc/'+target+':ro']
        run(command+['emqx/emqx:5.8.8'],env)
        state['containers']['railway-p0-test']=json.loads(subprocess.check_output(['docker','inspect','railway-p0-test']))[0]['Id'];save()
        (folder/'mediamtx.yml').write_text('authMethod: internal\nauthInternalUsers:\n- user: any\n  permissions:\n  - action: publish\n    path: p0_live_source\n- user: '+values['P0_RTSP_USERNAME']+'\n  pass: '+values['P0_RTSP_PASSWORD']+'\n  permissions:\n  - action: read\n    path: p0_live_source\npaths:\n  all_others:\n')
        (folder/'mediamtx.yml').chmod(0o644)
        run(['docker','run','-d','--name','railway-p0-preview','--network',network,'--label',LABEL+'='+str(folder),'-e','MTX_WRITEQUEUESIZE=8192',
             '-v',str(folder/'mediamtx.yml')+':/mediamtx.yml:ro','-p','127.0.0.1:18554:8554','bluenviron/mediamtx:1.18.2'])
        state['containers']['railway-p0-preview']=json.loads(subprocess.check_output(['docker','inspect','railway-p0-preview']))[0]['Id'];save()
        def dashboard():
            with urlopen(values['EMQX_ADMIN_URL']+'/status',timeout=1) as response:return response.status==200
        wait_for(dashboard)
        run(['python3','deploy/prepare_p0_broker.py','--output',str(folder),'--provision'],env)
        data=folder/'mysql';data.mkdir()
        run([str(MYSQL/'bin/mysqld'),'--no-defaults','--initialize-insecure','--basedir='+str(MYSQL),
             '--lc-messages-dir='+str(MYSQL/'share/mysql'),'--datadir='+str(data)])
        process=subprocess.Popen([str(MYSQL/'bin/mysqld'),'--no-defaults','--basedir='+str(MYSQL),
            '--lc-messages-dir='+str(MYSQL/'share/mysql'),'--datadir='+str(data),'--port=13317','--bind-address=127.0.0.1',
            '--socket='+str(folder/'mysql.sock'),'--pid-file='+str(folder/'mysql.pid'),'--log-error='+str(folder/'mysql.log'),
            '--skip-log-bin','--skip-name-resolve','--character-set-server=utf8mb4','--collation-server=utf8mb4_unicode_ci'],
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        state['mysqlPid']=process.pid;save()
        client=[str(MYSQL/'bin/mysqladmin'),'--no-defaults','--protocol=socket','--socket='+str(folder/'mysql.sock'),'-uroot']
        def mysql_ready():
            if process.poll() is not None:raise RuntimeError('isolated MySQL exited; inspect mysql.log')
            return subprocess.run(client+['--connect-timeout=1','ping'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3).returncode==0
        wait_for(mysql_ready)
        run([str(MYSQL/'bin/mysql'),'--no-defaults','--protocol=socket','--socket='+str(folder/'mysql.sock'),'-uroot','-e',
             "CREATE DATABASE railway_p0_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER 'root'@'127.0.0.1' IDENTIFIED BY ''; GRANT ALL PRIVILEGES ON railway_p0_test.* TO 'root'@'127.0.0.1';"])
    print(json.dumps({'prepared':True,'directory':str(folder),'mysqlPort':13317,'tlsMqttPort':18884,'rtspPort':18554}))


def cleanup(folder):
    state=json.loads((folder/'test-services.json').read_text());assert state['directory']==str(folder)
    for name,identifier in state['containers'].items():
        result=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
        if result.returncode:continue
        value=json.loads(result.stdout)[0]
        if value['Id']!=identifier or value['Config']['Labels'].get(LABEL)!=str(folder):raise RuntimeError('test container identity changed')
        subprocess.run(['docker','rm','-fv',name],check=True,stdout=subprocess.DEVNULL)
    if state['network']:
        result=subprocess.run(['docker','network','inspect',state['network']],capture_output=True,text=True)
        if result.returncode==0:
            value=json.loads(result.stdout)[0]
            if value['Labels'].get(LABEL)!=str(folder):raise RuntimeError('test network identity changed')
            subprocess.run(['docker','network','rm',state['network']],check=True,stdout=subprocess.DEVNULL)
    if state['mysqlPid']:
        process=Path('/proc')/str(state['mysqlPid'])/'cmdline'
        if process.exists():
            command=process.read_bytes()
            if ('--datadir='+str(folder/'mysql')).encode() not in command or b'--port=13317' not in command:raise RuntimeError('test MySQL identity changed')
            subprocess.run([str(MYSQL/'bin/mysqladmin'),'--no-defaults','--protocol=socket','--socket='+str(folder/'mysql.sock'),'-uroot','shutdown'],check=True)
    state['cleanedUp']=True;(folder/'test-services.json').write_text(json.dumps(state,indent=2))
    print('Only recorded isolated test services cleaned up; evidence retained.')


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','cleanup'));parser.add_argument('--directory',required=True)
    args=parser.parse_args();folder=Path(args.directory).resolve()
    if ROOT/'workspace/runtime/p0-reaudit' not in folder.parents:raise SystemExit('Use a disposable directory under workspace/runtime/p0-reaudit')
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    (prepare if args.action=='prepare' else cleanup)(folder)
