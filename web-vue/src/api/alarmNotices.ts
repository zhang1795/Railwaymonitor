import request from './request'
export interface AlarmNotice { id:string; noticeId?:string; kind?:string; noticeTime?:string; cameraId:string; location:string; type:string|null; eventTime:string }
export interface AlarmNoticePage { unreadCount:number; items:AlarmNotice[]; nextBeforeId:string|null }
export const getAlarmNotices = () => request.get<AlarmNoticePage>('/alarm-notices', {silent:true} as any)
export const readAlarmNotices = (ids:string[]) => request.post('/alarm-notices/read',{ids})
export const readNoticeIds = (noticeIds:string[]) => request.post('/alarm-notices/read',{noticeIds})
