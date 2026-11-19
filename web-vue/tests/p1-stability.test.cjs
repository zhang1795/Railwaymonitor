const test=require('node:test'),assert=require('node:assert/strict')
const {fixture,flush}=require('./frontend-fixture.cjs')

test('source corruption stays visible after stream termination and does not leave a stale picture',()=>{
  const f=fixture({props:{camera:{id:1},isActive:true}})
  const p=f.component('components/VideoPlayer/index.vue',['handleMessage','connectionErrorMessage','hasConnectionError'])
  p.handleMessage({type:'source_quality',data:{cameraId:1,state:'CORRUPT'}})
  p.handleMessage({type:'stream_stopped',data:{cameraId:1}})
  assert.equal(p.hasConnectionError.value,true);assert.match(p.connectionErrorMessage.value,/解码损坏/);f.unmount()
})

test('a recent RUNNING report needs real inference and frame progress',()=>{
  const f=fixture(),{monitoringLabel}=f.module('@/composables/useMonitoring'),now=f.now()
  const row={enabled:true,state:'RUNNING',last_status_at:new Date(now).toISOString()}
  assert.match(monitoringLabel(row,true,now),/尚未验证/)
  row.metrics={lastFrameAt:new Date(now).toISOString(),lastInferenceAt:new Date(now-60000).toISOString()}
  assert.match(monitoringLabel(row,true,now),/停滞/)
  row.metrics.lastInferenceAt=new Date(now).toISOString();assert.equal(monitoringLabel(row,true,now),'检测中');f.unmount()
})
test('human completion opens a result form and freezes version, prevents double submit',async()=>{
  const writes=[];let resolve
  const f=fixture({modules:{'@/api/Abnormal':{handleAbnormalEvent:value=>{writes.push(value);return new Promise(done=>resolve=done)}}}})
  const p=f.component('views/Abnormal/index.vue',['handleComplete','handleForm','handleVisible','handleFormRef','submitHandle'])
  p.handleComplete({id:7,version:4});assert.equal(p.handleVisible.value,true);assert.equal(writes.length,0)
  p.handleFormRef.value={validate:async()=>true};p.handleForm.handleResult='verified'
  const pending=p.submitHandle();await flush();p.handleForm.handleResult='later edit';await p.submitHandle()
  assert.equal(writes.length,1);assert.equal(writes[0].version,4);assert.equal(writes[0].handleResult,'verified')
  f.unmount();resolve();await pending;assert.equal(f.messages.length,0)
})
test('a human version conflict keeps the result dialog open without claiming success',async()=>{
  const f=fixture({modules:{'@/api/Abnormal':{handleAbnormalEvent:async()=>{throw {code:409}}}}})
  const p=f.component('views/Abnormal/index.vue',['handleComplete','handleFormRef','submitHandle','handleVisible'])
  p.handleComplete({id:7,version:1});p.handleFormRef.value={validate:async()=>true};await p.submitHandle()
  assert.equal(p.handleVisible.value,true);assert.equal(f.messages.filter(item=>item.kind==='success').length,0);f.unmount()
})
test('fault acknowledgement sends only the displayed IDs; a late query cannot update a departed page',async()=>{
  let data={items:[{id:7}],openCount:1,unreadCount:1};const reads=[];let resolve
  const f=fixture({modules:{'@/api/request':{__esModule:true,default:{get:async()=>data,post:async(path,body)=>reads.push(body.ids)}}}})
  const p=f.component('components/MonitoringFaultInbox/index.vue',['data','markRead','refresh'])
  await f.mount();data={items:[{id:8}],openCount:1,unreadCount:1};await p.markRead();assert.deepEqual(reads,[[7]])
  f.modules['@/api/request'].default.get=()=>new Promise(done=>resolve=done)
  const pending=p.refresh();f.unmount();resolve({items:[],openCount:0,unreadCount:0});await pending
  assert.equal(p.data.value.items[0].id,8);assert.equal(f.jobs.size,0)
})
test('recording filter changes discard an older response and reset pagination',async()=>{
  const calls=[]
  const f=fixture({modules:{'@/api/recordings':{getRecordings:(camera,args)=>new Promise(done=>calls.push({camera,args,done}))}}})
  const p=f.component('views/recordings/index.vue',['camera','items','next','load'])
  p.camera.value=1;await f.vue.nextTick();const first=p.load();await flush()
  p.camera.value=2;await f.vue.nextTick();const second=p.load();await flush()
  calls[1].done({items:[{id:'second'}],next:null});await second
  calls[0].done({items:[{id:'first'}],next:{beforeId:'old'}});await first
  assert.equal(p.items.value[0].id,'second');assert.equal(p.next.value,null);f.unmount()
})
test('provider acceptance and an uncertain send result never show carrier delivery',()=>{
  const f=fixture(),{deliveryLabel}=f.module('@/utils/riskDisplay')
  assert.match(deliveryLabel('ACCEPTED'),/待回执/);assert.match(deliveryLabel('UNKNOWN'),/未知/)
  assert.match(deliveryLabel('DELIVERED'),/运营商回执已送达/);f.unmount()
})
test('statistics without measured samples stay unknown even if an old API supplies a rate',async()=>{
  const response={totalCount:1,onlineCount:1,offlineCount:0,faultCount:0,statusDistribution:[],faultTypeDistribution:[],onlineRateTrend:[{date:'2026-11-11',rate:100}]}
  const f=fixture({modules:{echarts:{},'@/api/statistics':{getDeviceStatusStatistics:async()=>response}}})
  const p=f.component('views/statistics/DeviceStatus.vue',['statistics','fetchData'])
  await p.fetchData();assert.equal(p.statistics.value.onlineRateTrend[0].rate,null)
  response.trendSource='DETECTION_CHAIN_SAMPLES';response.onlineRateTrend[0].knownSamples=1
  await p.fetchData();assert.equal(p.statistics.value.onlineRateTrend[0].rate,100);f.unmount()
})
test('manual coordinates allow camera creation without the map and reject missing/out-of-range input',async()=>{
  const writes=[],f=fixture({modules:{'@/api/camera':{createCamera:async value=>writes.push(value)}}})
  const p=f.component('views/camera/index.vue',['form','formRef','submitForm'])
  p.formRef.value={validate:async()=>true};await p.submitForm();assert.equal(writes.length,0)
  p.form.longitude='181';p.form.latitude='36';await p.submitForm();assert.equal(writes.length,0)
  p.form.longitude='0';p.form.latitude='0';await p.submitForm();assert.equal(writes.length,1)
  assert.equal(writes[0].longitude,0);assert.equal(writes[0].latitude,0);f.unmount()
})
test('editing an old camera with no coordinates does not invent zero coordinates',async()=>{
  const writes=[],f=fixture({modules:{'@/api/camera':{updateCamera:async value=>writes.push(value)}}})
  const p=f.component('views/camera/index.vue',['form','formRef','dialogType','submitForm'])
  p.dialogType.value='update';p.formRef.value={validate:async()=>true};await p.submitForm()
  assert.equal(writes.length,1);assert.equal(writes[0].longitude,undefined);assert.equal(writes[0].latitude,undefined);f.unmount()
})
