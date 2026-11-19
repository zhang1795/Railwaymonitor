const fs=require('node:fs'),path=require('node:path'),ts=require('typescript'),vue=require('vue')
const flush=()=>new Promise(resolve=>setImmediate(resolve))
function fixture(overrides={}) {
  let now=Date.parse('2026-11-10T12:00:00Z'),serial=0
  const jobs=new Map(),mounted=[],unmounted=[],sockets=[],sent=[],writes=[],messages=[],images=[]
  const listeners=new Map(),cache=new Map(),scope=vue.effectScope()
  const timer={
    setTimeout:(fn,ms)=>{jobs.set(++serial,{fn,due:now+ms,ms,repeat:false});return serial},
    setInterval:(fn,ms)=>{jobs.set(++serial,{fn,due:now+ms,ms,repeat:true});return serial},
    clearTimeout:id=>jobs.delete(id),clearInterval:id=>jobs.delete(id),
  }
  class Clock extends Date { static now(){return now} }
  const events={addEventListener:(type,fn)=>{if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn)},removeEventListener:(type,fn)=>listeners.get(type)?.delete(fn)}
  const window={...events,...timer,location:{protocol:'https:',host:'test.example'}}
  const document={...events,visibilityState:'visible'}
  class Socket {
    static OPEN=1;static CONNECTING=0
    constructor(url){this.url=url;this.readyState=0;this.sent=[];sockets.push(this)}
    send(value){const parsed=JSON.parse(value);this.sent.push(parsed);sent.push(parsed)}
    close(){this.readyState=3}
  }
  class Image {
    width=640;height=480
    constructor(){images.push(this)}
    set src(value){if(overrides.autoDecode!==false)this.onload?.()}
  }
  const cameraRows=[1,2,3,4].map(id=>({id,name:'camera-'+id,status:1,longitude:103,latitude:36}))
  const monitoringRows=cameraRows.map(row=>({camera_id:row.id,enabled:true,state:'RUNNING',last_status_at:new Clock(now).toISOString(),metrics:{lastFrameAt:new Clock(now).toISOString(),lastInferenceAt:new Clock(now).toISOString()}}))
  const route=vue.reactive({query:{},path:'/monitor'})
  const message=Object.assign(value=>messages.push(value),Object.fromEntries(['success','error','warning','info'].map(kind=>[kind,value=>messages.push({kind,value})])))
  const modules={
    vue:{...vue,onMounted:fn=>mounted.push(fn),onBeforeUnmount:fn=>unmounted.push(fn),onUnmounted:fn=>unmounted.push(fn)},
    'vue-router':{useRouter:()=>({push(){},replace(){}}),useRoute:()=>route},
    'element-plus':{ElMessage:message,ElMessageBox:{confirm:async()=>{},alert:async()=>{}}},
    '@/api/request':{__esModule:true,default:{post:async()=>({grant:'test-only-opaque-grant'})}},
    '@/api/monitoring':{getMonitoring:async()=>monitoringRows.map(row=>({...row})),setMonitoring:async(id,enabled)=>{writes.push([id,enabled]);const row=monitoringRows.find(row=>row.camera_id===id);row.enabled=enabled;return {...row}}},
    '@/api/camera':{getCameraList:async()=>({records:cameraRows,total:cameraRows.length})},
    '@/api/alarmNotices':{getAlarmNotices:async()=>({unreadCount:0,items:[],nextBeforeId:null}),readAlarmNotices:async ids=>writes.push(ids),readNoticeIds:async ids=>writes.push(ids)},
    '@/api/Abnormal':{getAbnormalEventList:async()=>({records:[],total:0}),getAlarmInsight:async()=>({risk:[],sources:[],transitions:[],handling:[],notices:[],evidence:{configured:false,images:[],videoState:'NOT_UPLOADED'},evidenceWorker:[]})},
    '@/stores/user':{useUserStore:()=>({userInfo:{id:1,role:1}})},
    '@/utils/format':{formatDateTime:String,formatDeviceStatus:String,formatAbnormalLevel:String,formatStatus:String},
    '@/api/riskRules':{getTemplates:async()=>({versions:[],recommendation:{revision:0,template:null}}),riskClasses:['防撞设备','气球','牛','水害','滑坡','违规建筑','风筝','落石','鸟巢','广告牌','坑洞','垃圾','工人']},
    '@/utils/validate':{validateIP:()=>true,validateRTSP:()=>true},
    '@element-plus/icons-vue':{},

  }
  for(const [name,value] of Object.entries(overrides.modules || {}))modules[name]=name.startsWith('@/api/')?{...(modules[name] || {}),...value}:value
  const globals=['require','exports','window','document','console','setTimeout','clearTimeout','setInterval','clearInterval','Date','WebSocket','Image','defineModel','defineProps','defineEmits','defineExpose','testEnv']
  function evaluate(relative,expose) {
    const filename=path.resolve(__dirname,'../src',relative)
    let source=fs.readFileSync(filename,'utf8')
    if(relative.endsWith('.vue'))source=source.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1]
    source=source.replace(/import\.meta\.env/g,'testEnv')
    const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText
    const exports={}
    const values=[resolve,exports,window,document,{log(){},warn(){},error(){}},timer.setTimeout,timer.clearTimeout,timer.setInterval,timer.clearInterval,Clock,Socket,Image,()=>overrides.model||vue.ref(),()=>overrides.props||{},()=>()=>{},()=>{},{}]
    return scope.run(()=>new Function(...globals,output+(expose?'\nreturn {'+expose.join(',')+'};':'\nreturn exports;'))(...values))
  }
  function resolve(name) {
    if(name in modules)return modules[name]
    if(name.endsWith('.vue'))return {__esModule:true,default:{}}
    if(name.startsWith('@/')){
      if(!cache.has(name))cache.set(name,evaluate(name.slice(2)+'.ts'))
      return cache.get(name)
    }
    throw Error('Unexpected production dependency: '+name)
  }
  return {timer,jobs,sockets,sent,writes,messages,images,route,cameraRows,monitoringRows,modules,vue,
    module:name=>resolve(name),component:(file,expose)=>evaluate(file,expose),
    now:()=>now,
    async mount(){for(const fn of mounted)await fn();await flush()},
    unmount(){unmounted.forEach(fn=>fn());scope.stop()},
    async advance(ms){
      const end=now+ms
      for(;;){
        const next=[...jobs.entries()].filter(([,job])=>job.due<=end).sort((a,b)=>a[1].due-b[1].due)[0]
        if(!next)break
        const [id,job]=next;now=job.due
        if(job.repeat)job.due+=job.ms;else jobs.delete(id)
        await job.fn();await flush()
      }
      now=end;await flush()
    },
    async authenticate(socket=sockets[sockets.length-1]){
      socket.readyState=1;await socket.onopen()
      socket.onmessage({data:JSON.stringify({type:'authenticated',data:{cameraId:0}})})
      await vue.nextTick();return socket
    },
  }
}
module.exports={fixture,flush}
