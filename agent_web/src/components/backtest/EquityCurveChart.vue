<template>
  <div class="equity-chart">
    <div class="chart-header">
      <div class="chart-header-left">
        <h4 class="chart-title">{{ title }}</h4>
        <span
          v-if="headerStat"
          class="chart-latest"
          :class="headerStat.tone"
        >
          {{ headerStat.text }}
          <span v-if="headerStat.sub" class="chart-latest-rate">({{ headerStat.sub }})</span>
        </span>
      </div>
      <div class="chart-header-right">
        <div v-if="modeOptions.length > 1" class="mode-switch">
          <button
            v-for="opt in modeOptions"
            :key="opt.value"
            type="button"
            class="mode-btn"
            :class="{ 'is-active': activeMode === opt.value }"
            @click="activeMode = opt.value"
          >
            {{ opt.label }}
          </button>
        </div>
        <div class="chart-legend">
          <span
            v-for="item in legendItems"
            :key="item.label"
            class="legend-item"
          >
            <span class="legend-dot" :style="{ background: item.color }"></span>
            {{ item.label }}
          </span>
        </div>
      </div>
    </div>
    <div ref="chartRef" class="chart-container"></div>
    <p v-if="hasData && activeMode === 'pnl' && !hasVariation" class="chart-empty-hint">
      当前尚未产生总收益变化
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import * as echarts from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import type { TimeSeriesPoint } from '@/api/backtest'

type ChartMode = 'pnl' | 'equity' | 'drawdown'

const props = withDefaults(defineProps<{
  title?: string
  equityCurve: TimeSeriesPoint[]
  benchmarkCurve?: TimeSeriesPoint[]
  drawdownCurve?: TimeSeriesPoint[]
  initialCapital?: number
  showBenchmark?: boolean
  showDrawdown?: boolean
}>(), {
  title: '累计总收益',
  showBenchmark: false,
  showDrawdown: false,
})

const chartRef = ref<HTMLElement>()
const activeMode = ref<ChartMode>('pnl')
let chart: echarts.ECharts | null = null

const hasData = computed(() => props.equityCurve && props.equityCurve.length > 0)

const hasBenchmark = computed(() =>
  props.showBenchmark && Array.isArray(props.benchmarkCurve) && props.benchmarkCurve.length > 0,
)

const hasDrawdown = computed(() =>
  props.showDrawdown && Array.isArray(props.drawdownCurve) && props.drawdownCurve.length > 0,
)

const modeOptions = computed(() => {
  const opts: Array<{ value: ChartMode; label: string }> = [
    { value: 'pnl', label: '总收益' },
  ]
  if (hasBenchmark.value || props.equityCurve.some((p) => p.value != null)) {
    opts.push({ value: 'equity', label: '权益对比' })
  }
  if (hasDrawdown.value) {
    opts.push({ value: 'drawdown', label: '回撤' })
  }
  return opts
})

watch(
  modeOptions,
  (opts) => {
    if (!opts.some((o) => o.value === activeMode.value)) {
      activeMode.value = opts[0]?.value ?? 'pnl'
    }
  },
  { immediate: true },
)

const curvePoints = computed(() =>
  props.equityCurve.map((p) => ({
    time: p.time,
    equity: parseNum(p.value),
    totalPnl: parseNum(p.value) - (props.initialCapital ?? 0),
    totalRate: props.initialCapital
      ? ((parseNum(p.value) - props.initialCapital) / props.initialCapital) * 100
      : 0,
  })),
)

const hasVariation = computed(() => {
  const pts = curvePoints.value
  if (!pts.length) return false
  return pts.some((p) => Math.abs(p.totalPnl) > 1e-8 || Math.abs(p.totalRate) > 1e-8)
})

const legendItems = computed(() => {
  if (activeMode.value === 'drawdown') {
    return [{ label: '回撤', color: '#FF4D4D' }]
  }
  if (activeMode.value === 'equity') {
    const items = [{ label: '账户权益', color: '#00D26A' }]
    if (hasBenchmark.value) {
      items.push({ label: '做多持有', color: '#7B61FF' })
      items.push({ label: '做空持有', color: '#F59E0B' })
    }
    return items
  }
  return [{ label: '累计总收益', color: '#00D26A' }]
})

const headerStat = computed(() => {
  const pts = curvePoints.value
  if (!pts.length) return null
  const last = pts[pts.length - 1]

  if (activeMode.value === 'drawdown') {
    const dd = props.drawdownCurve ?? []
    const lastDd = dd.length ? parseNum(dd[dd.length - 1].value) : 0
    return {
      text: `${lastDd.toFixed(2)}%`,
      sub: '当前回撤',
      tone: 'text-loss',
    }
  }

  if (activeMode.value === 'equity') {
    const ic = props.initialCapital ?? 0
    const ret = ic ? ((last.equity - ic) / ic) * 100 : 0
    return {
      text: formatMoney(last.equity),
      sub: `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`,
      tone: ret >= 0 ? 'text-profit' : 'text-loss',
    }
  }

  return {
    text: formatSignedMoney(last.totalPnl),
    sub: formatPercent(last.totalRate),
    tone: last.totalPnl >= 0 ? 'text-profit' : 'text-loss',
  }
})

function parseNum(v: unknown): number {
  if (v == null || v === '') return 0
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  return Number.isFinite(n) ? n : 0
}

function formatMoney(v: number): string {
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatSignedMoney(v: number): string {
  if (!Number.isFinite(v)) return '-'
  const sign = v > 0 ? '+' : ''
  return `${sign}${formatMoney(v)}`
}

function formatPercent(v: number): string {
  if (!Number.isFinite(v)) return '-'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

function formatChartTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function buildValueMap(curve?: TimeSeriesPoint[]) {
  const map = new Map<string, number>()
  for (const p of curve ?? []) {
    map.set(p.time, parseNum(p.value))
  }
  return map
}

function getBenchmarkBaseCapital(curve?: TimeSeriesPoint[]): number {
  const configuredCapital = parseNum(props.initialCapital)
  if (configuredCapital > 0) return configuredCapital
  const firstValue = curve?.find((point) => Number.isFinite(parseNum(point.value)))?.value
  return parseNum(firstValue)
}

function invertBenchmarkEquity(longEquity: number, baseCapital: number): number {
  // 1x 做空持有：初始资金 + 初始等权空头组合的价格反向盈亏。
  return baseCapital * 2 - longEquity
}

function paddedRange(values: number[], zeroAnchor = false) {
  let min = values.length ? Math.min(...values) : 0
  let max = values.length ? Math.max(...values) : 0
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    min = 0
    max = 0
  }
  if (zeroAnchor) {
    min = Math.min(min, 0)
    max = Math.max(max, 0)
  }
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.2, 5)
    min -= pad
    max += pad
  } else {
    const span = max - min
    min -= span * 0.08
    max += span * 0.08
  }
  return { min, max }
}

let resizeObserver: ResizeObserver | null = null

function bindResizeObserver() {
  if (!chartRef.value || resizeObserver) return
  resizeObserver = new ResizeObserver(() => handleResize())
  resizeObserver.observe(chartRef.value)
}

function initChart() {
  if (!chartRef.value || !hasData.value) return
  chart = echarts.init(chartRef.value, chartTheme)
  updateChart()
  window.addEventListener('resize', handleResize)
  bindResizeObserver()
}

function updateChart() {
  if (!chart || !hasData.value) return

  const points = curvePoints.value
  const times = points.map((p) => formatChartTime(p.time))
  const benchmarkMap = buildValueMap(props.benchmarkCurve)
  const benchmarkBaseCapital = getBenchmarkBaseCapital(props.benchmarkCurve)
  const colors = {
    grid: 'rgba(255, 255, 255, 0.04)',
    text: '#808080',
  }

  let series: echarts.SeriesOption[] = []
  let yName = ''
  let yMin: number | undefined
  let yMax: number | undefined
  let accent = '#00D26A'

  if (activeMode.value === 'drawdown') {
    const ddMap = buildValueMap(props.drawdownCurve)
    const ddValues = points.map((p) => ddMap.get(p.time) ?? 0)
    const range = paddedRange(ddValues, true)
    yName = '回撤 (%)'
    yMin = range.min
    yMax = range.max
    accent = '#FF4D4D'
    series = [{
      name: '回撤',
      type: 'line',
      data: ddValues,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: accent },
      areaStyle: {
        color: 'rgba(220, 38, 38, 0.10)',
      },
    }]
  } else if (activeMode.value === 'equity') {
    const equityValues = points.map((p) => p.equity)
    const longBenchmarkValues = hasBenchmark.value
      ? points.map((p) => benchmarkMap.get(p.time) ?? null)
      : []
    const shortBenchmarkValues = longBenchmarkValues.map((value) => (
      value == null ? null : invertBenchmarkEquity(value, benchmarkBaseCapital)
    ))
    const rangeVals = [
      ...equityValues,
      ...longBenchmarkValues.filter((v): v is number => v != null),
      ...shortBenchmarkValues.filter((v): v is number => v != null),
    ]
    const range = paddedRange(rangeVals)
    yName = '权益 (USDT)'
    yMin = range.min
    yMax = range.max
    accent = '#00D26A'
    series = [{
      name: '账户权益',
      type: 'line',
      data: equityValues,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: accent },
    }]
    if (hasBenchmark.value) {
      series.push({
        name: '做多持有',
        type: 'line',
        data: longBenchmarkValues,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.6, color: '#7B61FF', type: 'dashed' },
      })
      series.push({
        name: '做空持有',
        type: 'line',
        data: shortBenchmarkValues,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.6, color: '#F59E0B', type: 'dotted' },
      })
    }
  } else {
    // 总收益由账户权益相对初始资金计算，包含已实现盈亏、未实现盈亏及交易成本。
    const pnlValues = points.map((p) => p.totalPnl)
    const lastPnl = pnlValues[pnlValues.length - 1] ?? 0
    const lineColor = lastPnl >= 0 ? '#00D26A' : '#FF4D4D'
    const areaTop = lastPnl >= 0 ? 'rgba(0, 210, 106, 0.2)' : 'rgba(255, 77, 77, 0.2)'
    const range = paddedRange(pnlValues, true)
    yName = '总收益 (USDT)'
    yMin = range.min
    yMax = range.max
    accent = lineColor
    series = [{
      name: '累计总收益',
      type: 'line',
      data: pnlValues,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: lineColor },
      areaStyle: {
        color: areaTop,
      },
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: { color: 'rgba(148,163,184,0.25)', type: 'dashed' },
        data: [{ yAxis: 0 }],
      },
    }]
  }

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1A1A1A',
      borderColor: 'rgba(255, 255, 255, 0.08)',
      borderRadius: 12,
      padding: [12, 16],
      textStyle: { color: '#fff', fontSize: 13 },
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params]
        const idx = (items[0] as { dataIndex?: number })?.dataIndex ?? 0
        const raw = points[idx]
        if (!raw) return ''
        const head = `<div style="font-weight: 600; margin-bottom: 8px; color: #B3B3B3; font-size: 12px;">${formatChartTime(raw.time)}</div>`
        if (activeMode.value === 'drawdown') {
          const ddMap = buildValueMap(props.drawdownCurve)
          const dd = ddMap.get(raw.time) ?? 0
          return `${head}<div style="color:#fff;">回撤：${dd.toFixed(2)}%</div>`
        }
        if (activeMode.value === 'equity') {
          const lines = [`<div style="color:#fff;">权益：${formatMoney(raw.equity)} USDT</div>`]
          if (hasBenchmark.value) {
            const longBenchmark = benchmarkMap.get(raw.time)
            if (longBenchmark != null) {
              const shortBenchmark = invertBenchmarkEquity(longBenchmark, benchmarkBaseCapital)
              lines.push(`<div style="color:#C4B5FD;">做多持有：${formatMoney(longBenchmark)} USDT</div>`)
              lines.push(`<div style="color:#FBBF24;">做空持有：${formatMoney(shortBenchmark)} USDT</div>`)
            }
          }
          return head + lines.join('')
        }
        const pnlSign = raw.totalPnl > 0 ? '+' : ''
        const rateSign = raw.totalRate > 0 ? '+' : ''
        return `${head}<div style="color:#fff;">总收益：${pnlSign}${raw.totalPnl.toFixed(2)} USDT (${rateSign}${raw.totalRate.toFixed(2)}%)</div>`
      },
    },
    legend: { show: false },
    grid: {
      containLabel: true,
      left: 8,
      right: 8,
      top: 48,
      bottom: 88,
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: colors.text,
        margin: 12,
      },
    },
    yAxis: {
      type: 'value',
      name: yName,
      min: yMin,
      max: yMax,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: colors.grid } },
      nameGap: 36,
      axisLabel: {
        color: colors.text,
        formatter: (val: number) => {
          if (activeMode.value === 'drawdown') return `${val.toFixed(1)}%`
          if (activeMode.value === 'equity') return val.toFixed(0)
          const sign = val > 0 ? '+' : ''
          return `${sign}${val.toFixed(0)}`
        },
      },
    },
    series,
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
      },
      {
        type: 'slider',
        start: 0,
        end: 100,
        height: 24,
        bottom: 12,
        showDetail: false,
        moveHandleSize: 6,
        borderColor: 'transparent',
        backgroundColor: 'rgba(255, 255, 255, 0.03)',
        fillerColor: 'rgba(0, 210, 106, 0.15)',
        handleStyle: { color: accent, borderColor: accent },
        textStyle: { color: colors.text, fontSize: 11 },
        dataBackground: {
          lineStyle: { opacity: 0.3 },
          areaStyle: { opacity: 0.08 },
        },
      },
    ],
  }

  chart.setOption(option, true)
  requestAnimationFrame(() => chart?.resize())
}

async function refreshChart() {
  if (!hasData.value) {
    chart?.dispose()
    chart = null
    return
  }
  await nextTick()
  if (!chart) {
    initChart()
    return
  }
  updateChart()
}

function handleResize() {
  chart?.resize()
}

onMounted(() => refreshChart())
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
})

watch(
  () => [props.equityCurve, props.benchmarkCurve, props.drawdownCurve, activeMode.value],
  () => refreshChart(),
  { deep: true },
)
</script>

<style scoped>
.equity-chart {
  background: transparent;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}

.chart-header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.chart-header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.chart-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
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

.mode-switch {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--radius-full);
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border);
}

.mode-btn {
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  cursor: pointer;
}

.mode-btn.is-active {
  background: var(--color-bg-active);
  color: var(--color-text-primary);
  font-weight: 600;
}

.chart-legend {
  display: flex;
  gap: 16px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-muted);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.chart-container {
  width: 100%;
  min-height: 400px;
  height: min(50vh, 500px);
}

.chart-empty-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-text-disabled);
  text-align: center;
}

.text-profit { color: var(--color-profit); }
.text-loss { color: var(--color-loss); }
</style>
