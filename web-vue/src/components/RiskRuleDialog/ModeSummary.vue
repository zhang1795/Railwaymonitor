<template>
  <el-popover trigger="click" :width="340" @show="refresh">
    <template #reference><el-button>{{modeLabel(rule)}}</el-button></template>
    <p>{{rule ? ruleSummary(rule) : '暂未取得此机位的规则'}}</p>
  </el-popover>
</template>
<script setup lang="ts">
import {ref,watch,onBeforeUnmount} from 'vue'
import type {Camera} from '@/types/camera'
import {effectiveRiskRule,type RiskRule} from '@/api/riskRules'
import {modeLabel,ruleSummary} from '@/utils/ruleSummary'
const props=defineProps<{camera:Camera;session?:string}>()
const rule=ref<RiskRule>()
let generation=0
async function refresh(){
  const token=++generation
  try{const current=await effectiveRiskRule(props.camera.id);if(token===generation)rule.value=current ?? undefined}
  catch{if(token===generation)rule.value=undefined}
}
watch(()=>[props.camera.id,props.session],()=>{rule.value=props.camera.riskRule;void refresh()},{immediate:true})
onBeforeUnmount(()=>generation++)
</script>
