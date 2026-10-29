<template>
  <div class="decision-stream">
    <div class="panel-head">
      <div>
        <span class="eyebrow">DECISIONS</span>
        <h3 class="title">决策中心</h3>
      </div>
      <span v-if="truncatedHint" class="hint" :title="truncatedHint">截断</span>
      <span v-else class="hint">{{ total ?? decisions.length }} 条</span>
    </div>

    <div class="decision-filters" role="tablist" aria-label="决策筛选">
      <button
        v-for="item in decisionFilterItems"
        :key="item.value"
        type="button"
        role="tab"
        class="filter-btn"
        :class="{ 'is-active': decisionFilter === item.value }"
        :aria-selected="decisionFilter === item.value"
        @click="decisionFilter = item.value"
      >
        {{ item.label }} <span>{{ item.count }}</span>
      </button>
    </div>

    <div v-if="filteredOrdered.length === 0" class="empty">
      <span class="empty-text">等待决策...</span>
      <span class="empty-hint">当前筛选条件下暂无决策</span>
    </div>

    <div v-else ref="listRef" class="stream-list">
      <article
        v-for="(row, idx) in filteredOrdered"
        :key="getRowKey(row, idx)"
        class="decision-card"
        :class="{ 'is-trade-like': isTradeAction(row.action) }"
      >
        <button
          type="button"
          class="card-main"
          @click="openDetail(row)"
        >
          <div class="card-top">
            <el-tag :type="getActionTagType(row.action)" size="small" effect="plain">
              {{ actionLabel(row.action) }}
            </el-tag>
            <span class="time">{{ formatTime(row.timestamp) }}</span>
          </div>

          <div class="card-mid">
            <span class="symbol">{{ row.symbol || '—' }}</span>
            <span v-if="row.currentPrice != null" class="price mono">
              {{ formatPrice(row.currentPrice) }}
            </span>
          </div>

          <p class="summary">{{ summarizeDecision(row) }}</p>
          <p v-if="row.executionResult" class="summary execution-summary">
            {{ executionSummary(row) }}
          </p>

          <div v-if="chips(row).length" class="chips">
            <span v-for="chip in chips(row)" :key="chip" class="chip">{{ chip }}</span>
          </div>
        </button>
      </article>
    </div>

    <div v-if="decisionTotal > pageSize" class="stream-pagination">
      <el-pagination
        :current-page="page"
        :page-size="pageSize"
        :total="decisionTotal"
        :pager-count="5"
        layout="prev, pager, next"
        small
        @current-change="handlePageChange"
      />
    </div>

    <el-dialog
      v-model="detailVisible"
      v-loading="detailLoading"
      title="决策详情"
      width="min(900px, 92vw)"
      class="decision-detail-dialog"
      destroy-on-close
      append-to-body
    >
      <template v-if="activeDecision">
        <div class="decision-hero">
          <div class="decision-hero__top">
            <div class="dialog-meta">
              <el-tag :type="getActionTagType(activeDecision.action)" size="small" effect="dark">
                {{ actionLabel(activeDecision.action) }}
              </el-tag>
              <el-tag v-if="ruleMeta(activeDecision).decisionMode" size="small" effect="plain" type="info">
                {{ ruleMeta(activeDecision).decisionMode === 'rule' ? '规则策略' : 'AI 交易员' }}
              </el-tag>
              <el-tag v-if="ruleMeta(activeDecision).regime" size="small" effect="plain">
                {{ regimeLabel(ruleMeta(activeDecision).regime) }}
              </el-tag>
            </div>
            <span class="dialog-time">{{ formatTimeFull(activeDecision.timestamp) }}</span>
          </div>
          <div class="decision-hero__main">
            <div class="hero-copy">
              <span class="hero-label">本轮结论</span>
              <strong class="hero-title">{{ activeDecisionTitle }}</strong>
              <p>{{ activeDecisionSubtitle }}</p>
            </div>
            <div v-if="activeDecision.symbol" class="hero-market">
              <span class="hero-label">决策快照</span>
              <strong>{{ activeDecision.symbol }}</strong>
              <span v-if="activeDecision.currentPrice != null" class="hero-market-price mono">
                {{ formatPlanPrice(numberValue(activeDecision.currentPrice)) }}
              </span>
            </div>
            <div v-else-if="activeDecisionSymbols.length" class="hero-markets">
              <span class="hero-label">关注市场</span>
              <div class="hero-symbol-list">
                <span v-for="symbol in activeDecisionSymbols" :key="symbol">{{ symbol }}</span>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="shouldShowExecutionOutcome(activeDecision)"
          class="execution-outcome"
          :class="executionStatusClass(activeDecision)"
        >
          <div>
            <span class="outcome-label">执行结果</span>
            <strong>{{ executionStatusLabel(activeDecision) }}</strong>
          </div>
          <p>{{ executionSummary(activeDecision) }}</p>
        </div>

        <section v-if="activeTradePlans.length" class="plan-section plan-section--primary">
          <div class="plan-section-head">
            <div>
              <div class="section-title">LLM 交易指令</div>
              <div class="plan-section-desc">先看入场、止损和止盈；仓位与逻辑放在后面</div>
            </div>
            <span class="plan-count">{{ activeTradePlans.length }} 笔指令</span>
          </div>

          <article
            v-for="(plan, index) in activeTradePlans"
            :key="plan.clientIntentId || `${plan.symbol}-${plan.action}-${index}`"
            class="trade-plan-card"
          >
            <div class="trade-plan-head">
              <div class="trade-plan-title">
                <el-tag :type="getActionTagType(plan.action)" size="small" effect="plain">
                  {{ actionLabel(plan.action) }}
                </el-tag>
                <el-tag
                  v-if="plan.executionRole !== 'standalone'"
                  size="small"
                  effect="light"
                  type="warning"
                >
                  {{ executionRoleLabel(plan.executionRole) }}
                </el-tag>
                <strong>{{ plan.symbol || '—' }}</strong>
              </div>
              <el-tag
                v-if="plan.riskStatus"
                :type="riskStatusTagType(plan.riskStatus)"
                size="small"
                effect="light"
              >
                {{ riskStatusLabel(plan.riskStatus) }}
              </el-tag>
            </div>

            <div class="price-route">
              <div class="price-node price-node--entry">
                <span>{{ plan.orderType === 'limit' ? '限价委托' : '市价入场' }}</span>
                <strong class="mono">{{ formatPlanPrice(plan.limitPrice ?? plan.entryReference) }}</strong>
                <small>{{ plan.orderType === 'limit' ? '价格触及后成交' : '按下一可执行价成交' }}</small>
              </div>
              <div class="price-node price-node--stop">
                <span>保护止损</span>
                <strong class="mono">{{ formatPlanPrice(plan.stopLossPrice) }}</strong>
                <small>观点失效后离场</small>
              </div>
              <div class="price-node price-node--take">
                <span>目标止盈</span>
                <strong class="mono">{{ formatPlanPrice(plan.takeProfitPrice) }}</strong>
                <small>达到目标后离场</small>
              </div>
            </div>

            <div class="plan-facts">
              <div class="plan-fact">
                <span>委托类型</span>
                <strong>{{ orderTypeLabel(plan.orderType) }}</strong>
              </div>
              <div class="plan-fact">
                <span>计划仓位</span>
                <strong>{{ formatPlanSize(plan) }}</strong>
                <small v-if="plan.quantity != null">批准 {{ formatExecutionNumber(plan.quantity) }}</small>
              </div>
              <div class="plan-fact">
                <span>杠杆</span>
                <strong>{{ formatLeverage(plan) }}</strong>
              </div>
              <div class="plan-fact">
                <span>计划盈亏比</span>
                <strong>{{ formatRiskReward(plan) }}</strong>
              </div>
              <div class="plan-fact">
                <span>有效期至</span>
                <strong>{{ plan.expiresAt ? formatTimeFull(plan.expiresAt) : '未设置' }}</strong>
              </div>
            </div>

            <div class="plan-narrative-grid">
              <div v-if="plan.rationale" class="plan-copy">
                <span>为什么操作</span>
                <p>{{ plan.rationale }}</p>
              </div>
              <div v-if="plan.invalidation" class="plan-copy plan-copy--danger">
                <span>什么情况证明判断错了</span>
                <p>{{ plan.invalidation }}</p>
              </div>
            </div>
            <div v-if="plan.thesis" class="plan-copy plan-copy--muted">
              <span>交易论点</span>
              <p>{{ plan.thesis }}</p>
            </div>
            <div v-if="plan.violations.length" class="plan-copy plan-copy--danger">
              <span>风控说明</span>
              <p>{{ plan.violations.join('；') }}</p>
            </div>
            <div v-if="plan.clientIntentId" class="plan-id mono">
              意图 ID：{{ plan.clientIntentId }}
              <template v-if="plan.parentIntentId">
                · 关联首仓：{{ plan.parentIntentId }}
              </template>
            </div>
          </article>
        </section>

        <section class="decision-analysis-card">
          <div class="analysis-heading">
            <span>决策依据</span>
            <small v-if="!isTradeAction(activeDecision.action)">未新增风险暴露</small>
          </div>
          <p>{{ activeDecision.decisionAnalysis || activeDecision.reasoning || '—' }}</p>
        </section>

        <el-collapse v-model="detailSections" class="detail-more">
          <el-collapse-item
            v-if="activePlanUpdates.length || activePendingActions.length || activeNextReview"
            name="plan-context"
          >
            <template #title>
              <div class="collapse-title">
                <strong>持续计划与下次复核</strong>
                <span>{{ activePlanUpdates.length }} 个标的计划·按需展开</span>
              </div>
            </template>
            <section v-if="activePlanUpdates.length" class="secondary-section">
              <div class="plan-section-desc">本轮更新后的观点、失效条件和复核触发器</div>
              <article
                v-for="(plan, index) in activePlanUpdates"
                :key="`${plan.symbol}-${index}`"
                class="state-plan-card"
              >
                <div class="trade-plan-head">
                  <strong>{{ plan.symbol || '—' }}</strong>
                  <el-tag size="small" effect="plain">{{ planStatusLabel(plan.status) }}</el-tag>
                </div>
                <div v-if="plan.thesis" class="plan-copy">
                  <span>核心观点</span>
                  <p>{{ plan.thesis }}</p>
                </div>
                <div v-if="plan.invalidation" class="plan-copy plan-copy--danger">
                  <span>失效条件</span>
                  <p>{{ plan.invalidation }}</p>
                </div>
                <div v-if="plan.reviewTriggers.length" class="plan-copy">
                  <span>复核触发</span>
                  <div class="chips plan-chips">
                    <span v-for="item in plan.reviewTriggers" :key="item" class="chip">{{ item }}</span>
                  </div>
                </div>
              </article>
            </section>

            <section v-if="activePendingActions.length" class="secondary-section">
              <div class="detail-label">活动挂单处置</div>
              <div class="pending-actions">
                <div v-for="item in activePendingActions" :key="item.orderId" class="pending-action">
                  <el-tag size="small" effect="plain">{{ pendingActionLabel(item.action) }}</el-tag>
                  <strong>{{ item.symbol || '—' }}</strong>
                  <span>{{ item.reason || '—' }}</span>
                </div>
              </div>
            </section>

            <section v-if="activeNextReview" class="secondary-section next-review-card">
              <div class="detail-label">下次复核</div>
              <div class="next-review-time">
                {{ activeNextReview.at ? formatTimeFull(activeNextReview.at) : '按事件触发' }}
              </div>
              <div v-if="activeNextReview.events.length" class="chips plan-chips">
                <span v-for="item in activeNextReview.events" :key="item" class="chip">
                  {{ reviewEventLabel(item) }}
                </span>
              </div>
              <ul v-if="activeNextReview.conditions.length" class="condition-list">
                <li v-for="item in activeNextReview.conditions" :key="item">{{ item }}</li>
              </ul>
            </section>
          </el-collapse-item>

          <el-collapse-item
            v-if="ruleMeta(activeDecision).signals?.length || ruleMeta(activeDecision).ruleHits?.length || resolveDecisionPrompt(activeDecision) || resolveLlmRawResponse(activeDecision)"
            name="audit"
          >
            <template #title>
              <div class="collapse-title">
                <strong>技术信号与原始数据</strong>
                <span>Prompt、LLM 响应与规则命中</span>
              </div>
            </template>
            <div v-if="ruleMeta(activeDecision).signals?.length" class="detail-block">
              <div class="detail-label">信号标签</div>
              <div class="chips">
                <span v-for="signal in ruleMeta(activeDecision).signals" :key="signal" class="chip">
                  {{ signal }}
                </span>
              </div>
            </div>

            <div v-if="ruleMeta(activeDecision).ruleHits?.length" class="detail-block">
              <div class="detail-label">规则命中</div>
              <pre class="detail-pre">{{ formatRuleHits(ruleMeta(activeDecision).ruleHits) }}</pre>
            </div>

            <div v-if="resolveDecisionPrompt(activeDecision)" class="detail-block">
              <div class="detail-label-row">
                <div class="detail-label">决策 Prompt</div>
                <el-button size="small" text type="primary" @click="copyPrompt(activeDecision)">
                  复制
                </el-button>
              </div>
              <pre class="detail-pre detail-pre--prompt">{{ resolveDecisionPrompt(activeDecision) }}</pre>
            </div>

            <div v-if="resolveLlmRawResponse(activeDecision)" class="detail-block">
              <div class="detail-label">LLM 原始响应</div>
              <pre class="detail-pre detail-pre--prompt">{{ resolveLlmRawResponse(activeDecision) }}</pre>
            </div>
          </el-collapse-item>
        </el-collapse>
      </template>

      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button
          v-if="activeDecision?.symbol"
          type="primary"
          @click="focusActive"
        >
          定位到 K 线
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { backtestApi } from '@/api/backtest'
import type { BacktestActiveOrder, BacktestDecisionRecord, RuleHitRecord } from '@/api/backtest'

const props = defineProps<{
  backtestId: string
  decisions: BacktestDecisionRecord[]
  /** 服务端真实总数；decisions 通常只包含最新一页。 */
  total?: number
  /** 服务端分页页码。 */
  page?: number
  /** 服务端分页大小。 */
  pageSize?: number
  truncatedHint?: string
  /** 有新决策时是否自动滚到最新（列表顶部） */
  autoFollow?: boolean
  /** 当前撮合引擎活动委托，用于回填旧决策记录未持久化的执行价格。 */
  activeOrders?: BacktestActiveOrder[]
}>()

const emit = defineEmits<{
  'focus-symbol': [symbol: string]
  'focus-decision': [decision: BacktestDecisionRecord]
  'page-change': [payload: { page: number; pageSize: number }]
}>()

const listRef = ref<HTMLElement | null>(null)
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailSections = ref<string[]>([])
const activeDecision = ref<BacktestDecisionRecord | null>(null)
const decisionFilter = ref<'all' | 'trade' | 'observe'>('all')
const page = computed(() => props.page ?? 1)
const pageSize = computed(() => props.pageSize ?? 10)
const decisionTotal = computed(() => props.total ?? props.decisions.length)

type JsonRecord = Record<string, unknown>

interface TradePlanView {
  clientIntentId: string
  symbol: string
  action: string
  orderType: string
  executionRole: string
  parentIntentId: string
  limitPrice?: number
  sizeMode: string
  riskPctEquity?: number
  notionalUsdt?: number
  requestedQuantity?: number
  quantity?: number
  requestedLeverage?: number
  approvedLeverage?: number
  stopLossPrice?: number
  takeProfitPrice?: number
  rationale: string
  thesis: string
  invalidation: string
  expiresAt: string
  riskStatus: string
  violations: string[]
  entryReference?: number
}

interface PlanUpdateView {
  symbol: string
  status: string
  thesis: string
  invalidation: string
  reviewTriggers: string[]
}

interface PendingActionView {
  orderId: string
  symbol: string
  action: string
  reason: string
}

interface NextReviewView {
  at: string
  events: string[]
  conditions: string[]
}

const activeTradePlans = computed(() => (
  activeDecision.value ? buildTradePlans(activeDecision.value) : []
))
const activePlanUpdates = computed(() => (
  activeDecision.value ? buildPlanUpdates(activeDecision.value) : []
))
const activePendingActions = computed(() => (
  activeDecision.value ? buildPendingActions(activeDecision.value) : []
))
const activeNextReview = computed(() => (
  activeDecision.value ? buildNextReview(activeDecision.value) : null
))
const activeDecisionSymbols = computed(() => {
  const symbols = [
    activeDecision.value?.symbol,
    ...activeTradePlans.value.map((item) => item.symbol),
    ...activePlanUpdates.value.map((item) => item.symbol),
    ...activePendingActions.value.map((item) => item.symbol),
  ].filter((item): item is string => Boolean(item))
  return [...new Set(symbols)]
})
const activeDecisionTitle = computed(() => {
  const row = activeDecision.value
  if (!row) return '—'
  if (row.action === 'hold') return '本轮观望'
  if (row.action === 'system_error') return '本轮决策失败'
  const symbol = row.symbol || activeTradePlans.value[0]?.symbol || ''
  return `${symbol ? `${symbol} ` : ''}${actionLabel(row.action)}`.trim()
})
const activeDecisionSubtitle = computed(() => {
  const row = activeDecision.value
  if (!row) return ''
  if (row.action === 'hold') return '当前条件不足，本轮不新增仓位或委托'
  if (row.action === 'system_error') return '系统未产生可执行交易计划'
  if (row.executionResult?.status === 'filled') return '交易计划已成交，下方价格为 LLM 原始计划'
  if (row.executionResult?.status === 'submitted') return '限价委托已提交，正在等待市场成交'
  return '以下为 LLM 提出的交易计划与风险边界'
})

const ordered = computed(() => [...props.decisions].sort((left, right) => {
  const leftTime = new Date(left.timestamp).getTime()
  const rightTime = new Date(right.timestamp).getTime()
  if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) return 0
  return rightTime - leftTime
}))

const filteredOrdered = computed(() => {
  if (decisionFilter.value === 'trade') return ordered.value.filter((row) => isTradeAction(row.action))
  if (decisionFilter.value === 'observe') return ordered.value.filter((row) => !isTradeAction(row.action))
  return ordered.value
})

const decisionFilterItems = computed(() => {
  const tradeCount = ordered.value.filter((row) => isTradeAction(row.action)).length
  const observeCount = ordered.value.length - tradeCount
  return [
    { value: 'all' as const, label: '全部', count: decisionTotal.value },
    { value: 'trade' as const, label: '交易', count: tradeCount },
    { value: 'observe' as const, label: '观望', count: observeCount },
  ]
})

const actionLabels: Record<string, string> = {
  hold: '观望',
  system_error: '系统错误',
  open_long: '开多',
  open_short: '开空',
  add_long: '加多',
  add_short: '加空',
  reduce_long: '减多',
  reduce_short: '减空',
  close_long: '平多',
  close_short: '平空',
}

watch(
  () => {
    const newest = ordered.value[0]
    return newest
      ? `${newest.id ?? ''}:${newest.timestamp ?? ''}`
      : ''
  },
  async () => {
    await nextTick()
    if (props.autoFollow && page.value === 1 && listRef.value) listRef.value.scrollTop = 0
  },
)

watch(page, async () => {
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = 0
})

watch(
  () => props.backtestId,
  () => {
    detailVisible.value = false
    activeDecision.value = null
  },
)

function handlePageChange(nextPage: number) {
  emit('page-change', { page: nextPage, pageSize: pageSize.value })
}

function getRowKey(row: BacktestDecisionRecord, idx: number) {
  return `${row.timestamp}-${row.action}-${row.symbol ?? ''}-${idx}`
}

async function openDetail(row: BacktestDecisionRecord) {
  activeDecision.value = row
  detailSections.value = []
  detailVisible.value = true
  emitFocus(row)
  if (!row.id || !props.backtestId) return

  const requestedId = row.id
  detailLoading.value = true
  try {
    const detail = await backtestApi.getDecision(props.backtestId, requestedId)
    if (activeDecision.value?.id === requestedId) {
      activeDecision.value = detail
    }
  } catch {
    ElMessage.error('加载决策详情失败')
  } finally {
    detailLoading.value = false
  }
}

function asRecord(value: unknown): JsonRecord | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as JsonRecord
    : null
}

function asRecordArray(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.map(asRecord).filter((item): item is JsonRecord => item !== null) : []
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function numberValue(value: unknown): number | undefined {
  if (value == null || value === '') return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? '').trim()).filter(Boolean)
    : []
}

function parseJsonRecord(value: unknown): JsonRecord | null {
  const direct = asRecord(value)
  if (direct) return direct
  if (typeof value !== 'string' || !value.trim()) return null
  const text = value.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
  try {
    return asRecord(JSON.parse(text))
  } catch {
    const start = text.indexOf('{')
    const end = text.lastIndexOf('}')
    if (start < 0 || end <= start) return null
    try {
      return asRecord(JSON.parse(text.slice(start, end + 1)))
    } catch {
      return null
    }
  }
}

function resolveParsedDecision(row: BacktestDecisionRecord): JsonRecord {
  const direct = parseJsonRecord(row.parsedDecision)
  if (direct) return direct
  const audit = findChainItem(row, 'llm_audit')
  return parseJsonRecord(audit?.parsedDecision) ?? {}
}

function resolveTraderTurn(row: BacktestDecisionRecord): JsonRecord {
  const parsed = resolveParsedDecision(row)
  const embedded = asRecord(parsed.trader_turn)
  if (embedded) return embedded
  return parseJsonRecord(resolveLlmRawResponse(row)) ?? parsed
}

function buildTradePlans(row: BacktestDecisionRecord): TradePlanView[] {
  const payload = resolveParsedDecision(row)
  const turn = resolveTraderTurn(row)
  const intents = asRecordArray(turn.order_intents)
  const orderBatch = asRecordArray(payload.order_batch)
  const proposal = asRecord(payload.order_proposal)
  const checks = asRecordArray(proposal?.intents)

  const plans = intents.map((intent) => {
    const clientIntentId = stringValue(intent.client_intent_id)
    const liveOrder = resolveActiveOrder(row, clientIntentId)
    const check = checks.find((item) => stringValue(item.client_intent_id) === clientIntentId)
    const approvedFromCheck = asRecord(check?.approved_decision)
    const approved = approvedFromCheck ?? orderBatch.find(
      (item) => stringValue(item.client_intent_id) === clientIntentId,
    ) ?? {}
    const size = asRecord(intent.size) ?? {}
    const protection = asRecord(intent.protection) ?? {}
    const tradePlan = asRecord(approved.trade_plan) ?? {}
    const effect = stringValue(intent.effect)
    const positionSide = stringValue(intent.position_side)
    const limitPrice = numberValue(liveOrder?.limitPrice ?? intent.limit_price ?? approved.limit_price)
    const executionPrice = numberValue(row.executionResult?.price)
    const currentPrice = numberValue(row.currentPrice)
    const violations = asRecordArray(check?.violations).map((item) => (
      stringValue(item.message) || stringValue(item.code)
    )).filter(Boolean)

    return {
      clientIntentId,
      symbol: stringValue(intent.symbol) || stringValue(approved.symbol) || row.symbol || '',
      action: effect && positionSide ? `${effect}_${positionSide}` : row.action,
      orderType: stringValue(liveOrder?.orderType) || stringValue(intent.order_type) || stringValue(approved.order_type) || 'market',
      executionRole: stringValue(liveOrder?.executionRole) || stringValue(intent.execution_role ?? approved.execution_role) || 'standalone',
      parentIntentId: stringValue(liveOrder?.parentIntentId) || stringValue(intent.parent_intent_id ?? approved.parent_intent_id),
      limitPrice,
      sizeMode: stringValue(size.mode),
      riskPctEquity: numberValue(size.risk_pct_equity),
      notionalUsdt: numberValue(size.notional_usdt),
      requestedQuantity: numberValue(size.quantity),
      quantity: numberValue(liveOrder?.quantity ?? approved.quantity ?? row.quantity),
      requestedLeverage: numberValue(liveOrder?.requestedLeverage ?? intent.requested_leverage),
      approvedLeverage: numberValue(approved.leverage ?? row.executionResult?.approvedLeverage),
      stopLossPrice: numberValue(liveOrder?.stopLossPrice ?? protection.stop_loss_price ?? tradePlan.stop_loss_price ?? approved.stop_loss_price),
      takeProfitPrice: numberValue(liveOrder?.takeProfitPrice ?? protection.take_profit_price ?? tradePlan.take_profit_price ?? approved.take_profit_price),
      rationale: stringValue(liveOrder?.rationale) || stringValue(intent.rationale) || stringValue(approved.reason),
      thesis: stringValue(liveOrder?.thesis) || stringValue(intent.thesis) || stringValue(tradePlan.thesis),
      invalidation: stringValue(liveOrder?.invalidation) || stringValue(intent.invalidation) || stringValue(tradePlan.invalidation),
      expiresAt: stringValue(liveOrder?.expiresAt) || stringValue(intent.expires_at ?? approved.expires_at),
      riskStatus: stringValue(check?.status),
      violations,
      entryReference: limitPrice ?? executionPrice ?? currentPrice,
    }
  })

  if (plans.length || !isTradeAction(row.action)) return plans
  const tradePlan = asRecord(payload.trade_plan) ?? {}
  const execution = row.executionResult
  const liveOrder = resolveActiveOrder(row, stringValue(payload.client_intent_id))
  const legacy = legacyExecutionPlan(row)
  return [{
    clientIntentId: stringValue(payload.client_intent_id),
    symbol: stringValue(payload.symbol) || row.symbol || '',
    action: stringValue(payload.action) || row.action,
    orderType: stringValue(liveOrder?.orderType) || stringValue(execution?.orderType) || stringValue(payload.order_type) || legacy.orderType || 'market',
    executionRole: stringValue(liveOrder?.executionRole) || stringValue(execution?.executionRole) || stringValue(payload.execution_role) || 'standalone',
    parentIntentId: stringValue(liveOrder?.parentIntentId) || stringValue(execution?.parentIntentId) || stringValue(payload.parent_intent_id),
    limitPrice: numberValue(liveOrder?.limitPrice ?? execution?.limitPrice ?? payload.limit_price ?? legacy.limitPrice),
    sizeMode: '',
    quantity: numberValue(liveOrder?.quantity ?? payload.quantity ?? row.quantity),
    requestedLeverage: numberValue(liveOrder?.requestedLeverage ?? execution?.requestedLeverage ?? payload.requested_leverage),
    approvedLeverage: numberValue(payload.leverage ?? row.executionResult?.approvedLeverage),
    stopLossPrice: numberValue(liveOrder?.stopLossPrice ?? execution?.stopLossPrice ?? payload.stop_loss_price ?? tradePlan.stop_loss_price ?? legacy.stopLossPrice),
    takeProfitPrice: numberValue(liveOrder?.takeProfitPrice ?? execution?.takeProfitPrice ?? payload.take_profit_price ?? tradePlan.take_profit_price ?? legacy.takeProfitPrice),
    rationale: stringValue(liveOrder?.rationale) || stringValue(payload.reason),
    thesis: stringValue(liveOrder?.thesis) || stringValue(payload.thesis ?? tradePlan.thesis),
    invalidation: stringValue(liveOrder?.invalidation) || stringValue(payload.invalidation ?? tradePlan.invalidation),
    expiresAt: stringValue(liveOrder?.expiresAt) || stringValue(execution?.expiresAt) || stringValue(payload.expires_at),
    riskStatus: '',
    violations: [],
    entryReference: numberValue(liveOrder?.limitPrice ?? execution?.limitPrice ?? payload.limit_price ?? legacy.limitPrice ?? row.executionResult?.price ?? row.currentPrice),
  }]
}

function resolveActiveOrder(row: BacktestDecisionRecord, clientIntentId = '') {
  const rows = props.activeOrders ?? []
  const orderId = row.executionResult?.orderId
  return rows.find((item) => (
    (orderId && item.orderId === orderId)
    || (clientIntentId && item.clientIntentId === clientIntentId)
  ))
}

/**
 * 兼容修复前已落库的交易记录：旧执行回执没有结构化订单/保护字段，
 * 但中文回执与决策结论中仍保留了明确价格。仅匹配带“限价/止损/止盈/目标”
 * 语义的单一数字；新记录始终优先使用结构化字段。
 */
function legacyExecutionPlan(row: BacktestDecisionRecord) {
  const executionText = row.executionResult?.message || ''
  const analysisText = `${row.decisionAnalysis || ''}\n${row.reasoning || ''}`
  const readPrice = (text: string, pattern: RegExp) => {
    const match = text.match(pattern)
    return match ? numberValue(match[1]?.replace(/,/g, '')) : undefined
  }
  const limitPrice = readPrice(executionText, /(?:等待价格|限价(?:为|价格)?)[\s：:]*([\d,.]+)/)
  const stopLossPrice = readPrice(analysisText, /止损(?:价格|价)?[\s：:]*([\d,.]+)/)
  const takeProfitPrice = readPrice(analysisText, /(?:止盈|目标)(?:价格|价)?[\s：:]*([\d,.]+)/)
  return {
    orderType: limitPrice != null || /限价/.test(executionText) ? 'limit' : '',
    limitPrice,
    stopLossPrice,
    takeProfitPrice,
  }
}

function buildPlanUpdates(row: BacktestDecisionRecord): PlanUpdateView[] {
  return asRecordArray(resolveTraderTurn(row).plan_updates).map((item) => ({
    symbol: stringValue(item.symbol),
    status: stringValue(item.status),
    thesis: stringValue(item.thesis),
    invalidation: stringValue(item.invalidation),
    reviewTriggers: stringArray(item.review_triggers),
  }))
}

function buildPendingActions(row: BacktestDecisionRecord): PendingActionView[] {
  return asRecordArray(resolveTraderTurn(row).pending_order_actions).map((item) => ({
    orderId: stringValue(item.order_id),
    symbol: stringValue(item.symbol),
    action: stringValue(item.action),
    reason: stringValue(item.reason),
  }))
}

function buildNextReview(row: BacktestDecisionRecord): NextReviewView | null {
  const review = asRecord(resolveTraderTurn(row).next_review)
  if (!review) return null
  const result = {
    at: stringValue(review.at),
    events: stringArray(review.events),
    conditions: stringArray(review.conditions),
  }
  return result.at || result.events.length || result.conditions.length ? result : null
}

function emitFocus(row: BacktestDecisionRecord) {
  if (row.symbol) emit('focus-symbol', row.symbol)
  emit('focus-decision', row)
}

function focusActive() {
  if (!activeDecision.value) return
  emitFocus(activeDecision.value)
  detailVisible.value = false
}

function actionLabel(action: string) {
  return actionLabels[action] ?? action
}

function formatExecutionNumber(value?: number) {
  if (value == null || Number.isNaN(value)) return '-'
  return value.toLocaleString(undefined, { maximumFractionDigits: 8 })
}

function executionSummary(row: BacktestDecisionRecord) {
  const result = row.executionResult
  if (!result) return row.action === 'hold' ? '未操作' : ''
  if (result.status === 'filled') {
    return [
      `${actionLabel(result.finalAction || row.action)} ${formatExecutionNumber(result.quantity)} @ ${formatExecutionNumber(result.price)}`,
      `金额 ${formatExecutionNumber(result.amount)}`,
      `手续费 ${formatExecutionNumber(result.fee)}`,
      `操作后持仓 ${formatExecutionNumber(result.positionQuantityAfter)}`,
    ].join('；')
  }
  if (result.status === 'rejected') return `未执行：${result.message || '复核拒绝'}`
  if (result.status === 'error') return result.message || '系统错误，未执行'
  if (result.status === 'pending') return '等待执行'
  return result.message || '未操作'
}

function executionStatusLabel(row: BacktestDecisionRecord) {
  const status = row.executionResult?.status
  const labels: Record<string, string> = {
    pending: '等待执行',
    submitted: '已提交委托',
    kept: '已保留原委托',
    partially_filled: '部分成交',
    filled: '已成交',
    rejected: '未执行',
    no_action: '未操作',
    error: '执行异常',
  }
  return labels[status ?? ''] ?? '执行状态'
}

function executionStatusClass(row: BacktestDecisionRecord) {
  const status = row.executionResult?.status ?? 'pending'
  if (['filled', 'submitted', 'kept', 'partially_filled'].includes(status)) {
    return 'execution-outcome--success'
  }
  if (['rejected', 'error'].includes(status)) return 'execution-outcome--danger'
  return 'execution-outcome--neutral'
}

function shouldShowExecutionOutcome(row: BacktestDecisionRecord) {
  const status = row.executionResult?.status
  return Boolean(
    row.executionResult
    && (isTradeAction(row.action) || !['no_action', 'pending'].includes(status ?? ''))
  )
}

function isTradeAction(action: string) {
  return ['open', 'add', 'reduce', 'close'].some((prefix) => action?.startsWith(prefix))
}

function getActionTagType(action: string): 'info' | 'success' | 'danger' | 'warning' {
  if (action === 'hold') return 'info'
  if (action === 'system_error') return 'danger'
  if (action?.startsWith('open') || action?.startsWith('add')) return 'success'
  if (action?.startsWith('close')) return 'danger'
  return 'warning'
}

function formatTime(iso: string) {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatTimeFull(iso: string) {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function formatPrice(n?: number | null) {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 })
}

function formatPlanPrice(value?: number) {
  if (value == null || Number.isNaN(value)) return '未设置'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function orderTypeLabel(value: string) {
  return value === 'limit' ? '限价单' : value === 'market' ? '市价单' : value || '—'
}

function executionRoleLabel(value: string) {
  return {
    trend_starter: '趋势主动首仓',
    pullback_add: '回撤加仓',
    standalone: '独立订单',
  }[value] ?? value
}

function formatPlanSize(plan: TradePlanView) {
  if (plan.sizeMode === 'risk_budget' && plan.riskPctEquity != null) {
    return `${plan.riskPctEquity.toFixed(2)}% 权益风险`
  }
  if (plan.sizeMode === 'notional' && plan.notionalUsdt != null) {
    return `${plan.notionalUsdt.toLocaleString(undefined, { maximumFractionDigits: 2 })} USDT`
  }
  const quantity = plan.requestedQuantity ?? plan.quantity
  return quantity != null ? `${formatExecutionNumber(quantity)} 数量` : '系统计算'
}

function formatLeverage(plan: TradePlanView) {
  const approved = plan.approvedLeverage
  const requested = plan.requestedLeverage
  if (approved != null && requested != null && approved !== requested) {
    return `${approved}x（申请 ${requested}x）`
  }
  const value = approved ?? requested
  return value != null ? `${value}x` : '历史记录未保存'
}

function formatRiskReward(plan: TradePlanView) {
  const entry = plan.entryReference
  const stop = plan.stopLossPrice
  const take = plan.takeProfitPrice
  if (entry == null || stop == null || take == null) return '未设置完整目标'
  const isShort = plan.action.endsWith('_short')
  const risk = isShort ? stop - entry : entry - stop
  const reward = isShort ? entry - take : take - entry
  if (risk <= 0 || reward <= 0) return '价格方向无效'
  return `1 : ${(reward / risk).toFixed(2)}`
}

function riskStatusLabel(value: string) {
  return {
    approved: '风控通过',
    resized: '风控缩量',
    rejected: '风控拒绝',
  }[value] ?? value
}

function riskStatusTagType(value: string): 'success' | 'warning' | 'danger' | 'info' {
  if (value === 'approved') return 'success'
  if (value === 'resized') return 'warning'
  if (value === 'rejected') return 'danger'
  return 'info'
}

function planStatusLabel(value: string) {
  return ({
    watching: '观察中',
    active: '执行中',
    invalidated: '已失效',
    closed: '已结束',
  }[value] ?? value) || '未标记'
}

function pendingActionLabel(value: string) {
  return { keep: '保留', replace: '修改', cancel: '撤销' }[value] ?? value
}

function reviewEventLabel(value: string) {
  return {
    bar_closed: 'K 线收盘',
    news_arrived: '新闻到达',
    order_updated: '订单变化',
    risk_changed: '风险变化',
  }[value] ?? value
}

function regimeLabel(regime?: string) {
  if (regime === 'trending') return '趋势市'
  if (regime === 'ranging') return '震荡市'
  return regime || ''
}

function findChainItem(row: BacktestDecisionRecord, type: string) {
  return row.chainOfThought?.find(
    (item) => typeof item === 'object' && item && (item as { type?: string }).type === type,
  ) as Record<string, unknown> | undefined
}

function ruleMeta(row: BacktestDecisionRecord) {
  if (row.decisionMode || row.ruleHits?.length || row.regime) {
    return {
      decisionMode: row.decisionMode,
      regime: row.regime,
      ruleHits: row.ruleHits,
      signals: row.signals,
    }
  }
  const audit = findChainItem(row, 'rule_audit') as {
    decisionMode?: 'trader' | 'rule'
    regime?: string
    ruleHits?: RuleHitRecord[]
    signals?: string[]
  } | undefined
  return {
    decisionMode: audit?.decisionMode,
    regime: audit?.regime,
    ruleHits: audit?.ruleHits,
    signals: audit?.signals,
  }
}

function resolveDecisionPrompt(row: BacktestDecisionRecord): string {
  if (row.decisionPrompt?.trim()) return row.decisionPrompt
  const audit = findChainItem(row, 'llm_audit')
  const prompt = audit?.decisionPrompt
  return typeof prompt === 'string' ? prompt : ''
}

function resolveLlmRawResponse(row: BacktestDecisionRecord): string {
  if (row.llmRawResponse?.trim()) return row.llmRawResponse
  const audit = findChainItem(row, 'llm_audit')
  const raw = audit?.llmRawResponse
  return typeof raw === 'string' ? raw : ''
}

function summarizeDecision(row: BacktestDecisionRecord) {
  const meta = ruleMeta(row)
  const base = row.decisionAnalysis || row.reasoning || ''
  if (meta.decisionMode === 'rule' && meta.regime) {
    return base ? `${base}` : regimeLabel(meta.regime)
  }
  return base || '—'
}

function chips(row: BacktestDecisionRecord) {
  const meta = ruleMeta(row)
  const list: string[] = []
  if (meta.decisionMode === 'rule') list.push('规则')
  else if (meta.decisionMode === 'trader' || resolveDecisionPrompt(row) || row.technicalAnalysis) {
    list.push('交易员')
  }
  if (meta.regime) list.push(regimeLabel(meta.regime))
  if (meta.signals?.length) list.push(...meta.signals.slice(0, 2))
  return list
}

function formatRuleHits(hits?: RuleHitRecord[]) {
  if (!hits?.length) return '-'
  return hits
    .map((h) => {
      const parts = [h.rule_id]
      if (h.action) parts.push(h.action)
      if (h.reason) parts.push(h.reason)
      return parts.join(' · ')
    })
    .join('\n')
}

async function copyPrompt(row: BacktestDecisionRecord) {
  const text = resolveDecisionPrompt(row)
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制决策 Prompt')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.decision-stream {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
  padding: 14px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.eyebrow {
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--color-primary);
}

.title {
  margin: 2px 0 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

.decision-filters {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  flex-shrink: 0;
  padding: 3px;
  border: 1px solid var(--color-border-light);
  border-radius: 9px;
  background: var(--color-bg-hover);
}

.filter-btn {
  padding: 6px 4px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 11px;
  cursor: pointer;
  transition: color .15s ease, background .15s ease, box-shadow .15s ease;
}

.filter-btn span {
  margin-left: 2px;
  font-variant-numeric: tabular-nums;
}

.filter-btn:hover { color: var(--color-text-primary); }
.filter-btn.is-active {
  color: var(--color-primary);
  background: var(--color-bg-card);
  box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
  font-weight: 600;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 1;
  min-height: 120px;
  color: var(--color-text-muted);
}

.empty-text {
  font-size: 14px;
  font-weight: 500;
}

.empty-hint {
  font-size: 12px;
  color: var(--color-text-disabled);
}

.stream-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.stream-pagination {
  display: flex;
  flex-shrink: 0;
  justify-content: center;
  padding-top: 2px;
}

.decision-card {
  flex-shrink: 0;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  background: transparent;
  overflow: hidden;
}

.decision-card.is-trade-like {
  border-color: var(--color-profit-border);
}

.card-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: 10px 11px;
  text-align: left;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.card-main:hover {
  background: var(--color-bg-hover);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.time {
  font-size: 11px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.card-mid {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}

.symbol {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.price {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.summary {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--color-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.chip {
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 10px;
  color: var(--color-text-muted);
  background: var(--color-bg-active);
}

.dialog-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
}

.decision-hero {
  padding: 2px 0 18px;
  border-bottom: 1px solid var(--color-border);
}

.decision-hero__top,
.decision-hero__main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.decision-hero__main {
  align-items: center;
  margin-top: 20px;
}

.hero-label {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.hero-copy {
  min-width: 0;
}

.hero-title {
  display: block;
  font-size: 26px;
  line-height: 1.15;
  color: var(--color-text-primary);
}

.hero-copy p {
  margin: 7px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-muted);
}

.hero-market {
  min-width: 168px;
  padding-left: 24px;
  border-left: 1px solid var(--color-border);
  text-align: right;
}

.hero-market > strong {
  display: block;
  font-size: 14px;
  color: var(--color-text-primary);
}

.hero-market-price {
  display: block;
  margin-top: 3px;
  font-size: 19px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.hero-markets {
  min-width: 168px;
  padding-left: 24px;
  border-left: 1px solid var(--color-border);
}

.hero-symbol-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.hero-symbol-list span {
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  background: var(--color-bg-card);
}

.execution-outcome {
  display: grid;
  grid-template-columns: minmax(120px, auto) 1fr;
  align-items: center;
  gap: 18px;
  margin-top: 12px;
  padding: 11px 14px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg-card);
}

.execution-outcome > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.execution-outcome p {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.execution-outcome--success {
  border-color: var(--color-profit-border);
  background: var(--color-profit-bg);
}

.execution-outcome--danger {
  border-color: var(--color-loss-border);
  background: var(--color-loss-bg);
}

.outcome-label {
  font-size: 10px;
  color: var(--color-text-muted);
}

.section-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.dialog-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.dialog-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.dialog-kv {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.plan-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.plan-section-head,
.trade-plan-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.plan-section-desc {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--color-text-muted);
}

.plan-count {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  color: var(--color-primary);
  background: var(--color-bg-active);
}

.trade-plan-card,
.state-plan-card,
.next-review-card {
  margin-top: 10px;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-bg-card);
}

.plan-section--primary {
  margin-top: 18px;
  padding-top: 0;
  border-top: none;
}

.price-route {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.price-node {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  padding: 13px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg-active);
}

.price-node > span,
.plan-fact > span,
.plan-copy > span,
.decision-analysis-card > span {
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.price-node strong {
  font-size: 19px;
  line-height: 1.2;
  color: var(--color-text-primary);
  overflow-wrap: anywhere;
}

.price-node small,
.plan-fact small {
  font-size: 10px;
  line-height: 1.35;
  color: var(--color-text-muted);
}

.price-node--entry {
  border-color: var(--color-border-active);
  background: var(--color-primary-ghost);
}

.price-node--stop {
  border-color: var(--color-loss-border);
  background: var(--color-loss-bg);
}

.price-node--stop strong { color: var(--color-loss); }

.price-node--take {
  border-color: var(--color-profit-border);
  background: var(--color-profit-bg);
}

.price-node--take strong { color: var(--color-profit); }

.plan-facts {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.plan-fact {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 9px 10px;
  border-radius: 8px;
  background: var(--color-bg-active);
}

.plan-fact strong {
  font-size: 12px;
  line-height: 1.4;
  color: var(--color-text-primary);
  overflow-wrap: anywhere;
}

.plan-narrative-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.plan-narrative-grid .plan-copy,
.plan-copy--muted {
  margin-top: 0;
}

.plan-copy--muted {
  margin-top: 10px;
  border-left-color: var(--color-text-muted);
}

.decision-analysis-card {
  margin-top: 14px;
  padding: 14px 16px;
  border-left: 3px solid var(--color-primary);
  border-radius: 0 8px 8px 0;
  background: var(--color-bg-hover);
}

.analysis-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.analysis-heading > span {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.analysis-heading small {
  font-size: 10px;
  font-weight: 500;
  color: var(--color-text-muted);
}

.decision-analysis-card p {
  margin: 5px 0 0;
  font-size: 13px;
  line-height: 1.65;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-more {
  margin-top: 18px;
  border-top: 1px solid var(--color-border);
  border-bottom: none;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.collapse-title strong {
  font-size: 13px;
  color: var(--color-text-primary);
}

.collapse-title span {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-muted);
}

.secondary-section {
  padding: 4px 2px 10px;
}

.trade-plan-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--color-text-primary);
}

.plan-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.plan-metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 10px;
  border-radius: 9px;
  background: var(--color-bg-active);
}

.plan-metric span,
.protection-item span,
.plan-copy > span {
  font-size: 11px;
  color: var(--color-text-muted);
}

.plan-metric strong,
.protection-item strong {
  font-size: 13px;
  line-height: 1.35;
  color: var(--color-text-primary);
  overflow-wrap: anywhere;
}

.plan-metric small {
  font-size: 10px;
  line-height: 1.35;
  color: var(--color-text-muted);
}

.protection-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1.4fr;
  gap: 8px;
  margin-top: 8px;
}

.protection-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 10px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
}

.protection-item--stop {
  border-color: var(--color-loss-border);
  background: var(--color-loss-bg);
}

.protection-item--take {
  border-color: var(--color-profit-border);
  background: var(--color-profit-bg);
}

.plan-copy {
  margin-top: 10px;
  padding-left: 10px;
  border-left: 2px solid var(--color-primary);
}

.plan-copy--danger {
  border-left-color: var(--color-loss);
}

.plan-copy p {
  margin: 3px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.plan-id {
  margin-top: 10px;
  font-size: 10px;
  color: var(--color-text-disabled);
  overflow-wrap: anywhere;
}

.state-plan-card + .state-plan-card {
  margin-top: 8px;
}

.plan-chips {
  margin-top: 5px;
}

.pending-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.pending-action {
  display: grid;
  grid-template-columns: auto minmax(80px, auto) 1fr;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid var(--color-border);
  border-radius: 9px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.pending-action strong {
  color: var(--color-text-primary);
}

.next-review-card {
  margin-top: 16px;
}

.next-review-time {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.condition-list {
  margin: 10px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.kv-label {
  font-size: 11px;
  color: var(--color-text-muted);
}

.kv-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.detail-block {
  margin-top: 12px;
}

.detail-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.detail-label {
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.detail-label-row .detail-label {
  margin-bottom: 0;
}

.detail-content {
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-pre {
  margin: 0;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.detail-pre--prompt {
  max-height: 360px;
  overflow: auto;
}

:deep(.decision-detail-dialog .el-dialog__body) {
  max-height: min(72vh, 760px);
  overflow-y: auto;
}

:deep(.decision-detail-dialog) {
  overflow: hidden;
  border-radius: 16px;
}

:deep(.decision-detail-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 22px 26px 18px;
  border-bottom: 1px solid var(--color-border);
}

:deep(.decision-detail-dialog .el-dialog__body) {
  padding: 22px 26px;
}

:deep(.decision-detail-dialog .el-dialog__footer) {
  padding: 14px 26px 18px;
  border-top: 1px solid var(--color-border);
}

:deep(.detail-more .el-collapse-item__header) {
  min-height: 54px;
  height: auto;
  line-height: 1.35;
}

:deep(.detail-more .el-collapse-item__wrap) {
  border-bottom: none;
}

@media (max-width: 760px) {
  .decision-hero__top,
  .decision-hero__main {
    align-items: flex-start;
    flex-direction: column;
  }

  .dialog-time {
    margin-left: 0;
  }

  .hero-market,
  .hero-markets {
    width: 100%;
    padding: 12px 0 0;
    border-top: 1px solid var(--color-border);
    border-left: none;
    text-align: left;
  }

  .hero-symbol-list {
    justify-content: flex-start;
  }

  .execution-outcome,
  .dialog-grid,
  .protection-row,
  .price-route,
  .plan-narrative-grid {
    grid-template-columns: 1fr;
  }

  .plan-metrics,
  .plan-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pending-action {
    grid-template-columns: auto 1fr;
  }

  .pending-action > span:last-child {
    grid-column: 1 / -1;
  }
}
</style>
