<template>
  <div class="recording-player">
    <strong>{{clip.kind==='DETECTION_SAMPLES'?'检测采样回放':'原始录像'}}</strong>
    <div class="picture" :style="manifest?{aspectRatio:`${manifest.width}/${manifest.height}`}:{aspectRatio:'16/9'}">
      <video ref="video" :src="clip.url" controls :controlslist="clip.kind==='DETECTION_SAMPLES'?'nofullscreen':undefined" :disable-picture-in-picture="clip.kind==='DETECTION_SAMPLES'" preload="none" @play="loadAnalysis" @seeking="index=-1" @error="failed"/>
      <DetectionOverlay v-if="current && exactSupported && !videoError" :objects="current.objects" :trails="trails" :show-boxes="showBoxes" :show-trails="showTrails"/>
    </div>
    <template v-if="clip.kind==='DETECTION_SAMPLES'">
      <div class="controls"><el-checkbox v-model="showBoxes" :disabled="!exactSupported">目标框</el-checkbox><el-checkbox v-model="showTrails" :disabled="!exactSupported">采样轨迹</el-checkbox></div>
      <p>真实推理采样，最多 {{manifest?.maxSampleFps ?? 2}} 帧/秒，按观测时间播放；采样间隔内的运动没有逐帧记录。</p>
      <p v-if="!exactSupported" class="error">当前浏览器不支持逐帧同步，已关闭叠框；请使用支持视频帧回调的浏览器查看检测结果。</p>
      <p v-if="analysisError" class="error">{{analysisError}}</p>
      <template v-if="manifest">
        <small>会话 {{manifest.sessionId.slice(0,8)}} · 模型 {{manifest.modelSha256.slice(0,12)}} · {{manifest.frameCount}} 个采样 · 写入丢弃 {{manifest.droppedSamples}} 个采样</small>
        <template v-if="current"><small>观测 {{utcTime(current.observedAt)}} · 推理帧 {{current.frameSeq}} · {{current.quality==='DECODE_CHECKED'?'解码检查通过':'源质量未核验'}}</small><div class="targets"><span v-for="(object,i) in current.objects" :key="i">{{object.label}} {{(object.confidence*100).toFixed(1)}}% · {{object.trackId?'跟踪 #'+object.trackId:'尚未确认跟踪'}}</span><span v-if="!current.objects.length">本次采样未检测到目标</span></div><small v-if="current.truncated">该帧结果有截断，共 {{current.totalObjects}} 个目标。</small></template>
      </template>
    </template>
    <p v-else>原始视频独立留存，时段来自录制端时钟估计，没有逐帧检测叠加。</p>
    <p v-if="videoError" class="error">录像播放失败，请检查文件与浏览器编码支持。</p>
    <small>识别结果不等于风险结论；采集时钟未经过硬件校准。</small>
  </div>
</template>
<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount,watch} from 'vue'
import type {RecordingClip} from '@/api/recordings'
import {getAnalysis} from '@/api/detectionFrames'
import type {AnalysisManifest} from '@/api/detectionFrames'
import {sampleIndex,sampleTrails} from '@/utils/frameResults'
import {utcTime} from '@/utils/riskDisplay'
import DetectionOverlay from '@/components/DetectionOverlay/index.vue'
const props=defineProps<{clip:RecordingClip}>()
const video=ref<HTMLVideoElement>(),manifest=ref<AnalysisManifest>(),index=ref(-1),exactSupported=ref(false),showBoxes=ref(true),showTrails=ref(true),analysisError=ref(''),videoError=ref(false)
const current=computed(()=>manifest.value && index.value>=0?manifest.value.frames[index.value]:undefined)
const trails=computed(()=>manifest.value?sampleTrails(manifest.value,index.value):[])
let active=true,generation=0,callback:number|undefined,loading=false,lastMediaTime=-1
const presented=(_now:number,frame:VideoFrameCallbackMetadata)=>{
  if(!active)return
  lastMediaTime=frame.mediaTime;index.value=manifest.value?sampleIndex(manifest.value,frame.mediaTime):-1
  callback=video.value?.requestVideoFrameCallback(presented)
}
const loadAnalysis=async()=>{
  if(props.clip.kind!=='DETECTION_SAMPLES' || !props.clip.analysisUrl || manifest.value || loading)return
  const token=generation;loading=true;analysisError.value=''
  try{
    const value=await getAnalysis(props.clip.analysisUrl)
    if(!active || token!==generation)return
    manifest.value=value;index.value=exactSupported.value?sampleIndex(value,lastMediaTime):-1
  }catch{if(active && token===generation)analysisError.value='检测元数据读取失败，暂不能叠加；可重新点击播放重试。'}
  finally{if(active && token===generation)loading=false}
}
const failed=()=>{videoError.value=true;index.value=-1}
watch(()=>props.clip.id,()=>{generation++;manifest.value=undefined;index.value=-1;lastMediaTime=-1;loading=false;analysisError.value='';videoError.value=false})
onMounted(()=>{exactSupported.value=typeof video.value?.requestVideoFrameCallback==='function';if(exactSupported.value)callback=video.value?.requestVideoFrameCallback(presented)})
onBeforeUnmount(()=>{active=false;generation++;video.value?.pause();if(callback!==undefined)video.value?.cancelVideoFrameCallback(callback);manifest.value=undefined})
</script>
<style scoped>.recording-player{display:flex;flex-direction:column;gap:8px;margin:10px 0;max-width:100%}.picture{position:relative;width:100%;background:#111;overflow:hidden}.picture video{display:block;width:100%;height:100%;object-fit:contain}.controls{display:flex;gap:16px}p,small{margin:0;color:var(--el-text-color-secondary);font-size:12px;overflow-wrap:anywhere}.error{color:var(--el-color-danger)}.targets{display:flex;gap:8px;flex-wrap:wrap;font-size:12px}.targets span{padding:4px;background:var(--el-fill-color-light)}</style>
