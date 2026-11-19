// Opt-in real Chromium QA against disposable 13000/18090 services only.
import fs from 'node:fs'
import path from 'node:path'
import {spawn} from 'node:child_process'
import assert from 'node:assert/strict'

const folder=process.env.P0_BROWSER_DIRECTORY,password=process.env.P0_TEST_PASSWORD
assert(folder?.includes('/workspace/runtime/p0-reaudit/') && password)
const profile=fs.mkdtempSync(path.join(folder,'browser-profile-')),log=fs.openSync(path.join(folder,'browser-chrome.log'),'a')
const browser=spawn('/opt/google/chrome/chrome',['--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--autoplay-policy=no-user-gesture-required','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore',log,log],detached:true})
let socket,stage='browser startup',serial=0;const pending=new Map(),errors=[]
const pause=ms=>new Promise(done=>setTimeout(done,ms))
async function until(fn,seconds=20){const deadline=Date.now()+seconds*1000;while(Date.now()<deadline){const result=await fn();if(result)return result;await pause(100)}throw Error('browser QA timed out: '+stage)}
async function cdp(method,params={}){const id=++serial;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const result=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(result.exceptionDetails)throw Error('browser expression failed: '+stage);return result.result?.value}
async function shot(name){const result=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(folder,name),Buffer.from(result.data,'base64'))}
async function run(){
 const port=await until(()=>{try{return Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0])}catch{return 0}})
 const pages=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();socket=new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl)
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
 socket.addEventListener('message',event=>{const value=JSON.parse(event.data);if(value.id){const promise=pending.get(value.id);pending.delete(value.id);if(value.error)promise?.reject(Error(value.error.message));else promise?.resolve(value.result)}else if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails.text)})
 await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false})
 await cdp('Page.navigate',{url:'http://127.0.0.1:13000/login'});await until(()=>evaluate('document.readyState==="complete" && !!document.querySelector("input")'))
 stage='isolated browser login'
 const logged=await evaluate(`(async()=>{const csrf=(await (await fetch('/api/auth/csrf')).json()).data;const response=await fetch('/api/user/login',{method:'POST',headers:{'Content-Type':'application/json',[csrf.headerName]:csrf.token},body:JSON.stringify({username:'admin',password:${JSON.stringify(password)}})});return (await response.json()).code===200})()`);assert(logged)
 await cdp('Page.navigate',{url:'http://127.0.0.1:13000/monitor'});await until(()=>evaluate('!!document.querySelector(".camera-item")'))
 await evaluate('document.querySelector(".camera-item").click()')
 stage='same-frame live detection'
 await until(()=>evaluate('!!document.querySelector(".detection-view .result-picture img") && document.querySelectorAll(".detection-view .targets span").length>0'))
 await evaluate('document.querySelectorAll(".toolbar .el-radio-group")[1].querySelector(".el-radio-button").click()');await pause(300)
 assert(await evaluate('document.querySelector(".detection-view").textContent.includes("解码检查通过")'))
 const liveRects=await evaluate('document.querySelectorAll(".detection-view .detection-overlay rect").length');assert(liveRects>0)
 await shot('browser-live-detection.png')
 await cdp('Emulation.setDeviceMetricsOverride',{width:768,height:1024,deviceScaleFactor:1,mobile:false});await pause(300);await shot('browser-live-768.png')
 const horizontalOverflow=await evaluate('Math.max(0,document.documentElement.scrollWidth-window.innerWidth)')
 await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false})
 stage='historical sample selection'
 await cdp('Page.navigate',{url:'http://127.0.0.1:13000/recordings'});await until(()=>evaluate('!!document.querySelector(".filters .el-select__wrapper")'))
 await evaluate('document.querySelector(".filters .el-select__wrapper").click()');await until(()=>evaluate('Array.from(document.querySelectorAll(".el-select-dropdown__item")).some(item=>item.textContent.includes("isolated acceptance"))'))
 await evaluate('Array.from(document.querySelectorAll(".el-select-dropdown__item")).find(item=>item.textContent.includes("isolated acceptance")).click()');await pause(100)
 await evaluate('document.querySelector(".filters .el-button--primary").click()')
 await until(()=>evaluate('Array.from(document.querySelectorAll(".el-table__row")).some(row=>row.textContent.includes("检测采样回放"))'))
 await evaluate('Array.from(document.querySelectorAll(".el-table__row")).find(row=>row.textContent.includes("检测采样回放")).querySelector("button").click()')
 await until(()=>evaluate('!!document.querySelector(".recording-player video")'))
 await evaluate('(async()=>{const video=document.querySelector(".recording-player video");await video.play()})()')
 stage='VFR seek and actual presented frame overlays'
 await until(()=>evaluate('document.querySelector(".recording-player").textContent.includes("推理帧")'))
 const target=await evaluate(`(async()=>{const page=(await (await fetch('/api/camera/1/recordings')).json()).data;const clip=page.items.find(item=>item.kind==='DETECTION_SAMPLES');const manifest=(await (await fetch(clip.analysisUrl)).json()).data;const sample=manifest.frames[Math.floor(manifest.frames.length/2)];const video=document.querySelector('.recording-player video');video.pause();video.currentTime=sample.offsetMs/1000;return {frameSeq:sample.frameSeq,objects:sample.objects.length,offsetMs:sample.offsetMs}})()`)
 await until(()=>evaluate(`document.querySelector('.recording-player').textContent.includes('推理帧 ${target.frameSeq} ·')`))
 assert.equal(await evaluate('document.querySelectorAll(".recording-player .detection-overlay rect").length'),target.objects)
 await shot('browser-sample-playback.png')
 await evaluate('Array.from(document.querySelectorAll(".recording-player .el-checkbox")).find(item=>item.textContent.includes("目标框")).click()');await pause(100)
 assert.equal(await evaluate('document.querySelectorAll(".recording-player .detection-overlay rect").length'),0)
 await evaluate('Array.from(document.querySelectorAll(".recording-player .el-checkbox")).find(item=>item.textContent.includes("目标框")).click()');await pause(100)
 assert.equal(await evaluate('document.querySelectorAll(".recording-player .detection-overlay rect").length'),target.objects)
 const result={realChromium:true,isolatedServices:true,liveFrameAndTargetsVisible:true,liveBoxes:liveRects,actualVideoFrameCallback:true,seekFrameSeq:target.frameSeq,seekOffsetMs:target.offsetMs,seekOverlayCount:target.objects,overlayToggle:true,horizontalOverflow768:horizontalOverflow,uncaughtExceptions:errors.length}
 fs.writeFileSync(path.join(folder,'browser-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result))
}
try{await Promise.race([run(),new Promise((_,reject)=>setTimeout(()=>reject(Error('browser QA total timeout: '+stage)),65000).unref())])}
catch(error){try{await shot('browser-failure.png');fs.writeFileSync(path.join(folder,'browser-failure-state.txt'),stage+'\n'+await evaluate('document.body.innerText'))}catch{}throw error}
finally{socket?.close();try{process.kill(-browser.pid,'SIGTERM')}catch{}fs.closeSync(log)}
