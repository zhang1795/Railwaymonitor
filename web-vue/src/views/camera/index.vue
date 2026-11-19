<template>
  <div class="camera">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-button type="primary" @click="handleCreate">
          <el-icon>
            <Plus />
          </el-icon>
          新增摄像头
        </el-button>
        <el-button type="primary" @click="checkAllCamerasStatus" :loading="checkingStatus">
          <el-icon>
            <Refresh :class="{ 'rotate-icon': checkingStatus }" />
          </el-icon>
          {{ checkingStatus ? '检测中...' : '检测状态' }}
        </el-button>
      </div>
    </div>

    <!-- 搜索表单 -->
    <el-form :model="queryParams" inline class="search-form">
      <el-form-item label="设备名称">
        <el-input v-model="queryParams.name" placeholder="请输入设备名称" clearable />
      </el-form-item>
      <el-form-item label="安装位置">
        <el-input v-model="queryParams.location" placeholder="请输入安装位置" clearable />
      </el-form-item>
      <el-form-item label="IP地址">
        <el-input v-model="queryParams.ipAddress" placeholder="请输入IP地址" clearable />
      </el-form-item>
      <el-form-item label="设备状态">
        <el-select v-model="queryParams.status" placeholder="请选择设备状态" clearable class="status-select">
          <el-option v-for="status in [0, 1, 2, 3]" :key="status" :label="formatDeviceStatus(status)" :value="status" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="handleQuery">
          <el-icon>
            <Search />
          </el-icon>
          查询
        </el-button>
        <el-button @click="handleReset">
          <el-icon>
            <Refresh />
          </el-icon>
          重置
        </el-button>
      </el-form-item>
    </el-form>

    <!-- 数据表格 -->
    <el-table v-loading="loading" :data="list" border stripe>
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column prop="name" label="设备名称" min-width="120" show-overflow-tooltip />
      <el-table-column prop="location" label="安装位置" min-width="130" show-overflow-tooltip />
      <el-table-column label="经纬度" min-width="180" align="center" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.longitude && row.latitude">
            {{ row.longitude.toFixed(6) }}, {{ row.latitude.toFixed(6) }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="ipAddress" label="IP地址" width="120" show-overflow-tooltip />
      <el-table-column prop="rtspUrl" label="RTSP地址" min-width="260" show-overflow-tooltip />
      <el-table-column prop="status" label="设备状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="checkingStatus && row.status !== 2" type="info" effect="plain" class="checking-tag">
            <span class="checking-text">检测中...</span>
          </el-tag>
          <el-tag v-else :type="getStatusType(row.status)">
            {{ formatDeviceStatus(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="faultType" label="故障类型" width="120" align="center">
        <template #default="{ row }">
          <span v-if="row.status === 2">{{ formatFaultType(row.faultType) }}</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="createTime" label="创建时间" width="180" align="center">
        <template #default="{ row }">
          {{ formatDateTime(row.createTime) }}
        </template>
      </el-table-column>
      <el-table-column label="后台检测" min-width="260">
        <template #default="{ row }">
          <MonitoringStatus :row="monitorRows[row.id]" :healthy="monitorHealthy" :label="monitoring.label(row.id)" :report-at="monitoring.reportAt(row.id)" />
          <el-button link :type="monitorRows[row.id]?.enabled ? 'danger' : 'primary'" :disabled="!monitorLoaded" :loading="changingMonitoring.has(row.id)" @click="changeMonitoring(row.id)">
            {{ monitorRows[row.id]?.enabled ? '停用后台检测' : '启用后台检测' }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="风险判定" min-width="170">
        <template #default="{row}">
          <el-tooltip :content="row.riskRule ? ruleSummary(row.riskRule) : '暂未取得规则'" placement="top">
            <el-tag :type="row.riskRule?.enabled ? 'success' : 'info'">{{modeLabel(row.riskRule)}}</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleUpdate(row)">
            <el-icon>
              <Edit />
            </el-icon>
            编辑
          </el-button>
          <el-button link type="primary" @click="ruleCameraId=row.id;ruleVisible=true">风险规则</el-button>
          <el-button link type="danger" @click="handleDelete(row)">
            <el-icon>
              <Delete />
            </el-icon>
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <pagination v-model:current="queryParams.current" v-model:size="queryParams.size" :total="total"
      @change="getList" />

    <!-- 新增/编辑对话框 -->
    <RiskRuleDialog v-model="ruleVisible" :camera-id="ruleCameraId" :running="monitorRows[ruleCameraId]?.enabled" :stopping="changingMonitoring.has(ruleCameraId)" @saved="getList" @stop="stopRuleCamera" />
    <el-dialog v-model="dialogVisible" :title="dialogType === 'create' ? '新增摄像头' : '编辑摄像头'" width="600px"
      @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="设备名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入设备名称" />
        </el-form-item>

        <el-form-item label="安装位置" prop="location">
          <el-input v-model="form.location" placeholder="请输入安装位置" />
        </el-form-item>

        <el-form-item label="经度"><el-input v-model="form.longitude" placeholder="-180 至 180，经度在前" /></el-form-item>
        <el-form-item label="纬度"><el-input v-model="form.latitude" placeholder="-90 至 90，纬度在后" /></el-form-item>
        <el-form-item><small>使用高德 GCJ-02 坐标。地图不可用时可手工填写经纬度；请先转换其他坐标系，不会自动填入 (0,0)。</small></el-form-item>
        <template v-if="dialogType === 'create'">
          <el-form-item>
            <el-button type="primary" @click="openMapDialog">在地图上选择位置</el-button>
            <span v-if="form.longitude && form.latitude" class="coordinate-info">
              已选坐标: {{ form.longitude }}, {{ form.latitude }}
            </span>
          </el-form-item>
        </template>


        <el-form-item label="IP地址" prop="ipAddress">
          <el-input v-model="form.ipAddress" placeholder="请输入IP地址" />
        </el-form-item>
        <el-form-item label="RTSP地址" prop="rtspUrl">
          <el-input v-model="form.rtspUrl" placeholder="请输入RTSP地址" />
        </el-form-item>
        <el-form-item v-if="dialogType === 'update'" label="设备状态" prop="status">
          <el-select v-model="form.status" placeholder="请选择设备状态">
            <el-option v-for="status in [0, 1, 2, 3]" :key="status" :label="formatDeviceStatus(status)" :value="status" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="dialogType === 'update' && form.status === 2" label="故障类型" prop="faultType">
          <el-select v-model="form.faultType" placeholder="请选择故障类型">
            <el-option value="network" label="网络故障" />
            <el-option value="hardware" label="硬件故障" />
            <el-option value="software" label="软件故障" />
            <el-option value="power" label="电源故障" />
            <el-option value="other" label="其他故障" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>

    <!-- 地图选择弹窗（使用修改后的地图组件） -->
    <el-dialog v-model="mapDialogVisible" title="选择摄像头位置" width="80%" height="90vh" destroy-on-close>
      <!-- 引入地图组件，监听自定义事件接收经纬度 -->
      <MapComponent @coordinate-select="handleCoordinateSelect" />
      <!-- 弹窗footer -->
      <template #footer>
        <el-button @click="mapDialogVisible = false">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { Camera } from '@/types/camera'
import { getCameraList, createCamera, updateCamera, deleteCamera, updateCameraStatus } from '@/api/camera'
import { formatDateTime, formatDeviceStatus } from '@/utils/format'
import { validateIP, validateRTSP } from '@/utils/validate'
import Pagination from '@/components/Pagination/index.vue'
import MapComponent from '@/components/Map/index.vue' // 引入地图组件
import wsClient from '@/utils/websocket'
import type { WebSocketMessage } from '@/utils/websocket'
import { useMonitoring } from '@/composables/useMonitoring'
import MonitoringStatus from '@/components/MonitoringStatus/index.vue'
import RiskRuleDialog from '@/components/RiskRuleDialog/index.vue'
import {modeLabel,ruleSummary} from '@/utils/ruleSummary'
async function stopRuleCamera(camera:number){try{await monitoring.change(camera,false)}catch{}}
const ruleVisible=ref(false),ruleCameraId=ref(0)

const monitoring = useMonitoring()
const { rows:monitorRows, loaded:monitorLoaded, healthy:monitorHealthy, changing:changingMonitoring } = monitoring
const changeMonitoring = async (id:number) => {
  try {
    const enabled=!monitorRows.value[id]?.enabled
    await monitoring.change(id,enabled)
    ElMessage.success(enabled?'已启用后台检测':'已请求停用后台检测')
  } catch { /* The request layer displays the actual error. */ }
}

// 查询参数
const queryParams = reactive({
  current: 1,
  size: 10,
  name: undefined,
  location: undefined,
  ipAddress: undefined,
  status: undefined,
})

// 数据列表
const list = ref<Camera[]>([])
const total = ref(0)
const loading = ref(false)
const checkingStatus = ref(false)
const pendingCheckCameraIds = ref<Set<number>>(new Set())

// 地图相关核心变量
const mapDialogVisible = ref(false)

// 表单相关
const formRef = ref<FormInstance>()
const dialogVisible = ref(false)
const dialogType = ref<'create' | 'update'>('create')
const submitLoading = ref(false)

// 核心：使用longitude/latitude字段，初始为空字符串
const form = reactive({
  id: 0,
  name: '',
  location: '',
  longitude: '', // 经度（字符串类型）
  latitude: '', // 纬度（字符串类型）
  ipAddress: '',
  rtspUrl: '',
  status: 1,
  faultType: '',
})

// 表单校验规则
const rules: FormRules = {
  name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  location: [{ required: true, message: '请输入安装位置', trigger: 'blur' }],
  ipAddress: [
    { required: true, message: '请输入IP地址', trigger: 'blur' },
    {
      validator: (rule: any, value: string, callback: any) => {
        if (!validateIP(value)) {
          callback(new Error('请输入正确的IP地址'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    },
  ],
  rtspUrl: [

    {
      validator: (rule: any, value: string, callback: any) => {
        if ((dialogType.value === 'create' || value) && !validateRTSP(value)) {
          callback(new Error('请输入正确的RTSP地址'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    },
  ],
  faultType: [
    {
      required: true,
      message: '请选择故障类型',
      trigger: 'change',
      validator: (rule: any, value: string, callback: any) => {
        if (form.status === 2 && !value) {
          callback(new Error('请选择故障类型'))
        } else {
          callback()
        }
      }
    }
  ]
}

// 监听状态变化，清空非故障状态的故障类型
watch(() => form.status, (newStatus) => {
  if (newStatus !== 2) {
    form.faultType = ''
  } else if (!form.faultType) {
    form.faultType = 'other'
  }
}, { immediate: true })

// 打开地图弹窗
const openMapDialog = () => {
  mapDialogVisible.value = true
}

// 核心：接收地图组件传递的经纬度
const handleCoordinateSelect = (coordinate: { longitude: string, latitude: string }) => {
  // 赋值到表单
  form.longitude = coordinate.longitude
  form.latitude = coordinate.latitude

  // 提示用户
  ElMessage.success(`已选择坐标：${coordinate.longitude}, ${coordinate.latitude}`)

  // 可选：自动关闭地图弹窗（也可以保留弹窗让用户确认）
  // mapDialogVisible.value = false
}

// 新增摄像头（初始化经纬度为空）
const handleCreate = () => {
  dialogType.value = 'create'
  dialogVisible.value = true

  // 重置经纬度
  form.longitude = ''
  form.latitude = ''
}

// 编辑摄像头（回显longitude/latitude）
const handleUpdate = (row: Camera) => {
  dialogType.value = 'update'
  Object.assign(form, row, {rtspUrl:''})

  // 经纬度回显（保留6位小数）
  form.longitude = row.longitude!=null ? row.longitude.toFixed(6) : ''
  form.latitude = row.latitude!=null ? row.latitude.toFixed(6) : ''
  dialogVisible.value = true
}

// 删除摄像头
const handleDelete = (row: Camera) => {
  ElMessageBox.confirm('确认删除该摄像头？删除后无法恢复！', '警告', {
    type: 'warning',
  })
    .then(async () => {
      await deleteCamera(row.id)
      ElMessage.success('删除成功')
      getList()
    })
    .catch(() => { })
}

// 重置表单
const resetForm = () => {
  if (formRef.value) {
    formRef.value.resetFields()
  }
  Object.assign(form, {
    id: 0,
    name: '',
    location: '',
    longitude: '',
    latitude: '',
    ipAddress: '',
    rtspUrl: '',
    status: 1,
    faultType: '',
  })
}

// 提交表单（仅保留基础非空判断，无复杂验证）
const submitForm = async () => {
  if(submitLoading.value)return
  const longitude=String(form.longitude).trim(),latitude=String(form.latitude).trim()
  const unspecified=dialogType.value==='update' && !longitude && !latitude
  if (!unspecified && (!longitude || !latitude || !Number.isFinite(Number(longitude)) || !Number.isFinite(Number(latitude)) || Math.abs(Number(longitude))>180 || Math.abs(Number(latitude))>90)) {
    ElMessage.error('请手工填写有效经纬度，或在地图上选择安装位置')
    return
  }

  if (!formRef.value) return
  await formRef.value.validate()
  submitLoading.value = true

  try {
    if (form.status !== 2) {
      form.faultType = ''
    }

    // 提交数据：转换经纬度为数字
    const submitData = {
      ...form,
      longitude: unspecified ? undefined : Number(longitude),
      latitude: unspecified ? undefined : Number(latitude),
    }

    if (dialogType.value === 'create') {
      await createCamera({...submitData,longitude:Number(longitude),latitude:Number(latitude)})
      ElMessage.success('新增成功')
    } else {
      await updateCamera(submitData)
      ElMessage.success('更新成功')
    }

    dialogVisible.value = false
    getList()
  } catch (error) {
    console.error('提交失败:', error)
    ElMessage.error('操作失败，请重试')
  } finally {
    submitLoading.value = false
  }
}

// 检查所有摄像头状态（原逻辑保留）
const checkAllCamerasStatus = async () => {
  if (loading.value || checkingStatus.value) return

  checkingStatus.value = true
  pendingCheckCameraIds.value.clear()

  try {
    ElMessage({
      message: '正在检测所有摄像头状态，请稍候...',
      type: 'info',
      duration: 2000
    })

    let checkCount = 0
    list.value.forEach(camera => {
      if (camera.status !== 2) {
        checkCount++
        pendingCheckCameraIds.value.add(camera.id)
        wsClient.send({
          type: 'check_camera',
          data: {
            cameraId: camera.id,
            rtspUrl: camera.rtspUrl
          }
        })
      }
    })

    if (checkCount === 0) {
      ElMessage({
        message: '没有可检测的摄像头设备',
        type: 'warning',
        duration: 2000
      })
      checkingStatus.value = false
      pendingCheckCameraIds.value.clear()
      return
    }

    setTimeout(() => {
      if (checkingStatus.value && pendingCheckCameraIds.value.size > 0) {
        console.warn('有摄像头检测超时未响应:', Array.from(pendingCheckCameraIds.value))
        checkingStatus.value = false
        pendingCheckCameraIds.value.clear()
        ElMessage({
          message: '摄像头状态检测完成 (部分设备未响应)',
          type: 'warning',
          duration: 2000
        })
      }
    }, 15000)

  } catch (error) {
    console.error('检查摄像头状态失败:', error)
    ElMessage.error('检查摄像头状态失败')
    checkingStatus.value = false
    pendingCheckCameraIds.value.clear()
  }
}

// 处理WebSocket消息（原逻辑保留）
const handleWebSocketMessage = async (message: WebSocketMessage) => {
  const { type, data } = message

  if (type === 'camera_status') {
    const targetCamera = list.value.find(c => c.id === data.cameraId)
    if (targetCamera) {
      const oldStatus = targetCamera.status
      const newStatus = data.status || 0

      if (checkingStatus.value && pendingCheckCameraIds.value.has(data.cameraId)) {
        pendingCheckCameraIds.value.delete(data.cameraId)

        if (pendingCheckCameraIds.value.size === 0 && checkingStatus.value) {
          checkingStatus.value = false
          ElMessage({
            message: '摄像头状态检测完成',
            type: 'success',
            duration: 2000
          })
        }
      }

      if (oldStatus !== newStatus) {
        targetCamera.status = newStatus

        try {
          await updateCameraStatus(targetCamera.id, newStatus)

          const statusText = newStatus === 1 ? '在线' : '离线'
          const messageType = newStatus === 1 ? 'success' : 'warning'

          ElMessage({
            type: messageType,
            message: '摄像头 ' + targetCamera.name + ' ' + statusText
          })
        } catch (error) {
          console.error('更新摄像头状态失败:', error)
          targetCamera.status = oldStatus
          ElMessage.error('更新摄像头状态失败')
        }
      }
    }
  }
}

// 格式化故障类型（原逻辑保留）
const formatFaultType = (type: string) => {
  const typeMap: Record<string, string> = {
    'network': '网络故障',
    'hardware': '硬件故障',
    'software': '软件故障',
    'power': '电源故障',
    'other': '其他故障'
  }
  return typeMap[type] || '未知故障'
}

// 获取状态类型（原逻辑保留）
const getStatusType = (status: number): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  const types = ['danger', 'success', 'warning'] as const
  return types[status] as 'success' | 'warning' | 'info' | 'danger' | 'primary'
}

// 获取数据列表（原逻辑保留）
const getList = async () => {
  loading.value = true
  try {
    const res = await getCameraList(queryParams)
    list.value = res.records
    total.value = res.total
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 查询（原逻辑保留）
const handleQuery = () => {
  queryParams.current = 1
  getList()
}

// 重置（原逻辑保留）
const handleReset = () => {
  Object.assign(queryParams, {
    current: 1,
    size: 10,
    name: undefined,
    location: undefined,
    ipAddress: undefined,
    status: undefined,
  })
  getList()
}

// 生命周期（原逻辑保留）
onMounted(() => {
  getList()
  wsClient.addMessageHandler(handleWebSocketMessage)
  if (!wsClient.isConnected()) {
    wsClient.connect()
  }
})

onBeforeUnmount(() => {
  wsClient.removeMessageHandler(handleWebSocketMessage)
  wsClient.close()
})
</script>

<style lang="scss" scoped>
.camera {
  padding: 20px;

  .toolbar {
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;

    .left {
      display: flex;
      gap: 10px;
    }
  }

  .search-form {
    margin-bottom: 20px;

    :deep(.el-form-item) {
      margin-bottom: 18px;
      margin-right: 18px;

      .el-input {
        width: 200px;
      }

      .status-select {
        width: 200px;
      }
    }
  }

  // 经纬度提示样式
  .coordinate-info {
    margin-left: 10px;
    color: #666;
    font-size: 14px;
  }

  // 旋转动画
  .rotate-icon {
    animation: rotate 1.5s linear infinite;
  }
}

@keyframes rotate {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}
</style>
