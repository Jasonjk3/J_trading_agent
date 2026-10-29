<template>
  <div class="dashboard-page page-content">
    <header class="dashboard-header">
      <div class="header-text">
        <h1 class="page-title">数据概览</h1>
        <p class="page-desc">交易收益与运行状态一览，默认展示近 30 天数据</p>
      </div>
      <div class="header-actions">
        <el-select v-model="periodLabel" placeholder="时间范围" style="width: 120px" @change="onPeriodChange">
          <el-option label="近 7 天" value="7" />
          <el-option label="近 30 天" value="30" />
          <el-option label="近 90 天" value="90" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="fetchAll">刷新</el-button>
      </div>
    </header>

    <el-alert v-if="summary && (summary.complete === false || summary.returnRate === null)" :closable="false" type="warning" show-icon
      :title="summary.warnings?.join('；') || summary.returnRateReason || '统计范围说明'" :description="summary.returnRateReason" style="margin-bottom: 16px" />
    <section class="stats-row">
      <div class="stat-card" v-for="card in statCards" :key="card.label">
        <div class="stat-icon-wrap" :style="{ '--stat-color': card.color, '--stat-bg': card.bg }">
          <el-icon :size="22"><component :is="card.icon" /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">{{ card.label }}</span>
          <span class="stat-value" :class="card.cls">{{ card.value }}</span>
        </div>
        <div class="stat-glow" :style="{ background: card.color }"></div>
      </div>
    </section>

    <section class="chart-section">
      <div class="chart-panel">
        <div class="panel-header">
          <h3 class="panel-title">收益趋势（累计）</h3>
        </div>
        <div ref="trendChartRef" class="chart-wrap chart-trend"></div>
      </div>
    </section>

    <section class="chart-row">
      <div class="chart-panel">
        <div class="panel-header">
          <h3 class="panel-title">按交易所</h3>
        </div>
        <div ref="exchangeChartRef" class="chart-wrap chart-pie"></div>
        <div v-if="byExchangeList.length" class="panel-legend">
          <div v-for="r in byExchangeList" :key="r.exchange" class="legend-item">
            <span class="legend-dot" :style="{ background: exchangeColor(r.exchange) }"></span>
            <span class="legend-name">{{ exchangeLabel(r.exchange) }}</span>
            <span class="legend-value" :class="pnlClass(r.netProfit)">{{ formatMoney(r.netProfit) }}</span>
          </div>
        </div>
      </div>
      <div class="chart-panel">
        <div class="panel-header">
          <h3 class="panel-title">按交易对（净收益 Top10）</h3>
        </div>
        <div ref="symbolChartRef" class="chart-wrap chart-bar"></div>
      </div>
    </section>

    <section class="quick-section">
      <h3 class="panel-title">快捷入口</h3>
      <div class="quick-grid">
        <router-link v-for="q in quickLinks" :key="q.to" :to="q.to" class="quick-card">
          <div class="quick-icon" :style="{ '--qc': q.color }">
            <el-icon :size="22"><component :is="q.icon" /></el-icon>
          </div>
          <div class="quick-info">
            <span class="quick-name">{{ q.name }}</span>
            <span class="quick-desc">{{ q.desc }}</span>
          </div>
          <el-icon class="quick-arrow"><ArrowRight /></el-icon>
        </router-link>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, markRaw } from 'vue'
import { ElMessage } from 'element-plus'
import {
  User, Connection, TrendCharts, Cpu, List, PieChart,
  ArrowRight, Wallet, Money, DataAnalysis,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { analyticsApi } from '@/api/analytics'
import type { ProfitSummary, ProfitTrendPoint, ProfitByExchangeItem, ProfitBySymbolItem, ExchangeCode } from '@/api/analytics'
import { agentsApi } from '@/api/agents'
import type { AgentListItem } from '@/api/agents'

const periodLabel = ref('30')
const loading = ref(false)
const summary = ref<ProfitSummary | null>(null)
const trendPoints = ref<ProfitTrendPoint[]>([])
const byExchangeList = ref<ProfitByExchangeItem[]>([])
const bySymbolList = ref<ProfitBySymbolItem[]>([])
const agentStats = ref({ total: 0, running: 0 })

const trendChartRef = ref<HTMLElement | null>(null)
const exchangeChartRef = ref<HTMLElement | null>(null)
const symbolChartRef = ref<HTMLElement | null>(null)
let trendChart: ECharts | null = null
let exchangeChart: ECharts | null = null
let symbolChart: ECharts | null = null

const statCards = computed(() => [
  {
    label: '总收益', icon: markRaw(TrendCharts), color: '#2563EB', bg: 'rgba(56,189,248,0.12)',
    value: formatMoney(summary.value?.totalProfit),
    cls: pnlClass(summary.value?.totalProfit),
  },
  {
    label: '总手续费', icon: markRaw(Wallet), color: '#94A3B8', bg: 'rgba(148,163,184,0.1)',
    value: formatMoney(summary.value?.totalFee), cls: '',
  },
  {
    label: '净收益', icon: markRaw(Money), color: '#16A34A', bg: 'rgba(34,197,94,0.12)',
    value: formatMoney(summary.value?.netProfit),
    cls: pnlClass(summary.value?.netProfit),
  },
  {
    label: '收益率', icon: markRaw(DataAnalysis), color: '#2563EB', bg: 'rgba(139,92,246,0.12)',
    value: summary.value?.returnRate ?? '-',
    cls: pnlClass(summary.value?.returnRate),
  },
  {
    label: '运行中 Agent', icon: markRaw(Cpu), color: '#F59E0B', bg: 'rgba(245,158,11,0.12)',
    value: `${agentStats.value.running} / ${agentStats.value.total}`, cls: '',
  },
])

const quickLinks = [
  { to: '/users', name: '用户管理', desc: '管理系统用户与权限', icon: markRaw(User), color: '#2563EB' },
  { to: '/exchange-accounts', name: '交易所配置', desc: '绑定与配置交易所账户', icon: markRaw(Connection), color: '#2563EB' },
  { to: '/positions', name: '持仓管理', desc: '查看与管理当前持仓', icon: markRaw(TrendCharts), color: '#F59E0B' },
  { to: '/agents', name: 'Agent 交易', desc: '配置与运行交易 Agent', icon: markRaw(Cpu), color: '#2563EB' },
  { to: '/orders', name: '交易记录', desc: '查看历史委托与成交', icon: markRaw(List), color: '#2563EB' },
  { to: '/analytics', name: '收益分析', desc: '收益与回撤分析报表', icon: markRaw(PieChart), color: '#16A34A' },
  { to: '/technical-analysis', name: '技术指标分析', desc: '多周期指标与 Agent 报告', icon: markRaw(TrendCharts), color: '#2563EB' },
]

function getDateRange() {
  const days = Number(periodLabel.value) || 30
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - days)
  return {
    from: start.toISOString().slice(0, 10),
    to: end.toISOString().slice(0, 10),
    period: 'day' as const,
  }
}

function onPeriodChange() { fetchAll() }

function exchangeLabel(code: ExchangeCode): string {
  const map: Record<ExchangeCode, string> = { binance: 'Binance', okx: 'OKX', bybit: 'Bybit' }
  return map[code] ?? code
}

const EXCHANGE_COLORS: Record<ExchangeCode, string> = {
  binance: '#F0B90B',
  okx: '#2563EB',
  bybit: '#2563EB',
}

function exchangeColor(code: ExchangeCode): string {
  return EXCHANGE_COLORS[code] ?? '#2563EB'
}

function formatMoney(s?: string | null): string {
  if (s == null) return '-'
  const n = parseFloat(s)
  if (Number.isNaN(n)) return s
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pnlClass(val?: string | null): string {
  if (!val) return ''
  const n = parseFloat(String(val).replace('%', ''))
  if (Number.isNaN(n)) return ''
  if (n > 0) return 'text-profit'
  if (n < 0) return 'text-loss'
  return ''
}

async function fetchAll() {
  loading.value = true
  const { from, to, period } = getDateRange()
  const params = { from, to, period }
  try {
    const [summaryRes, trendRes, byExRes, bySymRes, agentsRes] = await Promise.all([
      analyticsApi.getProfitSummary(params),
      analyticsApi.getProfitTrend(params),
      analyticsApi.getProfitByExchange(params),
      analyticsApi.getProfitBySymbol(params),
      agentsApi.getList().catch(() => ({ list: [] as AgentListItem[], total: 0 })),
    ])
    summary.value = summaryRes
    trendPoints.value = trendRes.points ?? []
    byExchangeList.value = byExRes.list ?? []
    bySymbolList.value = (bySymRes.list ?? []).slice(0, 10)
    const list = agentsRes.list ?? []
    const total = agentsRes.total ?? list.length
    const running = list.filter((a: AgentListItem) => a.status === 'running').length
    agentStats.value = { total, running }
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载失败')
  } finally {
    loading.value = false
  }
  renderTrendChart()
  renderExchangeChart()
  renderSymbolChart()
}

const chartTextColor = '#64748B'
const chartGridColor = 'rgba(148,163,184,0.08)'

function renderTrendChart() {
  if (!trendChartRef.value) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendChartRef.value, chartTheme)
  const dates = trendPoints.value.map((p) => p.date)
  const values = trendPoints.value.map((p) => p.profit == null ? null : parseFloat(p.cumulative ?? p.profit))
  trendChart.setOption({
    grid: { left: 56, right: 32, top: 28, bottom: 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0F172A',
      borderColor: '#334155',
      textStyle: { color: '#FFFFFF', fontSize: 12 },
    },
    xAxis: {
      type: 'category', data: dates, boundaryGap: false,
      axisLabel: { color: chartTextColor, fontSize: 11 },
      axisLine: { lineStyle: { color: chartGridColor } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value', name: '累计收益',
      nameTextStyle: { color: chartTextColor, fontSize: 11 },
      axisLabel: { color: chartTextColor, fontSize: 11 },
      splitLine: { lineStyle: { color: chartGridColor } },
    },
    series: [{
      name: '累计收益', type: 'line', smooth: true, data: values, showSymbol: false,
      lineStyle: { width: 2.5, color: '#2563EB' },
      areaStyle: { color: 'rgba(37,99,235,0.08)' },
    }],
  })
}

function renderExchangeChart() {
  if (!exchangeChartRef.value) return
  if (exchangeChart) exchangeChart.dispose()
  exchangeChart = echarts.init(exchangeChartRef.value, chartTheme)
  if (!byExchangeList.value.length) {
    exchangeChart.setOption({ title: { text: '暂无数据', left: 'center', top: 'middle', textStyle: { color: '#64748B', fontSize: 13 } } })
    return
  }
  const data = byExchangeList.value.filter(r => r.netProfit != null).map((r) => ({
    name: exchangeLabel(r.exchange),
    value: Math.abs(parseFloat(r.netProfit ?? 'NaN')),
    itemStyle: { color: EXCHANGE_COLORS[r.exchange] ?? '#2563EB' },
  }))
  exchangeChart.setOption({
    tooltip: {
      trigger: 'item', formatter: '{b}: {c}',
      backgroundColor: '#0F172A',
      borderColor: '#334155',
      textStyle: { color: '#FFFFFF', fontSize: 12 },
    },
    series: [{
      type: 'pie', radius: ['45%', '70%'], center: ['50%', '50%'], data,
      label: { color: chartTextColor, fontSize: 12 },
      labelLine: { length: 12, lineStyle: { color: 'rgba(148,163,184,0.3)' } },
      emphasis: { scaleSize: 6 },
    }],
  })
}

function renderSymbolChart() {
  if (!symbolChartRef.value) return
  if (symbolChart) symbolChart.dispose()
  symbolChart = echarts.init(symbolChartRef.value, chartTheme)
  if (!bySymbolList.value.length) {
    symbolChart.setOption({ title: { text: '暂无数据', left: 'center', top: 'middle', textStyle: { color: '#64748B', fontSize: 13 } } })
    return
  }
  const names = bySymbolList.value.map((r) => r.symbol)
  const values = bySymbolList.value.map((r) => parseFloat(r.netProfit ?? 'NaN'))
  symbolChart.setOption({
    grid: { left: 52, right: 24, top: 16, bottom: 36 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0F172A',
      borderColor: '#334155',
      textStyle: { color: '#FFFFFF', fontSize: 12 },
    },
    xAxis: {
      type: 'category', data: names,
      axisLabel: { color: chartTextColor, fontSize: 10, rotate: 30 },
      axisLine: { lineStyle: { color: chartGridColor } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: chartTextColor, fontSize: 11 },
      splitLine: { lineStyle: { color: chartGridColor } },
    },
    series: [{
      type: 'bar', barWidth: '55%',
      data: values.map((v) => ({
        value: v,
        itemStyle: {
          color: v >= 0 ? '#16A34A' : '#DC2626',
          borderRadius: [4, 4, 0, 0],
        },
      })),
    }],
  })
}

function onResize() {
  trendChart?.resize()
  exchangeChart?.resize()
  symbolChart?.resize()
}

onMounted(() => {
  fetchAll()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  trendChart?.dispose()
  exchangeChart?.dispose()
  symbolChart?.dispose()
})
</script>

<style scoped>
.dashboard-page {
  max-width: 1440px;
  margin: 0 auto;
}

.dashboard-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: var(--spacing-lg);
}
.header-text .page-title {
  margin-bottom: 6px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ---- 指标卡片 ---- */
.stats-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.stat-card {
  position: relative;
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  padding: 20px;
  border: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  gap: 16px;
  overflow: hidden;
  transition: all var(--transition-normal);
}
.stat-card:hover {
  border-color: var(--color-border-active);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}

.stat-glow {
  position: absolute;
  top: -20px;
  right: -20px;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  opacity: 0.08;
  filter: blur(24px);
  pointer-events: none;
}

.stat-icon-wrap {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  background: var(--stat-bg);
  color: var(--stat-color);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.stat-label {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}
.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

/* ---- 图表面板 ---- */
.chart-section {
  margin-bottom: var(--spacing-lg);
}

.chart-panel {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.panel-title {
  font-size: var(--font-size-card-title);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.chart-trend {
  height: 320px;
  width: 100%;
}

.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.chart-pie {
  height: 260px;
  width: 100%;
}
.chart-bar {
  height: 260px;
  width: 100%;
}

.panel-legend {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-desc);
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.legend-name {
  color: var(--color-text-secondary);
}
.legend-value {
  font-weight: 600;
  color: var(--color-text-primary);
}

/* ---- 快捷入口 ---- */
.quick-section {
  margin-top: var(--spacing-lg);
}
.quick-section > .panel-title {
  margin-bottom: var(--spacing-md);
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-md);
}

.quick-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  text-decoration: none;
  color: inherit;
  transition: all var(--transition-normal);
}
.quick-card:hover {
  border-color: var(--color-border-active);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}

.quick-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--qc) 15%, transparent);
  color: var(--qc);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.quick-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.quick-name {
  font-size: var(--font-size-body);
  font-weight: 600;
  color: var(--color-text-primary);
}
.quick-desc {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
}

.quick-arrow {
  color: var(--color-text-disabled);
  font-size: 14px;
  flex-shrink: 0;
  transition: color var(--transition-fast);
}
.quick-card:hover .quick-arrow {
  color: var(--color-primary);
}

@media (max-width: 1200px) {
  .stats-row { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .chart-row { grid-template-columns: 1fr; }
}
</style>

