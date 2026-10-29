import { request } from './request'

export type MarketInterval = '15m' | '1h' | '4h' | '1d'

export interface MarketSymbolItem {
  symbol: string
  baseAsset: string
  quoteAsset: string
}

export interface KlineItem {
  time: string
  open: string
  high: string
  low: string
  close: string
  volume: string
}

export interface MarketIndicators {
  symbol: string
  interval: MarketInterval
  latestPrice: string
  change24h: string
  high24h: string
  low24h: string
  volume24h: string
  ma5: string
  ma10: string
  ma20: string
  rsi14: string
  macd: string
  signal: string
  histogram: string
  volatility: string
  recommendation: 'bullish' | 'bearish' | 'neutral'
}

export interface FavoriteSymbolItem {
  id: number
  symbol: string
  name: string
  sortOrder: number
  createdAt?: string
  price?: string
  change?: string
}

const marketApi = {
  searchSymbols(keyword?: string) {
    return request.get<{ list: MarketSymbolItem[] }>('/v1/market/symbols', {
      params: { keyword },
    })
  },

  getKline(params: { symbol: string; interval: MarketInterval; limit?: number }) {
    return request.get<{ list: KlineItem[] }>('/v1/market/kline', { params })
  },

  getIndicators(params: { symbol: string; interval: MarketInterval }) {
    return request.get<MarketIndicators>('/v1/market/indicators', { params })
  },

  // 自选交易对相关
  getFavorites() {
    return request.get<{ list: FavoriteSymbolItem[] }>('/v1/market/favorites')
  },

  addFavorite(data: { symbol: string; name?: string }) {
    return request.post<FavoriteSymbolItem>('/v1/market/favorites', data)
  },

  removeFavorite(symbol: string) {
    return request.delete('/v1/market/favorites', { params: { symbol } })
  },

  checkFavorite(symbol: string) {
    return request.get<{ isFavorite: boolean }>('/v1/market/favorites/check', {
      params: { symbol },
    })
  },

  updateFavoriteSort(items: Array<{ symbol: string; sortOrder: number }>) {
    return request.put('/v1/market/favorites/sort', { items })
  },
}

export { marketApi }
