<template>
  <section class="trade-manager">
    <div class="manager-head">
      <div class="manager-tabs" role="tablist" aria-label="仓位与委托">
        <button
          type="button"
          role="tab"
          class="manager-tab"
          :class="{ 'is-active': activeTab === 'positions' }"
          :aria-selected="activeTab === 'positions'"
          @click="activeTab = 'positions'"
        >
          当前仓位 <span>{{ positions.length }}</span>
        </button>
        <button
          type="button"
          role="tab"
          class="manager-tab"
          :class="{ 'is-active': activeTab === 'orders' }"
          :aria-selected="activeTab === 'orders'"
          @click="activeTab = 'orders'"
        >
          当前委托 <span>{{ orders.length }}</span>
        </button>
      </div>

      <div class="manager-actions">
        <div v-if="activeTab === 'positions'" class="account-summary">
          <span>现金 <strong class="mono">{{ formatMoney(balance) }}</strong></span>
          <span>权益 <strong class="mono">{{ formatMoney(equity) }}</strong></span>
          <span>
            浮盈
            <strong class="mono" :class="unrealizedTotal >= 0 ? 'text-profit' : 'text-loss'">
              {{ signedMoney(unrealizedTotal) }}
            </strong>
          </span>
        </div>
        <span v-else class="managed-hint">委托由回测策略自动管理</span>
        <div class="scroll-controls">
          <button type="button" class="icon-btn" aria-label="向左浏览" @click="scrollCards(-1)">
            <el-icon><ArrowLeft /></el-icon>
          </button>
          <button type="button" class="icon-btn" aria-label="向右浏览" @click="scrollCards(1)">
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="activeTab === 'positions' && positions.length"
      ref="positionListRef"
      class="card-rail"
    >
      <button
        v-for="pos in positions"
        :key="`${pos.symbol}-${pos.side}`"
        type="button"
        class="trade-card position-card"
        :class="{ 'is-active': pos.symbol === activeSymbol }"
        @click="$emit('select-symbol', pos.symbol)"
      >
        <div class="card-head">
          <div class="identity">
            <strong>{{ pos.symbol }}</strong>
            <span class="side-chip" :class="pos.side === 'long' ? 'is-long' : 'is-short'">
              {{ pos.side === 'long' ? '多仓' : '空仓' }}
            </span>
            <span class="neutral-chip">{{ formatLeverage(pos.leverage) }}</span>
          </div>
          <div class="pnl" :class="pos.unrealizedPnl >= 0 ? 'text-profit' : 'text-loss'">
            <strong class="mono">{{ signedMoney(pos.unrealizedPnl) }}</strong>
            <span class="mono">{{ signedPercent(positionRoi(pos)) }}</span>
          </div>
        </div>
        <div class="metric-row">
          <div><span>持仓量</span><strong class="mono">{{ formatQty(pos.quantity) }} {{ baseAsset(pos.symbol) }}</strong></div>
          <div><span>开仓均价</span><strong class="mono">{{ formatPrice(pos.entryPrice) }}</strong></div>
          <div><span>标记价格</span><strong class="mono">{{ formatPrice(pos.currentPrice) }}</strong></div>
          <div><span>持仓时长</span><strong>{{ formatHoldingDuration(pos.entryTime) }}</strong></div>
        </div>
        <div class="protection-row">
          <span class="take">止盈 <strong class="mono">{{ formatOptionalPrice(pos.tradePlan?.takeProfitPrice) }}</strong></span>
          <span class="stop">止损 <strong class="mono">{{ formatOptionalPrice(pos.tradePlan?.stopLossPrice) }}</strong></span>
          <span class="locate">点击定位 K 线</span>
        </div>
      </button>
    </div>

    <div
      v-else-if="activeTab === 'orders' && orders.length"
      ref="orderListRef"
      class="card-rail"
    >
      <button
        v-for="order in orders"
        :key="order.orderId"
        type="button"
        class="trade-card order-card"
        :class="{ 'is-active': order.symbol === activeSymbol }"
        @click="$emit('select-symbol', order.symbol)"
      >
        <div class="card-head">
          <div class="identity">
            <strong>{{ order.symbol }}</strong>
            <span class="side-chip" :class="order.side === 'buy' ? 'is-long' : 'is-short'">
              {{ order.side === 'buy' ? '买入' : '卖出' }}
            </span>
            <span class="neutral-chip">{{ order.orderType === 'limit' ? '限价' : '市价' }}</span>
            <span v-if="order.requestedLeverage" class="neutral-chip">{{ formatLeverage(order.requestedLeverage) }}</span>
          </div>
          <span class="order-status"><i />{{ statusLabel(order.status) }}</span>
        </div>
        <div class="metric-row metric-row--order">
          <div><span>委托价格</span><strong class="mono">{{ formatPrice(order.limitPrice) }}</strong></div>
          <div><span>委托数量</span><strong class="mono">{{ formatQty(order.quantity) }} {{ baseAsset(order.symbol) }}</strong></div>
          <div><span>成交进度</span><strong class="mono">{{ formatQty(order.filledQuantity) }} / {{ formatQty(order.quantity) }}</strong></div>
          <div><span>创建时间</span><strong>{{ formatShortTime(order.createdAt) }}</strong></div>
        </div>
        <div class="order-footer">
          <span v-if="order.distancePct != null">
            距现价 <strong class="mono">{{ signedPercent(order.distancePct) }}</strong>
          </span>
          <span v-else>等待价格触达</span>
          <span class="managed-badge">策略托管</span>
          <span class="locate">点击定位 K 线</span>
        </div>
      </button>
    </div>

    <div v-else class="empty-state">
      <span>{{ activeTab === 'positions' ? '当前没有持仓' : '当前没有活动委托' }}</span>
      <small>{{ activeTab === 'positions' ? '开仓后会在这里实时展示' : '策略提交限价单后会在这里展示' }}</small>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import type { BacktestActiveOrder, LiveOpenPosition } from '@/api/backtest'

const props = defineProps<{
  positions: LiveOpenPosition[]
  orders: BacktestActiveOrder[]
  balance?: number
  equity?: number
  activeSymbol?: string
  currentTime?: string
}>()

defineEmits<{
  'select-symbol': [symbol: string]
}>()

const activeTab = ref<'positions' | 'orders'>('positions')
const positionListRef = ref<HTMLElement | null>(null)
const orderListRef = ref<HTMLElement | null>(null)

const unrealizedTotal = computed(() => props.positions.reduce((sum, item) => sum + Number(item.unrealizedPnl || 0), 0))

watch(
  () => [props.positions.length, props.orders.length],
  ([positionsCount, ordersCount]) => {
    if (!positionsCount && ordersCount) activeTab.value = 'orders'
    if (!ordersCount && positionsCount) activeTab.value = 'positions'
  },
  { immediate: true },
)

async function scrollCards(direction: -1 | 1) {
  await nextTick()
  const target = activeTab.value === 'positions' ? positionListRef.value : orderListRef.value
  target?.scrollBy({ left: direction * Math.max(320, target.clientWidth * 0.72), behavior: 'smooth' })
}

function formatMoney(value?: number) {
  return Number(value ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPrice(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatOptionalPrice(value?: number | null) {
  return value == null ? '未设置' : formatPrice(value)
}

function formatQty(value?: number | null) {
  return Number(value ?? 0).toLocaleString('en-US', { maximumFractionDigits: 8 })
}

function formatLeverage(value?: number | null) {
  const number = Number(value ?? 1)
  return `${Number.isInteger(number) ? number.toFixed(0) : number.toFixed(2)}x`
}

function signedMoney(value: number) {
  return `${value >= 0 ? '+' : ''}${formatMoney(value)}`
}

function signedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${Number(value || 0).toFixed(2)}%`
}

function positionRoi(position: LiveOpenPosition) {
  if (position.roiPercent != null && Number.isFinite(position.roiPercent)) return position.roiPercent
  const margin = Number(position.marginUsed ?? 0)
  return margin > 0 ? (position.unrealizedPnl / margin) * 100 : 0
}

function baseAsset(symbol: string) {
  return symbol.toUpperCase().replace(/[-_/]/g, '').replace(/(USDT|USDC|USD)$/, '') || symbol
}

function formatHoldingDuration(entryTime?: string) {
  if (!entryTime) return '—'
  const start = new Date(entryTime).getTime()
  const end = props.currentTime ? new Date(props.currentTime).getTime() : Date.now()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '—'
  const minutes = Math.floor((end - start) / 60_000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  if (days) return `${days}天 ${hours}小时`
  if (hours) return `${hours}小时 ${minutes % 60}分`
  return `${minutes}分钟`
}

function formatShortTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function statusLabel(value: string) {
  return ({ submitted: '等待成交', partially_filled: '部分成交' } as Record<string, string>)[value] ?? value
}
</script>

<style scoped>
.trade-manager {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  min-width: 0;
  margin-bottom: 14px;
  padding: 0 14px 12px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.manager-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 44px;
  border-bottom: 1px solid var(--color-border-light);
}

.manager-tabs,
.manager-actions,
.account-summary,
.scroll-controls,
.identity,
.protection-row,
.order-footer {
  display: flex;
  align-items: center;
}

.manager-tabs { align-self: stretch; gap: 22px; }

.manager-tab {
  position: relative;
  padding: 0 1px;
  border: 0;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.manager-tab span { margin-left: 4px; font-variant-numeric: tabular-nums; }
.manager-tab:hover { color: var(--color-text-primary); }
.manager-tab.is-active { color: var(--color-primary); }
.manager-tab.is-active::after {
  content: '';
  position: absolute;
  right: 0;
  bottom: -15px;
  left: 0;
  height: 2px;
  border-radius: 2px;
  background: var(--color-primary);
}

.manager-actions { gap: 12px; min-width: 0; }
.account-summary { gap: 14px; }
.account-summary span,
.managed-hint { font-size: 10px; color: var(--color-text-muted); }
.account-summary strong { margin-left: 4px; color: var(--color-text-primary); }
.scroll-controls { gap: 5px; }

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  color: var(--color-text-muted);
  background: var(--color-bg-card);
  cursor: pointer;
}
.icon-btn:hover { color: var(--color-primary); border-color: var(--color-border-active); background: var(--color-primary-ghost); }

.card-rail {
  display: flex;
  gap: 10px;
  width: 100%;
  min-width: 0;
  padding-bottom: 2px;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  scrollbar-width: thin;
}

.trade-card {
  flex: 0 0 420px;
  min-width: 420px;
  padding: 11px 12px 9px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg-card);
  color: inherit;
  text-align: left;
  cursor: pointer;
  scroll-snap-align: start;
  transition: border-color .16s ease, box-shadow .16s ease, transform .16s ease;
}
.trade-card:hover { border-color: var(--color-border-active); box-shadow: 0 5px 14px rgba(37, 99, 235, .07); transform: translateY(-1px); }
.trade-card.is-active { border-color: var(--color-primary); box-shadow: 0 0 0 1px rgba(37, 99, 235, .08); }

.card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.identity { flex-wrap: wrap; gap: 6px; min-width: 0; }
.identity > strong { font-size: 14px; color: var(--color-text-primary); }

.side-chip,
.neutral-chip,
.managed-badge {
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 10px;
  line-height: 1.45;
}
.side-chip.is-long { color: var(--color-profit); background: var(--color-profit-bg); }
.side-chip.is-short { color: var(--color-loss); background: var(--color-loss-bg); }
.neutral-chip { color: var(--color-text-muted); background: var(--color-bg-hover); }
.managed-badge { margin-left: auto; color: var(--color-primary); background: var(--color-primary-ghost); }

.pnl { display: flex; align-items: baseline; gap: 5px; white-space: nowrap; }
.pnl strong { font-size: 14px; }
.pnl span { font-size: 10px; }

.metric-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border-light);
}
.metric-row > div { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.metric-row span { font-size: 9px; color: var(--color-text-muted); }
.metric-row strong { overflow: hidden; color: var(--color-text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }

.protection-row,
.order-footer { gap: 8px; margin-top: 8px; font-size: 9px; color: var(--color-text-muted); }
.protection-row > span { padding: 3px 7px; border-radius: 6px; }
.protection-row .take { color: var(--color-profit); background: var(--color-profit-bg); }
.protection-row .stop { color: var(--color-loss); background: var(--color-loss-bg); }
.locate { margin-left: auto; color: var(--color-primary); }

.order-status { display: inline-flex; align-items: center; gap: 5px; color: var(--color-primary); font-size: 10px; white-space: nowrap; }
.order-status i { width: 6px; height: 6px; border-radius: 50%; background: var(--color-primary); animation: status-pulse 1.5s ease-in-out infinite; }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; min-height: 82px; color: var(--color-text-secondary); }
.empty-state span { font-size: 13px; font-weight: 600; }
.empty-state small { font-size: 11px; color: var(--color-text-muted); }

.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
.text-profit { color: var(--color-profit) !important; }
.text-loss { color: var(--color-loss) !important; }

@keyframes status-pulse { 50% { opacity: .38; } }

@media (max-width: 920px) {
  .account-summary { display: none; }
  .trade-card { flex-basis: min(420px, calc(100vw - 84px)); min-width: min(420px, calc(100vw - 84px)); }
}

@media (max-width: 620px) {
  .trade-manager { padding-inline: 10px; }
  .manager-tabs { gap: 14px; }
  .managed-hint { display: none; }
  .metric-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
