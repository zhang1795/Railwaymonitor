// Opt-in: real HTTP session/CSRF, Flask WebSocket, RTSP frames and revocation.
// Only use against an isolated test deployment with a synthetic/test camera.
const assert = require('node:assert/strict')
const WebSocket = require('ws')
const base = process.env.P0_HTTP_URL
const socketUrl = process.env.P0_WS_URL
if (!base || !socketUrl || !process.env.P0_TEST_PASSWORD) throw new Error('isolated test URLs and password required')
let cookie = ''
async function http(path, method='GET', body, token) {
  const headers={Cookie:cookie}
  if (body) headers['Content-Type']='application/json'
  if (token) headers[token.headerName]=token.token
  const result = await fetch(base+path,{method,headers,body:body?JSON.stringify(body):undefined})
  const set=result.headers.get('set-cookie')
  if (set) cookie=set.split(';')[0]
  assert.equal(result.status,200,await result.clone().text())
  const json=await result.json();assert.equal(json.code,200);return json.data
}
async function csrf(){return http('/auth/csrf')}
async function main() {
  await http('/user/login','POST',{username:'admin',password:process.env.P0_TEST_PASSWORD},await csrf())
  const users=await http('/user/page')
  assert(!JSON.stringify(users).includes('"password":'))
  const {grant}=await http('/preview/grant','POST',{},await csrf())
  const ws=new WebSocket(socketUrl,{origin:'http://127.0.0.1:3000'})
  let logout=false,frameCount=0
  const finished=new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(new Error('preview/revocation timed out')),25000)
    let resolved=false
    ws.on('error',reject)
    ws.on('close',(code,reason)=>{if(!resolved){clearTimeout(timeout);reject(new Error('preview closed before verification: '+code+' '+reason.toString()))}})
    ws.on('open',()=>ws.send(JSON.stringify({type:'authenticate',data:{grant}})))
    ws.on('message',async raw=>{
      try {
        const message=JSON.parse(raw.toString())
        if (message.type==='authenticated') ws.send(JSON.stringify({type:'start_stream',data:{cameraId:1,rtspUrl:'rtsp://untrusted.invalid/injected'}}))
        if (message.type==='video_frame') {
          const bytes=Buffer.from(message.data.frame.split(',')[1],'base64')
          assert.equal(bytes[0],255);assert.equal(bytes[1],216);frameCount++
          if (!logout) {logout=true;await http('/user/logout','POST',{},await csrf())}
        }
        if (message.type==='stream_stopped' && logout) {resolved=true;clearTimeout(timeout);resolve()}
      } catch(error) {clearTimeout(timeout);reject(error)}
    })
  })
  try {await finished;assert(frameCount>0)} finally {ws.close()}
  console.log(JSON.stringify({httpSession:true,csrf:true,realJpegFrames:true,clientSourceUrlIgnored:true,logoutRevokedStream:true,frameCount},null,2))
}
main().catch(error=>{console.error(error);process.exitCode=1})
