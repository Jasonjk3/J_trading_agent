<template>
  <div class="agent-monitor">
    <template v-if="!agent">
      <div class="empty-state">
        <el-empty v-if="!loading" description="请选择一个Agent查看详情" />
        <div v-else class="loading-wrap"><el-icon class="is-loading"><Loading /></el-icon> 加载中…</div>
      </div>
    </template>

    <template v-else>
      <div class="monitor-header">
        <div class="header-left">
          <h2 class="agent-title">{{ agent.name }}</h2>
          <el-tag :type="agent.status === 'running' ? 'success' : 'info'" size="small">
            {{ agent.status === 'running' ? '运行中' : '已停止' }}
          </el-tag>
          <span class="header-meta">{{ exchangeLabel(agent.exchange) }}</span>
          <span v-if="agent.status === 'running' && runningDuration" class="header-meta">
            已运行 {{ runningDuration }}
          </span>
        </div>
        <div class="header-right">
          <el-button :icon="Setting" @click="$emit('open-strategy')">策略配置</el-button>
          <el-button
            :type="agent.status === 'running' ? 'danger' : 'success'"
            :loading="toggleLoading"
            @click="handleToggle"
          >
            {{ agent.status === 'running' ? '停止' : '启动' }}
          </el-button>
        </div>
      </div>

      <div class="metrics-panel">
        <div class="metric-card">
          <div class="metric-label">总收益</div>
          <div class="metric-value" :class="pnlClass(agent.totalProfit)">
            {{ formatMoney(agent.totalProfit) }}
          </div>
          <div class="metric-sub">累计</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">今日收益</div>
          <div class="metric-value" :class="pnlClass(agent.todayProfit)">
            {{ formatPercent(agent.todayProfit) }}
          </div>
          <div class="metric-sub">对比昨日</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">胜率</div>
          <div class="metric-value">{{ agent.winRate ?? '-' }}%</div>
          <div class="metric-sub">共 {{ agent.totalTrades ?? 0 }} 笔</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">持仓数</div>
          <div class="metric-value">{{ positionsList.length }}</div>
          <div class="metric-sub">当前</div>
        </div>
      </div>

      <div class="monitor-layout">
        <div class="left-panel">
          <div class="page-card chart-card">
            <div class="card-header">
              <div class="chart-header-left">
                <h3 class="block-title">持仓浮盈</h3>
                <span v-if="latestUnrealized" class="chart-latest" :class="pnlClass(latestUnrealized.pnl)">
                  {{ formatSignedMoney(latestUnrealized.pnl) }}
                  <span class="chart-latest-rate">({{ formatPercent(latestUnrealized.rate) }})</span>
                </span>
              </div>
              <div class="time-filter">
                <el-radio-group v-model="profitPeriod" size="small" @change="onProfitPeriodChange">
                  <el-radio-button value="1d">昨天</el-radio-button>
                  <el-radio-button value="7d">近 7 天</el-radio-button>
                  <el-radio-button value="30d">近 30 天</el-radio-button>
                </el-radio-group>
                <el-date-picker
                  v-model="profitDateRange"
                  type="daterange"
                  size="small"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  :clearable="true"
                  @change="onProfitDateRangeChange"
                />
              </div>
            </div>
            <div ref="chartRef" class="chart-wrap"></div>
          </div>
          <div class="page-card tabs-card">
            <el-tabs v-model="leftTab" class="panel-tabs">
              <el-tab-pane label="当前持仓" name="positions">
                <div class="table-wrap small">
                  <el-table
                    v-loading="positionsLoading"
                    :data="positionsList"
                    class="data-table compact-table"
                    header-cell-class-name="table-header"
                    table-layout="auto"
                  >
                    <el-table-column prop="symbol" label="交易对" min-width="100" />
                    <el-table-column prop="side" label="方向" min-width="80" align="center">
                      <template #default="{ row }">
                        <el-tag :type="row.side === 'long' ? 'success' : 'danger'" size="small">
                          {{ row.side === 'long' ? '多' : '空' }}
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="quantity" label="数量" min-width="100" align="right">
                      <template #default="{ row }">{{ formatNum(row.quantity) }}</template>
                    </el-table-column>
                    <el-table-column prop="notional" label="市值" min-width="100" align="right">
                      <template #default="{ row }">{{ formatMoney(row.notional) }}</template>
                    </el-table-column>
                    <el-table-column prop="unrealizedPnl" label="未实现盈亏" min-width="120" align="right">
                      <template #default="{ row }">
                        <span :class="pnlClass(row.unrealizedPnl)">{{ formatMoney(row.unrealizedPnl) }}</span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-tab-pane>
              <el-tab-pane label="当前委托" name="orders">
                <div class="table-wrap small">
                  <el-table
                    v-loading="ordersLoading"
                    :data="ordersList"
                    class="data-table compact-table"
                    header-cell-class-name="table-header"
                    table-layout="auto"
                  >
                    <el-table-column prop="symbol" label="交易对" min-width="100" />
                    <el-table-column prop="side" label="方向" min-width="80" align="center">
                      <template #default="{ row }">
                        <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                          {{ row.side === 'buy' ? '买' : '卖' }}
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="type" label="类型" min-width="80" align="center">
                      <template #default="{ row }">{{ row.type === 'market' ? '市价' : '限价' }}</template>
                    </el-table-column>
                    <el-table-column prop="quantity" label="数量" min-width="100" align="right">
                      <template #default="{ row }">{{ formatNum(row.quantity) }}</template>
                    </el-table-column>
                    <el-table-column prop="status" label="状态" min-width="90" align="center">
                      <template #default="{ row }">{{ orderStatusLabel(row.status) }}</template>
                    </el-table-column>
                    <el-table-column prop="createdAt" label="时间" min-width="140" align="right">
                      <template #default="{ row }">{{ formatDate(row.createdAt) }}</template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-tab-pane>
            </el-tabs>
          </div>
        </div>

        <div class="right-panel">
          <div class="page-card operations-card">
            <div class="card-header-vertical">
              <div class="card-header-row">
                <h3 class="block-title">操作记录</h3>
                <el-radio-group v-model="operationsPeriod" size="small" @change="onOperationsPeriodChange">
                  <el-radio-button value="1d">昨天</el-radio-button>
                  <el-radio-button value="7d">7天</el-radio-button>
                  <el-radio-button value="30d">30天</el-radio-button>
                </el-radio-group>
              </div>
              <el-date-picker
                v-model="operationsDateRange"
                type="daterange"
                size="small"
                range-separator="至"
                start-placeholder="开始"
                end-placeholder="结束"
                format="MM-DD"
                value-format="YYYY-MM-DD"
                :clearable="true"
                class="ops-date-picker"
                @change="onOperationsDateRangeChange"
              />
            </div>
            <div v-loading="operationsLoading" class="operations-feed">
              <template v-if="operationsList.length">
                <div
                  v-for="op in operationsList"
                  :key="op.id"
                  class="operation-card"
                >
                  <div class="op-time">{{ formatDate(op.createdAt) }}</div>
                  <div class="op-body">
                    <div class="op-field">
                      <span class="op-label">分析：</span>
                      <span class="op-value">{{ op.reason?.trim() || '—' }}</span>
                    </div>
                    <div class="op-field">
                      <span class="op-label">操作：</span>
                      <span class="op-action-detail">
                        <span class="op-action-segments">
                          <span class="op-seg">{{ operationTypeLabel(op.type) }}</span>
                          <span v-if="op.symbol" class="op-seg">{{ op.symbol }}</span>
                          <span v-if="op.side" class="op-seg">{{ op.side === 'buy' ? '买' : '卖' }}</span>
                          <span v-if="op.quantity" class="op-seg">数量 {{ formatNum(op.quantity) }}</span>
                          <span v-if="op.price" class="op-seg">价格 {{ op.price }}</span>
                        </span>
                        <span v-if="op.result" class="op-result" :class="'op-result--' + op.result">
                          结果：{{ op.result === 'success' ? '成功' : op.result === 'partial' ? '部分成交' : '失败' }}
                        </span>
                      </span>
                    </div>
                  </div>
                  <div v-if="op.chainOfThought?.length" class="op-cot-wrap">
                    <el-collapse>
                      <el-collapse-item title="思维链详情" name="cot">
                        <div class="chain-of-thought">
                          <div
                            v-for="step in op.chainOfThought"
                            :key="step.step"
                            class="cot-step"
                          >
                            <span class="cot-step-num">步骤 {{ step.step }}</span>
                            <p class="cot-thought">{{ step.thought }}</p>
                            <p v-if="step.conclusion" class="cot-conclusion">结论：{{ step.conclusion }}</p>
                          </div>
                        </div>
                      </el-collapse-item>
                    </el-collapse>
                  </div>
                </div>
              </template>
              <el-empty v-else description="暂无操作记录" :image-size="64" />
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Setting } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { agentsApi } from '@/api/agents'
import type { AgentListItem, AgentOperationItem, OperationType, ExchangeCode } from '@/api/agents'
import type { PositionListItem } from '@/api/positions'
import type { OrderListItem, OrderStatus } from '@/api/orders'

const props = defineProps<{
  agentId: string | null
}>()

const emit = defineEmits<{
  'open-strategy': []
  'refresh': []
}>()

const loading = ref(false)
const agent = ref<AgentListItem | null>(null)
const toggleLoading = ref(false)

const chartRef = ref<HTMLElement | null>(null)
let chartInstance: ECharts | null = null

const profitPeriod = ref('7d')
const profitDateRange = ref<[string, string] | null>(null)
const profitCurveData = ref<{ time: string; pnl: number; rate: number }[]>([])

const leftTab = ref<'positions' | 'orders'>('positions')
const positionsLoading = ref(false)
const ordersLoading = ref(false)
const positionsList = ref<PositionListItem[]>([])
const ordersList = ref<OrderListItem[]>([])

const operationsLoading = ref(false)
const operationsList = ref<AgentOperationItem[]>([])
const operationsPeriod = ref('7d')
const operationsDateRange = ref<[string, string] | null>(null)

const runningDuration = computed(() => {
  if (!agent.value?.lastRunAt || agent.value.status !== 'running') return ''
  const start = new Date(agent.value.lastRunAt).getTime()
  const now = Date.now()
  const diff = now - start
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
  if (days > 0) return `${days}天${hours}小时`
  if (hours > 0) return `${hours}小时${minutes}分钟`
  return `${minutes}分钟`
})

function exchangeLabel(code?: ExchangeCode): string {
  if (!code) return '-'
  const map: Record<ExchangeCode, string> = { binance: 'Binance', okx: 'OKX', bybit: 'Bybit' }
  return map[code] ?? code
}

function operationTypeLabel(t: OperationType): string {
  const map: Record<OperationType, string> = {
    open_long: '开多',
    open_short: '开空',
    close_long: '平多',
    close_short: '平空',
    adjust: '调仓',
    cancel_order: '撤单',
    other: '其他',
  }
  return map[t] ?? t
}

function orderStatusLabel(s: OrderStatus): string {
  const map: Record<OrderStatus, string> = {
    pending: '待成交',
    partial: '部分成交',
    filled: '已成交',
    cancelled: '已取消',
    failed: '失败',
  }
  return map[s] ?? s
}

function formatDate(iso?: string): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

function formatNum(s: string | number): string {
  const n = parseFloat(String(s))
  if (Number.isNaN(n)) return String(s)
  if (n >= 1) return n.toFixed(4)
  return n.toFixed(8)
}

function formatMoney(s: string | number | undefined): string {
  if (s === undefined) return '-'
  const n = parseFloat(String(s))
  if (Number.isNaN(n)) return String(s)
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPercent(s: string | number | undefined): string {
  if (s === undefined) return '-'
  const n = parseFloat(String(s))
  if (Number.isNaN(n)) return String(s)
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function pnlClass(pnl: string | number | undefined): string {
  if (pnl === undefined) return ''
  const n = parseFloat(String(pnl))
  if (Number.isNaN(n)) return ''
  if (n > 0) return 'text-profit'
  if (n < 0) return 'text-loss'
  return ''
}

function formatSignedMoney(s: string | number | undefined): string {
  if (s === undefined) return '-'
  const n = parseFloat(String(s))
  if (Number.isNaN(n)) return String(s)
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatChartTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const latestUnrealized = computed(() => {
  const pts = profitCurveData.value
  if (!pts.length) return null
  const last = pts[pts.length - 1]
  return { pnl: last.pnl, rate: last.rate }
})

function renderChart() {
  if (!chartRef.value || !profitCurveData.value.length) return
  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartRef.value, chartTheme)
  const times = profitCurveData.value.map((p) => formatChartTime(p.time))
  const pnlValues = profitCurveData.value.map((p) => p.pnl)
  const lastPnl = pnlValues[pnlValues.length - 1] ?? 0
  const lineColor = lastPnl >= 0 ? '#00D26A' : '#FF4D4D'
  const areaTop = lastPnl >= 0 ? 'rgba(0, 210, 106, 0.2)' : 'rgba(255, 77, 77, 0.2)'

  chartInstance.setOption({
    grid: { left: 56, right: 24, top: 24, bottom: 32 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(17,24,39,0.95)',
      borderColor: 'rgba(148,163,184,0.15)',
      textStyle: { color: '#F1F5F9', fontSize: 12 },
      formatter(params: any) {
        const items = Array.isArray(params) ? params : [params]
        const idx = items[0]?.dataIndex ?? 0
        const raw = profitCurveData.value[idx]
        if (!raw) return ''
        const pnlSign = raw.pnl > 0 ? '+' : ''
        const rateSign = raw.rate > 0 ? '+' : ''
        return [
          formatChartTime(raw.time),
          `浮盈：${pnlSign}${raw.pnl.toFixed(2)} USDT (${rateSign}${raw.rate.toFixed(2)}%)`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: times,
      axisLabel: { color: '#64748B', fontSize: 11 },
      axisLine: { lineStyle: { color: 'rgba(148,163,184,0.08)' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '浮盈 (USDT)',
      nameTextStyle: { color: '#64748B', fontSize: 11 },
      axisLabel: {
        color: '#64748B',
        fontSize: 11,
        formatter: (v: number) => {
          const sign = v > 0 ? '+' : ''
          return `${sign}${v.toFixed(0)}`
        },
      },
      splitLine: { lineStyle: { color: 'rgba(148,163,184,0.08)' } },
    },
    series: [
      {
        name: '持仓浮盈',
        type: 'line',
        smooth: true,
        data: pnlValues,
        showSymbol: false,
        lineStyle: { width: 2.5, color: lineColor },
        areaStyle: {
          color: areaTop,
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: 'rgba(148,163,184,0.25)', type: 'dashed' },
          data: [{ yAxis: 0 }],
        },
      },
    ],
  })
}

async function fetchAgent() {
  if (!props.agentId) {
    agent.value = null
    return
  }
  loading.value = true
  try {
    agent.value = await agentsApi.getById(props.agentId)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载失败')
    agent.value = null
  } finally {
    loading.value = false
  }
}

async function fetchProfitCurve() {
  if (!props.agentId) return
  try {
    const params: Record<string, string> = {}
    if (profitDateRange.value && profitDateRange.value[0] && profitDateRange.value[1]) {
      params.startDate = profitDateRange.value[0]
      params.endDate = profitDateRange.value[1]
    } else {
      params.period = profitPeriod.value
    }
    const res = await agentsApi.getProfitCurve(props.agentId, params)
    profitCurveData.value = (res.points || []).map((p) => ({
      time: p.time,
      pnl: parseFloat(p.unrealizedPnl ?? '0'),
      rate: parseFloat(p.unrealizedPnlRate ?? '0'),
    }))
    renderChart()
  } catch {
    profitCurveData.value = []
  }
}

function onProfitPeriodChange() {
  profitDateRange.value = null
  fetchProfitCurve()
}

function onProfitDateRangeChange(val: [string, string] | null) {
  if (val && val[0] && val[1]) {
    profitPeriod.value = ''
  }
  fetchProfitCurve()
}

async function fetchPositions() {
  if (!props.agentId) return
  positionsLoading.value = true
  try {
    const res = await agentsApi.getPositions(props.agentId)
    positionsList.value = res.list || []
  } catch {
    positionsList.value = []
  } finally {
    positionsLoading.value = false
  }
}

async function fetchOrders() {
  if (!props.agentId) return
  ordersLoading.value = true
  try {
    const res = await agentsApi.getOrders(props.agentId, { page: 1, pageSize: 20 })
    ordersList.value = res.list || []
  } catch {
    ordersList.value = []
  } finally {
    ordersLoading.value = false
  }
}

async function fetchOperations() {
  if (!props.agentId) return
  operationsLoading.value = true
  try {
    const params: Record<string, string | number> = { limit: 50 }
    if (operationsDateRange.value && operationsDateRange.value[0] && operationsDateRange.value[1]) {
      params.startDate = operationsDateRange.value[0]
      params.endDate = operationsDateRange.value[1]
    } else if (operationsPeriod.value) {
      params.period = operationsPeriod.value
    }
    const res = await agentsApi.getOperations(props.agentId, params)
    operationsList.value = res.list || []
  } catch {
    operationsList.value = []
  } finally {
    operationsLoading.value = false
  }
}

function onOperationsPeriodChange() {
  operationsDateRange.value = null
  fetchOperations()
}

function onOperationsDateRangeChange(val: [string, string] | null) {
  if (val && val[0] && val[1]) {
    operationsPeriod.value = ''
  }
  fetchOperations()
}

async function handleToggle() {
  if (!agent.value) return
  toggleLoading.value = true
  try {
    const api = agent.value.status === 'running' ? agentsApi.stop : agentsApi.start
    const res = await api(agent.value.id)
    ElMessage.success(res.message ?? (agent.value.status === 'running' ? '已停止' : '已启动'))
    emit('refresh')
    await fetchAgent()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '操作失败')
  } finally {
    toggleLoading.value = false
  }
}

async function loadAllData() {
  await fetchAgent()
  if (agent.value) {
    await Promise.all([
      fetchProfitCurve(),
      fetchPositions(),
      fetchOrders(),
      fetchOperations(),
    ])
  }
}

watch(
  () => props.agentId,
  () => {
    loadAllData()
  },
  { immediate: true }
)

onMounted(() => {
  window.addEventListener('resize', () => chartInstance?.resize())
})

onUnmounted(() => {
  chartInstance?.dispose()
})

defineExpose({ refresh: loadAllData })
</script>

<style scoped>
.agent-monitor {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
}

.loading-wrap {
  padding: 32px;
  text-align: center;
  color: var(--color-text-muted);
}

.monitor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px 20px;
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  margin-bottom: 16px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.agent-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.header-meta {
  font-size: 13px;
  color: var(--color-text-muted);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.metrics-panel {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
  flex-shrink: 0;
}

@media (max-width: 1200px) {
  .metrics-panel {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .metrics-panel {
    grid-template-columns: 1fr;
  }
}

.metric-card {
  padding: 16px 20px;
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
}

.metric-label {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 6px;
}

.metric-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1.2;
}

.metric-value.text-profit {
  color: var(--color-profit, #10B981);
}

.metric-value.text-loss {
  color: var(--color-loss, #EF4444);
}

.metric-sub {
  font-size: 11px;
  color: var(--color-text-disabled);
  margin-top: 4px;
}

.monitor-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 1200px) {
  .monitor-layout {
    grid-template-columns: 1fr;
    overflow: auto;
  }
}

.left-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

.page-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  padding: 16px 20px;
}

.chart-card {
  flex-shrink: 0;
}

.tabs-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tabs-card :deep(.el-tabs) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.tabs-card :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}

.tabs-card :deep(.el-tab-pane) {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.chart-header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.chart-latest {
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.chart-latest-rate {
  font-size: 14px;
  font-weight: 500;
  margin-left: 4px;
  opacity: 0.85;
}

.block-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.time-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.time-filter :deep(.el-date-editor) {
  width: 220px;
}

.chart-wrap {
  height: 240px;
  width: 100%;
}

.table-wrap {
  height: 100%;
  overflow: auto;
}

.compact-table.el-table :deep(th.el-table__cell),
.compact-table.el-table :deep(td.el-table__cell) {
  padding: 10px 12px;
}

.right-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.operations-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.card-header-vertical {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ops-date-picker.el-date-editor {
  width: 100% !important;
}

.operations-feed {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.operation-card {
  padding: 12px 14px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.op-time {
  font-size: 12px;
  color: var(--color-text-muted);
  padding-bottom: 6px;
  border-bottom: 1px dashed var(--color-border);
}

.op-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.op-field {
  display: flex;
  gap: 4px;
  line-height: 1.6;
}

.op-label {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-muted);
}

.op-value {
  font-size: 13px;
  color: var(--color-text-primary);
  word-break: break-word;
}

.op-action-detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.op-action-segments {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 0;
}

.op-seg {
  font-size: 13px;
  color: var(--color-text-primary);
}

.op-seg + .op-seg::before {
  content: ' · ';
  color: var(--color-text-disabled);
  margin: 0 4px;
}

.op-result {
  font-size: 12px;
  font-weight: 500;
  margin-top: 2px;
}

.op-result--success {
  color: var(--color-profit, #10B981);
}

.op-result--partial {
  color: var(--color-warning, #F59E0B);
}

.op-result--failed {
  color: var(--color-loss, #EF4444);
}

.op-cot-wrap {
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border);
}

.op-cot-wrap :deep(.el-collapse-item__header) {
  height: auto;
  line-height: 1.4;
  padding: 4px 0;
  font-size: 12px;
  color: var(--color-primary);
}

.chain-of-thought {
  padding: 10px 12px;
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.cot-step {
  position: relative;
  padding: 8px 0 8px 16px;
  border-left: 2px solid var(--color-border);
  margin-left: 4px;
}

.cot-step:last-child {
  border-left-color: var(--color-primary);
}

.cot-step-num {
  font-size: 12px;
  color: var(--color-primary);
  font-weight: 600;
}

.cot-thought {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.cot-conclusion {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
  padding: 3px 8px;
  background: rgba(148, 163, 184, 0.06);
  border-radius: var(--radius-sm);
  display: inline-block;
}

.text-profit {
  color: var(--color-profit, #10B981);
}

.text-loss {
  color: var(--color-loss, #EF4444);
}
</style>
