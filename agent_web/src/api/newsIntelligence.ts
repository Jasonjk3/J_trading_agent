import { request } from './request'

/** 采集任务状态 */
export type NewsIntelAgentStatus = 'running' | 'stopped'

/** 预设金融方向（可多选） */
export const FINANCIAL_SECTOR_OPTIONS = [
  { value: 'banking', label: '银行' },
  { value: 'securities', label: '证券' },
  { value: 'insurance', label: '保险' },
  { value: 'fund', label: '基金' },
  { value: 'fintech', label: '金融科技' },
  { value: 'macro', label: '宏观政策' },
  { value: 'market_sentiment', label: '市场舆情' },
] as const

export type FinancialSectorValue = (typeof FINANCIAL_SECTOR_OPTIONS)[number]['value']

/** 消息面采集 Agent 列表项 */
export interface NewsIntelligenceAgentListItem {
  id: string
  name: string
  remark?: string
  /** 金融方向 code 列表 */
  sectors: string[]
  customKeywords?: string
  symbolCodes?: string
  llmModelId: number
  llmModelName?: string
  /** 采集间隔（分钟） */
  intervalMinutes: number
  maxItemsPerBatch?: number
  temperature?: number
  status: NewsIntelAgentStatus
  lastRunAt?: string
  createdAt: string
  updatedAt: string
}

export interface CreateNewsIntelligenceAgentDto {
  name: string
  remark?: string
  sectors: string[]
  customKeywords?: string
  symbolCodes?: string
  llmModelId: number
  intervalMinutes: number
  maxItemsPerBatch?: number
  temperature?: number
  /** 创建后是否启动 */
  runOnCreate?: boolean
}

export type UpdateNewsIntelligenceAgentDto = Partial<CreateNewsIntelligenceAgentDto>

/** 时间轴单条资讯 */
export interface NewsTimelineItem {
  id: string
  agentId: string
  title: string
  summary?: string
  sourceUrl?: string
  sourceName?: string
  /** 资讯发生/发布时间 */
  eventTime?: string
  /** 系统入库/创建时间（与发布时间可能不同） */
  ingestedAt: string
  /** 展示排序时间 */
  sortTime: string
}

export interface NewsTimelineListParams {
  from?: string
  to?: string
  order?: 'asc' | 'desc'
  page?: number
  pageSize?: number
  keyword?: string
}

export interface NewsTimelineListRes {
  list: NewsTimelineItem[]
  total: number
}

export const newsIntelligenceApi = {
  getList(): Promise<{ list: NewsIntelligenceAgentListItem[]; total: number }> {
    return request.get('/v1/news-intelligence-agents') as Promise<{
      list: NewsIntelligenceAgentListItem[]
      total: number
    }>
  },

  getById(id: string): Promise<NewsIntelligenceAgentListItem> {
    return request.get(`/v1/news-intelligence-agents/${id}`) as Promise<NewsIntelligenceAgentListItem>
  },

  create(dto: CreateNewsIntelligenceAgentDto): Promise<NewsIntelligenceAgentListItem> {
    return request.post('/v1/news-intelligence-agents', dto) as Promise<NewsIntelligenceAgentListItem>
  },

  update(id: string, dto: UpdateNewsIntelligenceAgentDto): Promise<NewsIntelligenceAgentListItem> {
    return request.put(`/v1/news-intelligence-agents/${id}`, dto) as Promise<NewsIntelligenceAgentListItem>
  },

  delete(id: string): Promise<void> {
    return request.delete(`/v1/news-intelligence-agents/${id}`) as Promise<void>
  },

  start(id: string): Promise<{ success: boolean; message?: string }> {
    return request.post(`/v1/news-intelligence-agents/${id}/start`) as Promise<{ success: boolean; message?: string }>
  },

  stop(id: string): Promise<{ success: boolean; message?: string }> {
    return request.post(`/v1/news-intelligence-agents/${id}/stop`) as Promise<{ success: boolean; message?: string }>
  },

  /** 立即执行一轮采集（忽略调度间隔；不要求任务处于运行中） */
  collectNow(id: string): Promise<{ success: boolean; inserted: number; message?: string }> {
    return request.post(`/v1/news-intelligence-agents/${id}/collect`) as Promise<{
      success: boolean
      inserted: number
      message?: string
    }>
  },

  getTimelineItems(id: string, params?: NewsTimelineListParams): Promise<NewsTimelineListRes> {
    return request.get(`/v1/news-intelligence-agents/${id}/items`, { params }) as Promise<NewsTimelineListRes>
  },
}
