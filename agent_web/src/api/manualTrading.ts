import { request } from './request'

export type InstrumentType = 'SPOT' | 'SWAP'
export type OrderType = 'market' | 'limit'
export type TradeMode = 'cash' | 'cross' | 'isolated'
export type TradeAction = 'buy' | 'sell' | 'open_long' | 'open_short' | 'close_long' | 'close_short'

export interface TradingInstrumentItem {
  instId: string
  instType: InstrumentType
  baseCcy?: string
  quoteCcy?: string
  settleCcy?: string
  tickSz?: string
  lotSz?: string
  minSz?: string
  state?: string
}

export interface TradingTicker {
  instId: string
  last: string
  askPx: string
  bidPx: string
  high24h: string
  low24h: string
  change24h: string
  vol24h?: string
  ts?: string
}

export interface OrderBookLevel {
  price: string
  size: string
}

export interface TradingSnapshot {
  ticker: TradingTicker
  bids: OrderBookLevel[]
  asks: OrderBookLevel[]
}

export interface TradingBalanceItem {
  ccy: string
  availBal: string
  frozenBal: string
  eq: string
  eqUsd: string
}

export interface TradingPositionItem {
  instId: string
  instType?: string
  posSide: string
  pos: string
  availPos?: string
  avgPx?: string
  markPx?: string
  upl?: string
  lever?: string
  mgnMode?: string
}

export interface TradingAccountOverview {
  balances: TradingBalanceItem[]
  positions: TradingPositionItem[]
}

export interface PendingOrderItem {
  ordId: string
  instId: string
  side: string
  ordType: string
  px?: string
  sz: string
  accFillSz: string
  state: string
  posSide?: string
  cTime?: string
}

export interface PlaceManualOrderDto {
  accountId: string
  instId: string
  instType: InstrumentType
  tradeAction: TradeAction
  ordType: OrderType
  sz: string
  px?: string
  tdMode?: TradeMode
  leverage?: string
  tgtCcy?: 'base_ccy' | 'quote_ccy'
}

export interface PlaceManualOrderResult {
  ordId?: string
  clOrdId?: string
  sCode?: string
  sMsg?: string
}

export const manualTradingApi = {
  searchInstruments(params: { accountId: string; instType: InstrumentType; keyword?: string }) {
    return request.get<{ list: TradingInstrumentItem[] }>('/v1/manual-trading/instruments', { params })
  },

  getSnapshot(params: { accountId: string; instId: string }) {
    return request.get<TradingSnapshot>('/v1/manual-trading/snapshot', { params })
  },

  getOverview(params: { accountId: string; instType?: InstrumentType; instId?: string }) {
    return request.get<TradingAccountOverview>('/v1/manual-trading/overview', { params })
  },

  getPendingOrders(params: { accountId: string; instType?: InstrumentType; instId?: string; limit?: number }) {
    return request.get<{ list: PendingOrderItem[] }>('/v1/manual-trading/pending-orders', { params })
  },

  placeOrder(data: PlaceManualOrderDto) {
    return request.post<PlaceManualOrderResult>('/v1/manual-trading/orders', data)
  },

  cancelOrder(data: { accountId: string; instId: string; ordId: string }) {
    return request.post<PlaceManualOrderResult>('/v1/manual-trading/orders/cancel', data)
  },
}
