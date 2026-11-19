<template>
  <div class="region">
    <div v-if="picture && !failed" class="picture" @pointerdown="start" @pointermove="move" @pointerup="finish" @pointercancel="cancel" @lostpointercapture="cancel">
      <img :src="picture.url" draggable="false" alt="风险区域校准参考画面" @load="ready=true" @error="failed=true" />
      <span class="box" :style="rectangle" />
      <i v-for="(p,i) in points" :key="i" :style="{left:p[0]*100+'%', top:p[1]*100+'%'}" />
    </div>
    <small v-if="picture && !failed">{{ live ? '检测帧' : '历史证据截图' }} · {{ utcTime(picture.capturedAt) }}。拖动画出矩形，按目标框底边中心判定入区。{{ points.length ? '黄点表示本帧目标的判定位置。' : '' }}</small>
    <small v-else>暂无可用画面，可输入现场已校准的区域边界。</small>
    <el-button link :loading="loading" @click="fetchFrame()">获取检测参考帧</el-button>
    <div class="coordinates"><label v-for="(label,i) in ['左','上','右','下']" :key="label">{{label}}
      <el-input-number v-model="roi[i]" :aria-label="label+'边界'" :min="0" :max="1" :step="0.01" :precision="3" />
    </label></div>
    <el-button link @click="roi=[0,0,1,1]">使用全画面</el-button>
  </div>
</template>
<script setup lang="ts">
import {computed,ref,watch,onBeforeUnmount} from 'vue'
import {ElMessage} from 'element-plus'
import {getDetectionFrame, type DetectionFrame} from '@/api/detectionFrames'
import type {RiskRule} from '@/api/riskRules'
import {utcTime} from '@/utils/riskDisplay'
const props=defineProps<{camera:number; preview?:RiskRule['preview']}>()
const roi=defineModel<RiskRule['roi']>({required:true})
const live=ref<DetectionFrame>(), loading=ref(false), ready=ref(false), failed=ref(false)
const picture=computed(()=>live.value ? {url:'data:image/jpeg;base64,'+live.value.jpeg,capturedAt:live.value.observedAt} : props.preview)
const points=computed(()=>live.value?.objects.map(({bbox})=>[(bbox[0]+bbox[2])/2,bbox[3]]) ?? [])
type Point=[number,number]
const drag=ref<{id:number; start:Point; end:Point}>()
const bounds=(a:Point,b:Point):RiskRule['roi']=>[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])]
const rectangle=computed(()=>{
  const [x,y,right,bottom]=drag.value ? bounds(drag.value.start,drag.value.end) : roi.value
  return {left:x*100+'%',top:y*100+'%',width:(right-x)*100+'%',height:(bottom-y)*100+'%'}
})
function point(e:PointerEvent):Point{
  const box=(e.currentTarget as HTMLElement).getBoundingClientRect()
  const clamp=(n:number)=>Math.round(Math.max(0,Math.min(1,n))*1000)/1000
  return [clamp((e.clientX-box.left)/box.width),clamp((e.clientY-box.top)/box.height)]
}
function start(e:PointerEvent){
  if(!ready.value || e.button!==0 || drag.value)return
  const p=point(e)
  const pictureElement=e.currentTarget as HTMLElement
  pictureElement.setPointerCapture(e.pointerId)
  drag.value={id:e.pointerId,start:p,end:p}
}
function move(e:PointerEvent){if(drag.value?.id===e.pointerId)drag.value.end=point(e)}
function finish(e:PointerEvent){
  if(drag.value?.id!==e.pointerId)return
  const box=bounds(drag.value.start,point(e))
  if(box[2]>box[0] && box[3]>box[1])roi.value=box
  drag.value=undefined
}
function cancel(e:PointerEvent){if(drag.value?.id===e.pointerId)drag.value=undefined}
let generation=0
async function fetchFrame(quiet=false){
  const token=++generation
  loading.value=true
  try{
    const response=await getDetectionFrame(props.camera)
    if(token!==generation)return
    if(response.state==='FRESH' && response.frame){live.value=response.frame;failed.value=false}
    else if(quiet!==true)ElMessage.info('当前没有新鲜检测帧，可使用历史截图或输入坐标')
  }catch{if(quiet!==true && token===generation)ElMessage.error('检测参考帧获取失败')}
  finally{if(token===generation)loading.value=false}
}
watch(()=>props.camera,()=>{live.value=undefined;drag.value=undefined;void fetchFrame(true)},{immediate:true})
watch(()=>picture.value?.url,()=>{ready.value=false;failed.value=false})
onBeforeUnmount(()=>generation++)
</script>
<style scoped>
.region{width:100%}.picture{position:relative;touch-action:none;cursor:crosshair;user-select:none}.picture img{display:block;width:100%;pointer-events:none}.picture .box{position:absolute;border:2px solid #16a36d;background:#19a96d22;box-sizing:border-box;pointer-events:none}.picture i{position:absolute;width:7px;height:7px;background:#ffd54d;border:1px solid #222;border-radius:50%;transform:translate(-50%,-50%);pointer-events:none}.coordinates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.coordinates label{display:flex;align-items:center;gap:6px}.coordinates .el-input-number{max-width:85%}
</style>
