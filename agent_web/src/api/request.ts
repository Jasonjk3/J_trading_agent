import axios, { type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { getMockResponse } from '@/mocks/handler'

const isMock = import.meta.env.VITE_USE_MOCK === 'true'

/** 后端统一响应格式 */
interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

const instance = axios.create({
  /** 各接口路径已含 `/v1/...`；此处填后端 origin（如 http://127.0.0.1:5005），勿再加 /api */
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const userStore = useUserStore()
  if (userStore.token) {
    config.headers.Authorization = `Bearer ${userStore.token}`
  }
  return config
})

instance.interceptors.response.use(
  async (res: AxiosResponse<ApiResponse>) => {
    // 文件下载：直接返回 Blob；若服务端用 JSON 报错，尝试解析
    if (res.config.responseType === 'blob' || res.data instanceof Blob) {
      const blob = res.data as unknown as Blob
      const contentType = blob.type || res.headers?.['content-type'] || ''
      if (contentType.includes('application/json')) {
        try {
          const text = await blob.text()
          const parsed = JSON.parse(text) as ApiResponse
          ElMessage.error(parsed.message || '请求失败')
          return Promise.reject(new Error(parsed.message || '请求失败'))
        } catch {
          return Promise.reject(new Error('请求失败'))
        }
      }
      return blob as unknown as ApiResponse
    }

    const { code, message, data } = res.data
    if (code === 200) {
      return data
    }
    if (code === 5002) {
      const userStore = useUserStore()
      userStore.logout()
      window.location.href = '/login'
      return Promise.reject(new Error(message || '未登录或已过期'))
    }
    ElMessage.error(message || '请求失败')
    return Promise.reject(new Error(message || '请求失败'))
  },
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.message ?? err.message ?? '请求失败'
    if (status === 401) {
      const userStore = useUserStore()
      userStore.logout()
      window.location.href = '/login'
      return Promise.reject(new Error('未登录或已过期'))
    }
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

async function doRequest<T = any>(method: string, url: string, data?: any, config?: any): Promise<T> {
  if (isMock) {
    const mock = getMockResponse(method, url, data, config)
    if (mock) return mock as Promise<T>
  }
  if (method.toUpperCase() === 'GET') {
    return instance.get(url, { ...config, params: data || config?.params }) as Promise<T>
  }
  if (method.toUpperCase() === 'POST') {
    return instance.post(url, data, config) as Promise<T>
  }
  if (method.toUpperCase() === 'PUT') {
    return instance.put(url, data, config) as Promise<T>
  }
  if (method.toUpperCase() === 'DELETE') {
    return instance.delete(url, config) as Promise<T>
  }
  return instance.request({ ...config, method, url, data }) as Promise<T>
}

export const requestClient = {
  get: <T = any>(url: string, config?: any) => doRequest<T>('GET', url, undefined, config),
  post: <T = any>(url: string, data?: any, config?: any) => doRequest<T>('POST', url, data, config),
  put: <T = any>(url: string, data?: any, config?: any) => doRequest<T>('PUT', url, data, config),
  delete: <T = any>(url: string, config?: any) => doRequest<T>('DELETE', url, undefined, config),
}

/** 兼容：组件中 request.post 使用方式 */
export const request = requestClient
