const test=require('node:test'),assert=require('node:assert/strict')
const {fixture,flush}=require('./frontend-fixture.cjs')
function page(f){return f.component('views/monitor/index.vue',['cameras','displayCameras','activeCamera','layout','monitoring','handleCameraSelect','toggleMonitoring','handleWebSocketMessage','updateDisplayCameras'])}

test('opening and closing monitor pages never changes persisted detection intent',async()=>{
  for(let i=0;i<2;i++){
    const f=fixture(),p=page(f);await f.mount();p.displayCameras.value=p.cameras.value.slice(0,2)
    await f.advance(6000);f.unmount()
    assert.deepEqual(f.writes,[]);assert.equal(f.jobs.size,0)
    assert(f.monitoringRows.every(row=>row.enabled))
  }
})
test('offline and faulty cameras can be selected and stopped without any preview connection',async()=>{
  const f=fixture(),p=page(f);await f.mount()
  for(const [index,status] of [[0,0],[1,2]]){
    const camera=p.cameras.value[index];camera.status=status;p.handleCameraSelect(camera)
    assert.equal(p.activeCamera.value.id,camera.id)
    await p.toggleMonitoring()
  }
  assert.deepEqual(f.writes,[[1,false],[2,false]])
  assert(f.monitoringRows.slice(2).every(row=>row.enabled));f.unmount()
})
test('grid changes and stream errors retain independent control of background detection',async()=>{
  const f=fixture(),p=page(f);await f.mount()
  p.displayCameras.value=p.cameras.value.slice();p.layout.value=1;p.updateDisplayCameras()
  assert.equal(p.displayCameras.value.length,1)
  p.handleWebSocketMessage({type:'camera_status',data:{cameraId:1,status:0}})
  assert.equal(p.displayCameras.value.length,1,'Keep an error tile available for retry')
  assert.deepEqual(f.writes,[]);f.unmount()
})
test('stale UTC samples and failed polls cannot keep a healthy RUNNING label',async()=>{
  let offline=false
  const f=fixture({modules:{'@/api/monitoring':{getMonitoring:async()=>{
    if(offline)throw Error('offline')
    return [{camera_id:1,enabled:true,state:'RUNNING',last_status_at:'2026-11-10T12:00:00.000',metrics:{lastFrameAt:'2026-11-10T12:00:00Z',lastInferenceAt:'2026-11-10T12:00:00Z'}}]
  }}}})
  const p=page(f);await f.mount();assert.equal(p.monitoring.label(1),'检测中')
  await f.advance(36000);assert.match(p.monitoring.label(1),/报告过期/)
  offline=true;await p.monitoring.refresh();assert.match(p.monitoring.label(1),/查询不可用/)
  assert.equal(p.monitoring.rows.value[1].enabled,true);f.unmount()
})
test('status polling is serialized and a late response cannot update an unmounted page',async()=>{
  let resolve,calls=0
  const f=fixture({modules:{'@/api/monitoring':{getMonitoring:()=>{calls++;return new Promise(done=>resolve=done)}}}})
  const p=page(f);await f.mount();await f.advance(8000);assert.equal(calls,1)
  f.unmount();resolve([{camera_id:1,enabled:true,state:'RUNNING'}]);await flush()
  assert.deepEqual(p.monitoring.rows.value,{})
})
test('camera management can stop a faulty device without opening its preview',async()=>{
  const f=fixture(),p=f.component('views/camera/index.vue',['changeMonitoring','monitoring'])
  f.cameraRows[0].status=2;await f.mount();await p.changeMonitoring(1)
  assert.deepEqual(f.writes,[[1,false]])
  assert(f.sent.every(message=>message.type!=='start_stream'));f.unmount()
})
