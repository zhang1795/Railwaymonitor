<template>
  <div class="monitor">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="left">
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
    </div>

    <div class="monitor-container">
      <!-- 左侧主画面区域 -->
      <div class="main-video">
        <template v-if="displayCameras.length > 0">
          <div class="video-grid" :class="'grid-' + layout">
            <div v-for="camera in displayCameras" :key="camera.id" class="video-item">
              <VideoPlayer :camera="camera" :is-active="wsClient.isConnected()"
                @click="handleCameraClick" />
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
            <span class="label">RTSP地址：</span>
            <span class="value">{{ activeCamera.rtspUrl }}</span>
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
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Camera } from '@/types/camera'
import { getCameraList } from '@/api/camera'
import { formatDeviceStatus } from '@/utils/format'
import wsClient from '@/utils/websocket'
import type { WebSocketMessage } from '@/utils/websocket'
import VideoPlayer from '@/components/VideoPlayer/index.vue'
import { Picture } from '@element-plus/icons-vue'
import mqttClient from '@/utils/mqttClient'
import type { MqttMessage, DetectionResult } from '@/utils/mqttClient'
import { getAbnormalEventList, createAbnormalEvent } from '@/api/Abnormal'
import MapComponent from '@/components/Map/index.vue'

// 定义mapRef引用Map子组件
const mapRef = ref<InstanceType<typeof MapComponent> | null>(null)

const router = useRouter()

// 布局方式（1/4/9宫格）
const layout = ref(4)
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
    return currentCamera && currentCamera.status === 1
  }).slice(0, layout.value)

  // 检查是否有摄像头被移除，确保停止其视频流
  oldDisplayCameras.forEach(camera => {
    if (!displayCameras.value.some(c => c.id === camera.id)) {
      wsClient.send({
        type: 'stop_stream',
        data: {
          cameraId: camera.id
        }
      })
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
        // 创建一个超时检测
        const timeoutId = setTimeout(() => {
          console.log('检测超时:', camera.name)
          resolve()
        }, 3000) // 给每个摄像头3秒的检测时间

        // 创建一个一次性的消息处理器
        const handler = (message: WebSocketMessage) => {
          if (message.type === 'camera_status' && message.data.cameraId === camera.id) {
            clearTimeout(timeoutId) // 清除超时定时器
            wsClient.removeMessageHandler(handler) // 移除这个临时处理器
            resolve()
          }
        }

        wsClient.addMessageHandler(handler)
      })

      // 检测完成后等待一小段时间再检测下一个，避免并发
      await new Promise(resolve => setTimeout(resolve, 500))
    }

    // 检测完成后显示提示
    ElMessage({
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

// 处理WebSocket消息
const handleWebSocketMessage = (message: WebSocketMessage) => {
  const { type, data } = message

  switch (type) {
    case 'camera_status':
      // 更新摄像头状态
      const targetCamera = cameras.value.find(c => c.id === data.cameraId)
      if (targetCamera) {
        const oldStatus = targetCamera.status
        targetCamera.status = data.status || 0

        // 只在状态真正发生变化时才显示消息
        if (oldStatus !== targetCamera.status) {
          const statusText = formatDeviceStatus(targetCamera.status)
          const messageType = targetCamera.status === 1 ? 'success' : targetCamera.status === 2 ? 'warning' : 'error'

          // 如果摄像头离线或故障，从显示列表中移除
          if (targetCamera.status === 0 || targetCamera.status === 2) {
            targetCamera.streaming = false
            displayCameras.value = displayCameras.value.filter(c => c.id !== data.cameraId)
            // 停止该摄像头的流
            wsClient.send({
              type: 'stop_stream',
              data: {
                cameraId: data.cameraId
              }
            })
          }

          ElMessage({
            type: messageType,
            message: '摄像头 ' + targetCamera.name + ' ' + statusText
          })
        }
      }
      break

    case 'stream_stopped':
      // 找到对应的摄像头
      const stoppedCamera = cameras.value.find(c => c.id === data.cameraId)
      if (stoppedCamera) {
        stoppedCamera.streaming = false
      }
      break;
  }
}

// 获取状态类型
const getStatusType = (status: number): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  const types = ['danger', 'success', 'warning'] as const
  return types[status] as 'success' | 'warning' | 'info' | 'danger' | 'primary'
}

// 启动视频流
const startStream = (camera: Camera): Promise<void> => {
  return new Promise((resolve, reject) => {
    console.log('启动视频流:', camera.id, camera.rtspUrl);

    try {
      // 添加一个标记，防止重复启动
      if (camera.streaming) {
        console.log('视频流已经在运行中:', camera.id)
        resolve()
        return
      }

      camera.streaming = true
      wsClient.send({
        type: 'start_stream',
        data: {
          cameraId: camera.id,
          rtspUrl: camera.rtspUrl
        }
      })
      // 这里简单处理为发送后立即resolve，实际可根据stream_ready消息调整
      resolve()
    } catch (error) {
      console.error('启动视频流失败:', error)
      camera.streaming = false
      ElMessage.error('启动视频流失败，请稍后重试')
      reject(error)
    }
    // // 防止重复启动
    // if (camera.streaming) {
    //   console.log('视频流已经在运行中:', camera.id);
    //   resolve();
    //   return;
    // }

    // // 超时定时器（15秒未就绪则视为失败）
    // const timeoutTimer = setTimeout(() => {
    //   camera.streaming = false;
    //   wsClient.removeMessageHandler(handleStreamReady); // 清理监听器
    //   reject(new Error(`视频流启动超时（摄像头ID: ${camera.id}）`));
    // }, 15000);

    // // 临时监听stream_ready消息的处理器
    // const handleStreamReady = (message: WebSocketMessage) => {
    //   // 只处理当前摄像头的就绪消息
    //   if (message.type === 'stream_ready' && message.data.cameraId === camera.id) {
    //     clearTimeout(timeoutTimer); // 清除超时定时器
    //     wsClient.removeMessageHandler(handleStreamReady); // 移除临时监听器
    //     camera.streaming = true;
    //     console.log('视频流真正就绪:', camera.id);
    //     resolve(); // 确认启动成功
    //   }
    // };

    // try {
    //   // 添加临时监听器，等待stream_ready消息
    //   wsClient.addMessageHandler(handleStreamReady);
    //   // 发送启动流命令
    //   wsClient.send({
    //     type: 'start_stream',
    //     data: {
    //       cameraId: camera.id,
    //       rtspUrl: camera.rtspUrl
    //     }
    //   });
    // } catch (error) {
    //   clearTimeout(timeoutTimer);
    //   wsClient.removeMessageHandler(handleStreamReady);
    //   console.error('启动视频流失败:', error)
    //   camera.streaming = false
    //   ElMessage.error('启动视频流失败，请稍后重试')
    //   reject(error);
    // }
  });
};

// 处理摄像头选择
const handleCameraSelect = (camera: Camera) => {
  // 如果是故障状态，直接提示不可用
  if (camera.status === 2) {
    ElMessage.warning('该摄像头处于故障状态，暂不可用')
    return
  }

  if (camera.status !== 1) {
    ElMessage.warning('该摄像头当前不可用')
    return
  }

  // 检查WebSocket连接状态
  if (!wsClient.isConnected()) {
    // 尝试重置连接
    wsClient.resetConnectionState()
    ElMessage.warning('正在重新连接服务器，请几秒后再试')
    return
  }

  // 检查MQTT连接状态
  if (!mqttClient.isConnected()) {
    ElMessage.warning('MQTT尚未连接，请等待连接完成')
    return
  }

  // ========== 新增：调用地图组件的定位方法 ==========
  // 1. 校验摄像头经纬度是否有效
  const { longitude, latitude } = camera;
  const lng = Number(longitude);
  const lat = Number(latitude);
  
  if (longitude && latitude && !isNaN(lng) && !isNaN(lat)) {
    nextTick(() => {
      // 2. 调用子组件暴露的定位方法（缩放级别16可按需调整）
      if (mapRef.value) {
        mapRef.value.setCameraLocation(lng, lat, 16);
        ElMessage.success(`已定位到摄像头【${camera.name}】的位置`);
      } else {
        ElMessage.warning('地图组件尚未加载完成，无法定位');
      }
    });
  } else if (!longitude || !latitude) {
    ElMessage.warning('该摄像头未配置经纬度信息，无法定位');
  } else {
    ElMessage.warning('该摄像头经纬度格式错误，无法定位');
  }
  // ========== 地图定位逻辑结束 ==========

  // 设置当前活跃摄像头（用于关键帧显示和抽屉面板）
  activeCamera.value = camera

  // 处理显示列表中的摄像头
  if (isActiveCamera(camera.id)) {
    // 如果已经在显示，则从显示列表中移除
    displayCameras.value = displayCameras.value.filter(c => c.id !== camera.id)
    // 停止该摄像头的流
    wsClient.send({
      type: 'stop_stream',
      data: {
        cameraId: camera.id
      }
    })
  } else {
    // 如果未显示且显示列表未满，则添加到显示列表
    if (displayCameras.value.length < layout.value) {
      // 列表未满：直接启动并添加
      startStream(camera)
        .then(() => {
          displayCameras.value.push(camera);
          // 启动成功后执行MQTT操作
          publishVideoMqttMessage(camera);
        })
        .catch((error) => {
          console.error('启动视频流失败:', error);
          ElMessage.error(`启动失败: ${error.message}`);
        });
    } else {
      // 列表已满：替换最早的摄像头
      const removedCamera = displayCameras.value.shift();
      if (removedCamera) {
        // 停止被替换的摄像头
        wsClient.send({
          type: 'stop_stream',
          data: { cameraId: removedCamera.id }
        });
      }
      // 启动新摄像头
      startStream(camera)
        .then(() => {
          displayCameras.value.push(camera);
          // 启动成功后执行MQTT操作
          publishVideoMqttMessage(camera);
          ElMessage.info(`已达到${layout.value}个摄像头上限，自动替换最早添加的摄像头`);
        })
        .catch((error) => {
          console.error('启动视频流失败:', error);
          ElMessage.error(`启动失败: ${error.message}`);
        });
    }
  }
};

// 发布视频流相关的MQTT消息
const publishVideoMqttMessage = (camera: Camera) => {
  const publishData = {
    videoUrl: camera.rtspUrl,
    videoId: camera.id.toString(),
    deviceName: camera.name,
    startTime: new Date().toISOString().replace('T', ' ').slice(0, 19)
  };

  // 发布到指定主题
  mqttClient.publish('/UAV/videoTopic/post', publishData);
  console.log('MQTT消息已发布:', publishData);

  // 订阅检测结果主题（确保只订阅一次，可根据实际需求调整）
  mqttClient.subscribe('/UAV/videoAlarmTopic/post');

  // 注册消息处理器（确保只注册一次，可根据实际需求调整）
  mqttClient.registerHandler('/UAV/videoAlarmTopic/post', handleDetectionData);
};

// 全局去重：避免同一视频同一物体重复存储（跨帧/跨批量生效）
const savedObjectIds: { [videoId: string]: Set<string> } = {};

// 全局聚合缓存：存储每个视频的物体置信度和时间范围（跨帧累积）
const globalAggregateCache: {
  [videoId: string]: {
    aggregatedObjects: { [objectID: string]: { type: string; maxScore: number } };
    firstStartTime: string; // 视频最早开始时间
    latestEndTime: string;  // 视频最新结束时间
    videoFileUrl: string;
  };
} = {};

// 视频结束判定：收到最后一帧后延迟1秒执行存储（确保所有帧都已处理）
const VIDEO_FINISH_DELAY = 1000;
const finishTimers: { [videoId: string]: NodeJS.Timeout } = {};

const handleDetectionData = (message: MqttMessage) => {
  console.log('收到检测结果（单条消息，含多帧数据）:', message);

  // 容错：消息格式错误（重点校验 objectDetect 字段是否存在）
  if (!message || !message.videoId || !message.result || !Array.isArray(message.result)) {
    console.warn('检测结果格式不正确或缺少核心字段（videoId/result）');
    ElMessage.warning('检测结果格式不正确');
    return;
  }

  // -------------------------- 1. 提取当前消息的核心信息 --------------------------
  const { videoId, startTime, endTime, videoFileUrl, result } = message;

  // 初始化当前视频的全局缓存（首次处理该视频时）
  if (!globalAggregateCache[videoId]) {
    globalAggregateCache[videoId] = {
      aggregatedObjects: {}, // 跨帧聚合物体（保留最高置信度）
      firstStartTime: startTime || new Date().toLocaleString(), // 取第一条消息的startTime
      latestEndTime: endTime || new Date().toLocaleString(),   // 实时更新为最新帧的endTime
      videoFileUrl: videoFileUrl || '待上传'
    };
  }

  // 更新视频的最新结束时间（每帧消息都更新，确保是完整时间范围）
  if (endTime) {
    globalAggregateCache[videoId].latestEndTime = endTime;
  }

  // -------------------------- 2. 跨帧聚合：保留同一物体的最高置信度（修复 type 问题） --------------------------
  const { aggregatedObjects } = globalAggregateCache[videoId];

  result.forEach((detection, idx) => {
    // 重点：打印检测结果，确认类别字段名（关键排查！）
    console.log(`第${idx + 1}个检测结果：`, detection);

    // 1. 确认类别字段（根据算法端返回的实际字段名修改！）
    // 假设算法端返回的类别字段是 objectDetect，若不是则替换为 label/className 等
    const type = detection.objectDetect || '未知类别';
    const objectID = detection.objectID;
    const score = detection.score;

    // 容错：跳过缺少 objectID/有效类别的结果（避免存储空类型）
    if (!objectID || type === '未知类别' || isNaN(score)) {
      console.warn(`无效检测结果（缺少ID/类别/置信度），跳过:`, detection);
      return;
    }

    // 2. 聚合逻辑：同一objectID跨帧保留最高置信度
    if (!aggregatedObjects[objectID]) {
      // 新物体：直接存入
      aggregatedObjects[objectID] = { type, maxScore: score };
      console.log(`视频${videoId}新增物体：ID=${objectID}，类别=${type}，初始置信度=${score}`);
    } else {
      // 已有物体：更新最高置信度
      if (score > aggregatedObjects[objectID].maxScore) {
        aggregatedObjects[objectID].maxScore = score;
        console.log(`视频${videoId}物体${objectID}最高置信度更新为:`, score);
      }
    }
  });

  // -------------------------- 3. 延迟存储：确保所有帧都已处理 --------------------------
  if (finishTimers[videoId]) {
    clearTimeout(finishTimers[videoId]);
  }

  finishTimers[videoId] = setTimeout(() => {
    const cache = globalAggregateCache[videoId];
    if (!cache || Object.keys(cache.aggregatedObjects).length === 0) {
      console.log(`视频${videoId}无有效物体，跳过存储`);
      delete globalAggregateCache[videoId];
      delete finishTimers[videoId];
      return;
    }

    // -------------------------- 4. 修复 location：从完整摄像头列表匹配（关键！） --------------------------
    // 错误做法：从 displayCameras（当前显示的摄像头）匹配
    // const targetCamera = displayCameras.value.find(c => c.id.toString() === videoId);
    // 正确做法：从 cameras（所有摄像头列表）匹配
    const targetCamera = cameras.value.find(c => c.id.toString() === videoId);
    const cameraLocation = targetCamera?.location || '未知位置';

    // 打印日志，确认摄像头是否匹配成功
    if (!targetCamera) {
      console.warn(`未找到 videoId=${videoId} 对应的摄像头，location 设为默认`);
    } else {
      console.log(`匹配到摄像头：${targetCamera.name}，位置：${targetCamera.location}`);
    }

    // -------------------------- 5. 统一存储：每个objectID仅存1次 --------------------------
    Object.entries(cache.aggregatedObjects).forEach(([objectID, { type, maxScore }]) => {
      // 初始化去重集合
      if (!savedObjectIds[videoId]) {
        savedObjectIds[videoId] = new Set();
      }

      // 去重：已保存过的物体跳过
      if (savedObjectIds[videoId].has(objectID)) {
        console.log(`视频${videoId}物体${objectID}（类别：${type}）已存储，跳过`);
        return;
      }

      // 执行存储
      console.log(`存储视频${videoId}物体: ID=${objectID}，类别=${type}，位置=${cameraLocation}，最高置信度=${maxScore}`);
      createAbnormalEvent({
        cameraId: Number(videoId),
        eventTime: new Date().toISOString(),
        location: cameraLocation, // 从完整摄像头列表获取
        level: maxScore >= 0.7 ? 2 : 1,
        imageUrl: cache.videoFileUrl,
        status: 0,
        type: type, 
        description: `物体【${type}】(ID: ${objectID}）在视频时间段「${cache.firstStartTime} 至 ${cache.latestEndTime}」内被检测到，
                      位置：${cameraLocation}，最高置信度：${(maxScore * 100).toFixed(1)}%`
      });

      // 标记为已保存
      savedObjectIds[videoId].add(objectID);
    });

    // 清理缓存和定时器
    console.log(`视频${videoId}所有帧处理完成，共存储${Object.keys(cache.aggregatedObjects).length}个唯一物体`);
    delete globalAggregateCache[videoId];
    delete finishTimers[videoId];
  }, VIDEO_FINISH_DELAY);
};


onMounted(() => {
  // 添加WebSocket消息处理器
  wsClient.addMessageHandler(handleWebSocketMessage)
  // 确保WebSocket连接状态正确，如果需要则重置连接
  wsClient.resetConnectionState()
  // 获取摄像头列表
  fetchCameras()
  // 连接MQTT服务器
  mqttClient.connect()
})

onBeforeUnmount(() => {
  // 移除WebSocket消息处理器
  wsClient.removeMessageHandler(handleWebSocketMessage)
  // 停止所有视频流
  displayCameras.value.forEach(camera => {
    wsClient.send({
      type: 'stop_stream',
      data: {
        cameraId: camera.id
      }
    })
  })
  // 关闭WebSocket连接
  wsClient.close()
  // 移除MQTT消息处理器
  mqttClient.removeHandler('/UAV/videoAlarmTopic/post')
  // 断开MQTT连接
  mqttClient.disconnect()
})
</script>

<style lang="scss" scoped>
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
    margin-bottom: 0;

    .right {
      display: flex;
      gap: 10px;
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
          grid-template-columns: repeat(2, 1fr);
          grid-template-rows: repeat(2, 1fr);
        }

        &.grid-9 {
          grid-template-columns: repeat(3, 1fr);
          grid-template-rows: repeat(3, 1fr);
        }
      }

      .video-item {
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
  .monitor-container {
    flex-direction: column;

    .main-video {
      min-height: 400px;
    }

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