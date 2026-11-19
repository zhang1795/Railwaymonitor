<template>
  <el-popover placement="bottom-end" :width="430" trigger="click">
    <template #reference><el-button :type="data.openCount ? 'warning' : 'default'" plain>{{healthy ? `监测故障 ${data.openCount} · 未读 ${data.unreadCount}` : '故障查询不可用'}}</el-button></template>
    <p>检测链路故障与目标风险分别记录；已读不会解除故障。</p>
    <el-scrollbar max-height="320px"><div v-for="item in data.items" :key="item.id" class="fault">
      <strong>{{item.camera_name || `摄像头 ${item.camera_id}`}}</strong> · {{item.recovered_at ? (item.closed_reason==='MONITORING_DISABLED'?'检测已停用':'推理已恢复') : '监测异常'}}
      <p>{{item.reason==='WORKER_FAILED'?'检测任务失败':'未收到近期有效推理，请检查节点与视频源'}}</p>
      <small>{{utcTime(item.opened_at)}}<span v-if="item.recovered_at"> → {{utcTime(item.recovered_at)}}</span></small>
    </div></el-scrollbar>
    <el-empty v-if="!data.items.length" description="暂无记录" :image-size="40"/>
    <p>最多展示最近100条未读/未恢复记录。</p>
    <el-button @click="refresh">刷新</el-button><el-button :disabled="!healthy || !data.items.length" :loading="reading" @click="markRead">本批标为已读</el-button>
  </el-popover>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import request from '@/api/request'
import {utcTime} from '@/utils/riskDisplay'
interface Fault {id:number;camera_id:number;camera_name?:string;reason:string;opened_at:string;recovered_at?:string;closed_reason?:string}
const data=ref<{items:Fault[];openCount:number;unreadCount:number}>({items:[],openCount:0,unreadCount:0})
const healthy=ref(false),reading=ref(false)
let active=true,pending=false,timer:ReturnType<typeof setInterval>|undefined
const refresh=async()=>{if(pending || !active)return;pending=true;try{const result=await request.get<typeof data.value>('/monitoring/faults',{silent:true} as any);if(active){data.value=result;healthy.value=true}}catch{if(active)healthy.value=false}finally{pending=false}}
const markRead=async()=>{const ids=data.value.items.map(item=>item.id);if(!ids.length || reading.value)return;reading.value=true;try{await request.post('/monitoring/faults/read',{ids});await refresh()}catch{}finally{reading.value=false}}
onMounted(()=>{void refresh();timer=setInterval(()=>void refresh(),5000)})
onBeforeUnmount(()=>{active=false;if(timer)clearInterval(timer)})
</script>
<style scoped>.fault{border-bottom:1px solid var(--el-border-color-lighter);padding:10px 0}p,small{font-size:12px;color:var(--el-text-color-secondary)}</style>
