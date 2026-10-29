<template>
  <section ref="panel" class="position-chart" :class="{ expanded }" @keydown.esc="expanded = false">
    <header>
      <div class="instrument">
        <el-select :model-value="selectedId" placeholder="选择持仓交易对" aria-label="选择持仓交易对" @update:model-value="emit('select', $event)">
          <el-option v-for="row in positions" :key="row.id" :value="row.id" :label="`${row.symbol} · ${row.exchange.toUpperCase()} · ${row.side === 'long' ? '多' : '空'}`" />
        </el-select>
        <strong v-if="latest">{{ price(latest) }} <small>USDT</small></strong>
        <span class="source">OKX 行情<span v-if="position?.exchange !== 'okx'"> · 跨交易所参考</span></span>
      </div>
      <div class="controls">
        <div class="intervals" aria-label="K线周期"><button v-for="item in intervals" :key="item.value" :class="{ active: interval === item.value }" :aria-pressed="interval === item.value" @click="interval = item.value">{{ item.label }}</button></div>
        <el-button :icon="Refresh" :loading="loading" aria-label="刷新K线" @click="fetchData" />
        <el-button :icon="FullScreen" :aria-label="expanded ? '退出图表全屏' : '放大图表'" @click="expanded = !expanded; collapsed = false" />
        <el-button :icon="collapsed ? ArrowDown : ArrowUp" :aria-label="collapsed ? '展开图表' : '收起图表'" @click="collapsed = !collapsed" />
      </div>
    </header>
    <div v-show="!collapsed" v-loading="loading" class="chart-body">
      <div ref="chartEl" class="chart" role="img" :aria-label="`${position?.symbol || ''} ${interval} K线与成交量`" />
      <div v-if="!loading && (error || !rows.length)" class="chart-state"><span>{{ error || '暂无 K 线数据' }}</span><el-button v-if="error" link type="primary" @click="fetchData">重新加载</el-button></div>
    </div>
    <footer v-if="!collapsed">点击持仓行切换图表 · 滚轮缩放，拖动查看<span>{{ position?.exchange !== 'okx' ? '参考行情不代表持仓交易所价格' : '蓝色虚线为持仓成本' }}<template v-if="lastTime"> · 最新K线 {{ lastTime }}</template></span></footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDown, ArrowUp, FullScreen, Refresh } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { marketApi, type KlineItem, type MarketInterval } from '@/api/market'
import type { PositionListItem } from '@/api/positions'
const props = defineProps<{ positions: PositionListItem[]; selectedId: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const position = computed(() => props.positions.find(row => row.id === props.selectedId))
const interval = ref<MarketInterval>('1h')
const intervals: { value: MarketInterval; label: string }[] = [{ value: '15m', label: '15分' }, { value: '1h', label: '1小时' }, { value: '4h', label: '4小时' }, { value: '1d', label: '日线' }]
const collapsed = ref(false), expanded = ref(false), loading = ref(false), error = ref('')
const rows = ref<KlineItem[]>([])
const chartEl = ref<HTMLDivElement>(), panel = ref<HTMLElement>()
let chart: echarts.ECharts | undefined, observer: ResizeObserver | undefined
let requestId = 0, disposed = false
const latest = computed(() => rows.value[rows.value.length - 1]?.close)
const price = (value: string | number) => Number(value).toLocaleString('en-US', { maximumFractionDigits: Number(value) < 1 ? 8 : 2 })
function time(value: string) { const numeric = Number(value); const date = new Date(Number.isFinite(numeric) ? (numeric < 1e12 ? numeric * 1000 : numeric) : value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
const lastTime = computed(() => rows.value.length ? time(rows.value[rows.value.length - 1]!.time) : '')
async function fetchData() {
  const id = ++requestId
  rows.value = []; error.value = ''; chart?.clear()
  if (!position.value) { loading.value = false; return }
  const symbol = position.value.symbol
  // The shared endpoint normalizes symbols to OKX; do not silently map dated contracts.
  if (!/^[A-Z0-9]+(?:[-/]?USDT)(?:-SWAP)?$/i.test(symbol)) { error.value = '该合约暂不支持参考行情'; loading.value = false; return }
  loading.value = true
  try {
    const result = await marketApi.getKline({ symbol: symbol.replace('/', '-'), interval: interval.value, limit: 160 })
    if (disposed || id !== requestId) return
    rows.value = (result.list ?? []).filter(row => [row.open, row.close, row.high, row.low, row.volume].every(value => Number.isFinite(Number(value))))
    render()
  } catch { if (id === requestId && !disposed) error.value = '行情加载失败，请稍后重试' }
  finally { if (id === requestId && !disposed) loading.value = false }
}
function render() {
  if (!chartEl.value || !rows.value.length) return
  chart ??= echarts.init(chartEl.value, chartTheme)
  const data = rows.value, cost = Number(position.value?.costPrice)
  chart.setOption({
    animation: false,
    tooltip: { trigger: 'axis', renderMode: 'richText', axisPointer: { type: 'cross' } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [{ left: 8, right: 105, top: 16, height: '64%' }, { left: 8, right: 105, top: '76%', height: '12%' }],
    xAxis: [0, 1].map(index => ({ type: 'category', gridIndex: index, data: data.map(row => time(row.time)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: index === 1, hideOverlap: true, color: '#94a3b8', fontSize: 10 } })),
    yAxis: [0, 1].map(index => ({ gridIndex: index, position: 'right', scale: true, splitNumber: index ? 2 : 4, axisLabel: { color: '#94a3b8', fontSize: 10 }, splitLine: { show: !index, lineStyle: { color: '#eef1f5', type: 'dashed' } } })),
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 30, end: 100 }],
    series: [
      { name: 'K线', type: 'candlestick', data: data.map(row => [Number(row.open), Number(row.close), Number(row.low), Number(row.high)]), itemStyle: { color: '#12a16a', color0: '#e5484d', borderColor: '#12a16a', borderColor0: '#e5484d' }, markLine: { silent: true, symbol: 'none', data: [
        ...(Number.isFinite(cost) && cost > 0 ? [{ yAxis: cost, lineStyle: { color: '#2563eb', type: 'dashed' }, label: { formatter: `成本 ${price(cost)}`, color: '#2563eb', fontSize: 10, position: 'insideEndTop' } }] : []),
        { yAxis: Number(latest.value), lineStyle: { color: '#64748b', type: 'dotted' }, label: { formatter: price(latest.value!), color: '#475569', fontSize: 10 } },
      ] } },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: data.map(row => ({ value: Number(row.volume), itemStyle: { color: Number(row.close) >= Number(row.open) ? '#a2dcca' : '#f1b3b6' } })) },
    ],
  }, true)
}
watch(() => [props.selectedId, interval.value], fetchData)
watch(() => position.value?.costPrice, render)
function onKey(event: KeyboardEvent) { if (event.key === 'Escape') expanded.value = false }
onMounted(() => { observer = new ResizeObserver(() => chart?.resize()); if (chartEl.value) observer.observe(chartEl.value); document.addEventListener('keydown', onKey); void fetchData() })
onBeforeUnmount(() => { disposed = true; requestId++; observer?.disconnect(); chart?.dispose(); document.removeEventListener('keydown', onKey) })
defineExpose({ refresh: fetchData })
</script>

<style scoped>
.position-chart{background:#fff;border:1px solid #e8edf3;border-radius:12px;padding:16px 18px 10px;margin-bottom:18px;min-width:0}.position-chart.expanded{position:fixed;inset:20px;z-index:2100;display:flex;flex-direction:column;box-shadow:0 16px 60px #0f172a26}.expanded .chart-body{flex:1}.expanded .chart{height:100%}header,.instrument,.controls,footer{display:flex;align-items:center;gap:12px}header{justify-content:space-between;flex-wrap:wrap}.instrument{flex-wrap:wrap}.instrument .el-select{width:280px}.instrument strong{font-size:21px;letter-spacing:-.5px}small,.source,footer{font-size:11px;color:#8490a1;font-weight:400}.controls{gap:6px}.controls .el-button{margin:0;padding:8px}.intervals{display:flex;border:1px solid #e8edf3;border-radius:7px;padding:3px}.intervals button{background:#fff;border:0;padding:6px 12px;border-radius:4px;color:#64748b;cursor:pointer}.intervals button.active{background:#eff5ff;color:#2563eb}.chart-body{position:relative;margin-top:10px}.chart{height:clamp(250px,30vh,360px);width:100%}.chart-state{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:12px;background:#fff;color:#8490a1}footer{justify-content:space-between;flex-wrap:wrap;padding:4px 0;gap:6px}button:focus-visible{outline:2px solid #2563eb;outline-offset:2px}@media(max-width:760px){.instrument .el-select{width:100%}.instrument{width:100%}.position-chart{padding:12px}.controls{flex-wrap:wrap}.position-chart.expanded{inset:8px}}
</style>
<style scoped>
.chart{height:clamp(190px,23vh,300px)}
.expanded .chart{height:100%}
</style>
