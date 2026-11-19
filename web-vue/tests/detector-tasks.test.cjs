const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const filename = path.resolve(__dirname, '../src/utils/detectorTasks.ts')
const output = ts.transpileModule(fs.readFileSync(filename,'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const compiled = { exports: {} }
// Compile the dependency without resetting node:test's current file context.
new Function('exports', output)(compiled.exports)
const { DetectorTasks } = compiled.exports

function fixture() {
  const messages = [], statuses = [], handlers = new Map()
  const transport = {
    publish: (topic, body, qos) => messages.push({topic,body,qos}),
    subscribe: () => {},
    registerHandler: (topic,handler) => handlers.set(topic,handler),
    removeHandler: topic => handlers.delete(topic),
  }
  const tasks = new DetectorTasks(transport, s => statuses.push(s), 'page-a', undefined, undefined, false)
  const camera = {videoId:'1',videoUrl:'rtsp://test',deviceName:'test'}
  return {tasks,camera,messages,statuses,handlers}
}
function ack(f, state='RUNNING', changes={}) {
  f.tasks.receive({videoId:'1',clientId:'page-a',requestId:f.messages[0].body.requestId,
                   sessionId:'session-a',revision:2,state,...changes})
}
test('start is idempotent and uses timezone-aware v2 control', () => {
  const f=fixture();f.tasks.start(f.camera);f.tasks.start(f.camera)
  assert.equal(f.messages.length,1)
  assert.equal(f.messages[0].body.protocolVersion,2)
  assert.match(f.messages[0].body.startTime,/Z$/)
  assert.equal(f.messages[0].qos,1)
  f.tasks.dispose()
})
test('unacknowledged start retries; running lease sends heartbeat', () => {
  const f=fixture();f.tasks.start(f.camera);f.tasks.tick()
  assert.equal(f.messages[0].body.requestId,f.messages[1].body.requestId)
  ack(f);f.tasks.tick()
  assert.equal(f.messages.at(-1).body.action,'heartbeat')
  assert.equal(f.messages.at(-1).body.sessionId,'session-a')
  f.tasks.dispose()
})
test('out of order and foreign client status do not regress state', () => {
  const f=fixture();f.tasks.start(f.camera);ack(f)
  ack(f) // Replayed status must not repeat UI effects.
  ack(f,'STARTING',{revision:1})
  ack(f,'FAILED',{clientId:'another-page',revision:3})
  assert.deepEqual(f.statuses.map(s=>s.state),['RUNNING'])
  f.tasks.dispose()
})
test('stop before start acknowledgement releases the late session', () => {
  const f=fixture();f.tasks.start(f.camera);f.tasks.stop('1');ack(f)
  assert.equal(f.messages.at(-1).body.action,'stop')
  assert.equal(f.messages.at(-1).body.sessionId,'session-a')
  assert.equal(f.statuses.at(-1).state,'STOPPING')
  const before=f.messages.length;f.tasks.tick();assert.equal(f.messages.length,before)
  f.tasks.dispose()
})
test('rapid stop and restart ignores terminal messages from the old session', () => {
  const f=fixture();f.tasks.start(f.camera);ack(f);f.tasks.stop('1');f.tasks.start(f.camera)
  const requestId=f.messages.at(-1).body.requestId
  f.tasks.receive({videoId:'1',sessionId:'session-a',state:'STOPPED',revision:9})
  f.tasks.receive({videoId:'1',sessionId:'session-b',clientId:'page-a',requestId,state:'RUNNING',revision:2})
  f.tasks.receive({videoId:'1',sessionId:'session-a',state:'STOPPED',revision:10})
  assert.equal(f.statuses.at(-1).sessionId,'session-b')
  f.tasks.dispose()
})
test('backend restart or expired lease starts a fresh session', () => {
  const f=fixture();f.tasks.start(f.camera);ack(f)
  f.tasks.receive({videoId:'1',sessionId:'session-a',state:'STOPPED',action:'heartbeat',revision:3})
  f.tasks.tick();assert.equal(f.messages.at(-1).body.action,'start')
  assert.notEqual(f.messages.at(-1).body.requestId,f.messages[0].body.requestId)
  f.tasks.dispose()
})
test('failure stops automatic retries; explicit retry gets new request', () => {
  const f=fixture();f.tasks.start(f.camera);ack(f,'FAILED')
  const before=f.messages.length;f.tasks.tick();assert.equal(f.messages.length,before)
  f.tasks.start(f.camera);assert.notEqual(f.messages.at(-1).body.requestId,f.messages[0].body.requestId)
  f.tasks.dispose()
})
test('dispose releases all held cameras and removes handler', () => {
  const f=fixture();f.tasks.start(f.camera);f.tasks.start({...f.camera,videoId:'2'})
  f.tasks.dispose()
  assert.deepEqual(f.messages.filter(m=>m.body.action==='stop').map(m=>m.body.videoId),['1','2'])
  assert.equal(f.handlers.size,0)
})
test('fast failure delivered before STARTING ack cannot be overwritten', () => {
  const f=fixture();f.tasks.start(f.camera)
  ack(f,'FAILED',{revision:3})
  ack(f,'STARTING',{revision:1})
  assert.equal(f.statuses.at(-1).state,'FAILED')
  const before=f.messages.length;f.tasks.tick();assert.equal(f.messages.length,before)
  f.tasks.dispose()
})
function mqttFixture() {
  const callbacks = new Map(), subscriptions = []
  let connects=0
  const client={connected:false,
    on:(name,cb)=>callbacks.set(name,cb),
    subscribe:(topic,opts,cb)=>{subscriptions.push([topic,opts.qos]);if(cb)cb(null)},
    end:()=>{client.connected=false},
  }
  const fake={__esModule:true,default:{connect:()=>{connects++;return client}}}
  const source=fs.readFileSync(path.resolve(__dirname,'../src/utils/mqttClient.ts'),'utf8')
    .replace(/import\.meta\.env/g, 'testEnv')
  const code=ts.transpileModule(source,{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true},
  }).outputText
  const result={}
  new Function('exports','require','window','console','testEnv',code)(result,
    name=>{assert.equal(name,'mqtt');return fake},
    {location:{protocol:'http:',hostname:'test'}},{log(){},warn(){},error(){}},{})
  return {api:result.default,client,callbacks,subscriptions,connects:()=>connects}
}
test('MQTT preserves subscriptions across initial connect and reconnect', () => {
  const f=mqttFixture()
  f.api.subscribe('status',1)
  f.api.connect('test',8083)
  f.client.connected=true;f.callbacks.get('connect')()
  assert.deepEqual(f.subscriptions,[['status',1]])
  f.client.connected=false;f.api.connect('test',8083)
  assert.equal(f.connects(),1)
  f.client.connected=true;f.callbacks.get('connect')()
  assert.equal(f.subscriptions.length,2)
})
test('MQTT status messages do not require detection result fields', () => {
  const f=mqttFixture();let received
  f.api.registerHandler('status',value=>received=value)
  f.api.connect('test',8083)
  const status={videoId:'1',state:'RUNNING',revision:2}
  f.callbacks.get('message')('status',Buffer.from(JSON.stringify(status)),{})
  assert.deepEqual(received,status)
})
