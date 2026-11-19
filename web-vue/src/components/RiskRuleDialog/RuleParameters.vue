<template>
  <el-form-item label="关注类别">
    <el-select v-model="value.classes" multiple aria-label="关注类别">
      <el-option v-for="(name,id) in riskClasses" :key="id" :value="id" :label="name" />
    </el-select>
  </el-form-item>
  <el-form-item label="最低置信度"><el-input-number v-model="value.confidence" :min="0" :max="1" :step="0.05" /></el-form-item>
  <el-form-item label="持续符合（秒）"><el-input-number v-model="value.dwellSeconds" :min="0" :max="60" /></el-form-item>
  <el-form-item label="短暂丢失（秒）"><el-input-number v-model="value.graceSeconds" :min="1" :max="30" /></el-form-item>
  <el-form-item label="持续提醒（秒）"><el-input-number v-model="value.reminderSeconds" :min="10" :max="3600" /></el-form-item>
  <el-form-item label="风险等级"><el-input-number v-model="value.level" :min="1" :max="5" /></el-form-item>
  <el-form-item label="持续升级（秒）"><el-input-number v-model="value.escalateSeconds" :min="0" :max="86400" /><small>0 表示关闭自动升级</small></el-form-item>
</template>
<script setup lang="ts">
import {riskClasses, type RiskParameters} from '@/api/riskRules'
defineProps<{value: RiskParameters}>()
</script>
