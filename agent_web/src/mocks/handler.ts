/**
 * Mock 处理器：在开发阶段拦截 /v1 请求并返回本地数据（与后端 API 前缀一致）
 */
import type { LoginRes } from '@/api/auth'
import type { BackendUser, UserRole } from '@/api/users'
import type {
  ExchangeAccountListItem,
  CreateExchangeAccountDto,
  UpdateExchangeAccountDto,
  ExchangeCode,
  BindStatus,
} from '@/api/exchangeAccounts'
import type { PositionListItem, PositionSide } from '@/api/positions'
import type { OrderListItem, TradeListItem, OrderSide, OrderStatus } from '@/api/orders'
import type { AgentListItem, AgentStatus, CreateAgentDto, UpdateAgentDto, AgentOperationItem, ProfitCurvePoint, StrategyConfig } from '@/api/agents'
import type { BacktestListItem, BacktestTask, BacktestStatus, CreateBacktestDto, BacktestConfig, BacktestResult, BacktestStatistics, TimeSeriesPoint, BacktestTradeRecord } from '@/api/backtest'

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** 脱敏：仅显示后 4 位 */
function maskSecret(secret: string): string {
  if (!secret || secret.length <= 4) return '****'
  return '****' + secret.slice(-4)
}

// ---------- Auth ----------
const mockLogin = async (username: string): Promise<LoginRes> => {
  await delay(400)
  const now = new Date().toISOString()
  return {
    access_token: 'mock-jwt-token-' + Date.now(),
    token_type: 'bearer',
    user: {
      id: '1',
      username: username || 'admin',
      role: 'admin',
      is_active: true,
      feature_permissions: [],
      created_at: now,
      updated_at: now,
    },
  }
}

// ---------- Users 内存数据 ----------
type MockCreateUserPayload = {
  username: string
  password: string
  email?: string
  role: UserRole
  is_active: boolean
}

type MockUpdateUserPayload = Partial<Omit<MockCreateUserPayload, 'username'>>

let mockUserSeq = 10
const mockUsers: BackendUser[] = [
  { id: '1', username: 'admin', email: 'admin@example.com', role: 'admin', is_active: true, feature_permissions: [], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
  { id: '2', username: 'trader1', email: 'trader1@example.com', role: 'user', is_active: true, feature_permissions: [], created_at: '2024-02-01T00:00:00Z', updated_at: '2024-02-01T00:00:00Z' },
  { id: '3', username: 'viewer1', email: 'viewer1@example.com', role: 'user', is_active: true, feature_permissions: [], created_at: '2024-03-01T00:00:00Z', updated_at: '2024-03-01T00:00:00Z' },
  { id: '4', username: 'trader2', email: 'trader2@example.com', role: 'user', is_active: false, feature_permissions: [], created_at: '2024-04-01T00:00:00Z', updated_at: '2024-05-01T00:00:00Z' },
]

function getUsers(params?: { username?: string; role?: UserRole; is_active?: boolean; skip?: number; limit?: number }) {
  let list = [...mockUsers]
  if (params?.username) {
    const q = params.username.trim().toLowerCase()
    list = list.filter((u) => u.username.toLowerCase().includes(q))
  }
  if (params?.role) list = list.filter((u) => u.role === params.role)
  if (params?.is_active !== undefined) list = list.filter((u) => u.is_active === params.is_active)
  const total = list.length
  const start = params?.skip ?? 0
  const limit = params?.limit ?? 10
  list = list.slice(start, start + limit)
  return { users: list, total }
}

function createUser(dto: MockCreateUserPayload): BackendUser {
  const id = String(++mockUserSeq)
  const now = new Date().toISOString()
  const user: BackendUser = {
    id,
    username: dto.username,
    email: dto.email,
    role: dto.role,
    is_active: dto.is_active,
    feature_permissions: [],
    created_at: now,
    updated_at: now,
  }
  mockUsers.push(user)
  return user
}

function updateUser(id: string, dto: MockUpdateUserPayload): BackendUser {
  const idx = mockUsers.findIndex((u) => u.id === id)
  if (idx === -1) throw new Error('用户不存在')
  const now = new Date().toISOString()
  mockUsers[idx] = {
    ...mockUsers[idx],
    ...(dto.email !== undefined && { email: dto.email }),
    ...(dto.role !== undefined && { role: dto.role }),
    ...(dto.is_active !== undefined && { is_active: dto.is_active }),
    updated_at: now,
  }
  return mockUsers[idx]
}

function deleteUser(id: string): void {
  const idx = mockUsers.findIndex((u) => u.id === id)
  if (idx === -1) throw new Error('用户不存在')
  mockUsers.splice(idx, 1)
}

// ---------- 交易所配置 内存数据 ----------
const EXCHANGE_NEEDS_PASSPHRASE: ExchangeCode[] = ['okx']
let mockExchangeSeq = 10
const mockExchangeAccounts: (ExchangeAccountListItem & { _apiSecret?: string })[] = [
  {
    id: '1',
    exchange: 'okx',
    remark: 'OKX 主账户',
    bindStatus: 'success',
    lastVerifiedAt: '2024-02-10T08:00:00Z',
    enabled: true,
    readOnly: false,
    apiKeyMasked: '****a1b2',
    hasPassphrase: true,
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-02-10T08:00:00Z',
  },
  {
    id: '2',
    exchange: 'okx',
    remark: 'OKX 子账户',
    bindStatus: 'success',
    lastVerifiedAt: '2024-02-12T10:00:00Z',
    enabled: true,
    readOnly: true,
    apiKeyMasked: '****c3d4',
    hasPassphrase: true,
    createdAt: '2024-02-01T00:00:00Z',
    updatedAt: '2024-02-12T10:00:00Z',
  },
  {
    id: '3',
    exchange: 'okx',
    remark: 'OKX 测试账户',
    bindStatus: 'failed',
    lastVerifiedAt: '2024-02-08T12:00:00Z',
    enabled: false,
    readOnly: false,
    apiKeyMasked: '****e5f6',
    hasPassphrase: true,
    createdAt: '2024-02-05T00:00:00Z',
    updatedAt: '2024-02-08T12:00:00Z',
  },
]

function getExchangeAccounts(params?: {
  exchange?: ExchangeCode
  enabled?: boolean
  bindStatus?: BindStatus
}): { list: ExchangeAccountListItem[]; total: number } {
  let list = mockExchangeAccounts.map(({ _apiSecret, ...rest }) => rest)
  if (params?.exchange) list = list.filter((a) => a.exchange === params.exchange)
  if (params?.enabled !== undefined) list = list.filter((a) => a.enabled === params.enabled)
  if (params?.bindStatus) list = list.filter((a) => a.bindStatus === params.bindStatus)
  return { list, total: list.length }
}

function createExchangeAccount(dto: CreateExchangeAccountDto): ExchangeAccountListItem {
  const id = String(++mockExchangeSeq)
  const now = new Date().toISOString()
  const hasPassphrase = EXCHANGE_NEEDS_PASSPHRASE.includes(dto.exchange)
  const item: ExchangeAccountListItem & { _apiSecret?: string } = {
    id,
    exchange: dto.exchange,
    remark: dto.remark,
    bindStatus: 'never',
    enabled: dto.enabled ?? true,
    readOnly: dto.readOnly ?? false,
    apiKeyMasked: maskSecret(dto.apiKey),
    hasPassphrase,
    createdAt: now,
    updatedAt: now,
  }
  mockExchangeAccounts.push(item)
  return item
}

function updateExchangeAccount(id: string, dto: UpdateExchangeAccountDto): ExchangeAccountListItem {
  const idx = mockExchangeAccounts.findIndex((a) => a.id === id)
  if (idx === -1) throw new Error('配置不存在')
  const now = new Date().toISOString()
  const cur = mockExchangeAccounts[idx]
  if (dto.apiKey !== undefined) (cur as any).apiKeyMasked = maskSecret(dto.apiKey)
  if (dto.remark !== undefined) cur.remark = dto.remark
  if (dto.readOnly !== undefined) cur.readOnly = dto.readOnly
  if (dto.enabled !== undefined) cur.enabled = dto.enabled
  cur.updatedAt = now
  return cur
}

function deleteExchangeAccount(id: string): void {
  const idx = mockExchangeAccounts.findIndex((a) => a.id === id)
  if (idx === -1) throw new Error('配置不存在')
  mockExchangeAccounts.splice(idx, 1)
}

/** Mock 校验连接：随机成功/失败，便于测试 */
async function verifyExchangeAccount(id: string): Promise<{ success: boolean; message?: string }> {
  await delay(800)
  const item = mockExchangeAccounts.find((a) => a.id === id)
  if (!item) throw new Error('配置不存在')
  const roll = Math.random()
  if (roll > 0.2) {
    item.bindStatus = 'success'
    item.lastVerifiedAt = new Date().toISOString()
    return { success: true, message: '连接成功' }
  }
  item.bindStatus = 'failed'
  item.lastVerifiedAt = new Date().toISOString()
  return { success: false, message: 'API 密钥无效或网络异常' }
}

// ---------- 持仓 Mock 数据 ----------
const mockPositions: PositionListItem[] = [
  { id: 'p1', exchange: 'binance', symbol: 'BTCUSDT', side: 'long', quantity: '0.15', costPrice: '43200.00', markPrice: '44500.00', notional: '6675.00', unrealizedPnl: '195.00', unrealizedPnlRate: '3.01', updatedAt: '2024-02-14T10:00:00Z' },
  { id: 'p2', exchange: 'binance', symbol: 'ETHUSDT', side: 'long', quantity: '2.5', costPrice: '2280.00', markPrice: '2350.00', notional: '5875.00', unrealizedPnl: '175.00', unrealizedPnlRate: '3.07', updatedAt: '2024-02-14T10:00:00Z' },
  { id: 'p3', exchange: 'binance', symbol: 'SOLUSDT', side: 'short', quantity: '50', costPrice: '98.00', markPrice: '96.20', notional: '4810.00', unrealizedPnl: '90.00', unrealizedPnlRate: '1.84', updatedAt: '2024-02-14T09:30:00Z' },
  { id: 'p4', exchange: 'okx', symbol: 'BTC-USDT', side: 'long', quantity: '0.08', costPrice: '43100.00', markPrice: '44500.00', notional: '3560.00', unrealizedPnl: '112.00', unrealizedPnlRate: '2.60', updatedAt: '2024-02-14T09:00:00Z' },
  { id: 'p5', exchange: 'okx', symbol: 'ETH-USDT', side: 'long', quantity: '1.2', costPrice: '2300.00', markPrice: '2350.00', notional: '2820.00', unrealizedPnl: '60.00', unrealizedPnlRate: '2.17', updatedAt: '2024-02-14T09:00:00Z' },
  { id: 'p6', exchange: 'bybit', symbol: 'BTCUSDT', side: 'long', quantity: '0.05', costPrice: '43000.00', markPrice: '44500.00', notional: '2225.00', unrealizedPnl: '75.00', unrealizedPnlRate: '1.74', updatedAt: '2024-02-14T08:00:00Z' },
]

function getPositions(params?: { exchange?: string; symbol?: string; side?: PositionSide; page?: number; pageSize?: number }) {
  let list = [...mockPositions]
  if (params?.exchange) list = list.filter((p) => p.exchange === params.exchange)
  if (params?.symbol) {
    const q = params.symbol.trim().toUpperCase()
    list = list.filter((p) => p.symbol.toUpperCase().includes(q))
  }
  if (params?.side) list = list.filter((p) => p.side === params.side)
  const total = list.length
  const page = params?.page ?? 1
  const pageSize = params?.pageSize ?? 10
  const start = (page - 1) * pageSize
  const paged = list.slice(start, start + pageSize)
  let totalNotional = '0'
  let totalUnrealizedPnl = '0'
  list.forEach((p) => {
    totalNotional = (parseFloat(totalNotional) + parseFloat(p.notional)).toFixed(2)
    totalUnrealizedPnl = (parseFloat(totalUnrealizedPnl) + parseFloat(p.unrealizedPnl)).toFixed(2)
  })
  return {
    list: paged,
    total,
    summary: { totalNotional, totalUnrealizedPnl },
  }
}

// ---------- 订单 / 成交 Mock 数据 ----------
const mockOrders: OrderListItem[] = [
  { id: 'o1', exchange: 'binance', symbol: 'BTCUSDT', side: 'buy', type: 'market', quantity: '0.1', filledQuantity: '0.1', amount: '4450.00', fee: '2.23', status: 'filled', createdAt: '2024-02-14T10:30:00Z' },
  { id: 'o2', exchange: 'binance', symbol: 'ETHUSDT', side: 'sell', type: 'limit', quantity: '1.0', price: '2360.00', filledQuantity: '1.0', amount: '2360.00', fee: '1.18', status: 'filled', createdAt: '2024-02-14T09:15:00Z' },
  { id: 'o3', exchange: 'okx', symbol: 'BTC-USDT', side: 'buy', type: 'market', quantity: '0.05', filledQuantity: '0.05', amount: '2225.00', fee: '1.11', status: 'filled', createdAt: '2024-02-14T08:00:00Z' },
  { id: 'o4', exchange: 'binance', symbol: 'SOLUSDT', side: 'sell', type: 'limit', quantity: '30', price: '97.50', filledQuantity: '0', amount: '0', fee: '0', status: 'pending', createdAt: '2024-02-14T11:00:00Z' },
  { id: 'o5', exchange: 'bybit', symbol: 'ETHUSDT', side: 'buy', type: 'market', quantity: '0.5', filledQuantity: '0.3', amount: '705.00', fee: '0.35', status: 'partial', createdAt: '2024-02-14T07:45:00Z' },
  { id: 'o6', exchange: 'binance', symbol: 'BTCUSDT', side: 'sell', type: 'limit', quantity: '0.02', price: '45000.00', filledQuantity: '0', amount: '0', fee: '0', status: 'cancelled', createdAt: '2024-02-13T16:00:00Z' },
]

const mockTrades: TradeListItem[] = [
  { id: 't1', orderId: 'o1', exchange: 'binance', symbol: 'BTCUSDT', side: 'buy', quantity: '0.1', price: '44500.00', amount: '4450.00', fee: '2.23', createdAt: '2024-02-14T10:30:01Z' },
  { id: 't2', orderId: 'o2', exchange: 'binance', symbol: 'ETHUSDT', side: 'sell', quantity: '1.0', price: '2360.00', amount: '2360.00', fee: '1.18', createdAt: '2024-02-14T09:15:02Z' },
  { id: 't3', orderId: 'o3', exchange: 'okx', symbol: 'BTC-USDT', side: 'buy', quantity: '0.05', price: '44500.00', amount: '2225.00', fee: '1.11', createdAt: '2024-02-14T08:00:01Z' },
  { id: 't4', orderId: 'o5', exchange: 'bybit', symbol: 'ETHUSDT', side: 'buy', quantity: '0.3', price: '2350.00', amount: '705.00', fee: '0.35', createdAt: '2024-02-14T07:45:02Z' },
]

function getOrders(params?: { startTime?: string; endTime?: string; exchange?: string; symbol?: string; side?: OrderSide; status?: OrderStatus; page?: number; pageSize?: number }) {
  let list = [...mockOrders]
  if (params?.exchange) list = list.filter((o) => o.exchange === params.exchange)
  if (params?.symbol) {
    const q = params.symbol.trim().toUpperCase()
    list = list.filter((o) => o.symbol.toUpperCase().replace('-', '').includes(q.replace('-', '')))
  }
  if (params?.side) list = list.filter((o) => o.side === params.side)
  if (params?.status) list = list.filter((o) => o.status === params.status)
  if (params?.startTime) {
    const t = new Date(params.startTime).getTime()
    list = list.filter((o) => new Date(o.createdAt).getTime() >= t)
  }
  if (params?.endTime) {
    const t = new Date(params.endTime).getTime()
    list = list.filter((o) => new Date(o.createdAt).getTime() <= t)
  }
  const total = list.length
  const page = params?.page ?? 1
  const pageSize = params?.pageSize ?? 10
  const start = (page - 1) * pageSize
  list = list.slice(start, start + pageSize)
  return { list, total }
}

function getTrades(params?: { startTime?: string; endTime?: string; exchange?: string; symbol?: string; side?: OrderSide; page?: number; pageSize?: number }) {
  let list = [...mockTrades]
  if (params?.exchange) list = list.filter((tr) => tr.exchange === params.exchange)
  if (params?.symbol) {
    const q = params.symbol.trim().toUpperCase()
    list = list.filter((tr) => tr.symbol.toUpperCase().replace('-', '').includes(q.replace('-', '')))
  }
  if (params?.side) list = list.filter((tr) => tr.side === params.side)
  if (params?.startTime) {
    const ts = new Date(params.startTime).getTime()
    list = list.filter((tr) => new Date(tr.createdAt).getTime() >= ts)
  }
  if (params?.endTime) {
    const te = new Date(params.endTime).getTime()
    list = list.filter((tr) => new Date(tr.createdAt).getTime() <= te)
  }
  const total = list.length
  const page = params?.page ?? 1
  const pageSize = params?.pageSize ?? 10
  const start = (page - 1) * pageSize
  list = list.slice(start, start + pageSize)
  return { list, total }
}

// ---------- Agent Mock 数据 ----------
let mockAgentSeq = 10

const mockAgentStrategyConfigs: Record<string, StrategyConfig> = {
  '1': {
    tradingStyle: 'balanced',
    symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
    initialCapital: 10000,
    targetProfit: { type: 'percentage', value: 8 },
    tradingCycle: 'short_term',
    minOrderAmount: 50,
    maxOrderAmount: 5000,
    maxLeverage: 5,
    positionDirection: 'both',
    marketMode: 'auto',
    rangeRsiLongThreshold: 35,
    rangeRsiShortThreshold: 65,
    rangeEntryBandTolerance: 0.005,
    rangeTakeProfitMode: 'mid_band',
    remark: 'BTC 主力短线策略，注重日内机会',
    decisionMode: 'trader',
  },
  '2': {
    tradingStyle: 'conservative',
    symbols: ['ETHUSDT'],
    initialCapital: 5000,
    targetProfit: { type: 'percentage', value: 5 },
    tradingCycle: 'short_term',
    minOrderAmount: 20,
    maxOrderAmount: 500,
    maxLeverage: 1,
    positionDirection: 'long_only',
    marketMode: 'range_only',
    rangeRsiLongThreshold: 32,
    rangeRsiShortThreshold: 68,
    rangeEntryBandTolerance: 0.003,
    rangeTakeProfitMode: 'opposite_band',
    remark: undefined,
    decisionMode: 'rule',
    ruleConfig: {
      preset: 'range_scalper',
      enabledRules: ['regime_detector', 'bollinger_range', 'rsi_threshold', 'fixed_pct_stop'],
      composition: 'priority_stack',
    },
  },
}

const mockAgents: AgentListItem[] = [
  {
    id: '1',
    name: 'BTC 趋势 Agent',
    exchangeId: '1',
    exchange: 'binance',
    llmModelId: 1,
    llmModelName: 'GPT-4o',
    remark: '主账户趋势跟踪',
    status: 'running',
    lastRunAt: '2024-02-14T10:30:00Z',
    createdAt: '2024-01-15T00:00:00Z',
    updatedAt: '2024-02-14T10:30:00Z',
    strategyConfig: mockAgentStrategyConfigs['1'],
  },
  {
    id: '2',
    name: 'ETH 网格 Agent',
    exchangeId: '1',
    exchange: 'binance',
    llmModelId: 2,
    llmModelName: 'Claude 3.5 Sonnet',
    remark: '',
    status: 'stopped',
    lastRunAt: '2024-02-13T18:00:00Z',
    createdAt: '2024-02-01T00:00:00Z',
    updatedAt: '2024-02-13T18:00:00Z',
    strategyConfig: mockAgentStrategyConfigs['2'],
  },
  {
    id: '3',
    name: 'OKX 套利 Agent',
    exchangeId: '2',
    exchange: 'okx',
    remark: '子账户',
    status: 'stopped',
    lastRunAt: undefined,
    createdAt: '2024-02-10T00:00:00Z',
    updatedAt: '2024-02-10T00:00:00Z',
  },
]

function getAgentList(): { list: AgentListItem[]; total: number } {
  return { list: [...mockAgents], total: mockAgents.length }
}

function getAgentById(id: string): AgentListItem | undefined {
  return mockAgents.find((a) => a.id === id)
}

function createAgent(dto: CreateAgentDto): AgentListItem {
  const id = String(++mockAgentSeq)
  const now = new Date().toISOString()
  const acc = mockExchangeAccounts.find((a) => a.id === dto.exchangeId)
  const item: AgentListItem = {
    id,
    name: dto.name,
    exchangeId: dto.exchangeId,
    exchange: acc?.exchange,
    llmModelId: dto.llmModelId,
    llmModelName: dto.llmModelId ? `Model-${dto.llmModelId}` : undefined,
    remark: dto.remark,
    status: 'stopped',
    createdAt: now,
    updatedAt: now,
  }
  mockAgents.push(item)
  return item
}

function updateAgent(id: string, dto: UpdateAgentDto): AgentListItem {
  const idx = mockAgents.findIndex((a) => a.id === id)
  if (idx === -1) throw new Error('Agent 不存在')
  const now = new Date().toISOString()
  const updates: Partial<AgentListItem> = { ...dto, updatedAt: now }
  if (dto.exchangeId) {
    const acc = mockExchangeAccounts.find((a) => a.id === dto.exchangeId)
    updates.exchange = acc?.exchange
  }
  if (dto.llmModelId !== undefined) {
    updates.llmModelName = dto.llmModelId ? `Model-${dto.llmModelId}` : undefined
  }
  mockAgents[idx] = { ...mockAgents[idx], ...updates }
  return mockAgents[idx]
}

function deleteAgent(id: string): void {
  const idx = mockAgents.findIndex((a) => a.id === id)
  if (idx === -1) throw new Error('Agent 不存在')
  mockAgents.splice(idx, 1)
}

function setAgentStatus(id: string, status: AgentStatus): void {
  const a = mockAgents.find((x) => x.id === id)
  if (a) {
    a.status = status
    a.lastRunAt = new Date().toISOString()
    a.updatedAt = a.lastRunAt
  }
}

function getAgentProfitCurve(_agentId: string, period?: string): { points: ProfitCurvePoint[]; period?: string } {
  const days = period === '30d' ? 30 : period === '1d' ? 1 : 7
  const points: ProfitCurvePoint[] = []
  for (let i = days; i >= 0; i--) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    const pnl = (Math.random() - 0.45) * 300
    const rate = (Math.random() - 0.45) * 8
    points.push({
      time: d.toISOString().slice(0, 16).replace('T', ' '),
      value: '0',
      cumulative: '0',
      unrealizedPnl: pnl.toFixed(2),
      unrealizedPnlRate: rate.toFixed(2),
    })
  }
  return { points, period: period ?? '7d' }
}

function getAgentPositions(agentId: string): { list: PositionListItem[]; total: number } {
  const agent = mockAgents.find((a) => a.id === agentId)
  const exchange = agent?.exchange
  let list = [...mockPositions]
  if (exchange) list = list.filter((p) => p.exchange === exchange)
  return { list: list.slice(0, 10), total: list.length }
}

function getAgentOrders(agentId: string, params?: { status?: OrderStatus; page?: number; pageSize?: number }) {
  const agent = mockAgents.find((a) => a.id === agentId)
  const exchange = agent?.exchange
  let list = [...mockOrders]
  if (exchange) list = list.filter((o) => o.exchange === exchange)
  const total = list.length
  const page = params?.page ?? 1
  const pageSize = params?.pageSize ?? 10
  list = list.slice((page - 1) * pageSize, page * pageSize)
  return { list, total }
}

const mockAgentOperations: AgentOperationItem[] = [
  {
    id: 'op1',
    agentId: '1',
    type: 'open_long',
    symbol: 'BTCUSDT',
    exchange: 'binance',
    side: 'buy',
    quantity: '0.05',
    price: '44200',
    reason: '趋势突破',
    result: 'success',
    createdAt: '2024-02-14T10:30:00Z',
    chainOfThought: [
      { step: 1, thought: '检查 BTC 近期走势与成交量', conclusion: '放量突破 44000 阻力' },
      { step: 2, thought: '评估当前持仓与风险敞口', conclusion: '仓位未超限，可加多' },
      { step: 3, thought: '计算建议开仓量与止损位', conclusion: '开 0.05 BTC 多单，止损 43500' },
    ],
  },
  {
    id: 'op2',
    agentId: '1',
    type: 'close_short',
    symbol: 'SOLUSDT',
    exchange: 'binance',
    side: 'buy',
    quantity: '20',
    reason: '止盈平仓',
    result: 'success',
    createdAt: '2024-02-14T09:15:00Z',
    chainOfThought: [
      { step: 1, thought: 'SOL 空单浮盈已达目标 2%', conclusion: '触发止盈' },
      { step: 2, thought: '市价平仓执行', conclusion: '委托已提交' },
    ],
  },
  {
    id: 'op3',
    agentId: '1',
    type: 'adjust',
    symbol: 'ETHUSDT',
    reason: '调仓：降低 ETH 占比',
    result: 'success',
    createdAt: '2024-02-14T08:00:00Z',
    chainOfThought: [
      { step: 1, thought: 'ETH 占比超过组合上限', conclusion: '需减仓' },
      { step: 2, thought: '卖出部分 ETH 多头', conclusion: '已下单' },
    ],
  },
]

function getAgentOperations(agentId: string, limit = 50): { list: AgentOperationItem[]; total: number } {
  const list = mockAgentOperations.filter((o) => o.agentId === agentId).slice(0, limit)
  return { list, total: list.length }
}

function getAgentStrategyConfig(agentId: string): { strategyConfig: StrategyConfig | null } {
  const config = mockAgentStrategyConfigs[agentId] || null
  return { strategyConfig: config }
}

function updateAgentStrategyConfig(agentId: string, strategyConfig: StrategyConfig): { success: boolean } {
  mockAgentStrategyConfigs[agentId] = { ...strategyConfig }
  const agent = mockAgents.find((a) => a.id === agentId)
  if (agent) {
    agent.strategyConfig = mockAgentStrategyConfigs[agentId]
    agent.updatedAt = new Date().toISOString()
  }
  return { success: true }
}

// ---------- 行情面板 Mock ----------
type MarketInterval = '15m' | '1h' | '4h' | '1d'

interface MarketSymbolItem {
  symbol: string
  baseAsset: string
  quoteAsset: string
}

const marketSymbols: MarketSymbolItem[] = [
  { symbol: 'BTCUSDT', baseAsset: 'BTC', quoteAsset: 'USDT' },
  { symbol: 'ETHUSDT', baseAsset: 'ETH', quoteAsset: 'USDT' },
  { symbol: 'SOLUSDT', baseAsset: 'SOL', quoteAsset: 'USDT' },
  { symbol: 'BNBUSDT', baseAsset: 'BNB', quoteAsset: 'USDT' },
  { symbol: 'XRPUSDT', baseAsset: 'XRP', quoteAsset: 'USDT' },
  { symbol: 'DOGEUSDT', baseAsset: 'DOGE', quoteAsset: 'USDT' },
  { symbol: 'ADAUSDT', baseAsset: 'ADA', quoteAsset: 'USDT' },
  { symbol: 'AVAXUSDT', baseAsset: 'AVAX', quoteAsset: 'USDT' },
  { symbol: 'DOTUSDT', baseAsset: 'DOT', quoteAsset: 'USDT' },
  { symbol: 'LINKUSDT', baseAsset: 'LINK', quoteAsset: 'USDT' },
]

function getMarketSymbols(params?: { keyword?: string }) {
  const keyword = (params?.keyword ?? '').trim().toUpperCase()
  if (!keyword) return { list: marketSymbols.slice(0, 20) }
  const list = marketSymbols.filter((item) => item.symbol.includes(keyword) || item.baseAsset.includes(keyword))
  return { list: list.slice(0, 20) }
}

function seededRandom(seed: string) {
  let hash = 0
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i)
    hash |= 0
  }
  const x = Math.sin(hash) * 10000
  return x - Math.floor(x)
}

function intervalMinutes(interval: MarketInterval): number {
  const map: Record<MarketInterval, number> = {
    '15m': 15,
    '1h': 60,
    '4h': 240,
    '1d': 1440,
  }
  return map[interval] ?? 60
}

function backtestIntervalMs(interval: string): number {
  const map: Record<string, number> = {
    '1m': 60 * 1000,
    '5m': 5 * 60 * 1000,
    '15m': 15 * 60 * 1000,
    '1h': 60 * 60 * 1000,
    '4h': 4 * 60 * 60 * 1000,
    '1d': 24 * 60 * 60 * 1000,
  }
  return map[interval] ?? 60 * 60 * 1000
}

function symbolBasePrice(symbol: string): number {
  const map: Record<string, number> = {
    BTCUSDT: 62000,
    ETHUSDT: 3200,
    SOLUSDT: 140,
    BNBUSDT: 560,
    XRPUSDT: 0.62,
    DOGEUSDT: 0.15,
    ADAUSDT: 0.72,
    AVAXUSDT: 42,
    DOTUSDT: 9.2,
    LINKUSDT: 19.5,
  }
  return map[symbol] ?? 100
}

function getMarketKline(params?: { symbol?: string; interval?: MarketInterval; limit?: number }) {
  const symbol = (params?.symbol ?? 'BTCUSDT').toUpperCase()
  const interval = params?.interval ?? '1h'
  const limit = Math.max(30, Math.min(Number(params?.limit ?? 120), 300))
  const ms = intervalMinutes(interval) * 60 * 1000
  const end = Date.now()
  const list: Array<{ time: string; open: string; high: string; low: string; close: string; volume: string }> = []
  let price = symbolBasePrice(symbol)
  for (let i = limit - 1; i >= 0; i -= 1) {
    const ts = end - i * ms
    const wave = (seededRandom(`${symbol}-${interval}-${i}-w`) - 0.5) * 0.04
    const drift = (seededRandom(`${symbol}-${interval}-${i}-d`) - 0.48) * 0.01
    const change = wave + drift
    const open = price
    const close = Math.max(0.0001, open * (1 + change))
    const upWick = Math.max(open, close) * (seededRandom(`${symbol}-${interval}-${i}-h`) * 0.01)
    const downWick = Math.max(0.0001, Math.min(open, close) * (seededRandom(`${symbol}-${interval}-${i}-l`) * 0.01))
    const high = Math.max(open, close) + upWick
    const low = Math.max(0.0001, Math.min(open, close) - downWick)
    const volume = Math.abs(close - open) * (80 + seededRandom(`${symbol}-${interval}-${i}-v`) * 300)
    list.push({
      time: new Date(ts).toISOString(),
      open: open.toFixed(6),
      high: high.toFixed(6),
      low: low.toFixed(6),
      close: close.toFixed(6),
      volume: volume.toFixed(2),
    })
    price = close
  }
  return { list }
}

function calcMA(values: number[], period: number) {
  if (!values.length) return 0
  const size = Math.min(period, values.length)
  const tail = values.slice(values.length - size)
  const total = tail.reduce((sum, v) => sum + v, 0)
  return total / size
}

function calcRSI(values: number[], period = 14) {
  if (values.length <= 1) return 50
  const gains: number[] = []
  const losses: number[] = []
  for (let i = 1; i < values.length; i += 1) {
    const diff = values[i] - values[i - 1]
    if (diff >= 0) gains.push(diff)
    else losses.push(Math.abs(diff))
  }
  const avgGain = gains.slice(-period).reduce((s, v) => s + v, 0) / period
  const avgLoss = losses.slice(-period).reduce((s, v) => s + v, 0) / period
  if (avgLoss === 0) return 100
  const rs = avgGain / avgLoss
  return 100 - 100 / (1 + rs)
}

function getMarketIndicators(params?: { symbol?: string; interval?: MarketInterval }) {
  const symbol = (params?.symbol ?? 'BTCUSDT').toUpperCase()
  const interval = params?.interval ?? '1h'
  const { list } = getMarketKline({ symbol, interval, limit: 160 })
  const closes = list.map((k) => parseFloat(k.close))
  const latestPrice = closes[closes.length - 1] ?? symbolBasePrice(symbol)
  const prev24 = closes[Math.max(0, closes.length - 25)] ?? latestPrice
  const change24h = prev24 === 0 ? 0 : ((latestPrice - prev24) / prev24) * 100
  const recent = list.slice(-24)
  const high24h = Math.max(...recent.map((k) => parseFloat(k.high)))
  const low24h = Math.min(...recent.map((k) => parseFloat(k.low)))
  const volume24h = recent.reduce((sum, k) => sum + parseFloat(k.volume), 0)
  const ma5 = calcMA(closes, 5)
  const ma10 = calcMA(closes, 10)
  const ma20 = calcMA(closes, 20)
  const rsi14 = calcRSI(closes, 14)
  const ema12 = calcMA(closes, 12)
  const ema26 = calcMA(closes, 26)
  const macd = ema12 - ema26
  const signal = macd * 0.88
  const histogram = macd - signal
  const variance = closes.slice(-24).reduce((sum, p) => sum + Math.pow(p - latestPrice, 2), 0) / 24
  const volatility = Math.sqrt(variance) / Math.max(latestPrice, 0.0001) * 100
  let recommendation: 'bullish' | 'bearish' | 'neutral' = 'neutral'
  if (latestPrice > ma20 && rsi14 > 55 && histogram > 0) recommendation = 'bullish'
  else if (latestPrice < ma20 && rsi14 < 45 && histogram < 0) recommendation = 'bearish'
  return {
    symbol,
    interval,
    latestPrice: latestPrice.toFixed(6),
    change24h: change24h.toFixed(2),
    high24h: high24h.toFixed(6),
    low24h: low24h.toFixed(6),
    volume24h: volume24h.toFixed(2),
    ma5: ma5.toFixed(6),
    ma10: ma10.toFixed(6),
    ma20: ma20.toFixed(6),
    rsi14: rsi14.toFixed(2),
    macd: macd.toFixed(6),
    signal: signal.toFixed(6),
    histogram: histogram.toFixed(6),
    volatility: volatility.toFixed(2),
    recommendation,
  }
}

// ---------- 回测 Mock 数据 ----------
let mockBacktestSeq = 10

function generateMockEquityCurve(days: number, startDate: string): TimeSeriesPoint[] {
  const points: TimeSeriesPoint[] = []
  let cumReturn = 0
  const start = new Date(startDate)
  for (let i = 0; i < days; i++) {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    const dailyReturn = (Math.random() - 0.45) * 3
    cumReturn += dailyReturn
    const pnl = (Math.random() - 0.4) * 120
    const rate = (Math.random() - 0.4) * 6
    points.push({
      time: d.toISOString().slice(0, 10),
      value: parseFloat(cumReturn.toFixed(2)),
      unrealizedPnl: parseFloat(pnl.toFixed(2)),
      unrealizedPnlRate: parseFloat(rate.toFixed(2)),
    })
  }
  return points
}

function generateMockDrawdownCurve(equityCurve: TimeSeriesPoint[]): TimeSeriesPoint[] {
  let peak = 0
  return equityCurve.map(point => {
    if (point.value > peak) peak = point.value
    const drawdown = peak > 0 ? ((peak - point.value) / peak) * 100 : 0
    return {
      time: point.time,
      value: parseFloat(Math.max(0, drawdown).toFixed(2))
    }
  })
}

function generateMockBenchmarkCurve(days: number, startDate: string): TimeSeriesPoint[] {
  const points: TimeSeriesPoint[] = []
  let cumReturn = 0
  const start = new Date(startDate)
  for (let i = 0; i < days; i++) {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    const dailyReturn = (Math.random() - 0.48) * 2
    cumReturn += dailyReturn
    points.push({
      time: d.toISOString().slice(0, 10),
      value: parseFloat(cumReturn.toFixed(2))
    })
  }
  return points
}

function generateMockTrades(count: number, startDate: string, symbols: string[]): BacktestTradeRecord[] {
  const trades: BacktestTradeRecord[] = []
  let balance = 10000
  const start = new Date(startDate)
  
  for (let i = 0; i < count; i++) {
    const d = new Date(start)
    d.setDate(d.getDate() + Math.floor(i / 3))
    d.setHours(Math.floor(Math.random() * 24))
    d.setMinutes(Math.floor(Math.random() * 60))
    
    const symbol = symbols[Math.floor(Math.random() * symbols.length)]
    const side = Math.random() > 0.5 ? 'buy' : 'sell'
    const type = i % 2 === 0 ? 'open' : 'close'
    const price = symbol.includes('BTC') ? 42000 + Math.random() * 3000 : 2200 + Math.random() * 200
    const quantity = symbol.includes('BTC') ? 0.01 + Math.random() * 0.05 : 0.5 + Math.random() * 2
    const amount = price * quantity
    const fee = amount * 0.001
    const pnl = type === 'close' ? (Math.random() - 0.4) * amount * 0.05 : 0
    const pnlPercent = type === 'close' ? (pnl / amount) * 100 : 0
    
    balance += pnl - fee
    
    const reasonings = [
      '价格突破关键阻力位，成交量放大，趋势确认',
      'RSI 超卖反弹信号，结合支撑位进场',
      'MACD 金叉，短期趋势转多',
      '达到止盈目标，执行平仓',
      '价格跌破支撑位，触发止损',
      '追踪止损触发，锁定利润'
    ]
    
    trades.push({
      id: `bt-${i + 1}`,
      timestamp: d.toISOString(),
      symbol,
      side,
      type,
      price: parseFloat(price.toFixed(2)),
      quantity: parseFloat(quantity.toFixed(4)),
      amount: parseFloat(amount.toFixed(2)),
      fee: parseFloat(fee.toFixed(2)),
      pnl: parseFloat(pnl.toFixed(2)),
      pnlPercent: parseFloat(pnlPercent.toFixed(2)),
      balance: parseFloat(balance.toFixed(2)),
      reasoning: Math.random() > 0.3 ? reasonings[Math.floor(Math.random() * reasonings.length)] : undefined,
      signals: Math.random() > 0.5 ? ['MA突破', 'RSI信号', 'MACD金叉'].slice(0, Math.floor(Math.random() * 3) + 1) : undefined
    })
  }
  return trades
}

function generateMockBacktestResult(config: BacktestConfig): BacktestResult {
  const startDate = config.startTime
  const endDate = config.endTime
  const days = Math.ceil((new Date(endDate).getTime() - new Date(startDate).getTime()) / (1000 * 60 * 60 * 24))
  
  const equityCurve = generateMockEquityCurve(days, startDate)
  const drawdownCurve = generateMockDrawdownCurve(equityCurve)
  const benchmarkCurve = generateMockBenchmarkCurve(days, startDate)
  const trades = generateMockTrades(Math.floor(days * 2.5), startDate, config.symbols)
  
  const totalReturn = equityCurve[equityCurve.length - 1]?.value || 0
  const maxDrawdown = Math.max(...drawdownCurve.map(p => p.value))
  const winTrades = trades.filter(t => t.type === 'close' && t.pnl > 0).length
  const lossTrades = trades.filter(t => t.type === 'close' && t.pnl < 0).length
  const totalCloseTrades = winTrades + lossTrades
  
  const statistics: BacktestStatistics = {
    totalReturn: parseFloat(totalReturn.toFixed(2)),
    annualizedReturn: parseFloat((totalReturn * (365 / days)).toFixed(2)),
    maxDrawdown: parseFloat(maxDrawdown.toFixed(2)),
    sharpeRatio: parseFloat((1.5 + Math.random()).toFixed(2)),
    sortinoRatio: parseFloat((1.8 + Math.random()).toFixed(2)),
    winRate: parseFloat((totalCloseTrades > 0 ? (winTrades / totalCloseTrades) * 100 : 0).toFixed(2)),
    profitFactor: parseFloat((1.2 + Math.random() * 0.8).toFixed(2)),
    totalTrades: trades.length,
    winTrades,
    lossTrades,
    avgProfit: parseFloat((trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0) / Math.max(winTrades, 1)).toFixed(2)),
    avgLoss: parseFloat(Math.abs(trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0) / Math.max(lossTrades, 1)).toFixed(2)),
    avgHoldingTime: `${Math.floor(Math.random() * 8 + 2)}h ${Math.floor(Math.random() * 60)}m`,
    maxConsecutiveWins: Math.floor(Math.random() * 5 + 3),
    maxConsecutiveLosses: Math.floor(Math.random() * 3 + 2),
    finalCapital: parseFloat((config.initialCapital * (1 + totalReturn / 100)).toFixed(2))
  }
  
  return {
    statistics,
    equityCurve,
    drawdownCurve,
    benchmarkCurve,
    positionHistory: [],
    trades
  }
}

const mockBacktests: BacktestTask[] = [
  {
    id: '1',
    name: 'BTC 动量策略回测',
    status: 'completed',
    progress: 100,
    createdAt: '2026-02-01T08:00:00Z',
    completedAt: '2026-02-01T08:15:00Z',
    config: {
      agentId: '1',
      agentName: 'BTC 趋势 Agent',
      strategyConfig: {
        tradingStyle: 'balanced',
        symbols: ['BTCUSDT', 'ETHUSDT'],
        initialCapital: 10000,
        targetProfit: { type: 'percentage', value: 5 },
        tradingCycle: 'short_term',
        minOrderAmount: 50,
        maxOrderAmount: 2000,
        maxLeverage: 5,
        positionDirection: 'both',
        remark: undefined
      },
      startTime: '2025-11-01',
      endTime: '2026-01-31',
      initialCapital: 10000,
      exchange: 'binance',
      symbols: ['BTCUSDT', 'ETHUSDT'],
      interval: '15m',
      makerFee: 0.1,
      takerFee: 0.1,
      slippage: 0.05
    },
    result: undefined
  },
  {
    id: '2',
    name: 'ETH 网格策略测试',
    status: 'completed',
    progress: 100,
    createdAt: '2026-02-10T10:00:00Z',
    completedAt: '2026-02-10T10:20:00Z',
    config: {
      agentId: '2',
      agentName: 'ETH 网格 Agent',
      strategyConfig: {
        tradingStyle: 'conservative',
        symbols: ['ETHUSDT'],
        initialCapital: 5000,
        targetProfit: { type: 'percentage', value: 2 },
        tradingCycle: 'short_term',
        minOrderAmount: 20,
        maxOrderAmount: 500,
        maxLeverage: 1,
        positionDirection: 'long_only',
        remark: undefined
      },
      startTime: '2025-12-01',
      endTime: '2026-01-31',
      initialCapital: 5000,
      exchange: 'binance',
      symbols: ['ETHUSDT'],
      interval: '1h',
      makerFee: 0.1,
      takerFee: 0.1,
      slippage: 0.05
    },
    result: undefined
  },
  {
    id: '3',
    name: 'SOL 激进策略回测',
    status: 'running',
    progress: 45,
    createdAt: '2026-03-04T09:00:00Z',
    config: {
      agentId: '1',
      agentName: 'BTC 趋势 Agent',
      strategyConfig: {
        tradingStyle: 'aggressive',
        symbols: ['SOLUSDT'],
        initialCapital: 20000,
        targetProfit: { type: 'percentage', value: 10 },
        tradingCycle: 'short_term',
        minOrderAmount: 100,
        maxOrderAmount: 5000,
        maxLeverage: 10,
        positionDirection: 'both',
        remark: undefined
      },
      startTime: '2025-10-01',
      endTime: '2026-02-28',
      initialCapital: 20000,
      exchange: 'binance',
      symbols: ['SOLUSDT'],
      interval: '15m',
      makerFee: 0.1,
      takerFee: 0.1,
      slippage: 0.05
    }
  }
]

// 为已完成的回测生成结果
mockBacktests.forEach(bt => {
  if (bt.status === 'completed' && !bt.result) {
    bt.result = generateMockBacktestResult(bt.config)
  }
})

function getBacktestList(params?: { status?: BacktestStatus; page?: number; pageSize?: number }): { list: BacktestListItem[]; total: number } {
  let list = mockBacktests.map(bt => ({
    id: bt.id,
    name: bt.name,
    status: bt.status,
    agentId: bt.config.agentId,
    agentName: bt.config.agentName,
    exchange: bt.config.exchange,
    symbols: bt.config.symbols,
    startTime: bt.config.startTime,
    endTime: bt.config.endTime,
    initialCapital: bt.config.initialCapital,
    totalReturn: bt.result?.statistics.totalReturn,
    maxDrawdown: bt.result?.statistics.maxDrawdown,
    winRate: bt.result?.statistics.winRate,
    sharpeRatio: bt.result?.statistics.sharpeRatio,
    createdAt: bt.createdAt,
    completedAt: bt.completedAt
  }))
  
  if (params?.status) list = list.filter(b => b.status === params.status)
  
  return { list, total: list.length }
}

function getBacktestById(id: string): BacktestTask | undefined {
  const bt = mockBacktests.find(b => b.id === id)
  if (bt && bt.status === 'completed' && !bt.result) {
    bt.result = generateMockBacktestResult(bt.config)
  }
  return bt
}

function getBacktestKline(id: string, params?: { symbol?: string }) {
  const bt = getBacktestById(id)
  if (!bt) throw new Error('回测任务不存在')
  const targetSymbol = (params?.symbol || bt.config.symbols[0] || 'BTCUSDT').toUpperCase()
  const configured = bt.config.symbols.map((s) => s.toUpperCase())
  if (!configured.includes(targetSymbol)) throw new Error('交易对不在回测配置中')

  const startMs = new Date(bt.config.startTime).getTime()
  const endMs = new Date(bt.config.endTime).getTime()
  const intervalMs = backtestIntervalMs(bt.config.interval)
  const list: Array<{ time: string; open: string; high: string; low: string; close: string; volume: string }> = []
  let price = symbolBasePrice(targetSymbol)
  let ts = startMs
  let i = 0
  const maxBars = 2000

  while (ts <= endMs && list.length < maxBars) {
    const wave = (seededRandom(`${targetSymbol}-${bt.config.interval}-${i}-w`) - 0.5) * 0.04
    const drift = (seededRandom(`${targetSymbol}-${bt.config.interval}-${i}-d`) - 0.48) * 0.01
    const change = wave + drift
    const open = price
    const close = Math.max(0.0001, open * (1 + change))
    const upWick = Math.max(open, close) * (seededRandom(`${targetSymbol}-${bt.config.interval}-${i}-h`) * 0.01)
    const downWick = Math.max(0.0001, Math.min(open, close) * (seededRandom(`${targetSymbol}-${bt.config.interval}-${i}-l`) * 0.01))
    const high = Math.max(open, close) + upWick
    const low = Math.max(0.0001, Math.min(open, close) - downWick)
    const volume = Math.abs(close - open) * (80 + seededRandom(`${targetSymbol}-${bt.config.interval}-${i}-v`) * 300)
    list.push({
      time: new Date(ts).toISOString(),
      open: open.toFixed(6),
      high: high.toFixed(6),
      low: low.toFixed(6),
      close: close.toFixed(6),
      volume: volume.toFixed(2),
    })
    price = close
    ts += intervalMs
    i += 1
  }

  return {
    symbol: targetSymbol,
    interval: bt.config.interval,
    startTime: bt.config.startTime,
    endTime: bt.config.endTime,
    list,
  }
}

function createBacktest(dto: CreateBacktestDto): { id: string } {
  const id = String(++mockBacktestSeq)
  const now = new Date().toISOString()
  const task: BacktestTask = {
    id,
    name: dto.name,
    status: 'running',
    progress: 0,
    createdAt: now,
    config: dto.config
  }
  mockBacktests.unshift(task)
  
  // 模拟异步完成
  setTimeout(() => {
    const bt = mockBacktests.find(b => b.id === id)
    if (bt && bt.status === 'running') {
      bt.status = 'completed'
      bt.progress = 100
      bt.completedAt = new Date().toISOString()
      bt.result = generateMockBacktestResult(bt.config)
    }
  }, 5000)
  
  return { id }
}

function getBacktestProgress(id: string): { status: BacktestStatus; progress: number; message?: string } {
  const bt = mockBacktests.find(b => b.id === id)
  if (!bt) throw new Error('回测任务不存在')
  
  if (bt.status === 'running') {
    bt.progress = Math.min(100, bt.progress + Math.floor(Math.random() * 15 + 5))
    if (bt.progress >= 100) {
      bt.status = 'completed'
      bt.completedAt = new Date().toISOString()
      bt.result = generateMockBacktestResult(bt.config)
    }
  }
  
  return {
    status: bt.status,
    progress: bt.progress,
    message: bt.status === 'running' ? `正在处理 ${bt.config.startTime} - ${bt.config.endTime} 的历史数据...` : undefined
  }
}

function stopBacktest(id: string): { success: boolean } {
  const bt = mockBacktests.find(b => b.id === id)
  if (!bt) throw new Error('回测任务不存在')
  if (bt.status === 'running') {
    bt.status = 'failed'
    bt.errorMessage = '用户手动停止'
  }
  return { success: true }
}

function deleteBacktest(id: string): void {
  const idx = mockBacktests.findIndex(b => b.id === id)
  if (idx === -1) throw new Error('回测任务不存在')
  mockBacktests.splice(idx, 1)
}

// ---------- 收益分析 Mock ----------
type AnalyticsExchangeCode = 'binance' | 'okx' | 'bybit'

function getAnalyticsDateRange(params?: { from?: string; to?: string }): { from: Date; to: Date } {
  const to = params?.to ? new Date(params.to) : new Date()
  let from = params?.from ? new Date(params.from) : new Date(to)
  from.setDate(from.getDate() - 30)
  if (from > to) from = new Date(to.getTime() - 30 * 24 * 60 * 60 * 1000)
  return { from, to }
}

function getProfitSummary(params?: { from?: string; to?: string; exchange?: AnalyticsExchangeCode }) {
  const { from, to } = getAnalyticsDateRange(params)
  const totalProfit = (Math.random() * 8000 + 2000).toFixed(2)
  const totalFee = (Math.random() * 200 + 50).toFixed(2)
  const net = parseFloat(totalProfit) - parseFloat(totalFee)
  const returnRate = (net / 100000 * 100).toFixed(2)
  return {
    totalProfit,
    totalFee,
    netProfit: net.toFixed(2),
    returnRate: returnRate + '%',
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
    exchange: params?.exchange,
  }
}

function getProfitTrend(params?: { from?: string; to?: string; period?: 'day' | 'week'; exchange?: AnalyticsExchangeCode }) {
  const { from, to } = getAnalyticsDateRange(params)
  const period = params?.period ?? 'day'
  const points: { date: string; profit: string; cumulative?: string }[] = []
  let cum = 0
  const step = period === 'week' ? 7 : 1
  const d = new Date(from)
  while (d <= to) {
    const v = (Math.random() - 0.35) * 1500
    cum += v
    points.push({
      date: d.toISOString().slice(0, 10),
      profit: v.toFixed(2),
      cumulative: cum.toFixed(2),
    })
    d.setDate(d.getDate() + step)
  }
  return { points, period }
}

function getProfitByExchange(_params?: { from?: string; to?: string }) {
  const exchanges: AnalyticsExchangeCode[] = ['binance', 'okx', 'bybit']
  const list = exchanges.map((exchange) => {
    const totalProfit = (Math.random() * 4000 + 500).toFixed(2)
    const totalFee = (Math.random() * 80 + 20).toFixed(2)
    const net = parseFloat(totalProfit) - parseFloat(totalFee)
    return {
      exchange,
      totalProfit,
      totalFee,
      netProfit: net.toFixed(2),
      tradeCount: Math.floor(Math.random() * 200 + 50),
    }
  })
  return { list }
}

function getProfitBySymbol(_params?: { from?: string; to?: string }) {
  const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
  const list = symbols.map((symbol) => {
    const totalProfit = (Math.random() * 3000 - 200).toFixed(2)
    const totalFee = (Math.random() * 60 + 10).toFixed(2)
    const net = parseFloat(totalProfit) - parseFloat(totalFee)
    return {
      symbol,
      totalProfit,
      totalFee,
      netProfit: net.toFixed(2),
      tradeCount: Math.floor(Math.random() * 150 + 20),
    }
  })
  return { list }
}

// ---------- 消息面采集 Mock ----------
let mockNewsIntelSeq = 2

const mockNewsIntelAgents: Array<{
  id: string
  name: string
  remark?: string
  sectors: string[]
  customKeywords?: string
  symbolCodes?: string
  llmModelId: number
  llmModelName?: string
  intervalMinutes: number
  maxItemsPerBatch?: number
  temperature?: number
  status: 'running' | 'stopped'
  lastRunAt?: string
  createdAt: string
  updatedAt: string
}> = [
  {
    id: '1',
    name: '证券·宏观组合',
    remark: '示例任务',
    sectors: ['securities', 'macro'],
    customKeywords: '降准 利率',
    symbolCodes: '',
    llmModelId: 1,
    llmModelName: 'GPT-4o',
    intervalMinutes: 60,
    maxItemsPerBatch: 10,
    temperature: 0.3,
    status: 'running',
    lastRunAt: new Date().toISOString(),
    createdAt: '2026-03-01T08:00:00Z',
    updatedAt: new Date().toISOString(),
  },
]

const mockNewsTimelineByAgent: Record<
  string,
  Array<{
    id: string
    agentId: string
    title: string
    summary?: string
    sourceUrl?: string
    sourceName?: string
    eventTime?: string
    ingestedAt: string
    sortTime: string
  }>
> = {}

function seedMockNewsItems() {
  const agentId = '1'
  const now = Date.now()
  const items: (typeof mockNewsTimelineByAgent)[string] = []
  for (let i = 0; i < 15; i++) {
    const ingested = new Date(now - i * 7200000 - i * 130000)
    const eventTime = new Date(ingested.getTime() - 20 * 60000)
    const sortTime = new Date(Math.max(eventTime.getTime(), ingested.getTime())).toISOString()
    items.push({
      id: `ni-${agentId}-${i}`,
      agentId,
      title: `【示例】金融板块动态 ${i + 1}：政策与市场解读`,
      summary:
        '此为 Mock 数据。接入后端后，此处展示 LLM 联网检索并归一化后的资讯摘要与来源链接。',
      sourceUrl: `https://example.com/finance/news/${i}`,
      sourceName: '示例财经',
      eventTime: eventTime.toISOString(),
      ingestedAt: ingested.toISOString(),
      sortTime,
    })
  }
  mockNewsTimelineByAgent[agentId] = items
}
seedMockNewsItems()

function getNewsIntelList() {
  return { list: [...mockNewsIntelAgents], total: mockNewsIntelAgents.length }
}

function createNewsIntelAgent(body: any) {
  if (!body?.name?.trim()) throw new Error('请输入任务名称')
  if (!body?.sectors?.length) throw new Error('请选择金融方向')
  if (!body?.llmModelId) throw new Error('请选择模型')
  const id = String(++mockNewsIntelSeq)
  const now = new Date().toISOString()
  const item = {
    id,
    name: body.name.trim(),
    remark: body.remark,
    sectors: body.sectors,
    customKeywords: body.customKeywords,
    symbolCodes: body.symbolCodes,
    llmModelId: body.llmModelId,
    llmModelName: `Model-${body.llmModelId}`,
    intervalMinutes: body.intervalMinutes ?? 60,
    maxItemsPerBatch: body.maxItemsPerBatch ?? 10,
    temperature: body.temperature ?? 0.3,
    status: (body.runOnCreate ? 'running' : 'stopped') as 'running' | 'stopped',
    lastRunAt: body.runOnCreate ? now : undefined,
    createdAt: now,
    updatedAt: now,
  }
  mockNewsIntelAgents.push(item)
  mockNewsTimelineByAgent[id] = []
  return item
}

function updateNewsIntelAgent(id: string, body: any) {
  const idx = mockNewsIntelAgents.findIndex((a) => a.id === id)
  if (idx === -1) throw new Error('任务不存在')
  const now = new Date().toISOString()
  const cur = mockNewsIntelAgents[idx]
  mockNewsIntelAgents[idx] = {
    ...cur,
    ...(body.name !== undefined && { name: body.name }),
    ...(body.remark !== undefined && { remark: body.remark }),
    ...(body.sectors !== undefined && { sectors: body.sectors }),
    ...(body.customKeywords !== undefined && { customKeywords: body.customKeywords }),
    ...(body.symbolCodes !== undefined && { symbolCodes: body.symbolCodes }),
    ...(body.llmModelId !== undefined && {
      llmModelId: body.llmModelId,
      llmModelName: `Model-${body.llmModelId}`,
    }),
    ...(body.intervalMinutes !== undefined && { intervalMinutes: body.intervalMinutes }),
    ...(body.maxItemsPerBatch !== undefined && { maxItemsPerBatch: body.maxItemsPerBatch }),
    ...(body.temperature !== undefined && { temperature: body.temperature }),
    updatedAt: now,
  }
  return mockNewsIntelAgents[idx]
}

function getNewsTimelineItems(
  agentId: string,
  params?: { order?: string; page?: number; pageSize?: number; keyword?: string }
) {
  let list = [...(mockNewsTimelineByAgent[agentId] || [])]
  const kw = (params?.keyword || '').trim().toLowerCase()
  if (kw) {
    list = list.filter(
      (it) =>
        it.title.toLowerCase().includes(kw) || (it.summary && it.summary.toLowerCase().includes(kw))
    )
  }
  list.sort((a, b) => {
    const ta = new Date(a.sortTime).getTime()
    const tb = new Date(b.sortTime).getTime()
    return params?.order === 'asc' ? ta - tb : tb - ta
  })
  const total = list.length
  const page = params?.page ?? 1
  const pageSize = params?.pageSize ?? 20
  const start = (page - 1) * pageSize
  list = list.slice(start, start + pageSize)
  return { list, total }
}

function handleNewsIntelligenceRoute(
  method: string,
  urlPath: string,
  config?: { params?: any },
  body?: any
): Promise<any> | null {
  const collectMatch = urlPath.match(/^\/v1\/news-intelligence-agents\/([^/]+)\/collect$/)
  if (method === 'POST' && collectMatch) {
    const id = collectMatch[1]
    return delay(800).then(() => {
      const a = mockNewsIntelAgents.find((x) => x.id === id)
      if (!a) throw new Error('任务不存在')
      const now = new Date().toISOString()
      a.lastRunAt = now
      a.updatedAt = now
      if (!mockNewsTimelineByAgent[id]) mockNewsTimelineByAgent[id] = []
      mockNewsTimelineByAgent[id].unshift({
        id: `ni-${id}-mock-${Date.now()}`,
        agentId: id,
        title: `【立即采集】${now.slice(11, 19)} Mock 新增一条`,
        summary: 'Mock：接入后端后将展示 LLM 联网检索结果。',
        sourceUrl: 'https://example.com',
        sourceName: 'Mock',
        eventTime: now,
        ingestedAt: now,
        sortTime: now,
      })
      return { success: true, inserted: 1, message: '已写入 1 条资讯' }
    })
  }
  const itemsMatch = urlPath.match(/^\/v1\/news-intelligence-agents\/([^/]+)\/items$/)
  if (method === 'GET' && itemsMatch) {
    const agentId = itemsMatch[1]
    return delay(200).then(() => getNewsTimelineItems(agentId, config?.params))
  }
  const startStop = urlPath.match(/^\/v1\/news-intelligence-agents\/([^/]+)\/(start|stop)$/)
  if (method === 'POST' && startStop) {
    const [, id, action] = startStop
    return delay(200).then(() => {
      const a = mockNewsIntelAgents.find((x) => x.id === id)
      if (!a) throw new Error('任务不存在')
      a.status = action === 'start' ? 'running' : 'stopped'
      a.lastRunAt = new Date().toISOString()
      a.updatedAt = a.lastRunAt
      return { success: true, message: action === 'start' ? '已启动' : '已停止' }
    })
  }
  const idOnly = urlPath.match(/^\/v1\/news-intelligence-agents\/([^/]+)$/)
  if (method === 'GET' && idOnly) {
    const id = idOnly[1]
    return delay(200).then(() => {
      const a = mockNewsIntelAgents.find((x) => x.id === id)
      if (!a) throw new Error('任务不存在')
      return { ...a }
    })
  }
  if (method === 'PUT' && idOnly) {
    const id = idOnly[1]
    return delay(300).then(() => updateNewsIntelAgent(id, body))
  }
  if (method === 'DELETE' && idOnly) {
    const id = idOnly[1]
    return delay(200).then(() => {
      const idx = mockNewsIntelAgents.findIndex((x) => x.id === id)
      if (idx === -1) throw new Error('任务不存在')
      mockNewsIntelAgents.splice(idx, 1)
      delete mockNewsTimelineByAgent[id]
    })
  }
  return null
}

const MOCK_TA_RECORD_ID = 'mock-ta-record-0001'

/** 技术指标分析 Agent（Mock，与后端 data 结构对齐） */
async function mockTechnicalAnalysis(body?: {
  symbol?: string
  analysisDate?: string
  timeframe?: string
  lookbackDays?: number
  llmModelId?: number
  temperature?: number
}) {
  await delay(400)
  const symbol = body?.symbol || 'BTC-USDT'
  const useModel = body?.llmModelId != null ? Number(body.llmModelId) : undefined
  return {
    success: true,
    recordId: MOCK_TA_RECORD_ID,
    symbol,
    analysisDate: new Date().toISOString(),
    timeframe: body?.timeframe || '4h',
    analysisMode: 'llm',
    ...(useModel != null && Number.isFinite(useModel)
      ? {
          llmModelId: useModel,
          llmModelName: `Mock 模型 ${useModel}`,
        }
      : {}),
    analysis: {
      summary: `${symbol} 当前处于震荡偏强格局（Mock），短期均线多头排列，RSI 中性区。`,
      trend: { direction: 'bullish', strength: 'moderate', description: 'MA 短期偏强' },
      momentum: { rsiStatus: 'neutral', macdStatus: 'bullish', description: 'RSI 约 55，MACD 柱为正' },
      volatility: { status: 'medium', bollingerPosition: 'middle', description: '波动率中等' },
      signals: [
        { type: 'bullish', indicator: 'MA', description: 'MA5 > MA20' },
        { type: 'bullish', indicator: 'MACD', description: '柱状图为正' },
      ],
      recommendation: {
        action: 'hold',
        confidence: 0.62,
        entryZone: '—',
        stopLoss: '—',
        takeProfit: '—',
        riskWarning: 'Mock 数据仅用于前端联调。',
      },
    },
    rawIndicators: {
      currentPrice: 65000,
      rsi14: 55.2,
      ma5: 64200,
      ma20: 63800,
      macd: { dif: 120, dea: 100, histogram: 20, signal: 'bullish' },
      bollinger: {
        upper: 66000,
        middle: 64500,
        lower: 63000,
        bandwidth: 4.2,
        position: 0.5,
        positionDesc: '中轨',
      },
    },
  }
}

async function mockTaRecordsList() {
  await delay(200)
  return {
    items: [
      {
        id: MOCK_TA_RECORD_ID,
        symbol: 'BTCUSDT',
        analysisDate: new Date().toISOString().slice(0, 10),
        timeframe: '4h',
        lookbackDays: 30,
        temperature: 0.3,
        llmModelId: null,
        llmModelName: null,
        success: true,
        errorMessage: null,
        summaryPreview: 'Mock：震荡偏强格局，短期均线多头排列',
        createdAt: new Date().toISOString(),
      },
    ],
    total: 1,
    page: 1,
    pageSize: 20,
  }
}

async function mockTaRecordDetail(recordId: string) {
  await delay(200)
  if (recordId !== MOCK_TA_RECORD_ID) {
    throw new Error('记录不存在或无权访问')
  }
  const snapshot = await mockTechnicalAnalysis({ symbol: 'BTCUSDT', timeframe: '4h' })
  delete (snapshot as { recordId?: string }).recordId
  return {
    id: MOCK_TA_RECORD_ID,
    createdAt: new Date().toISOString(),
    snapshot,
  }
}

/** GET /v1/technical-analysis/records 与 /v1/technical-analysis/records/:id */
function handleTechnicalAnalysisRecords(method: string, urlPath: string): Promise<any> | null {
  if (method !== 'GET') return null
  if (urlPath === '/v1/technical-analysis/records') {
    return mockTaRecordsList()
  }
  const m = urlPath.match(/^\/v1\/technical-analysis\/records\/([^/]+)$/)
  if (m) return mockTaRecordDetail(m[1])
  return null
}

// ---------- 精确匹配 Handlers ----------
export const mockHandlers: Record<string, (body?: any, params?: any) => Promise<any>> = {
  'POST /v1/auth/login': async (body) => mockLogin(body?.username),
  'POST /v1/auth/logout': async () => {
    await delay(200)
    return undefined
  },
  'POST /v1/auth/reset-password': async (body: { oldPassword?: string; newPassword?: string }) => {
    await delay(400)
    if (!body?.newPassword || body.newPassword.length < 6) throw new Error('新密码至少 6 位')
    return undefined
  },
  'GET /v1/users': async (_body, params) => {
    await delay(300)
    return getUsers(params)
  },
  'POST /v1/users': async (body: MockCreateUserPayload) => {
    await delay(300)
    if (mockUsers.some((u) => u.username === body.username)) throw new Error('用户名已存在')
    return createUser(body)
  },
  'GET /v1/exchange-accounts': async (_body, params) => {
    await delay(300)
    return getExchangeAccounts(params)
  },
  'POST /v1/exchange-accounts': async (body: CreateExchangeAccountDto) => {
    await delay(300)
    if (!body.apiKey?.trim()) throw new Error('请输入 API Key')
    if (!body.apiSecret?.trim()) throw new Error('请输入 API Secret')
    return createExchangeAccount(body)
  },
  'GET /v1/positions': async (_body, params) => {
    await delay(300)
    return getPositions(params)
  },
  'GET /v1/orders': async (_body, params) => {
    await delay(300)
    return getOrders(params)
  },
  'GET /v1/trades': async (_body, params) => {
    await delay(300)
    return getTrades(params)
  },
  'GET /v1/trading-agents': async () => {
    await delay(300)
    return getAgentList()
  },
  'GET /v1/news-intelligence-agents': async () => {
    await delay(200)
    return getNewsIntelList()
  },
  'POST /v1/news-intelligence-agents': async (body) => {
    await delay(300)
    return createNewsIntelAgent(body)
  },
  'POST /v1/trading-agents': async (body: CreateAgentDto) => {
    await delay(300)
    if (!body?.name?.trim()) throw new Error('请输入 Agent 名称')
    return createAgent(body)
  },
  'GET /v1/market/symbols': async (_body, params) => {
    await delay(200)
    return getMarketSymbols(params)
  },
  'GET /v1/market/kline': async (_body, params) => {
    await delay(250)
    return getMarketKline(params)
  },
  'GET /v1/market/indicators': async (_body, params) => {
    await delay(250)
    return getMarketIndicators(params)
  },
  'GET /v1/analytics/profit-summary': async (_body, params) => {
    await delay(250)
    return getProfitSummary(params)
  },
  'GET /v1/analytics/profit-trend': async (_body, params) => {
    await delay(250)
    return getProfitTrend(params)
  },
  'GET /v1/analytics/profit-by-exchange': async (_body, params) => {
    await delay(250)
    return getProfitByExchange(params)
  },
  'GET /v1/analytics/profit-by-symbol': async (_body, params) => {
    await delay(250)
    return getProfitBySymbol(params)
  },
  'POST /v1/technical-analysis/analyze': async (body) => mockTechnicalAnalysis(body),
  'GET /v1/technical-analysis/analyze': async (_body, params) =>
    mockTechnicalAnalysis({
      symbol: params?.symbol,
      analysisDate: params?.analysis_date,
      timeframe: params?.timeframe,
      lookbackDays: params?.lookback_days != null ? Number(params.lookback_days) : 30,
    }),
  'GET /v1/technical-analysis/indicators': async (_body, params) => {
    await delay(300)
    return {
      success: true,
      symbol: params?.symbol || 'BTC-USDT',
      timeframe: params?.timeframe || '4h',
      klineCount: 120,
      indicators: {
        currentPrice: 65000,
        rsi14: 55.2,
        ma5: 64200,
        ma20: 63800,
      },
    }
  },
  'GET /v1/technical-analysis/supported-timeframes': async () => {
    await delay(150)
    return {
      timeframes: [
        { value: '1h', label: '1小时', okx: '1H' },
        { value: '4h', label: '4小时', okx: '4H' },
        { value: '1d', label: '1天', okx: '1D' },
      ],
    }
  },
  'GET /v1/technical-analysis/supported-indicators': async () => {
    await delay(150)
    return {
      indicators: {
        trend: { name: '趋势指标', items: [{ key: 'ma20', name: 'MA20', description: 'Mock' }] },
      },
    }
  },
  // ---------- Backtest Handlers ----------
  'GET /v1/backtest': async (_body, params) => {
    await delay(300)
    return getBacktestList(params)
  },
  'POST /v1/backtest': async (body: CreateBacktestDto) => {
    await delay(500)
    if (!body?.name?.trim()) throw new Error('请输入回测名称')
    return createBacktest(body)
  },
}

/** 带路径参数的 Mock：key 为 "METHOD /path/prefix"，url 需匹配 prefix/:id */
const mockPatternHandlers: Array<{
  method: string
  prefix: string
  handler: (body: any, id: string) => Promise<any>
}> = [
  {
    method: 'PUT',
    prefix: '/v1/users/',
    handler: async (body: MockUpdateUserPayload, id: string) => {
      await delay(300)
      return updateUser(id, body)
    },
  },
  {
    method: 'DELETE',
    prefix: '/v1/users/',
    handler: async (_body: any, id: string) => {
      await delay(300)
      deleteUser(id)
    },
  },
  {
    method: 'PUT',
    prefix: '/v1/exchange-accounts/',
    handler: async (body: UpdateExchangeAccountDto, id: string) => {
      await delay(300)
      return updateExchangeAccount(id, body)
    },
  },
  {
    method: 'DELETE',
    prefix: '/v1/exchange-accounts/',
    handler: async (_body: any, id: string) => {
      await delay(300)
      deleteExchangeAccount(id)
    },
  },
  {
    method: 'POST',
    prefix: '/v1/exchange-accounts/',
    handler: async (_body: any, id: string) => {
      // POST /v1/exchange-accounts/:id/verify
      return verifyExchangeAccount(id)
    },
  },
  {
    method: 'GET',
    prefix: '/v1/trading-agents/',
    handler: async (_body: any, id: string) => {
      await delay(200)
      const agent = getAgentById(id)
      if (!agent) throw new Error('Agent 不存在')
      return agent
    },
  },
  {
    method: 'PUT',
    prefix: '/v1/trading-agents/',
    handler: async (body: UpdateAgentDto, id: string) => {
      await delay(300)
      return updateAgent(id, body)
    },
  },
  {
    method: 'DELETE',
    prefix: '/v1/trading-agents/',
    handler: async (_body: any, id: string) => {
      await delay(300)
      deleteAgent(id)
    },
  },
  // ---------- Backtest Pattern Handlers ----------
  {
    method: 'GET',
    prefix: '/v1/backtest/',
    handler: async (_body: any, id: string) => {
      await delay(300)
      const bt = getBacktestById(id)
      if (!bt) throw new Error('回测任务不存在')
      return bt
    },
  },
  {
    method: 'DELETE',
    prefix: '/v1/backtest/',
    handler: async (_body: any, id: string) => {
      await delay(300)
      deleteBacktest(id)
    },
  },
]

/** Agent 子路径：/v1/trading-agents/:id/profit-curve|positions|orders|operations|strategy-config 或 POST :id/start|stop */
function handleAgentSubRoute(
  method: string,
  urlPath: string,
  config?: { params?: any },
  body?: any
): Promise<any> | null {
  const getMatch = urlPath.match(/^\/v1\/trading-agents\/([^/]+)\/(.+)$/)
  if (method === 'GET' && getMatch) {
    const [, id, sub] = getMatch
    if (sub === 'profit-curve') {
      return delay(200).then(() => getAgentProfitCurve(id, config?.params?.period))
    }
    if (sub === 'positions') return delay(200).then(() => getAgentPositions(id))
    if (sub === 'orders') return delay(200).then(() => getAgentOrders(id, config?.params))
    if (sub === 'operations') return delay(200).then(() => getAgentOperations(id, config?.params?.limit))
    if (sub === 'strategy-config') return delay(200).then(() => getAgentStrategyConfig(id))
  }
  if (method === 'PUT' && getMatch) {
    const [, id, sub] = getMatch
    if (sub === 'strategy-config') {
      return delay(300).then(() => updateAgentStrategyConfig(id, body?.strategyConfig))
    }
  }
  if (method === 'POST') {
    const postMatch = urlPath.match(/^\/v1\/trading-agents\/([^/]+)\/(start|stop)$/)
    if (postMatch) {
      const [, id, action] = postMatch
      return delay(400).then(() => {
        setAgentStatus(id, action === 'start' ? 'running' : 'stopped')
        return { success: true, message: action === 'start' ? '已启动' : '已停止' }
      })
    }
  }
  return null
}

/** 回测子路径处理：/v1/backtest/:id/progress|stop|kline */
function handleBacktestSubRoute(
  method: string,
  urlPath: string,
  config?: { params?: any },
): Promise<any> | null {
  const getMatch = urlPath.match(/^\/v1\/backtest\/([^/]+)\/(.+)$/)
  if (method === 'GET' && getMatch) {
    const [, id, sub] = getMatch
    if (sub === 'progress') {
      return delay(200).then(() => getBacktestProgress(id))
    }
    if (sub === 'kline') {
      return delay(300).then(() => getBacktestKline(id, config?.params))
    }
  }
  if (method === 'POST' && getMatch) {
    const [, id, sub] = getMatch
    if (sub === 'stop') {
      return delay(300).then(() => stopBacktest(id))
    }
  }
  return null
}

export function getMockResponse(
  method: string,
  url: string,
  body?: any,
  config?: { params?: any }
): Promise<any> | null {
  const methodUpper = method.toUpperCase()
  const urlPath = url.split('?')[0]
  const key = `${methodUpper} ${urlPath}`

  const exact = mockHandlers[key]
  if (exact) {
    const params = config?.params ?? {}
    return exact(body, params)
  }

  const taRec = handleTechnicalAnalysisRecords(methodUpper, urlPath)
  if (taRec) return taRec

  const agentSub = handleAgentSubRoute(methodUpper, urlPath, config, body)
  if (agentSub) return agentSub

  const newsIntelSub = handleNewsIntelligenceRoute(methodUpper, urlPath, config, body)
  if (newsIntelSub) return newsIntelSub

  // Backtest 子路径处理
  const backtestSub = handleBacktestSubRoute(methodUpper, urlPath, config)
  if (backtestSub) return backtestSub

  for (const { method: m, prefix, handler } of mockPatternHandlers) {
    if (m !== methodUpper || !urlPath.startsWith(prefix)) continue
    const id = urlPath.slice(prefix.length).split('/')[0]
    if (id) return handler(body, id)
  }

  return null
}
