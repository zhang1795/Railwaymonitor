<template>
  <div class="statistics-container">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="box-card">
          <template #header>
            <div class="card-header">
              <span>统计分析</span>
            </div>
          </template>
          <el-menu
            :default-active="activeMenu"
            mode="horizontal"
            router
            @select="handleSelect"
          >
            <el-menu-item index="/statistics/overview">
              <el-icon><DataAnalysis /></el-icon>
              <span>统计概览</span>
            </el-menu-item>
            <el-menu-item index="/statistics/Abnormal-event">
              <el-icon><Warning /></el-icon>
              <span>异常事件统计</span>
            </el-menu-item>
            <el-menu-item index="/statistics/device-status">
              <el-icon><Monitor /></el-icon>
              <span>设备状态统计</span>
            </el-menu-item>
          </el-menu>
          <router-view></router-view>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataAnalysis,
  Warning,
  Monitor,
  List,
  ChatDotRound,
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const activeMenu = ref(route.path)

const handleSelect = (key: string) => {
  activeMenu.value = key
}

onMounted(() => {
  // 如果当前路径是 /statistics，重定向到 /statistics/overview
  if (route.path === '/statistics') {
    router.push('/statistics/overview')
  }
})
</script>

<style scoped>
.statistics-container {
  padding: 20px;
}

.box-card {
  margin-bottom: 20px;
  
  :deep(.el-card__header) {
    padding: 15px 20px;
    border-bottom: 1px solid var(--el-border-color-light);
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;

  span {
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
}

.el-menu {
  margin-bottom: 20px;
  border-bottom: 1px solid var(--el-border-color-light);

  .el-menu-item {
    display: flex;
    align-items: center;
    font-weight: 500;
    color: #303133 !important;
    transition: all 0.3s ease;
    
    &:hover {
      color: #303133 !important;
      background-color: rgba(64, 158, 255, 0.08);
    }
    
    &.is-active {
      color: #303133 !important;
      font-weight: 600;
      background-color: rgba(64, 158, 255, 0.08);
      border-bottom: 2px solid var(--el-color-primary);
    }
    
    .el-icon {
      margin-right: 5px;
      color: inherit;
    }
  }
}

:deep(.el-menu--horizontal .el-menu-item) {
  color: #303133 !important;
  
  &:hover {
    color: #303133 !important;
    background-color: rgba(64, 158, 255, 0.08);
  }
  
  &.is-active {
    color: #303133 !important;
    font-weight: 600;
    background-color: rgba(64, 158, 255, 0.08);
    border-bottom: 2px solid var(--el-color-primary);
  }
}
</style> 