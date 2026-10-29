<template>
  <div class="page-content agent-monitor-page">
    <template v-if="!agent">
      <div class="page-card">
        <el-empty v-if="!loading" description="Agent 不存在或已删除" />
        <div v-else class="loading-wrap"><el-icon class="is-loading"><Loading /></el-icon> 加载中…</div>
      </div>
    </template>

    <template v-else>
      <div class="monitor-header page-card">
        <div class="header-left">
          <el-button :icon="ArrowLeft" text @click="goBack">返回</el-button>
          <h2 class="page-title">{{ agent.name }}</h2>
          <el-tag :type="agent.status === 'running' ? 'success' : 'info'" size="small">
            {{ agent.status === 'running' ? '运行中' : '已停止' }}
          </el-tag>
          <span class="header-meta">{{ exchangeLabel(agent.exchange) }}</span>
        </div>
        <div class="header-right">
          <el-button :icon="Setting" @click="openStrategyDialog">策略配置</el-button>
        </div>
      </div>

      <div class="monitor-layout">
        <div class="left-panel">
          <div class="page-card chart-card">
            <div class="card-header">
              <div class="chart-header-left">
                <h3 class="block-title">持仓浮盈</h3>
                <span v-if="latestUnrealized" class="chart-latest" :class="pnlClass(String(latestUnrealized.pnl))">
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
                    <el-table-column prop="side" label="方向" min-width="92" align="center">
                      <template #default="{ row }">
                        <el-tag :type="row.side === 'long' ? 'success' : 'danger'" size="small">
                          {{ row.side === 'long' ? '多' : '空' }}
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="quantity" label="数量" min-width="110" align="right">
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
                    <el-table-column prop="side" label="方向" min-width="92" align="center">
                      <template #default="{ row }">
                        <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                          {{ row.side === 'buy' ? '买' : '卖' }}
                        </el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column prop="type" label="类型" min-width="92" align="center">
                      <template #default="{ row }">{{ row.type === 'market' ? '市价' : '限价' }}</template>
                    </el-table-column>
                    <el-table-column prop="quantity" label="数量" min-width="110" align="right">
                      <template #default="{ row }">{{ formatNum(row.quantity) }}</template>
                    </el-table-column>
                    <el-table-column prop="status" label="状态" min-width="96" align="center">
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
                      <span class="op-value">{{ operationAnalysis(op) }}</span>
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
      <!-- 策略配置弹窗 -->
      <el-dialog
        v-model="strategyDialogVisible"
        title="策略配置"
        width="760px"
        :close-on-click-modal="false"
        class="strategy-dialog"
      >
        <div v-loading="strategyLoading" class="strategy-dialog-body">
          <StrategyConfigPanel
            v-if="strategyDialogVisible && !strategyLoading"
            ref="strategyConfigRef"
            v-model="currentStrategyConfig"
          />
        </div>
        <template #footer>
          <el-button @click="strategyDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="strategySaving" @click="saveStrategyConfig">
            保存配置
          </el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Loading, Setting } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { agentsApi, mergeLegacyDecisionLlm } from '@/api/agents'
import type { AgentListItem, AgentOperationItem, OperationType, StrategyConfig } from '@/api/agents'
import type { ExchangeCode } from '@/api/agents'
import type { PositionListItem } from '@/api/positions'
import type { OrderListItem, OrderStatus } from '@/api/orders'
import StrategyConfigPanel from '@/components/StrategyConfigPanel.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const agent = ref<AgentListItem | null>(null)
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

const strategyDialogVisible = ref(false)
const strategyLoading = ref(false)
const strategySaving = ref(false)
const strategyConfigRef = ref<InstanceType<typeof StrategyConfigPanel>>()
const currentStrategyConfig = ref<StrategyConfig | null>(null)

const agentId = () => String(route.params.id)

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

function operationAnalysis(op: AgentOperationItem): string {
  return op.reason?.trim() || '—'
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

function formatNum(s: string): string {
  const n = parseFloat(s)
  if (Number.isNaN(n)) return s
  if (n >= 1) return n.toFixed(4)
  return n.toFixed(8)
}

function formatMoney(s: string): string {
  const n = parseFloat(s)
  if (Number.isNaN(n)) return s
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatSignedMoney(s: string | number | undefined): string {
  if (s === undefined) return '-'
  const n = parseFloat(String(s))
  if (Number.isNaN(n)) return String(s)
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatPercent(s: string | number | undefined): string {
  if (s === undefined) return '-'
  const n = parseFloat(String(s))
  if (Number.isNaN(n)) return String(s)
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function formatChartTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function pnlClass(pnl: string): string {
  const n = parseFloat(pnl)
  if (Number.isNaN(n)) return ''
  if (n > 0) return 'text-profit'
  if (n < 0) return 'text-loss'
  return ''
}

const latestUnrealized = computed(() => {
  const pts = profitCurveData.value
  if (!pts.length) return null
  const last = pts[pts.length - 1]
  return { pnl: last.pnl, rate: last.rate }
})

function goBack() {
  router.push('/agents')
}

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
    series: [{
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
    }],
  })
}

async function fetchAgent() {
  loading.value = true
  try {
    agent.value = await agentsApi.getById(agentId())
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载失败')
    agent.value = null
  } finally {
    loading.value = false
  }
}

async function fetchProfitCurve() {
  if (!agent.value) return
  try {
    const params: Record<string, string> = {}
    if (profitDateRange.value && profitDateRange.value[0] && profitDateRange.value[1]) {
      params.startDate = profitDateRange.value[0]
      params.endDate = profitDateRange.value[1]
    } else {
      params.period = profitPeriod.value
    }
    const res = await agentsApi.getProfitCurve(agentId(), params)
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
  positionsLoading.value = true
  try {
    const res = await agentsApi.getPositions(agentId())
    positionsList.value = res.list || []
  } catch {
    positionsList.value = []
  } finally {
    positionsLoading.value = false
  }
}

async function fetchOrders() {
  ordersLoading.value = true
  try {
    const res = await agentsApi.getOrders(agentId(), { page: 1, pageSize: 20 })
    ordersList.value = res.list || []
  } catch {
    ordersList.value = []
  } finally {
    ordersLoading.value = false
  }
}

async function fetchOperations() {
  operationsLoading.value = true
  try {
    const params: Record<string, string | number> = { limit: 50 }
    if (operationsDateRange.value && operationsDateRange.value[0] && operationsDateRange.value[1]) {
      params.startDate = operationsDateRange.value[0]
      params.endDate = operationsDateRange.value[1]
    } else if (operationsPeriod.value) {
      params.period = operationsPeriod.value
    }
    const res = await agentsApi.getOperations(agentId(), params)
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

async function openStrategyDialog() {
  strategyDialogVisible.value = true
  strategyLoading.value = true
  try {
    const res = await agentsApi.getStrategyConfig(agentId())
    const raw = res.strategyConfig
    currentStrategyConfig.value = raw
      ? mergeLegacyDecisionLlm(raw, agent.value?.llmModelId)
      : null
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载策略配置失败')
    currentStrategyConfig.value = null
  } finally {
    strategyLoading.value = false
  }
}

async function saveStrategyConfig() {
  if (!strategyConfigRef.value) return
  const valid = await strategyConfigRef.value.validate()
  if (!valid) return

  strategySaving.value = true
  try {
    const config = strategyConfigRef.value.getConfig()
    await agentsApi.updateStrategyConfig(agentId(), { strategyConfig: config })
    ElMessage.success('策略配置保存成功')
    strategyDialogVisible.value = false
    await fetchAgent()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  } finally {
    strategySaving.value = false
  }
}

onMounted(async () => {
  await fetchAgent()
  if (agent.value) {
    await fetchProfitCurve()
    await fetchPositions()
    await fetchOrders()
    await fetchOperations()
  }
})

watch(
  () => route.params.id,
  async () => {
    await fetchAgent()
    if (agent.value) {
      await fetchProfitCurve()
      await fetchPositions()
      await fetchOrders()
      await fetchOperations()
    }
  }
)
</script>

<style scoped>
.agent-monitor-page {
  padding: 0;
  min-height: 0;
}

.page-card {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}

.monitor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md) var(--spacing-lg);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.header-left .page-title {
  margin: 0;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-meta {
  font-size: var(--font-size-desc);
  color: var(--color-text-muted);
}
.loading-wrap {
  padding: 32px;
  text-align: center;
  color: var(--color-text-muted);
}

.monitor-layout {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: var(--spacing-lg);
  align-items: stretch;
}
@media (max-width: 1200px) {
  .monitor-layout { grid-template-columns: 1fr; }
}

.left-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}
.left-panel .chart-card {
  flex-shrink: 0;
}
.left-panel .tabs-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.left-panel .tabs-card :deep(.el-tabs) {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.left-panel .tabs-card :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}
.left-panel .tabs-card :deep(.el-tab-pane) {
  height: 100%;
}
.left-panel .tabs-card .table-wrap {
  height: 100%;
}
.left-panel .tabs-card .table-wrap .el-table {
  height: 100% !important;
  max-height: none !important;
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
.card-header .block-title {
  margin: 0;
}
.block-title {
  margin: 0 0 12px;
  font-size: var(--font-size-card-title);
  font-weight: 600;
  color: var(--color-text-primary);
}
.time-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.time-filter :deep(.el-radio-group) {
  flex-shrink: 0;
}
.time-filter :deep(.el-date-editor) {
  width: 220px;
}
.time-filter :deep(.el-radio-button__inner) {
  padding: 6px 12px;
}

.card-header-vertical {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.card-header-row .block-title {
  margin: 0;
  flex-shrink: 0;
}
.card-header-row :deep(.el-radio-button__inner) {
  padding: 4px 10px;
  font-size: 12px;
}
.ops-date-picker.el-date-editor {
  width: 100% !important;
}
.ops-date-picker :deep(.el-range-input) {
  font-size: 12px;
}
.ops-date-picker :deep(.el-range-separator) {
  font-size: 12px;
  padding: 0 4px;
}
.chart-wrap {
  height: 260px;
  width: 100%;
  margin-top: 8px;
}
.panel-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.table-wrap.small .data-table {
  font-size: var(--font-size-caption);
}
.data-table {
  width: 100%;
}
.compact-table.el-table :deep(th.el-table__cell),
.compact-table.el-table :deep(td.el-table__cell) {
  padding: 10px 14px;
}
.compact-table.el-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  white-space: nowrap;
}
.compact-table.el-table :deep(.el-table__body td) {
  font-size: 13px;
}

.right-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.operations-card {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}
.operations-card .block-title {
  flex-shrink: 0;
}
.operations-feed {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}
.operation-card {
  padding: 12px 14px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color var(--transition-fast);
}
.operation-card:hover {
  border-color: var(--color-border-active);
}
.op-time {
  font-size: var(--font-size-caption);
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
  font-size: var(--font-size-desc);
  font-weight: 500;
  color: var(--color-text-muted);
  white-space: nowrap;
}
.op-value {
  font-size: var(--font-size-desc);
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
  align-items: center;
  gap: 2px 0;
}
.op-seg {
  font-size: var(--font-size-desc);
  color: var(--color-text-primary);
}
.op-seg + .op-seg::before {
  content: ' · ';
  color: var(--color-text-disabled);
  margin: 0 4px;
}
.op-result {
  font-size: var(--font-size-caption);
  font-weight: 500;
  margin-top: 2px;
}
.op-result--success {
  color: var(--color-profit);
}
.op-result--partial {
  color: var(--color-warning, #F59E0B);
}
.op-result--failed {
  color: var(--color-loss);
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
  font-size: var(--font-size-caption);
  color: var(--color-primary);
}
.op-cot-wrap :deep(.el-collapse-item__content) {
  padding: 10px 0 4px;
}
.op-cot-wrap :deep(.el-collapse-item__arrow) {
  color: var(--color-primary);
}

.chain-of-thought {
  padding: 10px 12px;
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 0;
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
.cot-step + .cot-step {
  margin-top: 0;
}
.cot-step-num {
  display: inline-block;
  font-size: var(--font-size-caption);
  color: var(--color-primary);
  font-weight: 600;
  margin-bottom: 2px;
}
.cot-thought {
  margin: 0;
  font-size: var(--font-size-desc);
  color: var(--color-text-primary);
  line-height: 1.5;
}
.cot-conclusion {
  margin: 4px 0 0;
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
  padding: 3px 8px;
  background: rgba(148, 163, 184, 0.06);
  border-radius: var(--radius-sm);
  display: inline-block;
}

.strategy-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
  max-height: 65vh;
  overflow-y: auto;
}

.strategy-dialog-body {
  min-height: 200px;
}
</style>
