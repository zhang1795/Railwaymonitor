/** Per-page ownership and leases for the camera detector task protocol. */
export interface TaskStatus {
  videoId: string
  sessionId?: string
  clientId?: string
  requestId?: string
  state: string
  revision?: number
  action?: string
  error?: string
}
export interface TaskTransport {
  publish(topic: string, message: unknown, qos?: 0 | 1 | 2): void
  subscribe(topic: string, qos?: 0 | 1 | 2): void
  registerHandler<T>(topic: string, handler: (message: T) => void): void
  removeHandler(topic: string): void
}
interface CameraTask {
  videoId: string
  videoUrl: string
  deviceName: string
}
interface Entry {
  camera: CameraTask
  desired: boolean
  sessionId?: string
  requestId: string
  state: string
  revision: number
  waitingForStop: boolean
}
function token(): string {
  const bytes = new Uint8Array(16)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(bytes)
    return Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('')
  }
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}
export class DetectorTasks {
  private entries = new Map<string, Entry>()
  private timer?: ReturnType<typeof setInterval>
  constructor(
    private transport: TaskTransport,
    private notify: (status: TaskStatus) => void = () => {},
    readonly clientId = token(),
    private taskTopic = '/UAV/videoTopic/post',
    private statusTopic = '/UAV/videoTaskStatus/post',
    autoTick = true,
  ) {
    transport.registerHandler<TaskStatus>(statusTopic, status => this.receive(status))
    transport.subscribe(statusTopic, 1)
    if (autoTick) this.timer = setInterval(() => this.tick(), 5000)
  }
  start(camera: CameraTask) {
    const previous = this.entries.get(camera.videoId)
    if (previous?.desired && previous.camera.videoUrl === camera.videoUrl) return
    const entry: Entry = {
      camera, desired: true, requestId: token(), state: 'PENDING',
      revision: -1, waitingForStop: false,
    }
    this.entries.set(camera.videoId, entry)
    this.sendStart(entry)
  }
  private sendStart(entry: Entry) {
    this.transport.publish(this.taskTopic, {
      ...entry.camera, action: 'start', protocolVersion: 2,
      clientId: this.clientId, requestId: entry.requestId,
      startTime: new Date().toISOString(),
    }, 1)
  }
  stop(videoId: string) {
    const entry = this.entries.get(videoId)
    if (!entry || !entry.desired) return
    entry.desired = false
    this.sendStop(entry)
  }
  private sendStop(entry: Entry) {
    this.transport.publish(this.taskTopic, {
      action: 'stop', protocolVersion: 2, videoId: entry.camera.videoId,
      clientId: this.clientId, requestId: token(), sessionId: entry.sessionId,
    }, 1)
  }
  tick() {
    for (const entry of this.entries.values()) {
      if (!entry.desired) continue
      if (!entry.sessionId || entry.waitingForStop) {
        if (entry.waitingForStop) entry.requestId = token()
        this.sendStart(entry)
      } else {
        this.transport.publish(this.taskTopic, {
          action: 'heartbeat', protocolVersion: 2, videoId: entry.camera.videoId,
          clientId: this.clientId, sessionId: entry.sessionId, requestId: token(),
        }, 1)
      }
    }
  }
  receive(status: TaskStatus) {
    if (!status || typeof status.videoId !== 'string' || typeof status.state !== 'string') return
    const entry = this.entries.get(status.videoId)
    if (!entry) return
    if (status.clientId && status.clientId !== this.clientId) return
    if (!entry.sessionId && status.requestId !== entry.requestId) return
    if (entry.sessionId && status.sessionId && status.sessionId !== entry.sessionId) {
      if (status.requestId !== entry.requestId) return
      entry.revision = -1
    }
    if (status.revision !== undefined && status.revision <= entry.revision) return
    entry.revision = status.revision ?? entry.revision
    entry.sessionId = status.sessionId || entry.sessionId
    entry.state = status.state
    if (!entry.desired && (status.state === 'STARTING' || status.state === 'RUNNING')) {
      if (status.requestId === entry.requestId) this.sendStop(entry)
      this.notify({ ...status, state: 'STOPPING' })
      return
    }
    if (entry.desired && status.state === 'STOPPING') entry.waitingForStop = true
    if (status.state === 'FAILED' || status.state === 'REJECTED') entry.desired = false
    if (status.state === 'STOPPED' && entry.desired) {
      if (entry.waitingForStop || status.action === 'heartbeat') {
        entry.sessionId = undefined
        entry.requestId = token()
        entry.revision = -1
        entry.waitingForStop = false
      } else entry.desired = false
    }
    this.notify(status)
  }
  dispose() {
    if (this.timer !== undefined) clearInterval(this.timer)
    for (const id of this.entries.keys()) this.stop(id)
    this.transport.removeHandler(this.statusTopic)
    this.entries.clear()
  }
}
