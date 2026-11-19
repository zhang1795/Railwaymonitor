// 摄像头设备
export interface Camera {
  riskRule?: import('@/api/riskRules').RiskRule
  id: number
  name: string
  location: string
  longitude: number  // 新增字段
  latitude: number   // 新增字段
  ipAddress: string
  rtspUrl?: string
  status: number
  AbnormalDetected?: boolean
  streaming?: boolean
  createTime?: string
  updateTime?: string
}

// 摄像头状态
export enum CameraStatus {
  OFFLINE = 0,
  ONLINE = 1,
  FAULT = 2,
}

// 摄像头列表查询参数
export interface CameraQueryParams {
  current: number
  size: number
  name?: string
  location?: string
  ipAddress?: string
  status?: number
}

// 摄像头列表响应
export interface CameraListResult {
  records: Camera[]
  total: number
  size: number
  current: number
}

// 创建摄像头参数
export interface CameraCreateParams {
  name: string
  location: string
  ipAddress: string
  rtspUrl?: string
  longitude: number  // 新增字段
  latitude: number   // 新增字段
}

// 更新摄像头参数
export interface CameraUpdateParams {
  id: number
  name: string
  location: string
  ipAddress: string
  rtspUrl?: string
  status?: number
  longitude?: number  // 新增字段
  latitude?: number   // 新增字段
} 