<template>
  <div v-loading="loading" class="backtest-kline-chart">
    <div ref="chartRef" class="chart-container"></div>
    <div v-if="!loading && !hasData" class="chart-empty">
      <el-icon class="empty-icon"><TrendCharts /></el-icon>
      <span class="empty-text">{{ emptyText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { TrendCharts } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import {
  backtestApi,
  type BacktestDecisionRecord,
  type BacktestKlineItem,
  type BacktestTradeRecord,
  type KlineInterval,
  type LiveOpenPosition,
} from '@/api/backtest'

const props = defineProps<{
  backtestId: string
  symbol: string
  interval: KlineInterval
  startTime: string
  endTime: string
  /** 当前交易对成交记录，用于在 K 线上标注买卖动作 */
  trades?: BacktestTradeRecord[]
  /** 当前未平持仓（用于成本、目标止盈和保护止损线） */
  positions?: LiveOpenPosition[]
  /** 回测模拟当前时刻（竖线） */
  currentTime?: string
  /** 是否展示模拟当前时刻之后、回测截止时间之前的 K 线 */
  showFutureKlines?: boolean
  /** 聚焦到决策/成交时刻（竖线 + 视窗） */
  focusTime?: string | null
  /** 当前聚焦的最终决策；只允许传风控复核后的决策记录 */
  focusDecision?: BacktestDecisionRecord | null
}>()

const emit = defineEmits<{
  'trade-click': [trade: BacktestTradeRecord]
}>()

const loading = ref(false)
const klineList = ref<BacktestKlineItem[]>([])
const loadError = ref('')
const chartRef = ref<HTMLElement>()
let chart: ECharts | null = null
let categoryTimes: string[] = []

const chartKlineList = computed(() => {
  if (props.showFutureKlines || !props.currentTime) return klineList.value
  const cutoff = new Date(props.currentTime).getTime()
  if (Number.isNaN(cutoff)) return klineList.value
  return klineList.value.filter((item) => {
    const timestamp = new Date(item.time).getTime()
    return !Number.isNaN(timestamp) && timestamp <= cutoff
  })
})

const hasData = computed(() => chartKlineList.value.length > 0)
const emptyText = computed(() => loadError.value || '暂无 K 线数据')

const symbolPositions = computed(() => {
  const norm = normalizeSymbol(props.symbol)
  return (props.positions ?? []).filter((p) => normalizeSymbol(p.symbol) === norm)
})

function formatChartTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function calcMA(values: number[], period: number): Array<number | '-'> {
  return values.map((_, idx) => {
    if (idx < period - 1) return '-'
    const slice = values.slice(idx - period + 1, idx + 1)
    const sum = slice.reduce((s, v) => s + v, 0)
    return Number((sum / period).toFixed(6))
  })
}

function normalizeSymbol(value: string): string {
  return value.replace(/[-_/]/g, '').toUpperCase()
}

function normalizePrice(value: unknown): number | null {
  const price = Number(value)
  return Number.isFinite(price) && price > 0 ? price : null
}

function formatPrice(value: number): string {
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function buildPositionPriceLine(
  name: string,
  price: number,
  color: string,
  position: 'insideEndTop' | 'insideEndBottom',
): Record<string, unknown> {
  return {
    name,
    yAxis: price,
    label: {
      formatter: `${name} ${formatPrice(price)}`,
      position,
      color,
      fontSize: 11,
      fontWeight: 700,
      backgroundColor: '#FFFFFF',
      borderColor: color,
      borderWidth: 1,
      borderRadius: 4,
      padding: [3, 6],
    },
    lineStyle: {
      color,
      type: 'dashed',
      width: 1.5,
      opacity: 0.95,
    },
  }
}

function findKlineIndex(tradeTs: number, klines: BacktestKlineItem[]): number {
  if (!klines.length) return -1
  for (let i = klines.length - 1; i >= 0; i -= 1) {
    const barTs = new Date(klines[i].time).getTime()
    if (!Number.isNaN(barTs) && tradeTs >= barTs) return i
  }
  return 0
}

function findIndexByIso(iso?: string | null): number {
  if (!iso || !chartKlineList.value.length) return -1
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return -1
  return findKlineIndex(ts, chartKlineList.value)
}

function tradeActionLabel(trade: BacktestTradeRecord): string {
  if (trade.type === 'open') {
    return trade.side === 'buy' ? '开多' : '开空'
  }
  // 平仓方向必须按持仓语义展示：卖出平多，买入平空。
  return trade.side === 'sell' ? '平多' : '平空'
}

function finalDecisionActionLabel(action?: string): string {
  const labels: Record<string, string> = {
    hold: '观望',
    open_long: '开多',
    open_short: '开空',
    add_long: '加多',
    add_short: '加空',
    reduce_long: '减多',
    reduce_short: '减空',
    close_long: '平多',
    close_short: '平空',
    system_error: '系统错误',
  }
  const normalized = String(action ?? '').trim().toLowerCase()
  return labels[normalized] ?? (normalized || '未知')
}

function tradeMarkerStyle(trade: BacktestTradeRecord) {
  const isBuy = trade.side === 'buy'
  const isOpen = trade.type === 'open'
  const color = isBuy ? '#16A34A' : '#DC2626'
  return {
    color,
    fill: isOpen ? color : '#FFFFFF',
    textColor: isOpen ? '#FFFFFF' : color,
    text: isBuy ? 'B' : 'S',
    direction: isBuy ? 1 : -1,
  }
}

function buildTradeMarkPoints(
  trades: BacktestTradeRecord[],
  klines: BacktestKlineItem[],
  times: string[],
): Array<Record<string, unknown>> {
  const symbolNorm = normalizeSymbol(props.symbol)
  const bucketOffset = new Map<string, number>()
  const points: Array<Record<string, unknown>> = []
  const klineTimestamps = klines
    .map((item) => new Date(item.time).getTime())
    .filter((value) => Number.isFinite(value))
  const firstKlineTs = klineTimestamps[0]
  const lastKlineTs = klineTimestamps[klineTimestamps.length - 1]
  const intervals = klineTimestamps
    .slice(1)
    .map((value, index) => value - klineTimestamps[index])
    .filter((value) => value > 0)
  const typicalInterval = intervals.length
    ? intervals.sort((a, b) => a - b)[Math.floor(intervals.length / 2)]
    : 60 * 60 * 1000

  for (const trade of trades) {
    if (normalizeSymbol(trade.symbol) !== symbolNorm) continue
    const tradeTs = new Date(trade.timestamp).getTime()
    if (Number.isNaN(tradeTs)) continue

    if (
      !Number.isFinite(firstKlineTs)
      || !Number.isFinite(lastKlineTs)
      || tradeTs < firstKlineTs
      || tradeTs > lastKlineTs + typicalInterval
    ) continue

    const idx = findKlineIndex(tradeTs, klines)
    if (idx < 0 || idx >= times.length) continue

    const bucketKey = `${idx}:${trade.side}`
    const offset = bucketOffset.get(bucketKey) ?? 0
    bucketOffset.set(bucketKey, offset + 1)
    const style = tradeMarkerStyle(trade)
    const label = tradeActionLabel(trade)

    const kline = klines[idx]
    const markerPrice = style.direction > 0
      ? parseFloat(kline.low)
      : parseFloat(kline.high)

    points.push({
      name: label,
      coord: [times[idx], Number.isFinite(markerPrice) ? markerPrice : trade.price],
      value: trade.price,
      symbol: 'roundRect',
      symbolSize: [22, 17],
      symbolOffset: [0, style.direction * (8 + Math.min(offset, 2) * 20)],
      itemStyle: {
        color: style.fill,
        borderColor: style.color,
        borderWidth: 1.5,
      },
      label: {
        show: true,
        position: 'inside',
        formatter: style.text,
        color: style.textColor,
        fontSize: 10,
        fontWeight: 700,
      },
      emphasis: {
        scale: 1.08,
        itemStyle: { borderWidth: 2 },
      },
      trade,
    })
  }

  return points
}

function buildMarkLineData(): Array<Record<string, unknown>> {
  const lines: Array<Record<string, unknown>> = []

  for (const pos of symbolPositions.value) {
    const isLong = String(pos.side).toLowerCase() === 'long'
    const entryPrice = normalizePrice(pos.entryPrice)
    const takeProfitPrice = normalizePrice(pos.tradePlan?.takeProfitPrice)
    const stopLossPrice = normalizePrice(pos.tradePlan?.stopLossPrice)

    if (entryPrice !== null) {
      lines.push(buildPositionPriceLine(
        isLong ? '多头成本' : '空头成本',
        entryPrice,
        '#2563EB',
        'insideEndTop',
      ))
    }
    if (takeProfitPrice !== null) {
      lines.push(buildPositionPriceLine(
        '目标止盈',
        takeProfitPrice,
        '#16A34A',
        isLong ? 'insideEndTop' : 'insideEndBottom',
      ))
    }
    if (stopLossPrice !== null) {
      lines.push(buildPositionPriceLine(
        '保护止损',
        stopLossPrice,
        '#DC2626',
        isLong ? 'insideEndBottom' : 'insideEndTop',
      ))
    }
  }

  const simIdx = findIndexByIso(props.currentTime)
  const backtestStartIdx = findIndexByIso(props.startTime)
  if (
    backtestStartIdx >= 0
    && categoryTimes[backtestStartIdx]
    && backtestStartIdx !== simIdx
  ) {
    lines.push({
      name: '回测开始',
      xAxis: categoryTimes[backtestStartIdx],
      label: {
        formatter: '回测开始',
        position: 'start',
        color: '#2563EB',
        fontSize: 11,
        fontWeight: 600,
      },
      lineStyle: {
        color: '#2563EB',
        type: 'dashed',
        width: 1.5,
        opacity: 0.85,
      },
    })
  }

  if (simIdx >= 0 && categoryTimes[simIdx]) {
    lines.push({
      name: '模拟时刻',
      xAxis: categoryTimes[simIdx],
      label: {
        formatter: 'NOW',
        position: 'end',
        color: '#FFB800',
        fontSize: 11,
        fontWeight: 700,
      },
      lineStyle: {
        color: '#FFB800',
        type: 'solid',
        width: 1.5,
        opacity: 0.9,
      },
    })
  }

  const focusIdx = findIndexByIso(props.focusTime)
  if (focusIdx >= 0 && categoryTimes[focusIdx]) {
    const isDecisionFocus = Boolean(props.focusDecision)
    const focusLabel = isDecisionFocus
      ? `最终决策：${finalDecisionActionLabel(props.focusDecision?.action)}`
      : '定位'
    lines.push({
      name: focusLabel,
      xAxis: categoryTimes[focusIdx],
      label: {
        formatter: focusLabel,
        position: 'start',
        color: '#7B61FF',
        fontSize: 11,
      },
      lineStyle: {
        color: '#7B61FF',
        type: 'dotted',
        width: 1.5,
        opacity: 0.95,
      },
    })
  }

  return lines
}

function zoomToIndex(idx: number) {
  if (!chart || idx < 0 || !categoryTimes.length) return
  const total = categoryTimes.length
  const windowSize = Math.max(40, Math.floor(total * 0.25))
  let startIdx = Math.max(0, idx - Math.floor(windowSize / 2))
  let endIdx = Math.min(total - 1, startIdx + windowSize)
  if (endIdx - startIdx < windowSize) {
    startIdx = Math.max(0, endIdx - windowSize)
  }
  const start = (startIdx / Math.max(total - 1, 1)) * 100
  const end = (endIdx / Math.max(total - 1, 1)) * 100
  chart.dispatchAction({
    type: 'dataZoom',
    start,
    end,
  })
}

function updateOverlays(options?: { zoomToFocus?: boolean }) {
  if (!chart || !hasData.value) return

  const tradeMarkPoints = buildTradeMarkPoints(props.trades ?? [], chartKlineList.value, categoryTimes)
  const markLineData = buildMarkLineData()

  chart.setOption({
    series: [
      {
        name: 'K线',
        markPoint: tradeMarkPoints.length
          ? {
              symbolKeepAspect: true,
              tooltip: {
                trigger: 'item',
                backgroundColor: '#FFFFFF',
                borderColor: '#E2E8F0',
                borderWidth: 1,
                borderRadius: 8,
                padding: [10, 12],
                extraCssText: 'box-shadow: 0 10px 28px rgba(15,23,42,.12);',
                textStyle: { color: '#0F172A', fontSize: 12 },
                formatter: (param: { data?: { trade?: BacktestTradeRecord } }) => {
                  const trade = param.data?.trade
                  if (!trade) return ''
                  const pnlText = trade.type === 'close'
                    ? `<br/>盈亏: ${trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)} (${trade.pnlPercent >= 0 ? '+' : ''}${trade.pnlPercent.toFixed(2)}%)`
                    : ''
                  const reasonText = trade.reasoning
                    ? `<br/>原因: ${escapeTooltipHtml(trade.reasoning)}`
                    : ''
                  return [
                    `<strong>实际成交：${tradeActionLabel(trade)}</strong>`,
                    `时间: ${formatChartTime(trade.timestamp)}`,
                    `价格: ${trade.price}`,
                    `数量: ${trade.quantity}`,
                    `金额: ${trade.amount.toFixed(2)}`,
                  ].join('<br/>') + pnlText + reasonText
                },
              },
              data: tradeMarkPoints,
            }
          : { data: [] },
        markLine: markLineData.length
          ? {
              symbol: 'none',
              silent: true,
              animation: false,
              data: markLineData,
            }
          : { data: [] },
      },
    ],
  })

  if (options?.zoomToFocus && props.focusTime) {
    const focusIdx = findIndexByIso(props.focusTime)
    if (focusIdx >= 0) zoomToIndex(focusIdx)
  }
}

function escapeTooltipHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 将视窗定位到模拟当前时刻 */
function zoomToCurrentTime() {
  const simIdx = findIndexByIso(props.currentTime)
  if (simIdx >= 0) zoomToIndex(simIdx)
}

defineExpose({ zoomToCurrentTime })

async function fetchKlines() {
  if (!props.backtestId || !props.symbol) return
  loading.value = true
  loadError.value = ''
  try {
    const res = await backtestApi.getKline(props.backtestId, {
      symbol: props.symbol,
      includeFuture: Boolean(props.showFutureKlines),
    })
    klineList.value = res.list ?? []
    await nextTick()
    renderChart()
  } catch (e: any) {
    klineList.value = []
    loadError.value = e?.message ?? '加载 K 线失败'
    disposeChart()
  } finally {
    loading.value = false
  }
}

function disposeChart() {
  if (chart) {
    chart.off('click')
    chart.dispose()
    chart = null
  }
  categoryTimes = []
}

function renderChart() {
  if (!chartRef.value || !hasData.value) {
    disposeChart()
    return
  }

  if (chart) {
    chart.off('click')
    chart.dispose()
  }
  chart = echarts.init(chartRef.value, chartTheme)
  bindResizeObserver()

  categoryTimes = chartKlineList.value.map((k) => formatChartTime(k.time))
  const candle = chartKlineList.value.map((k) => [
    parseFloat(k.open),
    parseFloat(k.close),
    parseFloat(k.low),
    parseFloat(k.high),
  ])
  const volume = chartKlineList.value.map((k) => parseFloat(k.volume))
  const closes = chartKlineList.value.map((k) => parseFloat(k.close))
  const ma5 = calcMA(closes, 5)
  const ma10 = calcMA(closes, 10)
  const ma20 = calcMA(closes, 20)

  chart.setOption({
    animation: false,
    legend: {
      top: 4,
      textStyle: { color: '#808080' },
      data: ['K线', 'MA5', 'MA10', 'MA20', '成交量'],
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: '#1A1A1A',
      borderColor: 'rgba(255, 255, 255, 0.08)',
      borderRadius: 12,
      padding: [12, 16],
      textStyle: { color: '#fff', fontSize: 12 },
    },
    axisPointer: {
      link: [{ xAxisIndex: [0, 1] }],
    },
    grid: [
      { left: 54, right: 18, top: 36, height: '58%' },
      { left: 54, right: 18, top: '73%', height: '18%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: categoryTimes,
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.08)' } },
        axisLabel: { color: '#808080', fontSize: 11 },
        splitLine: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: categoryTimes,
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.08)' } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        scale: true,
        splitNumber: 4,
        axisLabel: { color: '#808080', fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.04)' } },
      },
      {
        gridIndex: 1,
        splitNumber: 2,
        axisLabel: { color: '#808080', fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255, 255, 255, 0.04)' } },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      {
        show: true,
        type: 'slider',
        xAxisIndex: [0, 1],
        bottom: 6,
        start: 0,
        end: 100,
        height: 18,
        borderColor: 'rgba(255, 255, 255, 0.08)',
        fillerColor: 'rgba(0, 210, 106, 0.12)',
        handleStyle: { color: '#00D26A' },
        textStyle: { color: '#808080' },
      },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: candle,
        itemStyle: {
          color: '#00D26A',
          color0: '#FF4D4D',
          borderColor: '#00D26A',
          borderColor0: '#FF4D4D',
        },
      },
      {
        name: 'MA5',
        type: 'line',
        data: ma5,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.2, color: '#F59E0B' },
      },
      {
        name: 'MA10',
        type: 'line',
        data: ma10,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.2, color: '#38BDF8' },
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma20,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.2, color: '#A78BFA' },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volume,
        itemStyle: { color: 'rgba(56, 189, 248, 0.45)' },
      },
    ],
  })

  chart.on('click', (params) => {
    const data = params.data as { trade?: BacktestTradeRecord } | null | undefined
    if (params.componentType === 'markPoint' && data?.trade) {
      emit('trade-click', data.trade)
    }
  })

  updateOverlays({ zoomToFocus: Boolean(props.focusTime) })
}

function handleResize() {
  chart?.resize()
}

let resizeObserver: ResizeObserver | null = null

function bindResizeObserver() {
  if (!chartRef.value || resizeObserver) return
  resizeObserver = new ResizeObserver(() => handleResize())
  resizeObserver.observe(chartRef.value)
}

watch(
  () => [props.backtestId, props.symbol, props.interval, props.startTime, props.endTime],
  () => { void fetchKlines() },
)

watch(
  () => props.trades,
  () => { updateOverlays() },
  { deep: true },
)

watch(
  () => props.positions,
  () => { updateOverlays() },
  { deep: true },
)

watch(
  () => props.currentTime,
  () => {
    if (props.showFutureKlines) renderChart()
    else void fetchKlines()
  },
)

watch(
  () => props.showFutureKlines,
  () => { void fetchKlines() },
)

watch(
  () => [props.focusTime, props.focusDecision?.action],
  () => { updateOverlays({ zoomToFocus: true }) },
)

onMounted(() => {
  void fetchKlines()
  window.addEventListener('resize', handleResize)
  void nextTick(() => bindResizeObserver())
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  resizeObserver?.disconnect()
  resizeObserver = null
  disposeChart()
})
</script>

<style scoped>
.backtest-kline-chart {
  position: relative;
  width: 100%;
  min-width: 0;
  min-height: 420px;
}

.chart-container {
  width: 100%;
  height: 420px;
}

.chart-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.empty-icon {
  font-size: 48px;
  color: var(--color-text-disabled);
}

.empty-text {
  font-size: 14px;
  color: var(--color-text-muted);
}
</style>
