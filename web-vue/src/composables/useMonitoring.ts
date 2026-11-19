import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { getMonitoring, setMonitoring } from '@/api/monitoring'
import type { MonitoringState } from '@/api/monitoring'

export const REPORT_TTL = 35000
export const QUERY_TTL = 10000
// The monitoring API currently serializes UTC DATETIME without a zone suffix.
export function reportTime(value?: string|null): number {
  if (!value) return NaN
  return Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : value.replace(' ', 'T') + 'Z')
}
export function monitoringLabel(row: MonitoringState|undefined, healthy: boolean, now: number): string {
  if (!healthy) return '状态未知（查询不可用）'
  if (!row) return '未启用检测'
  const time = reportTime(row.last_status_at)
  if (!Number.isFinite(time)) return '等待节点确认'
  if (now - time > REPORT_TTL || time - now > 30000) {
    return !row.enabled && row.state === 'STOPPED' ? '已停用（停止确认已过期）' : '状态未知（报告过期）'
  }
  if(row.state==='RUNNING'){
    const inference=reportTime(row.metrics?.lastInferenceAt),frame=reportTime(row.metrics?.lastFrameAt)
    if(!Number.isFinite(inference) || !Number.isFinite(frame))return '进程运行，推理尚未验证'
    if(now-inference>REPORT_TTL || now-frame>REPORT_TTL || inference-now>5000 || frame-now>5000)return '推理或取帧停滞，请检查'
  }
  const labels: Record<string, string> = { STARTING:'启动中', RUNNING:'检测中', STOPPING:'停止中', STOPPED:'已停止', FAILED:'检测失败' }
  return labels[row.state] || '未知节点状态'
}

export function useMonitoring() {
  const rows = ref<Record<number, MonitoringState>>({})
  const loaded = ref(false)
  const reachable = ref(false)
  const lastQuery = ref(0)
  const now = ref(Date.now())
  const changing = ref(new Set<number>())
  let active = true
  let pending: Promise<void>|undefined
  let poll: ReturnType<typeof setInterval>|undefined
  let ticker: ReturnType<typeof setInterval>|undefined
  const healthy = computed(() => reachable.value && now.value - lastQuery.value <= QUERY_TTL)
  const refresh = (): Promise<void> => {
    if (pending) return pending
    pending = (async () => {
      try {
        const result = await getMonitoring()
        if (!active) return
        rows.value = Object.fromEntries(result.map(row => [row.camera_id, row]))
        lastQuery.value = Date.now(); now.value = Date.now()
        reachable.value = true; loaded.value = true
      } catch { if (active) reachable.value = false }
      finally { pending = undefined }
    })()
    return pending
  }
  const change = async (cameraId: number, enabled: boolean) => {
    if (changing.value.has(cameraId)) return
    changing.value = new Set(changing.value).add(cameraId)
    try {
      const row = await setMonitoring(cameraId, enabled)
      if (!active) return
      // The requested intent is explicit, never inverted using a stale state.
      rows.value = { ...rows.value, [cameraId]: row }
      await pending
      await refresh()
    } finally {
      const next = new Set(changing.value); next.delete(cameraId); changing.value = next
    }
  }
  const label = (id: number) => monitoringLabel(rows.value[id], healthy.value, now.value)
  const reportAt = (id: number) => {
    const time = reportTime(rows.value[id]?.last_status_at)
    return Number.isFinite(time) ? new Date(time).toLocaleString('zh-CN', { hour12:false }) : '尚无报告'
  }
  onMounted(() => {
    void refresh()
    poll = setInterval(() => { void refresh() }, 2000)
    ticker = setInterval(() => { now.value = Date.now() }, 1000)
  })
  onBeforeUnmount(() => {
    active = false
    if (poll) clearInterval(poll)
    if (ticker) clearInterval(ticker)
  })
  return { rows, loaded, healthy, changing, refresh, change, label, reportAt }
}
