<template>
  <section aria-label="摄像头告警策略">
    <h3>摄像头告警策略</h3>
    <el-alert v-if="failed" title="摄像头列表加载失败" type="error" :closable="false">
      <el-button link @click="load">重新加载</el-button>
    </el-alert>
    <el-table v-else v-loading="loading" :data="cameras" border empty-text="尚未添加摄像头">
      <el-table-column label="摄像头" prop="name" />
      <el-table-column label="位置" prop="location" />
      <el-table-column label="风险判定">
        <template #default="{row}">{{modeLabel(row.riskRule)}}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{row}"><el-button link type="primary" @click="edit(row)">设置策略</el-button></template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>size" v-model:current-page="page" :page-size="size" :total="total" layout="prev, pager, next" />
    <RiskRuleDialog v-model="editing" :camera-id="cameraId" :camera-name="cameraName"
      :running="rows[cameraId]?.enabled" :stopping="changing.has(cameraId)" @saved="load" @stop="stop" />
  </section>
</template>
<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue'
import {getCameraList} from '@/api/camera'
import type {Camera} from '@/types/camera'
import {useMonitoring} from '@/composables/useMonitoring'
import {modeLabel} from '@/utils/ruleSummary'
import RiskRuleDialog from '@/components/RiskRuleDialog/index.vue'

const props=defineProps<{refreshKey:number}>()
const cameras=ref<Camera[]>([]), page=ref(1), total=ref(0), size=10
const loading=ref(false), failed=ref(false), editing=ref(false), cameraId=ref(0), cameraName=ref('')
const {rows,changing,change}=useMonitoring()
let generation=0
async function load(){
  const token=++generation
  loading.value=true;failed.value=false
  try{
    const result=await getCameraList({current:page.value,size})
    if(token!==generation)return
    total.value=result.total
    const last=Math.max(1,Math.ceil(total.value/size))
    if(page.value>last){page.value=last;return}
    cameras.value=result.records
  }catch{if(token===generation)failed.value=true}
  finally{if(token===generation)loading.value=false}
}
function edit(camera:Camera){
  cameraId.value=camera.id;cameraName.value=camera.name;editing.value=true
}
async function stop(camera:number){try{await change(camera,false)}catch{}}
watch(()=>[page.value,props.refreshKey],load,{immediate:true})
onBeforeUnmount(()=>generation++)
</script>
<style scoped>
h3{font-weight:600}.el-pagination{margin:12px 0;justify-content:flex-end}
</style>
