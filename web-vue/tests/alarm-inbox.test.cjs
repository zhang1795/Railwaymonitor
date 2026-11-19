const test=require('node:test'),assert=require('node:assert/strict')
const {fixture,flush}=require('./frontend-fixture.cjs')
const notice=id=>({id:String(id),cameraId:'1',type:'工人',location:'test',eventTime:'2026-11-10T20:00:00'})

test('unread alerts are visible on first login and a later lower ID is detected too',async()=>{
  let rows=[notice(3)],calls=0
  const f=fixture({modules:{'@/api/alarmNotices':{getAlarmNotices:async()=>{calls++;return {unreadCount:rows.length,items:rows}}}}})
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await flush()
  assert.equal(inbox.state.unreadCount,1)
  rows=[notice(3),notice(2)];await f.advance(5000)
  assert.equal(inbox.state.unreadCount,2);assert.equal(inbox.state.changed,true)
  assert.equal(calls,2);assert.deepEqual(f.writes,[]);inbox.stop();assert.equal(f.jobs.size,0)
})
test('disconnection marks the count unknown and reconnect polling recovers all server unread items',async()=>{
  let offline=false,rows=[notice(1)]
  const f=fixture({modules:{'@/api/alarmNotices':{getAlarmNotices:async()=>{if(offline)throw Error('offline');return {unreadCount:rows.length,items:rows}}}}})
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await flush()
  offline=true;await f.advance(5000);assert.equal(inbox.state.healthy,false);assert.equal(inbox.state.unreadCount,1)
  rows=[notice(5),notice(4),notice(3),notice(2),notice(1)];offline=false
  await f.advance(5000);assert.equal(inbox.state.healthy,true);assert.equal(inbox.state.unreadCount,5);inbox.stop()
})
test('read acknowledges explicit displayed IDs without consuming an arrival during the request',async()=>{
  let rows=[notice(3),notice(2)],acked
  const f=fixture({modules:{'@/api/alarmNotices':{
    getAlarmNotices:async()=>({unreadCount:rows.length,items:rows}),
    readAlarmNotices:async ids=>{acked=ids;rows=[notice(4)]},
  }}})
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await flush()
  await inbox.markRead(inbox.state.items.map(row=>row.id))
  assert.deepEqual(acked,['3','2']);assert.equal(inbox.state.unreadCount,1)
  assert.equal(inbox.state.items[0].id,'4');inbox.stop()
})
test('a failed read request does not optimistically erase unread alerts',async()=>{
  const f=fixture({modules:{'@/api/alarmNotices':{
    getAlarmNotices:async()=>({unreadCount:1,items:[notice(1)]}),readAlarmNotices:async()=>{throw Error('offline')},
  }}})
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await flush()
  await assert.rejects(inbox.markRead(['1']),/offline/)
  assert.equal(inbox.state.unreadCount,1);inbox.stop()
})
test('slow polling is serialized, expires, and responses from a previous login cannot leak',async()=>{
  const resolves=[]
  const f=fixture({modules:{'@/api/alarmNotices':{getAlarmNotices:()=>new Promise(resolve=>resolves.push(resolve))}}})
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await f.advance(16000)
  assert.equal(resolves.length,1);assert.equal(inbox.state.healthy,false)
  inbox.stop();inbox.start();resolves[1]({unreadCount:2,items:[notice(2)]});await flush()
  resolves[0]({unreadCount:99,items:[notice(99)]});await flush()
  assert.equal(inbox.state.unreadCount,2);assert.equal(inbox.state.items[0].id,'2');inbox.stop()
})
test('notification polling preserves an open edit draft and does not replace the event table',async()=>{
  let count=1,listCalls=0
  const row={id:1,cameraId:1,description:'original',status:0}
  const f=fixture({modules:{
    '@/api/alarmNotices':{getAlarmNotices:async()=>({unreadCount:count,items:[notice(count)]})},
    '@/api/Abnormal':{getAbnormalEventList:async()=>{listCalls++;return {records:[row],total:1}}},
  }})
  const p=f.component('views/Abnormal/index.vue',['handleEdit','editForm','list'])
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await f.mount()
  p.handleEdit(row);p.editForm.description='unsaved operator draft';count=2
  await f.advance(6000)
  assert.equal(inbox.state.unreadCount,2);assert.equal(p.editForm.description,'unsaved operator draft')
  assert.equal(listCalls,1);assert.equal(p.list.value.length,1)
  inbox.stop();f.unmount()
})
test('a notice link opens the exact event and acknowledges only that successful detail',async()=>{
  const opened=[],reads=[]
  const f=fixture({modules:{
    '@/api/alarmNotices':{getAlarmNotices:async()=>({unreadCount:1,items:[notice(3)]}),readAlarmNotices:async ids=>reads.push(ids)},
    '@/api/Abnormal':{getAbnormalEventList:async()=>({records:[],total:0}),getAbnormalEventById:async id=>{opened.push(id);return {id:Number(id),cameraId:1}}},
  }})
  f.route.query.noticeId='3'
  const p=f.component('views/Abnormal/index.vue',['detail','detailVisible'])
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await f.mount();await flush()
  assert.deepEqual(opened,['3']);assert.deepEqual(reads,[['3']])
  assert.equal(p.detail.value.id,3);assert.equal(p.detailVisible.value,true)
  inbox.stop();f.unmount()
})
test('late detail responses after navigation never mark an event read',async()=>{
  let resolve;const reads=[]
  const f=fixture({modules:{
    '@/api/alarmNotices':{getAlarmNotices:async()=>({unreadCount:1,items:[notice(3)]}),readAlarmNotices:async ids=>reads.push(ids)},
    '@/api/Abnormal':{getAbnormalEventList:async()=>({records:[],total:0}),getAbnormalEventById:()=>new Promise(done=>resolve=done)},
  }})
  const p=f.component('views/Abnormal/index.vue',['handleDetail'])
  const inbox=f.module('@/stores/alarmInbox').alarmInbox;inbox.start();await f.mount()
  const request=p.handleDetail({id:3});f.unmount();resolve({id:3,cameraId:1});await request
  assert.deepEqual(reads,[]);inbox.stop()
})
