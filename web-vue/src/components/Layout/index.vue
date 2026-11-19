<template>
  <el-container class="layout">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '200px'" class="sidebar-container">
      <div class="sidebar-logo" :class="{ 'is-collapse': isCollapse }">
        <img class="logo-img" src="@/assets/logo.png" alt="logo" />
        <span v-show="!isCollapse" class="logo-text">铁路沿线监测系统</span>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="isCollapse"
        :collapse-transition="false"
        router
      >
        <template v-for="item in menuList" :key="item.path">
          <el-menu-item
            v-if="!item.meta?.admin || userInfo?.role === 1"
            :index="item.path"
          >
            <el-icon>
              <component :is="item.meta?.icon" />
            </el-icon>
            <template #title>{{ item.meta?.title }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶部导航栏 -->
      <el-header class="header">
        <div class="left">
          <el-icon class="collapse-btn" @click="toggleCollapse">
            <Fold v-if="!isCollapse" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb>
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="right">
          <AlarmInbox v-if="!userInfo?.passwordChangeRequired" />
          <MonitoringFaultInbox v-if="!userInfo?.passwordChangeRequired" />
          <el-tooltip content="刷新页面" placement="bottom">
            <el-icon class="action-icon" @click="refresh">
              <Refresh />
            </el-icon>
          </el-tooltip>
          <!-- <el-tooltip content="切换主题" placement="bottom">
            <el-icon class="action-icon" @click="toggleDark">
              <Moon v-if="isDark" />
              <Sunny v-else />
            </el-icon>
          </el-tooltip> -->
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="32" :src="userInfo?.avatar">
                {{ userInfo?.realName?.charAt(0) }}
              </el-avatar>
              <span class="username">{{ userInfo?.realName }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">
                  <el-icon><Lock /></el-icon>
                  修改密码
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 主要内容区域 -->
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>

    <!-- 修改密码对话框 -->
    <el-dialog
      v-model="passwordDialogVisible"
      title="修改密码"
      width="400px"
      :close-on-click-modal="false"
      :show-close="!userInfo?.passwordChangeRequired"
      :close-on-press-escape="!userInfo?.passwordChangeRequired"
    >
      <el-form
        ref="passwordFormRef"
        :model="passwordForm"
        :rules="passwordRules"
        label-width="100px"
      >
        <el-form-item label="原密码" prop="oldPassword">
          <el-input
            v-model="passwordForm.oldPassword"
            type="password"
            show-password
            placeholder="请输入原密码"
          />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input
            v-model="passwordForm.newPassword"
            type="password"
            show-password
            placeholder="请输入新密码"
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="passwordForm.confirmPassword"
            type="password"
            show-password
            placeholder="请再次输入新密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="!userInfo?.passwordChangeRequired" @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleUpdatePassword">
          确定
        </el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import AlarmInbox from '@/components/AlarmInbox/index.vue'
import MonitoringFaultInbox from '@/components/MonitoringFaultInbox/index.vue'
import { alarmInbox } from '@/stores/alarmInbox'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import { validatePassword } from '@/utils/validate'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

// 用户信息
const userInfo = computed(() => userStore.userInfo)
watch(() => `${userInfo.value?.id}:${userInfo.value?.passwordChangeRequired}`, () => {
  alarmInbox.stop()
  if(userInfo.value && !userInfo.value.passwordChangeRequired)alarmInbox.start()
}, {immediate:true})
onBeforeUnmount(()=>alarmInbox.stop())

// 菜单列表
const menuList = computed(() => route.matched[0]?.children || [])

// 侧边栏折叠状态
const isCollapse = computed(() => appStore.sidebarCollapse)
const toggleCollapse = () => appStore.toggleSidebar()

// 暗黑模式
const isDark = computed(() => appStore.isDark)
const toggleDark = () => appStore.toggleDark()

// 刷新页面
const refresh = () => {
  router.go(0)
}

// 下拉菜单命令处理
const handleCommand = (command: string) => {
  switch (command) {
    case 'password':
      passwordDialogVisible.value = true
      break
    case 'logout':
      handleLogout()
      break
  }
}

// 退出登录
const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  }).then(async () => {
    await userStore.logout()
    router.push('/login')
  })
}

// 修改密码
const loading = ref(false)
const passwordDialogVisible = ref(Boolean(userInfo.value?.passwordChangeRequired))
const passwordFormRef = ref<FormInstance>()
const passwordForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

// 密码校验规则
const passwordRules = {
  oldPassword: [
    { required: true, message: '请输入原密码', trigger: 'blur' },
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { validator: (rule: any, value: string) => {
      if (value.length < 12 || new TextEncoder().encode(value).length > 72) {
        return new Error('口令至少12个字符，UTF-8最多72字节')
      }
      return true
    }, trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: (rule: any, value: string) => {
      if (value !== passwordForm.value.newPassword) {
        return new Error('两次输入的密码不一致')
      }
      return true
    }, trigger: 'blur' },
  ],
}

// 处理修改密码
const handleUpdatePassword = async () => {
  if (!passwordFormRef.value) return
  
  await passwordFormRef.value.validate()
  
  try {
    loading.value = true
    await userStore.updatePassword({
      id: userInfo.value?.id,
      oldPassword: passwordForm.value.oldPassword,
      newPassword: passwordForm.value.newPassword,
    })
    
    passwordDialogVisible.value = false
    ElMessageBox.alert('密码修改成功，请重新登录', '提示', {
      confirmButtonText: '确定',
      callback: () => {
        userStore.logout()
        router.push('/login')
      },
    })
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.layout {
  width: 100%;
  height: 100%;
  
  .aside {
    transition: width 0.3s;
    overflow: hidden;
  }
  
  .header {
    background-color: #fff;
    border-bottom: 1px solid #dcdfe6;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    
    .left {
      display: flex;
      align-items: center;
      
      .collapse-btn {
        font-size: 20px;
        cursor: pointer;
        margin-right: 20px;
        
        &:hover {
          color: var(--el-color-primary);
        }
      }
    }
    
    .right {
      display: flex;
      align-items: center;
      
      .action-icon {
        font-size: 20px;
        cursor: pointer;
        margin-right: 20px;
        
        &:hover {
          color: var(--el-color-primary);
        }
      }
      
      .user-info {
        display: flex;
        align-items: center;
        cursor: pointer;
        
        .username {
          margin-left: 8px;
          font-size: 14px;
        }
      }
    }
  }
  
  .main {
    background-color: #f0f2f5;
    padding: 20px;
  }
}

// 路由过渡动画
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
