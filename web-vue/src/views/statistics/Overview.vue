<!-- 统计概览页面 -->
<template>
  <div class="overview-container">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>统计概览</span>
              <el-button type="primary" @click="refreshData">刷新数据</el-button>
            </div>
          </template>
          <el-row v-loading="loading" :gutter="20">
            <!-- 趋势图区域 -->
            <el-col :span="24" class="mb-4">
              <el-card shadow="hover">
                <template #header>
                  <div class="card-header">
                    <span>本周事件趋势</span>
                  </div>
                </template>
                <div ref="trendChart" class="trend-chart" />
              </el-card>
            </el-col>
            <!-- 今日数据卡片 -->
            <el-col :span="24" class="mb-4">
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-card shadow="hover">
                    <template #header>
                      <div class="card-header">
                        <span>今日异常事件</span>
                        <el-icon><Warning /></el-icon>
                      </div>
                    </template>
                    <div class="card-value danger">{{ statistics.todayAbnormalEvents }}</div>
                  </el-card>
                </el-col>
                <el-col :span="12">
                  <el-card shadow="hover">
                    <template #header>
                      <div class="card-header">
                        <span>在线设备数</span>
                        <el-icon><Monitor /></el-icon>
                      </div>
                    </template>
                    <div class="card-value success">{{ statistics.onlineDevices }}</div>
                  </el-card>
                </el-col>
              </el-row>
            </el-col>
            <!-- 饼图区域 -->
            <el-col :span="16">
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-card shadow="hover">
                    <template #header>
                      <div class="card-header">
                        <span>今日事件统计</span>
                      </div>
                    </template>
                    <div ref="AbnormalEventChart" class="chart" />
                  </el-card>
                </el-col>
                <el-col :span="12">
                  <el-card shadow="hover">
                    <template #header>
                      <div class="card-header">
                        <span>设备状态统计</span>
                      </div>
                    </template>
                    <div ref="deviceStatusChart" class="chart" />
                  </el-card>
                </el-col>
               
              </el-row>
            </el-col>
            <!-- 近期警报列表 -->
            <el-col :span="8">
              <el-card shadow="hover" class="alarm-card">
                <template #header>
                  <div class="card-header">
                    <span>近期警报</span>
                    <el-icon><Bell /></el-icon>
                  </div>
                </template>
                <el-table :data="statistics.recentAlarms" stripe height="318">
                  <el-table-column prop="time" label="时间" width="160">
                    <template #default="{ row }">
                      {{ new Date(row.time).toLocaleString('zh-CN', { hour12: false }) }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="location" label="位置" min-width="200" />
                  <el-table-column prop="level" label="等级" width="120" align="center">
                    <template #default="{ row }">
                      <el-tag :type="getAbnormalLevelType(row.level)">
                        {{ formatAbnormalLevel(row.level) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>
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
import {
  Warning,
  List,
  ChatDotRound,
  Monitor,
  Bell
} from '@element-plus/icons-vue'
import { getSystemOverview } from '@/api/statistics'
import type { SystemOverviewVO } from '@/types/statistics'
import { ElMessage } from 'element-plus'
import { formatDateTime, formatAbnormalLevel } from '@/utils/format'

// 图表实例
const AbnormalEventChart = ref<HTMLElement>()
const deviceStatusChart = ref<HTMLElement>()
const trendChart = ref<HTMLElement>()

let AbnormalEventChartInstance: EChartsType | null = null
let deviceStatusChartInstance: EChartsType | null = null
let trendChartInstance: EChartsType | null = null

// 加载状态
const loading = ref(false)

// 统计数据
const statistics = ref<SystemOverviewVO>({
  todayAbnormalEvents: 0,


  onlineDevices: 0,
  runningDays: 0,
  weeklyTrend: [],
  deviceStatus: [],
  recentAlarms: [],
  pendingItems: {
    AbnormalEvents: 0,

 
  },
 
})

// 获取异常等级类型
const getAbnormalLevelType = (level: number | undefined | null): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  switch (level) {
    case 0:
      return 'info'    // 无异常
    case 1:
      return 'primary' // 可疑异常
    case 2:
      return 'success' // 轻微异常
    case 3:
      return 'warning' // 中等异常
    case 4:
      return 'danger'  // 严重异常
    case 5:
      return 'danger'  // 特别严重
    default:
      return 'info'
  }
}

// 初始化异常事件图表
const initAbnormalEventChart = () => {
  if (!AbnormalEventChart.value) return
  AbnormalEventChartInstance = echarts.init(AbnormalEventChart.value)
  const option = {
    title: {
      text: '今日事件统计',
      left: 'center'
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c}起 ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [
      {
        name: '今日事件',
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
        data: [
          {
            name: '异常事件',
            value: statistics.value.todayAbnormalEvents,
            itemStyle: { color: '#F56C6C' }
          },
          
        ].filter(item => item.value > 0)
      }
    ]
  }
  AbnormalEventChartInstance.setOption(option)
}

// 初始化设备状态图表
const initDeviceStatusChart = () => {
  if (!deviceStatusChart.value) return
  deviceStatusChartInstance = echarts.init(deviceStatusChart.value)
  const option = {
    title: {
      text: '设备状态统计',
      left: 'center'
    },
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c}台'
    },
    legend: {
      orient: 'vertical',
      left: 'left'
    },
    series: [
      {
        name: '设备状态',
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
        data: statistics.value.deviceStatus.map(item => ({
          name: item.status === 1 ? '在线' : item.status === 0 ? '离线' : '故障',
          value: item.count,
          itemStyle: {
            color: item.status === 1 ? '#67C23A' : item.status === 0 ? '#E6A23C' : '#F56C6C'
          }
        }))
      }
    ]
  }
  deviceStatusChartInstance.setOption(option)
}



// 初始化异常趋势图表
const initTrendChart = () => {
  if (!trendChart.value) return
  trendChartInstance = echarts.init(trendChart.value)
  
  // 对趋势数据按时间从小到大排序
  const sortedTrend = [...statistics.value.weeklyTrend].sort((a, b) => {
    return new Date(a.date).getTime() - new Date(b.date).getTime()
  })
  
  const option = {
    title: {
      text: '本周事件趋势',
      left: 'center'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      // data: ['异常事件', '消防检查', '用户反馈'],
      data: ['异常事件'],
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
      data: sortedTrend.map(item => item.date)
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '异常事件',
        type: 'line',
        data: sortedTrend.map(item => item.AbnormalEvents),
        smooth: true,
        itemStyle: {
          color: '#F56C6C'
        }
      },
    ]
  }
  trendChartInstance.setOption(option)
}

// 获取数据并初始化图表
const initCharts = async () => {
  try {
    loading.value = true
    const data = await getSystemOverview()
    console.log('系统概览数据:', data)
    statistics.value = data
    initAbnormalEventChart()
    initDeviceStatusChart()
    initTrendChart()
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
  AbnormalEventChartInstance?.resize()
  deviceStatusChartInstance?.resize()
  trendChartInstance?.resize()
}

onMounted(() => {
  initCharts()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (deviceStatusChartInstance) {
    deviceStatusChartInstance.dispose()
  }

  if (trendChartInstance) {
    trendChartInstance.dispose()
  }
})
</script>

<style scoped>
.overview-container {
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
  height: 350px;
  width: 100%;
}

.trend-chart {
  height: 400px;
  width: 100%;
}

.alarm-card {
  height: 100%;
}

.mb-4 {
  margin-bottom: 16px;
}

.mt-4 {
  margin-top: 16px;
}

.card-value {
  font-size: 24px;
  font-weight: bold;
  text-align: center;
}

.danger {
  color: #F56C6C;
}

.success {
  color: #67C23A;
}

.charts {
  margin-top: 16px;
}

:deep(.el-table) {
  --el-table-header-bg-color: var(--el-fill-color-light);
  --el-table-row-hover-bg-color: var(--el-fill-color);
  margin: 8px 0;
}

:deep(.el-table th) {
  font-weight: bold;
  background-color: var(--el-fill-color-light);
}

:deep(.el-table td) {
  padding: 8px 0;
}
</style> 