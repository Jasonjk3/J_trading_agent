import { request } from './request'

/** 持仓方向 */
export type PositionSide = 'long' | 'short'

/** 交易所代码（与 exchangeAccounts 一致） */
export type ExchangeCode = 'binance' | 'okx' | 'bybit'

/** 平仓类型 */
export type CloseType = 'liquidation' | 'partial_liquidation' | 'adl' | 'delivery' | 'manual'

/** 持仓列表项 */
export interface PositionListItem {
  id: string
  exchange: ExchangeCode
  symbol: string
  side: PositionSide
  quantity: string
  costPrice: string
  markPrice: string
  notional: string
  unrealizedPnl: string
  unrealizedPnlRate: string
  updatedAt?: string
}

/** 历史持仓列表项 */
export interface PositionHistoryItem {
  id: string
  exchange: ExchangeCode
  symbol: string
  side: PositionSide
  quantity: string
  openAvgPrice: string
  closeAvgPrice: string
  pnl: string
  pnlRate: string
  lever: string
  closeType?: CloseType
  openTime?: string
  closeTime?: string
}

/** 持仓列表查询参数 */
export interface PositionListParams {
  exchange?: ExchangeCode
  symbol?: string
  side?: PositionSide
  page?: number
  pageSize?: number
}

/** 历史持仓查询参数 */
export interface PositionHistoryParams {
  exchange?: ExchangeCode
  symbol?: string
  side?: PositionSide
  page?: number
  pageSize?: number
}

/** 持仓列表响应（可选返回汇总，便于前端展示） */
export interface PositionListRes {
  list: PositionListItem[]
  total: number
  summary?: {
    complete?: boolean
    warnings?: string[]
    totalNotional: string
    totalUnrealizedPnl: string
  }
}

/** 历史持仓列表响应 */
export interface PositionHistoryRes {
  list: PositionHistoryItem[]
  total: number
  summary?: {
    complete?: boolean
    warnings?: string[]
    totalPnl: string
  }
}

export const positionsApi = {
  getList(params?: PositionListParams): Promise<PositionListRes> {
    return request.get('/v1/positions', { params }) as Promise<PositionListRes>
  },

  getHistory(params?: PositionHistoryParams): Promise<PositionHistoryRes> {
    return request.get('/v1/positions/history', { params }) as Promise<PositionHistoryRes>
  },
}
