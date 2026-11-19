<template>
  <div class="detection-view">
    <div class="detection-heading"><strong>{{camera.name}} · 检测采样</strong><span>{{statusLabel}}</span></div>
    <div v-if="displayed && state==='FRESH'" class="result-picture" :style="{aspectRatio:`${displayed.width}/${displayed.height}`}">
      <img :key="displayed.sessionId+':'+displayed.frameSeq" :src="'data:image/jpeg;base64,'+displayed.jpeg" alt="同一次推理的原始图像"/>
      <DetectionOverlay :objects="displayed.objects" :trails="displayed.trails||[]" :show-boxes="showBoxes" :show-trails="showTrails"/>
    </div>
    <div v-else class="waiting">{{statusLabel}}</div>
    <div class="controls"><el-checkbox v-model="showBoxes">目标框</el-checkbox><el-checkbox v-model="showTrails">采样轨迹</el-checkbox></div>
    <template v-if="displayed && state==='FRESH'">
      <small>观测 {{utcTime(displayed.observedAt)}} · 帧 {{displayed.frameSeq}} · 帧龄 {{Math.round(ageMs)}} ms</small>
      <small>会话 {{displayed.sessionId.slice(0,8)}} · 模型 {{displayed.modelSha256.slice(0,12)}} · {{displayed.quality==='DECODE_CHECKED'?'解码检查通过':'源质量未核验'}}</small>
      <div class="targets" v-if="displayed.objects.length"><span v-for="(object,index) in displayed.objects" :key="index">{{object.label}} {{(object.confidence*100).toFixed(1)}}% · {{object.trackId?'跟踪 #'+object.trackId:'尚未确认跟踪'}}</span></div>
      <small v-else>本次推理未检测到目标。</small>
      <small v-if="displayed.truncated">目标共 {{displayed.totalObjects}} 个，当前最多展示 64 个。</small>
    </template>
    <small>识别结果不等于风险结论。轨迹只连接本会话内确认匹配的采样点。</small>
  </div>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount,watch} from 'vue'
import type {Camera} from '@/types/camera'
import {getDetectionFrame} from '@/api/detectionFrames'
import type {DetectionFrame} from '@/api/detectionFrames'
import {utcTime} from '@/utils/riskDisplay'
import DetectionOverlay from '@/components/DetectionOverlay/index.vue'
const props=defineProps<{camera:Camera}>()
const displayed=ref<DetectionFrame>(),state=ref('WAITING'),ageMs=ref(0),showBoxes=ref(true),showTrails=ref(true)
const statusLabel=computed(()=>({FRESH:'最新检测结果',WAITING:'等待本会话检测帧',DISABLED:'后台检测已停用',EXPIRED:'检测结果已过期，等待新帧',SOURCE_ERROR:'视频源或检测任务异常',NETWORK_ERROR:'检测结果连接异常'}[state.value]||'等待检测结果'))
let active=true,generation=0,timer:ReturnType<typeof setTimeout>|undefined,watchdog:ReturnType<typeof setInterval>|undefined,lastFresh=0,serverAge=0,decoding:HTMLImageElement|undefined
const clear=()=>{displayed.value=undefined;decoding=undefined}
const poll=async()=>{
  const token=generation
  try{
    const value=await getDetectionFrame(props.camera.id,displayed.value?.frameSeq||0,displayed.value?.sessionId||'')
    if(!active || token!==generation)return
    state.value=value.state
    if(value.state!=='FRESH'){clear();return}
    lastFresh=Date.now();serverAge=value.observedAgeMs||0;ageMs.value=serverAge
    if(value.frame){
      const frame=value.frame,image=new Image();decoding=image
      image.onload=()=>{if(active && token===generation && decoding===image && state.value==='FRESH'){displayed.value=frame;decoding=undefined}}
      image.onerror=()=>{if(active && token===generation && decoding===image){state.value='NETWORK_ERROR';clear()}}
      image.src='data:image/jpeg;base64,'+frame.jpeg
    }
  }catch{if(active && token===generation){state.value='NETWORK_ERROR';clear()}}
  finally{if(active && token===generation)timer=setTimeout(()=>{void poll()},500)}
}
watch(()=>props.camera.id,()=>{generation++;if(timer)clearTimeout(timer);clear();state.value='WAITING';void poll()})
onMounted(()=>{void poll();watchdog=setInterval(()=>{if(state.value==='FRESH'){ageMs.value=serverAge+Math.max(0,Date.now()-lastFresh);if(ageMs.value>5000){state.value='EXPIRED';clear()}}},250)})
onBeforeUnmount(()=>{active=false;generation++;if(timer)clearTimeout(timer);if(watchdog)clearInterval(watchdog);clear()})
</script>
<style scoped>
.detection-view{height:100%;overflow:auto;background:#17212e;color:#eef4fa;padding:10px;box-sizing:border-box;display:flex;flex-direction:column;gap:7px}.detection-heading{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}.result-picture{position:relative;width:100%;flex-shrink:0;background:#000}.result-picture img{display:block;width:100%;height:100%}.waiting{min-height:140px;display:grid;place-items:center;color:#e7c68a}.controls{display:flex;gap:14px}.controls :deep(.el-checkbox__label){color:#e6eef8}small{font-size:12px;overflow-wrap:anywhere;color:#c4d2e3}.targets{display:flex;flex-wrap:wrap;gap:8px;max-height:110px;overflow:auto}.targets span{font-size:12px;background:#26394c;padding:4px}
</style>
