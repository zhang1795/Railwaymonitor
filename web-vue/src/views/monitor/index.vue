<template>
  <div class="monitor" :class="{'detection-mode':viewMode==='detection'}">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-radio-group v-model="viewMode" size="small" aria-label="画面模式"><el-radio-button value="detection">检测结果</el-radio-button><el-radio-button value="source">原始直播</el-radio-button></el-radio-group>
        <el-radio-group v-model="layout" size="large">
          <el-radio-button :value="1">
            <el-icon>
              <Monitor />
            </el-icon>
          </el-radio-button>
          <el-radio-button :value="4">
            <el-icon>
              <Grid />
            </el-icon>
          </el-radio-button>
          <el-radio-button :value="9">
            <el-icon>
              <Grid />
            </el-icon>
          </el-radio-button>
        </el-radio-group>
      </div>
      <div class="right" v-if="activeCamera">
        <span>{{ activeCamera.name }}</span>
        <MonitoringStatus :row="monitorRows[activeCamera.id]" :healthy="monitorHealthy" :label="monitoring.label(activeCamera.id)" :report-at="monitoring.reportAt(activeCamera.id)" />
        <ModeSummary :camera="activeCamera" :session="monitorRows[activeCamera.id]?.session_id" />
        <el-button v-if="userStore.userInfo?.role === 1" :disabled="!monitorLoaded" :type="monitorRows[activeCamera.id]?.enabled ? 'danger' : 'primary'" :loading="changingMonitoring.has(activeCamera.id)" @click="toggleMonitoring">
          {{ monitorRows[activeCamera.id]?.enabled ? '停用后台检测' : '启用后台检测' }}
        </el-button>
      </div>
    </div>

    <div class="monitor-container">
      <!-- 左侧主画面区域 -->
      <div class="main-video">
        <template v-if="displayCameras.length > 0">
          <div class="video-grid" :class="'grid-' + layout">
            <div v-for="camera in displayCameras" :key="camera.id" class="video-item">
              <DetectionView v-if="viewMode==='detection'" :camera="camera"/>
              <VideoPlayer v-else :camera="camera" :is-active="wsClient.isConnected()"
                @click="handleCameraClick" />
              <el-tag v-if="viewMode==='source'" class="detector-state">{{ monitoring.label(camera.id) }}</el-tag>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="empty-state">
            <el-empty description="请从下方列表选择要查看的摄像头" :image-size="200">
              <template #image>
                <el-icon :size="60" style="margin-bottom: 15px;">
                  <Monitor />
                </el-icon>
              </template>
            </el-empty>
          </div>
        </template>
      </div>

      <!-- 右侧地图区域 -->
      <div class="map-area">
        <div class="map">
          <MapComponent ref="mapRef" />
        </div>
      </div>
    </div>

    <!-- 下侧区域 -->
    <div class="bottom-panel">
      <!-- 摄像头列表 -->
      <div class="camera-list">
        <div class="section-header">
          <h3>摄像头列表</h3>
          <el-button type="primary" link @click="checkAllCamerasStatus" :loading="checkingStatus">
            <el-icon>
              <Refresh :class="{ 'rotate-icon': checkingStatus }" />
            </el-icon>
            {{ checkingStatus ? '检测中...' : '检测状态' }}
          </el-button>
        </div>
        <el-scrollbar mode="horizontal">
          <div class="list-content">
            <template v-if="cameras.length > 0">
              <div v-for="camera in cameras" :key="camera.id" class="camera-item" :class="{
                'is-active': isActiveCamera(camera.id),
                'is-online': camera.status === 1,
                'is-checking': checkingStatus && camera.status !== 2
              }" @click="handleCameraSelect(camera)">
                <span class="name">{{ camera.name }}</span>
                <span class="location">{{ camera.location }}</span>
                <span class="status" :class="{
                  'online': camera.status === 1,
                  'offline': camera.status === 0,
                  'fault': camera.status === 2,
                  'checking': checkingStatus && camera.status !== 2
                }">
                  {{ checkingStatus && camera.status !== 2 ? '检测中...' : formatDeviceStatus(camera.status) }}
                </span>
              </div>
            </template>
            <template v-else>
              <div class="empty-state">
                <el-empty description="暂无摄像头" :image-size="100">
                  <template #image>
                    <el-icon :size="40" style="margin-bottom: 10px;">
                      <VideoCameraFilled />
                    </el-icon>
                  </template>
                </el-empty>
              </div>
            </template>
          </div>
        </el-scrollbar>
      </div>
    </div>

    <!-- 摄像头详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="摄像头详情" size="400px" :show-close="true" :with-header="true">
      <template v-if="activeCamera">
        <div class="camera-info">
          <div class="info-item">
            <span class="label">设备名称：</span>
            <span class="value">{{ activeCamera.name }}</span>
          </div>
          <div class="info-item">
            <span class="label">安装位置：</span>
            <span class="value">{{ activeCamera.location }}</span>
          </div>
          <div class="info-item">
            <span class="label">IP地址：</span>
            <span class="value">{{ activeCamera.ipAddress }}</span>
          </div>

          <div class="info-item">
            <span class="label">设备状态：</span>
            <el-tag :type="getStatusType(activeCamera.status)">
              {{ formatDeviceStatus(activeCamera.status) }}
            </el-tag>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import ModeSummary from '@/components/RiskRuleDialog/ModeSummary.vue'
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Camera } from '@/types/camera'
import { getCameraList } from '@/api/camera'
import { formatDeviceStatus } from '@/utils/format'
import wsClient from '@/utils/websocket'
import type { WebSocketMessage } from '@/utils/websocket'
import VideoPlayer from '@/components/VideoPlayer/index.vue'
import DetectionView from '@/components/DetectionView/index.vue'
import { Picture } from '@element-plus/icons-vue'
import { useMonitoring } from '@/composables/useMonitoring'
import MonitoringStatus from '@/components/MonitoringStatus/index.vue'
import { useUserStore } from '@/stores/user'
import MapComponent from '@/components/Map/index.vue'

// 定义mapRef引用Map子组件
const mapRef = ref<InstanceType<typeof MapComponent> | null>(null)

const router = useRouter()

// 布局方式（1/4/9宫格）
const layout = ref(4)
const viewMode = ref<'detection'|'source'>('detection')
// 摄像头列表
const cameras = ref<Camera[]>([])
// 当前显示的摄像头列表
const displayCameras = ref<Camera[]>([])
// 当前选中的摄像头
const activeCamera = ref<Camera>()
// // 异常记录列表
// const AbnormalRecords = ref<AbnormalEvent[]>([])
// 抽屉可见性
const drawerVisible = ref(false)
// 加载状态
const loading = ref(false)
// 检测状态加载中
const checkingStatus = ref(false)
// 当前显示的消息框
let currentMessageBox: Promise<any> | null = null
let disposed=false
const pendingChecks=new Set<()=>void>()

// 获取摄像头列表
const fetchCameras = async () => {
  if (loading.value) return // 防止重复调用

  try {
    loading.value = true
    console.log('开始获取摄像头列表')
    const res = await getCameraList({
      current: 1,
      size: 100, // 获取更多摄像头
    })
    console.log('获取摄像头列表成功:', res)
    cameras.value = res.records
    // 初始化显示的摄像头
    updateDisplayCameras()
  } catch (error) {
    console.error('获取摄像头列表失败:', error)
    return // 如果获取列表失败，直接返回
  } finally {
    loading.value = false
  }
}

// 更新显示的摄像头列表
const updateDisplayCameras = () => {
  // 过滤掉离线的摄像头
  const oldDisplayCameras = displayCameras.value.slice()
  displayCameras.value = displayCameras.value.filter(camera => {
    const currentCamera = cameras.value.find(c => c.id === camera.id)
    return Boolean(currentCamera)
  }).slice(0, layout.value)

  // 检查是否有摄像头被移除，确保停止其视频流
  oldDisplayCameras.forEach(camera => {
    if (!displayCameras.value.some(c => c.id === camera.id)) {
      stopCameraStream(camera.id)
    }
  })
}

// 检查摄像头是否在显示列表中（即是否激活）
const isActiveCamera = (cameraId: number) => {
  return displayCameras.value.some(camera => camera.id === cameraId)
}

// 检查所有摄像头状态
const checkAllCamerasStatus = async () => {
  if (loading.value || checkingStatus.value) return // 如果正在加载中，直接返回

  loading.value = true
  checkingStatus.value = true

  try {
    // 显示正在检测的提示
    ElMessage({
      message: '正在检测所有摄像头状态，请稍候...',
      type: 'info',
      duration: 2000
    })

    // 清除所有非故障摄像头的状态
    cameras.value.forEach(camera => {
      if (camera.status !== 2) {
        camera.status = 0
      }
    })

    // 串行检查每个摄像头的状态，跳过故障状态的设备
    for (const camera of cameras.value) {
      if(disposed)break
      // 跳过故障状态的设备
      if (camera.status === 2) {
        continue
      }

      console.log('检查摄像头状态:', camera.name)

      // 发送检测请求
      wsClient.send({
        type: 'check_camera',
        data: {
          cameraId: camera.id,
          rtspUrl: camera.rtspUrl
        }
      })

      // 等待检测完成
      await new Promise<void>((resolve) => {
        const finish=()=>{
          clearTimeout(timeoutId)
          wsClient.removeMessageHandler(handler)
          pendingChecks.delete(finish)
          resolve()
        }
        // 创建一个超时检测
        const timeoutId = setTimeout(() => {
          console.log('检测超时:', camera.name)
          finish()
        }, 3000) // 给每个摄像头3秒的检测时间

        // 创建一个一次性的消息处理器
        const handler = (message: WebSocketMessage) => {
          if (message.type === 'camera_status' && message.data.cameraId === camera.id) {
            finish()
          }
        }

        wsClient.addMessageHandler(handler)
        pendingChecks.add(finish)
      })

      // 检测完成后等待一小段时间再检测下一个，避免并发
      if(!disposed)await new Promise(resolve => setTimeout(resolve, 500))
    }

    // 检测完成后显示提示
    if(!disposed)ElMessage({
      message: '摄像头状态检测完成',
      type: 'success',
      duration: 2000
    })
  } catch (error) {
    console.error('检查摄像头状态失败:', error)
    ElMessage.error('检查摄像头状态失败')
  } finally {
    loading.value = false
    checkingStatus.value = false
  }
}

// 监听布局变化
watch(() => layout.value, () => {
  // 更新显示的摄像头列表
  updateDisplayCameras()
})

// 处理摄像头点击
const handleCameraClick = (camera: Camera) => {
  activeCamera.value = camera
  drawerVisible.value = true
  // fetchAbnormalRecords(camera.id)
}

// Preview failures remain visible in their tiles so they can be retried.
const handleWebSocketMessage = (message: WebSocketMessage) => {
  if(message.type==='camera_status') {
    const camera=cameras.value.find(row=>row.id===message.data.cameraId)
    if(camera)camera.status=message.data.status ?? 0
  }
}

// 获取状态类型
const getStatusType = (status: number): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  const types = ['danger', 'success', 'warning'] as const
  return types[status] as 'success' | 'warning' | 'info' | 'danger' | 'primary'
}

// Selecting a device never depends on its preview or cached online status.
const handleCameraSelect = (camera:Camera) => {
  activeCamera.value=camera
  if(isActiveCamera(camera.id)) {
    displayCameras.value=displayCameras.value.filter(row=>row.id!==camera.id)
    stopCameraStream(camera.id)
    return
  }
  if(displayCameras.value.length>=layout.value) {
    const removed=displayCameras.value.shift()
    if(removed)stopCameraStream(removed.id)
  }
  displayCameras.value.push(camera)
  if(mapRef.value && Number.isFinite(camera.longitude) && Number.isFinite(camera.latitude)) {
    nextTick(()=>mapRef.value?.setCameraLocation(camera.longitude,camera.latitude,16))
  }
}

const userStore = useUserStore()
const monitoring = useMonitoring()
const { rows:monitorRows, loaded:monitorLoaded, healthy:monitorHealthy, changing:changingMonitoring } = monitoring
const refreshDetectionState = monitoring.refresh
const toggleMonitoring = async () => {
  const camera=activeCamera.value
  if(!camera || !monitorLoaded.value)return
  const enabled=!monitorRows.value[camera.id]?.enabled
  await monitoring.change(camera.id,enabled)
  ElMessage.success(enabled?'已启用后台检测，离开页面后继续运行':'已请求停用后台检测')
}
function stopCameraStream(cameraId: number) {
  wsClient.send({ type:'stop_stream', data:{ cameraId } })
}

onMounted(() => {
  // 添加WebSocket消息处理器
  wsClient.addMessageHandler(handleWebSocketMessage)
  // 确保WebSocket连接状态正确，如果需要则重置连接
  wsClient.resetConnectionState()
  // 获取摄像头列表
  fetchCameras()
})

onBeforeUnmount(() => {
  disposed=true
  for(const finish of pendingChecks)finish()
  // 移除WebSocket消息处理器
  wsClient.removeMessageHandler(handleWebSocketMessage)
  // 停止所有视频流
  displayCameras.value.forEach(camera => {
    stopCameraStream(camera.id)
  })
  // 关闭WebSocket连接
  wsClient.close()

})
</script>

<style lang="scss" scoped>
.detector-state { position: absolute; top: 8px; right: 8px; z-index: 3; }
.monitor {
  height: 100%;
  padding: 20px;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color);

  .toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 0;
    .left { display:flex;align-items:center;flex-wrap:wrap;gap:12px; }

    .right {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
  }

  .monitor-container {
    width: 100%;
    display: flex;
    flex-direction: row;
    gap: 20px;
    align-items: flex-start;
    padding: 10px 0;
    box-sizing: border-box;

    .main-video {
      flex: 1;
      max-width: 800px;
      background-color: var(--el-bg-color-overlay);
      border-radius: 8px;
      overflow: hidden;
      position: relative;
      min-height: 410px;
      box-sizing: border-box;

      .video-grid {
        height: 400px;
        width: 100%;
        display: grid;
        gap: 10px;
        padding: 10px;
        box-sizing: border-box;

        &.grid-1 {
          grid-template-columns: 1fr;
          grid-template-rows: 1fr;
        }

        &.grid-4 {
          height: 450px;
          grid-template-columns: repeat(2, 1fr);
          grid-template-rows: repeat(2, 1fr);
        }

        &.grid-9 {
          height: 660px;
          grid-template-columns: repeat(3, 1fr);
          grid-template-rows: repeat(3, 1fr);
        }
      }

      .video-item {
        position: relative;
        width: 100%;
        height: 100%;
        min-height: 200px;
        overflow: hidden;
        border-radius: 4px;
        background-color: var(--el-bg-color);
      }

      .empty-state {
        height: 400px;
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 20px;
        box-sizing: border-box;
      }
    }

    .map-area {
      flex: 1;
      height: 410px;
      background-color: var(--el-bg-color-overlay);
      border-radius: 8px;
      overflow: hidden;
      box-sizing: border-box;
      padding: 10px;
      // 添加定位上下文，让子组件绝对定位参考此容器
      position: relative;

      .map {
        height: 100%;
        width: 100%;
        padding: 0;
        box-sizing: border-box;
      }
    }
  }

  // ========== 精准穿透地图子组件样式 ==========
  .monitor-container .map-area :deep(.map-wrapper) {
    position: relative !important;
    width: 100% !important;
    height: 100% !important;
    max-height: 100% !important;
    min-height: unset !important;
    overflow: hidden !important;
    box-sizing: border-box !important;

    // 1. 匹配 #panel（第一个子元素）
    & > #panel {
      position: absolute !important;
      top: 88px !important;
      left: 13px !important;
      z-index: 999 !important;
      width: calc(100% - 20px) !important;
      max-width: 280px !important;
      box-sizing: border-box !important;
    }

    // 2. 匹配 .search-container（第二个子元素）
    & > .search-container {
      position: absolute !important;
      top: 10px !important; // 避开panel，防止重叠
      left: 70px !important;
      z-index: 999 !important;
      width: calc(100% - 20px) !important;
      max-width: 200px !important;
      box-sizing: border-box !important;
    }

    // 3. 匹配 #amap（第三个子元素）
    & > #amap {
      height: 100% !important;
      max-height: 100% !important;
      width: 100% !important;
      box-sizing: border-box !important;
      overflow: hidden !important;
    }

    // 4. 匹配 .draw-area（第四个子元素）
    & > .draw-area {
      position: absolute !important;
      bottom: 20px !important;
      right: 180px !important;
      z-index: 999 !important;
      box-sizing: border-box !important;
    }
  }


  .bottom-panel {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0;

    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0;

      h3 {
        margin: 0;
        font-size: 16px;
        color: var(--el-text-color-primary);
      }
    }

    .camera-list {
      flex: 1;
      background-color: var(--el-bg-color-overlay);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      min-height: 100px;
      width: 100%;

      .list-content {
        display: flex;
        flex-direction: row;
        gap: 12px;
        padding: 8px 0;
        width: fit-content;

        .camera-item {
          padding: 10px;
          width: 150px;
          flex-shrink: 0;
          border-radius: 4px;
          cursor: pointer;
          transition: all 0.3s;
          display: flex;
          flex-direction: column;
          gap: 5px;

          &:hover {
            background-color: var(--el-fill-color-light);
          }

          &.is-active {
            background-color: var(--el-color-primary-light-9);
          }

          &.is-checking {
            background-color: var(--el-color-info-light-9);
            animation: pulse 1.5s infinite;
          }

          .name {
            font-weight: bold;
            color: var(--el-text-color-primary);
          }

          .location {
            font-size: 12px;
            color: var(--el-text-color-secondary);
          }

          .status {
            font-size: 12px;
            padding: 2px 6px;
            border-radius: 4px;
            align-self: flex-start;

            &.online {
              background-color: var(--el-color-success-light-8);
              color: var(--el-color-success);
            }

            &.offline {
              background-color: var(--el-color-info-light-8);
              color: var(--el-color-info);
            }

            &.fault {
              background-color: var(--el-color-warning-light-8);
              color: var(--el-color-warning);
            }

            &.checking {
              background-color: var(--el-color-info-light-8);
              color: var(--el-color-info);
            }
          }
        }
      }
    }
  }
}

.monitor.detection-mode .monitor-container .main-video .video-grid {
  &.grid-1 { height:620px; }
  &.grid-4 { height:720px; }
  &.grid-9 { height:900px; }
}

.camera-info {
  margin-bottom: 30px;

  .info-item {
    margin-bottom: 15px;

    .label {
      color: var(--el-text-color-secondary);
      margin-right: 10px;
    }

    .value {
      color: var(--el-text-color-primary);
    }
  }
}

.Abnormal-records {
  .title {
    font-size: 16px;
    font-weight: bold;
    margin-bottom: 20px;
    color: var(--el-text-color-primary);
  }

  .record-content {

    .level,
    .status {
      margin-bottom: 5px;
    }

    .description {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
  }
}

.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;

  :deep(.el-empty) {
    padding: 40px;

    .el-icon {
      color: var(--el-text-color-secondary);
    }

    .el-empty__description {
      margin-top: 10px;
      color: var(--el-text-color-secondary);
    }
  }
}

@media (max-width: 1200px) {
  .monitor .monitor-container {
    flex-direction: column;
    align-items:stretch;

    .main-video {
      min-height: 400px;
      width:100%;max-width:none;flex:none;
    }
    .map-area { width:100%;height:300px;flex:none; }

    .right-panel {
      width: 100%;
      flex-direction: row;
      gap: 20px;

      .camera-list {
        flex: 1;
        min-height: 300px;
      }
    }
  }
}

@media (max-width: 768px) {
  .monitor-container {
    .right-panel {
      flex-direction: column;
    }
  }
}

// 旋转动画
@keyframes rotate {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

// 脉冲动画
@keyframes pulse {
  0% {
    opacity: 1;
  }

  50% {
    opacity: 0.7;
  }

  100% {
    opacity: 1;
  }
}

.rotate-icon {
  animation: rotate 1.5s linear infinite;
  display: inline-block;
}
</style>
