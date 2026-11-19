// 异常事件
export interface AbnormalEvent {
  version: number
  manualOverride?:boolean
  risk?: {kind:string;state:string;risk_level?:number;risk_since?:string;missing_since?:string;last_observed?:string;association?:string}
  unreadNoticeIds?: string[]
  type?: string
  detectionState?: string
  detectedType?: string
  confidence?: number
  firstSeen?: string
  lastSeen?: string
  id: number
  cameraId: number
  cameraName?: string
  eventTime: string
  location: string
  level: number
  status: number
  imageUrl?: string
  description?: string
  handlerId?: number
  handlerName?: string
  handleTime?: string
  handleResult?: string
  createTime?: string
  updateTime?: string
}

// 异常等级
export enum AbnormalLevel {
  LEVEL1 = 1, // 轻微
  LEVEL2 = 2, // 一般
  LEVEL3 = 3, // 严重
  LEVEL4 = 4, // 特别严重
  LEVEL5 = 5, // 灾难级
}

// 处理状态
export enum AbnormalStatus {
  PENDING = 0,   // 未处理
  PROCESSING = 1, // 处理中
  HANDLED = 2,   // 已处理
}

// 异常事件列表查询参数
export interface AbnormalEventQueryParams {
  unreadOnly?: boolean
  current: number
  size: number
  cameraId?: number
  location?: string
  level?: number
  status?: number
  handlerId?: number
  startTime?: string
  endTime?: string
}

// 异常事件列表响应
export interface AbnormalEventListResult {
  records: AbnormalEvent[]
  total: number
  size: number
  current: number
}

// 创建异常事件参数
export interface AbnormalEventCreateParams {
  cameraId: number
  eventTime: string
  location: string
  level: number
  status?: number  // 0: 待处理, 1: 处理中, 2: 稍后处理
  imageUrl?: string
  description?: string
  type: string; 
}

// 处理异常事件参数
export interface AbnormalEventHandleParams {
  version: number
  id: number
  handlerId: number
  handleResult: string
}
