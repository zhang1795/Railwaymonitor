const test=require('node:test'),assert=require('node:assert/strict')
const {fixture,flush}=require('./frontend-fixture.cjs')

test('preview authenticates before stream commands and renews through HTTP',async()=>{
  const calls=[],f=fixture({modules:{'@/api/request':{__esModule:true,default:{post:async(url,body)=>{calls.push({url,body});return {grant:'opaque-test-grant'}}}}}})
  const client=f.module('@/utils/websocket').default
  client.send({type:'start_stream',data:{cameraId:1}})
  const socket=f.sockets[0];socket.readyState=1;await socket.onopen()
  assert.equal(socket.url,'wss://test.example/stream/ws')
  assert.deepEqual(socket.sent,[{type:'authenticate',data:{grant:'opaque-test-grant'}}])
  assert.equal(client.isConnected(),false)
  socket.onmessage({data:JSON.stringify({type:'authenticated',data:{cameraId:0}})})
  assert.equal(client.isConnected(),true);assert.equal(socket.sent[1].type,'start_stream')
  await f.advance(60000);assert.equal(calls[1].url,'/preview/grant/renew')
  client.close();assert.equal(f.jobs.size,0)
})

test('offline status command queue is bounded and cancelled streams never reopen',()=>{
  const f=fixture(),client=f.module('@/utils/websocket').default
  for(let id=1;id<=64;id++)client.send({type:'check_camera',data:{cameraId:id}})
  assert.throws(()=>client.send({type:'check_camera',data:{cameraId:65}}),/队列已满/)
  client.close();const count=f.sockets.length
  client.send({type:'stop_stream',data:{cameraId:1}})
  assert.equal(f.sockets.length,count);assert.equal(f.jobs.size,0)
})

test('Vue render effects observe connection changes without unrelated renders',async()=>{
  const f=fixture(),client=f.module('@/utils/websocket').default,values=[]
  const runner=f.vue.effect(()=>values.push(client.isConnected()))
  client.connect();const socket=await f.authenticate()
  assert.equal(values[0],false);assert.equal(values.at(-1),true)
  socket.readyState=3;socket.onclose({wasClean:false})
  assert.equal(values.at(-1),false);client.close();f.vue.stop(runner)
})

test('reconnection restores only still-mounted previews and isolates a cancelled camera',async()=>{
  const f=fixture(),client=f.module('@/utils/websocket').default
  for(const cameraId of [1,2])client.send({type:'start_stream',data:{cameraId}})
  let socket=await f.authenticate();socket.readyState=3;socket.onclose({wasClean:false})
  client.send({type:'stop_stream',data:{cameraId:1}})
  await f.advance(3000);socket=await f.authenticate()
  assert.deepEqual(socket.sent.filter(row=>row.type==='start_stream').map(row=>row.data.cameraId),[2])
  client.close()
})

test('manual retry recovers after the five automatic reconnect attempts are exhausted',async()=>{
  const f=fixture(),client=f.module('@/utils/websocket').default
  client.send({type:'start_stream',data:{cameraId:1}})
  for(let attempt=0;attempt<6;attempt++){
    const socket=f.sockets.at(-1);socket.readyState=3;socket.onclose({wasClean:false})
    if(attempt<5)await f.advance(3000)
  }
  assert.equal(client.connectionState.value,'failed')
  client.retryStream(1);await f.authenticate()
  assert.equal(client.isConnected(),true)
  assert.equal(f.sockets.at(-1).sent.at(-1).type,'start_stream');client.close()
})

test('an old asynchronous grant cannot authenticate a replacement connection',async()=>{
  let finishOld,calls=0
  const f=fixture({modules:{'@/api/request':{__esModule:true,default:{post:()=>++calls===1?new Promise(resolve=>finishOld=resolve):Promise.resolve({grant:'new-grant'})}}}})
  const client=f.module('@/utils/websocket').default;client.connect()
  const old=f.sockets[0];old.readyState=1;const pending=old.onopen()
  client.retryStream(1);const current=f.sockets[1];await f.authenticate(current)
  finishOld({grant:'old-grant'});await pending
  assert.equal(old.sent.length,0)
  assert.equal(current.sent[0].data.grant,'new-grant');client.close()
})

test('stream retry waits for its own stop acknowledgement and leaves other streams running',async()=>{
  const f=fixture(),client=f.module('@/utils/websocket').default
  for(const cameraId of [1,2])client.send({type:'start_stream',data:{cameraId}})
  const socket=await f.authenticate();socket.sent=[]
  client.retryStream(1);assert.deepEqual(socket.sent,[{type:'stop_stream',data:{cameraId:1}}])
  socket.onmessage({data:JSON.stringify({type:'stream_stopped',data:{cameraId:1}})})
  assert.deepEqual(socket.sent,[{type:'stop_stream',data:{cameraId:1}},{type:'start_stream',data:{cameraId:1}}])
  client.close()
})

function player(f) {
  const p=f.component('components/VideoPlayer/index.vue',['canvas','handleMessage','fresh','lastFrameAt','isLoading','hasConnectionError','connectionErrorMessage','retryConnection'])
  const counts={drawn:0,cleared:0}
  p.canvas.value=f.vue.markRaw({width:640,height:480,getContext:()=>({fillRect(){counts.cleared++},clearRect(){counts.cleared++},drawImage(){counts.drawn++}})})
  return {p,counts}
}
function playerFixture(extras={}) {return fixture({...extras,props:{camera:{id:1,name:'test',status:1},isActive:true}})}
const frame={type:'video_frame',data:{cameraId:1,frame:'data:image/jpeg;base64,test-only'}}

test('a ready message without a decoded frame never claims the picture is live',async()=>{
  const f=playerFixture(),{p}=player(f);await f.mount();await f.authenticate()
  p.handleMessage({type:'stream_ready',data:{cameraId:1}})
  assert.equal(p.fresh.value,false)
  await f.advance(16000);assert.equal(p.hasConnectionError.value,true)
  f.unmount();f.module('@/utils/websocket').default.close()
})

test('missing frames expire the picture in five seconds, and a new frame recovers it',async()=>{
  const f=playerFixture(),{p,counts}=player(f);await f.mount();await f.authenticate()
  p.handleMessage(frame);assert.equal(p.fresh.value,true)
  const previous=counts.cleared
  await f.advance(6000);assert.equal(p.fresh.value,false)
  assert.match(p.connectionErrorMessage.value,/过期/);assert(counts.cleared>previous)
  p.handleMessage(frame);assert.equal(p.fresh.value,true)
  f.unmount();f.module('@/utils/websocket').default.close()
})

test('player retry creates a connection even when WebSocket is disconnected',async()=>{
  const f=playerFixture(),{p}=player(f);await f.mount();const socket=await f.authenticate()
  socket.readyState=3;socket.onclose({wasClean:false})
  const count=f.sockets.length;p.retryConnection()
  assert.equal(f.sockets.length,count+1)
  await f.authenticate();p.handleMessage(frame);assert.equal(p.fresh.value,true)
  assert.deepEqual(f.writes,[]);f.unmount();f.module('@/utils/websocket').default.close()
})

test('a late image decode cannot paint a removed player or overwrite a newer frame',async()=>{
  const f=playerFixture({autoDecode:false}),{p,counts}=player(f);await f.mount();await f.authenticate()
  p.handleMessage(frame);p.handleMessage(frame)
  f.images[1].onload();f.images[0].onload();assert.equal(counts.drawn,1)
  p.handleMessage(frame);f.unmount();f.images[2].onload();await flush()
  assert.equal(counts.drawn,1);f.module('@/utils/websocket').default.close()
})
