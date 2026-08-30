<!-- 设备状态统计页面 -->
<template>
  <div class="device-status-container">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>设备状态统计</span>
            </div>
          </template>
          
          <div class="device-status-statistics">
            <!-- 数据总览 -->
            <el-row :gutter="20" class="mb-4">
              <el-col :span="6">
                <el-card shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>总设备数</span>
                      <el-icon><DataLine /></el-icon>
                    </div>
                  </template>
                  <div class="card-value">{{ statistics.total }}</div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>在线设备</span>
                      <el-icon><Monitor /></el-icon>
                    </div>
                  </template>
                  <div class="card-value success">{{ statistics.online }}</div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>离线设备</span>
                      <el-icon><CloseBold /></el-icon>
                    </div>
                  </template>
                  <div class="card-value warning">{{ statistics.offline }}</div>
                </el-card>
              </el-col>
              <el-col :span="6">
                <el-card shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>故障设备</span>
                      <el-icon><Warning /></el-icon>
                    </div>
                  </template>
                  <div class="card-value danger">{{ statistics.fault }}</div>
                </el-card>
              </el-col>
            </el-row>

            <!-- 状态分布和在线率趋势 -->
            <el-row :gutter="20" class="mb-4">
              <el-col :span="12">
                <el-card shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>状态分布</span>
                      <el-icon><PieChart /></el-icon>
                    </div>
                  </template>
                  <div ref="statusChart" style="height: 400px"></div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>在线率趋势</span>
                      <el-icon><TrendCharts /></el-icon>
                    </div>
                  </template>
                  <div ref="onlineRateChart" style="height: 400px"></div>
                </el-card>
              </el-col>
            </el-row>

            <!-- 故障类型分布 -->
            <el-card shadow="hover">
              <template #header>
                <div class="card-header">
                  <span>故障类型分布</span>
                  <el-icon><WarningFilled /></el-icon>
                </div>
              </template>
              <div ref="faultTypeChart" style="height: 400px"></div>
            </el-card>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import {
  DataLine,
  Monitor,
  CloseBold,
  Warning,
  PieChart,
  TrendCharts,
  WarningFilled
} from '@element-plus/icons-vue'
import { getDeviceStatusStatistics } from '@/api/statistics'
import type { DeviceStatusStatisticsVO } from '@/types/statistics'
import { ElMessage } from 'element-plus'

interface DeviceStatusViewModel {
  total: number
  online: number
  offline: number
  fault: number
  statusDistribution: Array<{ status: string; count: number }>
  onlineRateTrend: Array<{ date: string; rate: number }>
  faultTypeDistribution: DeviceStatusStatisticsVO['faultTypeDistribution']
}

const statusChart = ref<HTMLElement>()
const onlineRateChart = ref<HTMLElement>()
const faultTypeChart = ref<HTMLElement>()
const statistics = ref<DeviceStatusViewModel>({
  total: 0,
  online: 0,
  offline: 0,
  fault: 0,
  statusDistribution: [],
  onlineRateTrend: [],
  faultTypeDistribution: []
})

// 初始化状态分布图表
const initStatusChart = () => {
  if (!statusChart.value) return

  const chart = echarts.init(statusChart.value)
  const option: EChartsOption = {
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
        name: '设备状态',
        type: 'pie',
        radius: ['50%', '70%'],
        avoidLabelOverlap: false,
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: '16',
            fontWeight: 'bold'
          }
        },
        labelLine: {
          show: false
        },
        data: statistics.value.statusDistribution.map(item => ({
          name: item.status,
          value: item.count,
          itemStyle: {
            color: getStatusColor(item.status)
          }
        }))
      }
    ]
  }
  chart.setOption(option)

  window.addEventListener('resize', () => {
    chart.resize()
  })
}

// 初始化在线率趋势图表
const initOnlineRateChart = () => {
  if (!onlineRateChart.value) return

  const chart = echarts.init(onlineRateChart.value)
  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      formatter: '{b}<br/>{a}: {c}%'
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: statistics.value.onlineRateTrend.map(item => item.date)
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: {
        formatter: '{value}%'
      }
    },
    series: [
      {
        name: '在线率',
        type: 'line',
        smooth: true,
        data: statistics.value.onlineRateTrend.map(item => item.rate),
        itemStyle: {
          color: '#67C23A'
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {
              offset: 0,
              color: 'rgba(103, 194, 58, 0.3)'
            },
            {
              offset: 1,
              color: 'rgba(103, 194, 58, 0.1)'
            }
          ])
        }
      }
    ]
  }
  chart.setOption(option)

  window.addEventListener('resize', () => {
    chart.resize()
  })
}

// 初始化故障类型分布图表
const initFaultTypeChart = () => {
  if (!faultTypeChart.value) return

  const chart = echarts.init(faultTypeChart.value)
  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: statistics.value.faultTypeDistribution.map(item => item.type)
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '故障数量',
        type: 'bar',
        data: statistics.value.faultTypeDistribution.map(item => ({
          value: item.count,
          itemStyle: {
            color: '#F56C6C'
          }
        })),
        label: {
          show: true,
          position: 'top'
        }
      }
    ]
  }
  chart.setOption(option)

  window.addEventListener('resize', () => {
    chart.resize()
  })
}

// 获取状态对应的颜色
const getStatusColor = (status: string) => {
  switch (status) {
    case '在线':
      return '#67C23A'
    case '离线':
      return '#E6A23C'
    case '故障':
      return '#F56C6C'
    default:
      return '#909399'
  }
}

// 获取数据
const fetchData = async () => {
  try {
    const res = await getDeviceStatusStatistics()
    console.log('后端返回的数据:', res)

    // 映射后端返回的字段名称
    statistics.value = {
      total: res.totalCount,
      online: res.onlineCount,
      offline: res.offlineCount,
      fault: res.faultCount,
      statusDistribution: res.statusDistribution.map(item => ({
        status: getStatusText(item.status),
        count: item.count
      })),
      onlineRateTrend: res.onlineRateTrend.map(item => ({
        date: item.date,
        rate: Number(item.rate)
      })),
      faultTypeDistribution: res.faultTypeDistribution
    }

    // 初始化图表
    nextTick(() => {
      initStatusChart()
      initOnlineRateChart()
      initFaultTypeChart()
    })
  } catch (error) {
    console.error('获取设备状态统计数据失败:', error)
    ElMessage.error('获取统计数据失败')
  }
}

// 获取状态文本
const getStatusText = (status: number) => {
  switch (status) {
    case 1:
      return '在线'
    case 0:
      return '离线'
    case 2:
      return '故障'
    default:
      return '未知'
  }
}

// 页面加载时获取数据
onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.device-status-container {
  padding: 20px;
}

.mb-4 {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-value {
  font-size: 24px;
  font-weight: bold;
  text-align: center;
}

.success {
  color: #67C23A;
}

.warning {
  color: #E6A23C;
}

.danger {
  color: #F56C6C;
}
</style> 
