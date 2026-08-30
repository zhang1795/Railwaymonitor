import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

// 存储桶类型
export type BucketType = 'avatars' | 'Abnormal-images' |'temp'

// 创建 axios 实例
const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_FILE_URL,
  timeout: 60000,
})

// 请求拦截器
service.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (response: AxiosResponse) => {
    const { code, message, data } = response.data

    if (code === 200) {
      return data
    }

    ElMessage.error(message || '请求失败')
    return Promise.reject(new Error(message || '请求失败'))
  },
  (error) => {
    ElMessage.error(error.message || '请求失败')
    return Promise.reject(error)
  }
)

// 封装请求方法
const fileRequest = {
  /**
   * 上传文件
   * @param bucket 存储桶名称
   * @param file 文件对象
   * @param isCache 是否为缓存文件
   * @param config 额外的请求配置
   * @returns 返回文件访问URL
   */
  upload<T = string>(bucket: BucketType, file: File, isCache?: boolean, config?: AxiosRequestConfig): Promise<T> {
    const formData = new FormData()
    formData.append('file', file)
    if (isCache) {
      formData.append('is_cache', 'true')
    }
    return service.post(`/file/upload/${bucket}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      ...config,
    })
  },

  /**
   * 获取文件
   * @param bucket 存储桶名称
   * @param objectKey 文件名
   * @param config 额外的请求配置
   * @returns 返回文件内容
   */
  get(bucket: BucketType, objectKey: string, config?: AxiosRequestConfig): Promise<Blob> {
    return service.get(`/file/${bucket}/${objectKey}`, {
      responseType: 'blob',
      ...config,
    })
  },

  /**
   * 删除文件
   * @param bucket 存储桶名称
   * @param objectKey 文件名
   * @param config 额外的请求配置
   * @returns 返回响应数据
   */
  delete<T = any>(bucket: BucketType, objectKey: string, config?: AxiosRequestConfig): Promise<T> {
    return service.delete(`/file/${bucket}/${objectKey}`, config)
  },

  /**
   * 获取文件URL
   * @param bucket 存储桶名称
   * @param objectKey 文件名
   * @returns 返回文件访问URL
   */
  getFileUrl(bucket: BucketType, objectKey: string): string {
    return `${import.meta.env.VITE_FILE_URL}/file/${bucket}/${objectKey}`
  }
}

export default fileRequest 