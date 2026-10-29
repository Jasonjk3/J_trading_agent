import { request } from './request'

/** 交易所代码 */
export type ExchangeCode = 'binance' | 'okx' | 'bybit'

/** 订单方向 */
export type OrderSide = 'buy' | 'sell'

/** 订单类型 */
export type OrderType = 'market' | 'limit'

/** 订单状态 */
export type OrderStatus = 'pending' | 'filled' | 'partial' | 'cancelled' | 'failed'

/** 订单列表项（与后端对齐） */
export interface OrderListItem {
  id: string
  exchange: ExchangeCode
  symbol: string
  side: OrderSide
  type: OrderType
  quantity: string
  price?: string
  filledQuantity?: string
  amount?: string
  fee?: string
  status: OrderStatus
  createdAt: string
  updatedAt?: string
}

/** 成交明细项（可单独接口或合并在订单详情） */
export interface TradeListItem {
  id: string
  orderId: string
  exchange: ExchangeCode
  symbol: string
  side: OrderSide
  quantity: string
  price: string
  amount: string
  fee: string
  createdAt: string
}

/** 订单列表查询参数 */
export interface OrderListParams {
  startTime?: string
  endTime?: string
  exchange?: ExchangeCode
  symbol?: string
  side?: OrderSide
  status?: OrderStatus
  page?: number
  pageSize?: number
}

/** 订单列表响应 */
export interface OrderListRes {
  list: OrderListItem[]
  total: number
}

/** 成交列表查询参数 */
export interface TradeListParams {
  startTime?: string
  endTime?: string
  exchange?: ExchangeCode
  symbol?: string
  side?: OrderSide
  page?: number
  pageSize?: number
}

/** 成交列表响应 */
export interface TradeListRes {
  list: TradeListItem[]
  total: number
}

export const ordersApi = {
  getList(params?: OrderListParams): Promise<OrderListRes> {
    return request.get('/v1/orders', { params }) as Promise<OrderListRes>
  },

  /** 成交明细列表（静态阶段可用 Mock） */
  getTrades(params?: TradeListParams): Promise<TradeListRes> {
    return request.get('/v1/trades', { params }) as Promise<TradeListRes>
  },
}
