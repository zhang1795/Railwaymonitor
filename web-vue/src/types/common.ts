// 分页查询参数
export interface PageQuery {
  current: number
  size: number
  startTime?: string
  endTime?: string
  [key: string]: any
}

// 分页结果
export interface PageResult<T> {
  records: T[]
  total: number
  size: number
  current: number
  pages: number
}

// 通用响应结果
export interface Result<T> {
  code: number
  message: string
  data: T
} 