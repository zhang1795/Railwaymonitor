import type {AnalysisManifest,FrameTrail} from '@/api/detectionFrames'

// mediaTime is the timestamp of the frame actually presented by the browser,
// rather than a timer reading or the current frame of an independent stream.
export function sampleIndex(manifest:AnalysisManifest,mediaTime:number):number {
  if(!Number.isFinite(mediaTime) || mediaTime<0 || mediaTime*1000>=manifest.durationMs)return -1
  let low=0,high=manifest.frames.length-1,index=-1
  while(low<=high){const mid=(low+high)>>1;if(manifest.frames[mid].offsetMs<=mediaTime*1000+.5){index=mid;low=mid+1}else high=mid-1}
  return index
}
export function sampleTrails(manifest:AnalysisManifest,index:number):FrameTrail[] {
  if(index<0)return []
  const visible=new Set(manifest.frames[index].objects.map(object=>object.trackId).filter(Boolean)),trails=new Map<string,[number,number][]>()
  for(let i=Math.max(0,index-29);i<=index;i++){
    if(manifest.frames[index].offsetMs-manifest.frames[i].offsetMs>10000)continue
    for(const object of manifest.frames[i].objects){if(!object.trackId || !visible.has(object.trackId))continue;const [x1,y1,x2,y2]=object.bbox;const points=trails.get(object.trackId)||[];points.push([(x1+x2)/2,(y1+y2)/2]);trails.set(object.trackId,points)}
  }
  return Array.from(trails,([trackId,points])=>({trackId,points}))
}
