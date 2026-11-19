<template>
  <el-card>
    <template #header>历史录像查询</template>
    <el-alert title="原始录像与检测采样回放分别留存，共享30天/2 TB媒体预算。检测采样只覆盖识别目标前后及持续期间；原始录像时段采用录制端时钟估计。未登记、过期或缺失不代表当时没有风险。" type="info" :closable="false"/>
    <el-form inline class="filters">
      <el-form-item label="摄像头"><el-select v-model="camera" placeholder="选择摄像头" style="width:220px"><el-option v-for="item in cameras" :key="item.id" :value="item.id" :label="item.name"/></el-select></el-form-item>
      <el-form-item label="录制时间"><el-date-picker v-model="range" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束"/></el-form-item>
      <el-button type="primary" :loading="loading" @click="load(false)">查询</el-button>
    </el-form>
    <el-table :data="items" v-loading="loading">
      <el-table-column label="开始"><template #default="{row}">{{utcTime(row.started_at)}}</template></el-table-column>
      <el-table-column label="结束"><template #default="{row}">{{utcTime(row.ended_at)}}</template></el-table-column>
      <el-table-column label="大小"><template #default="{row}">{{(row.bytes/1024/1024).toFixed(2)}} MiB</template></el-table-column>
      <el-table-column label="内容"><template #default="{row}">{{row.kind==='DETECTION_SAMPLES'?'检测采样回放':'原始录像'}}</template></el-table-column>
      <el-table-column label="状态"><template #default="{row}">{{row.state==='READY'?'可读取':row.state==='EXPIRED'?'已过期':'文件不可用'}}</template></el-table-column>
      <el-table-column label="查看"><template #default="{row}"><el-button link type="primary" :disabled="row.state!=='READY'" @click="selected=row">播放</el-button></template></el-table-column>
    </el-table>
    <el-button v-if="next" :loading="loading" @click="load(true)">加载更多</el-button>
    <el-dialog :model-value="!!selected" title="历史录像" width="min(900px, 95vw)" @close="selected=undefined"><RecordingPlayer v-if="selected" :key="selected.id" :clip="selected"/></el-dialog>
  </el-card>
</template>
<script setup lang="ts">
import {ref,watch,onMounted,onBeforeUnmount} from 'vue'
import {ElMessage} from 'element-plus'
import {getCameraList} from '@/api/camera'
import type {Camera} from '@/types/camera'
import {getRecordings} from '@/api/recordings'
import type {RecordingClip,RecordingPage} from '@/api/recordings'
import {utcTime} from '@/utils/riskDisplay'
import RecordingPlayer from '@/components/RecordingPlayer/index.vue'
const cameras=ref<Camera[]>([]),camera=ref<number>(),range=ref<[Date,Date]>([new Date(Date.now()-3600000),new Date()])
const items=ref<RecordingClip[]>([]),next=ref<RecordingPage['next']>(null),selected=ref<RecordingClip>()
const loading=ref(false);let active=true,generation=0
watch([camera,range],()=>{generation++;items.value=[];next.value=null;selected.value=undefined;loading.value=false})
const load=async(more=false)=>{
  if(loading.value || !active)return
  if(!camera.value || !range.value?.[0] || !range.value?.[1]){ElMessage.warning('请选择摄像头和查询时间');return}
  if(range.value[1].getTime()<range.value[0].getTime() || range.value[1].getTime()-range.value[0].getTime()>31*86400000){ElMessage.warning('查询范围最多31天');return}
  const current=++generation;loading.value=true
  try{
    const result=await getRecordings(camera.value,{startTime:range.value[0].toISOString(),endTime:range.value[1].toISOString(),...(more && next.value ? next.value : {})})
    if(!active || current!==generation)return
    items.value=more?[...items.value,...result.items]:result.items;next.value=result.next
  }catch{}finally{if(active && current===generation)loading.value=false}
}
onMounted(async()=>{try{const result=await getCameraList({current:1,size:100});if(active)cameras.value=result.records}catch{}})
onBeforeUnmount(()=>{active=false;generation++;selected.value=undefined})
</script>
<style scoped>.filters{margin:20px 0}.el-table{margin-bottom:16px}</style>
