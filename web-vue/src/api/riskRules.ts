import request from './request'
export const riskClasses = ['防撞设备','气球','牛','水害','滑坡','违规建筑','风筝','落石','鸟巢','广告牌','坑洞','垃圾','工人']
export interface RiskParameters {
  classes: number[]
  confidence: number
  dwellSeconds: number
  graceSeconds: number
  reminderSeconds: number
  level: number
  escalateSeconds: number
}
export interface TemplateRef { id: string; version: number; name: string }
export interface RiskRule extends RiskParameters {
  enabled: boolean
  roi: [number, number, number, number]
  revision: number
  resetOverrides?: boolean
  overrides?: (keyof RiskParameters)[]
  template?: TemplateRef | null
  preview?: {url: string; capturedAt: string}
}
export interface Published extends TemplateRef { parameters: RiskParameters; publishedAt: string; actorId: number | null }
export interface Catalog {versions: Published[]; recommendation: {revision: number; template: TemplateRef | null}}
export interface UpgradeImpact {
  cameraId: number; name: string; revision: number; running: boolean; fromVersion: number
  before: RiskParameters; after: RiskParameters
}
export interface RuleRevision {revision: number; changed_at: string; actor_id: number | null; policy: string}

export const getRiskRule = (camera: number) => request.get<RiskRule>(`/camera/${camera}/risk-rule`)
export const effectiveRiskRule = (camera: number) => request.get<RiskRule | null>(`/camera/${camera}/risk-rule/effective`)
export const saveRiskRule = (camera: number, rule: RiskRule) => request.put<RiskRule>(`/camera/${camera}/risk-rule`,rule)
export const getRuleHistory = (camera: number) => request.get<RuleRevision[]>(`/camera/${camera}/risk-rule/history`)
export const getTemplates = () => request.get<Catalog>('/risk-templates')
export const publishTemplate = (name: string, parameters: RiskParameters, base?: TemplateRef) =>
  request.post<Published>(base ? `/risk-templates/${base.id}/versions` : '/risk-templates', {name, parameters, previous: base?.version})
export const recommendTemplate = (revision: number, template: TemplateRef | null) =>
  request.put('/risk-templates/default',{revision,template})
export const templateImpact = (version: TemplateRef) => request.get<UpgradeImpact[]>(`/risk-templates/${version.id}/${version.version}/impact`)
export const upgradeCameras = (version: TemplateRef, selected: UpgradeImpact[]) =>
  request.post(`/risk-templates/${version.id}/${version.version}/upgrade`, selected.map(({cameraId,revision}) => ({cameraId,revision})))
