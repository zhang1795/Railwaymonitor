<template>
  <div class="Abnormal">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="left">
        <el-button type="primary" @click="handleCreate">
          <el-icon>
            <Plus />
          </el-icon>
          新增事件
        </el-button>
        <el-button type="danger" :disabled="selectedIds.length === 0" @click="handleBatchDelete">
          <el-icon>
            <Delete />
          </el-icon>
          批量删除
        </el-button>
      </div>
    </div>

    <!-- 搜索表单 -->
    <el-form :model="queryParams" inline class="search-form">
      <el-form-item label="摄像头">
        <el-select v-model="queryParams.cameraId" placeholder="请选择摄像头" clearable class="form-select">
          <el-option v-for="camera in cameraOptions" :key="camera.id" :label="camera.name" :value="camera.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="事件位置">
        <el-input v-model="queryParams.location" placeholder="请输入事件位置" clearable />
      </el-form-item>
      <el-form-item label="异常等级">
        <el-select v-model="queryParams.level" placeholder="请选择异常等级" clearable class="form-select">
          <el-option v-for="level in [0, 1, 2, 3, 4, 5]" :key="level" :label="formatAbnormalLevel(level)"
            :value="level" />
        </el-select>
      </el-form-item>
      <el-form-item label="处理状态">
        <el-select v-model="queryParams.status" placeholder="请选择处理状态" clearable class="form-select">
          <el-option v-for="status in [0, 1, 2]" :key="status" :label="formatStatus(status)" :value="status" />
        </el-select>
      </el-form-item>
      <el-form-item label="事件时间">
        <el-date-picker v-model="timeRange" type="datetimerange" range-separator="至" start-placeholder="开始时间"
          end-placeholder="结束时间" value-format="YYYY-MM-DDTHH:mm:ss" :default-time="[
            new Date(2000, 1, 1, 0, 0, 0),
            new Date(2000, 1, 1, 23, 59, 59),
          ]" />
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
    <el-table v-loading="loading" :data="list" border stripe @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" />
      <el-table-column type="index" label="序号" width="60" align="center" />
      <el-table-column prop="cameraName" label="摄像头" min-width="120" show-overflow-tooltip />
      <el-table-column prop="location" label="位置" min-width="120" show-overflow-tooltip />
      <el-table-column prop="level" label="异常等级" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getAbnormalLevelType(row.level)">
            {{ row.level ? formatAbnormalLevel(row.level) : '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="处理状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)">
            {{ formatStatus(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="eventTime" label="发生时间" width="180" align="center">
        <template #default="{ row }">
          {{ formatDateTime(row.eventTime) }}
        </template>
      </el-table-column>
      <el-table-column prop="handlerName" label="处理人" width="120" align="center" />
      <el-table-column prop="handleTime" label="处理时间" width="180" align="center">
        <template #default="{ row }">
          {{ row.handleTime ? formatDateTime(row.handleTime) : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleDetail(row)">
            <el-icon>
              <View />
            </el-icon>
            详情
          </el-button>
          <el-button link type="primary" @click="handleEdit(row)">
            <el-icon>
              <Edit />
            </el-icon>
            编辑
          </el-button>
          <el-button v-if="row.status === 0" link type="primary" @click="handleProcess(row)">
            <el-icon>
              <VideoPlay />
            </el-icon>
            处理
          </el-button>
          <el-button v-if="row.status === 1" link type="success" @click="handleComplete(row)">
            <el-icon><Select /></el-icon>
            完成
          </el-button>
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

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" title="异常事件详情" size="600px">
      <template #default>
        <div class="detail">
          <div class="detail-item">
            <span class="label">摄像头：</span>
            <span class="value">{{ detail?.cameraName }}</span>
          </div>
          <div class="detail-item">
            <span class="label">位置：</span>
            <span class="value">{{ detail?.location }}</span>
          </div>
          <div class="detail-item">
            <span class="label">异常等级：</span>
            <span class="value">
              <el-tag :type="getAbnormalLevelType(detail?.level)">
                {{ detail?.level ? formatAbnormalLevel(detail.level) : '-' }}
              </el-tag>
            </span>
          </div>
          <div class="detail-item">
            <span class="label">处理状态：</span>
            <span class="value">
              <el-tag :type="getStatusType(detail?.status)">
                {{ formatStatus(detail?.status) }}
              </el-tag>
            </span>
          </div>
          <div class="detail-item">
            <span class="label">发生时间：</span>
            <span class="value">{{ formatDateTime(detail?.eventTime) }}</span>
          </div>
          <div class="detail-item video-map-item">
            <!-- 现场视频区域 -->
            <div class="content-group">
              <span class="label">现场视频：</span>
              <div class="value video-container">
                <el-image v-if="detail?.imageUrl" :src="detail.imageUrl" :preview-src-list="[detail.imageUrl]"
                  fit="cover" class="image" />
                <span v-else>暂无视频</span>
              </div>
            </div>
            <!-- 地图区域（新增“地图”标签） -->
            <div class="content-group">
              <span class="label">地图：</span>
              <div class="value map-container">
                <MapComponent ref="mapRef" class="map" :show-map-controls="false" />
                <span v-if="!detail?.cameraId" class="map-tip">暂无摄像头信息</span>
              </div>
            </div>
          </div>
          <div class="detail-item">
            <span class="label">事件描述：</span>
            <span class="value">{{ detail?.description || '暂无描述' }}</span>
          </div>
          <div class="detail-item">
            <span class="label">处理人：</span>
            <span class="value">{{ detail?.handlerName || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="label">处理时间：</span>
            <span class="value">{{ detail?.handleTime ? formatDateTime(detail.handleTime) : '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="label">处理结果：</span>
            <span class="value">{{ detail?.handleResult || '-' }}</span>
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- 处理对话框 -->
    <el-dialog v-model="handleVisible" title="处理异常事件" width="500px">
      <el-form ref="handleFormRef" :model="handleForm" :rules="handleRules" label-width="100px">
        <el-form-item label="处理结果" prop="handleResult">
          <el-input v-model="handleForm.handleResult" type="textarea" :rows="4" placeholder="请输入处理结果" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitHandle">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editVisible" :title="editForm.id ? '编辑异常事件' : '新增异常事件'" width="500px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="100px">
        <el-form-item label="摄像头" prop="cameraId">
          <el-select v-model="editForm.cameraId" placeholder="请选择摄像头">
            <el-option v-for="item in cameras" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="位置" prop="location">
          <el-input v-model="editForm.location" placeholder="请输入位置" />
        </el-form-item>
        <el-form-item label="异常等级" prop="level">
          <el-select v-model="editForm.level" placeholder="请选择异常等级">
            <el-option v-for="level in [1, 2, 3, 4, 5]" :key="level" :label="formatAbnormalLevel(level)"
              :value="level" />
          </el-select>
        </el-form-item>
        <el-form-item label="处理状态" prop="status">
          <el-select v-model="editForm.status" placeholder="请选择处理状态">
            <el-option v-for="status in [0, 1, 2]" :key="status" :label="formatStatus(status)" :value="status" />
          </el-select>
        </el-form-item>
        <el-form-item label="事件描述" prop="description">
          <el-input v-model="editForm.description" type="textarea" :rows="4" placeholder="请输入事件描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitEdit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useUserStore } from '@/stores/user'
import type { AbnormalEvent, AbnormalEventQueryParams } from '@/types/Abnormal'
import type { Camera } from '@/types/camera'
import { getAbnormalEventList, getAbnormalEventById, handleAbnormalEvent, updateAbnormalEventStatus, deleteAbnormalEvent, updateAbnormalEvent, batchDeleteAbnormalEvents, createAbnormalEvent } from '@/api/Abnormal'
import { getCameraList } from '@/api/camera'
import { formatDateTime, formatAbnormalLevel, formatStatus } from '@/utils/format'
import Pagination from '@/components/Pagination/index.vue'
import type { PageQuery } from '@/types/common'
import MapComponent from '@/components/Map/index.vue'

// 定义地图组件ref
const mapRef = ref<InstanceType<typeof MapComponent> | null>(null)


const userStore = useUserStore()

// 查询参数
const queryParams = reactive<AbnormalEventQueryParams>({
  current: 1,
  size: 10,
  cameraId: undefined,
  location: undefined,
  level: undefined,
  status: undefined,
  startTime: undefined,
  endTime: undefined,
})

// 时间范围
const timeRange = ref<[string, string]>()

// 摄像头列表
const cameras = ref<Camera[]>([])

// 数据列表
const list = ref<AbnormalEvent[]>([])
const total = ref(0)
const loading = ref(false)

// 摄像头选项
const cameraOptions = ref<Array<{ id: number; name: string }>>([])

// 获取摄像头列表
const getCameras = async () => {
  try {
    const res = await getCameraList({ current: 1, size: 999 })
    cameraOptions.value = res.records
    cameras.value = res.records
  } catch (error) {
    console.error('获取摄像头列表失败:', error)
  }
}

// 获取数据列表
const getList = async () => {
  loading.value = true
  try {
    // 处理时间范围
    if (timeRange.value) {
      queryParams.startTime = timeRange.value[0]
      queryParams.endTime = timeRange.value[1]
    } else {
      queryParams.startTime = undefined
      queryParams.endTime = undefined
    }
    const res = await getAbnormalEventList(queryParams)
    list.value = res.records
    total.value = res.total
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 查询
const handleQuery = () => {
  queryParams.current = 1
  getList()
}

// 重置
const handleReset = () => {
  timeRange.value = undefined
  Object.assign(queryParams, {
    current: 1,
    size: 10,
    cameraId: undefined,
    location: undefined,
    level: undefined,
    status: undefined,
    startTime: undefined,
    endTime: undefined,
  })
  getList()
}

// 获取异常等级类型
const getAbnormalLevelType = (level: number | undefined | null): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  switch (level) {
    case 0:
      return 'info'    // 无异常
    case 1:
      return 'primary' // 可疑异常
    case 2:
      return 'success' // 轻微异常
    case 3:
      return 'warning' // 中等异常
    case 4:
      return 'danger'  // 严重异常
    case 5:
      return 'danger'  // 特别严重
    default:
      return 'info'
  }
}

// 获取状态类型
const getStatusType = (status: number | undefined | null): 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  if (!status) return 'info'
  const types = ['danger', 'warning', 'success'] as const
  return types[status] as 'success' | 'warning' | 'info' | 'danger' | 'primary'
}

// 详情
const detail = ref<AbnormalEvent | null>(null)
const detailVisible = ref(false)

const handleDetail = async (row: AbnormalEvent) => {
  const res = await getAbnormalEventById(row.id)
  detail.value = res
  detailVisible.value = true

  // ========== 新增：地图定位逻辑 ==========
  // 根据摄像头ID匹配摄像头信息
  const camera = cameras.value.find(item => item.id === res.cameraId);
  if (!camera) {
    ElMessage.warning('未找到该摄像头信息，无法定位地图');
    return;
  }
  // 校验摄像头经纬度是否有效
  const { longitude, latitude } = camera;
  const lng = Number(longitude);
  const lat = Number(latitude);

  if (longitude && latitude && !isNaN(lng) && !isNaN(lat)) {
    nextTick(() => {
      // 调用地图组件定位方法
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
}

// 处理
const handleFormRef = ref<FormInstance>()
const handleVisible = ref(false)
const submitLoading = ref(false)
const handleForm = reactive({
  id: 0,
  handlerId: 0,
  handleResult: '',
})
const handleRules = {
  handleResult: [{ required: true, message: '请输入处理结果', trigger: 'blur' }],
}

const handleProcess = (row: AbnormalEvent) => {
  handleForm.id = row.id
  handleForm.handlerId = userStore.userInfo?.id || 0
  handleForm.handleResult = ''
  handleVisible.value = true
}

const submitHandle = async () => {
  if (!handleFormRef.value) return
  await handleFormRef.value.validate()
  submitLoading.value = true
  try {
    await handleAbnormalEvent(handleForm)
    ElMessage.success('处理成功')
    handleVisible.value = false
    getList()
  } catch (error) {
    console.error(error)
  } finally {
    submitLoading.value = false
  }
}

// 完成
const handleComplete = (row: AbnormalEvent) => {
  ElMessageBox.confirm('确认完成该异常事件的处理？', '提示', {
    type: 'warning',
  })
    .then(async () => {
      await updateAbnormalEventStatus(row.id, 2)
      ElMessage.success('操作成功')
      getList()
    })
    .catch(() => { })
}

// 选中的记录ID
const selectedIds = ref<number[]>([])

// 编辑表单
const editFormRef = ref<FormInstance>()
const editVisible = ref(false)
const editForm = reactive({
  id: 0,
  cameraId: undefined,
  location: '',
  level: 1,
  status: 0,
  description: ''
})
const editRules = {
  cameraId: [{ required: true, message: '请选择摄像头', trigger: 'change' }],
  location: [{ required: true, message: '请输入位置', trigger: 'blur' }],
  level: [{ required: true, message: '请选择异常等级', trigger: 'change' }],
  status: [{ required: true, message: '请选择处理状态', trigger: 'change' }]
}

// 处理选择变化
const handleSelectionChange = (selection: AbnormalEvent[]) => {
  selectedIds.value = selection.map(item => item.id)
}

// 编辑
const handleEdit = (row: AbnormalEvent) => {
  Object.assign(editForm, row)
  editVisible.value = true
}

// 提交编辑
const submitEdit = async () => {
  if (!editFormRef.value) return
  await editFormRef.value.validate()
  submitLoading.value = true
  try {
    await updateAbnormalEvent(editForm)
    ElMessage.success('保存成功')
    editVisible.value = false
    getList()
  } catch (error) {
    console.error(error)
  } finally {
    submitLoading.value = false
  }
}

// 删除
const handleDelete = (row: AbnormalEvent) => {
  ElMessageBox.confirm('确认删除该异常事件？', '提示', {
    type: 'warning'
  })
    .then(async () => {
      await deleteAbnormalEvent(row.id)
      ElMessage.success('删除成功')
      getList()
    })
    .catch(() => { })
}

// 批量删除
const handleBatchDelete = () => {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请选择要删除的记录')
    return
  }

  ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 条记录？`, '提示', {
    type: 'warning'
  })
    .then(async () => {
      await batchDeleteAbnormalEvents(selectedIds.value)
      ElMessage.success('删除成功')
      getList()
    })
    .catch(() => { })
}

// 处理时间范围变化
watch(timeRange, (newValue) => {
  if (newValue) {
    queryParams.startTime = newValue[0]
    queryParams.endTime = newValue[1]
  } else {
    queryParams.startTime = undefined
    queryParams.endTime = undefined
  }
})

// 新增事件
const handleCreate = () => {
  // TODO: 实现新增事件功能
  ElMessage.info('新增事件功能开发中')
}

onMounted(() => {
  getCameras()
  getList()
})
</script>

<style lang="scss" scoped>
.Abnormal {
  padding: 20px;

  .toolbar {
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;

    .left {
      display: flex;
      gap: 12px;

      .el-button {
        min-width: 100px;
      }
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

      .form-select {
        width: 200px;
      }

      .el-date-editor {
        width: 360px;
      }
    }
  }

  .detail {
    // 新增视频+地图组合样式
    .video-map-item {
      display: flex;
      gap: 20px; // 视频和地图之间的间距
      align-items: flex-start;

      .content-group {
        display: flex;
        flex-direction: column;
        gap: 8px; // 标签和容器的间距

        .label {
          color: #606266;
          font-size: 14px;
        }

        .value {
          width: 270px; 
          height: 270px; 
          position: relative;
          // 核心：限制容器溢出隐藏，确保地图不超界
          overflow: hidden;
          box-sizing: border-box;

          .image, .map {
            width: 100%;
            height: 100%;
            border-radius: 4px;
            // 强制地图填满容器且不超出
            max-height: 100%;
            box-sizing: border-box;
          }

          span {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #909399;
          }
        }
      }
    }

    // 保留原有detail-item基础样式
    .detail-item {
      margin-bottom: 20px;

      &:not(.video-map-item) {
        .label {
          display: inline-block;
          width: 100px;
          color: #606266;
        }

        .value {
          color: #303133;
        }
      }
    }
  }

  // ========== 关键：穿透地图组件样式，隐藏搜索/绘制框 ==========
  .detail .video-map-item :deep(.map-wrapper) {
    position: relative !important;
    width: 100% !important;
    height: 100% !important;
    max-height: 100% !important; // 强制不超容器高度
    min-height: unset !important;
    overflow: hidden !important;
    box-sizing: border-box !important;

    // 隐藏搜索容器
    & > .search-container {
      display: none !important;
    }
    // 隐藏绘制区域
    & > .draw-area {
      display: none !important;
    }
    // 隐藏面板（如果有）
    & > #panel {
      display: none !important;
    }
    // 强制地图容器填满且不超界
    & > #amap {
      height: 100% !important;
      max-height: 100% !important;
      width: 100% !important;
      box-sizing: border-box !important;
      overflow: hidden !important;
    }
  }
}
</style>