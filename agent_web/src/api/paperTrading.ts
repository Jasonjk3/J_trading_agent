import { request } from './request'

export type PaperAccountStatus = 'running' | 'paused'
export type PaperAccountKind = 'human' | 'agent'
export type PaperTradeSide = 'buy' | 'sell'

export interface PaperTradingSummary {
  totalEquity: number
  totalReturnRate: number
  totalPnl: number
  todayPnl: number
  maxDrawdown: number
  runningAccounts: number
  totalAccounts: number
  winRate: number | null
}

export interface PaperTradingAccount {
  id: string
  sourceAgentId?: string | null
  name: string
  kind: PaperAccountKind
  status: PaperAccountStatus
  strategy: string
  currency: string
  initialCapital: number
  cashBalance: number
  equity: number
  returnRate: number
  positionCount: number
  winRate: number | null
}

export interface PaperCurvePoint { time: string; value: number }
export interface PaperAccountCurve { accountId: string; name: string; points: PaperCurvePoint[] }
export interface PaperActivity {
  id: string
  type: 'trade' | 'decision'
  accountId: string
  accountName: string
  title: string
  detail: string
  occurredAt: string
}

export interface PaperDashboard {
  summary: PaperTradingSummary
  accounts: PaperTradingAccount[]
  curves: PaperAccountCurve[]
  activities: PaperActivity[]
}

export interface PaperPosition {
  id: string
  symbol: string
  quantity: number
  averagePrice: number
  lastPrice: number
  unrealizedPnl: number
  realizedPnl: number
}

export interface PaperTrade {
  id: string
  symbol: string
  side: PaperTradeSide
  price: number
  quantity: number
  amount: number
  realizedPnl: number
  executedAt: string
}

export interface PaperDecision {
  id: string
  symbol: string
  action: string
  title?: string | null
  summary?: string | null
  reasoning?: string | null
  referencePrice?: number | null
  confidence?: number | null
  result?: string | null
  createdAt: string
}

export const paperTradingApi = {
  initializeHumanAccount() {
    return request.post('/v1/paper-trading/accounts/human') as Promise<{ id: string }>
  },
  getDashboard(range = '30D') {
    return request.get('/v1/paper-trading/dashboard', { params: { range } }) as Promise<PaperDashboard>
  },
  createAccount(agentId: string, initialCapital: number) {
    return request.post('/v1/paper-trading/accounts', { agentId, initialCapital }) as Promise<{ id: string }>
  },
  pauseAccount(accountId: string) {
    return request.post(`/v1/paper-trading/accounts/${accountId}/pause`) as Promise<{ success: boolean }>
  },
  resumeAccount(accountId: string) {
    return request.post(`/v1/paper-trading/accounts/${accountId}/resume`) as Promise<{ success: boolean }>
  },
  deleteAccount(accountId: string) {
    return request.delete(`/v1/paper-trading/accounts/${accountId}`) as Promise<void>
  },
  getPositions(accountId: string) {
    return request.get(`/v1/paper-trading/accounts/${accountId}/positions`) as Promise<{ list: PaperPosition[]; total: number }>
  },
  getTrades(accountId: string) {
    return request.get(`/v1/paper-trading/accounts/${accountId}/trades`) as Promise<{ list: PaperTrade[]; total: number }>
  },
  createTrade(accountId: string, payload: { symbol: string; side: PaperTradeSide; amount: number; price: number }) {
    return request.post(`/v1/paper-trading/accounts/${accountId}/trades`, payload) as Promise<PaperTrade>
  },
  getDecisions(accountId: string) {
    return request.get(`/v1/paper-trading/accounts/${accountId}/decisions`) as Promise<{ list: PaperDecision[]; total: number }>
  },
}
