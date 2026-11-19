import request from './request'
import type {
  AbnormalEvent,
  AbnormalEventQueryParams,
  AbnormalEventListResult,
  AbnormalEventCreateParams,
  AbnormalEventHandleParams,
} from '@/types/Abnormal'
import type { PageQuery, PageResult } from '@/types/common'
export interface AlarmInsight {
  recordings?:import('./recordings').RecordingClip[]
  notificationConfiguration?:{smsConfigured:boolean;webhookConfigured:boolean;inAppEnabled:boolean;smsMinLevel:number}
  deliveries?:Array<{id:string;channel:string;status:string;attempts:number;error:string;updated_at:string}>
  risk: Array<{kind:string;state:string;risk_level:number;risk_since:string;last_observed:string;association:string;policy:string;session_policy?:string}>
  sources:Array<{source_key:string;session_id:string;state:string;first_sequence:number;last_sequence:number|null}>
  transitions:Array<{from_state:string|null;to_state:string;reason:string;observed_at:string}>
  handling:Array<{user_id:number;action:string;before_status:number;after_status:number;result:string|null;created_at:string}>
  notices:Array<{kind:string;created_at:string}>
  evidence:{configured:boolean;images:Array<{id:string;capturedAt:string;state:string;url:string;bytes:number;sha256:string}>;videoState:string}
  evidenceWorker:Array<{pending_events:number;skipped:number;error:string;reported_at:string}>
}
export const getAlarmInsight=(id:number|string)=>request.get<AlarmInsight>(`/Abnormal-event/${id}/insight`)

// 获取异常事件列表
export const getAbnormalEventList = (params: AbnormalEventQueryParams) => {
  return request.get<AbnormalEventListResult>('/Abnormal-event/page', { params })
}

// 获取异常事件详情
export const getAbnormalEventById = (id: number|string) => {
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
export const updateAbnormalEventStatus = (id: number, status: number, version: number, result?: string) => {
  return request.put<void>(`/Abnormal-event/${id}/status`, { status, version, result })
}
