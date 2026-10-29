import { request } from './request'

/** 交易所代码（与 orders 等一致） */
export type ExchangeCode = 'binance' | 'okx' | 'bybit'

/** 收益汇总 */
export interface ProfitSummary {
  totalProfit: string | null
  totalFee: string | null
  netProfit: string | null
  returnRate: string | null
  returnRateReason?: string
  complete?: boolean
  warnings?: string[]
  currency?: string | null
  from?: string
  to?: string
  exchange?: ExchangeCode
}

/** 收益趋势点（按日/周） */
export interface ProfitTrendPoint {
  date: string
  profit: string | null
  cumulative?: string | null
}

/** 收益趋势查询参数 */
export interface ProfitTrendParams {
  from?: string
  to?: string
  period?: 'day' | 'week'
  exchange?: ExchangeCode
  symbol?: string
  agentId?: string
}

/** 按交易所收益项 */
export interface ProfitByExchangeItem {
  exchange: ExchangeCode
  totalProfit: string | null
  totalFee: string | null
  netProfit: string | null
  tradeCount: number
}

/** 按币种收益项 */
export interface ProfitBySymbolItem {
  symbol: string
  totalProfit: string | null
  totalFee: string | null
  netProfit: string | null
  tradeCount: number
}

/** 收益汇总查询参数 */
export interface ProfitSummaryParams {
  from?: string
  to?: string
  exchange?: ExchangeCode
  symbol?: string
  agentId?: string
}

/** 钱包余额项 */
export interface WalletBalanceItem {
  currency: string
  available: string
  frozen: string
  total: string
  eqUsd: string
}

/** 钱包余额响应 */
export interface WalletBalance {
  totalEqUsd: string
  balances: WalletBalanceItem[]
  exchange: string
  updatedAt?: string
}

const analyticsApi = {
  /** 收益概览 */
  getProfitSummary(params?: ProfitSummaryParams) {
    return request.get<ProfitSummary>('/v1/analytics/profit-summary', { params })
  },

  /** 收益趋势（按日/周） */
  getProfitTrend(params?: ProfitTrendParams) {
    return request.get<{ points: ProfitTrendPoint[]; period?: string }>('/v1/analytics/profit-trend', { params })
  },

  /** 按交易所维度 */
  getProfitByExchange(params?: ProfitSummaryParams) {
    return request.get<{ list: ProfitByExchangeItem[] }>('/v1/analytics/profit-by-exchange', { params })
  },

  /** 按币种维度 */
  getProfitBySymbol(params?: ProfitSummaryParams) {
    return request.get<{ list: ProfitBySymbolItem[] }>('/v1/analytics/profit-by-symbol', { params })
  },

  /** 钱包余额 */
  getWalletBalance(params?: { exchange?: string }) {
    return request.get<{ list: WalletBalance[] }>('/v1/analytics/wallet-balance', { params })
  },
}

export { analyticsApi }
