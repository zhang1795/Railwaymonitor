"""Guarded local P1 stability rollout: additive schema, private backups, identity checks.

Explicitly limited to this project's loopback 3307/18080 installation. Does not
change cameras, risk rules, receipts, provider destinations or Docker images.
"""
import argparse,json,os,sqlite3,subprocess,sys,time
from pathlib import Path
from urllib.request import urlopen
from stage_backend import stage_artifact
from stage_detector import stage_source_tree
from stop_managed import process,expected,stop

ROOT=Path(__file__).resolve().parents[1];RUNTIME=ROOT/'workspace/runtime'

def rollout(acceptance_directory=None):
    os.umask(0o077)
    folder=RUNTIME/'p1-rollout'/time.strftime('%Y%m%d-%H%M%S-stability');folder.mkdir(parents=True,mode=0o700)
    old={}
    for name in ('backend','flask','detector'):
        pid=int((RUNTIME/'pids'/(name+'.pid')).read_text());info=process(pid)
        if info is None or not expected(name,ROOT,info[1],info[2]):raise RuntimeError('current '+name+' identity mismatch')
        env=dict(item.decode().split('=',1) for item in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0') if b'=' in item)
        old[name]={'pid':pid,'args':info[1],'cwd':str(info[2]),'env':env}
    assert old['backend']['env']['SERVER_PORT']=='18080'
    assert Path(old['detector']['env']['DETECTOR_OUTPUT_DIR']).resolve()==RUNTIME/'detector-output'
    assert old['detector']['env']['EVIDENCE_SERVICE_KEY']==old['backend']['env']['EVIDENCE_SERVICE_KEY']
    client=['/data/anaconda3/bin/mysql','--no-defaults','--protocol=socket','--socket='+str(RUNTIME/'mysql/run/mysql.sock'),'-uroot','--batch','--skip-column-names','railway_monitoring']
    def query(sql):return subprocess.check_output(client+['-e',sql],text=True).strip()
    assert query('SELECT @@port')=='3307'
    def tasks():return {line.split('\t')[0]:line.split('\t')[1:] for line in query('SELECT camera_id,enabled,session_id,state FROM monitoring_task ORDER BY camera_id').splitlines()}
    before=tasks();record={'beforeTasks':before,'startedAt':time.time(),'beforeLegacy':int(query('SELECT COUNT(*) FROM abnormal_event WHERE source_key IS NULL')),'oldProcesses':{name:{k:v for k,v in spec.items() if k!='env'} for name,spec in old.items()}}
    def manual_fields():
        rows=query("SELECT id,SHA2(CONCAT_WS('|',status,COALESCE(handler_id,-1),COALESCE(DATE_FORMAT(handle_time,'%Y%m%d%H%i%s%f'),''),HEX(COALESCE(handle_result,'')),COALESCE(manual_override,0)),256) FROM abnormal_event ORDER BY id")
        return dict(line.split('\t') for line in rows.splitlines())
    manual_before=manual_fields()
    def save():(folder/'deployment.json').write_text(json.dumps(record,indent=2))
    save();(folder/'private-process-config.json').write_text(json.dumps(old))
    for name in ('.env','.env.p0'):(folder/(name+'.before')).write_bytes((ROOT/'deploy'/name).read_bytes())
    with (folder/'before.sql').open('wb') as out:
        subprocess.run(['/data/anaconda3/bin/mysqldump','--no-defaults','--protocol=socket','--socket='+str(RUNTIME/'mysql/run/mysql.sock'),'-uroot','--single-transaction','--routines','--triggers','railway_monitoring'],stdout=out,check=True);out.flush();os.fsync(out.fileno())
    def sqlite_backup(suffix):
        for name,source in [('events',RUNTIME/'detector-output/events.sqlite3'),('evidence',RUNTIME/'detector-output/evidence.sqlite3'),('manifests',RUNTIME/'full-recordings/manifests.sqlite3')]:
            if not source.exists():continue
            with sqlite3.connect(str(source)) as db,sqlite3.connect(str(folder/(name+'-'+suffix+'.sqlite3'))) as backup:
                db.backup(backup);assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    sqlite_backup('before')
    jar=stage_artifact(ROOT/'web-springboot/target/railway-monitoring-1.0.0.jar',RUNTIME/'releases/backend')
    detector=stage_source_tree(ROOT/'RailwayDetector',RUNTIME/'releases/detector')
    gateway=stage_source_tree(ROOT/'web-flask',RUNTIME/'releases/gateway',required=('app.py',))
    acceptance_directory=Path(acceptance_directory or RUNTIME/'p0-reaudit/p2').resolve()
    if RUNTIME/'p0-reaudit' not in acceptance_directory.parents:raise RuntimeError('acceptance must belong to the project isolated test directory')
    record['acceptanceDirectory']=str(acceptance_directory);save()
    acceptance=json.loads((acceptance_directory/'live-runtime-result.json').read_text())
    assert acceptance['runMode']=='FULL' and acceptance['pendingFinal']==0 and acceptance['rejectedEvents']==0,'full isolated runtime acceptance required'
    assert acceptance['backendHash']==jar.parent.name and acceptance['detectorHash']==detector.name and acceptance['gatewayHash']==gateway.name,'tested artifacts must match rollout artifacts'
    assert all(acceptance.get(key) is True for key in ('authenticatedSharedLiveDetectionFrame','liveSourceDecodeChecked','sampledAnalysisArchiveRegistered','exactSampleVideoPts','preservedFullSourceRecording')),'detection-view acceptance required'
    assert str(jar) not in old['backend']['args'],'already on this jar; refusing redundant restart'
    updates={'FULL_RECORDING_ROOT':str(RUNTIME/'full-recordings'),'SOURCE_RECORDING_ENABLED':'true','SOURCE_SEGMENT_SECONDS':'30','SAMPLED_RECORDING_ENABLED':'false','RECORDING_MAX_BYTES':'2000000000000','RECORDING_RETENTION_DAYS':'30','RECORDING_MIN_FREE_BYTES':'1073741824','DETECTOR_STALL_SECONDS':'120','RAILWAY_PROJECT_ROOT':str(ROOT)}
    updates.update(LIVE_RESULTS_ENABLED='true',LIVE_RESULTS_MAX_FPS='2',ANALYSIS_RECORDING_ENABLED='true',ANALYSIS_MAX_SAMPLE_FPS='2',VIDEO_DECODE_THREADS='4',VIDEO_MAX_RELATIVE_LAG_MS='2000')
    for migration in ('p1-alarm-migration.sql','p1-stability-migration.sql','p1-visualization-migration.sql','risk-template-migration.sql'):
        subprocess.run(client,input=(ROOT/'web-springboot/src/main/resources/db'/migration).read_text(),text=True,check=True)
    subprocess.run([sys.executable,str(ROOT/'deploy/apply_stability_indexes.py'),'--socket',str(RUNTIME/'mysql/run/mysql.sock'),'--database','railway_monitoring'],check=True)
    path=ROOT/'deploy/.env.p0';lines=[line for line in path.read_text().splitlines() if line.partition('=')[0] not in updates]
    tmp=path.with_suffix('.stability-tmp');tmp.write_text('\n'.join(lines+[key+'='+value for key,value in updates.items()])+'\n');tmp.chmod(0o600);tmp.replace(path)
    envs={name:dict(spec['env'],**updates) for name,spec in old.items()}
    private_channels=('NOTIFY_WEBHOOK_URL','NOTIFY_WEBHOOK_KEY','SMS_ACCESS_KEY_ID','SMS_ACCESS_KEY_SECRET','SMS_SIGN_NAME','SMS_TEMPLATE_CODE','SMS_RECIPIENTS','SMS_TEMPLATE_PARAMS_JSON')
    for name in ('flask','detector'):
        for key in private_channels:envs[name].pop(key,None)
    for key in ('EVIDENCE_SERVICE_KEY','MQTT_USERNAME','MQTT_PASSWORD','MQTT_BACKEND_USERNAME','MQTT_BACKEND_PASSWORD','DB_URL','DB_USERNAME','DB_PASSWORD','RAILWAY_EMQX_COOKIE','EMQX_DASHBOARD_PASSWORD','MQTT_SERVER_KEY'):envs['flask'].pop(key,None)
    envs['flask']['DETECTOR_CODE_ROOT']=str(detector)
    envs['backend'].pop('DEBUG',None)
    # Source publishers are also managed here. Preserve their existing private
    # specs when replacing the three application releases.
    manifest=RUNTIME/'managed-services.json'
    specs=json.loads(manifest.read_text()) if manifest.exists() else {}
    (folder/'managed-services.before.json').write_text(json.dumps(specs))
    def start(name,args,env,cwd,register=True):
        with (RUNTIME/'logs'/(name+'.log')).open('ab',buffering=0) as out:
            child=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        (RUNTIME/'pids'/(name+'.pid')).write_text(str(child.pid)+'\n')
        if register:specs[name]={'args':args,'env':env,'cwd':str(cwd),'startupGrace':180,'health':'http://127.0.0.1:'+('18080/api/health/live' if name=='backend' else '5000/api/health')}
        return child
    def ready(url,pid,timeout=45):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline and process(pid):
            try:
                with urlopen(url,timeout=2) as response:
                    if response.status==200:return True
            except Exception:pass
            time.sleep(.25)
        return False
    stop('guardian',ROOT)
    start_at=time.monotonic();stop('backend',ROOT)
    args=old['backend']['args'].copy();args[args.index('-jar')+1]=str(jar)
    backend=start('backend',args,envs['backend'],ROOT)
    if not ready('http://127.0.0.1:18080/api/health/ready',backend.pid):
        stop('backend',ROOT);rollback=start('backend',old['backend']['args'],old['backend']['env'],ROOT,False)
        record.update(backendRolledBack=True,rollbackPid=rollback.pid);save();raise RuntimeError('new backend not ready; prior immutable jar restarted')
    record['backendReadySeconds']=round(time.monotonic()-start_at,3);save()
    stop('flask',ROOT)
    gateway_args=[str(RUNTIME/'flask-venv/bin/python'),'-m','gunicorn','--no-control-socket','--workers','1','--worker-class','gthread','--threads','80','--timeout','30','--graceful-timeout','15','--bind','127.0.0.1:5000','app:app']
    flask=start('flask',gateway_args,envs['flask'],gateway)
    if not ready('http://127.0.0.1:5000/api/health',flask.pid,20):
        stop('flask',ROOT);start('flask',old['flask']['args'],old['flask']['env'],Path(old['flask']['cwd']),False);raise RuntimeError('gateway restart failed; prior startup parameters restored')
    start_at=time.monotonic();stop('detector',ROOT);sqlite_backup('after-stop')
    worker=start('detector',old['detector']['args'],envs['detector'],detector)
    deadline=time.monotonic()+120;recovered=False
    while time.monotonic()<deadline:
        assert process(backend.pid),'backend exited during switch'
        if not process(worker.pid):
            start('detector',old['detector']['args'],old['detector']['env'],Path(old['detector']['cwd']),False);raise RuntimeError('new detector exited; prior immutable detector restarted')
        after=tasks();recovered=all(after.get(camera,['?'])[0]==row[0] and (row[0]!='1' or after[camera][2]=='RUNNING' and after[camera][1]!=row[1]) for camera,row in before.items())
        if recovered:break
        time.sleep(.5)
    record.update(afterTasks=after,intentPreserved=all(after.get(camera,['?'])[0]==row[0] for camera,row in before.items()),enabledRunning=recovered,detectorRecoverySeconds=round(time.monotonic()-start_at,3),newBackend=backend.pid,newFlask=flask.pid,newDetector=worker.pid,newJar=str(jar),detectorRelease=str(detector),gatewayRelease=str(gateway),afterLegacy=int(query('SELECT COUNT(*) FROM abnormal_event WHERE source_key IS NULL')));save()
    manual_after=manual_fields();record.update(comparedHumanRecords=len(manual_before),humanRecordsUnchanged=all(manual_after.get(key)==value for key,value in manual_before.items()),enabledCameraCount=sum(row[0]=='1' for row in before.values()));save()
    assert recovered and record['intentPreserved'] and record['beforeLegacy']==record['afterLegacy']
    tmp=manifest.with_suffix('.tmp');tmp.write_text(json.dumps(specs));tmp.chmod(0o600);tmp.replace(manifest)
    guardian=start('guardian',[sys.executable,str(ROOT/'deploy/guardian.py'),'--root',str(ROOT)],{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8'},ROOT,False)
    record['guardianPid']=guardian.pid;record['completedAt']=time.time();save()
    print(json.dumps({'folder':str(folder),'backendReadySeconds':record['backendReadySeconds'],'detectorRecoverySeconds':record['detectorRecoverySeconds'],'intentPreserved':record['intentPreserved'],'enabledRunning':record['enabledRunning'],'legacyPreserved':record['beforeLegacy']==record['afterLegacy']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--acceptance-directory');args=parser.parse_args()
    if not args.apply:raise SystemExit('Read deploy/P1-STABILITY-ROLLOUT.md and run with --apply only after acceptance')
    rollout(args.acceptance_directory)
