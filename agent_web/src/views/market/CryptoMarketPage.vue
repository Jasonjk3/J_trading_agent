<template>
  <div class="market-page">
    <header class="page-heading">
      <div><h1>大盘走势</h1><p>快速掌握核心资产趋势与市场强弱</p></div>
      <div class="refresh-area"><span>{{ updatedAt ? `行情更新于 ${updatedAt}` : '等待行情更新' }}</span><el-button :icon="Refresh" :loading="refreshing || loading" @click="refreshAll">刷新</el-button></div>
    </header>

    <section class="overview" aria-label="主流资产行情">
      <button v-for="symbol in overviewSymbols" :key="symbol" class="ticker" :class="{ selected: form.symbol === symbol }" @click="selectSymbol(symbol)">
        <span class="ticker-name">{{ symbol }}</span>
        <div><strong>{{ price(quotes[symbol]?.latestPrice) }}</strong><span :class="tone(quotes[symbol]?.change24h)">{{ percent(quotes[symbol]?.change24h, true) }}</span></div>
      </button>
      <div class="breadth"><span class="ticker-name">三币种观察</span><div><strong>{{ overviewSummary }}</strong><span>BTC · ETH · SOL</span></div></div>
    </section>

    <div class="market-grid">
      <section class="surface chart-panel" v-loading="loading">
        <div class="chart-toolbar">
          <div class="symbol-controls">
            <strong class="current-symbol">{{ form.symbol }}</strong>
            <el-button class="favorite-button" text :type="isFavorite ? 'primary' : 'default'" :icon="isFavorite ? StarFilled : Star" :loading="favoriteLoading" :aria-label="isFavorite ? '取消自选' : '添加自选'" :title="isFavorite ? '取消自选' : '添加自选'" @click="toggleFavorite" />
          </div>
          <el-select v-model="searchSelection" class="symbol-search" filterable remote remote-show-suffix clearable :remote-method="loadSymbols" :loading="searchLoading" aria-label="搜索其他交易对" placeholder="搜索币种，如 BTC / ETH" no-match-text="未找到匹配交易对" @change="onSearchSelect">
            <template #prefix><el-icon><Search /></el-icon></template>
            <el-option v-for="item in availableSymbols" :key="item" :label="item" :value="item" />
          </el-select>
          <div class="intervals" aria-label="K 线周期"><button v-for="interval in intervals" :key="interval" :class="{ active: form.interval === interval }" :aria-pressed="form.interval === interval" @click="selectInterval(interval)">{{ interval }}</button></div>
        </div>
        <div class="quote-head"><strong>{{ price(indicators?.latestPrice) }}</strong><span :class="tone(indicators?.change24h)">{{ percent(indicators?.change24h, true) }}</span><span class="quote-unit">USDT · 24H 涨跌</span></div>
        <div v-if="error" class="chart-message" role="alert">{{ error }}<el-button link type="primary" @click="fetchData">重试</el-button></div>
        <div v-else-if="!loading && !klines.length" class="chart-message">暂无 K 线数据，请切换交易对或周期</div>
        <div ref="chartEl" class="chart" :class="{ hidden: error || (!loading && !klines.length) }" role="img" :aria-label="`${form.symbol} ${form.interval} K线及成交量`" />
      </section>

      <aside class="surface snapshot" v-loading="loading">
        <h2>市场快照</h2><strong class="trend" :class="recommendationTone">{{ recommendation }}</strong><span class="scope">{{ form.symbol }} · {{ form.interval }} 周期</span>
        <dl class="facts"><div><dt>24H 高</dt><dd>{{ price(indicators?.high24h) }}</dd></div><div><dt>24H 低</dt><dd>{{ price(indicators?.low24h) }}</dd></div><div><dt>24H 成交量</dt><dd>{{ compact(indicators?.volume24h) }}</dd></div><div><dt>波动率</dt><dd>{{ percent(indicators?.volatility) }}</dd></div></dl>
        <div class="signals"><h2>核心信号</h2><div><span>均线</span><strong>{{ maSignal }}</strong></div><div><span>RSI <small>{{ price(indicators?.rsi14) }}</small></span><strong>{{ rsiSignal }}</strong></div><div><span>MACD</span><strong>{{ macdSignal }}</strong></div></div>
        <p class="insight">{{ insight }}</p>
        <details class="raw-indicators"><summary>查看指标数值</summary><dl class="facts"><div v-for="item in indicatorRows" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ price(item.value) }}</dd></div></dl></details>
      </aside>

      <section class="surface watchlist">
        <div class="section-heading"><h2>我的自选 <small>{{ favorites.length }}</small></h2><el-button link type="primary" @click="managing = !managing">{{ managing ? '完成管理' : '管理自选' }}</el-button></div>
        <p v-if="favoritesError" class="list-message" role="alert">自选加载失败 <el-button link type="primary" @click="loadFavorites">重试</el-button></p>
        <p v-else-if="!favorites.length" class="list-message">搜索交易对，点击名称旁的星标添加自选。</p>
        <div v-else class="table-scroll"><table><thead><tr><th>交易对</th><th>最新价</th><th>24H 涨跌</th><th>24H 成交量</th><th>趋势 · 1h</th><th v-if="managing">操作</th></tr></thead><tbody><tr v-for="item in favorites" :key="item.symbol" :class="{ current: item.symbol === form.symbol }"><td><button class="symbol-link" @click="selectSymbol(item.symbol)">{{ item.symbol }}</button></td><td>{{ price(quotes[item.symbol]?.latestPrice) }}</td><td :class="tone(quotes[item.symbol]?.change24h)">{{ percent(quotes[item.symbol]?.change24h, true) }}</td><td>{{ compact(quotes[item.symbol]?.volume24h) }}</td><td>{{ trendLabel(quotes[item.symbol]?.recommendation) }}</td><td v-if="managing"><el-button link type="danger" :disabled="favoriteLoading" @click="removeFavorite(item.symbol)">移除</el-button></td></tr></tbody></table></div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search, Star, StarFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { marketApi } from '@/api/market'
import type { FavoriteSymbolItem, KlineItem, MarketIndicators, MarketInterval } from '@/api/market'

const overviewSymbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
const intervals: MarketInterval[] = ['15m', '1h', '4h', '1d']
const form = ref<{ symbol: string; interval: MarketInterval }>({ symbol: 'BTCUSDT', interval: '1h' })
const indicators = ref<MarketIndicators | null>(null)
const klines = ref<KlineItem[]>([])
const favorites = ref<FavoriteSymbolItem[]>([])
const quotes = ref<Record<string, MarketIndicators | undefined>>({})
const searchResults = ref<string[]>([])
const searchSelection = ref('')
const searchKeyword = ref('')
const loading = ref(false)
const refreshing = ref(false)
const favoriteLoading = ref(false)
const searchLoading = ref(false)
const managing = ref(false)
const favoritesError = ref(false)
const error = ref('')
const updatedAt = ref('')
const chartEl = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined
let resizeObserver: ResizeObserver | undefined
let requestId = 0
let searchId = 0
let disposed = false
const availableSymbols = computed(() => searchKeyword.value ? searchResults.value : [...new Set([form.value.symbol, ...overviewSymbols, ...favorites.value.map(item => item.symbol)])])
const symbolKey = (symbol: string) => symbol.replace(/[-/]/g, '').toUpperCase()
const currentFavorite = computed(() => favorites.value.find(item => symbolKey(item.symbol) === symbolKey(form.value.symbol)))
const isFavorite = computed(() => !!currentFavorite.value)
const overviewSummary = computed(() => {
  const values = overviewSymbols.map(symbol => number(quotes.value[symbol]?.change24h))
  if (values.some(value => value === null)) return '数据待更新'
  return `${values.filter(value => value !== null && value > 0).length} / 3 上涨`
})
function number(value?: string): number | null {
  if (value == null || value.trim() === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}
function price(value?: string) {
  const n = number(value)
  return n === null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: Math.abs(n) >= 1 ? 2 : 6 })
}
function percent(value?: string, signed = false) {
  const n = number(value)
  return n === null ? '—' : `${signed && n > 0 ? '+' : ''}${n.toFixed(2)}%`
}
function compact(value?: string) {
  const n = number(value)
  return n === null ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n)
}
function tone(value?: string) { const n = number(value); return n === null ? '' : n > 0 ? 'positive' : n < 0 ? 'negative' : '' }
function trendLabel(value?: string) { return value === 'bullish' ? '偏多趋势' : value === 'bearish' ? '偏空趋势' : value === 'neutral' ? '震荡中性' : '暂无数据' }
const recommendation = computed(() => trendLabel(indicators.value?.recommendation))
const recommendationTone = computed(() => indicators.value?.recommendation === 'bearish' ? 'negative' : 'blue')
const maSignal = computed(() => {
  const a = number(indicators.value?.ma5), b = number(indicators.value?.ma10), c = number(indicators.value?.ma20)
  if (a === null || b === null || c === null) return '暂无数据'
  return a > b && b > c ? '多头排列' : a < b && b < c ? '空头排列' : '均线交织'
})
const rsiSignal = computed(() => { const n = number(indicators.value?.rsi14); return n === null ? '暂无数据' : n >= 70 ? '超买区间' : n <= 30 ? '超卖区间' : n >= 50 ? '中性偏强' : '中性偏弱' })
const macdSignal = computed(() => { const n = number(indicators.value?.histogram); return n === null ? '暂无数据' : n > 0 ? '正向动能' : n < 0 ? '负向动能' : '动能持平' })
const insight = computed(() => {
  const p = number(indicators.value?.latestPrice), ma = number(indicators.value?.ma20)
  if (p === null || ma === null) return '行情加载后，将根据当前周期展示趋势解读。'
  return `价格位于 MA20 ${p >= ma ? '上方' : '下方'}，${maSignal.value}；RSI 处于${rsiSignal.value}。`
})
const indicatorRows = computed(() => [
  { label: 'MA5', value: indicators.value?.ma5 }, { label: 'MA10', value: indicators.value?.ma10 },
  { label: 'MA20', value: indicators.value?.ma20 }, { label: 'MACD', value: indicators.value?.macd },
  { label: 'Signal', value: indicators.value?.signal }, { label: 'Histogram', value: indicators.value?.histogram },
])
async function loadSymbols(keyword: string) {
  searchKeyword.value = keyword.trim()
  searchResults.value = []
  const id = ++searchId
  searchLoading.value = true
  try { const res = await marketApi.searchSymbols(keyword); if (id === searchId && !disposed) searchResults.value = res.list.map(item => item.symbol) }
  catch { if (id === searchId) ElMessage.error('交易对搜索失败，请重试') }
  finally { if (id === searchId) searchLoading.value = false }
}
function onSearchSelect(symbol?: string) {
  if (symbol) selectSymbol(symbol)
  searchSelection.value = ''
  searchKeyword.value = ''
}
function selectSymbol(symbol: string) { if (form.value.symbol === symbol) return; form.value.symbol = symbol; void fetchData() }
function selectInterval(interval: MarketInterval) { if (form.value.interval === interval) return; form.value.interval = interval; void fetchData() }
async function loadQuotes() {
  const symbols = [...new Set([...overviewSymbols, ...favorites.value.map(item => item.symbol)])]
  await Promise.allSettled(symbols.map(async symbol => {
    try { const result = await marketApi.getIndicators({ symbol, interval: '1h' }); if (!disposed) quotes.value[symbol] = result }
    catch { if (!disposed) quotes.value[symbol] = undefined }
  }))
}
async function loadFavorites() {
  favoritesError.value = false
  try { const result = await marketApi.getFavorites(); if (!disposed) favorites.value = result.list ?? [] }
  catch { favoritesError.value = true }
}
async function toggleFavorite() {
  if (favoriteLoading.value) return
  const symbol = form.value.symbol
  if (currentFavorite.value) { await removeFavorite(currentFavorite.value.symbol); return }
  favoriteLoading.value = true
  try { await marketApi.addFavorite({ symbol, name: symbol.replace(/-?USDT$/, '') }); await loadFavorites(); await loadQuotes(); ElMessage.success('已添加自选') }
  catch { ElMessage.error('添加自选失败') }
  finally { favoriteLoading.value = false }
}
async function removeFavorite(symbol: string) {
  favoriteLoading.value = true
  try { await marketApi.removeFavorite(symbol); favorites.value = favorites.value.filter(item => item.symbol !== symbol); ElMessage.success('已移除自选') }
  catch { ElMessage.error('移除自选失败') }
  finally { favoriteLoading.value = false }
}
async function refreshAll() {
  if (refreshing.value) return
  refreshing.value = true
  try { await Promise.all([fetchData(), loadFavorites().then(loadQuotes)]) }
  finally { refreshing.value = false }
}
async function fetchData() {
  const id = ++requestId
  const params = { ...form.value }
  loading.value = true
  error.value = ''
  indicators.value = null
  klines.value = []
  chart?.clear()
  try {
    const [kline, snapshot] = await Promise.all([marketApi.getKline({ ...params, limit: 140 }), marketApi.getIndicators(params)])
    if (id !== requestId || disposed) return
    klines.value = kline.list ?? []
    indicators.value = snapshot
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    renderChart()
  } catch { if (id === requestId && !disposed) error.value = '行情加载失败，请重试。' }
  finally { if (id === requestId) loading.value = false }
}
function renderChart() {
  if (!chartEl.value) return
  chart ??= echarts.init(chartEl.value, chartTheme)
  const rows = klines.value
  const times = rows.map(item => { const time = new Date(Number(item.time)); return Number.isNaN(time.getTime()) ? item.time : time.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', ...(form.value.interval === '1d' ? {} : { hour: '2-digit', minute: '2-digit' }) }) })
  const ma = (period: number) => rows.map((_, i) => i < period - 1 ? '-' : rows.slice(i - period + 1, i + 1).reduce((sum, item) => sum + Number(item.close), 0) / period)
  chart.setOption({
    animation: false,
    color: ['#2563eb', '#e9a12e', '#9775db'],
    legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: '#64748b', fontSize: 11 }, data: ['MA5', 'MA10', 'MA20', '成交量'] },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: '#fff', borderColor: '#e2e8f0', textStyle: { color: '#334155', fontSize: 12 } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [{ left: 12, right: 70, top: 36, height: '57%' }, { left: 12, right: 70, top: '72%', height: '15%' }],
    xAxis: [0, 1].map(index => ({ type: 'category', gridIndex: index, data: times, boundaryGap: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: index === 1, hideOverlap: true, color: '#94a3b8', fontSize: 10 }, splitLine: { show: false } })),
    yAxis: [0, 1].map(index => ({ gridIndex: index, position: 'right', scale: true, splitNumber: index === 0 ? 4 : 2, axisLabel: { color: '#94a3b8', fontSize: 10, formatter: (value: number) => Intl.NumberFormat('en-US', { notation: index === 1 ? 'compact' : 'standard', maximumFractionDigits: 2 }).format(value) }, splitLine: { lineStyle: { color: '#f0f3f8' } } })),
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 35, end: 100 }, { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 14, start: 35, end: 100, showDetail: false, borderColor: '#e9eef5', fillerColor: '#eaf1ff', dataBackground: { lineStyle: { color: '#a9bce2' }, areaStyle: { color: '#f5f8fc' } } }],
    series: [
      { name: 'K线', type: 'candlestick', data: rows.map(item => [Number(item.open), Number(item.close), Number(item.low), Number(item.high)]), itemStyle: { color: '#12a16a', color0: '#e5484d', borderColor: '#12a16a', borderColor0: '#e5484d' } },
      ...[5, 10, 20].map((period, i) => ({ name: `MA${period}`, type: 'line', data: ma(period), showSymbol: false, itemStyle: { color: ['#2563eb', '#e9a12e', '#9775db'][i] }, lineStyle: { width: 1.3 } })),
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: rows.map(item => ({ value: Number(item.volume), itemStyle: { color: Number(item.close) >= Number(item.open) ? '#94d5b9' : '#f0a6aa' } })) },
    ],
  }, true)
}
onMounted(() => {
  resizeObserver = new ResizeObserver(() => chart?.resize())
  if (chartEl.value) resizeObserver.observe(chartEl.value)
  void refreshAll()
})
onUnmounted(() => { disposed = true; requestId++; searchId++; resizeObserver?.disconnect(); chart?.dispose() })
</script>

<style scoped>
.current-symbol { font-size: 17px; font-weight: 650; }
.symbol-search { width: 260px; margin-left: auto; }
.symbol-search :deep(.el-select__wrapper) { min-height: 36px; background: #f8fafd; border-radius: 8px; box-shadow: 0 0 0 1px #dce4ef inset; }
.symbol-search :deep(.el-select__wrapper.is-focused) { box-shadow: 0 0 0 1px #2563eb inset; }
@media (max-width: 600px) { .symbol-search { width: 100%; margin-left: 0; } }
.market-page { padding: 24px; max-width: 1920px; margin: 0 auto; color: #152036; font-family: var(--font-family-base, 'PingFang SC', 'Microsoft YaHei', sans-serif); font-variant-numeric: tabular-nums; }
.page-heading, .refresh-area, .chart-toolbar, .symbol-controls, .quote-head, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-heading { margin-bottom: 20px; }
h1 { margin: 0 0 6px; font-size: 26px; letter-spacing: -.6px; } h2 { margin: 0; font-size: 16px; font-weight: 600; }
.page-heading p, .refresh-area > span, .scope, .quote-unit { color: #8591a5; font-size: 12px; margin: 0; }
.overview { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); background: white; border: 1px solid #e4eaf2; border-radius: 12px; overflow: hidden; margin-bottom: 16px; }
.ticker, .breadth { padding: 17px 22px; min-width: 0; background: white; border: 0; border-right: 1px solid #edf1f7; text-align: left; font: inherit; }
.ticker { cursor: pointer; transition: background .18s ease; }.ticker:hover { background: #f8faff; }.ticker.selected { background: #eff5ff; box-shadow: inset 0 0 0 1px #9fbeff; border-radius: 8px; }.ticker.selected .ticker-name, .ticker.selected strong { color: #2563eb; }
.ticker-name { display: block; font-size: 12px; font-weight: 600; color: #66748b; margin-bottom: 8px; }
.ticker > div, .breadth > div { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }.ticker strong, .breadth strong { font-size: 21px; font-weight: 650; }.ticker > div > span, .breadth > div > span { font-size: 12px; }.breadth > div > span { color: #8591a5; }
.market-grid { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 16px; align-items: start; }.surface { background: white; border: 1px solid #e4eaf2; border-radius: 12px; min-width: 0; }.chart-panel { padding: 20px 20px 14px; }.chart-toolbar { flex-wrap: wrap; }.symbol-controls { gap: 4px; }.symbol-controls .el-select { width: 190px; }.symbol-controls :deep(.el-select__wrapper) { box-shadow: none; font-size: 17px; font-weight: 650; padding-left: 0; }.favorite-button { font-size: 20px; }.intervals { display: flex; padding: 3px; border: 1px solid #e4eaf2; border-radius: 8px; }.intervals button { padding: 6px 13px; border: 0; border-radius: 5px; background: white; color: #718096; font: inherit; font-size: 12px; cursor: pointer; transition: background .16s; }.intervals button:hover { background: #f1f5ff; }.intervals button.active { background: #2563eb; color: white; }
.quote-head { justify-content: flex-start; flex-wrap: wrap; gap: 12px; margin: 14px 0 18px; }.quote-head > strong { font-size: 30px; letter-spacing: -.8px; }.quote-head > span { font-size: 13px; }.chart { height: clamp(320px, 42vh, 490px); width: 100%; }.chart.hidden { display: none; }.chart-message { min-height: 320px; display: flex; align-items: center; justify-content: center; gap: 12px; color: #8591a5; }
.snapshot { padding: 22px; grid-column: 2; grid-row: 1 / span 2; }.trend { display: block; margin: 20px 0 6px; font-size: 26px; letter-spacing: -.5px; }.scope { display: block; }.facts { margin: 18px 0; }.facts > div, .signals > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid #f0f3f8; font-size: 13px; }.facts dt, .signals span { color: #718096; }.facts dd { margin: 0; font-weight: 500; }.signals { border-top: 1px solid #e9eef5; padding-top: 20px; }.signals h2 { margin-bottom: 8px; }.signals strong { font-size: 12px; font-weight: 500; }.signals small { margin-left: 8px; color: #334155; }.insight { margin: 18px 0 0; padding: 14px; background: #f2f6ff; border-left: 3px solid #2563eb; border-radius: 4px; font-size: 12px; line-height: 1.9; color: #52657f; }.raw-indicators { margin-top: 18px; font-size: 12px; color: #718096; }.raw-indicators summary { cursor: pointer; padding: 8px 0; }.raw-indicators .facts { margin: 0; }
.watchlist { grid-column: 1; padding: 16px 20px 8px; }.section-heading { margin-bottom: 10px; }.section-heading small { font-weight: 400; font-size: 12px; color: #94a3b8; margin-left: 8px; }.table-scroll { overflow-x: auto; }table { border-collapse: collapse; width: 100%; font-size: 12px; white-space: nowrap; }th { text-align: right; color: #8591a5; font-weight: 500; background: #f8fafd; padding: 10px 12px; }td { padding: 11px 12px; text-align: right; border-top: 1px solid #f0f3f8; }th:first-child, td:first-child { text-align: left; }tr.current td { background: #f7faff; }.symbol-link { font: inherit; font-weight: 600; border: 0; padding: 0; background: none; cursor: pointer; color: #243249; }.symbol-link:hover { color: #2563eb; }.list-message { padding: 20px 0; color: #8591a5; font-size: 13px; }.positive { color: #0d9b65; }.negative { color: #df4651; }.blue { color: #2563eb; }button:focus-visible, summary:focus-visible { outline: 2px solid #2563eb; outline-offset: 3px; }
@media (max-width: 1200px) { .market-grid { grid-template-columns: minmax(0, 1fr) 260px; }.snapshot { padding: 18px; }.ticker, .breadth { padding: 14px; }.ticker strong, .breadth strong { font-size: 18px; }.quote-unit { display: none; } }
@media (max-width: 960px) { .market-grid { grid-template-columns: 1fr; }.snapshot { grid-column: 1; grid-row: auto; }.watchlist { grid-row: 2; }.overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }.ticker, .breadth { border-bottom: 1px solid #edf1f7; }.refresh-area > span { display: none; } }
@media (max-width: 600px) { .market-page { padding: 16px; }.chart-panel { padding: 14px; }h1 { font-size: 22px; }.quote-head > strong { font-size: 26px; }.chart-toolbar { gap: 10px; }.intervals { width: 100%; }.intervals button { flex: 1; }.chart { height: 340px; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; } }
</style>
