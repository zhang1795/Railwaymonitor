import dayjs from 'dayjs'
import { AbnormalStatus } from '@/types/Abnormal'


// 格式化日期时间
export function formatDateTime(date?: string) {
  if (!date) return '-'
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

// 格式化日期
export const formatDate = (date: string | number | Date) => {
  const d = new Date(date)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return year + '-' + month + '-' + day
}

// 格式化文件大小
export const formatFileSize = (size: number) => {
  if (size < 1024) {
    return size + ' B'
  } else if (size < 1024 * 1024) {
    return (size / 1024).toFixed(2) + ' KB'
  } else if (size < 1024 * 1024 * 1024) {
    return (size / (1024 * 1024)).toFixed(2) + ' MB'
  } else {
    return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
  }
}

// 格式化异常等级
export const formatAbnormalLevel = (level: number) => {
  const levelMap: Record<number, string> = {
    0: '未检测到',
    1: '可疑异常',
    2: '轻微异常',
    3: '中等异常',
    4: '严重异常',
    5: '特别严重'
  }
  return levelMap[level] || '未知等级'
}




// 格式化处理状态
export function formatStatus(status?: number) {
  switch (status) {
    case AbnormalStatus.PENDING:
      return '未处理'
    case AbnormalStatus.PROCESSING:
      return '处理中'
    case AbnormalStatus.HANDLED:
      return '已处理'
    default:
      return '-'
  }
}

// 格式化用户角色
export const formatRole = (role: number) => {
  const roles = ['普通用户', '管理员']
  return roles[role] || '未知'
}

// 格式化设备状态
export const formatDeviceStatus = (status: number) => {
  const statusMap: Record<number, string> = {
    0: '离线',
    1: '在线',
    2: '故障',
    3: '未验证'
  }
  return statusMap[status] || '未知状态'
}

