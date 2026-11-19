import { ref, readonly } from 'vue'
import request from '@/api/request'

export interface WebSocketMessage {
  type: 'video_frame'|'camera_status'|'start_stream'|'stop_stream'|'check_camera'|'stream_stopped'|'stream_ready'|'authenticated'|'source_quality'
  data: { cameraId:number; frame?:string; status?:number; [key:string]:any }
}
type ConnectionState = 'idle'|'connecting'|'authenticating'|'connected'|'reconnecting'|'failed'
const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
const url = import.meta.env.VITE_ALGO_WS_URL || `${protocol}://${window.location.host}/stream/ws`

export class WebSocketClient {
  private ws: WebSocket|null = null
  private state = ref<ConnectionState>('idle')
  readonly connectionState = readonly(this.state)
  private handlers = new Set<(message:WebSocketMessage)=>void>()
  private streams = new Set<number>()
  private checks = new Set<number>()
  private restarting = new Map<number, ReturnType<typeof setTimeout>>()
  private retryTimer?:ReturnType<typeof setTimeout>
  private handshake?:ReturnType<typeof setTimeout>
  private renewTimer?:ReturnType<typeof setInterval>
  private attempts = 0
  private activeClose = false
  private epoch = 0

  constructor(private url:string) {}
  isConnected() { return this.state.value === 'connected' }
  connect() {
    if (this.ws && (this.ws.readyState===WebSocket.CONNECTING || this.ws.readyState===WebSocket.OPEN)) return
    this.cleanup()
    this.activeClose = false
    this.state.value = 'connecting'
    const epoch = this.epoch
    try {
      const socket = new WebSocket(this.url)
      this.ws = socket
      const current = () => this.epoch === epoch && this.ws === socket && !this.activeClose
      this.handshake = setTimeout(() => { if(current()) this.failedConnection() }, 12000)
      socket.onopen = async () => {
        this.state.value = 'authenticating'
        try {
          const {grant} = await request.post<{grant:string}>('/preview/grant')
          if (!current() || socket.readyState !== WebSocket.OPEN) return
          socket.send(JSON.stringify({type:'authenticate',data:{grant}}))
          this.renewTimer = setInterval(() => {
            request.post('/preview/grant/renew',{grant}).catch(() => { if(current()) this.failedConnection() })
          },60000)
        } catch { if(current()) this.failedConnection() }
      }
      socket.onmessage = event => {
        if(!current()) return
        let message:WebSocketMessage
        try { message = JSON.parse(event.data) } catch { return }
        if(!message?.data || typeof message.type !== 'string') return
        if(message.type === 'authenticated') {
          if(this.handshake) clearTimeout(this.handshake)
          this.handshake = undefined
          this.attempts = 0
          this.state.value = 'connected'
          for(const id of this.streams) this.sendImmediate({type:'start_stream',data:{cameraId:id}})
          for(const id of this.checks) this.sendImmediate({type:'check_camera',data:{cameraId:id}})
          this.checks.clear()
        }
        if(message.type === 'stream_stopped' && this.restarting.has(message.data.cameraId)) this.finishRestart(message.data.cameraId)
        for(const handler of this.handlers) handler(message)
      }
      socket.onclose = () => { if(current()) this.failedConnection() }
      socket.onerror = () => { if(current()) this.failedConnection() }
    } catch { this.failedConnection() }
  }
  private cleanup() {
    this.epoch++
    if(this.retryTimer) clearTimeout(this.retryTimer)
    if(this.handshake) clearTimeout(this.handshake)
    if(this.renewTimer) clearInterval(this.renewTimer)
    this.retryTimer = undefined; this.handshake = undefined; this.renewTimer = undefined
    for(const timer of this.restarting.values()) clearTimeout(timer)
    this.restarting.clear()
    if(this.ws) {
      const socket=this.ws;this.ws=null
      socket.onopen=null;socket.onclose=null;socket.onmessage=null;socket.onerror=null
      if(socket.readyState===WebSocket.OPEN || socket.readyState===WebSocket.CONNECTING) {
        try { socket.close(1000,'Preview connection reset') } catch { /* Already closing. */ }
      }
    }
  }
  private failedConnection() {
    this.cleanup()
    if(this.activeClose) { this.state.value='idle';return }
    if(this.attempts>=5) { this.state.value='failed';return }
    this.state.value='reconnecting'
    this.attempts++
    this.retryTimer=setTimeout(()=>{this.retryTimer=undefined;this.connect()},3000)
  }
  private sendImmediate(message:WebSocketMessage) {
    if(!this.isConnected() || this.ws?.readyState!==WebSocket.OPEN) return
    try { this.ws.send(JSON.stringify(message)) } catch { this.failedConnection() }
  }
  send(message:WebSocketMessage) {
    const id=message.data.cameraId
    if(message.type==='stop_stream') {
      this.streams.delete(id)
      const timer=this.restarting.get(id);if(timer)clearTimeout(timer)
      this.restarting.delete(id)
      // Unmounting during an outage must never create a new socket.
      this.sendImmediate(message);return
    }
    if(message.type==='start_stream') {
      if(this.streams.has(id)) return
      this.streams.add(id)
    } else if(message.type==='check_camera' && !this.isConnected()) {
      if(this.checks.size>=64) throw new Error('预览命令队列已满')
      this.checks.add(id)
    }
    if(this.isConnected()) this.sendImmediate(message)
    else if(this.state.value!=='failed') this.connect()
  }
  retryStream(id:number) {
    this.streams.add(id)
    if(!this.isConnected()) { this.attempts=0;this.cleanup();this.connect();return }
    const previous=this.restarting.get(id);if(previous)clearTimeout(previous)
    // Wait for stream_stopped, not an arbitrary 500ms, before restarting.
    this.restarting.set(id,setTimeout(()=>this.finishRestart(id),6500))
    this.sendImmediate({type:'stop_stream',data:{cameraId:id}})
  }
  private finishRestart(id:number) {
    const timer=this.restarting.get(id);if(timer)clearTimeout(timer)
    this.restarting.delete(id)
    if(this.streams.has(id))this.sendImmediate({type:'start_stream',data:{cameraId:id}})
  }
  addMessageHandler(handler:(message:WebSocketMessage)=>void) { this.handlers.add(handler) }
  removeMessageHandler(handler:(message:WebSocketMessage)=>void) { this.handlers.delete(handler) }
  resetConnectionState() {
    if(this.isConnected() || this.state.value==='connecting' || this.state.value==='authenticating')return
    this.attempts=0;this.cleanup();this.connect()
  }
  close() {
    this.activeClose=true;this.streams.clear();this.checks.clear();this.cleanup();this.state.value='idle'
  }
}
export default new WebSocketClient(url)
