<template>
  <el-popover v-model:visible="visible" placement="bottom-end" :width="420" trigger="click" @show="openInbox">
    <template #reference>
      <el-button :type="state.unreadCount ? 'danger' : 'default'" plain aria-label="查看未读告警">
        <el-icon><Bell /></el-icon>
        {{ state.loading ? '提醒加载中' : !state.healthy ? '提醒状态未知' : `未读提醒 ${state.unreadCount}` }}
        <span v-if="state.changed"> · 有更新</span>
      </el-button>
    </template>
    <div class="notice-header"><strong>未读提醒 {{ state.unreadCount }}</strong><el-button link @click="alarmInbox.refresh">刷新</el-button></div>
    <el-alert v-if="!state.healthy" title="告警查询不可用，以下为上次结果" type="warning" :closable="false" />
    <p>已读表示已查看，告警处置状态单独记录。</p>
    <el-scrollbar max-height="320px">
      <div v-for="item in state.items" :key="item.noticeId || item.id" class="notice-row">
        <div><strong>{{ noticeKind(item.kind) }} · {{ item.type || '待核验观察' }}</strong> · {{ item.location }}<br/><small>{{ formatDateTime(item.noticeTime || item.eventTime) }}</small></div>
        <el-button link type="primary" @click="view(item.id)">查看</el-button>
      </div>
      <el-empty v-if="!state.loading && !state.items.length" description="暂无未读告警" :image-size="48" />
    </el-scrollbar>
    <p>展示最近20条未读提醒；同一事件可有持续或升级提醒。</p>
    <el-button type="primary" @click="viewAll">查看全部未读</el-button>
    <el-button :disabled="!state.items.length || !state.healthy" :loading="reading" @click="readDisplayed">本批标为已读</el-button>
  </el-popover>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import { alarmInbox } from '@/stores/alarmInbox'
import { formatDateTime } from '@/utils/format'
const {state}=alarmInbox
const router=useRouter()
const reading=ref(false)
const visible=ref(false)
const noticeKind=(kind?:string)=>(({FIRST:'首次发现',ONGOING:'持续存在，请复核',ESCALATION:'风险升级'} as Record<string,string>)[kind || 'FIRST'] || '事件提醒')
const openInbox=()=>{state.changed=false;void alarmInbox.refresh()}
const view=(id:string)=>{visible.value=false;return router.push({path:'/Abnormal',query:{noticeId:id}})}
const viewAll=()=>{visible.value=false;return router.push({path:'/Abnormal',query:{unread:'1'}})}
const readDisplayed=async()=>{
  const ids=state.items.map(row=>row.noticeId || row.id)
  if(!ids.length)return
  reading.value=true
  try {await alarmInbox.markNotificationsRead(ids)} catch { /* Request layer explains failure. */ }
  finally {reading.value=false}
}
</script>
<style scoped>
.notice-header,.notice-row { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.notice-row { padding:10px 0; border-bottom:1px solid var(--el-border-color-lighter); overflow-wrap:anywhere; }
p,small { color:var(--el-text-color-secondary); font-size:12px; }
</style>
