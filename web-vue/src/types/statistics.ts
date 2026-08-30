// 统计数据接口
export interface StatisticsVO {
  // 异常事件等级分布
  AbnormalEventLevelCount: Record<number, number>
  // 异常事件处理状态分布
  AbnormalEventStatusCount: Record<number, number>
  // 异常事件趋势
  AbnormalEventTrend: Record<string, number>
  // 摄像头设备状态分布
  cameraStatusCount: Record<number, number>
  // 消防检查结果分布
  dangerousAreaTop5: Array<{
    location: string
    count: number
  }>
}

// 异常事件统计
export interface AbnormalEventStatisticsVO {
  // 总数统计
  total: number
  processing: number
  processed: number
  // 趋势数据
  trend: {
    date: string
    count: number
  }[]
  // 等级分布
  typeDistribution: {
    type: string
    count: number
  }[]
  // 热力图数据
  heatmap: {
    location: string
    count: number
  }[]
  // 类型分布
  abnormalTypeNameDistribution: {
    type: string 
    count: number 
  }[]
}

// 设备状态统计
export interface DeviceStatusStatisticsVO {
  // 总数统计
  totalCount: number
  onlineCount: number
  offlineCount: number
  faultCount: number
  // 状态分布
  statusDistribution: {
    status: number
    count: number
  }[]
  // 在线率趋势
  onlineRateTrend: {
    date: string
    rate: number | string
  }[]
  // 故障类型分布
  faultTypeDistribution: {
    type: string
    count: number
  }[]
}


// 系统概览数据
export interface SystemOverviewVO {
  // 今日数据
  todayAbnormalEvents: number
  onlineDevices: number
  
  // 系统运行天数
  runningDays: number
  
  // 本周事件趋势
  weeklyTrend: Array<{
    date: string
    AbnormalEvents: number
  }>
  
  // 设备状态分布
  deviceStatus: Array<{
    status: number
    count: number
  }>
  
  // 近期告警TOP5
  recentAlarms: Array<{
    id: number
    time: string
    location: string
    level: number
    type: string | null
    status: number
  }>
  
  // 待处理事项
  pendingItems: {
    AbnormalEvents: number
  }


} 
