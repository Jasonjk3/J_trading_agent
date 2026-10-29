<template>
  <section class="pending-orders-panel">
    <div class="panel-head">
      <div>
        <span class="eyebrow">ORDERS</span>
        <h3 class="title">委托订单</h3>
      </div>
      <span class="count">{{ orders.length }} 笔活动委托</span>
    </div>

    <div v-if="orders.length === 0" class="empty">
      <span class="empty-text">暂无活动委托</span>
      <span class="empty-hint">限价单提交后会在这里显示，成交、撤销或过期后自动移除</span>
    </div>

    <div v-else class="order-list">
      <button
        v-for="order in orders"
        :key="order.orderId"
        type="button"
        class="order-card"
        :class="{ 'is-active': order.symbol === activeSymbol }"
        @click="$emit('select-symbol', order.symbol)"
      >
        <div class="order-head">
          <div>
            <div class="symbol-line">
              <strong>{{ order.symbol }}</strong>
              <span class="contract-tag">模拟永续</span>
            </div>
            <div class="tags">
              <span class="type-tag">{{ orderTypeLabel(order.orderType) }}</span>
              <span :class="['side-tag', sideClass(order)]">{{ actionLabel(order.action) }}</span>
              <span v-if="order.executionRole === 'pullback_add'" class="role-tag">回撤加仓</span>
              <span v-if="order.requestedLeverage" class="leverage-tag">
                {{ formatLeverage(order.requestedLeverage) }}
              </span>
            </div>
          </div>
          <div class="order-status">
            <span class="status-dot" />
            {{ statusLabel(order.status) }}
          </div>
        </div>

        <div class="order-metrics">
          <div class="metric metric--price">
            <span>委托价格</span>
            <strong class="mono">{{ formatPrice(order.limitPrice) }}</strong>
          </div>
          <div class="metric">
            <span>委托数量 ({{ baseAsset(order.symbol) }})</span>
            <strong class="mono">{{ formatQuantity(order.quantity) }}</strong>
          </div>
          <div class="metric">
            <span>已成交 / 剩余</span>
            <strong class="mono">
              {{ formatQuantity(order.filledQuantity) }} / {{ formatQuantity(order.remainingQuantity) }}
            </strong>
          </div>
          <div class="metric">
            <span>当前价 / 距现价</span>
            <strong class="mono">
              {{ formatOptionalPrice(order.currentPrice) }}
              <small v-if="order.distancePct != null" :class="distanceClass(order.distancePct)">
                {{ signedPercent(order.distancePct) }}
              </small>
            </strong>
          </div>
          <div class="metric">
            <span>创建时间</span>
            <strong>{{ formatTime(order.createdAt) }}</strong>
          </div>
          <div class="metric">
            <span>有效期至</span>
            <strong>{{ order.expiresAt ? formatTime(order.expiresAt) : '未设置' }}</strong>
          </div>
        </div>

        <div class="protection-strip">
          <div class="protection protection--take">
            <span>止盈</span>
            <strong class="mono">{{ formatOptionalPrice(order.takeProfitPrice) }}</strong>
          </div>
          <div class="protection protection--stop">
            <span>止损</span>
            <strong class="mono">{{ formatOptionalPrice(order.stopLossPrice) }}</strong>
          </div>
        </div>

        <div v-if="order.rationale || order.thesis" class="order-reason">
          <span>委托逻辑</span>
          <p>{{ order.rationale || order.thesis }}</p>
        </div>

        <div class="order-footer">
          <span v-if="order.parentPositionId">已绑定父仓</span>
          <span v-if="order.ageBars != null">已等待 {{ order.ageBars }} 根 K 线</span>
          <span class="locate-hint">点击定位到 K 线</span>
        </div>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { BacktestActiveOrder } from '@/api/backtest'

defineProps<{
  orders: BacktestActiveOrder[]
  activeSymbol?: string
}>()

defineEmits<{
  'select-symbol': [symbol: string]
}>()

const labels: Record<string, string> = {
  open_long: '开多', open_short: '开空',
  add_long: '加多', add_short: '加空',
  reduce_long: '减多', reduce_short: '减空',
  close_long: '平多', close_short: '平空',
}

function actionLabel(action: string) {
  return labels[action] ?? action
}

function sideClass(order: BacktestActiveOrder) {
  return order.positionSide === 'long' ? 'side-tag--long' : 'side-tag--short'
}

function orderTypeLabel(value: string) {
  return value === 'limit' ? '限价' : '市价'
}

function statusLabel(value: string) {
  return ({ submitted: '等待成交', partially_filled: '部分成交' } as Record<string, string>)[value] ?? value
}

function formatPrice(value: number) {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatOptionalPrice(value?: number | null) {
  return value == null || Number.isNaN(value) ? '未设置' : formatPrice(value)
}

function formatQuantity(value?: number | null) {
  const number = Number(value ?? 0)
  return number.toLocaleString('en-US', { maximumFractionDigits: 8 })
}

function formatLeverage(value: number) {
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2)}x`
}

function signedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function distanceClass(value: number) {
  return value >= 0 ? 'distance-up' : 'distance-down'
}

function baseAsset(symbol: string) {
  return symbol.toUpperCase().replace(/[-_/]/g, '').replace(/(USDT|USDC|USD)$/, '') || symbol
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getMonth() + 1}/${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.pending-orders-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.panel-head,
.order-head,
.order-footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
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

.count,
.empty-hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 82px;
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
}

.empty-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.order-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 10px;
}

.order-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  text-align: left;
  color: inherit;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s, background .15s;
}

.order-card:hover,
.order-card.is-active {
  border-color: var(--color-border-active);
  background: var(--color-primary-ghost);
  box-shadow: 0 6px 18px rgba(37, 99, 235, .08);
}

.symbol-line,
.tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.symbol-line strong {
  font-size: 16px;
  color: var(--color-text-primary);
}

.tags { margin-top: 7px; }

.contract-tag,
.type-tag,
.role-tag,
.leverage-tag,
.side-tag {
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 11px;
  line-height: 1.4;
  background: var(--color-bg-hover);
  color: var(--color-text-muted);
}

.contract-tag { color: #b7791f; background: #fff7df; }
.type-tag,
.side-tag--long { color: var(--color-profit); background: var(--color-profit-bg); }
.side-tag--short { color: var(--color-loss); background: var(--color-loss-bg); }
.role-tag { color: var(--color-primary); background: var(--color-primary-ghost); }

.order-status {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-primary);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-primary);
}

.order-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 18px;
  padding: 12px 0;
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.metric span,
.order-reason span {
  font-size: 10px;
  color: var(--color-text-muted);
}

.metric strong {
  font-size: 12px;
  color: var(--color-text-primary);
  overflow-wrap: anywhere;
}

.metric--price strong { font-size: 15px; }
.metric small { margin-left: 5px; font-size: 10px; }
.distance-up { color: var(--color-profit); }
.distance-down { color: var(--color-loss); }

.protection-strip {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.protection {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  font-size: 11px;
}

.protection--take { color: var(--color-profit); border-color: var(--color-profit-border); background: var(--color-profit-bg); }
.protection--stop { color: var(--color-loss); border-color: var(--color-loss-border); background: var(--color-loss-bg); }

.order-reason {
  padding-left: 9px;
  border-left: 2px solid var(--color-primary);
}

.order-reason p {
  margin: 3px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.order-footer {
  align-items: center;
  flex-wrap: wrap;
  font-size: 10px;
  color: var(--color-text-muted);
}

.locate-hint { margin-left: auto; color: var(--color-primary); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }

@media (max-width: 900px) {
  .order-list { grid-template-columns: 1fr; }
  .order-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
