<!-- 统计卡片组件 -->
<template>
  <el-card shadow="hover" :class="{ 'statistics-card': true, 'is-loading': loading }">
    <template #header>
      <div class="card-header">
        <span>{{ title }}</span>
        <el-icon v-if="icon"><component :is="icon" /></el-icon>
      </div>
    </template>
    <div class="card-content">
      <div :class="['card-value', type]">
        <span class="value">{{ value }}</span>
        <span v-if="unit" class="unit">{{ unit }}</span>
      </div>
      <div v-if="subTitle" class="card-subtitle">{{ subTitle }}</div>
      <div v-if="trend" class="card-trend">
        <span :class="['trend-value', trend.type]">
          <el-icon v-if="trend.type === 'up'"><ArrowUp /></el-icon>
          <el-icon v-if="trend.type === 'down'"><ArrowDown /></el-icon>
          {{ trend.value }}{{ trend.unit }}
        </span>
        <span class="trend-text">{{ trend.text }}</span>
      </div>
    </div>
    <div v-if="loading" class="loading-mask">
      <el-icon class="loading-icon"><Loading /></el-icon>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ArrowUp, ArrowDown, Loading } from '@element-plus/icons-vue'

interface TrendInfo {
  type: 'up' | 'down'
  value: string | number
  unit?: string
  text: string
}

interface Props {
  title: string
  value: string | number
  unit?: string
  subTitle?: string
  icon?: string
  type?: 'default' | 'success' | 'warning' | 'danger' | 'info'
  trend?: TrendInfo
  loading?: boolean
}

withDefaults(defineProps<Props>(), {
  type: 'default',
  loading: false
})
</script>

<style scoped>
.statistics-card {
  position: relative;
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.card-value {
  font-size: 24px;
  font-weight: bold;
  text-align: center;
}

.card-value.default {
  color: #409EFF;
}

.card-value.success {
  color: #67C23A;
}

.card-value.warning {
  color: #E6A23C;
}

.card-value.danger {
  color: #F56C6C;
}

.card-value.info {
  color: #909399;
}

.value {
  margin-right: 4px;
}

.unit {
  font-size: 14px;
  color: #909399;
}

.card-subtitle {
  font-size: 14px;
  color: #909399;
}

.card-trend {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.trend-value {
  display: flex;
  align-items: center;
  gap: 2px;
}

.trend-value.up {
  color: #67C23A;
}

.trend-value.down {
  color: #F56C6C;
}

.trend-text {
  color: #909399;
}

.loading-mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.8);
  display: flex;
  justify-content: center;
  align-items: center;
}

.loading-icon {
  font-size: 24px;
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style> 