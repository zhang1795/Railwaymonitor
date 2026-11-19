const test=require('node:test'),assert=require('node:assert/strict')
const {fixture,flush}=require('./frontend-fixture.cjs')
const object={bbox:[.1,.1,.5,.5],classId:12,className:'worker',label:'工人',confidence:.7,trackId:'7'}
function manifest(){return {sessionId:'a'.repeat(32),modelSha256:'f'.repeat(64),durationMs:2750,frames:[0,750,2250].map((offsetMs,index)=>({offsetMs,frameSeq:index+1,objects:index===1?[]:[object]}))}}
function frame(sequence=1){return {cameraId:'1',sessionId:'a'.repeat(32),frameSeq:sequence,width:8,height:8,jpeg:'test',objects:[],trails:[],observedAt:'2026-11-10T12:00:00Z',processedAt:'2026-11-10T12:00:00Z',modelSha256:'f'.repeat(64)}}

test('sample playback chooses the presented media timestamp including seeks and empty frames',()=>{
 const f=fixture(),{sampleIndex,sampleTrails}=f.module('@/utils/frameResults'),value=manifest()
 assert.equal(sampleIndex(value,0),0);assert.equal(sampleIndex(value,.75),1);assert.equal(sampleIndex(value,2.25),2)
 assert.equal(sampleIndex(value,.4),0);assert.equal(sampleIndex(value,2.75),-1);assert.equal(sampleIndex(value,NaN),-1)
 assert.deepEqual(sampleTrails(value,1),[]);assert.equal(sampleTrails(value,2)[0].points.length,2);f.unmount()
})
test('live results distinguish fresh empty observations from expiry and clear old targets',async()=>{
 let value={state:'FRESH',observedAgeMs:1000,frame:frame()}
 const f=fixture({props:{camera:{id:1,name:'test'}},modules:{'@/api/detectionFrames':{getDetectionFrame:async()=>value}}})
 const p=f.component('components/DetectionView/index.vue',['displayed','state']);await f.mount()
 assert.equal(p.state.value,'FRESH');assert.equal(p.displayed.value.objects.length,0)
 value={state:'EXPIRED'};await f.advance(500);assert.equal(p.state.value,'EXPIRED');assert.equal(p.displayed.value,undefined);f.unmount();assert.equal(f.jobs.size,0)
})
test('live image decoding never installs an obsolete camera frame after departure',async()=>{
 const f=fixture({autoDecode:false,props:{camera:{id:1}},modules:{'@/api/detectionFrames':{getDetectionFrame:async()=>({state:'FRESH',frame:frame()})}}})
 const p=f.component('components/DetectionView/index.vue',['displayed']);await f.mount();assert.equal(p.displayed.value,undefined)
 const image=f.images[0];f.unmount();image.onload();assert.equal(p.displayed.value,undefined)
})
test('live view watchdog expires a picture even while its next request hangs',async()=>{
 let stalled=false
 const f=fixture({props:{camera:{id:1}},modules:{'@/api/detectionFrames':{getDetectionFrame:()=>stalled?new Promise(()=>{}):Promise.resolve({state:'FRESH',frame:frame(),observedAgeMs:1000})}}})
 const p=f.component('components/DetectionView/index.vue',['displayed','state']);await f.mount();stalled=true
 await f.advance(4500);assert.equal(p.state.value,'EXPIRED');assert.equal(p.displayed.value,undefined);f.unmount()
})
test('recording overlays follow video frame callbacks and clean up when closed',async()=>{
 const value=manifest(),f=fixture({props:{clip:{id:'clip',kind:'DETECTION_SAMPLES',analysisUrl:'/api/camera/1/recordings/clip/analysis'}},modules:{'@/api/detectionFrames':{getAnalysis:async()=>value}}})
 const p=f.component('components/RecordingPlayer/index.vue',['video','manifest','index','presented','loadAnalysis','exactSupported']),cancelled=[]
 p.video.value={requestVideoFrameCallback:()=>7,cancelVideoFrameCallback:id=>cancelled.push(id),pause(){}}
 await f.mount();await p.loadAnalysis();p.presented(10,{mediaTime:.75});assert.equal(p.index.value,1)
 p.presented(11,{mediaTime:2.25});assert.equal(p.index.value,2);p.presented(12,{mediaTime:0});assert.equal(p.index.value,0)
 f.unmount();assert.deepEqual(cancelled,[7]);assert.equal(p.manifest.value,undefined)
})
test('unsupported video frame callbacks never substitute timer-based stale boxes',async()=>{
 const f=fixture({props:{clip:{id:'clip',kind:'DETECTION_SAMPLES',analysisUrl:'/api/x'}},modules:{'@/api/detectionFrames':{getAnalysis:async()=>manifest()}}})
 const p=f.component('components/RecordingPlayer/index.vue',['video','index','loadAnalysis','exactSupported']);p.video.value={pause(){}}
 await f.mount();await p.loadAnalysis();assert.equal(p.exactSupported.value,false);assert.equal(p.index.value,-1);f.unmount()
})
