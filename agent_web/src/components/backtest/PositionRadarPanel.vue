<template>
  <div class="position-radar" :class="`position-radar--${layout}`">
    <div class="panel-head">
      <div>
        <span class="eyebrow">POSITIONS</span>
        <h3 class="title">仓位雷达</h3>
      </div>
      <span class="count">{{ positions.length }} 仓</span>
    </div>

    <div class="radar-body">
      <div class="summary-grid">
        <div class="summary-cell">
          <span class="summary-label">现金</span>
          <span class="summary-value mono">{{ formatMoney(balance) }}</span>
        </div>
        <div class="summary-cell">
          <span class="summary-label">权益</span>
          <span class="summary-value mono">{{ formatMoney(equity) }}</span>
        </div>
        <div class="summary-cell" :class="{ 'summary-cell--wide': layout === 'vertical' }">
          <span class="summary-label">未实现盈亏</span>
          <span
            class="summary-value mono"
            :class="unrealizedTotal >= 0 ? 'text-profit' : 'text-loss'"
          >
            {{ unrealizedTotal >= 0 ? '+' : '' }}{{ formatMoney(unrealizedTotal) }}
          </span>
        </div>
      </div>

      <div v-if="positions.length === 0" class="empty">
        <span class="empty-text">当前空仓</span>
        <span class="empty-hint">有开仓后会实时显示浮盈</span>
      </div>

      <div v-else class="position-list">
        <button
          v-for="pos in positions"
          :key="`${pos.symbol}-${pos.side}`"
          type="button"
          class="position-card"
          :class="{ 'is-active': pos.symbol === activeSymbol }"
          @click="$emit('select-symbol', pos.symbol)"
        >
          <div class="position-head">
            <div class="position-identity">
              <div class="symbol-line">
                <span class="symbol">{{ pos.symbol }}</span>
                <span class="contract-tag">模拟永续</span>
              </div>
              <div class="position-tags">
                <span
                  class="side-tag"
                  :class="pos.side === 'long' ? 'side-tag--long' : 'side-tag--short'"
                >
                  {{ pos.side === 'long' ? '多' : '空' }}
                </span>
                <span class="mode-tag">逐仓</span>
                <span class="leverage-tag">{{ formatLeverage(pos.leverage) }}</span>
              </div>
            </div>

            <div class="position-pnl">
              <span class="pnl-label">收益额 / 保证金收益率</span>
              <div
                class="pnl-values"
                :class="pos.unrealizedPnl >= 0 ? 'text-profit' : 'text-loss'"
              >
                <strong class="pnl-amount mono">
                  {{ signedMoney(pos.unrealizedPnl) }}
                </strong>
                <span class="pnl-pct mono">({{ signedPercent(positionRoi(pos)) }})</span>
              </div>
            </div>
          </div>

          <div class="position-metrics">
            <div class="metric">
              <span>持仓量 ({{ baseAsset(pos.symbol) }})</span>
              <strong class="mono">{{ formatQty(pos.quantity) }}</strong>
            </div>
            <div class="metric">
              <span>保证金 (USDT)</span>
              <strong class="mono">{{ formatMoney(pos.marginUsed) }}</strong>
            </div>
            <div class="metric">
              <span>名义价值 (USDT)</span>
              <strong class="mono">{{ formatMoney(positionNotional(pos)) }}</strong>
            </div>
            <div class="metric">
              <span>开仓均价</span>
              <strong class="mono">{{ formatPrice(pos.entryPrice) }}</strong>
            </div>
            <div class="metric">
              <span>标记价格</span>
              <strong class="mono">{{ formatPrice(pos.currentPrice) }}</strong>
            </div>
            <div class="metric">
              <span>持仓时长</span>
              <strong>{{ formatHoldingDuration(pos.entryTime) }}</strong>
            </div>
          </div>

          <div v-if="hasProtection(pos)" class="protection-strip">
            <div class="protection-value protection-value--take">
              <span>止盈</span>
              <strong class="mono">{{ formatOptionalPrice(pos.tradePlan?.takeProfitPrice) }}</strong>
            </div>
            <div class="protection-value protection-value--stop">
              <span>止损</span>
              <strong class="mono">{{ formatOptionalPrice(pos.tradePlan?.stopLossPrice) }}</strong>
            </div>
          </div>

          <div v-if="pos.tradePlan?.thesis" class="position-thesis">
            <span>持仓逻辑</span>
            <p>{{ pos.tradePlan.thesis }}</p>
          </div>

          <div class="position-footer">
            <span v-if="pos.entryTime">开仓于 {{ formatShortTime(pos.entryTime) }}</span>
            <span class="locate-hint">点击定位到 K 线</span>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LiveOpenPosition } from '@/api/backtest'

const props = withDefaults(defineProps<{
  positions: LiveOpenPosition[]
  balance?: number
  equity?: number
  activeSymbol?: string
  currentTime?: string
  layout?: 'vertical' | 'horizontal'
}>(), {
  layout: 'vertical',
})

defineEmits<{
  'select-symbol': [symbol: string]
}>()

const unrealizedTotal = computed(() =>
  props.positions.reduce((sum, p) => sum + (p.unrealizedPnl || 0), 0),
)

function formatMoney(value?: number) {
  const n = value ?? 0
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatPrice(value: number) {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatOptionalPrice(value?: number | null) {
  return value == null || Number.isNaN(value) ? '未设置' : formatPrice(value)
}

function formatQty(value: number) {
  return value.toLocaleString('en-US', { maximumFractionDigits: 8 })
}

function formatLeverage(value?: number) {
  const n = Number(value ?? 1)
  return `${Number.isInteger(n) ? n.toFixed(0) : n.toFixed(2)}x`
}

function signedMoney(value: number) {
  return `${value >= 0 ? '+' : ''}${formatMoney(value)}`
}

function signedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function positionRoi(pos: LiveOpenPosition) {
  if (pos.roiPercent != null && Number.isFinite(pos.roiPercent)) return pos.roiPercent
  const margin = Number(pos.marginUsed ?? 0)
  return margin > 0 ? (pos.unrealizedPnl / margin) * 100 : 0
}

function positionNotional(pos: LiveOpenPosition) {
  return pos.notional ?? pos.quantity * pos.currentPrice
}

function baseAsset(symbol: string) {
  return symbol.toUpperCase().replace(/[-_/]/g, '').replace(/(USDT|USDC|USD)$/, '') || symbol
}

function hasProtection(pos: LiveOpenPosition) {
  return pos.tradePlan?.stopLossPrice != null || pos.tradePlan?.takeProfitPrice != null
}

function formatHoldingDuration(entryTime?: string) {
  if (!entryTime) return '—'
  const start = new Date(entryTime).getTime()
  const end = props.currentTime ? new Date(props.currentTime).getTime() : Date.now()
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '—'
  const totalMinutes = Math.floor((end - start) / 60_000)
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60
  if (days > 0) return `${days}天 ${hours}小时`
  if (hours > 0) return `${hours}小时 ${minutes}分`
  return `${minutes}分钟`
}

function formatShortTime(iso: string) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getMonth() + 1}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.position-radar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  min-width: 0;
  padding: 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-sizing: border-box;
}

.position-radar--vertical {
  height: 100%;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-shrink: 0;
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

.count {
  font-size: 12px;
  color: var(--color-text-muted);
}

.radar-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  min-height: 0;
  flex: 1;
}

.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  flex-shrink: 0;
}

.summary-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-sm);
  min-width: 0;
}

.summary-cell--wide {
  grid-column: 1 / -1;
}

.summary-label {
  font-size: 11px;
  color: var(--color-text-muted);
}

.summary-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.mono {
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 1;
  min-height: 80px;
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

.position-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  min-width: 0;
}

.position-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
  padding: 14px;
  text-align: left;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-card);
  color: inherit;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.position-card:hover,
.position-card.is-active {
  border-color: var(--color-border-active);
  background: var(--color-primary-ghost);
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.08);
}

.position-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.position-identity {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}

.symbol-line,
.position-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.symbol {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.contract-tag,
.mode-tag,
.leverage-tag {
  padding: 2px 6px;
  border-radius: 5px;
  font-size: 10px;
  line-height: 1.4;
  color: var(--color-text-muted);
  background: var(--color-bg-hover);
}

.contract-tag {
  color: #b7791f;
  background: #fff7df;
}

.side-tag {
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 600;
}

.side-tag--long {
  color: var(--color-profit);
  background: var(--color-profit-bg);
}

.side-tag--short {
  color: var(--color-loss);
  background: var(--color-loss-bg);
}

.position-pnl {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.pnl-label {
  font-size: 10px;
  color: var(--color-text-muted);
}

.pnl-values {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 5px;
}

.pnl-amount {
  font-size: 18px;
  font-weight: 700;
}

.pnl-pct {
  font-size: 13px;
  font-weight: 600;
}

.position-metrics {
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

.metric span {
  font-size: 10px;
  color: var(--color-text-muted);
}

.metric strong {
  font-size: 12px;
  line-height: 1.35;
  color: var(--color-text-primary);
  overflow-wrap: anywhere;
}

.protection-strip {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.protection-value {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 9px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  font-size: 11px;
}

.protection-value--take {
  color: var(--color-profit);
  border-color: var(--color-profit-border);
  background: var(--color-profit-bg);
}

.protection-value--stop {
  color: var(--color-loss);
  border-color: var(--color-loss-border);
  background: var(--color-loss-bg);
}

.position-thesis {
  padding-left: 9px;
  border-left: 2px solid var(--color-primary);
}

.position-thesis span {
  font-size: 10px;
  color: var(--color-text-muted);
}

.position-thesis p {
  display: -webkit-box;
  margin: 3px 0 0;
  overflow: hidden;
  font-size: 11px;
  line-height: 1.45;
  color: var(--color-text-secondary);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.position-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.locate-hint {
  margin-left: auto;
  color: var(--color-primary);
}

.text-profit { color: var(--color-profit); }
.text-loss { color: var(--color-loss); }

/* 底部横向布局 */
.position-radar--horizontal .radar-body {
  flex-direction: row;
  align-items: stretch;
  gap: 16px;
}

.position-radar--horizontal .summary-grid {
  grid-template-columns: repeat(3, minmax(100px, 140px));
  width: auto;
  align-content: start;
}

.position-radar--horizontal .summary-cell--wide {
  grid-column: auto;
}

.position-radar--horizontal .empty {
  flex: 1;
  min-height: 72px;
  align-items: flex-start;
  justify-content: center;
  padding-left: 8px;
}

.position-radar--horizontal .position-list {
  flex-direction: row;
  overflow-x: auto;
  overflow-y: hidden;
  flex: 1;
  padding-bottom: 2px;
}

.position-radar--horizontal .position-card {
  width: 430px;
  min-width: 430px;
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .position-radar--horizontal .radar-body {
    flex-direction: column;
  }

  .position-radar--horizontal .summary-grid {
    grid-template-columns: repeat(3, 1fr);
    width: 100%;
  }

  .position-radar--horizontal .position-list {
    flex-direction: row;
  }
}

@media (max-width: 620px) {
  .position-radar--horizontal .summary-grid {
    grid-template-columns: 1fr;
  }

  .position-radar--horizontal .position-card {
    width: min(430px, calc(100vw - 64px));
    min-width: min(430px, calc(100vw - 64px));
  }

  .position-head {
    flex-direction: column;
  }

  .position-pnl {
    align-items: flex-start;
  }

  .position-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
