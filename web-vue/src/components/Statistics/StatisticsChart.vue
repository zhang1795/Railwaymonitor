<!-- 统计图表组件 -->
<template>
  <el-card shadow="hover" :class="{ 'statistics-chart': true, 'is-loading': loading }">
    <template #header>
      <div class="card-header">
        <span>{{ title }}</span>
        <div class="header-right">
          <slot name="header-right"></slot>
          <el-icon v-if="icon"><component :is="icon" /></el-icon>
        </div>
      </div>
    </template>
    <div ref="chartRef" :style="{ height: height + 'px' }"></div>
    <div v-if="loading" class="loading-mask">
      <el-icon class="loading-icon"><Loading /></el-icon>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { Loading } from '@element-plus/icons-vue'

interface Props {
  title: string
  icon?: string
  height?: number
  loading?: boolean
  options: EChartsOption
}

const props = withDefaults(defineProps<Props>(), {
  height: 400,
  loading: false
})

const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null

// 初始化图表
const initChart = () => {
  if (!chartRef.value) return

  // 销毁旧的图表实例
  if (chart) {
    chart.dispose()
  }

  // 创建新的图表实例
  chart = echarts.init(chartRef.value)
  chart.setOption(props.options)

  // 监听窗口大小变化
  window.addEventListener('resize', handleResize)
}

// 处理窗口大小变化
const handleResize = () => {
  if (chart) {
    chart.resize()
  }
}

// 监听 options 变化
watch(
  () => props.options,
  (newOptions) => {
    if (chart) {
      chart.setOption(newOptions)
    }
  },
  { deep: true }
)

// 组件挂载时初始化图表
onMounted(() => {
  initChart()
})

// 组件卸载前清理事件监听
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
    chart = null
  }
})
</script>

<style scoped>
.statistics-chart {
  position: relative;
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
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