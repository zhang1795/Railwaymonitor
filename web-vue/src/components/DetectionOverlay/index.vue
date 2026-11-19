<template>
  <svg class="detection-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="当前图像的目标检测结果">
    <g v-if="showTrails" fill="none" stroke="#48e4ff" stroke-width="2"><polyline v-for="trail in trails" :key="trail.trackId" :points="trail.points.map(point=>point.map(n=>n*1000).join(',')).join(' ')" vector-effect="non-scaling-stroke"/></g>
    <g v-if="showBoxes" v-for="(object,index) in objects" :key="index">
      <rect :x="object.bbox[0]*1000" :y="object.bbox[1]*1000" :width="(object.bbox[2]-object.bbox[0])*1000" :height="(object.bbox[3]-object.bbox[1])*1000" fill="none" stroke="#ffdf5d" stroke-width="2" vector-effect="non-scaling-stroke"/>
    </g>
  </svg>
  <div v-if="showBoxes" class="object-labels"><span v-for="(object,index) in objects" :key="index" :style="{left:Math.min(object.bbox[0]*100,65)+'%',top:Math.max(0,object.bbox[1]*100-6)+'%'}">{{object.label}} {{(object.confidence*100).toFixed(0)}}% · {{object.trackId?'#'+object.trackId:'待确认'}}</span></div>
</template>
<script setup lang="ts">
import type {FrameObject,FrameTrail} from '@/api/detectionFrames'
defineProps<{objects:FrameObject[];trails:FrameTrail[];showBoxes:boolean;showTrails:boolean}>()
</script>
<style scoped>.detection-overlay,.object-labels{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.object-labels span{position:absolute;font:12px/1.4 sans-serif;background:#17212ee0;color:#ffef98;padding:0 3px;white-space:nowrap;max-width:95%;overflow:hidden;text-overflow:ellipsis}</style>
