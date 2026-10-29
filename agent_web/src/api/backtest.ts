import { request } from './request'
import type { StrategyConfig, ExchangeCode } from './agents'

/** K线周期 */
export type KlineInterval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'

/** 回测任务状态 */
export type BacktestStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

/** 时间序列数据点 */
export interface TimeSeriesPoint {
  time: string
  value: number
  unrealizedPnl?: number
  unrealizedPnlRate?: number
}

/** 持仓数据点 */
export interface PositionPoint {
  time: string
  symbol: string
  side: 'long' | 'short'
  quantity: number
  entryPrice: number
  currentPrice: number
  unrealizedPnl: number
}

/** Agent 单步思考 */
export interface ThoughtStep {
  step?: string
  thought?: string
  conclusion?: string
  [key: string]: unknown
}

/** 规则命中记录 */
export interface RuleHitRecord {
  rule_id: string
  action?: string
  reason?: string
  confidence?: number
  signals?: string[]
  score?: number
  metadata?: Record<string, unknown>
}

/** 决策经过执行价、流动性和风控复核后的最终回执 */
export interface BacktestExecutionResult {
  status: 'pending' | 'submitted' | 'kept' | 'partially_filled' | 'filled' | 'rejected' | 'no_action' | 'error'
  requestedAction?: string
  finalAction?: string
  tradeId?: string
  side?: 'buy' | 'sell'
  tradeType?: 'open' | 'close'
  quantity?: number
  price?: number
  amount?: number
  requestedLeverage?: number
  approvedLeverage?: number
  orderType?: 'limit' | 'market'
  limitPrice?: number | null
  stopLossPrice?: number | null
  takeProfitPrice?: number | null
  executionRole?: string
  clientIntentId?: string | null
  parentIntentId?: string | null
  orderId?: string
  expiresAt?: string
  marginUsed?: number
  fee?: number
  pnl?: number
  pnlPercent?: number
  balanceAfter?: number
  positionQuantityAfter?: number
  message?: string
}

/** 单次决策记录（含 hold / 开平仓） */
export interface BacktestDecisionRecord {
  /** 决策记录主键，用于按需加载完整详情 */
  id?: string
  timestamp: string
  action: string
  errorType?: string
  symbol?: string
  quantity?: number
  /** 决策时点该交易对（或首个配置标的）的参考价 */
  currentPrice?: number | null
  reasoning?: string
  /** 最终决策分析结论 */
  decisionAnalysis?: string
  /** 当次注入给决策 Agent 的技术分析全文 */
  technicalAnalysis?: string
  chainOfThought?: ThoughtStep[]
  /** 决策模式 */
  decisionMode?: 'trader' | 'rule'
  /** 市场状态（规则模式） */
  regime?: string
  /** 触发的规则 */
  ruleHits?: RuleHitRecord[]
  /** 信号标签 */
  signals?: string[]
  /** 指标快照（规则模式） */
  indicatorsSnapshot?: Record<string, unknown>
  /** 当次决策完整 prompt（LLM 模式） */
  decisionPrompt?: string
  /** LLM 原始响应 */
  llmRawResponse?: string
  /** 解析后的决策 JSON 字符串 */
  parsedDecision?: string
  /** LLM 元数据 */
  llmMetadata?: Record<string, unknown>
  /** 风控复核与撮合之后的最终结果；不同于模型提出的原始意图 */
  executionResult?: BacktestExecutionResult
}

/** 交易记录 */
export interface BacktestTradeRecord {
  id: string
  timestamp: string
  symbol: string
  side: 'buy' | 'sell'
  type: 'open' | 'close'
  /** 最终细粒度动作；旧记录可能为空，此时由 side/type 兼容推断 */
  action?: 'open_long' | 'open_short' | 'add_long' | 'add_short' | 'reduce_long' | 'reduce_short' | 'close_long' | 'close_short'
  price: number
  quantity: number
  amount: number
  leverage?: number
  marginUsed?: number
  fee: number
  pnl: number
  pnlPercent: number
  balance: number
  reasoning?: string
  signals?: string[]
  /** Agent 思考过程（思维链） */
  chainOfThought?: ThoughtStep[]
}

/** 回测配置 */
export interface BacktestConfig {
  /** 关联的 Agent ID */
  agentId: string
  /** Agent 名称 (冗余存储便于展示) */
  agentName?: string
  /** 策略配置 */
  strategyConfig: StrategyConfig
  /** 开始时间 */
  startTime: string
  /** 结束时间 */
  endTime: string
  /** 初始资金 */
  initialCapital: number
  /** 交易所 */
  exchange: ExchangeCode
  /** 交易对列表 */
  symbols: string[]
  /** K线周期 */
  interval: KlineInterval
  /** Maker 手续费率 (%) */
  makerFee: number
  /** Taker 手续费率 (%) */
  takerFee: number
  /** 滑点 (%) */
  slippage: number
}

/** 交易对在回测区间的价格 */
export interface SymbolPrices {
  startPrice: number
  endPrice: number
}

/** 回测结束时未平仓持仓 */
export interface OpenPositionAtEnd {
  symbol: string
  side: string
  quantity: number
  entryPrice: number
  endPrice: number
  unrealizedPnl: number
  leverage?: number
  marginUsed?: number
}

/** 运行中当前持仓（含现价） */
export interface LiveOpenPosition {
  symbol: string
  side: string
  quantity: number
  entryPrice: number
  currentPrice: number
  /** 与完成后 openPositions.endPrice 对齐 */
  endPrice?: number
  unrealizedPnl: number
  /** 标的价格变化收益率（未计杠杆） */
  unrealizedPnlPercent?: number
  /** 保证金收益率（未实现盈亏 / 占用保证金） */
  roiPercent?: number
  entryTime?: string
  notional?: number
  leverage?: number
  marginUsed?: number
  tradePlan?: {
    stopLossPrice?: number | null
    takeProfitPrice?: number | null
    thesis?: string
    invalidation?: string
  }
}

/** 回测撮合引擎中尚未完全成交的活动委托 */
export interface BacktestActiveOrder {
  orderId: string
  proposalId?: string | null
  clientIntentId?: string | null
  parentIntentId?: string | null
  parentPositionId?: string | null
  symbol: string
  action: string
  side: 'buy' | 'sell'
  positionSide: 'long' | 'short'
  orderType: 'limit' | 'market'
  executionRole?: string
  limitPrice: number
  currentPrice?: number | null
  distancePct?: number | null
  quantity: number
  remainingQuantity: number
  filledQuantity: number
  requestedLeverage?: number | null
  stopLossPrice?: number | null
  takeProfitPrice?: number | null
  thesis?: string | null
  invalidation?: string | null
  rationale?: string | null
  createdAt: string
  expiresAt?: string | null
  ageBars?: number | null
  maxAgeBars?: number | null
  maxDistancePct?: number | null
  status: string
}

/** 运行中最近一次动作摘要 */
export interface LiveLastAction {
  kind: 'decision' | 'trade'
  timestamp?: string | null
  action?: string
  side?: string
  type?: string
  symbol?: string
  price?: number
  summary?: string
}

/** 回测结果统计 */
export interface BacktestStatistics {
  /** 总收益率 (%) */
  totalReturn: number
  /** 年化收益率 (%) */
  annualizedReturn: number
  /** 最大回撤 (%) */
  maxDrawdown: number
  /** 夏普比率 */
  sharpeRatio: number
  /** 索提诺比率 */
  sortinoRatio: number
  /** 胜率(%)，已平仓笔数中的胜率 */
  winRate: number
  /** 盈利因子(毛利/毛损) */
  profitFactor: number
  /** 已完成的开仓—平仓交易数（非成交腿数） */
  totalTrades: number
  /** 已平仓笔数 */
  closedTrades?: number
  /** 盈利次数(已平仓) */
  winTrades: number
  /** 亏损次数(已平仓) */
  lossTrades: number
  /** 平均盈利 */
  avgProfit: number
  /** 平均亏损 */
  avgLoss: number
  /** 平均持仓时间 */
  avgHoldingTime: string
  /** 最大连续盈利次数 */
  maxConsecutiveWins: number
  /** 最大连续亏损次数 */
  maxConsecutiveLosses: number
  /** 最终资金(权益=现金+未实现盈亏) */
  finalCapital: number
  /** 各交易对开始/结束价格 */
  symbolPrices?: Record<string, SymbolPrices>
  /** 回测结束时未平仓持仓 */
  openPositions?: OpenPositionAtEnd[]
  /** 回测结束时现金余额 */
  balanceAtEnd?: number
  /** 未实现盈亏合计 */
  unrealizedPnlTotal?: number
}

/** 运行中进度快照内的曲线与统计（progress_snapshot.livePreview） */
export interface BacktestLivePreviewPayload {
  equityCurve: TimeSeriesPoint[]
  drawdownCurve: TimeSeriesPoint[]
  benchmarkCurve: TimeSeriesPoint[]
  statistics: Partial<BacktestStatistics>
  /** 最近若干条决策（与完成后 decisionLog 字段一致），全量在结束后可查 */
  decisionLog?: BacktestDecisionRecord[]
  decisionLogTotal?: number
  decisionLogTruncated?: boolean
  /** 已产生的全部成交（运行中实时同步） */
  trades?: BacktestTradeRecord[]
  /** 当前未平持仓 */
  openPositions?: LiveOpenPosition[]
  /** 当前尚未完全成交的委托 */
  activeOrders?: BacktestActiveOrder[]
  /** 各标的最新标记价 */
  markPrices?: Record<string, number>
  /** 现金余额 */
  balance?: number
  /** 账户权益 */
  equity?: number
  /** 最近一次决策/成交摘要 */
  lastAction?: LiveLastAction | null
}

/** 回测结果 */
export interface BacktestResult {
  /** 统计数据 */
  statistics: BacktestStatistics
  /** 权益曲线 */
  equityCurve: TimeSeriesPoint[]
  /** 回撤曲线 */
  drawdownCurve: TimeSeriesPoint[]
  /** 做多持有基准曲线；前端据此生成同资金、1x 的做空持有对照 */
  benchmarkCurve: TimeSeriesPoint[]
  /** 持仓历史 */
  positionHistory: PositionPoint[]
  /** 每次决策记录（含思考过程），不限于成交流水 */
  decisionLog?: BacktestDecisionRecord[]
  /** 交易记录 */
  trades: BacktestTradeRecord[]
}

/** 运行中由后端 progress_snapshot 写入（可含嵌套 livePreview） */
export interface BacktestRunningProgress {
  currentTime?: string
  message?: string
  currentStep?: number
  totalSteps?: number
  intervalSeconds?: number
  livePreview?: BacktestLivePreviewPayload | null
}

/** 回测任务 */
export interface BacktestTask {
  id: string
  name: string
  status: BacktestStatus
  progress: number
  createdAt: string
  startedAt?: string
  completedAt?: string
  config: BacktestConfig
  result?: BacktestResult
  errorMessage?: string
  /** 详情接口在 running/failed 状态下附带；failed 用于恢复中断前的执行快照 */
  runningProgress?: BacktestRunningProgress | null
}

/** 回测列表项 */
export interface BacktestListItem {
  id: string
  name: string
  status: BacktestStatus
  agentId: string
  agentName?: string
  exchange: ExchangeCode
  symbols: string[]
  startTime: string
  endTime: string
  initialCapital: number
  totalReturn?: number
  maxDrawdown?: number
  winRate?: number
  sharpeRatio?: number
  createdAt: string
  completedAt?: string
}

/** 创建回测 DTO */
export interface CreateBacktestDto {
  name: string
  config: BacktestConfig
}

/** 回测进度响应 */
export interface BacktestProgressRes {
  status: BacktestStatus
  progress: number
  currentTime?: string
  message?: string
  currentStep?: number
  totalSteps?: number
  intervalSeconds?: number
  livePreview?: BacktestLivePreviewPayload | null
}

/** 回测 K 线数据点 */
export interface BacktestKlineItem {
  time: string
  open: string
  high: string
  low: string
  close: string
  volume: string
}

/** 回测 K 线响应 */
export interface BacktestKlineRes {
  symbol: string
  interval: KlineInterval
  /** 决策上下文（预热 K 线）的起始时间 */
  startTime: string
  endTime: string
  /** 完整回测截止时间；endTime 在默认模式下可能只是当前模拟时间 */
  backtestEndTime?: string
  /** 正式回测区间起点，用于区分预热数据 */
  backtestStartTime: string
  contextLookbackBars: number
  list: BacktestKlineItem[]
}

export const backtestApi = {
  /** 获取回测列表 */
  getList(params?: {
    status?: BacktestStatus
    page?: number
    pageSize?: number
  }): Promise<{ list: BacktestListItem[]; total: number }> {
    return request.get('/v1/backtest', { params }) as Promise<{ list: BacktestListItem[]; total: number }>
  },

  /** 获取回测详情 */
  getById(id: string): Promise<BacktestTask> {
    return request.get(`/v1/backtest/${id}`) as Promise<BacktestTask>
  },

  /** 创建回测任务 */
  create(dto: CreateBacktestDto): Promise<{ id: string }> {
    return request.post('/v1/backtest', dto) as Promise<{ id: string }>
  },

  /** 获取回测进度 */
  getProgress(id: string): Promise<BacktestProgressRes> {
    return request.get(`/v1/backtest/${id}/progress`) as Promise<BacktestProgressRes>
  },

  /** 停止回测 */
  stop(id: string): Promise<{ success: boolean }> {
    return request.post(`/v1/backtest/${id}/stop`) as Promise<{ success: boolean }>
  },

  /** 删除回测 */
  delete(id: string): Promise<void> {
    return request.delete(`/v1/backtest/${id}`) as Promise<void>
  },

  /** 重新运行回测 */
  rerun(id: string): Promise<{ id: string }> {
    return request.post(`/v1/backtest/${id}/rerun`) as Promise<{ id: string }>
  },

  /** 分页获取成交明细 */
  getTrades(id: string, params?: { skip?: number; limit?: number; order?: 'asc' | 'desc' }): Promise<{ list: BacktestTradeRecord[]; total: number }> {
    return request.get(`/v1/backtest/${id}/trades`, { params }) as Promise<{ list: BacktestTradeRecord[]; total: number }>
  },

  /** 分页获取决策明细 */
  getDecisions(id: string, params?: { skip?: number; limit?: number }): Promise<{ list: BacktestDecisionRecord[]; total: number }> {
    return request.get(`/v1/backtest/${id}/decisions`, { params }) as Promise<{ list: BacktestDecisionRecord[]; total: number }>
  },

  /** 按需获取单条完整决策（含 Prompt 与 LLM 原始响应） */
  getDecision(id: string, decisionId: string): Promise<BacktestDecisionRecord> {
    return request.get(`/v1/backtest/${id}/decisions/${decisionId}`) as Promise<BacktestDecisionRecord>
  },

  /** 按需获取权益、回撤和基准曲线 */
  getEquityCurve(id: string): Promise<{
    equityCurve: TimeSeriesPoint[]
    drawdownCurve: TimeSeriesPoint[]
    benchmarkCurve: TimeSeriesPoint[]
  }> {
    return request.get(`/v1/backtest/${id}/equity-curve`) as Promise<{
      equityCurve: TimeSeriesPoint[]
      drawdownCurve: TimeSeriesPoint[]
      benchmarkCurve: TimeSeriesPoint[]
    }>
  },

  /** 导出回测报告 */
  exportReport(id: string, format: 'csv' | 'pdf' = 'csv'): Promise<Blob> {
    return request.get(`/v1/backtest/${id}/export`, {
      params: { format },
      responseType: 'blob',
      timeout: 120000,
    }) as Promise<Blob>
  },

  /** 获取回测区间 K 线 */
  getKline(id: string, params?: { symbol?: string; includeFuture?: boolean }): Promise<BacktestKlineRes> {
    return request.get(`/v1/backtest/${id}/kline`, { params }) as Promise<BacktestKlineRes>
  },
}
