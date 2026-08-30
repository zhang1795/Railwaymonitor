<!-- 异常事件统计页面 -->
<template>
  <div class="Abnormal-event-container">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>异常事件统计</span>
              <el-button type="primary" @click="refreshData">刷新数据</el-button>
            </div>
          </template>
          <el-row v-loading="loading" :gutter="20">
            <el-col :span="8">
              <div ref="levelChart" class="chart"></div>
            </el-col>
            <el-col :span="8">
              <div ref="locationChart" class="chart"></div>
            </el-col>
            <el-col :span="8">
              <div ref="typeChart" class="chart"></div>
            </el-col>
          </el-row>
          <el-row :gutter="20" class="mt-4">
            <el-col :span="24">
              <div ref="trendChart" class="chart"></div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { EChartsType } from 'echarts'
import { getAbnormalEventStatistics } from '@/api/statistics'
import { ElMessage } from 'element-plus'

// 图表实例
const levelChart = ref<HTMLElement>()
const locationChart = ref<HTMLElement>()
const trendChart = ref<HTMLElement>()
const typeChart = ref<HTMLElement>()

let levelChartInstance: EChartsType | null = null
let locationChartInstance: EChartsType | null = null
let trendChartInstance: EChartsType | null = null
let typeChartInstance: EChartsType | null = null

// 加载状态
const loading = ref(false)

// 初始化异常等级分布图表
const initLevelChart = (data: any) => {
  if (!levelChart.value) return
  levelChartInstance = echarts.init(levelChart.value)
  const option = {
    title: {
      text: '异常等级分布',
      left: 'center'
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [
      {
        name: '异常等级',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: '20',
            fontWeight: 'bold'
          }
        },
        labelLine: {
          show: false
        },
        data: data?.typeDistribution?.map((item: any) => {
          let name = '未知'
          let color = '#909399' // 默认颜色
          
          switch (item.level) {
            case 0:
              name = '无异常'
              color = '#909399' // info
              break
            case 1:
              name = '可疑异常'
              color = '#409EFF' // primary
              break
            case 2:
              name = '轻微异常'
              color = '#67C23A' // success
              break
            case 3:
              name = '中等异常'
              color = '#E6A23C' // warning
              break
            case 4:
              name = '严重异常'
              color = '#F56C6C' // danger
              break
            case 5:
              name = '特别严重'
              color = '#FF0000' // danger
              break
          }
          
          return {
            name,
            value: item.count,
            itemStyle: { color }
          }
        }) || []
      }
    ]
  }
  levelChartInstance.setOption(option)
}

// 初始化异常位置分布图表
const initLocationChart = (data: any) => {
  if (!locationChart.value) return
  locationChartInstance = echarts.init(locationChart.value)
  const option = {
    title: {
      text: '异常位置分布',
      left: 'center'
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [
      {
        name: '异常位置',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: '20',
            fontWeight: 'bold'
          }
        },
        labelLine: {
          show: false
        },
        data: data?.locationHeatmap?.map((item: any, index: number) => {
          // 使用预定义的颜色数组来区分不同位置
          const colors = [
            '#409EFF', // 蓝色
            '#67C23A', // 绿色
            '#E6A23C', // 橙色
            '#F56C6C', // 红色
            '#909399', // 灰色
            '#8E44AD', // 紫色
            '#2ECC71', // 翠绿
            '#F1C40F', // 黄色
            '#E67E22', // 橘色
            '#16A085'  // 青色
          ]
          return {
            name: item.location,
            value: item.count,
            itemStyle: {
              color: colors[index % colors.length]
            }
          }
        }) || []
      }
    ]
  }
  locationChartInstance.setOption(option)
}

// 初始化异常类型分布
const initTypeChart = (data: any) => {
  if (!typeChart.value) return
  typeChartInstance = echarts.init(typeChart.value)
  
  // 预定义颜色数组
  const colors = [
    '#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399',
    '#8E44AD', '#2ECC71', '#F1C40F', '#E67E22', '#16A085',
    '#FF6B6B', '#4ECDC4', '#45B7D1'
  ]
  
  // 核心
  const chartData = data?.typeNameDistribution?.map((item: any, index: number) => {
    return {
      name: item.type, // 后端返回的中文类型（如“牛”“防撞设备”）
      value: item.count, // 该类型的事件数
      itemStyle: { 
        color: colors[index % colors.length] // 循环分配颜色
      }
    }
  }) || [] // 兜底：后端返回空时显示空数组，避免报错
  
  // 图表配置
  const option = {
    title: { text: '异常类型分布', left: 'center' },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)' 
    },
    legend: {
      orient: 'vertical', // 垂直排列
      left: 'left', // 图例在左侧
      textStyle: { fontSize: 12 }
    },
    series: [
      {
        name: '异常类型',
        type: 'pie',
        radius: ['40%', '70%'], // 内外半径
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2 // 边框样式
        },
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: '20',
            fontWeight: 'bold'
          }
        },
        labelLine: { show: false },
        data: chartData // 直接用 map 后的数组
      }
    ]
  }
  typeChartInstance.setOption(option)
}

// 初始化异常趋势图表
const initTrendChart = (data: any) => {
  if (!trendChart.value) return
  trendChartInstance = echarts.init(trendChart.value)
  const option = {
    title: {
      text: '异常趋势分析',
      left: 'center'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: ['异常事件数'],
      top: 30
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: data?.trendData?.map((item: any) => item.date) || []
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '异常事件数',
        type: 'line',
        data: data?.trendData?.map((item: any) => item.count) || [],
        smooth: true,
        itemStyle: {
          color: '#F56C6C'
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {
              offset: 0,
              color: 'rgba(245, 108, 108, 0.3)'
            },
            {
              offset: 1,
              color: 'rgba(245, 108, 108, 0.1)'
            }
          ])
        }
      }
    ]
  }
  trendChartInstance.setOption(option)
}

// 获取数据并初始化图表
const initCharts = async () => {
  try {
    loading.value = true
    const data = await getAbnormalEventStatistics()
    console.log('异常事件统计数据:', data)
    initLevelChart(data)
    initLocationChart(data)
    initTypeChart(data)
    initTrendChart(data)
  } catch (error) {
    ElMessage.error('获取数据失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 刷新数据
const refreshData = () => {
  initCharts()
}

// 监听窗口大小变化
const handleResize = () => {
  levelChartInstance?.resize()
  locationChartInstance?.resize()
  typeChartInstance?.resize()
  trendChartInstance?.resize()
}

onMounted(() => {
  initCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  levelChartInstance?.dispose()
  locationChartInstance?.dispose()
  typeChartInstance?.dispose()
  trendChartInstance?.dispose()
})
</script>

<style scoped>
.Abnormal-event-container {
  padding: 20px;
}

.box-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart {
  height: 400px;
  width: 100%;
}

.mt-4 {
  margin-top: 20px;
}
</style> 