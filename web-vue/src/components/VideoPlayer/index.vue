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
        <el-button size="small" type="primary" @click="retryConnection">
          重试连接
        </el-button>
      </div>
    </div>
    
    <!-- 摄像头信息 -->
    <div class="camera-info">
      <span class="name">{{ camera.name }}</span>
      <span class="status" :class="camera.status === 1 ? 'online' : 'offline'">
        {{ camera.status === 1 ? '在线' : '离线' }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { Camera } from '@/types/camera'
import wsClient from '@/utils/websocket'
import type { WebSocketMessage } from '@/utils/websocket'

const props = defineProps<{
  camera: Camera
  isActive: boolean
  width?: number
  height?: number
}>()

const emit = defineEmits<{
  (e: 'click', camera: Camera): void
}>()

const router = useRouter()
const isLoading = ref(false)
const hasConnectionError = ref(false)
const connectionErrorMessage = ref('连接失败，请重试')
const connectionTimeout = ref<number | null>(null)

// 组件状态
const canvas = ref<HTMLCanvasElement | null>(null)
const ctx = ref<CanvasRenderingContext2D | null>(null)
const videoContainer = ref<HTMLDivElement | null>(null)
const frameCount = ref(0)  // 添加帧计数器

// 默认尺寸
const width = props.width || 640
const height = props.height || 480

// 重试连接
const retryConnection = () => {
  if (!props.camera || !wsClient.isConnected()) return
  
  hasConnectionError.value = false
  isLoading.value = true
  
  // 先清除之前的连接
  wsClient.send({
    type: 'stop_stream',
    data: {
      cameraId: props.camera.id
    }
  })
  
  // 清理现有超时定时器
  if (connectionTimeout.value !== null) {
    clearTimeout(connectionTimeout.value)
    connectionTimeout.value = null
  }
  
  // 设置新的连接超时
  connectionTimeout.value = window.setTimeout(() => {
    if (isLoading.value) {
      isLoading.value = false
      hasConnectionError.value = true
      connectionErrorMessage.value = '连接超时，请重试'
    }
  }, 15000) // 15秒超时
  
  // 重新发起连接
  setTimeout(() => {
    wsClient.send({
      type: 'start_stream',
      data: {
        cameraId: props.camera.id,
        rtspUrl: props.camera.rtspUrl
      }
    })
  }, 500)
}

// 清除画面和检测框
const clearDisplay = () => {
  console.log('清除画面:', props.camera.id)
  // 清除画布
  if (ctx.value) {
    ctx.value.fillStyle = '#000'  // 设置为黑色背景
    ctx.value.fillRect(0, 0, width, height)  // 填充整个画布
  }
  // 重置帧计数
  frameCount.value = 0
}

// 处理点击事件
const handleClick = () => {
  emit('click', props.camera)
}

// 处理WebSocket消息
const handleMessage = (message: WebSocketMessage) => {
  if (message.data.cameraId !== props.camera.id) return

  // 处理视频帧准备就绪消息
  if (message.type === 'stream_ready') {
    console.log('视频流准备就绪:', message.data)
    isLoading.value = false
    hasConnectionError.value = false
    
    // 清除连接超时定时器
    if (connectionTimeout.value !== null) {
      clearTimeout(connectionTimeout.value)
      connectionTimeout.value = null
    }
    return
  }

  // 处理视频帧
  if (message.type === 'video_frame') {  
    // 显示视频帧（带检测框的图像）
    if (message.data.frame) {
      const image = new Image()
      image.onload = () => {
        if (ctx.value && canvas.value) {
          // 获取Canvas和图像尺寸
          const canvasWidth = canvas.value.width
          const canvasHeight = canvas.value.height
          
          // 清除画布
          ctx.value.clearRect(0, 0, canvasWidth, canvasHeight)
          
          // 计算保持宽高比的缩放尺寸和位置
          const imgWidth = image.width
          const imgHeight = image.height
          const canvasRatio = canvasWidth / canvasHeight
          const imgRatio = imgWidth / imgHeight
          
          let drawWidth, drawHeight, x, y
          
          if (canvasRatio > imgRatio) {
            // Canvas更宽，高度限制
            drawHeight = canvasHeight
            drawWidth = imgRatio * drawHeight
            x = (canvasWidth - drawWidth) / 2
            y = 0
          } else {
            // Canvas更高，宽度限制
            drawWidth = canvasWidth
            drawHeight = drawWidth / imgRatio
            x = 0
            y = (canvasHeight - drawHeight) / 2
          }
          
          // 绘制图像
          ctx.value.drawImage(image, x, y, drawWidth, drawHeight)
          
          // 更新帧计数
          frameCount.value++
          if (frameCount.value % 30 === 0) {  // 每30帧打印一次日志
            console.log('已接收', frameCount.value, '帧')
          }
        }
      }
      image.onerror = (error) => {
        console.error('图片加载失败:', error)
      }
      image.src = message.data.frame
    }
    return
  }

  // 处理摄像头状态更新
  if (message.type === 'camera_status') {
    console.log('摄像头状态更新:', message.data)
    // 如果摄像头离线，清除画面
    if (message.data.status === 0) {
      clearDisplay()
      hasConnectionError.value = true
      isLoading.value = false
      connectionErrorMessage.value = '摄像头不在线，请检查设备'
    }
    return
  }

  // 处理停止流消息
  if (message.type === 'stream_stopped') {
    console.log('收到停止流消息')
    clearDisplay()
    return
  }
}

// 初始化视频播放器
const initPlayer = () => {
  if (!canvas.value) return
  
  // 获取Canvas 2D上下文
  ctx.value = canvas.value.getContext('2d')
  
  // 清除画布
  if (ctx.value) {
    ctx.value.fillStyle = '#000'  // 设置为黑色背景
    ctx.value.fillRect(0, 0, width, height)  // 填充整个画布
  }
  
  // 添加WebSocket消息处理器
  wsClient.addMessageHandler(handleMessage)
  
  // 如果摄像头在线并且WebSocket连接有效，则开始获取视频流
  if (props.camera && props.camera.status === 1 && props.isActive) {
    startStream()
  }
}

// 开始视频流
const startStream = () => {
  if (!props.camera || !props.isActive) return
  
  isLoading.value = true
  hasConnectionError.value = false
  
  // 清理现有的超时定时器
  if (connectionTimeout.value !== null) {
    clearTimeout(connectionTimeout.value)
    connectionTimeout.value = null
  }
  
  // 设置连接超时
  connectionTimeout.value = window.setTimeout(() => {
    if (isLoading.value) {
      isLoading.value = false
      hasConnectionError.value = true
      connectionErrorMessage.value = '连接超时，请重试'
    }
  }, 15000) // 15秒超时
  
  console.log('开始获取视频流:', props.camera.id)
  wsClient.send({
    type: 'start_stream',
    data: {
      cameraId: props.camera.id,
      rtspUrl: props.camera.rtspUrl
    }
  })
}

// 停止视频流
const stopStream = () => {
  if (!props.camera) return
  
  // 清除超时定时器
  if (connectionTimeout.value !== null) {
    clearTimeout(connectionTimeout.value)
    connectionTimeout.value = null
  }
  
  console.log('停止视频流:', props.camera.id)
  wsClient.send({
    type: 'stop_stream',
    data: {
      cameraId: props.camera.id
    }
  })
  
  // 清除画面
  clearDisplay()
  isLoading.value = false
}

// 监听组件挂载
onMounted(() => {
  initPlayer()
})

// 监听组件卸载
onBeforeUnmount(() => {
  // 停止视频流
  stopStream()
  
  // 移除WebSocket消息处理器
  wsClient.removeMessageHandler(handleMessage)
  
  // 清除超时定时器
  if (connectionTimeout.value !== null) {
    clearTimeout(connectionTimeout.value)
    connectionTimeout.value = null
  }
})

// 监听props变化
watch(() => props.isActive, (newValue) => {
  if (newValue) {
    // WebSocket已连接并且摄像头在线
    if (wsClient.isConnected() && props.camera.status === 1) {
      startStream()
    }
  } else {
    // 停止视频流
    stopStream()
  }
})

// 监听摄像头状态变化
watch(() => props.camera.status, (newValue) => {
  if (newValue === 1) {
    // 摄像头在线
    if (props.isActive && wsClient.isConnected()) {
      startStream()
    }
  } else {
    // 摄像头离线，停止视频流
    stopStream()
    hasConnectionError.value = true
    connectionErrorMessage.value = '摄像头不在线，请检查设备'
  }
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