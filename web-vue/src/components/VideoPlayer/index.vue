<template>
  <div class="video-player" @click="handleClick">
    <div class="video-container" ref="videoContainer">
      <canvas ref="canvas" :width="width" :height="height"></canvas>
      
      <!-- 加载状态 -->
      <div v-if="isLoading" class="loading-overlay">
        <el-icon class="loading-icon"><Loading /></el-icon>
        <span class="loading-text">正在连接视频流...</span>
      </div>
      
      <!-- 连接错误状态 -->
      <div v-if="hasConnectionError && !isLoading" class="error-overlay">
        <el-icon class="error-icon"><CircleClose /></el-icon>
        <span class="error-text">{{ connectionErrorMessage }}</span>
        <el-button size="small" type="primary" @click.stop="retryConnection">
          重试连接
        </el-button>
      </div>
    </div>
    
    <!-- 摄像头信息 -->
    <div class="camera-info">
      <span class="name">{{ camera.name }}</span>
      <span class="status" :class="fresh ? 'online' : 'offline'">
        {{ fresh ? '画面实时' : '画面未确认' }} · 最后画面：{{ lastFrameLabel }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import type { Camera } from '@/types/camera'
import wsClient from '@/utils/websocket'
import type { WebSocketMessage } from '@/utils/websocket'

const props = defineProps<{ camera:Camera; isActive:boolean; width?:number; height?:number }>()
const emit = defineEmits<{ (e:'click',camera:Camera):void }>()
const canvas = ref<HTMLCanvasElement|null>(null)
const ctx = ref<CanvasRenderingContext2D|null>(null)
const videoContainer = ref<HTMLDivElement|null>(null)
const width = props.width || 640
const height = props.height || 480
const isLoading = ref(true)
const hasConnectionError = ref(false)
const connectionErrorMessage = ref('正在等待预览连接')
const lastFrameAt = ref(0)
const now = ref(Date.now())
const fresh = computed(() => props.isActive && lastFrameAt.value > 0 && now.value-lastFrameAt.value <= 5000 && !hasConnectionError.value && !isLoading.value)
const lastFrameLabel = computed(() => lastFrameAt.value ? new Date(lastFrameAt.value).toLocaleTimeString('zh-CN',{hour12:false}) : '尚未收到画面')
let timer:ReturnType<typeof setInterval>|undefined
let startedAt = Date.now()
let disposed = false
let imageEpoch = 0
let received = 0
let drawn = 0
let sourceCorrupt=false

const clearDisplay = () => {
  imageEpoch++
  if(ctx.value) { ctx.value.fillStyle='#000';ctx.value.fillRect(0,0,width,height) }
}
const fail = (message:string) => {
  isLoading.value=false;hasConnectionError.value=true;connectionErrorMessage.value=message
  clearDisplay()
}
const waitForFrames = () => {
  sourceCorrupt=false
  startedAt=Date.now();isLoading.value=true;hasConnectionError.value=false
  clearDisplay()
}
const retryConnection = () => {
  if(disposed)return
  waitForFrames()
  wsClient.retryStream(props.camera.id)
}
const handleClick = () => emit('click',props.camera)
const handleMessage = (message:WebSocketMessage) => {
  if(disposed || message.data.cameraId!==props.camera.id)return
  if(message.type==='source_quality' && message.data.state==='CORRUPT') {sourceCorrupt=true;fail('源画面解码损坏，已停止显示，请检查源流后重试');return}
  if(message.type==='camera_status' && message.data.status!==1) {
    fail('预览不可用，请检查设备或重试');return
  }
  if(message.type==='stream_stopped') {
    if(!sourceCorrupt)fail('预览已停止，画面已过期');return
  }
  // stream_ready alone is not proof that a usable JPEG has been displayed.
  if(message.type!=='video_frame' || !message.data.frame)return
  const image=new Image(), epoch=imageEpoch, sequence=++received
  image.onload=()=>{
    if(disposed || epoch!==imageEpoch || sequence<=drawn || !ctx.value || !canvas.value || !wsClient.isConnected())return
    const w=canvas.value.width,h=canvas.value.height
    const scale=Math.min(w/image.width,h/image.height)
    ctx.value.clearRect(0,0,w,h)
    ctx.value.drawImage(image,(w-image.width*scale)/2,(h-image.height*scale)/2,image.width*scale,image.height*scale)
    drawn=sequence;lastFrameAt.value=Date.now();now.value=Date.now()
    isLoading.value=false;hasConnectionError.value=false
  }
  image.onerror=()=>{if(!disposed && epoch===imageEpoch)fail('画面解码失败，请重试')}
  image.src=message.data.frame
}

watch(()=>props.isActive,connected=>{
  if(connected)waitForFrames()
  else fail('预览连接已断开，画面已过期')
})
onMounted(()=>{
  if(canvas.value)ctx.value=canvas.value.getContext('2d')
  clearDisplay()
  wsClient.addMessageHandler(handleMessage)
  wsClient.send({type:'start_stream',data:{cameraId:props.camera.id}})
  timer=setInterval(()=>{
    now.value=Date.now()
    if(lastFrameAt.value && now.value-lastFrameAt.value>5000 && !hasConnectionError.value && !isLoading.value)fail('超过5秒没有新画面，画面已过期')
    if(isLoading.value && now.value-startedAt>15000)fail('等待新画面超时，请重试连接')
  },1000)
})
onBeforeUnmount(()=>{
  disposed=true;imageEpoch++
  if(timer)clearInterval(timer)
  wsClient.removeMessageHandler(handleMessage)
  wsClient.send({type:'stop_stream',data:{cameraId:props.camera.id}})
})
</script>

<style lang="scss" scoped>
.video-player {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #000;
  border-radius: 8px;
  overflow: hidden;
  
  .video-container {
    position: relative;
    width: 100%;
    height: 100%;
    
    canvas {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
  }
  
  .camera-info {
    position: absolute;
    top: 10px;
    left: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 5px 10px;
    background-color: rgba(0, 0, 0, 0.5);
    border-radius: 4px;
    
    .name {
      color: #fff;
      font-size: 14px;
    }
    
    .status {
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 12px;
      
      &.online {
        background-color: #67c23a;
        color: #fff;
      }
      
      &.offline {
        background-color: #909399;
        color: #fff;
      }
    }
  }
  
  .Abnormal-alert-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: linear-gradient(to bottom, 
      rgba(220, 38, 38, 0.2), 
      rgba(0, 0, 0, 0.4)
    );
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
    
    &.alert-active {
      opacity: 1;
      pointer-events: auto;
      animation: pulseBackground 2s infinite;
    }

    .alert-icon {
      margin-bottom: 20px;
      .el-icon {
        font-size: 48px;
        color: #fff;
        animation: pulse 1s infinite;
      }
    }

    .alert-info {
      background: rgba(0, 0, 0, 0.75);
      padding: 15px;
      border-radius: 8px;
      backdrop-filter: blur(4px);
      border: 2px solid #f56c6c;
      animation: borderBlink 2s infinite;

      .alert-title {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;

        .warning-text {
          color: #f56c6c;
          font-size: 20px;
          font-weight: bold;
        }

        .level-tag {
          margin-left: auto;
        }
      }

      .alert-details {
        display: grid;
        gap: 8px;

        .detail-item {
          display: flex;
          align-items: center;
          gap: 8px;

          .label {
            color: #909399;
            min-width: 50px;
          }

          .value {
            color: #fff;
            font-weight: 500;
          }
        }
      }
    }

    .alert-actions {
      margin-top: 15px;

      .action-button {
        animation: shake 1s infinite;
      }
    }
  }
  
  .loading-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.7);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 5;
  }
  
  .loading-icon {
    font-size: 32px;
    color: #409eff;
    animation: rotating 2s linear infinite;
  }
  
  .loading-text {
    margin-top: 12px;
    color: #fff;
    font-size: 14px;
  }
  
  .error-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.7);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    z-index: 5;
  }
  
  .error-icon {
    font-size: 32px;
    color: #f56c6c;
  }
  
  .error-text {
    margin: 12px 0;
    color: #fff;
    font-size: 14px;
    text-align: center;
  }
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.2); opacity: 0.8; }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-2px); }
  75% { transform: translateX(2px); }
}

@keyframes borderBlink {
  0% { border-color: rgba(245, 108, 108, 0.4); }
  50% { border-color: rgba(245, 108, 108, 1); }
  100% { border-color: rgba(245, 108, 108, 0.4); }
}

@keyframes pulseBackground {
  0% { background: linear-gradient(to bottom, rgba(220, 38, 38, 0.1), rgba(0, 0, 0, 0.4)); }
  50% { background: linear-gradient(to bottom, rgba(220, 38, 38, 0.3), rgba(0, 0, 0, 0.4)); }
  100% { background: linear-gradient(to bottom, rgba(220, 38, 38, 0.1), rgba(0, 0, 0, 0.4)); }
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
