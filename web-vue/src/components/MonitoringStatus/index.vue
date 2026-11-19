<template>
  <div class="monitoring-status">
    <el-tag :type="healthy && row?.state === 'RUNNING' && label === '检测中' ? 'success' : 'info'">{{ label }}</el-tag>
    <small>{{ row ? (row.enabled ? '配置：已启用' : '配置：已停用') : healthy ? '配置：未启用' : '配置：待确认' }} · 最后报告：{{ reportAt }}</small>
    <small v-if="row?.error" class="failure">{{ row.error }}</small>
    <small v-if="row?.metrics">有效检测 {{ row.metrics.effectiveFps ?? '-' }} 帧/秒 · 处理 P95 {{ row.metrics.processingP95Ms ?? '-' }} ms · 跳过帧 {{row.metrics.skippedFrames ?? '-'}}<br/>解码接收后帧龄 {{row.metrics.frameAgeMs ?? '-'}} ms（不含摄像机及网络前段延迟）</small>
    <small v-if="row?.metrics?.sourceQuality==='DECODE_CHECKED'">源帧：解码检查通过 · 本会话丢弃/拦截 {{row.metrics.decodeErrors ?? 0}} 次解码异常</small>
    <small v-else-if="row?.metrics?.sourceQuality==='CORRUPT'" class="failure">源画面解码损坏，本次推理已中断并等待恢复；不能据此判断目标消失。</small>
    <small v-else-if="row?.metrics?.sourceQuality==='UNAVAILABLE'" class="failure">视频源不可用，正在等待恢复。</small>
    <small v-if="row?.metrics?.recordingState==='BUDGET_EXHAUSTED' || row?.metrics?.recordingState==='ERROR'" class="failure">本地检测片段记录失败或空间不足；关键事件继续传输，请检查证据存储。</small>
    <small v-if="row?.metrics?.sourceRecordingState">源录像：{{recordingLabel(row.metrics.sourceRecordingState)}} · 待登记 {{row.metrics.recordingPending ?? 0}} · 登记失败 {{row.metrics.recordingFailed ?? 0}}</small>
    <small v-if="['ERROR','BUDGET_EXHAUSTED','NOT_CONFIGURED'].includes(row?.metrics?.sourceRecordingState || '') || row?.metrics?.recordingFailed" class="failure">源录像异常，请检查存储与证据服务；关键告警继续传输。</small>
    <small v-if="row?.metrics?.analysisRecordingState">检测采样留存：{{analysisLabel(row.metrics.analysisRecordingState)}} · 写入丢弃 {{row.metrics.analysisDroppedSamples ?? 0}} 帧</small>
    <small v-if="['ERROR','BUDGET_EXHAUSTED'].includes(row?.metrics?.analysisRecordingState || '') || row?.metrics?.liveResultState==='ERROR'" class="failure">检测画面传递或采样录像异常，请检查服务与存储；关键告警使用独立队列。</small>
  </div>
</template>
<script setup lang="ts">
import type { MonitoringState } from '@/api/monitoring'
defineProps<{ row?:MonitoringState; healthy:boolean; label:string; reportAt:string }>()
const recordingLabel=(state:string)=>({RECORDING:'录制进程运行',STARTING:'启动中',STOPPED:'已停止',ERROR:'录制异常',BUDGET_EXHAUSTED:'空间不足',NOT_CONFIGURED:'未配置',DISABLED:'已停用'}[state] || '未知')
const analysisLabel=(state:string)=>({WAITING:'等待目标窗口',RECORDING:'录制中',ERROR:'写入异常',BUDGET_EXHAUSTED:'空间不足'}[state] || '未知')
</script>
<style scoped>
.monitoring-status { display:flex; flex-direction:column; align-items:flex-start; gap:4px; }
small { color:var(--el-text-color-secondary); white-space:normal; }
.failure { color:var(--el-color-danger); overflow-wrap:anywhere; }
</style>
