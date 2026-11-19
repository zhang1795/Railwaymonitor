<template>
  <div class="Abnormal">
    <el-alert :type="alarmState.healthy ? 'warning' : 'info'" :closable="false" show-icon>
      <template #title>{{ alarmState.healthy ? `有 ${alarmState.unreadCount} 条未读提醒（同一事件可重复提醒）` : '提醒状态未知，正在重试' }}</template>
      列表不会自动替换正在查看或编辑的内容。
      <el-button link type="primary" @click="handleQuery">刷新当前列表</el-button>
      <el-button link type="primary" @click="showUnread">查看全部未读</el-button>
    </el-alert>
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
      <el-form-item><el-checkbox v-model="queryParams.unreadOnly" @change="handleQuery">仅看未读</el-checkbox></el-form-item>
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
      <el-table-column label="类别" min-width="120"><template #default="{row}">{{ row.type || row.detectedType || '待核验' }}</template></el-table-column>
      <el-table-column label="事件性质 / 观测结论" min-width="210"><template #default="{row}"><el-tag :type="row.risk?.kind==='RISK' ? 'danger' : 'info'">{{ eventKind(row.risk?.kind) }}</el-tag><br/>{{ riskStatus(row) }}<br/><small>{{utcTime(row.risk?.last_observed)}}</small></template></el-table-column>
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
        <el-button :loading="detailLoading" @click="detail && handleDetail(detail)">刷新详情</el-button>
        <el-alert :title="eventKind(detail?.risk?.kind)+' · '+riskStatus(detail)" :type="detail?.risk?.state==='INTERRUPTED' ? 'warning' : 'info'" :closable="false" />
        <div class="detail">
          <div class="detail-item"><span class="label">自动检测：</span><span class="value">{{ detail?.detectedType || '未知' }} · 类别历史分数峰值 {{ detail?.confidence!=null ? (detail.confidence*100).toFixed(1)+'%' : '未知' }}（分数不等于风险等级）</span></div>
          <div class="detail-item"><span class="label">记录类别：</span><span class="value">{{ detail?.type || '尚未填写' }} · {{detail?.manualOverride ? '人工编辑保留的类别' : '自动记录，尚未人工核验'}}</span></div>
          <div class="detail-item"><span class="label">观测状态：</span><span class="value">{{ detectionLabel(detail?.detectionState) }}</span></div>
          <div class="detail-item"><span class="label">首末观测：</span><span class="value">{{ formatDateTime(detail?.firstSeen) }} 至 {{ formatDateTime(detail?.lastSeen) }}</span></div>
          <div class="detail-item"><span class="label">规则判定：</span><span class="value">{{ policyDescription }}<br/>{{ associationLabel(detail?.risk?.association) }} · 已关联 {{ insight?.sources.length || 0 }} 段轨迹</span></div>
          <div class="detail-item"><span class="label">风险等级：</span><span class="value">{{ detail?.risk?.risk_level || '-' }} · 判定开始 {{ utcTime(detail?.risk?.risk_since) }}<br/>最后有效观测 {{ utcTime(detail?.risk?.last_observed) }}</span></div>
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
              <span class="label">事发截图：</span>
              <div class="value video-container">
                <div v-for="image in insight?.evidence.images" :key="image.id">
                  <el-image v-if="image.state==='READY'" :src="image.url" :preview-src-list="[image.url]" fit="contain" class="image"><template #error>截图不可用或校验失败，请刷新核对</template></el-image>
                  <span v-else>截图文件不可用</span><small>{{ utcTime(image.capturedAt) }}</small>
                </div>
                <span v-if="!insight?.evidence.images.length">{{ insight?.evidence.configured ? '尚无已上传截图；证据缺失不代表未发生告警' : '证据上传未配置' }}</span>
                <div v-for="worker in insight?.evidenceWorker" :key="worker.reported_at"><small>最近上报：待传 {{ worker.pending_events }}，跳过 {{worker.skipped}}；{{worker.error || '未报告上传异常'}}（{{utcTime(worker.reported_at)}}）</small></div>
                <div v-for="clip in insight?.recordings" :key="clip.id"><small>{{utcTime(clip.started_at)}} → {{utcTime(clip.ended_at)}}</small><RecordingPlayer v-if="clip.state==='READY'" :clip="clip"/><span v-else>{{clip.state==='EXPIRED'?'录像已按保留策略过期':'录像暂不可用'}}</span></div>
                <p v-if="!insight?.recordings?.length">暂无已登记的相关历史录像；当前直播不能代替事发证据。</p>
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
          <el-collapse>
            <el-collapse-item title="风险状态变化" name="risk"><el-timeline><el-timeline-item v-for="(item,index) in insight?.transitions" :key="index" :timestamp="utcTime(item.observed_at)">{{riskLabel(item.to_state,detail?.risk?.kind)}} · {{transitionReason(item.reason)}}</el-timeline-item></el-timeline></el-collapse-item>
            <el-collapse-item title="提醒历史（已读与处置分别记录）" name="notices"><div v-for="(item,index) in insight?.notices" :key="index">{{noticeLabel(item.kind)}} · {{utcTime(item.created_at)}}</div></el-collapse-item>
            <el-collapse-item title="外部通知状态" name="delivery"><p>Webhook：{{insight?.notificationConfiguration?.webhookConfigured?'已配置':'未配置'}}；短信：{{insight?.notificationConfiguration?.smsConfigured?'已配置':'未配置'}}。站内已读与外部送达分别记录。</p><div v-for="item in insight?.deliveries" :key="item.id">{{item.channel}} · {{deliveryLabel(item.status)}} · {{utcTime(item.updated_at)}} · {{item.error}}</div></el-collapse-item>
            <el-collapse-item title="人工处置记录" name="handling"><div v-for="(item,index) in insight?.handling" :key="index">{{utcTime(item.created_at)}} · 用户 {{item.user_id}} · {{formatStatus(item.before_status)}} → {{formatStatus(item.after_status)}} · {{item.result || '状态更新'}}</div></el-collapse-item>
          </el-collapse>
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
        <el-form-item label="核验类别" prop="type">
          <el-select v-model="editForm.type" placeholder="请选择核验类别">
            <el-option v-for="name in abnormalTypes" :key="name" :label="name" :value="name" />
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
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { alarmInbox } from '@/stores/alarmInbox'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useUserStore } from '@/stores/user'
import type { AbnormalEvent, AbnormalEventQueryParams } from '@/types/Abnormal'
import type { Camera } from '@/types/camera'
import { getAbnormalEventList, getAbnormalEventById, handleAbnormalEvent, updateAbnormalEventStatus, deleteAbnormalEvent, updateAbnormalEvent, batchDeleteAbnormalEvents, createAbnormalEvent } from '@/api/Abnormal'
import {getAlarmInsight} from '@/api/Abnormal'
import type {AlarmInsight} from '@/api/Abnormal'
import {eventKind,riskLabel,riskAt,detectionLabel,associationLabel,transitionReason,noticeLabel,deliveryLabel,utcTime} from '@/utils/riskDisplay'
import {ruleSummary} from '@/utils/ruleSummary'
import { getCameraList } from '@/api/camera'
import { formatDateTime, formatAbnormalLevel, formatStatus } from '@/utils/format'
import Pagination from '@/components/Pagination/index.vue'
import type { PageQuery } from '@/types/common'
import MapComponent from '@/components/Map/index.vue'
import RecordingPlayer from '@/components/RecordingPlayer/index.vue'

// 定义地图组件ref
const mapRef = ref<InstanceType<typeof MapComponent> | null>(null)


const userStore = useUserStore()
const route = useRoute()
const alarmState = alarmInbox.state
const displayClock=ref(Date.now())
const displayTicker=setInterval(()=>{displayClock.value=Date.now()},1000)
onBeforeUnmount(()=>clearInterval(displayTicker))
const riskStatus=(event?:AbnormalEvent|null)=>riskAt(event?.risk?.state,event?.risk?.kind,event?.risk?.last_observed,displayClock.value)
let disposed=false
let detailRequest=0
let listRequest=0
onBeforeUnmount(()=>{disposed=true})

// 查询参数
const queryParams = reactive<AbnormalEventQueryParams>({
  unreadOnly: route.query.unread === '1',
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
  const sequence=++listRequest
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
    if(disposed || sequence!==listRequest)return
    list.value = res.records
    total.value = res.total
  } catch (error) {
    console.error(error)
  } finally {
    if(!disposed && sequence===listRequest)loading.value = false
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
    unreadOnly: false,
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
const detailLoading=ref(false),insight=ref<AlarmInsight>()
const policyDescription=computed(()=>{
  const item=insight.value?.risk[0]
  if(!item || item.kind==='LEGACY')return '历史数据，没有可核验的区域规则快照'
  try{
    if(item.association==='LATE_SNAPSHOT_REVIEW' && item.session_policy)
      return '前序观测不完整，本次记录为待核验观察。当时的会话配置：'+ruleSummary(JSON.parse(item.session_policy))
    const policy=JSON.parse(item.policy)
    return ruleSummary(policy)
  }catch{return '规则快照不可读，请联系管理员核查'}
})

const handleDetail = async (row: {id:number|string}) => {
  const sequence=++detailRequest
  detailLoading.value=true
  let res:AbnormalEvent,extra:AlarmInsight
  try{[res,extra]=await Promise.all([getAbnormalEventById(row.id),getAlarmInsight(row.id)])}
  finally{if(sequence===detailRequest)detailLoading.value=false}
  if(disposed || sequence!==detailRequest)return
  insight.value=extra
  detail.value = res
  detailVisible.value = true
  // Only the specific successfully opened event is acknowledged.
  if(res.unreadNoticeIds?.length)void alarmInbox.markNotificationsRead(res.unreadNoticeIds).catch(()=>{})
  else if(res.unreadNoticeIds===undefined)void alarmInbox.markRead([String(row.id)]).catch(() => {})

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
  version: 0,
  id: 0,
  handlerId: 0,
  handleResult: '',
})
const handleRules = {
  handleResult: [{ required: true, message: '请输入处理结果', trigger: 'blur' }],
}

const handleProcess = (row: AbnormalEvent) => {
  handleForm.version = row.version ?? 0
  handleForm.id = row.id
  handleForm.handlerId = userStore.userInfo?.id || 0
  handleForm.handleResult = ''
  handleVisible.value = true
}

const submitHandle = async () => {
  if (!handleFormRef.value || submitLoading.value || disposed) return
  submitLoading.value = true
  try {
    await handleFormRef.value.validate()
    const submitted={...handleForm}
    await handleAbnormalEvent(submitted)
    if(disposed || submitted.id!==handleForm.id)return
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
const handleComplete = (row: AbnormalEvent) => handleProcess(row)

// 选中的记录ID
const selectedIds = ref<number[]>([])

// 编辑表单
const editFormRef = ref<FormInstance>()
const editVisible = ref(false)
const abnormalTypes = ['防撞设备','气球','牛','水害','滑坡','违规建筑','风筝','落石','鸟巢','广告牌','坑洞','垃圾','工人']
const editForm = reactive({
  version: 0,
  type: '',
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
  if (!editFormRef.value || submitLoading.value || disposed) return
  submitLoading.value = true
  try {
    await editFormRef.value.validate()
    const submitted={...editForm}
    await updateAbnormalEvent(submitted)
    if(disposed || submitted.id!==editForm.id)return
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

const showUnread = () => {
  timeRange.value=undefined
  Object.assign(queryParams,{current:1,size:10,unreadOnly:true,cameraId:undefined,location:undefined,level:undefined,status:undefined,startTime:undefined,endTime:undefined})
  getList()
}
const openNotice = async (id:unknown) => {
  if(typeof id==='string' && /^[1-9]\d{0,18}$/.test(id)) {
    try { await handleDetail({id}) } catch { /* Request layer explains failure. */ }
  }
}
let mounted=false
watch(()=>route.query.noticeId,id=>{if(mounted)void openNotice(id)})
watch(()=>route.query.unread,value=>{if(mounted && value==='1')showUnread()})
onMounted(async () => {
  await getCameras()
  if(disposed)return
  getList()
  mounted=true
  await openNotice(route.query.noticeId)
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
