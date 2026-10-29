<template>
  <div class="ta-report-page page-content">
    <div class="page-card">
      <div class="report-toolbar">
        <el-button class="back-btn" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回记录
        </el-button>
        <div class="report-titles">
          <div class="report-kicker"><DataAnalysis /> AI 技术研究报告</div>
          <h2 class="page-title">{{ result?.symbol || '技术分析' }} 市场研判</h2>
          <p v-if="metaLine" class="report-meta">{{ metaLine }}</p>
        </div>
        <div v-if="result?.success" class="report-status">
          <span class="status-dot"></span>
          报告已生成
        </div>
      </div>

      <div v-loading="pageLoading" class="report-body">
        <el-alert v-if="loadError" type="error" :title="loadError" show-icon class="mb-16" :closable="false" />
        <template v-else-if="result && !result.success">
          <el-alert type="error" :title="result.error || '分析失败'" show-icon :closable="false" />
        </template>
        <template v-else-if="result?.success">
          <div class="summary-cards">
            <div class="summary-card">
              <span class="summary-label">交易对</span>
              <span class="summary-value">{{ result.symbol }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">截止日</span>
              <span class="summary-value">{{ result.analysisDate?.slice(0, 10) ?? '--' }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">模式</span>
              <span class="summary-value">{{ result.analysisMode === 'rule_based' ? '规则' : 'LLM' }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">建议</span>
              <span class="summary-value" :class="actionClass(recAction)">{{ recActionText }}</span>
            </div>
            <div class="summary-card">
              <span class="summary-label">分析模型</span>
              <span class="summary-value model-summary">{{ modelSummaryText }}</span>
            </div>
          </div>

          <div class="summary-banner">
            <div class="summary-banner-icon"><DocumentChecked /></div>
            <div>
              <span class="summary-banner-label">核心结论</span>
              <p class="summary-text">{{ result.analysis?.summary || '暂无摘要' }}</p>
            </div>
          </div>

          <div class="chart-row">
            <div class="page-card chart-panel">
              <h3 class="section-title">多维度评估</h3>
              <div ref="radarRef" class="chart-wrap chart-radar"></div>
            </div>
            <div class="page-card chart-panel">
              <h3 class="section-title">RSI(14)</h3>
              <div ref="gaugeRef" class="chart-wrap chart-gauge"></div>
            </div>
            <div class="page-card chart-panel">
              <h3 class="section-title">多空信号</h3>
              <div ref="barRef" class="chart-wrap chart-bar"></div>
            </div>
          </div>

          <div class="page-card chart-panel" v-if="klineTimes.length">
            <h3 class="section-title">收盘价走势（辅助参考，{{ marketInterval }}）</h3>
            <div ref="lineRef" class="chart-wrap chart-line"></div>
          </div>

          <div class="detail-grid">
            <div class="page-card detail-card">
              <h3 class="section-title">趋势</h3>
              <ul class="detail-list">
                <li><span class="k">方向</span>{{ trendDirection }}</li>
                <li><span class="k">强度</span>{{ trendStrength }}</li>
                <li><span class="k">说明</span>{{ trendDesc }}</li>
              </ul>
            </div>
            <div class="page-card detail-card">
              <h3 class="section-title">动量</h3>
              <ul class="detail-list">
                <li><span class="k">RSI</span>{{ momentumRsi }}</li>
                <li><span class="k">MACD</span>{{ momentumMacd }}</li>
                <li><span class="k">说明</span>{{ momentumDesc }}</li>
              </ul>
            </div>
            <div class="page-card detail-card">
              <h3 class="section-title">波动</h3>
              <ul class="detail-list">
                <li><span class="k">状态</span>{{ volStatus }}</li>
                <li><span class="k">布林位置</span>{{ volBoll }}</li>
                <li><span class="k">说明</span>{{ volDesc }}</li>
              </ul>
            </div>
          </div>

          <div class="page-card" v-if="signals.length">
            <h3 class="section-title">信号列表</h3>
            <div class="signal-tags">
              <el-tag
                v-for="(s, i) in signals"
                :key="i"
                :type="s.type === 'bearish' ? 'danger' : s.type === 'bullish' ? 'success' : 'info'"
                effect="plain"
                class="signal-tag"
              >
                {{ s.indicator }}：{{ s.description }}
              </el-tag>
            </div>
          </div>

          <div class="page-card" v-if="rec">
            <h3 class="section-title">交易建议</h3>
            <ul class="detail-list rec-list">
              <li v-if="rec.confidence != null"><span class="k">置信度</span>{{ (rec.confidence * 100).toFixed(0) }}%</li>
              <li v-if="rec.entryZone"><span class="k">入场</span>{{ rec.entryZone }}</li>
              <li v-if="rec.stopLoss"><span class="k">止损</span>{{ rec.stopLoss }}</li>
              <li v-if="rec.takeProfit"><span class="k">止盈</span>{{ rec.takeProfit }}</li>
              <li v-if="rec.riskWarning"><span class="k">风险</span>{{ rec.riskWarning }}</li>
            </ul>
          </div>

          <div class="page-card" v-if="rawRows.length">
            <h3 class="section-title">原始指标（节选）</h3>
            <el-table :data="rawRows" border size="small" class="raw-table">
              <el-table-column prop="key" label="指标" width="200" />
              <el-table-column prop="value" label="数值" />
            </el-table>
          </div>

          <el-collapse class="detail-json-collapse">
            <el-collapse-item title="完整 JSON（快照）" name="json">
              <pre class="json-pre">{{ detailJson }}</pre>
            </el-collapse-item>
          </el-collapse>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { ArrowLeft, DataAnalysis, DocumentChecked } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { technicalAnalysisApi } from '@/api/technicalAnalysis'
import type { TechnicalAnalysisResult, TaAnalysisBlock } from '@/api/technicalAnalysis'
import { marketApi } from '@/api/market'
import type { KlineItem, MarketInterval } from '@/api/market'

const SESSION_PREVIEW_KEY = 'technicalAnalysisPreview'

const route = useRoute()
const router = useRouter()

const pageLoading = ref(false)
const loadError = ref('')
const result = ref<TechnicalAnalysisResult | null>(null)
const recordMeta = ref<{ id?: string; createdAt?: string | null }>({})

const radarRef = ref<HTMLElement | null>(null)
const gaugeRef = ref<HTMLElement | null>(null)
const barRef = ref<HTMLElement | null>(null)
const lineRef = ref<HTMLElement | null>(null)
let radarChart: ECharts | null = null
let gaugeChart: ECharts | null = null
let barChart: ECharts | null = null
let lineChart: ECharts | null = null

const klineTimes = ref<string[]>([])
const klineCloses = ref<number[]>([])
const marketInterval = ref<MarketInterval>('4h')

function pick<T = string>(obj: Record<string, unknown> | undefined, ...keys: string[]): T | undefined {
  if (!obj) return undefined
  for (const k of keys) {
    const v = obj[k]
    if (v !== undefined && v !== null && v !== '') return v as T
  }
  return undefined
}

const analysis = computed(() => result.value?.analysis)

const rec = computed(() => analysis.value?.recommendation)
const recAction = computed(() =>
  pick(rec.value as Record<string, unknown>, 'action', 'Action')?.toString().toLowerCase() ?? ''
)
const recActionText = computed(() => {
  const a = recAction.value
  if (a === 'buy') return '买入 / 偏多'
  if (a === 'sell') return '卖出 / 偏空'
  if (a === 'hold') return '持有'
  if (a === 'wait') return '观望'
  return '--'
})

function actionClass(action: string) {
  if (action === 'buy') return 'text-profit'
  if (action === 'sell') return 'text-loss'
  return ''
}

const modelSummaryText = computed(() => {
  const r = result.value
  if (!r?.success) return '--'
  if (r.llmModelName) {
    return r.llmModelId != null ? `${r.llmModelName} (#${r.llmModelId})` : r.llmModelName
  }
  return '默认（环境变量）'
})

const metaLine = computed(() => {
  const parts: string[] = []
  if (recordMeta.value.createdAt) {
    parts.push(`生成时间：${formatRecordTime(recordMeta.value.createdAt)}`)
  }
  if (result.value?.symbol) {
    parts.push(`交易对：${result.value.symbol}`)
  }
  return parts.join(' · ')
})

const trend = computed(() => analysis.value?.trend as Record<string, unknown> | undefined)
const trendDirection = computed(() => pick(trend.value, 'direction', 'Direction') ?? '--')
const trendStrength = computed(() => pick(trend.value, 'strength', 'Strength') ?? '--')
const trendDesc = computed(() => pick(trend.value, 'description', 'Description') ?? '--')

const momentum = computed(() => analysis.value?.momentum as Record<string, unknown> | undefined)
const momentumRsi = computed(() => pick(momentum.value, 'rsi_status', 'rsiStatus') ?? '--')
const momentumMacd = computed(() => pick(momentum.value, 'macd_status', 'macdStatus') ?? '--')
const momentumDesc = computed(() => pick(momentum.value, 'description', 'Description') ?? '--')

const volatility = computed(() => analysis.value?.volatility as Record<string, unknown> | undefined)
const volStatus = computed(() => pick(volatility.value, 'status', 'Status') ?? '--')
const volBoll = computed(() =>
  pick(volatility.value, 'bollinger_position', 'bollingerPosition') ?? '--'
)
const volDesc = computed(() => pick(volatility.value, 'description', 'Description') ?? '--')

const signals = computed(() => result.value?.analysis?.signals ?? [])

const detailJson = computed(() => {
  try {
    return JSON.stringify(result.value, null, 2)
  } catch {
    return ''
  }
})

const rawRows = computed(() => flattenRaw(result.value?.rawIndicators ?? {}, ''))

function flattenRaw(obj: Record<string, unknown>, prefix: string): { key: string; value: string }[] {
  const rows: { key: string; value: string }[] = []
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      rows.push(...flattenRaw(v as Record<string, unknown>, path))
    } else {
      rows.push({ key: path, value: formatVal(v) })
    }
  }
  return rows.slice(0, 80)
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return '--'
  if (typeof v === 'number') return Number.isFinite(v) ? v.toFixed(6) : String(v)
  return String(v)
}

function formatRecordTime(iso?: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 19)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function scoreFromTrend(t: TaAnalysisBlock['trend']): number {
  const d = String(pick(t as Record<string, unknown> | undefined, 'direction', 'Direction') ?? '')
  if (d === 'bullish') return 78
  if (d === 'bearish') return 22
  return 50
}

function scoreFromMomentum(m: TaAnalysisBlock['momentum']): number {
  const r = String(pick(m as Record<string, unknown> | undefined, 'rsi_status', 'rsiStatus') ?? '')
  if (r === 'oversold') return 72
  if (r === 'overbought') return 28
  return 55
}

function scoreFromVolatility(v: TaAnalysisBlock['volatility']): number {
  const s = String(pick(v as Record<string, unknown> | undefined, 'status', 'Status') ?? '')
  if (s === 'high') return 35
  if (s === 'low') return 72
  return 55
}

function scoreSignals(sigs: TaAnalysisBlock['signals']): number {
  if (!sigs?.length) return 50
  let b = 0
  let bear = 0
  for (const s of sigs) {
    if (s.type === 'bullish') b++
    if (s.type === 'bearish') bear++
  }
  const t = b + bear || 1
  return Math.round((b / t) * 100)
}

function scoreConfidence(reco: TaAnalysisBlock['recommendation']): number {
  const c = pick(reco as Record<string, unknown> | undefined, 'confidence', 'Confidence')
  if (typeof c === 'number' && Number.isFinite(c)) return Math.round(c * 100)
  return 60
}

function buildRadarOption(a: TaAnalysisBlock | undefined) {
  const trend = scoreFromTrend(a?.trend)
  const mom = scoreFromMomentum(a?.momentum)
  const vol = scoreFromVolatility(a?.volatility)
  const sig = scoreSignals(a?.signals)
  const conf = scoreConfidence(a?.recommendation)
  return {
    color: ['#2563EB'],
    radar: {
      indicator: [
        { name: '趋势', max: 100 },
        { name: '动量', max: 100 },
        { name: '波动适宜', max: 100 },
        { name: '信号偏多', max: 100 },
        { name: '置信度', max: 100 },
      ],
      splitArea: { areaStyle: { color: ['#F8FAFC', '#EFF6FF'] } },
    },
    series: [
      {
        type: 'radar',
        data: [{ value: [trend, mom, vol, sig, conf], name: '评估' }],
        areaStyle: { color: 'rgba(37,99,235,0.12)' },
        lineStyle: { width: 2 },
      },
    ],
  }
}

function rsiFromRaw(raw: Record<string, unknown> | undefined): number {
  const n = Number(pick(raw, 'rsi14', 'rsi_14', 'Rsi14'))
  if (Number.isFinite(n)) return Math.min(100, Math.max(0, n))
  return 50
}

function buildGaugeOption(val: number) {
  return {
    series: [
      {
        type: 'gauge',
        min: 0,
        max: 100,
        splitNumber: 10,
        axisLine: {
          lineStyle: {
            width: 14,
            color: [
              [0.3, '#22C55E'],
              [0.7, '#F59E0B'],
              [1, '#EF4444'],
            ],
          },
        },
        pointer: { width: 5 },
        detail: { fontSize: 16, formatter: '{value}' },
        data: [{ value: Math.round(val) }],
      },
    ],
  }
}

function buildBarOption(a: TaAnalysisBlock | undefined) {
  let bull = 0
  let bear = 0
  for (const s of a?.signals ?? []) {
    if (s.type === 'bullish') bull++
    if (s.type === 'bearish') bear++
  }
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 32 },
    xAxis: { type: 'category', data: ['看多', '看空'] },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'bar',
        data: [
          { value: bull, itemStyle: { color: '#16A34A' } },
          { value: bear, itemStyle: { color: '#DC2626' } },
        ],
        barWidth: '48%',
      },
    ],
  }
}

function buildLineOption(times: string[], closes: number[]) {
  return {
    grid: { left: 48, right: 24, top: 16, bottom: 40 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: times, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', scale: true },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: '#2563EB' },
        areaStyle: {
          color: 'rgba(37,99,235,0.08)',
        },
        data: closes,
      },
    ],
  }
}

function disposeCharts() {
  radarChart?.dispose()
  gaugeChart?.dispose()
  barChart?.dispose()
  lineChart?.dispose()
  radarChart = gaugeChart = barChart = lineChart = null
}

function resizeCharts() {
  radarChart?.resize()
  gaugeChart?.resize()
  barChart?.resize()
  lineChart?.resize()
}

async function initCharts() {
  await nextTick()
  disposeCharts()
  if (!result.value?.success || !analysis.value) return

  if (radarRef.value) {
    radarChart = echarts.init(radarRef.value, chartTheme)
    radarChart.setOption(buildRadarOption(analysis.value))
  }
  if (gaugeRef.value) {
    gaugeChart = echarts.init(gaugeRef.value, chartTheme)
    gaugeChart.setOption(buildGaugeOption(rsiFromRaw(result.value.rawIndicators)))
  }
  if (barRef.value) {
    barChart = echarts.init(barRef.value, chartTheme)
    barChart.setOption(buildBarOption(analysis.value))
  }
  if (lineRef.value && klineTimes.value.length) {
    lineChart = echarts.init(lineRef.value, chartTheme)
    lineChart.setOption(buildLineOption(klineTimes.value, klineCloses.value))
  }
}

watch(
  () => [result.value, klineTimes.value.length],
  () => {
    initCharts()
  },
  { flush: 'post' }
)

function mapTimeframeToMarketInterval(tf: string): MarketInterval {
  const t = tf.toLowerCase()
  if (t === '15m' || t === '5m' || t === '1m' || t === '30m') return '15m'
  if (t === '1d' || t === '1w') return '1d'
  if (t === '4h' || t === '6h' || t === '12h' || t === '2h') return '4h'
  return '1h'
}

async function loadKlineForChart(symbol: string, tf: string) {
  klineTimes.value = []
  klineCloses.value = []
  const interval = mapTimeframeToMarketInterval(tf)
  marketInterval.value = interval
  try {
    const res = await marketApi.getKline({ symbol, interval, limit: 120 })
    const list = res.list ?? []
    klineTimes.value = list.map((k: KlineItem) => {
      const t = Number(k.time)
      if (!Number.isFinite(t)) return k.time
      const d = new Date(t)
      return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    })
    klineCloses.value = list.map((k: KlineItem) => parseFloat(k.close)).filter((n) => Number.isFinite(n))
  } catch {
    /* 忽略 */
  }
}

function goBack() {
  router.push({ name: 'TechnicalAnalysis' })
}

async function loadReport() {
  loadError.value = ''
  result.value = null
  recordMeta.value = {}

  if (route.name === 'TechnicalAnalysisRecord') {
    const id = route.params.recordId as string
    pageLoading.value = true
    try {
      const data = await technicalAnalysisApi.getRecord(id)
      recordMeta.value = { id: data.id, createdAt: data.createdAt }
      result.value = data.snapshot as TechnicalAnalysisResult
      if (result.value?.success && result.value.symbol) {
        await loadKlineForChart(result.value.symbol, result.value.timeframe || '4h')
      }
    } catch {
      loadError.value = '记录加载失败或无权访问'
    } finally {
      pageLoading.value = false
    }
    return
  }

  if (route.name === 'TechnicalAnalysisReportPreview') {
    const raw = sessionStorage.getItem(SESSION_PREVIEW_KEY)
    sessionStorage.removeItem(SESSION_PREVIEW_KEY)
    if (!raw) {
      loadError.value = '未找到报告数据，请从分析页重新生成'
      return
    }
    try {
      result.value = JSON.parse(raw) as TechnicalAnalysisResult
      if (result.value?.success && result.value.symbol) {
        await loadKlineForChart(result.value.symbol, result.value.timeframe || '4h')
      }
    } catch {
      loadError.value = '报告数据无效'
    }
  }
}

onMounted(() => {
  loadReport()
  window.addEventListener('resize', resizeCharts)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  disposeCharts()
})

watch(
  () => route.params.recordId,
  async (newId, oldId) => {
    if (route.name !== 'TechnicalAnalysisRecord' || !newId || newId === oldId) return
    await loadReport()
  }
)
</script>

<style scoped>
.ta-report-page { width: 100%; max-width: 1440px; margin: 0 auto; }
.ta-report-page > .page-card { padding: 0; background: transparent; border: 0; box-shadow: none; }
.mb-16 { margin-bottom: 16px; }

.report-toolbar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: start;
  gap: 16px;
  margin-bottom: 22px;
  padding: 4px 0 22px;
  border-bottom: 1px solid var(--color-border);
}
.back-btn { margin-top: 2px; color: var(--color-text-secondary) !important; background: #fff !important; border-color: var(--color-border) !important; }
.back-btn:hover { color: var(--color-primary) !important; background: var(--color-primary-ghost) !important; border-color: #93c5fd !important; }
.back-btn .el-icon { margin-right: 5px; }
.report-titles { min-width: 0; }
.report-kicker { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; color: var(--color-primary); font-size: 11px; font-weight: 700; letter-spacing: .06em; }
.report-kicker :deep(svg) { width: 14px; height: 14px; }
.page-title { margin: 0 0 6px; color: var(--color-text-primary); font-size: 26px; font-weight: 700; letter-spacing: -.025em; }
.report-meta { margin: 0; color: var(--color-text-muted); font-size: 12px; }
.report-status { display: inline-flex; align-items: center; gap: 7px; margin-top: 5px; padding: 6px 9px; color: var(--color-profit); background: var(--color-profit-bg); border: 1px solid var(--color-profit-border); border-radius: 7px; font-size: 11px; font-weight: 650; }
.status-dot { width: 6px; height: 6px; background: var(--color-profit); border-radius: 50%; }
.report-body { min-height: 160px; }

.summary-cards { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.summary-card { min-width: 0; min-height: 82px; display: flex; flex-direction: column; justify-content: center; gap: 6px; padding: 14px 16px; background: #fff; border: 1px solid var(--color-border); border-radius: 10px; transition: border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast); }
.summary-card:hover { transform: translateY(-1px); border-color: #bfdbfe; box-shadow: var(--shadow-card-hover); }
.summary-label { color: var(--color-text-muted); font-size: 11px; font-weight: 600; }
.summary-value { overflow: hidden; color: var(--color-text-primary); font-size: 16px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.model-summary { font-size: 12px; font-weight: 600; line-height: 1.4; white-space: normal; }
.text-profit { color: var(--color-profit) !important; }
.text-loss { color: var(--color-loss) !important; }

.summary-banner { display: flex; align-items: flex-start; gap: 13px; margin-bottom: 18px; padding: 16px 18px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; }
.summary-banner-icon { width: 34px; height: 34px; display: grid; place-items: center; flex: 0 0 auto; color: #fff; background: var(--color-primary); border-radius: 8px; }
.summary-banner-icon :deep(svg) { width: 17px; }
.summary-banner-label { display: block; margin-bottom: 4px; color: var(--color-primary); font-size: 11px; font-weight: 700; }
.summary-text { margin: 0; color: #1e3a5f; font-size: 14px; line-height: 1.7; }

.chart-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 14px; }
.chart-panel, .detail-card, .report-body > .page-card { background: #fff; border: 1px solid var(--color-border); border-radius: 10px; box-shadow: var(--shadow-card); }
.chart-panel { margin: 0; padding: 18px; }
.section-title { margin: 0 0 4px; color: var(--color-text-primary); font-size: 14px; font-weight: 650; }
.section-title::after { content: ''; display: block; width: 24px; height: 2px; margin-top: 8px; background: var(--color-primary); border-radius: 2px; }
.chart-wrap { width: 100%; height: 250px; }
.chart-radar, .chart-gauge, .chart-bar { height: 230px; }
.chart-line { height: 300px; }

.detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 14px 0; }
.detail-card { margin: 0; padding: 18px; }
.detail-list { margin: 14px 0 0; padding: 0; list-style: none; color: var(--color-text-secondary); font-size: 13px; }
.detail-list li { display: grid; grid-template-columns: 74px 1fr; gap: 8px; padding: 9px 0; line-height: 1.55; border-bottom: 1px solid var(--color-border-light); }
.detail-list li:last-child { border-bottom: 0; }
.detail-list .k { color: var(--color-text-muted); font-size: 12px; font-weight: 600; }
.rec-list .k { min-width: 56px; }

.report-body > .page-card { margin: 14px 0 0; padding: 18px; }
.signal-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.signal-tag { max-width: 100%; height: auto; padding-top: 5px !important; padding-bottom: 5px !important; line-height: 1.5; white-space: normal; }
.raw-table { width: 100%; margin-top: 14px; border: 1px solid var(--color-border); border-radius: 8px; overflow: hidden; }
.detail-json-collapse { margin-top: 14px; background: #fff; border: 1px solid var(--color-border); border-radius: 10px; overflow: hidden; }
.detail-json-collapse :deep(.el-collapse-item__header) { padding: 0 18px; font-weight: 600; }
.detail-json-collapse :deep(.el-collapse-item__content) { padding: 0 18px 18px; }
.json-pre { max-height: 320px; margin: 0; padding: 14px; overflow: auto; color: #334155; background: #f8fafc; border: 1px solid var(--color-border); border-radius: 8px; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }

@media (max-width: 1100px) {
  .summary-cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .chart-row { grid-template-columns: 1fr; }
  .chart-radar, .chart-gauge, .chart-bar { height: 260px; }
}
@media (max-width: 760px) {
  .report-toolbar { grid-template-columns: 1fr; }
  .back-btn { width: fit-content; }
  .report-status { display: none; }
  .page-title { font-size: 22px; }
  .summary-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .summary-card:last-child { grid-column: 1 / -1; }
  .detail-grid { grid-template-columns: 1fr; }
}
@media (max-width: 480px) {
  .summary-cards { grid-template-columns: 1fr; }
  .summary-card:last-child { grid-column: auto; }
  .summary-banner { padding: 14px; }
  .chart-panel, .detail-card, .report-body > .page-card { padding: 14px; }
}
</style>


