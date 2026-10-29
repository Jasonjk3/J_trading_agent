import { request } from './request'

/** 与后端 technical_analysis_service._format_response 对齐 */
export interface TaAnalysisBlock {
  summary?: string
  trend?: {
    direction?: string
    strength?: string
    description?: string
  }
  momentum?: {
    rsiStatus?: string
    macdStatus?: string
    description?: string
  }
  volatility?: {
    status?: string
    bollingerPosition?: string
    description?: string
  }
  supportResistance?: Record<string, unknown>
  signals?: Array<{ type?: string; indicator?: string; description?: string }>
  recommendation?: {
    action?: string
    confidence?: number
    entryZone?: string
    stopLoss?: string
    takeProfit?: string
    riskWarning?: string
  }
}

export interface TechnicalAnalysisResult {
  success: boolean
  symbol: string
  analysisDate?: string
  timeframe?: string
  analysisMode?: string
  /** 落库后的记录 ID（需登录且库表已创建） */
  recordId?: string
  /** 本次分析使用的模型管理 ID（仅在选择模型时返回） */
  llmModelId?: number
  llmModelName?: string
  analysis?: TaAnalysisBlock
  rawIndicators?: Record<string, unknown>
  error?: string
}

/** 生成记录列表项（与后端 list_generation_records items 对齐） */
export interface TechnicalAnalysisRecordItem {
  id: string
  symbol: string
  analysisDate?: string | null
  timeframe: string
  lookbackDays: number
  temperature?: number | null
  llmModelId?: number | null
  llmModelName?: string | null
  success: boolean
  errorMessage?: string | null
  summaryPreview?: string | null
  createdAt?: string | null
}

export interface TechnicalAnalysisRecordListData {
  items: TechnicalAnalysisRecordItem[]
  total: number
  page: number
  pageSize: number
}

export interface TechnicalAnalysisRecordDetailData {
  id: string
  createdAt?: string | null
  /** 与 analyze 成功时 data 结构一致 */
  snapshot: TechnicalAnalysisResult
}

export interface IndicatorDetailResult {
  success: boolean
  symbol: string
  timeframe?: string
  indicators?: Record<string, unknown>
  klineCount?: number
  error?: string
}

export interface AnalyzeParams {
  symbol: string
  analysisDate?: string
  timeframe?: string
  lookbackDays?: number
  /** 模型管理中的模型 ID；不传则后端使用环境变量默认 DeepSeek */
  llmModelId?: number
  /** LLM 温度 0～2，默认 0.3 */
  temperature?: number
}

const ANALYZE_TIMEOUT_MS = 120000

const technicalAnalysisApi = {
  analyze(body: AnalyzeParams) {
    return request.post<TechnicalAnalysisResult>('/v1/technical-analysis/analyze', body, {
      timeout: ANALYZE_TIMEOUT_MS,
    })
  },

  getIndicators(params: { symbol: string; timeframe?: string; lookbackDays?: number }) {
    return request.get<IndicatorDetailResult>('/v1/technical-analysis/indicators', { params })
  },

  getSupportedTimeframes() {
    return request.get<{ timeframes: Array<{ value: string; label: string; okx: string }> }>(
      '/v1/technical-analysis/supported-timeframes'
    )
  },

  listRecords(params?: { page?: number; pageSize?: number }) {
    return request.get<TechnicalAnalysisRecordListData>('/v1/technical-analysis/records', {
      params,
    })
  },

  getRecord(recordId: string) {
    return request.get<TechnicalAnalysisRecordDetailData>(
      `/v1/technical-analysis/records/${encodeURIComponent(recordId)}`
    )
  },
}

export { technicalAnalysisApi }
