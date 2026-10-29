<template>
  <div class="analytics-page page-content">
    <el-alert v-if="summary && (summary.complete === false || summary.returnRate === null)" :closable="false" type="warning" show-icon
      :title="summary.warnings?.join('；') || summary.returnRateReason || '统计范围说明'"
      :description="summary.returnRateReason" style="margin-bottom: 16px" />
    <!-- 钱包余额区域 -->
    <div class="wallet-section" v-if="walletBalances.length > 0">
      <div class="page-card wallet-card" v-for="wallet in walletBalances" :key="wallet.exchange">
        <div class="wallet-header">
          <div class="wallet-exchange">
            <el-icon :size="24" class="wallet-icon"><CreditCard /></el-icon>
            <span class="wallet-exchange-name">{{ exchangeLabel(wallet.exchange) }}</span>
          </div>
          <span class="wallet-updated" v-if="wallet.updatedAt">
            更新于 {{ formatTime(wallet.updatedAt) }}
          </span>
        </div>
        <div class="wallet-total">
          <span class="wallet-total-label">账户总权益</span>
          <span class="wallet-total-value">${{ formatMoney(wallet.totalEqUsd) }}</span>
        </div>
        <div class="wallet-balances" v-if="wallet.balances.length > 0">
          <div class="wallet-balance-item" v-for="b in wallet.balances.slice(0, 5)" :key="b.currency">
            <span class="balance-currency">{{ b.currency }}</span>
            <div class="balance-values">
              <span class="balance-total">{{ formatCrypto(b.total) }}</span>
              <span class="balance-usd">≈ ${{ formatMoney(b.eqUsd) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="page-card">
      <div class="page-header">
        <h2 class="page-title">收益分析</h2>
        <p class="page-desc">多维度统计与展示收益，支持时间范围、交易所、币种筛选。</p>
      </div>

      <div class="toolbar">
        <el-form :model="filter" inline class="filter-form">
          <el-form-item label="时间范围">
            <el-date-picker
              v-model="filter.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              :shortcuts="dateShortcuts"
              style="width: 280px"
            />
          </el-form-item>
          <el-form-item label="交易所">
            <el-select v-model="filter.exchange" placeholder="全部" clearable style="width: 120px">
              <el-option label="Binance" value="binance" />
              <el-option label="OKX" value="okx" />
              <el-option label="Bybit" value="bybit" />
            </el-select>
          </el-form-item>
          <el-form-item label="汇总粒度">
            <el-select v-model="filter.period" placeholder="按日" style="width: 100px">
              <el-option label="按日" value="day" />
              <el-option label="按周" value="week" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchAll">查询</el-button>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="summary-cards">
        <div class="summary-card" v-for="c in summaryCards" :key="c.label">
          <div class="summary-icon" :style="{ '--sc': c.color }">
            <el-icon :size="20"><component :is="c.icon" /></el-icon>
          </div>
          <div class="summary-body">
            <span class="summary-label">{{ c.label }}</span>
            <span class="summary-value" :class="c.cls">{{ c.value }}</span>
          </div>
        </div>
      </div>

      <div class="page-card chart-section">
        <h3 class="section-title">收益趋势</h3>
        <div ref="trendChartRef" class="chart-wrap"></div>
      </div>

      <div class="dimension-row">
        <div class="page-card dimension-card">
          <h3 class="section-title">按交易所</h3>
          <div ref="exchangeChartRef" class="chart-wrap chart-bar"></div>
          <el-table
            :data="byExchangeList"
            class="data-table dimension-table"
            header-cell-class-name="table-header"
            table-layout="auto"
          >
            <el-table-column prop="exchange" label="交易所" min-width="108">
              <template #default="{ row }">{{ exchangeLabel(row.exchange) }}</template>
            </el-table-column>
            <el-table-column prop="netProfit" label="净收益" align="right" min-width="124">
              <template #default="{ row }">
                <span :class="pnlClass(row.netProfit)">{{ formatMoney(row.netProfit) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="tradeCount" label="成交笔数" align="right" min-width="112" />
          </el-table>
        </div>
        <div class="page-card dimension-card">
          <h3 class="section-title">按币种</h3>
          <div ref="symbolChartRef" class="chart-wrap chart-bar"></div>
          <el-table
            :data="bySymbolList"
            class="data-table dimension-table"
            header-cell-class-name="table-header"
            table-layout="auto"
          >
            <el-table-column prop="symbol" label="交易对" min-width="108" />
            <el-table-column prop="netProfit" label="净收益" align="right" min-width="124">
              <template #default="{ row }">
                <span :class="pnlClass(row.netProfit)">{{ formatMoney(row.netProfit) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="tradeCount" label="成交笔数" align="right" min-width="112" />
          </el-table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, markRaw } from 'vue'
import { ElMessage } from 'element-plus'
import { TrendCharts, Wallet, Money, DataAnalysis, CreditCard } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { analyticsApi } from '@/api/analytics'
import type { ProfitSummary, ProfitTrendPoint, ProfitByExchangeItem, ProfitBySymbolItem, ExchangeCode, WalletBalance } from '@/api/analytics'

const filter = ref<{
  dateRange: [string, string] | null
  exchange: ExchangeCode | ''
  period: 'day' | 'week'
}>({
  dateRange: null,
  exchange: '',
  period: 'day',
})

const dateShortcuts = [
  { text: '近 7 天', value: () => {
    const end = new Date(); const start = new Date(); start.setDate(start.getDate() - 7); return [start, end]
  }},
  { text: '近 30 天', value: () => {
    const end = new Date(); const start = new Date(); start.setDate(start.getDate() - 30); return [start, end]
  }},
  { text: '近 90 天', value: () => {
    const end = new Date(); const start = new Date(); start.setDate(start.getDate() - 90); return [start, end]
  }},
]

const loading = ref(false)
const summary = ref<ProfitSummary | null>(null)
const trendPoints = ref<ProfitTrendPoint[]>([])
const byExchangeList = ref<ProfitByExchangeItem[]>([])
const bySymbolList = ref<ProfitBySymbolItem[]>([])
const walletBalances = ref<WalletBalance[]>([])

const trendChartRef = ref<HTMLElement | null>(null)
const exchangeChartRef = ref<HTMLElement | null>(null)
const symbolChartRef = ref<HTMLElement | null>(null)
let trendChart: ECharts | null = null
let exchangeChart: ECharts | null = null
let symbolChart: ECharts | null = null

const summaryCards = computed(() => [
  {
    label: '总收益', icon: markRaw(TrendCharts), color: '#38BDF8',
    value: formatMoney(summary.value?.totalProfit),
    cls: summaryNetClass(summary.value?.netProfit),
  },
  {
    label: '总手续费', icon: markRaw(Wallet), color: '#94A3B8',
    value: formatMoney(summary.value?.totalFee), cls: '',
  },
  {
    label: '净收益', icon: markRaw(Money), color: '#22C55E',
    value: formatMoney(summary.value?.netProfit),
    cls: summaryNetClass(summary.value?.netProfit),
  },
  {
    label: '收益率', icon: markRaw(DataAnalysis), color: '#8B5CF6',
    value: summary.value?.returnRate ?? '-',
    cls: summaryNetClass(summary.value?.returnRate),
  },
])

function getParams() {
  let from: string | undefined
  let to: string | undefined
  if (filter.value.dateRange && filter.value.dateRange.length === 2) {
    from = filter.value.dateRange[0]; to = filter.value.dateRange[1]
  } else {
    const end = new Date(); const start = new Date(); start.setDate(start.getDate() - 30)
    from = start.toISOString().slice(0, 10); to = end.toISOString().slice(0, 10)
  }
  return { from, to, exchange: filter.value.exchange || undefined, period: filter.value.period }
}

function exchangeLabel(code: ExchangeCode | string): string {
  const map: Record<string, string> = { binance: 'Binance', okx: 'OKX', bybit: 'Bybit' }
  return map[code] ?? code
}

function formatTime(isoStr: string): string {
  try {
    const date = new Date(isoStr)
    return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return isoStr
  }
}

function formatCrypto(val: string): string {
  if (val == null) return ""
  const n = parseFloat(val)
  if (Number.isNaN(n)) return val
  if (n >= 1) return n.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 })
  return n.toLocaleString('en-US', { minimumFractionDigits: 8, maximumFractionDigits: 8 })
}

function formatMoney(s?: string | null): string {
  if (s == null) return "-"
  const n = parseFloat(s)
  if (Number.isNaN(n)) return s
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pnlClass(val: string | null): string {
  if (val == null) return ""
  const n = parseFloat(val)
  if (Number.isNaN(n)) return ''
  if (n > 0) return 'text-profit'
  if (n < 0) return 'text-loss'
  return ''
}

function summaryNetClass(val?: string | null): string {
  if (!val) return ''
  const n = parseFloat(val.replace('%', ''))
  if (Number.isNaN(n)) return ''
  if (n > 0) return 'text-profit'
  if (n < 0) return 'text-loss'
  return ''
}

function resetFilter() {
  filter.value = { dateRange: null, exchange: '', period: 'day' }
  fetchAll()
}

const chartText = '#64748B'
const chartGrid = 'rgba(148,163,184,0.08)'

async function fetchAll() {
  loading.value = true
  const params = getParams()
  try {
    const [summaryRes, trendRes, byExRes, bySymRes, walletRes] = await Promise.all([
      analyticsApi.getProfitSummary(params),
      analyticsApi.getProfitTrend(params),
      analyticsApi.getProfitByExchange(params),
      analyticsApi.getProfitBySymbol(params),
      analyticsApi.getWalletBalance({ exchange: params.exchange }),
    ])
    summary.value = summaryRes
    trendPoints.value = trendRes.points ?? []
    byExchangeList.value = byExRes.list ?? []
    bySymbolList.value = bySymRes.list ?? []
    walletBalances.value = walletRes.list ?? []
    renderTrendChart()
    renderExchangeChart()
    renderSymbolChart()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载失败')
  } finally {
    loading.value = false
  }
}

function renderTrendChart() {
  if (!trendChartRef.value) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendChartRef.value, chartTheme)
  const dates = trendPoints.value.map((p) => p.date)
  const values = trendPoints.value.map((p) => p.profit == null ? null : parseFloat(p.cumulative ?? p.profit))
  trendChart.setOption({
    grid: { left: 56, right: 24, top: 24, bottom: 36 },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(17,24,39,0.95)', borderColor: 'rgba(148,163,184,0.15)', textStyle: { color: '#F1F5F9', fontSize: 12 } },
    xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { color: chartText, fontSize: 11 }, axisLine: { lineStyle: { color: chartGrid } }, axisTick: { show: false } },
    yAxis: { type: 'value', name: '累计收益', nameTextStyle: { color: chartText }, axisLabel: { color: chartText, fontSize: 11 }, splitLine: { lineStyle: { color: chartGrid } } },
    series: [{
      name: '累计收益', type: 'line', smooth: true, data: values, showSymbol: false,
      lineStyle: { width: 2.5, color: '#2563EB' },
      areaStyle: { color: 'rgba(37,99,235,0.08)' },
    }],
  })
}

function renderExchangeChart() {
  if (!exchangeChartRef.value || !byExchangeList.value.length) return
  if (exchangeChart) exchangeChart.dispose()
  exchangeChart = echarts.init(exchangeChartRef.value, chartTheme)
  const names = byExchangeList.value.map((r) => exchangeLabel(r.exchange))
  const values = byExchangeList.value.map((r) => r.netProfit == null ? null : parseFloat(r.netProfit))
  exchangeChart.setOption({
    grid: { left: 48, right: 24, top: 16, bottom: 32 },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(17,24,39,0.95)', borderColor: 'rgba(148,163,184,0.15)', textStyle: { color: '#F1F5F9', fontSize: 12 } },
    xAxis: { type: 'category', data: names, axisLabel: { color: chartText, fontSize: 11 }, axisLine: { lineStyle: { color: chartGrid } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: chartText, fontSize: 11 }, splitLine: { lineStyle: { color: chartGrid } } },
    series: [{
      type: 'bar', barWidth: '50%',
      data: values.map((v) => ({
        value: v,
        itemStyle: {
          color: v != null && v >= 0
            ? '#16A34A'
            : '#DC2626',
          borderRadius: [4, 4, 0, 0],
        },
      })),
    }],
  })
}

function renderSymbolChart() {
  if (!symbolChartRef.value || !bySymbolList.value.length) return
  if (symbolChart) symbolChart.dispose()
  symbolChart = echarts.init(symbolChartRef.value, chartTheme)
  const names = bySymbolList.value.map((r) => r.symbol)
  const values = bySymbolList.value.map((r) => r.netProfit == null ? null : parseFloat(r.netProfit))
  symbolChart.setOption({
    grid: { left: 48, right: 24, top: 16, bottom: 32 },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(17,24,39,0.95)', borderColor: 'rgba(148,163,184,0.15)', textStyle: { color: '#F1F5F9', fontSize: 12 } },
    xAxis: { type: 'category', data: names, axisLabel: { color: chartText, fontSize: 11 }, axisLine: { lineStyle: { color: chartGrid } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: chartText, fontSize: 11 }, splitLine: { lineStyle: { color: chartGrid } } },
    series: [{
      type: 'bar', barWidth: '50%',
      data: values.map((v) => ({
        value: v,
        itemStyle: {
          color: v != null && v >= 0
            ? '#2563EB'
            : '#DC2626',
          borderRadius: [4, 4, 0, 0],
        },
      })),
    }],
  })
}

watch([byExchangeList, bySymbolList], () => {
  renderExchangeChart()
  renderSymbolChart()
}, { flush: 'post' })

onMounted(() => fetchAll())
</script>

<style scoped>
.analytics-page { max-width: 1200px; }

.page-card {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}

/* 钱包余额区域样式 */
.wallet-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.wallet-card {
  background: #FFFFFF;
  border: 1px solid var(--color-border);
  position: relative;
  overflow: hidden;
}

.wallet-card::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -50%;
  width: 100%;
  height: 100%;
  background: #EFF6FF;
  pointer-events: none;
}

.wallet-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

.wallet-exchange {
  display: flex;
  align-items: center;
  gap: 10px;
}

.wallet-icon {
  color: #38BDF8;
}

.wallet-exchange-name {
  font-size: var(--font-size-body);
  font-weight: 600;
  color: var(--color-text-primary);
}

.wallet-updated {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
}

.wallet-total {
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
}

.wallet-total-label {
  display: block;
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.wallet-total-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-primary);
  background: #2563EB;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.wallet-balances {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wallet-balance-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--color-bg-base);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.wallet-balance-item:hover {
  background: var(--color-bg-elevated);
}

.balance-currency {
  font-size: var(--font-size-body);
  font-weight: 600;
  color: var(--color-text-primary);
}

.balance-values {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.balance-total {
  font-size: var(--font-size-body);
  color: var(--color-text-primary);
  font-family: 'Monaco', 'Menlo', monospace;
}

.balance-usd {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
}

.page-header { margin-bottom: var(--spacing-lg); }
.page-title { margin: 0 0 8px; }
.toolbar { margin-bottom: var(--spacing-lg); }
.filter-form :deep(.el-form-item) { margin-bottom: 12px; }

.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}
.summary-card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: 14px;
  transition: all var(--transition-normal);
}
.summary-card:hover {
  border-color: var(--color-border-active);
}
.summary-icon {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--sc) 15%, transparent);
  color: var(--sc);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.summary-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.summary-label {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.summary-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.chart-section { margin-bottom: var(--spacing-lg); }
.section-title {
  font-size: var(--font-size-card-title);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 16px;
}
.chart-wrap { height: 280px; width: 100%; }
.chart-bar { height: 180px; }

.dimension-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
}
.dimension-card {
  display: flex;
  flex-direction: column;
}
.dimension-table { margin-top: 12px; }
.data-table { width: 100%; }

@media (max-width: 900px) {
  .summary-cards { grid-template-columns: repeat(2, 1fr); }
  .dimension-row { grid-template-columns: 1fr; }
}
</style>

