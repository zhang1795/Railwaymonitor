import request from './request'
export interface FrameObject {bbox:[number,number,number,number];classId:number;className:string;label:string;confidence:number;trackId:string|null}
export interface FrameTrail {trackId:string;points:[number,number][]}
export interface FrameResult {frameSeq:number;sourceFrameSeq:number;observedAt:string;processedAt:string;quality:'DECODE_CHECKED'|'UNVERIFIED';objects:FrameObject[];totalObjects:number;truncated:boolean;trails?:FrameTrail[]}
export interface DetectionFrame extends FrameResult {version:number;cameraId:string;sessionId:string;generation:number;modelSha256:string;width:number;height:number;sourceWidth:number;sourceHeight:number;jpeg:string;timeSource:string}
export interface LiveFrameResponse {state:'FRESH'|'DISABLED'|'WAITING'|'EXPIRED'|'SOURCE_ERROR';serverTime:string;observedAgeMs?:number;unchanged?:boolean;frame?:DetectionFrame}
export interface AnalysisManifest {version:number;cameraId:string;sessionId:string;modelSha256:string;width:number;height:number;durationMs:number;maxSampleFps:number;frameCount:number;droppedSamples:number;frames:(FrameResult & {offsetMs:number})[]}
export const getDetectionFrame=(camera:number,after=0,session='')=>request.get<LiveFrameResponse>(`/monitoring/${camera}/frame`,{params:{after,session},silent:true} as any)
export const getAnalysis=(url:string)=>request.get<AnalysisManifest>(url.startsWith('/api/')?url.slice(4):url)
