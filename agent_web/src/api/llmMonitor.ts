import { request } from './request'

// ============================================================================
// 使用量相关类型
// ============================================================================

export interface PaginationInfo {
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface UsageLogItem {
  id: number
  request_id: string
  model_name: string
  model_provider: string
  agent_name?: string
  task_type?: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
  cost_cny: number
  response_time_ms: number
  status: string
  error_message?: string
  user_id?: string
  session_id?: string
  created_at: string
  extra_data?: Record<string, any>
}

export interface UsageHistoryParams {
  start_time?: string
  end_time?: string
  model_name?: string
  agent_name?: string
  status?: string
  user_id?: string
  page?: number
  page_size?: number
}

export interface UsageHistoryResponse {
  items: UsageLogItem[]
  pagination: PaginationInfo
}

export interface RealtimeUsageData {
  total_requests: number
  total_tokens: number
  total_cost_cny: number
  success_rate: number
  avg_response_time_ms?: number
}

export interface TopAgentItem {
  name: string
  requests: number
}

export interface RealtimeUsageResponse {
  today: RealtimeUsageData
  current_hour: RealtimeUsageData
  active_models: string[]
  top_agents: TopAgentItem[]
}

// ============================================================================
// 统计相关类型
// ============================================================================

export interface DailyStatsParams {
  start_date: string
  end_date: string
  model_name?: string
  agent_name?: string
  group_by?: 'model' | 'agent' | 'none'
}

export interface DailyStatsItem {
  date: string
  model_name?: string
  agent_name?: string
  total_requests: number
  success_requests: number
  failed_requests: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
  cost_cny: number
  avg_response_time_ms: number
  p50_response_time_ms?: number
  p99_response_time_ms?: number
}

export interface DailyStatsSummary {
  total_requests: number
  total_tokens: number
  total_cost_usd: number
  total_cost_cny: number
}

export interface DailyStatsResponse {
  items: DailyStatsItem[]
  summary: DailyStatsSummary
}

export interface OverviewStatsResponse {
  today: DailyStatsSummary
  this_week: DailyStatsSummary
  this_month: DailyStatsSummary
  success_rate: number
  avg_response_time_ms: number
}

export interface ModelStatsItem {
  model_name: string
  model_provider: string
  total_requests: number
  total_tokens: number
  cost_cny: number
  avg_response_time_ms: number
  success_rate: number
}

export interface ModelStatsResponse {
  items: ModelStatsItem[]
  total_models: number
}

export interface AgentStatsItem {
  agent_name: string
  total_requests: number
  total_tokens: number
  cost_cny: number
  avg_response_time_ms: number
  success_rate: number
  primary_model: string
}

export interface AgentStatsResponse {
  items: AgentStatsItem[]
  total_agents: number
}

// ============================================================================
// 费用相关类型
// ============================================================================

export interface CostSummaryParams {
  start_date?: string
  end_date?: string
  group_by?: 'model' | 'agent'
}

export interface CostPeriodSummary {
  cost_cny: number
  cost_usd: number
  tokens: number
}

export interface CostModelItem {
  model_name: string
  cost_cny: number
  percentage: number
}

export interface CostAgentItem {
  agent_name: string
  cost_cny: number
  percentage: number
}

export interface CostSummaryResponse {
  today: CostPeriodSummary
  this_week: CostPeriodSummary
  this_month: CostPeriodSummary
  by_model: CostModelItem[]
  by_agent: CostAgentItem[]
  total_cost_usd: number
  total_cost_cny: number
}

export interface CostTrendParams {
  start_date: string
  end_date: string
  granularity?: 'day' | 'week' | 'month'
}

export interface CostTrendItem {
  period: string
  cost_usd: number
  cost_cny: number
  tokens: number
  requests: number
}

export interface CostTrendResponse {
  items: CostTrendItem[]
  total_cost_cny: number
}

// ============================================================================
// 配置管理类型
// ============================================================================

export interface ModelCostConfigItem {
  id: number
  model_name: string
  provider: string
  input_price_per_1m: number
  output_price_per_1m: number
  currency: string
  exchange_rate: number
  effective_date: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ModelCostConfigListResponse {
  items: ModelCostConfigItem[]
  total: number
}

export interface ModelCostConfigCreateRequest {
  model_name: string
  provider: string
  input_price_per_1m: number
  output_price_per_1m: number
  exchange_rate?: number
  effective_date: string
  is_active?: boolean
}

export interface ModelCostConfigUpdateRequest {
  input_price_per_1m?: number
  output_price_per_1m?: number
  exchange_rate?: number
  is_active?: boolean
}

// ============================================================================
// 预警相关类型
// ============================================================================

export interface AlertRuleItem {
  id: number
  rule_name: string
  alert_type: string
  threshold_value: number
  model_name?: string
  agent_name?: string
  notify_channels: Record<string, any>
  is_active: boolean
  cooldown_minutes: number
  created_at: string
  updated_at: string
}

export interface AlertRuleListResponse {
  items: AlertRuleItem[]
  total: number
}

export interface AlertRuleCreateRequest {
  rule_name: string
  alert_type: 'daily_cost' | 'monthly_cost' | 'single_request'
  threshold_value: number
  model_name?: string
  agent_name?: string
  notify_channels: Record<string, any>
  is_active?: boolean
  cooldown_minutes?: number
}

export interface AlertRuleUpdateRequest {
  rule_name?: string
  threshold_value?: number
  notify_channels?: Record<string, any>
  is_active?: boolean
  cooldown_minutes?: number
}

export interface AlertHistoryItem {
  id: number
  rule_id: number
  rule_name?: string
  alert_type: string
  current_value: number
  threshold_value: number
  alert_message: string
  notify_status: string
  notify_result?: Record<string, any>
  created_at: string
}

export interface AlertHistoryParams {
  start_time?: string
  end_time?: string
  rule_id?: number
  alert_type?: string
  notify_status?: string
  page?: number
  page_size?: number
}

export interface AlertHistoryResponse {
  items: AlertHistoryItem[]
  pagination: PaginationInfo
}

// ============================================================================
// API 方法
// ============================================================================

const llmMonitorApi = {
  // 使用量 API
  getRealtimeUsage() {
    return request.get<RealtimeUsageResponse>('/v1/monitor/usage/realtime')
  },

  getUsageHistory(params?: UsageHistoryParams) {
    return request.get<UsageHistoryResponse>('/v1/monitor/usage/history', { params })
  },

  // 统计 API
  getOverviewStats() {
    return request.get<OverviewStatsResponse>('/v1/monitor/stats/overview')
  },

  getDailyStats(params: DailyStatsParams) {
    return request.get<DailyStatsResponse>('/v1/monitor/stats/daily', { params })
  },

  getStatsByModel(params?: { start_date?: string; end_date?: string }) {
    return request.get<ModelStatsResponse>('/v1/monitor/stats/by-model', { params })
  },

  getStatsByAgent(params?: { start_date?: string; end_date?: string }) {
    return request.get<AgentStatsResponse>('/v1/monitor/stats/by-agent', { params })
  },

  // 费用 API
  getCostSummary(params?: CostSummaryParams) {
    return request.get<CostSummaryResponse>('/v1/monitor/cost/summary', { params })
  },

  getCostTrend(params: CostTrendParams) {
    return request.get<CostTrendResponse>('/v1/monitor/cost/trend', { params })
  },

  // 配置管理 API
  getModelConfigs(params?: { model_name?: string; provider?: string; is_active?: boolean }) {
    return request.get<ModelCostConfigListResponse>('/v1/monitor/config/models', { params })
  },

  createModelConfig(data: ModelCostConfigCreateRequest) {
    return request.post<ModelCostConfigItem>('/v1/monitor/config/models', data)
  },

  updateModelConfig(configId: number, data: ModelCostConfigUpdateRequest) {
    return request.put<ModelCostConfigItem>(`/v1/monitor/config/models/${configId}`, data)
  },

  deleteModelConfig(configId: number) {
    return request.delete(`/v1/monitor/config/models/${configId}`)
  },

  // 预警 API
  getAlertRules(params?: { is_active?: boolean }) {
    return request.get<AlertRuleListResponse>('/v1/monitor/alert/rules', { params })
  },

  createAlertRule(data: AlertRuleCreateRequest) {
    return request.post<AlertRuleItem>('/v1/monitor/alert/rules', data)
  },

  updateAlertRule(ruleId: number, data: AlertRuleUpdateRequest) {
    return request.put<AlertRuleItem>(`/v1/monitor/alert/rules/${ruleId}`, data)
  },

  deleteAlertRule(ruleId: number) {
    return request.delete(`/v1/monitor/alert/rules/${ruleId}`)
  },

  getAlertHistory(params?: AlertHistoryParams) {
    return request.get<AlertHistoryResponse>('/v1/monitor/alert/history', { params })
  },

  triggerAlertCheck(ruleId?: number) {
    return request.post('/v1/monitor/alert/check', null, { params: { rule_id: ruleId } })
  },
}

export { llmMonitorApi }
