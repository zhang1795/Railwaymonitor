import {formatDateTime} from '@/utils/format'
export const eventKind=(kind?:string)=>({RISK:'区域风险告警',OBSERVATION:'待核验观察',LEGACY:'历史记录'} as Record<string,string>)[kind || 'LEGACY'] || '待核验'
export function riskLabel(state?:string,kind?:string){
  const risk=kind==='RISK'
  const labels:Record<string,string>={PRESENT:risk?'风险持续':'目标持续',MISSING:'暂未见目标，等待确认',CLEARED:risk?'已观测确认解除':'观察结束',INTERRUPTED:'监测中断，当前状态未知',UNKNOWN:'状态未验证'}
  return labels[state || 'UNKNOWN'] || '状态未知'
}
export const detectionLabel=(state?:string)=>({ACTIVE:'当前被观测',MISSING:'暂未匹配',ENDED:'该次观测结束',INTERRUPTED:'观测中断'} as Record<string,string>)[state || ''] || '历史状态未知'
export const associationLabel=(state?:string)=>({NEW:'首次建立',RELINKED:'按时间和位置续接，物理身份仍需核验',AMBIGUOUS_NEW:'存在多个关联候选，单独建事件',LEGACY_TRACK:'旧协议来源',LATE_SNAPSHOT_REVIEW:'前序观测不完整，保留待核验记录'} as Record<string,string>)[state || ''] || '没有可靠关联信息'
export const noticeLabel=(kind:string)=>({FIRST:'首次发现',ONGOING:'持续存在，请复核',ESCALATION:'风险升级'} as Record<string,string>)[kind] || '事件提醒'
export const deliveryLabel=(state:string)=>({PENDING:'排队中',RETRY:'等待重试',SENDING:'正在请求服务商',ACCEPTED:'服务商已受理，待回执',DELIVERED:'运营商回执已送达',ACKNOWLEDGED:'接收服务已确认',UNKNOWN:'发送结果未知，请核查',FAILED:'发送失败',RECEIPT_TIMEOUT:'回执超时，需核查',NOT_CONFIGURED:'渠道未配置'} as Record<string,string>)[state] || '状态未知'
export const transitionReason=(reason:string)=>({first_observation:'首次有效观测',qualified_observation:'符合规则的观测',temporary_loss:'短暂丢失',confirmed_absence:'持续有效观测确认目标消失',outside_rule_region:'区域规则已不再满足',monitoring_interrupted:'监测已中断',worker_interrupted:'工作节点中断',disabled:'管理员停用检测',legacy_track_ended_unverified:'旧轨迹结束，未验证业务风险解除',other_linked_source_present:'其他关联轨迹仍有有效观测'} as Record<string,string>)[reason] || '状态变化，请核查来源'
export function utcTime(value?:string){
  if(!value)return '-'
  return formatDateTime(/[zZ]$|[+-]\d\d:\d\d$/.test(value)?value:value.replace(' ','T')+'Z')
}
export function riskAt(state?:string,kind?:string,observed?:string,now=Date.now()){
  const parsed=observed?Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(observed)?observed:observed.replace(' ','T')+'Z'):NaN
  if((state==='PRESENT' || state==='MISSING') && (!Number.isFinite(parsed) || now-parsed>35000 || parsed-now>30000))return '观测已过期，当前风险状态未知'
  return riskLabel(state,kind)
}
