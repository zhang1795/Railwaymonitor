import request from './request'
import type {
  AbnormalEvent,
  AbnormalEventQueryParams,
  AbnormalEventListResult,
  AbnormalEventCreateParams,
  AbnormalEventHandleParams,
} from '@/types/Abnormal'
import type { PageQuery, PageResult } from '@/types/common'

// 获取异常事件列表
export const getAbnormalEventList = (params: AbnormalEventQueryParams) => {
  return request.get<AbnormalEventListResult>('/Abnormal-event/page', { params })
}

// 获取异常事件详情
export const getAbnormalEventById = (id: number) => {
  return request.get<AbnormalEvent>(`/Abnormal-event/${id}`)
}

// 创建异常事件
export const createAbnormalEvent = (data: AbnormalEventCreateParams) => {
  return request.post<number>('/Abnormal-event', data)
}

// 更新异常事件
export const updateAbnormalEvent = (data: Partial<AbnormalEvent>) => {
  return request.put<void>(`/Abnormal-event/${data.id}`, data)
}

// 删除异常事件
export const deleteAbnormalEvent = (id: number) => {
  return request.delete<void>(`/Abnormal-event/${id}`)
}

// 批量删除异常事件
export const batchDeleteAbnormalEvents = (ids: number[]) => {
  return request.delete<void>('/Abnormal-event/batch', { data: ids })
}

// 处理异常事件
export const handleAbnormalEvent = (data: AbnormalEventHandleParams) => {
  return request.post<void>(`/Abnormal-event/${data.id}/handle`, data)
}

// 更新异常事件状态
export const updateAbnormalEventStatus = (id: number, status: number) => {
  return request.put<void>(`/Abnormal-event/${id}/status`, { status })
} 