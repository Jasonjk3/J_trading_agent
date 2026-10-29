import { request } from './request'

/** 交易所代码 */
export type ExchangeCode = 'binance' | 'okx' | 'bybit'

/** Agent 运行状态 */
export type AgentStatus = 'running' | 'stopped'

/** 交易风格 */
export type TradingStyle = 'conservative' | 'balanced' | 'aggressive'

/** 市场模式 */
export type MarketMode = 'auto' | 'trend_only' | 'range_only'

/** 交易周期 */
export type TradingCycle = 'short_term' | 'medium_term' | 'long_term'

/** 持仓方向限制 */
export type PositionDirection = 'long_only' | 'short_only' | 'both'

/** 技术分析周期 */
export type TechnicalAnalysisTimeframe =
  | '1m'
  | '5m'
  | '15m'
  | '30m'
  | '1h'
  | '2h'
  | '4h'
  | '6h'
  | '12h'
  | '1d'
  | '1w'

/** 决策模式 */
export type DecisionMode = 'trader' | 'rule'

/** 规则决策配置 */
export interface RuleConfig {
  /** 预设模板 ID */
  preset?: string
  /** 启用的规则 ID */
  enabledRules?: string[]
  /** 从预设中排除的规则 */
  disabledRules?: string[]
  /** 组合策略 */
  composition?: 'priority_stack'
  /** 按规则覆盖参数 */
  overrides?: Record<string, Record<string, number | string | boolean>>
}

export interface TraderConfig {
  /** shadow 只记录订单意图；live 才允许进入风险与执行链路 */
  executionMode: 'shadow' | 'live'
  maxToolCallsPerTurn?: number
  maxOrderRevisionsPerTurn?: number
  turnTimeoutSeconds?: number
  defaultReviewIntervalMinutes?: number
}

/** 目标利润配置 */
export interface TargetProfitConfig {
  /** 目标利润类型 */
  type: 'fixed' | 'percentage'
  /** fixed: 目标利润金额(USDT)；percentage: 本金百分比 */
  value: number
}

/** 策略配置 */
export interface StrategyConfig {
  tradingStyle: TradingStyle
  symbols: string[]
  /** 初始本金(USDT) */
  initialCapital: number
  /** 目标利润 */
  targetProfit: TargetProfitConfig
  /** 交易周期 */
  tradingCycle: TradingCycle
  /** 单次交易最小金额(USDT) */
  minOrderAmount: number
  /** 单笔最大保证金(USDT)，名义价值可按批准杠杆放大 */
  maxOrderAmount: number
  /** 全部持仓保证金占账户权益的上限(1-100%) */
  maxPositionRatio?: number
  /** 每次 reduce_* 动作减少当前仓位的比例(1-100%) */
  reducePositionRatio?: number
  /** 最大杠杆倍数(1-125) */
  maxLeverage: number
  /** 持仓方向限制: 仅做多/仅做空/均可 */
  positionDirection: PositionDirection
  /** 市场模式: 自动识别/仅趋势/仅震荡 */
  marketMode?: MarketMode
  /** 震荡策略做多 RSI 阈值 */
  rangeRsiLongThreshold?: number
  /** 震荡策略做空 RSI 阈值 */
  rangeRsiShortThreshold?: number
  /** 震荡策略入场时距离布林轨道的容忍比例 */
  rangeEntryBandTolerance?: number
  /** 震荡策略止盈模式 */
  rangeTakeProfitMode?: 'mid_band' | 'opposite_band'
  /** 备注 */
  remark?: string
  /** 是否注入消息面（服务端按 newsIntelligenceAgentId 查资讯） */
  useNewsAnalysis?: boolean
  /** 消息面采集任务 ID（news_intelligence_agents） */
  newsIntelligenceAgentId?: string
  /** 单次决策最多带入的资讯条数 */
  newsContextMaxItems?: number
  /** 是否注入技术面（按交易对查 technical_analysis_records） */
  useTechnicalAnalysis?: boolean
  /** 技术分析执行周期 */
  technicalAnalysisTimeframe?: TechnicalAnalysisTimeframe
  /** 额外纳入决策的高周期背景列表 */
  technicalAnalysisContextTimeframes?: TechnicalAnalysisTimeframe[]
  /** 决策模式：trader | rule */
  decisionMode?: DecisionMode
  /** 交易员运行预算与复核节奏 */
  traderConfig?: TraderConfig
  /** 不可由交易员绕过的账户与订单硬约束 */
  hardRiskPolicy?: Record<string, unknown>
  /** 仅供交易员参考、不参与代码否决的交易偏好 */
  preferences?: Record<string, unknown>
  /** 回测 LLM 响应处理：始终实时调用，或实时调用并保存成功响应；两者都不读缓存 */
  llmCacheMode?: 'fresh' | 'record'
  /** 规则模式配置 */
  ruleConfig?: RuleConfig
  /** 交易员模型管理主键（decisionMode=trader 时） */
  decisionLlmModelId?: number
  /** 决策 LLM 温度 */
  decisionLlmTemperature?: number
  /** 技术面自动分析所用模型（库中无记录时） */
  technicalAnalysisLlmModelId?: number
  /** 技术面分析回溯天数 */
  technicalAnalysisLookbackDays?: number
  /** 技术面分析 LLM 温度 */
  technicalAnalysisTemperature?: number
}

/** Agent 列表项 */
export interface AgentListItem {
  id: string
  name: string
  exchangeId: string
  exchange?: ExchangeCode
  /** LLM 模型 ID */
  llmModelId?: number
  /** LLM 模型名称 */
  llmModelName?: string
  remark?: string
  status: AgentStatus
  lastRunAt?: string
  createdAt: string
  updatedAt: string
  /** 策略配置 */
  strategyConfig?: StrategyConfig
  /** 今日收益率(%) */
  todayProfit?: number
  /** 总收益(USDT) */
  totalProfit?: number
  /** 胜率(%) */
  winRate?: number
  /** 总交易笔数 */
  totalTrades?: number
}

/** 创建/编辑 Agent DTO */
export interface CreateAgentDto {
  name: string
  exchangeId: string
  /** LLM 模型 ID */
  llmModelId?: number
  remark?: string
  /** 策略配置 */
  strategyConfig?: StrategyConfig
}

export type UpdateAgentDto = Partial<CreateAgentDto>

/** 将 Agent 表上的旧版 llmModelId 回填到策略配置的 decisionLlmModelId（仅展示/编辑用） */
export function mergeLegacyDecisionLlm(
  config: StrategyConfig,
  legacyAgentLlmModelId?: number
): StrategyConfig {
  const merged = { ...config }
  const mode = merged.decisionMode ?? 'trader'
  if (mode !== 'rule' && merged.decisionLlmModelId == null && legacyAgentLlmModelId != null) {
    merged.decisionLlmModelId = legacyAgentLlmModelId
  }
  return merged
}

/** 提交时把策略中的决策 LLM 同步到 Agent 基础字段，兼容后端回退链 */
export function syncAgentLlmFromStrategy(payload: CreateAgentDto): CreateAgentDto {
  const cfg = payload.strategyConfig
  if (cfg?.decisionMode === 'trader' && cfg.decisionLlmModelId != null) {
    return { ...payload, llmModelId: cfg.decisionLlmModelId }
  }
  if (cfg?.decisionMode === 'rule') {
    return { ...payload, llmModelId: undefined }
  }
  return payload
}

/** 更新策略配置 DTO */
export interface UpdateStrategyConfigDto {
  strategyConfig: StrategyConfig
}

/** 收益曲线数据点 */
export interface ProfitCurvePoint {
  time: string
  value: string
  cumulative?: string
  unrealizedPnl?: string
  unrealizedPnlRate?: string
}

/** 收益曲线响应 */
export interface AgentProfitCurveRes {
  points: ProfitCurvePoint[]
  period?: string
}

/** 操作类型 */
export type OperationType = 'open_long' | 'open_short' | 'close_long' | 'close_short' | 'adjust' | 'cancel_order' | 'other'

/** Agent 操作记录项（含思维链可内嵌） */
export interface AgentOperationItem {
  id: string
  agentId: string
  type: OperationType
  symbol?: string
  exchange?: ExchangeCode
  side?: 'buy' | 'sell'
  quantity?: string
  price?: string
  reason?: string
  result?: 'success' | 'failed' | 'partial'
  createdAt: string
  /** 思维链详情（可内嵌或单独接口） */
  chainOfThought?: ChainOfThoughtStep[]
}

/** 思维链单步 */
export interface ChainOfThoughtStep {
  step: number
  thought: string
  conclusion?: string
}

/** 操作记录列表响应 */
export interface AgentOperationsRes {
  list: AgentOperationItem[]
  total: number
}

export interface TraderRuntimeEvent {
  id: string
  decisionId?: string
  type: string
  payload: Record<string, unknown>
  occurredAt: string
}

export interface TraderRuntimeRes {
  sessionId: string
  state: Record<string, unknown> | null
  stateRevision: number
  nextReviewAt?: string
  turns: Record<string, unknown>[]
  events: TraderRuntimeEvent[]
}

export const agentsApi = {
  getList(): Promise<{ list: AgentListItem[]; total: number }> {
    return request.get('/v1/trading-agents') as Promise<{ list: AgentListItem[]; total: number }>
  },

  getById(id: string): Promise<AgentListItem> {
    return request.get(`/v1/trading-agents/${id}`) as Promise<AgentListItem>
  },

  create(dto: CreateAgentDto): Promise<AgentListItem> {
    return request.post('/v1/trading-agents', dto) as Promise<AgentListItem>
  },

  update(id: string, dto: UpdateAgentDto): Promise<AgentListItem> {
    return request.put(`/v1/trading-agents/${id}`, dto) as Promise<AgentListItem>
  },

  delete(id: string): Promise<void> {
    return request.delete(`/v1/trading-agents/${id}`) as Promise<void>
  },

  start(id: string): Promise<{ success: boolean; message?: string }> {
    return request.post(`/v1/trading-agents/${id}/start`) as Promise<{ success: boolean; message?: string }>
  },

  stop(id: string): Promise<{ success: boolean; message?: string }> {
    return request.post(`/v1/trading-agents/${id}/stop`) as Promise<{ success: boolean; message?: string }>
  },

  getProfitCurve(id: string, params?: { period?: string }): Promise<AgentProfitCurveRes> {
    return request.get(`/v1/trading-agents/${id}/profit-curve`, { params }) as Promise<AgentProfitCurveRes>
  },

  getPositions(id: string): Promise<{ list: import('./positions').PositionListItem[]; total: number }> {
    return request.get(`/v1/trading-agents/${id}/positions`) as Promise<{ list: import('./positions').PositionListItem[]; total: number }>
  },

  getOrders(id: string, params?: { status?: string; page?: number; pageSize?: number }): Promise<import('./orders').OrderListRes> {
    return request.get(`/v1/trading-agents/${id}/orders`, { params }) as Promise<import('./orders').OrderListRes>
  },

  getOperations(id: string, params?: { limit?: number }): Promise<AgentOperationsRes> {
    return request.get(`/v1/trading-agents/${id}/operations`, { params }) as Promise<AgentOperationsRes>
  },

  getTraderRuntime(id: string, params?: { limit?: number }): Promise<TraderRuntimeRes> {
    return request.get(`/v1/trading-agents/${id}/trader-runtime`, { params }) as Promise<TraderRuntimeRes>
  },

  getStrategyConfig(id: string): Promise<{ strategyConfig: StrategyConfig | null }> {
    return request.get(`/v1/trading-agents/${id}/strategy-config`) as Promise<{ strategyConfig: StrategyConfig | null }>
  },

  updateStrategyConfig(id: string, dto: UpdateStrategyConfigDto): Promise<{ success: boolean }> {
    return request.put(`/v1/trading-agents/${id}/strategy-config`, dto) as Promise<{ success: boolean }>
  },
}
