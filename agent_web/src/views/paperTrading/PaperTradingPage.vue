<template>
  <div v-loading="pageLoading" class="paper-page page-content">
    <header class="page-head">
      <div>
        <div class="eyebrow"><span class="live-dot"></span> PAPER TRADING</div>
        <h1>模拟盘</h1>
        <p>让你的判断与 Agent 的策略，在同一片市场里接受检验。</p>
      </div>
      <div class="head-actions">
        <button v-if="!accounts.some(account => account.kind === 'human')" class="quiet-button" :disabled="initializingHuman" @click="initializeHumanAccount">创建我的模拟账户</button>
        <button class="quiet-button" @click="openAgentDialog">
          <el-icon><Plus /></el-icon> 添加 Agent
        </button>
        <button class="primary-button" :disabled="!activeAccount" @click="tradeDrawerVisible = true">
          <el-icon><Sort /></el-icon> 模拟交易
        </button>
      </div>
    </header>

    <section class="hero-card">
      <div class="hero-top">
        <div class="portfolio-copy">
          <span class="section-kicker">组合总资产</span>
          <div class="portfolio-value">¥ {{ money(summary.totalEquity) }}</div>
          <div class="portfolio-change">
            <span :class="summary.totalReturnRate >= 0 ? 'positive' : 'negative'"><el-icon><TopRight /></el-icon> {{ percent(summary.totalReturnRate) }}</span>
            <span>{{ activeRange === 'ALL' ? '全部' : `近 ${activeRange.replace('D', ' 天')}` }} · {{ signedMoney(summary.totalPnl) }}</span>
          </div>
        </div>
        <div class="range-switch" aria-label="收益时间范围">
          <button
            v-for="range in ranges"
            :key="range"
            :class="{ active: activeRange === range }"
            @click="activeRange = range"
          >{{ range }}</button>
        </div>
      </div>

      <div class="comparison-head">
        <div>
          <strong>账户收益率对比</strong>
          <span>统一以区间起点归零，比较真实策略表现</span>
        </div>
        <div class="chart-legend" aria-label="账户曲线图例">
          <button
            v-for="series in comparisonSeries"
            :key="series.id"
            :class="{ hidden: !visibleSeries.includes(series.id) }"
            @click="toggleSeries(series.id)"
          >
            <i :style="{ background: series.color }"></i>
            <span>{{ series.name }}</span>
            <b :class="series.return.startsWith('+') ? 'positive' : 'negative'">{{ series.return }}</b>
          </button>
        </div>
      </div>

      <div class="chart-wrap">
        <div class="chart-y-axis"><span v-for="label in chartYAxisLabels" :key="label">{{ label }}</span></div>
        <svg viewBox="0 0 1000 220" preserveAspectRatio="none" role="img" aria-label="各账户收益率对比曲线">
          <line v-for="y in [30, 80, 130, 180]" :key="y" x1="44" :y1="y" x2="1000" :y2="y" class="grid-line" :class="{ baseline: y === 180 }" />
          <g v-for="series in activeComparisonSeries" :key="series.id">
            <path :d="series.path" class="series-line" :style="{ stroke: series.color }" />
            <circle cx="1000" :cy="series.end" r="4" class="series-point" :style="{ stroke: series.color }" />
          </g>
        </svg>
        <div class="chart-labels"><span v-for="(label, index) in chartXAxisLabels" :key="`${label}-${index}`">{{ label }}</span></div>
        <div v-if="!comparisonSeries.length" class="chart-empty">暂无收益数据</div>
      </div>

      <div class="hero-stats">
        <div><span>今日已实现收益</span><strong :class="summary.todayPnl >= 0 ? 'positive' : 'negative'">{{ signedMoney(summary.todayPnl) }}</strong></div>
        <div><span>账户最大回撤</span><strong>{{ summary.maxDrawdown.toFixed(2) }}%</strong></div>
        <div><span>运行账户</span><strong>{{ summary.runningAccounts }} <small>/ {{ summary.totalAccounts }}</small></strong></div>
        <div><span>组合胜率</span><strong>{{ summary.winRate == null ? '--' : `${summary.winRate.toFixed(1)}%` }}</strong></div>
      </div>
    </section>

    <section class="account-section">
      <div class="section-head">
        <div>
          <h2>策略账户</h2>
          <p>一个属于你，其余交给不同风格的 Agent。</p>
        </div>
        <button class="text-button" @click="showAllAccounts = !showAllAccounts">
          {{ showAllAccounts ? '收起' : '查看全部' }} <el-icon><ArrowRight /></el-icon>
        </button>
      </div>

      <div class="account-grid">
        <article
          v-for="account in visibleAccounts"
          :key="account.id"
          class="account-card"
          :class="{ selected: selectedAccount === account.id }"
          @click="selectAccount(account.id)"
        >
          <div class="account-top">
            <div class="identity">
            <div class="avatar" :class="account.kind">{{ account.initial }}</div>
              <div>
                <div class="account-name">
                  {{ account.name }}
                  <span v-if="account.kind === 'human'" class="you-badge">你</span>
                </div>
                <span class="strategy">{{ account.strategy }}</span>
              </div>
            </div>
            <span class="status" :class="account.status"><i></i>{{ statusLabel(account.status) }}</span>
          </div>
          <div class="account-value">¥ {{ account.value }}</div>
          <div class="account-meta">
            <span>累计收益</span>
            <strong :class="account.return.startsWith('+') ? 'positive' : 'negative'">{{ account.return }}</strong>
          </div>
          <div class="sparkline">
            <svg viewBox="0 0 240 42" preserveAspectRatio="none">
              <path :d="account.spark" :class="account.return.startsWith('+') ? 'spark-up' : 'spark-down'" />
            </svg>
          </div>
          <div class="account-footer">
            <span>{{ account.positions }} 个持仓</span>
            <span>胜率 {{ account.winRate }}</span>
          </div>
        </article>

        <button class="add-card" @click="openAgentDialog">
          <span class="add-icon"><el-icon><Plus /></el-icon></span>
          <strong>添加 Agent 账户</strong>
          <small>给新策略一笔独立的模拟资金</small>
        </button>
      </div>
    </section>

    <section class="bottom-grid">
      <div class="panel positions-panel">
        <div class="panel-head">
          <div>
            <span class="section-kicker">当前焦点</span>
            <h3>{{ activeAccount?.name }} · 账户明细</h3>
          </div>
          <div class="detail-toolbar">
            <div class="detail-tabs" role="tablist" aria-label="账户明细类型">
              <button :class="{ active: detailTab === 'positions' }" @click="detailTab = 'positions'">持仓 <span>{{ positions.length }}</span></button>
              <button :class="{ active: detailTab === 'decisions' }" @click="detailTab = 'decisions'">决策记录 <span>{{ decisions.length }}</span></button>
              <button :class="{ active: detailTab === 'trades' }" @click="detailTab = 'trades'">模拟交易 <span>{{ trades.length }}</span></button>
            </div>
            <div v-if="activeAccount?.kind !== 'human'" class="account-actions">
              <button class="account-action" @click="toggleActiveAccount">
                <el-icon><VideoPlay v-if="activeAccount?.status === 'paused'" /><VideoPause v-else /></el-icon>
                {{ activeAccount?.status === 'paused' ? '继续' : '暂停' }}
              </button>
              <button class="account-action danger" @click="removeActiveAccount">
                <el-icon><Delete /></el-icon> 删除
              </button>
            </div>
          </div>
        </div>
        <div v-if="detailTab === 'positions'" class="position-list">
          <div v-if="detailLoading" class="detail-empty">正在读取账户数据…</div>
          <div v-else-if="positions.length === 0" class="detail-empty">暂无持仓</div>
          <div v-for="position in positions" v-else :key="position.symbol" class="position-row">
            <div class="asset-icon" :class="position.theme">{{ position.symbol.slice(0, 1) }}</div>
            <div class="position-asset"><strong>{{ position.symbol }}</strong><span>{{ position.name }}</span></div>
            <div class="position-price"><strong>${{ position.price }}</strong><span>现价</span></div>
            <div class="position-pnl" :class="position.pnl.startsWith('+') ? 'positive' : 'negative'">
              <strong>{{ position.pnl }}</strong><span>浮动盈亏</span>
            </div>
          </div>
        </div>

        <div v-else-if="detailTab === 'decisions'" class="decision-list">
          <div v-if="activeAccount?.kind === 'human'" class="context-note">
            自主账户没有 Agent 推理链，这里记录你的下单选择与当时行情快照。
          </div>
          <div v-if="detailLoading" class="detail-empty">正在读取决策记录…</div>
          <div v-else-if="decisions.length === 0" class="detail-empty">暂无决策记录</div>
          <article
            v-for="decision in decisions"
            v-else
            :key="decision.id"
            class="decision-row"
            :class="{ expanded: expandedDecisionId === decision.id }"
            @click="expandedDecisionId = expandedDecisionId === decision.id ? '' : decision.id"
          >
            <div class="decision-time"><strong>{{ decision.time }}</strong><span>{{ decision.date }}</span></div>
            <span class="decision-action" :class="decision.tone">{{ decision.action }}</span>
            <div class="decision-main">
              <strong>{{ decision.symbol }} · {{ decision.title }}</strong>
              <p>{{ decision.summary }}</p>
              <div v-if="expandedDecisionId === decision.id" class="decision-detail">
                <div><span>决策依据</span><p>{{ decision.reasoning }}</p></div>
                <div class="decision-metrics"><span>参考价格 <b>${{ decision.price }}</b></span><span>置信度 <b>{{ decision.confidence }}</b></span><span>执行结果 <b>{{ decision.result }}</b></span></div>
              </div>
            </div>
            <el-icon class="row-arrow"><ArrowDown /></el-icon>
          </article>
        </div>

        <div v-else class="trade-log">
          <div v-if="detailLoading" class="detail-empty">正在读取成交记录…</div>
          <div v-else-if="trades.length === 0" class="detail-empty">暂无模拟成交</div>
          <template v-else>
          <div class="log-head"><span>时间 / 标的</span><span>动作</span><span>成交价</span><span>数量</span><span>盈亏</span></div>
          <div v-for="trade in trades" :key="trade.id" class="trade-row">
            <div><strong>{{ trade.symbol }}</strong><span>{{ trade.time }}</span></div>
            <span class="trade-side" :class="trade.side === '买入' ? 'buy' : 'sell'">{{ trade.side }}</span>
            <strong>${{ trade.price }}</strong>
            <span>{{ trade.quantity }}</span>
            <strong :class="trade.pnl.startsWith('+') ? 'positive' : trade.pnl === '—' ? '' : 'negative'">{{ trade.pnl }}</strong>
          </div>
          <div class="log-foot"><span>仅展示最近记录</span><button>查看完整交易记录 <el-icon><ArrowRight /></el-icon></button></div>
          </template>
        </div>
      </div>

      <div class="panel activity-panel">
        <div class="panel-head"><h3>最近动态</h3><span class="subtle">实时</span></div>
        <div class="activity-list">
          <div v-if="activities.length === 0" class="detail-empty">暂无账户动态</div>
          <div v-for="event in activities" :key="event.time + event.title" class="activity-item">
            <span class="activity-mark" :class="event.type"><el-icon><component :is="event.icon" /></el-icon></span>
            <div><strong>{{ event.title }}</strong><p>{{ event.detail }}</p></div>
            <time>{{ event.time }}</time>
          </div>
        </div>
      </div>
    </section>

    <el-drawer v-model="tradeDrawerVisible" title="模拟交易" size="420px" class="trade-drawer">
      <div class="trade-account">
        <span>使用账户</span>
        <strong>{{ activeAccount?.name }}</strong>
      </div>
      <div class="trade-tabs">
        <button :class="{ active: tradeSide === 'buy' }" @click="tradeSide = 'buy'">买入</button>
        <button :class="{ active: tradeSide === 'sell' }" @click="tradeSide = 'sell'">卖出</button>
      </div>
      <label class="field-label">交易标的</label>
      <el-select v-model="tradeSymbol" size="large" style="width: 100%">
        <el-option
          v-for="symbol in tradeSymbols"
          :key="symbol.symbol"
          :label="`${symbol.baseAsset} / ${symbol.quoteAsset}`"
          :value="`${symbol.baseAsset}/${symbol.quoteAsset}`"
        />
      </el-select>
      <div class="market-price"><span>模拟成交价</span><strong>${{ money(currentTradePrice) }}</strong></div>
      <label class="field-label">交易金额</label>
      <el-input v-model="tradeAmount" size="large" placeholder="0.00"><template #prefix>¥</template></el-input>
      <div class="amount-presets">
        <button v-for="amount in ['1,000', '5,000', '10,000', '全部']" :key="amount" @click="tradeAmount = amount === '全部' ? '86,420' : amount">{{ amount }}</button>
      </div>
      <div class="drawer-summary"><span>预计成交</span><strong>≈ {{ estimatedQuantity }} {{ tradeSymbol.split('/')[0] }}</strong></div>
      <button class="confirm-trade" :class="tradeSide" :disabled="submittingTrade" @click="submitPaperTrade">{{ submittingTrade ? '提交中…' : `确认${tradeSide === 'buy' ? '买入' : '卖出'}` }}</button>
      <p class="drawer-note">仅使用虚拟资金，不会产生真实资产交易。</p>
    </el-drawer>

    <el-dialog v-model="agentDialogVisible" title="添加已有 Agent" width="520px">
      <div class="dialog-copy">从「Agent 交易」中选择一个已有 Agent，为它开设独立模拟账户。这里不会创建新的 Agent。</div>
      <div class="picker-head">
        <label class="field-label">选择 Agent</label>
        <router-link to="/agents" class="manage-link" @click="agentDialogVisible = false">管理 Agent <el-icon><ArrowRight /></el-icon></router-link>
      </div>
      <div v-loading="loadingSourceAgents" class="agent-picker">
        <button
          v-for="agent in sourceAgents"
          :key="agent.id"
          class="agent-option"
          :class="{ selected: selectedSourceAgentId === agent.id, disabled: isAgentBound(agent.id) }"
          :disabled="isAgentBound(agent.id)"
          @click="selectedSourceAgentId = agent.id"
        >
          <span class="option-avatar">{{ agent.name.slice(0, 1).toUpperCase() }}</span>
          <span class="option-body">
            <strong>{{ agent.name }}</strong>
            <small>{{ agent.llmModelName || '未指定模型' }} · {{ strategyLabel(agent) }}</small>
          </span>
          <span v-if="isAgentBound(agent.id)" class="bound-badge">已添加</span>
          <span v-else class="radio-dot"><i></i></span>
        </button>
        <div v-if="!loadingSourceAgents && sourceAgents.length === 0" class="picker-empty">
          暂无可用 Agent，请先前往 Agent 交易创建。
        </div>
      </div>
      <label class="field-label dialog-field">模拟初始资金</label>
      <el-input v-model="newAgentCapital"><template #prefix>¥</template></el-input>
      <template #footer>
        <el-button @click="agentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="bindingAgent" :disabled="!selectedSourceAgentId" @click="bindExistingAgent">添加到模拟盘</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Sort, TopRight, ArrowRight, ArrowDown, TrendCharts, Bell, VideoPause, VideoPlay, Delete } from '@element-plus/icons-vue'
import { agentsApi, type AgentListItem } from '@/api/agents'
import { marketApi, type MarketSymbolItem } from '@/api/market'
import {
  paperTradingApi,
  type PaperActivity,
  type PaperAccountCurve,
  type PaperDecision,
  type PaperPosition,
  type PaperTrade,
  type PaperTradingSummary,
} from '@/api/paperTrading'

type AccountStatus = 'running' | 'paused'
interface Account {
  id: string
  name: string
  initial: string
  kind: 'human' | 'agent' | 'agent-alt'
  strategy: string
  status: AccountStatus
  value: string
  return: string
  positions: number
  winRate: string
  spark: string
  sourceAgentId?: string
}

interface PositionView { symbol: string; name: string; price: string; pnl: string; theme: string }
interface DecisionView { id: string; time: string; date: string; action: string; tone: string; symbol: string; title: string; summary: string; reasoning: string; price: string; confidence: string; result: string }
interface TradeView { id: string; time: string; symbol: string; side: string; price: string; quantity: string; pnl: string }
interface ActivityView { icon: Component; type: string; title: string; detail: string; time: string }

const ranges = ['7D', '30D', '90D', 'ALL']
const activeRange = ref('30D')
const selectedAccount = ref('')
const showAllAccounts = ref(false)
const tradeDrawerVisible = ref(false)
const agentDialogVisible = ref(false)
const tradeSide = ref<'buy' | 'sell'>('buy')
const tradeSymbol = ref('')
const tradeAmount = ref('5,000')
const newAgentCapital = ref('200,000')
const selectedSourceAgentId = ref('')
const sourceAgents = ref<AgentListItem[]>([])
const tradeSymbols = ref<MarketSymbolItem[]>([])
const loadingSourceAgents = ref(false)
const detailTab = ref<'positions' | 'decisions' | 'trades'>('positions')
const expandedDecisionId = ref('')
const visibleSeries = ref<string[]>([])
const backendCurves = ref<PaperAccountCurve[]>([])
const detailLoading = ref(false)
const submittingTrade = ref(false)
const bindingAgent = ref(false)
const pageLoading = ref(false)
const initializingHuman = ref(false)
async function initializeHumanAccount() {
  initializingHuman.value = true
  try { await paperTradingApi.initializeHumanAccount(); await loadDashboard(); ElMessage.success('模拟账户已创建') }
  finally { initializingHuman.value = false }
}
const summary = ref<PaperTradingSummary>({
  totalEquity: 0, totalReturnRate: 0, totalPnl: 0,
  todayPnl: 0, maxDrawdown: 0, runningAccounts: 0, totalAccounts: 0, winRate: null,
})

const accounts = ref<Account[]>([])

const visibleAccounts = computed(() => showAllAccounts.value ? accounts.value : accounts.value.slice(0, 4))
const activeAccount = computed(() => accounts.value.find(item => item.id === selectedAccount.value))
const seriesColors = ['#172554', '#2563eb', '#7c3aed', '#ef4444', '#0891b2', '#d97706']
const chartScale = computed(() => {
  const values = backendCurves.value.flatMap(curve => curve.points.map(point => Number(point.value) || 0))
  const minimum = Math.min(0, ...values)
  const maximum = Math.max(0, ...values)
  const span = Math.max(maximum - minimum, 1)
  const padding = span * 0.12
  return { min: minimum - padding, max: maximum + padding }
})
const chartYAxisLabels = computed(() => Array.from({ length: 4 }, (_, index) => {
  const value = chartScale.value.max - ((chartScale.value.max - chartScale.value.min) * index / 3)
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}))
const chartXAxisLabels = computed(() => {
  const timestamps = backendCurves.value.flatMap(curve => curve.points
    .map(point => new Date(point.time).getTime())
    .filter(Number.isFinite))
  if (!timestamps.length) return []
  const start = Math.min(...timestamps)
  const end = Math.max(...timestamps)
  return Array.from({ length: 5 }, (_, index) => {
    const date = new Date(start + ((end - start) * index / 4))
    return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  })
})
function curvePath(points: { value: number }[]) {
  const values = points.length ? points : [{ value: 0 }]
  const span = Math.max(chartScale.value.max - chartScale.value.min, 1)
  const coordinates = values.map((point, index) => {
    const x = values.length === 1 ? 44 : 44 + (956 * index / (values.length - 1))
    const y = 30 + ((chartScale.value.max - point.value) / span * 150)
    return { x, y }
  })
  if (coordinates.length === 1) coordinates.push({ x: 1000, y: coordinates[0].y })
  return {
    path: coordinates.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' '),
    end: coordinates[coordinates.length - 1].y,
  }
}
function sparkPath(points: { value: number }[]) {
  if (!points.length) return 'M0 21 L240 21'
  const values = points.map(point => Number(point.value) || 0)
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const span = Math.max(maximum - minimum, 1)
  const coordinates = values.map((value, index) => ({
    x: values.length === 1 ? 0 : 240 * index / (values.length - 1),
    y: 38 - ((value - minimum) / span * 34),
  }))
  if (coordinates.length === 1) coordinates.push({ x: 240, y: coordinates[0].y })
  return coordinates.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ')
}
const comparisonSeries = computed(() => {
  return backendCurves.value.map((curve, index) => {
    const account = accounts.value.find(item => item.id === curve.accountId)
    return {
      id: curve.accountId,
      name: curve.name,
      color: seriesColors[index % seriesColors.length],
      return: account?.return || '+0.00%',
      ...curvePath(curve.points),
    }
  })
})
const activeComparisonSeries = computed(() => comparisonSeries.value
  .filter(series => visibleSeries.value.includes(series.id)))
const positions = ref<PositionView[]>([])
const decisions = ref<DecisionView[]>([])
const trades = ref<TradeView[]>([])
const activities = ref<ActivityView[]>([])
const liveTradePrice = ref(0)
const currentTradePrice = computed(() => liveTradePrice.value)
const estimatedQuantity = computed(() => {
  const amount = Number(tradeAmount.value.replace(/,/g, '')) || 0
  return currentTradePrice.value ? (amount / currentTradePrice.value).toFixed(6) : '0.000000'
})

function money(value: number) {
  return Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function percent(value: number) {
  return `${value >= 0 ? '+' : ''}${Number(value || 0).toFixed(2)}%`
}

function signedMoney(value: number) {
  return `${value >= 0 ? '+¥ ' : '-¥ '}${money(Math.abs(value))}`
}

function statusLabel(status: AccountStatus) {
  return status === 'running' ? '运行中' : '已暂停'
}

function toggleSeries(id: string) {
  if (visibleSeries.value.includes(id)) {
    if (visibleSeries.value.length === 1) return
    visibleSeries.value = visibleSeries.value.filter(item => item !== id)
  } else {
    visibleSeries.value = [...visibleSeries.value, id]
  }
}

async function submitPaperTrade() {
  const account = activeAccount.value
  const amount = Number(tradeAmount.value.replace(/,/g, ''))
  if (!account || !amount || amount <= 0) {
    ElMessage.warning('请输入有效的交易金额')
    return
  }
  if (!currentTradePrice.value) {
    ElMessage.warning('暂未获取到市场价格，请稍后重试')
    return
  }
  submittingTrade.value = true
  try {
    await paperTradingApi.createTrade(account.id, {
      symbol: tradeSymbol.value,
      side: tradeSide.value,
      amount,
      price: currentTradePrice.value,
    })
    await loadDashboard()
    await loadAccountDetails(account.id)
    tradeDrawerVisible.value = false
    ElMessage.success(`模拟${tradeSide.value === 'buy' ? '买入' : '卖出'}已成交`)
  } catch {
    // 请求层已展示错误消息。
  } finally {
    submittingTrade.value = false
  }
}

async function toggleActiveAccount() {
  const account = activeAccount.value
  if (!account || account.kind === 'human') return
  const nextStatus = account.status === 'running' ? 'paused' : 'running'
  try {
    if (nextStatus === 'paused') await paperTradingApi.pauseAccount(account.id)
    else await paperTradingApi.resumeAccount(account.id)
    account.status = nextStatus
    ElMessage.success(nextStatus === 'paused' ? `${account.name} 已暂停模拟交易` : `${account.name} 已继续运行`)
  } catch {
    // 请求层已展示错误消息。
  }
}

async function removeActiveAccount() {
  const account = activeAccount.value
  if (!account || account.kind === 'human') return
  try {
    await ElMessageBox.confirm(
      `将删除 ${account.name} 的模拟账户、持仓与历史记录。Agent 交易中的原 Agent 不会被删除。`,
      '删除模拟账户',
      { confirmButtonText: '删除模拟账户', cancelButtonText: '取消', type: 'warning' },
    )
    await paperTradingApi.deleteAccount(account.id)
    accounts.value = accounts.value.filter(item => item.id !== account.id)
    backendCurves.value = backendCurves.value.filter(item => item.accountId !== account.id)
    visibleSeries.value = visibleSeries.value.filter(id => id !== account.id)
    selectedAccount.value = accounts.value.find(item => item.kind === 'human')?.id || accounts.value[0]?.id || ''
    detailTab.value = 'positions'
    expandedDecisionId.value = ''
    await loadDashboard()
    if (selectedAccount.value) await loadAccountDetails(selectedAccount.value)
    ElMessage.success('模拟账户已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败')
  }
}

function isAgentBound(agentId: string) {
  return accounts.value.some(account => account.sourceAgentId === agentId)
}

function strategyLabel(agent: AgentListItem) {
  const mode = agent.strategyConfig?.marketMode
  if (mode === 'trend_only') return '趋势跟随'
  if (mode === 'range_only') return '均值回归'
  return '自适应策略'
}

function openAgentDialog() {
  const firstAvailable = sourceAgents.value.find(agent => !isAgentBound(agent.id))
  selectedSourceAgentId.value = firstAvailable?.id || ''
  agentDialogVisible.value = true
}

async function bindExistingAgent() {
  const source = sourceAgents.value.find(agent => agent.id === selectedSourceAgentId.value)
  if (!source || isAgentBound(source.id)) {
    ElMessage.warning('请选择一个尚未添加的 Agent')
    return
  }
  bindingAgent.value = true
  try {
    const result = await paperTradingApi.createAccount(
      source.id,
      Number(newAgentCapital.value.replace(/,/g, '')) || 200000,
    )
    const id = result.id
    await loadDashboard()
    selectedAccount.value = id
    visibleSeries.value = Array.from(new Set([...visibleSeries.value, id]))
    showAllAccounts.value = true
    agentDialogVisible.value = false
    selectedSourceAgentId.value = ''
    await loadAccountDetails(id)
    ElMessage.success(`${source.name} 已添加到模拟盘`)
  } catch {
    // 请求层已展示错误消息。
  } finally {
    bindingAgent.value = false
  }
}

function mapPosition(item: PaperPosition) {
  const asset = item.symbol.split('-')[0]
  const names: Record<string, string> = { BTC: 'Bitcoin', ETH: 'Ethereum', SOL: 'Solana' }
  const themes: Record<string, string> = { BTC: 'orange', ETH: 'blue', SOL: 'violet' }
  return {
    symbol: asset, name: names[asset] || item.symbol,
    price: money(item.lastPrice), pnl: signedMoney(item.unrealizedPnl), theme: themes[asset] || 'blue',
  }
}

function mapDecision(item: PaperDecision) {
  const date = new Date(item.createdAt)
  const actionMap: Record<string, string> = { buy: '开多', sell: '减仓', hold: '观望', open_long: '开多', close_long: '平多' }
  const toneMap: Record<string, string> = { buy: 'buy', open_long: 'buy', sell: 'sell', close_long: 'sell', hold: 'hold' }
  return {
    id: item.id, time: date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    date: date.toLocaleDateString('zh-CN'), action: actionMap[item.action] || item.action,
    tone: toneMap[item.action] || 'hold', symbol: item.symbol.replace('-', ' / '),
    title: item.title || '策略决策', summary: item.summary || '暂无摘要',
    reasoning: item.reasoning || '暂无详细依据', price: money(item.referencePrice || 0),
    confidence: item.confidence == null ? '--' : `${item.confidence.toFixed(0)}%`, result: item.result || '已记录',
  }
}

function mapTrade(item: PaperTrade) {
  const date = new Date(item.executedAt)
  return {
    id: item.id, time: date.toLocaleString('zh-CN'), symbol: item.symbol.replace('-', ' / '),
    side: item.side === 'buy' ? '买入' : '卖出', price: money(item.price),
    quantity: `${item.quantity.toFixed(6)} ${item.symbol.split('-')[0]}`,
    pnl: item.side === 'buy' ? '—' : signedMoney(item.realizedPnl),
  }
}

function mapActivity(item: PaperActivity): ActivityView {
  const date = new Date(item.occurredAt)
  return {
    icon: item.type === 'trade' ? TrendCharts : Bell,
    type: item.type === 'trade' ? 'trade' : 'alert',
    title: item.title,
    detail: item.detail,
    time: Number.isNaN(date.getTime())
      ? '--'
      : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
  }
}

async function loadAccountDetails(accountId: string) {
  if (!accountId) return
  detailLoading.value = true
  try {
    const [positionResult, decisionResult, tradeResult] = await Promise.all([
      paperTradingApi.getPositions(accountId),
      paperTradingApi.getDecisions(accountId),
      paperTradingApi.getTrades(accountId),
    ])
    positions.value = positionResult.list.map(mapPosition)
    decisions.value = decisionResult.list.map(mapDecision)
    trades.value = tradeResult.list.map(mapTrade)
  } catch {
    positions.value = []
    decisions.value = []
    trades.value = []
  } finally {
    detailLoading.value = false
  }
}

async function selectAccount(accountId: string) {
  selectedAccount.value = accountId
  expandedDecisionId.value = ''
  await loadAccountDetails(accountId)
}

async function loadDashboard() {
  pageLoading.value = true
  try {
    const result = await paperTradingApi.getDashboard(activeRange.value)
    summary.value = result.summary
    backendCurves.value = result.curves
    accounts.value = result.accounts.map((account, index) => {
      const curve = result.curves.find(item => item.accountId === account.id)
      return {
        id: account.id, sourceAgentId: account.sourceAgentId || undefined,
        name: account.name, initial: account.name.slice(0, 1).toUpperCase(),
        kind: account.kind === 'human' ? 'human' : (index % 2 ? 'agent' : 'agent-alt'),
        strategy: account.strategy, status: account.status, value: money(account.equity),
        return: percent(account.returnRate), positions: account.positionCount,
        winRate: account.winRate == null ? '--' : `${account.winRate.toFixed(0)}%`,
        spark: sparkPath(curve?.points || []),
      }
    })
    activities.value = (result.activities || []).map(mapActivity)
    visibleSeries.value = result.accounts.map(account => account.id)
    if (!accounts.value.some(account => account.id === selectedAccount.value)) {
      selectedAccount.value = accounts.value.find(account => account.kind === 'human')?.id || accounts.value[0]?.id || ''
    }
  } catch {
    summary.value = { totalEquity: 0, totalReturnRate: 0, totalPnl: 0, todayPnl: 0, maxDrawdown: 0, runningAccounts: 0, totalAccounts: 0, winRate: null }
    accounts.value = []
    backendCurves.value = []
    activities.value = []
  } finally {
    pageLoading.value = false
  }
}

async function loadTradePrice() {
  liveTradePrice.value = 0
  try {
    const result = await marketApi.getIndicators({ symbol: tradeSymbol.value.replace('/', '-'), interval: '15m' })
    liveTradePrice.value = Number(result.latestPrice) || 0
  } catch {
    liveTradePrice.value = 0
  }
}

async function loadSourceAgents() {
  loadingSourceAgents.value = true
  try {
    const result = await agentsApi.getList()
    sourceAgents.value = result.list || []
  } catch {
    sourceAgents.value = []
  } finally {
    loadingSourceAgents.value = false
  }
}

async function loadTradeSymbols() {
  try {
    const result = await marketApi.searchSymbols()
    tradeSymbols.value = result.list || []
    if (!tradeSymbol.value && tradeSymbols.value.length) {
      const first = tradeSymbols.value[0]
      tradeSymbol.value = `${first.baseAsset}/${first.quoteAsset}`
    }
  } catch {
    tradeSymbols.value = []
    tradeSymbol.value = ''
  }
}

watch(activeRange, loadDashboard)
watch(tradeSymbol, loadTradePrice)
watch(tradeDrawerVisible, visible => { if (visible) loadTradePrice() })
onMounted(async () => {
  await Promise.all([loadSourceAgents(), loadTradeSymbols(), loadDashboard()])
  if (selectedAccount.value) await loadAccountDetails(selectedAccount.value)
})
</script>

<style scoped>
.paper-page { max-width: 1480px; margin: 0 auto; padding: 34px 38px 64px; }
.page-head, .hero-top, .section-head, .panel-head, .account-top, .identity, .account-meta, .account-footer, .position-row, .activity-item, .head-actions { display: flex; align-items: center; }
.page-head { justify-content: space-between; gap: 32px; margin-bottom: 26px; }
.eyebrow, .section-kicker { color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: .14em; }
.eyebrow { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 4px #dcfce7; }
.page-head h1 { margin: 0; color: #0f172a; font-size: 31px; font-weight: 720; letter-spacing: -.04em; }
.page-head p { margin: 7px 0 0; color: #64748b; font-size: 13px; }
.head-actions { gap: 10px; }
.quiet-button, .primary-button, .text-button, .icon-button, .range-switch button, .trade-tabs button, .amount-presets button, .confirm-trade { border: 0; cursor: pointer; font: inherit; }
.quiet-button, .primary-button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px; padding: 0 16px; border-radius: 10px; font-size: 13px; font-weight: 650; transition: .18s ease; }
.quiet-button { color: #334155; background: #fff; border: 1px solid #dfe5ec; }
.quiet-button:hover { border-color: #aebdce; background: #f8fafc; }
.primary-button { color: #fff; background: #172554; box-shadow: 0 6px 16px rgba(23,37,84,.16); }
.primary-button:hover { background: #1e3a8a; transform: translateY(-1px); }
.primary-button:disabled { cursor: not-allowed; opacity: .45; transform: none; }

.hero-card { padding: 28px 30px 22px; background: #fff; border: 1px solid #e3e8ef; border-radius: 18px; box-shadow: 0 4px 18px rgba(15,23,42,.035); }
.hero-top { justify-content: space-between; gap: 20px; }
.portfolio-value { margin-top: 7px; color: #0f172a; font-size: 36px; font-weight: 720; letter-spacing: -.045em; font-variant-numeric: tabular-nums; }
.portfolio-change { display: flex; align-items: center; gap: 10px; margin-top: 7px; color: #64748b; font-size: 12px; }
.positive { color: #15803d !important; }
.negative { color: #dc2626 !important; }
.portfolio-change .positive { display: inline-flex; align-items: center; gap: 3px; font-weight: 700; }
.range-switch { display: flex; padding: 3px; border-radius: 9px; background: #f1f5f9; }
.range-switch button { min-width: 45px; padding: 6px 8px; color: #64748b; background: transparent; border-radius: 7px; font-size: 11px; font-weight: 650; }
.range-switch button.active { color: #0f172a; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,.1); }
.comparison-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin-top: 27px; }
.comparison-head > div:first-child { display: flex; flex-direction: column; gap: 3px; }
.comparison-head strong { color: #1e293b; font-size: 12px; font-weight: 680; }
.comparison-head span { color: #94a3b8; font-size: 9px; }
.chart-legend { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; }
.chart-legend button { display: inline-flex; align-items: center; gap: 5px; padding: 5px 7px; color: #475569; background: #fff; border: 1px solid #e8edf3; border-radius: 7px; cursor: pointer; transition: .16s ease; }
.chart-legend button:hover { border-color: #cbd5e1; }.chart-legend button.hidden { opacity: .38; filter: grayscale(1); }
.chart-legend i { width: 7px; height: 7px; border-radius: 50%; }.chart-legend span { color: #475569; font-size: 9px; }.chart-legend b { font-size: 9px; font-weight: 680; }
.chart-wrap { position: relative; height: 242px; margin-top: 4px; }
.chart-wrap svg { width: 100%; height: 210px; overflow: visible; }
.grid-line { stroke: #edf1f5; stroke-width: 1; stroke-dasharray: 3 5; }.grid-line.baseline { stroke: #cbd5e1; stroke-dasharray: 0; }
.series-line { fill: none; stroke-width: 2; vector-effect: non-scaling-stroke; }
.series-point { fill: #fff; stroke-width: 2.5; vector-effect: non-scaling-stroke; }
.chart-y-axis { position: absolute; top: 21px; bottom: 45px; left: 0; display: flex; flex-direction: column; justify-content: space-between; color: #94a3b8; font-size: 9px; }
.chart-labels { display: flex; justify-content: space-between; padding-left: 42px; color: #94a3b8; font-size: 10px; }
.chart-empty { position: absolute; inset: 0 0 28px 42px; display: grid; place-items: center; color: #94a3b8; font-size: 12px; }
.hero-stats { display: grid; grid-template-columns: repeat(4, 1fr); padding-top: 20px; border-top: 1px solid #edf1f5; }
.hero-stats > div { padding: 0 22px; border-right: 1px solid #edf1f5; }
.hero-stats > div:first-child { padding-left: 0; }
.hero-stats > div:last-child { border-right: 0; }
.hero-stats span { display: block; margin-bottom: 5px; color: #64748b; font-size: 11px; }
.hero-stats strong { color: #0f172a; font-size: 17px; font-weight: 680; font-variant-numeric: tabular-nums; }
.hero-stats small { color: #94a3b8; font-size: 12px; font-weight: 500; }

.account-section { margin-top: 34px; }
.section-head { justify-content: space-between; margin-bottom: 15px; }
.section-head h2 { margin: 0; color: #0f172a; font-size: 18px; letter-spacing: -.02em; }
.section-head p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
.text-button { display: inline-flex; align-items: center; gap: 4px; color: #475569; background: transparent; font-size: 12px; font-weight: 600; }
.text-button:hover { color: #2563eb; }
.account-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.account-card, .add-card { min-height: 208px; padding: 18px; background: #fff; border: 1px solid #e3e8ef; border-radius: 14px; transition: .18s ease; }
.account-card { cursor: pointer; box-shadow: 0 2px 8px rgba(15,23,42,.025); }
.account-card:hover, .account-card.selected { border-color: #9bb8f6; box-shadow: 0 8px 22px rgba(37,99,235,.08); transform: translateY(-2px); }
.account-card.selected { box-shadow: inset 0 0 0 1px #bfdbfe, 0 8px 22px rgba(37,99,235,.08); }
.account-top { justify-content: space-between; gap: 10px; }
.identity { gap: 10px; min-width: 0; }
.avatar { display: grid; place-items: center; width: 35px; height: 35px; border-radius: 10px; color: #1d4ed8; background: #eff6ff; font-size: 13px; font-weight: 750; }
.avatar.human { color: #fff; background: #172554; }
.avatar.agent-alt { color: #6d28d9; background: #f5f3ff; }
.account-name { color: #1e293b; font-size: 13px; font-weight: 680; white-space: nowrap; }
.you-badge { margin-left: 4px; padding: 1px 5px; color: #64748b; background: #f1f5f9; border-radius: 4px; font-size: 9px; }
.strategy { display: block; margin-top: 2px; color: #94a3b8; font-size: 10px; white-space: nowrap; }
.status { display: inline-flex; align-items: center; gap: 5px; color: #64748b; font-size: 9px; white-space: nowrap; }
.status i { width: 5px; height: 5px; border-radius: 50%; background: #94a3b8; }
.status.running i { background: #22c55e; }
.account-value { margin-top: 19px; color: #0f172a; font-size: 21px; font-weight: 700; letter-spacing: -.025em; font-variant-numeric: tabular-nums; }
.account-meta { justify-content: space-between; margin-top: 4px; color: #94a3b8; font-size: 10px; }
.account-meta strong { font-size: 11px; }
.sparkline { height: 42px; margin: 10px 0 7px; }
.sparkline svg { width: 100%; height: 100%; }
.sparkline path { fill: none; stroke-width: 1.7; vector-effect: non-scaling-stroke; }
.spark-up { stroke: #22c55e; }
.spark-down { stroke: #ef4444; }
.account-footer { justify-content: space-between; padding-top: 9px; border-top: 1px solid #f1f5f9; color: #64748b; font-size: 9px; }
.add-card { display: none; cursor: pointer; text-align: center; color: #64748b; border-style: dashed; }
.account-grid:has(.account-card:nth-child(5)) .add-card { display: flex; }
.add-card { flex-direction: column; align-items: center; justify-content: center; gap: 5px; }
.add-card:hover { color: #2563eb; border-color: #93c5fd; background: #f8fbff; }
.add-icon { display: grid; place-items: center; width: 34px; height: 34px; margin-bottom: 3px; border-radius: 50%; background: #eff6ff; color: #2563eb; }
.add-card strong { color: #334155; font-size: 12px; }
.add-card small { font-size: 10px; }

.bottom-grid { display: grid; grid-template-columns: 1.45fr .85fr; gap: 14px; margin-top: 28px; }
.panel { padding: 20px; background: #fff; border: 1px solid #e3e8ef; border-radius: 14px; }
.panel-head { justify-content: space-between; margin-bottom: 14px; }
.panel-head h3 { margin: 2px 0 0; color: #1e293b; font-size: 14px; }
.detail-toolbar { display: flex; align-items: center; gap: 8px; }
.detail-tabs { display: flex; gap: 3px; padding: 3px; background: #f1f5f9; border-radius: 9px; }
.detail-tabs button { padding: 6px 9px; color: #64748b; background: transparent; border: 0; border-radius: 7px; cursor: pointer; font-size: 10px; font-weight: 600; }
.detail-tabs button span { margin-left: 3px; color: #94a3b8; font-size: 9px; }
.detail-tabs button.active { color: #0f172a; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,.09); }
.account-actions { display: flex; gap: 5px; padding-left: 8px; border-left: 1px solid #e2e8f0; }
.account-action { display: inline-flex; align-items: center; gap: 4px; padding: 7px 9px; color: #475569; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; cursor: pointer; font-size: 9px; font-weight: 650; transition: .16s ease; }
.account-action:hover { color: #1d4ed8; border-color: #bfdbfe; background: #f8fbff; }
.account-action.danger { color: #b91c1c; }.account-action.danger:hover { color: #dc2626; border-color: #fecaca; background: #fef2f2; }
.position-list { display: grid; gap: 2px; }
.detail-empty { padding: 34px 12px; color: #94a3b8; text-align: center; font-size: 12px; }
.position-row { display: grid; grid-template-columns: 38px 1fr .9fr .9fr; gap: 10px; padding: 12px 8px; border-radius: 9px; }
.position-row:hover { background: #f8fafc; }
.asset-icon { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 50%; color: #fff; font-size: 11px; font-weight: 700; }
.asset-icon.orange { background: #f59e0b; }.asset-icon.blue { background: #627eea; }.asset-icon.violet { background: #7c3aed; }
.position-asset, .position-price, .position-pnl { display: flex; flex-direction: column; justify-content: center; }
.position-price, .position-pnl { text-align: right; }
.position-row strong { color: #334155; font-size: 11px; font-weight: 650; }
.position-row span { margin-top: 2px; color: #94a3b8; font-size: 9px; }
.context-note { margin-bottom: 8px; padding: 9px 11px; color: #64748b; background: #f8fafc; border-radius: 8px; font-size: 10px; }
.decision-list { display: grid; gap: 5px; }
.decision-row { display: grid; grid-template-columns: 48px 46px 1fr 18px; gap: 9px; align-items: start; padding: 11px 8px; border-radius: 9px; cursor: pointer; transition: .16s ease; }
.decision-row:hover, .decision-row.expanded { background: #f8fafc; }
.decision-time { display: flex; flex-direction: column; }
.decision-time strong { color: #334155; font-size: 10px; }.decision-time span { margin-top: 2px; color: #94a3b8; font-size: 9px; }
.decision-action { justify-self: start; padding: 3px 7px; border-radius: 999px; font-size: 9px; font-weight: 700; }
.decision-action.buy { color: #15803d; background: #f0fdf4; }.decision-action.sell { color: #dc2626; background: #fef2f2; }.decision-action.hold { color: #64748b; background: #f1f5f9; }
.decision-main strong { color: #334155; font-size: 10px; }.decision-main > p { margin: 3px 0 0; color: #64748b; font-size: 9px; line-height: 1.5; }
.row-arrow { margin-top: 2px; color: #94a3b8; font-size: 11px; transition: transform .16s ease; }.decision-row.expanded .row-arrow { transform: rotate(180deg); }
.decision-detail { margin-top: 10px; padding: 10px; border-left: 2px solid #bfdbfe; background: #fff; border-radius: 0 7px 7px 0; }
.decision-detail span { color: #94a3b8; font-size: 8px; }.decision-detail p { margin: 3px 0 8px; color: #475569; font-size: 9px; line-height: 1.6; }
.decision-metrics { display: flex; flex-wrap: wrap; gap: 16px; }.decision-metrics span { display: inline-flex; gap: 4px; }.decision-metrics b { color: #334155; font-weight: 650; }
.trade-log { overflow: hidden; }
.log-head, .trade-row { display: grid; grid-template-columns: 1.25fr .55fr .75fr .75fr .65fr; align-items: center; gap: 10px; }
.log-head { padding: 7px 8px; color: #94a3b8; background: #f8fafc; border-radius: 7px; font-size: 8px; }
.trade-row { min-height: 48px; padding: 7px 8px; border-bottom: 1px solid #f1f5f9; color: #475569; font-size: 9px; }
.trade-row > div { display: flex; flex-direction: column; }.trade-row strong { color: #334155; font-size: 10px; font-weight: 650; }.trade-row div span { margin-top: 2px; color: #94a3b8; font-size: 8px; }
.trade-side { justify-self: start; padding: 3px 7px; border-radius: 999px; font-size: 9px; font-weight: 700; }.trade-side.buy { color: #15803d; background: #f0fdf4; }.trade-side.sell { color: #dc2626; background: #fef2f2; }
.log-foot { display: flex; align-items: center; justify-content: space-between; padding: 10px 8px 0; color: #94a3b8; font-size: 8px; }.log-foot button { display: inline-flex; align-items: center; gap: 3px; color: #2563eb; background: transparent; border: 0; cursor: pointer; font-size: 9px; }
.activity-list { display: grid; gap: 1px; }
.activity-item { display: grid; grid-template-columns: 30px 1fr auto; gap: 9px; padding: 11px 4px; }
.activity-mark { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; color: #2563eb; background: #eff6ff; font-size: 13px; }
.activity-mark.human { color: #475569; background: #f1f5f9; }.activity-mark.alert { color: #7c3aed; background: #f5f3ff; }
.activity-item strong { color: #334155; font-size: 10px; font-weight: 650; }
.activity-item p { margin: 2px 0 0; color: #94a3b8; font-size: 9px; }
.activity-item time, .subtle { color: #94a3b8; font-size: 9px; }

.trade-account, .market-price, .drawer-summary { display: flex; align-items: center; justify-content: space-between; }
.trade-account { padding: 13px 14px; margin-bottom: 18px; border-radius: 10px; background: #f8fafc; color: #64748b; font-size: 12px; }
.trade-account strong { color: #1e293b; }
.trade-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; padding: 4px; margin-bottom: 22px; border-radius: 10px; background: #f1f5f9; }
.trade-tabs button { padding: 9px; color: #64748b; background: transparent; border-radius: 7px; font-weight: 650; }
.trade-tabs button.active { color: #0f172a; background: #fff; box-shadow: 0 1px 4px rgba(15,23,42,.1); }
.field-label { display: block; margin: 16px 0 7px; color: #475569; font-size: 12px; font-weight: 600; }
.market-price { margin: 12px 1px 2px; color: #64748b; font-size: 11px; }
.market-price strong { color: #0f172a; }
.amount-presets { display: grid; grid-template-columns: repeat(4,1fr); gap: 7px; margin-top: 8px; }
.amount-presets button { padding: 6px; color: #64748b; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 7px; font-size: 10px; }
.drawer-summary { margin-top: 24px; padding: 15px 0; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 12px; }
.drawer-summary strong { color: #0f172a; }
.confirm-trade { width: 100%; padding: 12px; color: #fff; background: #15803d; border-radius: 10px; font-weight: 700; }
.confirm-trade.sell { background: #dc2626; }
.drawer-note, .dialog-copy { color: #94a3b8; font-size: 10px; }
.drawer-note { margin-top: 10px; text-align: center; }.dialog-copy { margin-bottom: 12px; font-size: 12px; line-height: 1.6; }.dialog-field { margin-top: 16px; }
.picker-head { display: flex; align-items: center; justify-content: space-between; }
.picker-head .field-label { margin-top: 4px; }
.manage-link { display: inline-flex; align-items: center; gap: 3px; color: #2563eb; font-size: 11px; text-decoration: none; }
.agent-picker { display: grid; gap: 8px; min-height: 90px; max-height: 264px; padding: 2px; overflow-y: auto; }
.agent-option { display: flex; align-items: center; gap: 11px; width: 100%; padding: 12px; color: inherit; background: #fff; border: 1px solid #e2e8f0; border-radius: 11px; cursor: pointer; text-align: left; transition: .16s ease; }
.agent-option:hover:not(.disabled), .agent-option.selected { border-color: #93b4f6; background: #f8fbff; box-shadow: inset 0 0 0 1px #dbeafe; }
.agent-option.disabled { cursor: not-allowed; opacity: .56; background: #f8fafc; }
.option-avatar { display: grid; place-items: center; width: 34px; height: 34px; flex: 0 0 auto; color: #1d4ed8; background: #eff6ff; border-radius: 9px; font-size: 12px; font-weight: 750; }
.option-body { display: flex; flex: 1; min-width: 0; flex-direction: column; }
.option-body strong { color: #1e293b; font-size: 12px; font-weight: 680; }
.option-body small { margin-top: 3px; color: #94a3b8; font-size: 10px; }
.bound-badge { padding: 3px 7px; color: #64748b; background: #e2e8f0; border-radius: 999px; font-size: 9px; }
.radio-dot { display: grid; place-items: center; width: 17px; height: 17px; border: 1.5px solid #cbd5e1; border-radius: 50%; }
.agent-option.selected .radio-dot { border-color: #2563eb; }
.agent-option.selected .radio-dot i { width: 9px; height: 9px; background: #2563eb; border-radius: 50%; }
.picker-empty { padding: 26px 16px; color: #94a3b8; background: #f8fafc; border-radius: 10px; text-align: center; font-size: 11px; }

@media (max-width: 1200px) { .account-grid { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 900px) { .paper-page { padding: 24px 20px 48px; }.page-head { align-items: flex-start; flex-direction: column; gap: 18px; }.head-actions { width: 100%; }.head-actions button { flex: 1; }.comparison-head { align-items: flex-start; flex-direction: column; }.chart-legend { justify-content: flex-start; }.bottom-grid { grid-template-columns: 1fr; }.panel-head { align-items: flex-start; flex-direction: column; gap: 12px; }.detail-toolbar { width: 100%; flex-wrap: wrap; }.detail-tabs { flex: 1; }.detail-tabs button { flex: 1; }.hero-stats { grid-template-columns: repeat(2,1fr); gap: 18px 0; }.hero-stats > div:nth-child(2) { border-right: 0; } }
@media (max-width: 640px) { .page-head { align-items: flex-start; flex-direction: column; }.account-grid { grid-template-columns: 1fr; }.hero-card { padding: 22px 18px; }.portfolio-value { font-size: 28px; }.hero-top { align-items: flex-start; flex-direction: column; }.position-row { grid-template-columns: 36px 1fr 1fr; }.position-price { display: none; }.decision-row { grid-template-columns: 42px 42px 1fr 14px; }.log-head, .trade-row { grid-template-columns: 1.25fr .6fr .8fr .7fr; }.log-head span:nth-child(4), .trade-row > span:nth-child(4) { display: none; } }
</style>
