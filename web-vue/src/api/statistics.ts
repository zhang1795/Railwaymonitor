import request from './request'
import type {
  AbnormalEventStatisticsVO,
  DeviceStatusStatisticsVO,
  SystemOverviewVO
} from '@/types/statistics'

// 获取异常事件统计数据
export const getAbnormalEventStatistics = (params?: { startTime?: string; endTime?: string }) => {
  return request.get<AbnormalEventStatisticsVO>('/statistics/Abnormal-event', { params })
}

// 获取设备状态统计数据
export const getDeviceStatusStatistics = () => {
  return request.get<DeviceStatusStatisticsVO>('/statistics/device-status')
}




// 获取系统概览统计数据
export const getSystemOverview = () => {
  return request.get<SystemOverviewVO>('/statistics/overview')
} 