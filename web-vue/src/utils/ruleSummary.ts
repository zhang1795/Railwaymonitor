import { riskClasses } from '@/api/riskRules'
import type { RiskParameters, RiskRule, TemplateRef } from '@/api/riskRules'
export const templateLabel = (ref: TemplateRef) => `${ref.name} · v${ref.version}`
export const modeLabel = (rule?: RiskRule) => !rule ? '规则状态未知' : rule.enabled ? (rule.template ? templateLabel(rule.template) : '自定义风险判定') : '仅待核验观察'
export function ruleSummary(rule: RiskRule) {
  const source = rule.template ? templateLabel(rule.template) : (rule.revision ? '摄像头自定义' : '内置观察')
  const classes = rule.classes.map(id => riskClasses[id]).join('、') || '未选择'
  return `${source} · 摄像头规则 r${rule.revision}。${rule.enabled ? '已启用区域风险判定' : '仅记录待核验观察'}。关注类别 ${classes}，最低置信度 ${rule.confidence}，持续符合 ${rule.dwellSeconds} 秒。区域 [${rule.roi.join(', ')}]，短暂丢失容忍 ${rule.graceSeconds} 秒，持续提醒间隔 ${rule.reminderSeconds} 秒，风险等级 ${rule.level}，${rule.escalateSeconds ? `持续 ${rule.escalateSeconds} 秒升级` : '关闭自动升级'}。`
}
const labels: Record<keyof RiskParameters,string> = {
  classes:'类别', confidence:'最低置信度', dwellSeconds:'持续符合（秒）', graceSeconds:'丢失容忍（秒）',
  reminderSeconds:'提醒间隔（秒）', level:'风险等级', escalateSeconds:'持续升级（秒）'
}
export function changes(before: RiskParameters, after: RiskParameters) {
  const display = (value: number | number[]) => Array.isArray(value) ? value.map(id => riskClasses[id]).join('、') : String(value)
  return (Object.keys(labels) as (keyof RiskParameters)[]).filter(key => display(before[key]) !== display(after[key]))
    .map(key => `${labels[key]} ${display(before[key])} → ${display(after[key])}`)
}
export const templateKey = (ref?: TemplateRef | null) => ref ? ref.id + '/' + ref.version : ''
