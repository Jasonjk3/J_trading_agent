import { request } from './request'

// ============================================================================
// API 配置相关类型
// ============================================================================

export interface ApiConfigItem {
  id: number
  name: string
  provider: string
  api_type: string
  api_key: string
  api_url?: string
  extra_headers?: Record<string, string>
  extra_params?: Record<string, any>
  description?: string
  is_default: boolean
  is_active: boolean
  user_id?: string
  created_at?: string
  updated_at?: string
}

export interface ApiConfigCreateRequest {
  name: string
  provider: string
  api_type?: string
  api_key: string
  api_url?: string
  extra_headers?: Record<string, string>
  extra_params?: Record<string, any>
  description?: string
  is_default?: boolean
  user_id?: string
}

export interface ApiConfigUpdateRequest {
  name?: string
  provider?: string
  api_type?: string
  api_key?: string
  api_url?: string
  extra_headers?: Record<string, string>
  extra_params?: Record<string, any>
  description?: string
  is_default?: boolean
  is_active?: boolean
}

export interface ApiConfigListResponse {
  items: ApiConfigItem[]
  total: number
}

// ============================================================================
// 模型管理相关类型
// ============================================================================

export interface ModelItem {
  id: number
  model_id: string
  name: string
  provider: string
  description?: string
  max_tokens?: number
  max_output_tokens?: number
  supports_streaming: boolean
  supports_thinking: boolean
  use_max_completion_tokens: boolean
  input_price_per_1m: number
  output_price_per_1m: number
  api_config_id?: number
  custom_params?: Record<string, any>
  tags?: string[]
  status: 'available' | 'unavailable' | 'unknown'
  last_test_at?: string
  last_test_latency_ms?: number
  last_test_error?: string
  is_active: boolean
  sort_order: number
  user_id?: string
  created_at?: string
  updated_at?: string
}

export interface ModelCreateRequest {
  model_id: string
  name: string
  provider: string
  description?: string
  max_tokens?: number
  max_output_tokens?: number
  supports_streaming?: boolean
  supports_thinking?: boolean
  use_max_completion_tokens?: boolean
  input_price_per_1m?: number
  output_price_per_1m?: number
  api_config_id?: number
  custom_params?: Record<string, any>
  tags?: string[]
  sort_order?: number
  user_id?: string
}

export interface ModelUpdateRequest {
  name?: string
  provider?: string
  description?: string
  max_tokens?: number
  max_output_tokens?: number
  supports_streaming?: boolean
  supports_thinking?: boolean
  use_max_completion_tokens?: boolean
  input_price_per_1m?: number
  output_price_per_1m?: number
  api_config_id?: number
  custom_params?: Record<string, any>
  tags?: string[]
  is_active?: boolean
  sort_order?: number
}

export interface ModelListResponse {
  items: ModelItem[]
  total: number
}

export interface ModelTestRequest {
  model_ids?: number[]
  test_prompt?: string
  timeout?: number
}

export interface ModelTestResult {
  id: number
  model_id: string
  name: string
  status: 'available' | 'unavailable'
  latency_ms?: number
  error?: string
}

export interface ModelTestResponse {
  total: number
  available: number
  unavailable: number
  results: ModelTestResult[]
}

// ============================================================================
// 标签管理相关类型
// ============================================================================

export interface TagItem {
  id: number
  name: string
  color?: string
  description?: string
  sort_order: number
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface TagCreateRequest {
  name: string
  color?: string
  description?: string
  sort_order?: number
}

export interface TagUpdateRequest {
  name?: string
  color?: string
  description?: string
  sort_order?: number
  is_active?: boolean
}

export interface TagListResponse {
  items: TagItem[]
  total: number
}

// ============================================================================
// 健康检查响应
// ============================================================================

export interface HealthCheckResponse {
  status: string
  total_models: number
  available_models: number
  total_api_configs: number
}

// ============================================================================
// API 方法
// ============================================================================

const modelManagementApi = {
  // ==================== API 配置管理 ====================
  getApiConfigs(params?: { provider?: string; is_active?: boolean; user_id?: string }) {
    return request.get<ApiConfigListResponse>('/v1/model-management/api-configs', { params })
  },

  getApiConfig(configId: number) {
    return request.get<ApiConfigItem>(`/v1/model-management/api-configs/${configId}`)
  },

  createApiConfig(data: ApiConfigCreateRequest) {
    return request.post<ApiConfigItem>('/v1/model-management/api-configs', data)
  },

  updateApiConfig(configId: number, data: ApiConfigUpdateRequest) {
    return request.put<ApiConfigItem>(`/v1/model-management/api-configs/${configId}`, data)
  },

  deleteApiConfig(configId: number) {
    return request.delete(`/v1/model-management/api-configs/${configId}`)
  },

  setDefaultApiConfig(configId: number, userId?: string) {
    return request.post(`/v1/model-management/api-configs/${configId}/set-default`, null, {
      params: { user_id: userId },
    })
  },

  // ==================== 模型管理 ====================
  getModels(params?: { provider?: string; status?: string; is_active?: boolean; user_id?: string }) {
    return request.get<ModelListResponse>('/v1/model-management/models', { params })
  },

  getModel(modelId: number) {
    return request.get<ModelItem>(`/v1/model-management/models/${modelId}`)
  },

  createModel(data: ModelCreateRequest) {
    return request.post<ModelItem>('/v1/model-management/models', data)
  },

  updateModel(modelId: number, data: ModelUpdateRequest) {
    return request.put<ModelItem>(`/v1/model-management/models/${modelId}`, data)
  },

  deleteModel(modelId: number) {
    return request.delete(`/v1/model-management/models/${modelId}`)
  },

  testModels(data: ModelTestRequest, userId?: string) {
    return request.post<ModelTestResponse>('/v1/model-management/models/test', data, {
      params: { user_id: userId },
    })
  },

  // ==================== 标签管理 ====================
  getTags(params?: { is_active?: boolean }) {
    return request.get<TagListResponse>('/v1/model-management/tags', { params })
  },

  getTag(tagId: number) {
    return request.get<TagItem>(`/v1/model-management/tags/${tagId}`)
  },

  createTag(data: TagCreateRequest) {
    return request.post<TagItem>('/v1/model-management/tags', data)
  },

  updateTag(tagId: number, data: TagUpdateRequest) {
    return request.put<TagItem>(`/v1/model-management/tags/${tagId}`, data)
  },

  deleteTag(tagId: number) {
    return request.delete(`/v1/model-management/tags/${tagId}`)
  },

  // ==================== 健康检查 ====================
  healthCheck() {
    return request.get<HealthCheckResponse>('/v1/model-management/health')
  },
}

export { modelManagementApi }
