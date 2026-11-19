import request from './request'
export interface RecordingClip { id:string;camera_id:number;started_at:string;ended_at:string;bytes:number;sha256:string;state:'READY'|'EXPIRED'|'UNAVAILABLE';url:string;kind:'FULL_SOURCE'|'DETECTION_SAMPLES';clockSource:string;analysisUrl?:string;frameCount?:number;modelSha256?:string }
export interface RecordingPage {items:RecordingClip[];next:{beforeEnd:string;beforeId:string}|null;retentionDays:number;budgetBytes:number}
export const getRecordings=(camera:number,params:{startTime:string;endTime:string;beforeEnd?:string;beforeId?:string})=>request.get<RecordingPage>(`/camera/${camera}/recordings`,{params})
