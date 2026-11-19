const test=require('node:test'),assert=require('node:assert/strict')
const {fixture,flush}=require('./frontend-fixture.cjs')
const note=(noticeId)=>({id:'7',noticeId:String(noticeId),kind:noticeId===1?'FIRST':'ONGOING',cameraId:'1',type:'工人',location:'test',eventTime:'2026-11-11T00:00:00'})

test('a persistent reminder has a new notification identity on the same alarm',async()=>{
  let items=[note(1)];const reads=[]
  const f=fixture({modules:{'@/api/alarmNotices':{getAlarmNotices:async()=>({unreadCount:items.length,items}),readNoticeIds:async ids=>{reads.push(ids);items=[]}}}})
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await flush()
  await inbox.markNotificationsRead(['1']);items=[note(2)];await f.advance(5000)
  assert.equal(inbox.state.changed,true);assert.equal(inbox.state.items[0].id,'7');assert.deepEqual(reads,[['1']]);inbox.stop()
})
test('detail acknowledgement uses the exact displayed notification IDs',async()=>{
  const reads=[]
  const f=fixture({modules:{
    '@/api/alarmNotices':{getAlarmNotices:async()=>({unreadCount:2,items:[note(1),note(2)]}),readNoticeIds:async ids=>reads.push(ids)},
    '@/api/Abnormal':{getAbnormalEventById:async()=>({id:7,cameraId:1,unreadNoticeIds:['2']})},
  }})
  const p=f.component('views/Abnormal/index.vue',['handleDetail','insight'])
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await f.mount();await p.handleDetail({id:7});await flush()
  assert.deepEqual(reads,[['2']]);inbox.stop();f.unmount()
})
test('stale risk observations are shown unknown while preserving the last recorded state',()=>{
  const f=fixture(),display=f.module('@/utils/riskDisplay')
  assert.equal(display.riskAt('PRESENT','RISK','2026-11-10T12:00:00Z',f.now()),'风险持续')
  assert.match(display.riskAt('PRESENT','RISK','2026-11-10T11:59:00Z',f.now()),/未知/)
  assert.match(display.riskAt('INTERRUPTED','RISK','2026-11-10T12:00:00Z',f.now()),/中断/)
  assert.equal(display.riskAt('CLEARED','OBSERVATION','2026-11-10T12:00:00Z',f.now()),'观察结束')
})
const rule=()=>({enabled:true,classes:[12],roi:[0,0,1,1],confidence:.5,dwellSeconds:2,graceSeconds:3,reminderSeconds:60,level:3,escalateSeconds:180,revision:0})
test('risk-rule form keeps malformed regions local and submits valid revision-fenced rules',async()=>{
  const writes=[],f=fixture({props:{modelValue:true,cameraId:1},modules:{'@/api/riskRules':{getRiskRule:async()=>rule(),saveRiskRule:async(id,value)=>writes.push([id,JSON.parse(JSON.stringify(value))])}}})
  const p=f.component('components/RiskRuleDialog/index.vue',['rule','save']);await f.mount()
  p.rule.value.roi=[.8,0,.2,1];await p.save();assert.equal(writes.length,0)
  p.rule.value.roi=[0,0,.5,1];await p.save();assert.equal(writes[0][0],1);assert.equal(writes[0][1].revision,0);f.unmount()
})
test('a late rule response cannot populate a closed dialog',async()=>{
  let resolve
  const f=fixture({props:{modelValue:true,cameraId:1},modules:{'@/api/riskRules':{getRiskRule:()=>new Promise(done=>resolve=done)}}})
  const p=f.component('components/RiskRuleDialog/index.vue',['rule']);f.unmount();resolve(rule());await flush()
  assert.equal(p.rule.value,undefined)
})
test('rule saves freeze the submitted value, suppress duplicates and ignore success after unmount',async()=>{
  const writes=[];let done
  const f=fixture({props:{modelValue:true,cameraId:1},modules:{'@/api/riskRules':{
    getRiskRule:async()=>rule(),saveRiskRule:(id,value)=>{writes.push([id,value]);return new Promise(resolve=>done=resolve)},
  }}})
  const p=f.component('components/RiskRuleDialog/index.vue',['rule','save']);await f.mount()
  const saving=p.save();p.rule.value.roi[2]=.5;await p.save()
  assert.equal(writes.length,1);assert.deepEqual(writes[0][1].roi,[0,0,1,1])
  f.unmount();done();await saving;assert.equal(f.messages.length,0)
})
test('selecting a template copies parameters but preserves the camera region and observation mode',async()=>{
  const values={classes:[7],confidence:.65,dwellSeconds:0,graceSeconds:3,reminderSeconds:60,level:3,escalateSeconds:60}
  const v={id:'rockfall',version:1,name:'落石',parameters:values}
  const f=fixture({props:{modelValue:true,cameraId:2},modules:{'@/api/riskRules':{
    getRiskRule:async()=>({...rule(),enabled:false,roi:[.1,.2,.5,.9]}),getTemplates:async()=>({versions:[v]})
  }}})
  const p=f.component('components/RiskRuleDialog/index.vue',['rule','choose'])
  await f.mount();p.choose('rockfall/1')
  assert.deepEqual(p.rule.value.roi,[.1,.2,.5,.9]);assert.equal(p.rule.value.enabled,false)
  assert.equal(p.rule.value.template.version,1);p.rule.value.classes.push(2);assert.deepEqual(values.classes,[7])
  p.choose('');assert.equal(p.rule.value.template,null);f.unmount()
})
test('pointer region selection normalizes reversed drags, clips edges and ignores cancelled gestures',async()=>{
  const model={value:[0,0,1,1]}
  const f=fixture({model,props:{camera:1},modules:{'@/api/detectionFrames':{getDetectionFrame:async()=>({state:'DISABLED'})}}})
  const p=f.component('components/RiskRuleDialog/RegionPicker.vue',['ready','start','move','finish','cancel'])
  await f.mount();p.ready.value=true
  const target={setPointerCapture(){},getBoundingClientRect:()=>({left:10,top:20,width:200,height:100})}
  const e=(x,y)=>({button:0,pointerId:1,clientX:x,clientY:y,currentTarget:target})
  p.start(e(160,95));p.move(e(30,30));p.finish(e(-10,30))
  assert.deepEqual(model.value,[0,.1,.75,.75])
  p.start(e(100,90));p.cancel(e(100,90));p.finish(e(180,110))
  assert.deepEqual(model.value,[0,.1,.75,.75]);f.unmount()
})
test('publishing a template only previews upgrades until the administrator selects cameras',async()=>{
  const calls=[],v={id:'rockfall',version:1,name:'落石',parameters:rule()}
  const rows=[1,2].map(cameraId=>({cameraId,revision:3,running:false}))
  const f=fixture({modules:{'@/api/riskRules':{getTemplates:async()=>({versions:[v],recommendation:{revision:0,template:null}}),
    publishTemplate:async()=>({...v,version:2}),templateImpact:async()=>rows,upgradeCameras:async(target,items)=>calls.push([target.version,items.map(x=>x.cameraId)])}}})
  const p=f.component('views/riskTemplates/index.vue',['edit','publish','reviewing','selected','applyUpgrade'])
  await f.mount();p.edit(v);await p.publish()
  assert.equal(p.reviewing.value,true);assert.deepEqual(calls,[])
  p.selected.value=[rows[1]];await p.applyUpgrade();assert.deepEqual(calls,[[2,[2]]]);f.unmount()
})

test('settings page edits the selected camera and ignores stale camera lists after pagination',async()=>{
  let resolveFirst
  const second={id:18,name:'东侧机位'}
  const f=fixture({props:{refreshKey:0},modules:{'@/api/camera':{
    getCameraList:({current})=>current===1 ? new Promise(resolve=>{resolveFirst=resolve}) : Promise.resolve({records:[second],total:11})
  }}})
  const panel=f.component('views/riskTemplates/CameraPolicies.vue',['page','cameras','edit','editing','cameraId','cameraName'])
  await f.mount()
  panel.page.value=2
  await flush()
  resolveFirst({records:[{id:2,name:'西侧机位'}],total:11});await flush()
  assert.deepEqual(panel.cameras.value,[second])
  panel.edit(panel.cameras.value[0])
  assert.equal(panel.editing.value,true)
  assert.equal(panel.cameraId.value,18)
  assert.equal(panel.cameraName.value,'东侧机位');f.unmount()
})
