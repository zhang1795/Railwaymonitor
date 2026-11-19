<template>
  <el-dialog :model-value="modelValue" :title="cameraName ? cameraName+' · 告警策略' : '摄像头告警策略'" width="min(720px, 95vw)" :close-on-click-modal="false" @update:model-value="emit('update:modelValue',$event)">
    <el-form v-if="rule" label-width="140px" :disabled="saving">
      <el-alert v-if="running" title="此路后台检测已启用。可先校准画面，停用该路后再保存。" type="warning" :closable="false"/>
      <el-form-item label="场景模板">
        <el-select :model-value="templateKey(rule.template)" @change="choose">
          <el-option value="" label="摄像头自定义" />
          <el-option v-for="v in versions" :key="templateKey(v)" :value="templateKey(v)" :label="templateLabel(v)" />
        </el-select>
        <el-button v-if="rule.template" link @click="choose(templateKey(rule.template))">重新载入模板参数</el-button>
        <small>选择模板会载入该版本的参数；区域和启用状态由本机位单独确认。</small>
      </el-form-item>
      <el-form-item label="启用区域风险判定"><el-switch v-model="rule.enabled" /><small>{{rule.enabled ? '按下列区域与参数判定风险' : '仅记录待核验观察'}}</small></el-form-item>
      <el-form-item label="图像风险区域"><RegionPicker v-model="rule.roi" :camera="cameraId" :preview="rule.preview"/></el-form-item>
      <RuleParameters :value="rule"/>
      <el-button link @click="loadHistory">查看最近规则变更</el-button>
      <div v-for="item in history" :key="item.revision" class="history">
        r{{item.revision}} · {{utcTime(item.changed_at)}} · {{item.actor_id ? '用户 #'+item.actor_id : '历史配置'}}<br/>
        {{ruleSummary(JSON.parse(item.policy))}}
      </div>
      <small v-if="history && !history.length">尚无保存记录</small>
    </el-form>
    <el-skeleton v-else-if="loading" :rows="5" animated />
    <el-alert v-else-if="modelValue" title="规则加载失败，请关闭后重试" type="error" :closable="false" />
    <template #footer>
      <el-button @click="emit('update:modelValue',false)">关闭</el-button>
      <el-button v-if="running" :disabled="stopping" @click="stopDetection">停用此路后台检测</el-button>
      <el-button type="primary" :disabled="!rule || running" :loading="saving" @click="confirmSave">保存规则</el-button>
    </template>
  </el-dialog>
</template>
<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue'
import {ElMessage,ElMessageBox} from 'element-plus'
import {getRiskRule,saveRiskRule,getTemplates,getRuleHistory,type RiskRule,type Published,type RuleRevision} from '@/api/riskRules'
import {utcTime} from '@/utils/riskDisplay'
import {templateKey,templateLabel,ruleSummary} from '@/utils/ruleSummary'
import RegionPicker from './RegionPicker.vue'
import RuleParameters from './RuleParameters.vue'
const props=defineProps<{modelValue:boolean;cameraId:number; cameraName?:string; running?:boolean; stopping?:boolean}>()
const emit=defineEmits<{(e:'update:modelValue',value:boolean):void;(e:'saved'):void;(e:'stop',camera:number):void}>()
const rule=ref<RiskRule>(), loading=ref(false), saving=ref(false)
const versions=ref<Published[]>([]), history=ref<RuleRevision[]>()
let generation=0
watch(()=>[props.modelValue,props.cameraId],async()=>{
  const token=++generation
  rule.value=undefined;versions.value=[];history.value=undefined
  if(!props.modelValue)return
  loading.value=true
  try{
    const [result,catalog]=await Promise.all([getRiskRule(props.cameraId),getTemplates()])
    if(token===generation){rule.value=result;versions.value=catalog.versions}
  }catch{}finally{if(token===generation)loading.value=false}
},{immediate:true})
onBeforeUnmount(()=>generation++)
function choose(key:string){
  if(!rule.value)return
  const version=versions.value.find(v=>templateKey(v)===key)
  if(!version){rule.value.template=null;return}
  Object.assign(rule.value,version.parameters,{classes:[...version.parameters.classes],
    resetOverrides:true,template:{id:version.id,version:version.version,name:version.name}})
}
async function loadHistory(){
  const token=generation
  try{const rows=await getRuleHistory(props.cameraId);if(token===generation)history.value=rows}catch{}
}
async function stopDetection(){
  const token=generation
  try{await ElMessageBox.confirm('停用后此路检测会中断。保存规则后可重新启用。','停用后台检测')
    if(token===generation)emit('stop',props.cameraId)
  }catch{}
}
async function confirmSave(){
  const token=generation
  if(rule.value?.enabled && rule.value.roi.join(',')==='0,0,1,1'){
    try{await ElMessageBox.confirm('当前区域覆盖全画面。已确认该范围适合此机位？','确认风险区域')}catch{return}
  }
  if(token===generation)await save()
}
async function save(){
  if(!rule.value || saving.value || props.running)return
  if(rule.value.enabled && !rule.value.classes.length){ElMessage.warning('请选择风险目标类别');return}
  if(rule.value.roi[0]>=rule.value.roi[2] || rule.value.roi[1]>=rule.value.roi[3]){ElMessage.warning('左/上边界须小于右/下边界');return}
  const token=generation,camera=props.cameraId
  const values=JSON.parse(JSON.stringify(rule.value)) as RiskRule
  delete values.preview
  saving.value=true
  try{
    await saveRiskRule(camera,values)
    emit('saved')
    if(token===generation){ElMessage.success('风险规则已保存，下次启用检测时生效');emit('update:modelValue',false)}
  }catch{}finally{saving.value=false}
}
</script>
<style scoped>
.el-select{width:100%}small,.history{color:var(--el-text-color-secondary);font-size:12px}.history{padding:6px}.el-switch+small{margin-left:8px}
</style>
