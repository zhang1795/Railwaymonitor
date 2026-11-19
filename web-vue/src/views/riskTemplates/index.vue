<template>
  <section class="templates">
    <header><h2>告警策略设置</h2><el-button :disabled="busy || loading" @click="refresh">刷新</el-button></header>
    <el-alert v-if="!catalog && !loading" title="全局默认策略和场景模板加载失败" type="error" :closable="false" />
    <CameraPolicies :refresh-key="cameraRefresh" />
    <h3>全局默认策略</h3>
    <div v-if="catalog" class="default">
      <label for="recommended">新增摄像头的默认模板</label>
      <el-select id="recommended" v-model="recommended" aria-label="新增摄像头的默认模板" :disabled="busy">
        <el-option label="无默认模板" value="" />
        <el-option v-for="v in catalog.versions" :key="templateKey(v)" :value="templateKey(v)" :label="templateLabel(v)" />
      </el-select>
      <el-button :disabled="busy || recommended===templateKey(catalog.recommendation.template)" @click="setDefault">保存默认</el-button>
      <small>新机位以待核验观察启动。管理员校准本机位区域后，可开启风险判定。</small>
    </div>
    <header><h3>场景模板</h3><el-button type="primary" :disabled="!catalog || busy" @click="edit()">新建模板</el-button></header>
    <el-table v-loading="loading" :data="latest" border>
      <el-table-column label="场景"><template #default="{row}">{{templateLabel(row)}}</template></el-table-column>
      <el-table-column label="关注类别"><template #default="{row}">{{row.parameters.classes.map((i:number)=>riskClasses[i]).join('、')}}</template></el-table-column>
      <el-table-column label="最低置信度" prop="parameters.confidence" />
      <el-table-column label="持续符合（秒）" prop="parameters.dwellSeconds"/>
      <el-table-column label="发布记录"><template #default="{row}">{{row.actorId ? '用户 #'+row.actorId+' · '+utcTime(row.publishedAt) : '系统预设，参数需现场校准'}}</template></el-table-column>
      <el-table-column label="操作" min-width="190"><template #default="{row}">
        <el-button link type="primary" :disabled="busy" @click="edit(row)">编辑并发布</el-button>
        <el-button link type="primary" :disabled="busy" @click="review(row)">选择升级机位</el-button>
      </template></el-table-column>
    </el-table>
    <el-dialog v-model="editing" title="发布场景模板" width="min(600px, 95vw)" :close-on-click-modal="false">
      <el-form label-width="140px" :disabled="busy">
        <el-form-item label="模板名称"><el-input v-model="draftName" maxlength="80"/></el-form-item>
        <RuleParameters :value="draft"/>
      </el-form>
      <small>发布后可选择需要升级的摄像头。当前机位和全局默认均固定在已选版本。</small>
      <template #footer><el-button :disabled="busy" @click="editing=false">取消</el-button><el-button type="primary" :loading="busy" @click="publish">发布 v{{(base?.version || 0)+1}}</el-button></template>
    </el-dialog>
    <el-dialog v-model="reviewing" :title="target ? templateLabel(target)+' · 升级预览' : '升级预览'" width="min(900px, 96vw)" :close-on-click-modal="false" @close="impactGeneration++">
      <el-alert v-if="impactError" title="升级预览加载失败，请关闭后重试" type="error" :closable="false" />
      <el-table v-else v-loading="impactLoading" :data="impact" row-key="cameraId" empty-text="没有绑定旧版本的摄像头" @selection-change="selected=$event">
        <el-table-column type="selection" :selectable="(row:UpgradeImpact)=>!row.running && !busy" />
        <el-table-column prop="name" label="摄像头" />
        <el-table-column label="版本"><template #default="{row}">v{{row.fromVersion}} → v{{target?.version}}</template></el-table-column>
        <el-table-column label="实际参数变化" min-width="200"><template #default="{row}">{{changes(row.before,row.after).join('，') || '仅更新绑定版本'}}</template></el-table-column>
        <el-table-column label="后台检测"><template #default="{row}">{{row.running ? '已启用，需先停用' : '已停用'}}</template></el-table-column>
      </el-table>
      <p>升级保留每路摄像头的风险区域、启用设置和已调过的参数。重新启用检测后生效。</p>
      <template #footer><el-button :disabled="busy" @click="reviewing=false">关闭</el-button><el-button type="primary" :loading="busy" :disabled="!selected.length || impactLoading || impactError" @click="applyUpgrade">升级选中的 {{selected.length}} 路</el-button></template>
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import {computed,onMounted,onBeforeUnmount,ref} from 'vue'
import {ElMessage} from 'element-plus'
import CameraPolicies from './CameraPolicies.vue'
import RuleParameters from '@/components/RiskRuleDialog/RuleParameters.vue'
import {getTemplates,publishTemplate,recommendTemplate,templateImpact,upgradeCameras,riskClasses,
  type RiskParameters,type Catalog,type Published,type UpgradeImpact} from '@/api/riskRules'
import {changes,templateKey,templateLabel} from '@/utils/ruleSummary'
import {utcTime} from '@/utils/riskDisplay'
const catalog=ref<Catalog>(), recommended=ref(''), loading=ref(false), busy=ref(false)
const latest=computed(()=>catalog.value?.versions.filter((v,i,all)=>all.findIndex(x=>x.id===v.id)===i) ?? [])
const cameraRefresh=ref(0)
function refresh(){cameraRefresh.value++;return load()}
let generation=0,impactGeneration=0
async function load(){
  const token=++generation;loading.value=true
  try{
    const value=await getTemplates()
    if(token===generation){catalog.value=value;recommended.value=templateKey(value.recommendation.template)}
  }catch{if(token===generation)catalog.value=undefined}finally{if(token===generation)loading.value=false}
}
onMounted(load)
onBeforeUnmount(()=>{generation++;impactGeneration++})
async function setDefault(){
  if(!catalog.value || busy.value)return
  busy.value=true
  try{
    const value=catalog.value.versions.find(v=>templateKey(v)===recommended.value)
    await recommendTemplate(catalog.value.recommendation.revision,value ? {id:value.id,version:value.version,name:value.name} : null)
    ElMessage.success('新增摄像头的默认模板已保存');await load()
  }catch{}finally{busy.value=false}
}
const empty=():RiskParameters=>({classes:[],confidence:0.5,dwellSeconds:2,graceSeconds:3,reminderSeconds:60,level:1,escalateSeconds:180})
const draft=ref<RiskParameters>(empty()), draftName=ref(''),base=ref<Published>(),editing=ref(false)
function edit(source?:Published){
  base.value=source;draftName.value=source?.name || ''
  draft.value=source ? {...source.parameters,classes:[...source.parameters.classes]} : empty()
  editing.value=true
}
async function publish(){
  if(busy.value)return
  if(!draftName.value.trim() || !draft.value.classes.length){ElMessage.warning('请输入名称并选择关注类别');return}
  busy.value=true
  try{
    const next=await publishTemplate(draftName.value.trim(),draft.value,base.value)
    editing.value=false;ElMessage.success('已发布 '+templateLabel(next));await load()
    if(next.version>1)await review(next)
  }catch{}finally{busy.value=false}
}
const reviewing=ref(false),impactLoading=ref(false),impactError=ref(false),target=ref<Published>()
const impact=ref<UpgradeImpact[]>([]),selected=ref<UpgradeImpact[]>([])
async function review(version:Published){
  const token=++impactGeneration
  target.value=version;selected.value=[];impact.value=[];impactError.value=false;impactLoading.value=true;reviewing.value=true
  try{const rows=await templateImpact(version);if(token===impactGeneration)impact.value=rows}
  catch{if(token===impactGeneration)impactError.value=true}finally{if(token===impactGeneration)impactLoading.value=false}
}
async function applyUpgrade(){
  if(!target.value || !selected.value.length || busy.value)return
  busy.value=true
  try{
    await upgradeCameras(target.value,selected.value)
    cameraRefresh.value++;ElMessage.success('已保存所选机位的新版规则');await review(target.value)
  }catch{if(reviewing.value)await review(target.value)}finally{busy.value=false}
}
</script>
<style scoped>
.templates{padding:20px}header,.default{display:flex;align-items:center;gap:12px;flex-wrap:wrap}header{justify-content:space-between}h2,h3{font-weight:600}.default{padding:16px;border:1px solid var(--el-border-color);border-radius:6px}.default .el-select{width:240px}small,p{color:var(--el-text-color-secondary)}small{font-size:13px}
</style>
