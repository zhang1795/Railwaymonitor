<template>
  <el-card>
    <template #header><span>外部通知发送记录</span><el-button style="float:right" :loading="loading" @click="refresh">刷新</el-button></template>
    <el-alert :title="`站内提醒已启用；Webhook：${data.configuration.webhookConfigured?'已配置':'未配置'}；短信：${data.configuration.smsConfigured?'已配置':'未配置'}`" type="info" :closable="false"/>
    <p>短信默认发送等级 {{data.configuration.smsMinLevel}} 及以上风险的首次/升级提醒和监测故障；持续提醒保留站内。服务商受理不等于送达，结果未知时不自动重新发送短信。</p>
    <el-table :data="data.deliveries" v-loading="loading">
      <el-table-column prop="channel" label="渠道" width="110"/>
      <el-table-column label="来源"><template #default="{row}">{{row.entity_type==='FAULT'?'监测故障':'风险提醒'}} #{{row.entity_id}}</template></el-table-column>
      <el-table-column label="状态"><template #default="{row}">{{deliveryLabel(row.status)}}</template></el-table-column>
      <el-table-column prop="attempts" label="发送次数" width="100"/>
      <el-table-column label="更新时间"><template #default="{row}">{{utcTime(row.updated_at)}}</template></el-table-column>
      <el-table-column prop="error" label="最近错误"/>
      <el-table-column label="操作"><template #default="{row}"><el-button v-if="['FAILED','UNKNOWN','NOT_CONFIGURED'].includes(row.status)" link type="primary" @click="retryId=row.id;checked=false">核查后重试</el-button></template></el-table-column>
    </el-table>
    <p>展示最近100条外部发送记录。未配置渠道不会补发全部历史提醒。</p>
    <el-dialog :model-value="!!retryId" title="核查通知发送结果" @close="retryId=''"><p>先在服务商确认发送与回执记录；再次发送可能产生重复通知和费用。</p><el-checkbox v-model="checked">我已核对结果，确认需要重新发送</el-checkbox><template #footer><el-button @click="retryId=''">取消</el-button><el-button type="primary" :disabled="!checked" :loading="retrying" @click="retry">重新发送</el-button></template></el-dialog>
  </el-card>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import request from '@/api/request'
import {deliveryLabel,utcTime} from '@/utils/riskDisplay'
interface View {configuration:{webhookConfigured:boolean;smsConfigured:boolean;smsMinLevel:number};deliveries:Array<{id:string;entity_type:string;entity_id:number;channel:string;status:string;attempts:number;updated_at:string;error:string}>}
const data=ref<View>({configuration:{webhookConfigured:false,smsConfigured:false,smsMinLevel:3},deliveries:[]}),loading=ref(false),retryId=ref(''),checked=ref(false),retrying=ref(false)
let active=true
const refresh=async()=>{if(loading.value)return;loading.value=true;try{const result=await request.get<View>('/notifications');if(active)data.value=result}catch{}finally{if(active)loading.value=false}}
const retry=async()=>{if(!checked.value || !retryId.value || retrying.value)return;retrying.value=true;try{await request.post(`/notifications/${retryId.value}/retry`,{resultChecked:true});if(active){retryId.value='';await refresh()}}catch{}finally{if(active)retrying.value=false}}
onMounted(()=>void refresh());onBeforeUnmount(()=>{active=false})
</script>
