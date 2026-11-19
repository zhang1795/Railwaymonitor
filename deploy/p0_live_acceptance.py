"""Opt-in runtime fault acceptance on p0_test_environment.py services only."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from urllib.request import Request, build_opener, HTTPCookieProcessor, urlopen
from urllib.parse import quote
from stage_backend import stage_artifact
from stage_detector import stage_source_tree

ROOT=Path(__file__).resolve().parents[1]
MYSQL=Path('/data/anaconda3')
JAVA=ROOT/'workspace/runtime/jdk17/usr/lib/jvm/java-17-openjdk-amd64/bin/java'
PYTHON=ROOT/'workspace/runtime/detector-env/bin/python'
JAR=ROOT/'web-springboot/target/railway-monitoring-1.0.0.jar'
NODE=Path('/home/a6411/.nvm/versions/node/v22.19.0/bin/node')


def wait_for(predicate,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            result=predicate()
            if result:return result
        except (OSError,ValueError,subprocess.CalledProcessError):pass
        time.sleep(.2)
    raise AssertionError('runtime acceptance condition timed out')


class Session:
    def __init__(self,password):
        self.password=password
        self.client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def api(self,path,body=None,method='GET'):
        headers={}
        if method!='GET':
            csrf=self.api('/auth/csrf');headers[csrf['headerName']]=csrf['token'];headers['Content-Type']='application/json'
        request=Request('http://127.0.0.1:18090/api'+path,None if body is None else json.dumps(body).encode(),headers,method=method)
        with self.client.open(request,timeout=4) as response:result=json.load(response)
        if result['code']!=200:raise AssertionError('API rejected '+path)
        return result.get('data')
    def login(self):self.api('/user/login',{'username':'admin','password':self.password},'POST')


class Acceptance:
    def __init__(self,folder):
        self.folder=folder;self.children=[];self.logs=[]
        self.state=json.loads((folder/'test-services.json').read_text())
        assert not self.state.get('cleanedUp') and self.state['directory']==str(folder)
        self.env=os.environ.copy();self.env.pop('DEBUG',None)
        self.env.update(dict(line.split('=',1) for line in (folder/'services.env').read_text().splitlines()))
        assert self.env['P0_MQTT_URI']=='ssl://localhost:18884'
        assert self.env['P0_TEST_DB_URL'].startswith('jdbc:mysql://127.0.0.1:13317/railway_p0_test?'),'refusing non-test JDBC URL'
        cache=Path(tempfile.mkdtemp(prefix='cold-assets-',dir=folder))
        self.env.update(DB_URL=self.env['P0_TEST_DB_URL'],DB_USERNAME='root',DB_PASSWORD='',MQTT_ENABLED='true',
            NOTIFY_WEBHOOK_URL='',NOTIFY_WEBHOOK_KEY='',SMS_ACCESS_KEY_ID='',SMS_ACCESS_KEY_SECRET='',SMS_SIGN_NAME='',SMS_TEMPLATE_CODE='',SMS_RECIPIENTS='',
            SERVER_ADDRESS='127.0.0.1',SERVER_PORT='18090',SESSION_COOKIE_SECURE='false',
            FLASK_HOST='127.0.0.1',FLASK_PORT='15000',BACKEND_INTERNAL_URL='http://127.0.0.1:18090/api',
            EVIDENCE_INGEST_URL='http://127.0.0.1:18090/api',EVIDENCE_ROOT=str(folder/'evidence-files'),PREVIEW_ALLOWED_ORIGINS='http://127.0.0.1:3000,http://127.0.0.1:13000',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',
            FULL_RECORDING_ROOT=str(folder/'full-recordings'),SOURCE_RECORDING_ENABLED='true',SOURCE_SEGMENT_SECONDS='5',
            RAILWAY_MODEL_PATH=str(ROOT/'RailwayDetector/models/best1030.pt'),RAILWAY_DEVICE='cpu',
            YOLOV5_CONFIG_DIR=str(cache/'yolo'),MPLCONFIGDIR=str(cache/'matplotlib'),
            XDG_CONFIG_HOME=str(cache/'config'),XDG_CACHE_HOME=str(cache/'cache'))
        self.password=secrets.token_urlsafe(24)
        self.jar=stage_artifact(JAR,folder/'backend-releases')
        self.detector=stage_source_tree(ROOT/'RailwayDetector',folder/'detector-releases')
        self.gateway=stage_source_tree(ROOT/'web-flask',folder/'gateway-releases',required=('app.py',))
        self.env.update(RAILWAY_PROJECT_ROOT=str(ROOT),DETECTOR_CODE_ROOT=str(self.detector))
        self.session=Session(self.password)
        assert self.query('SELECT @@port')=='13317','must use isolated MySQL'
        for name,identifier in self.state['containers'].items():
            value=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
            assert value['Id']==identifier and value['Config']['Labels'].get('railway.p0.test.directory')==str(folder)
    def stage(self,text):
        (self.folder/'live-stage.txt').write_text(text);print(text,flush=True)
    def query(self,sql):
        return subprocess.check_output([str(MYSQL/'bin/mysql'),'--no-defaults','--protocol=socket',
            '--socket='+str(self.folder/'mysql.sock'),'-uroot','--batch','--skip-column-names','railway_p0_test','-e',sql],text=True).strip()
    def spawn(self,name,args,cwd=ROOT,env=None):
        output=(self.folder/(name+'.log')).open('a');self.logs.append(output)
        process=subprocess.Popen([str(arg) for arg in args],cwd=cwd,env=env or self.env,
            stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        self.children.append(process);return process
    @staticmethod
    def stop(process,hard=False):
        if process is None or process.poll() is not None:return
        (process.kill if hard else process.terminate)()
        try:process.wait(10)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    def backend(self):
        process=self.spawn('live-backend',[JAVA,'-jar',self.jar,'--railway.reconcile-ms=1000',
            '--railway.mqtt.persistence='+str(self.folder/'live-backend-persistence')])
        wait_for(lambda:self.ready(process),30)
        self.session=Session(self.password);self.session.login();return process
    def ready(self,process):
        if process.poll() is not None:raise AssertionError('packaged backend exited')
        with urlopen('http://127.0.0.1:18090/api/auth/csrf',timeout=1) as response:return response.status==200
    def pending(self,folder):return json.loads((folder/'metrics.json').read_text())['pending']
    def task(self):return next(row for row in self.session.api('/monitoring') if row['camera_id']==1)
    def start_mysql(self):
        process=self.spawn('live-mysql',[MYSQL/'bin/mysqld','--no-defaults','--basedir='+str(MYSQL),
            '--lc-messages-dir='+str(MYSQL/'share/mysql'),'--datadir='+str(self.folder/'mysql'),
            '--port=13317','--bind-address=127.0.0.1','--socket='+str(self.folder/'mysql.sock'),
            '--pid-file='+str(self.folder/'mysql.pid'),'--log-error='+str(self.folder/'mysql.log'),
            '--skip-log-bin','--skip-name-resolve','--character-set-server=utf8mb4','--collation-server=utf8mb4_unicode_ci'])
        # MySQL is owned by the environment cleanup, rather than the child
        # service cleanup below. Preserve it for verification/evidence reads.
        self.children.remove(process)
        self.state['mysqlPid']=process.pid;(self.folder/'test-services.json').write_text(json.dumps(self.state,indent=2))
        wait_for(lambda:self.query('SELECT 1')=='1')
    def run(self):
        self.stage('Resetting only isolated test fixtures and MQTT test sessions')
        # Retain previous failed-run media for inspection, but do not replay its
        # manifests into the newly reset fixture sessions.
        for name in ('full-recordings','evidence-files'):
            previous=self.folder/name
            if previous.exists():previous.rename(self.folder/(name+'-prior-'+str(time.time_ns())))
        # The test database is rebuilt between suites. Clear broker sessions
        # only in this disposable environment to avoid mixing those histories.
        reset="""import os,threading,paho.mqtt.client as m
for prefix in ('MQTT_','MQTT_BACKEND_'):
 c=m.Client(m.CallbackAPIVersion.VERSION2,clean_session=True);c.username_pw_set(os.environ[prefix+'USERNAME'],os.environ[prefix+'PASSWORD']);c.tls_set(ca_certs=os.environ['MQTT_CA_FILE']);done=threading.Event();c.on_connect=lambda a,b,d,r,p:done.set() if r==0 else None;c.connect('localhost',18884,10);c.loop_start();assert done.wait(5);c.disconnect();c.loop_stop()
"""
        subprocess.run([str(PYTHON),'-c',reset],env=self.env,check=True)
        for table in ('notification_delivery','recording_analysis','recording_clip','monitoring_fault_receipt','monitoring_fault','monitoring_health_sample','monitoring_metric','alarm_edit_version','worker_evidence_status','alarm_evidence','alarm_notice_receipt','alarm_notice','alarm_handling_audit','alarm_transition','alarm_source_link','risk_incident','risk_track','session_risk_policy','camera_risk_revision','camera_risk_rule','alarm_notice_read','preview_grant','detection_track','detection_rejection','detection_receipt','monitoring_task','monitoring_session','abnormal_event','camera','user'):
            self.query('DELETE FROM `'+table+'`')
        credentials=quote(self.env['P0_RTSP_USERNAME'],safe='')+':'+quote(self.env['P0_RTSP_PASSWORD'],safe='')
        self.query("INSERT INTO camera(id,name,location,rtsp_url,status) VALUES(1,'isolated acceptance','test only','rtsp://"+credentials+"@127.0.0.1:18554/p0_live_source',3)")
        with (self.folder/'live-admin-bootstrap.log').open('w') as output:
            subprocess.run([str(JAVA),'-Dloader.main=com.example.security.AdminBootstrap','-cp',str(self.jar),
                'org.springframework.boot.loader.launch.PropertiesLauncher'],env=self.env,input=self.password+'\n',text=True,
                stdout=output,stderr=subprocess.STDOUT,check=True)
        backend=self.backend()
        policy={'enabled':True,'classes':[2],'roi':[0,0,1,1],'confidence':.5,'dwellSeconds':0,'graceSeconds':3,'reminderSeconds':60,'level':3,'escalateSeconds':180,'revision':0}
        self.session.api('/camera/1/risk-rule',policy,'PUT')
        alarms=lambda:None
        full_run=os.getenv('P1_REAL_ONLY')!='true'
        if full_run:
            worker_folder=Path(tempfile.mkdtemp(prefix='live-synthetic-',dir=self.folder))
            worker=self.spawn('live-synthetic-worker',[PYTHON,ROOT/'RailwayDetector/tests/mqtt_integration_driver.py',worker_folder])
            self.session.api('/monitoring/1',{'enabled':True},'PUT');session=self.task()['session_id']
            assert len(session)==32 and all(char in 'abcdef0123456789' for char in session)
            alarms=lambda:int(self.query("SELECT COUNT(*) FROM detection_track WHERE session_id='"+session+"'"))
            wait_for(lambda:alarms()==1);wait_for(lambda:self.task()['state']=='RUNNING')
            wait_for(lambda:self.pending(worker_folder)==0)
            self.stage('Verifying a real 60-second continuous-risk reminder after read and human resolution')
            alarm=int(self.query("SELECT alarm_id FROM detection_track WHERE session_id='"+session+"'"))
            first=self.session.api('/alarm-notices')['items'][0]['noticeId']
            self.session.api('/alarm-notices/read',{'noticeIds':[first]},'POST')
            actor=self.session.api('/user/current')['id']
            self.session.api('/Abnormal-event/'+str(alarm)+'/handle',{'id':alarm,'handlerId':actor,'handleResult':'isolated operator check','version':self.session.api('/Abnormal-event/'+str(alarm))['version']},'POST')
            wait_for(lambda:int(self.query("SELECT COUNT(*) FROM alarm_notice WHERE alarm_id="+str(alarm)+" AND kind='ONGOING'"))>=1,72)
            assert alarms()==1 and self.query('SELECT status FROM abnormal_event WHERE id='+str(alarm))=='2'
            assert self.query("SELECT COUNT(*) FROM alarm_notice WHERE alarm_id="+str(alarm)+" AND kind='ONGOING'")=='1'
            assert self.session.api('/alarm-notices')['unreadCount']==1
            self.stage('Injecting isolated MySQL outage; unacknowledged events must remain on disk')
            subprocess.run([str(MYSQL/'bin/mysqladmin'),'--no-defaults','--protocol=socket',
                '--socket='+str(self.folder/'mysql.sock'),'-uroot','shutdown'],check=True)
            wait_for(lambda:self.pending(worker_folder)>0,8)
            self.start_mysql()
            wait_for(lambda:self.pending(worker_folder)==0,45)
            assert alarms()==1 and self.task()['session_id']==session
            self.stage('Hard-killing packaged backend; persistent intent and same worker session must recover')
            receipts=int(self.query('SELECT COUNT(*) FROM detection_receipt'))
            self.stop(backend,hard=True);wait_for(lambda:self.pending(worker_folder)>0,8)
            backend=self.backend()
            assert self.task()['enabled'] and self.task()['session_id']==session
            wait_for(lambda:self.task()['state']=='RUNNING')
            wait_for(lambda:int(self.query('SELECT COUNT(*) FROM detection_receipt'))>receipts)
            wait_for(lambda:self.pending(worker_folder)==0,30);assert alarms()==1
            self.session.api('/monitoring/1',{'enabled':False},'PUT');wait_for(lambda:self.task()['state']=='STOPPED')
            self.stop(worker)
        self.stage('Starting real YOLO/RTSP, authenticated two-viewer preview and logout tests')
        ffmpeg=ROOT/'workspace/runtime/detector-env/lib/python3.8/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux64-v4.2.2'
        video=ROOT/'workspace/runtime/smoke-cow-short.mp4'
        assert video.exists() and Path(self.env['RAILWAY_MODEL_PATH']).exists(),'real-model assets unavailable'
        self.spawn('live-rtsp-publisher',[ffmpeg,'-hide_banner','-loglevel','warning','-nostats','-nostdin','-re',
            '-stream_loop','-1','-i',video,'-c','copy','-f','rtsp','-rtsp_transport','tcp','rtsp://127.0.0.1:18554/p0_live_source'])
        self.spawn('live-flask',[ROOT/'workspace/runtime/flask-venv/bin/python','-m','gunicorn','--no-control-socket','--workers','1','--worker-class','gthread','--threads','80','--timeout','30','--graceful-timeout','15','--bind','127.0.0.1:15000','app:app'],self.gateway)
        wait_for(lambda:urlopen('http://127.0.0.1:15000/api/health',timeout=1).status==200)
        real_folder=Path(tempfile.mkdtemp(prefix='live-real-worker-',dir=self.folder))
        real_env=dict(self.env,DETECTOR_OUTBOX_PATH=str(real_folder/'events.sqlite3'),DETECTOR_OUTPUT_DIR=str(real_folder/'media'))
        self.spawn('live-real-worker',[PYTHON,'ui.py'],self.detector,real_env)
        self.session.api('/monitoring/1',{'enabled':True},'PUT');real_session=self.task()['session_id']
        assert len(real_session)==32 and all(char in 'abcdef0123456789' for char in real_session)
        real_count=lambda:int(self.query("SELECT COUNT(*) FROM detection_track WHERE session_id='"+real_session+"'"))
        wait_for(lambda:real_count()>0,45)
        assert int(self.query("SELECT COUNT(DISTINCT a.id) FROM abnormal_event a JOIN detection_track t ON a.id=t.alarm_id WHERE t.session_id='"+real_session+"' AND a.detected_type='牛'"))>0
        wait_for(lambda:int(self.query('SELECT COUNT(*) FROM alarm_evidence'))>0,20)
        wait_for(lambda:int(self.query('SELECT COUNT(*) FROM recording_clip'))>0,30)
        def fresh_frame():
            result=self.session.api('/monitoring/1/frame')
            return result if result.get('state')=='FRESH' and result.get('frame',{}).get('quality')=='DECODE_CHECKED' and result.get('frame',{}).get('objects') else None
        live_frame=wait_for(fresh_frame,20)['frame']
        assert live_frame['sessionId']==real_session,'live frame belongs to another worker session'
        assert live_frame['objects'] and live_frame['modelSha256'],'target-bearing frame required for the positive display check'
        unchanged=self.session.api('/monitoring/1/frame?after='+str(live_frame['frameSeq'])+'&session='+real_session)
        # A new inference may legitimately arrive between the two requests.
        assert unchanged['state']=='FRESH' and (unchanged.get('unchanged') or unchanged.get('frame',{}).get('frameSeq',0)>live_frame['frameSeq'])
        recording=next(item for item in self.session.api('/camera/1/recordings')['items'] if item['kind']=='FULL_SOURCE')
        assert recording['state']=='READY'
        request=Request('http://127.0.0.1:18090'+recording['url'],headers={'Range':'bytes=0-31'})
        with self.session.client.open(request,timeout=5) as response:
            assert response.status==206 and len(response.read())==32
        from urllib.error import HTTPError
        try:urlopen('http://127.0.0.1:18090'+recording['url'],timeout=3);raise AssertionError('anonymous recording access accepted')
        except HTTPError as error:assert error.code==401
        file=self.folder/'full-recordings'/self.query("SELECT file_name FROM recording_clip WHERE id='"+recording['id']+"'")
        with (self.folder/'video-decode.log').open('w') as output:
            subprocess.run([str(ffmpeg),'-v','error','-xerror','-i',str(file),'-f','null','-'],stdout=output,stderr=subprocess.STDOUT,check=True,timeout=30)
        assert (self.folder/'video-decode.log').stat().st_size==0,'recorded stream contains decoder errors'
        node_env=dict(self.env,P0_HTTP_URL='http://127.0.0.1:18090/api',P0_WS_URL='ws://127.0.0.1:15000/ws',
            P0_TEST_PASSWORD=self.password,P0_RESULT_FILE=str(self.folder/'live-viewers.json'))
        with (self.folder/'live-node.log').open('w') as output:
            subprocess.run([str(NODE),str(ROOT/'web-vue/tests/p0-live-acceptance.cjs')],env=node_env,
                stdout=output,stderr=subprocess.STDOUT,check=True,timeout=65)
        def sampled_clip():
            return next((item for item in self.session.api('/camera/1/recordings')['items'] if item['kind']=='DETECTION_SAMPLES'),None)
        sampled=wait_for(sampled_clip,40)
        manifest=self.session.api(sampled['analysisUrl'].removeprefix('/api'))
        assert manifest['sessionId']==real_session and manifest['frameCount']>1 and any(frame['objects'] for frame in manifest['frames'])
        sample_file=self.folder/'full-recordings'/self.query("SELECT file_name FROM recording_clip WHERE id='"+sampled['id']+"'")
        check="""import av,json,sys
value=json.load(sys.stdin)
with av.open(value['file']) as clip:
 frames=list(clip.decode(video=0));expected=value['manifest']['frames']
 assert len(frames)==len(expected)
 assert all(abs(frame.time*1000-sample['offsetMs'])<1 for frame,sample in zip(frames,expected))
 assert abs(clip.duration/1000-value['manifest']['durationMs'])<5
print(json.dumps({'frames':len(frames),'exactSamplePts':True,'durationMs':value['manifest']['durationMs']}))
"""
        with (self.folder/'sample-decode.json').open('w') as output:
            subprocess.run([str(PYTHON),'-c',check],input=json.dumps({'file':str(sample_file),'manifest':manifest}),text=True,stdout=output,check=True,timeout=20)
        browser_qa=False
        if os.getenv('P1_BROWSER_QA')=='true':
            self.stage('Checking actual Chromium live display, VFR seek and overlay toggles')
            frontend=self.spawn('live-vite',[NODE,ROOT/'web-vue/node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','13000','--strictPort'],ROOT/'web-vue',dict(self.env,VITE_API_PROXY_TARGET='http://127.0.0.1:18090',VITE_ALGO_WS_URL='ws://127.0.0.1:15000/ws',VITE_AMAP_KEY='',VITE_AMAP_SECURITY_CODE=''))
            wait_for(lambda:urlopen('http://127.0.0.1:13000/login',timeout=2).status==200,20)
            with (self.folder/'browser-qa.log').open('w') as output:
                subprocess.run([str(NODE),str(ROOT/'deploy/tests/browser_detection_views.mjs')],env=dict(self.env,P0_TEST_PASSWORD=self.password,P0_BROWSER_DIRECTORY=str(self.folder)),stdout=output,stderr=subprocess.STDOUT,check=True,timeout=75)
            self.stop(frontend);browser_qa=True
        after_logout=int(self.query('SELECT COUNT(*) FROM detection_receipt'))
        wait_for(lambda:int(self.query('SELECT COUNT(*) FROM detection_receipt'))>after_logout,10)
        assert self.task()['enabled'] and self.task()['state']=='RUNNING'
        self.stage('Measuring three real inference routes with one shared model and no viewers')
        source=self.query('SELECT rtsp_url FROM camera WHERE id=1')
        for camera in (2,3):
            self.query("INSERT INTO camera(id,name,location,rtsp_url,status) VALUES("+str(camera)+",'parallel "+str(camera)+"','isolated only','"+source+"',3)")
            self.session.api('/monitoring/'+str(camera),{'enabled':True},'PUT')
        def all_progress():
            rows=self.session.api('/monitoring')
            return rows if len(rows)==3 and all(row['state']=='RUNNING' and row.get('metrics',{}).get('processedFrames',0)>=3 for row in rows) else None
        parallel=wait_for(all_progress,45)
        baseline={row['camera_id']:row['metrics']['processedFrames'] for row in parallel};window=time.monotonic()
        time.sleep(10);parallel=all_progress();assert parallel;window=time.monotonic()-window
        parallel_metrics=[{'camera':row['camera_id'],'concurrentWindowFps':round((row['metrics']['processedFrames']-baseline[row['camera_id']])/window,3),**{key:row['metrics'].get(key) for key in ('effectiveFps','processedFrames','decodedFrames','skippedFrames','processingP95Ms','inferenceWaitMs','frameAgeMs')}} for row in parallel]
        for row in parallel:
            stamp=row['metrics']['lastInferenceAt'];from datetime import datetime,timezone
            assert (datetime.now(timezone.utc)-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()<35
        for camera in (1,2,3):self.session.api('/monitoring/'+str(camera),{'enabled':False},'PUT')
        wait_for(lambda:all(row['state']=='STOPPED' for row in self.session.api('/monitoring')))
        import sqlite3
        def pending_real():
            with sqlite3.connect('file:'+str(real_folder/'events.sqlite3')+'?mode=ro',uri=True) as connection:
                return connection.execute('SELECT COUNT(*) FROM pending').fetchone()[0]
        wait_for(lambda:pending_real()==0,15)
        assert self.query('SELECT COUNT(*) FROM detection_rejection')=='0'
        cow_count=int(self.query("SELECT COUNT(DISTINCT a.id) FROM abnormal_event a JOIN detection_track t ON a.id=t.alarm_id WHERE t.session_id='"+real_session+"' AND a.detected_type='牛'"))
        result={'runMode':'FULL' if full_run else 'REAL_ONLY','databaseOutageRecovered':full_run,'backendHardKillRecovered':full_run,'persistentIntentRestored':full_run,
            'backendHash':self.jar.parent.name,'detectorHash':self.detector.name,'gatewayHash':self.gateway.name,
            'sameSessionWithinLease':full_run,'syntheticSessionAlarms':alarms(),'realYoloTrackSources':real_count(),'realYoloCowEvents':cow_count,'continuous60SecondReminderAfterReadAndResolution':full_run,
            'authenticatedScreenshotUpload':int(self.query('SELECT COUNT(*) FROM alarm_evidence'))>0,'detectionContinuesAfterLogout':True,'pendingFinal':0,'rejectedEvents':0,
            'authenticatedRtspSource':True,'gunicornWebsocketGateway':True,'independentSourceRecordingDecoded':True,'authenticatedVideoRange':True,
            'authenticatedSharedLiveDetectionFrame':True,'liveSourceDecodeChecked':True,'sampledAnalysisArchiveRegistered':True,'exactSampleVideoPts':True,'preservedFullSourceRecording':True,
            'realBrowserDetectionViews':browser_qa,
            'parallelRealRoutes':parallel_metrics,
            'viewers':json.loads((self.folder/'live-viewers.json').read_text())}
        (self.folder/'live-runtime-result.json').write_text(json.dumps(result,indent=2))
        self.stage('Live runtime fault acceptance passed')
        print(json.dumps(result),flush=True)
    def close(self):
        for process in reversed(self.children):self.stop(process)
        for output in self.logs:output.close()


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);args=parser.parse_args()
    folder=Path(args.directory).resolve()
    if ROOT/'workspace/runtime/p0-reaudit' not in folder.parents:raise SystemExit('Use only the disposable P0 test directory')
    runner=Acceptance(folder)
    try:runner.run()
    finally:runner.close()
