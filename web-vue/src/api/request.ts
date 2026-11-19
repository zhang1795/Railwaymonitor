import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

// 创建 axios 实例
const instance: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: 10000,
})

let csrf: { headerName:string; token:string } | undefined
let csrfPending: Promise<void> | undefined
export function resetCsrf() { csrf = undefined; csrfPending = undefined }
async function ensureCsrf() {
  if (csrf) return
  if (!csrfPending) csrfPending = instance.get('/auth/csrf').then((data:any) => { csrf=data }).finally(() => {csrfPending=undefined})
  await csrfPending
}
instance.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const method = (config.method || 'get').toLowerCase()
  if (!['get','head','options'].includes(method)) {
    await ensureCsrf()
    if (csrf) config.headers.set(csrf.headerName, csrf.token)
  }
  return config
})

// 响应拦截器
instance.interceptors.response.use(
  (response: AxiosResponse) => {
    const { code, msg, data } = response.data

    if (response.config.url === '/user/login' || response.config.url === '/user/logout') resetCsrf()
    // 请求成功
    if (code === 200 || code === 0) {
      return data
    }

    // 登录过期
    if (code === 401) {
      const userStore = useUserStore()
      userStore.clearUserInfo()
      window.location.href = '/login'
      return Promise.reject(new Error('登录已过期，请重新登录'))
    }

    // 显示错误信息
    const error = new Error(msg || '请求失败') as Error & { response?: any }
    error.response = response
    ElMessage.error(msg || '请求失败')
    return Promise.reject(error)
  },
  (error) => {
    // 处理网络错误
    let message = '网络请求失败，请检查网络连接'
    if (error.response) {
      const { status, data } = error.response
      switch (status) {
        case 400:
          message = data.msg || '请求参数错误'
          break
        case 401:
          message = '登录已过期，请重新登录'
          const userStore = useUserStore()
          userStore.clearUserInfo()
          window.location.href = '/login'
          break
        case 403:
          resetCsrf()
          message = '没有权限访问该资源'
          break
        case 404:
          message = '请求的资源不存在'
          break
        case 500:
          message = '服务器内部错误'
          break
        default:
          message = data.msg || '请求失败'
      }
    }
    if (!error.config?.silent) {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  }
)

// 封装请求方法
const request = {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.get(url, config)
  },

  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, data, config)
  },

  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return instance.put(url, data, config)
  },

  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.delete(url, config)
  },
}

export default request 
 