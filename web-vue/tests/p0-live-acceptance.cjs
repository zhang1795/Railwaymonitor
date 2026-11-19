// Opt-in socket/HTTP integration, not a browser rendering test.
const assert=require('node:assert/strict')
const fs=require('node:fs')
const WebSocket=require('ws')
const base=process.env.P0_HTTP_URL, socketUrl=process.env.P0_WS_URL
const password=process.env.P0_TEST_PASSWORD, camera=Number(process.env.P0_TEST_CAMERA_ID||1)
let phase='startup'
if(!base || !socketUrl || !password || new URL(base).port!=='18090' || new URL(socketUrl).port!=='15000')
  throw new Error('Use explicit isolated test HTTP/WS endpoints and credentials')
if(![base,socketUrl].every(url=>['127.0.0.1','localhost'].includes(new URL(url).hostname)))
  throw new Error('Only loopback test services are allowed')

async function wait(predicate,seconds=15){
  const end=Date.now()+seconds*1000
  while(Date.now()<end){const value=await predicate();if(value)return value;await new Promise(resolve=>setTimeout(resolve,100))}
  throw new Error('live acceptance condition timed out: '+phase)
}
function session(){
  let cookie=''
  async function api(path,method='GET',body){
    const headers={}
    if(method!=='GET'){
      const csrf=await api('/auth/csrf');headers[csrf.headerName]=csrf.token;headers['Content-Type']='application/json'
    }
    headers.Cookie=cookie
    const response=await fetch(base+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)})
    const next=response.headers.get('set-cookie');if(next)cookie=next.split(';')[0]
    const result=await response.json();assert.equal(response.status,200,result.msg);assert.equal(result.code,200,result.msg)
    return result.data
  }
  return {api,async login(){await api('/user/login','POST',{username:'admin',password})},get cookie(){return cookie}}
}
class Viewer {
  constructor(grant){
    this.frames=0;this.stopped=0;this.error=null
    this.ws=new WebSocket(socketUrl,{origin:'http://127.0.0.1:3000'})
    this.ws.on('error',error=>{this.error=error})
    this.ws.on('open',()=>this.ws.send(JSON.stringify({type:'authenticate',data:{grant}})))
    this.ws.on('message',raw=>{
      try{
        const message=JSON.parse(raw)
        if(message.type==='authenticated')this.start()
        if(message.type==='stream_stopped')this.stopped++
        if(message.type==='video_frame'){
          const frame=Buffer.from(message.data.frame.split(',')[1],'base64')
          assert.equal(frame[0],255);assert.equal(frame[1],216);this.frames++
        }
      }catch(error){this.error=error}
    })
  }
  send(type,data){this.ws.send(JSON.stringify({type,data}))}
  start(){this.send('start_stream',{cameraId:camera,rtspUrl:'rtsp://untrusted.invalid/injected'})}
  close(){this.ws.close()}
  async until(predicate,seconds=15){return wait(()=>{if(this.error)throw this.error;return predicate()},seconds)}
}
async function rejectedSocket(origin,firstMessage){
  const ws=new WebSocket(socketUrl,{origin});let frames=0
  try{
    phase='production clients first frames'
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('unauthorized preview was not closed')),7000)
      ws.on('open',()=>ws.send(JSON.stringify(firstMessage)))
      ws.on('message',()=>frames++)
      ws.on('error',()=>{})
      ws.on('close',()=>{clearTimeout(timer);resolve()})
    })
    assert.equal(frames,0)
  }finally{ws.close()}
}
async function productionClients(a,b){
  const ts=require('typescript'),vue=require('vue'),path=require('node:path')
  const source=fs.readFileSync(path.resolve(__dirname,'../src/utils/websocket.ts'),'utf8').replace(/import\.meta\.env/g,'testEnv')
  const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText
  const sockets=[]
  class BrowserSocket extends WebSocket {
    constructor(url){super(url,{origin:'http://127.0.0.1:3000'});this.on('error',()=>{});sockets.push(this)}
  }
  function client(session){
    const exports={}
    new Function('exports','require','window','WebSocket','testEnv',output)(exports,name=>{
      if(name==='vue')return vue
      assert.equal(name,'@/api/request');return {__esModule:true,default:{post:(path,data)=>session.api(path,'POST',data)}}
    },{location:{protocol:'http:',host:'127.0.0.1:3000'}},BrowserSocket,{VITE_ALGO_WS_URL:socketUrl})
    return exports.default
  }
  const first=client(a),second=client(b);let af=0,bf=0
  const frame=message=>{
    if(message.type!=='video_frame')return false
    const jpeg=Buffer.from(message.data.frame.split(',')[1],'base64');assert.equal(jpeg[0],255);assert.equal(jpeg[1],216);return true
  }
  first.addMessageHandler(message=>{if(frame(message))af++})
  second.addMessageHandler(message=>{if(frame(message))bf++})
  try{
    first.send({type:'start_stream',data:{cameraId:camera}})
    second.send({type:'start_stream',data:{cameraId:camera}})
    await wait(()=>af>=2 && bf>=2)
    phase='production client reconnect';const before=af;sockets[0].terminate()
    await wait(()=>!first.isConnected());await wait(()=>af>=before+2,15)
    phase='production client isolation';first.close();const remaining=bf;await wait(()=>bf>=remaining+2)
    phase='production client retry';second.retryStream(camera);const retry=bf;await wait(()=>bf>=retry+2,15)
    const unread=await b.api('/alarm-notices');assert(unread.unreadCount>0)
    phase='screenshot evidence';const photos=await wait(async()=>{
      for(const item of unread.items){const insight=await b.api('/Abnormal-event/'+item.id+'/insight');const image=insight.evidence.images.find(row=>row.state==='READY');if(image)return image}
      return null
    },15)
    const picture=await fetch(new URL(photos.url,base),{headers:{Cookie:b.cookie}});assert.equal(picture.status,200)
    const pictureBytes=Buffer.from(await picture.arrayBuffer());assert.equal(require('node:crypto').createHash('sha256').update(pictureBytes).digest('hex'),photos.sha256)
    const anonymous=await fetch(new URL(photos.url,base));assert.equal(anonymous.status,401)
    if(process.env.P0_RESULT_FILE)fs.writeFileSync(require('node:path').join(require('node:path').dirname(process.env.P0_RESULT_FILE),'evidence-sample.jpg'),pictureBytes)

    const id=unread.items[0].id,prior=await b.api('/Abnormal-event/'+id)
    await a.api('/alarm-notices/read','POST',{ids:[id]})
    const current=await b.api('/Abnormal-event/'+id);assert.equal(current.status,prior.status)
    const page=await b.api('/Abnormal-event/page?unreadOnly=true&size=100')
    assert(!page.records.some(row=>String(row.id)===id))
    assert((await b.api('/monitoring')).find(row=>row.camera_id===camera).enabled)
    return {productionClientReconnect:true,productionClientRetry:true,productionClientsIsolated:true,authenticatedScreenshotRead:true,anonymousScreenshotDenied:true,screenshotChecksumVerified:true,realUnreadReceipts:true,readingDoesNotResolve:true}
  }finally{first.close();second.close()}
}
async function main(){
  const a=session(),b=session();let va,vb
  try{
    await a.login();await b.login();assert.notEqual(a.cookie,b.cookie)
    const users=await a.api('/user/page');assert(!JSON.stringify(users).includes('"password":'))
    const ga=await a.api('/preview/grant','POST',{}),gb=await b.api('/preview/grant','POST',{})
    await rejectedSocket('http://attacker.invalid',{type:'authenticate',data:{grant:ga.grant}})
    await rejectedSocket('http://127.0.0.1:3000',{type:'start_stream',data:{cameraId:camera}})
    const frontend=await productionClients(a,b)
    phase='two raw viewers';va=new Viewer(ga.grant);vb=new Viewer(gb.grant)
    await Promise.all([va.until(()=>va.frames>=2),vb.until(()=>vb.frames>=2)])
    va.close();await a.api('/user/logout','POST',{})
    phase='raw viewer isolation';const beforeClose=vb.frames;await vb.until(()=>vb.frames>=beforeClose+3)
    const stopped=vb.stopped;vb.send('stop_stream',{cameraId:camera});await vb.until(()=>vb.stopped>stopped)
    const task=(await b.api('/monitoring')).find(row=>row.camera_id===camera)
    assert(task.enabled);assert.equal(task.state,'RUNNING')
    phase='background inference progress';const records=await wait(async()=>{const page=await b.api('/Abnormal-event/page?cameraId='+camera+'&size=100');return page.records.some(row=>row.detectionState==='ACTIVE')&&page.records},10)
    const latestTime=Math.max(...records.map(row=>Date.parse(row.lastSeen)||0))
    await wait(async()=>{const page=await b.api('/Abnormal-event/page?cameraId='+camera+'&size=100');return page.records.some(row=>Date.parse(row.lastSeen)>latestTime)},10)
    const beforeRestart=vb.frames;vb.start();await vb.until(()=>vb.frames>=beforeRestart+2)
    const beforeLogout=vb.stopped;await b.api('/user/logout','POST',{})
    await vb.until(()=>vb.stopped>beforeLogout,20)
    const result={twoAuthenticatedSessions:true,twoViewersReceiveJpeg:true,closingOneKeepsOther:true,
      stoppingPreviewKeepsDetection:true,detectionAdvancesWithoutPreview:true,clientSourceUrlIgnored:true,
      logoutStopsPreview:true,badOriginDenied:true,unauthenticatedPreviewDenied:true,frameCounts:{a:va.frames,b:vb.frames},...frontend}
    if(process.env.P0_RESULT_FILE)fs.writeFileSync(process.env.P0_RESULT_FILE,JSON.stringify(result,null,2))
    console.log(JSON.stringify(result))
  }finally{
    va?.close();vb?.close()
    await Promise.allSettled([a.api('/user/logout','POST',{}),b.api('/user/logout','POST',{})])
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1})
