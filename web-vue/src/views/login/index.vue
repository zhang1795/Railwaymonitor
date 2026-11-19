<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <h2>铁路沿线异常监测系统</h2>
        <p>Railway Line Anomaly Detection System</p>
      </div>
      
      <el-tabs v-model="activeTab" class="login-tabs">
        <!-- 登录表单 -->
        <el-tab-pane name="login" label="登录">
          <el-form
            ref="loginFormRef"
            :model="form"
            :rules="rules"
            class="login-form"
          >
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名"
                :prefix-icon="User"
                clearable
              />
            </el-form-item>
            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="请输入密码"
                :prefix-icon="Lock"
                show-password
                clearable
                @keyup.enter="handleSubmit"
              />
            </el-form-item>

            <div class="login-options">
              <el-checkbox v-model="rememberMe">记住我</el-checkbox>
              <el-link type="primary">忘记密码？</el-link>
            </div>

            <el-form-item>
              <el-button
                type="primary"
                :loading="loading"
                class="submit-btn"
                @click="handleSubmit"
              >
                登录
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
        
        <!-- 注册表单 -->
        <el-tab-pane v-if="false" name="register" label="注册">
          <el-form
            ref="registerFormRef"
            :model="form"
            :rules="registerRules"
            class="login-form"
          >
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名"
                :prefix-icon="User"
                clearable
              />
            </el-form-item>
            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="请输入密码"
                :prefix-icon="Lock"
                show-password
                clearable
              />
            </el-form-item>
            <el-form-item prop="confirmPassword">
              <el-input
                v-model="form.confirmPassword"
                type="password"
                placeholder="请确认密码"
                :prefix-icon="Lock"
                show-password
                clearable
              />
            </el-form-item>
            <el-form-item prop="realName">
              <el-input
                v-model="form.realName"
                placeholder="请输入真实姓名"
                :prefix-icon="UserFilled"
                clearable
              />
            </el-form-item>
            <el-form-item prop="phone">
              <el-input
                v-model="form.phone"
                placeholder="请输入手机号码"
                :prefix-icon="Phone"
                clearable
              />
            </el-form-item>
            <el-form-item prop="email">
              <el-input
                v-model="form.email"
                placeholder="请输入邮箱"
                :prefix-icon="Message"
                clearable
                @keyup.enter="handleSubmit"
              />
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="loading"
                class="submit-btn"
                @click="handleSubmit"
              >
                注册
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="login-footer">
        <p>推荐使用Chrome浏览器访问本系统</p>
        <p>© {{ new Date().getFullYear() }} 铁路沿线异常监测系统</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { User, Lock, UserFilled, Phone, Message } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { login, register } from '@/api/user'

const router = useRouter()
const userStore = useUserStore()

// 表单引用
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

// 加载状态
const loading = ref(false)

// 记住我
const rememberMe = ref(false)

// 当前标签页
const activeTab = ref('login')

// 表单数据
const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  realName: '',
  phone: '',
  email: ''
})

// 登录表单校验规则
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度应在3-20个字符之间', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 72, message: '密码长度应在6-72个字符之间', trigger: 'blur' }
  ]
}

// 注册表单校验规则
const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度应在3-20个字符之间', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 72, message: '密码长度应在6-72个字符之间', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule: any, value: string, callback: any) => {
        if (value !== form.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ],
  realName: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' }
  ],
  phone: [
    { required: true, message: '请输入手机号码', trigger: 'blur' },
    { 
      pattern: /^1[3-9]\d{9}$/, 
      message: '请输入正确的手机号码', 
      trigger: 'blur' 
    }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { 
      pattern: /^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}$/, 
      message: '请输入正确的邮箱地址', 
      trigger: 'blur' 
    }
  ]
}

// 提交表单
const handleSubmit = async () => {
  const formRef = activeTab.value === 'login' ? loginFormRef.value : registerFormRef.value
  if (!formRef) return
  
  try {
    await formRef.validate()
    loading.value = true

    if (activeTab.value === 'login') {
      // 登录
      try {
        const res = await login(form.username, form.password)
        // 存储用户信息到 store
        userStore.setUserInfo(res)
        
        // 记住用户名
        if (rememberMe.value) {
          localStorage.setItem('rememberedUsername', form.username)
        } else {
          localStorage.removeItem('rememberedUsername')
        }
        
        ElMessage.success('登录成功')
        router.push('/')
      } catch (error) {
        // 错误已经在响应拦截器中处理
        console.error('登录失败:', error)
      }
    } else {
      // 注册
      await register({
        username: form.username,
        password: form.password,
        realName: form.realName,
        phone: form.phone,
        email: form.email
      })
      ElMessage.success('注册成功，请登录')
      activeTab.value = 'login'
      form.password = ''
      form.confirmPassword = ''
      form.realName = ''
      form.phone = ''
      form.email = ''
    }
  } catch (error: any) {
    console.error(error)
    ElMessage.error(error.message || '操作失败')
  } finally {
    loading.value = false
  }
}

// 初始化时，如果有记住的用户名则填充
const rememberedUsername = localStorage.getItem('rememberedUsername')
if (rememberedUsername) {
  form.username = rememberedUsername
  rememberMe.value = true
}
</script>

<style lang="scss" scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: url('@/assets/images/login-bg.jpg') no-repeat center center;
  background-size: cover;
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
  }
}

.login-box {
  position: relative;
  width: 420px;
  padding: 30px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  animation: fadeIn 0.5s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
  
  h2 {
    font-size: 28px;
    color: var(--el-color-primary);
    margin: 0 0 10px;
    font-weight: 600;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  p {
    font-size: 14px;
    color: var(--el-text-color-secondary);
    margin: 0;
    letter-spacing: 1px;
  }
}

.login-form {
  .el-tabs {
    margin-bottom: 20px;
  }
  
  .el-input {
    --el-input-height: 42px;
    margin-bottom: 5px;
    
    :deep(.el-input__wrapper) {
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
      transition: all 0.3s ease;
      
      &:hover, &:focus-within {
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
      }
    }
    
    :deep(.el-input__inner) {
      &::placeholder {
        color: var(--el-text-color-placeholder);
      }
    }
  }
}

.login-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 0 2px;
  
  .el-checkbox {
    color: var(--el-text-color-regular);
  }
  
  .el-link {
    font-size: 14px;
  }
}

.submit-btn {
  width: 100%;
  height: 42px;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 1px;
  transition: all 0.3s ease;
  
  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.2);
  }
}

.login-footer {
  text-align: center;
  margin-top: 24px;
  
  p {
    margin: 5px 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    line-height: 1.6;
  }
}

// 响应式设计
@media (max-width: 576px) {
  .login-box {
    width: 90%;
    max-width: 420px;
    margin: 20px;
    padding: 24px;
  }
  
  .login-header {
    h2 {
      font-size: 24px;
    }
    
    p {
      font-size: 12px;
    }
  }
  
  .submit-btn {
    height: 40px;
    font-size: 15px;
  }
}
</style> 