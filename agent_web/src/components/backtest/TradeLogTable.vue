<template>
  <div class="trade-log-table">
    <div class="table-header">
      <div>
        <h4 class="table-title">交易记录</h4>
        <p class="table-description">
          按实际成交时间展示；限价委托可能晚于决策提交成交，风控平仓为系统自动执行。
        </p>
      </div>
      <div class="table-actions">
        <el-select
          v-if="!remote"
          v-model="filterSymbol"
          placeholder="筛选交易对"
          clearable
          size="small"
          style="width: 140px"
        >
          <el-option
            v-for="symbol in symbolOptions"
            :key="symbol"
            :label="symbol"
            :value="symbol"
          />
        </el-select>
        <el-select
          v-if="!remote"
          v-model="filterSide"
          placeholder="筛选方向"
          clearable
          size="small"
          style="width: 100px"
        >
          <el-option label="买入" value="buy" />
          <el-option label="卖出" value="sell" />
        </el-select>
        <el-button size="small" @click="exportTrades">
          <el-icon><Download /></el-icon>
          导出
        </el-button>
      </div>
    </div>

    <el-table
      :data="paginatedTrades"
      class="custom-table"
      table-layout="fixed"
      :row-class-name="getRowClassName"
      @row-click="handleRowClick"
    >
      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          <span class="time-cell">{{ formatTime(row.timestamp) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="交易对" width="128" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="symbol-cell">{{ row.symbol }}</span>
        </template>
      </el-table-column>

      <el-table-column label="成交动作" width="132" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.side === 'buy' ? 'success' : 'danger'"
            size="small"
            effect="plain"
          >
            {{ fullTradeActionLabel(row) }}
          </el-tag>
          <span v-if="executionSourceLabel(row)" class="execution-source">
            {{ executionSourceLabel(row) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="成交价格" min-width="148" align="right">
        <template #default="{ row }">
          <div class="trade-price-cell">
            <span class="price-side-label">{{ row.side === 'buy' ? '买入价' : '卖出价' }}</span>
            <span class="price-cell">{{ formatPrice(row.price) }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="杠杆" width="82" align="right">
        <template #default="{ row }">
          <span class="leverage-cell">{{ formatLeverage(row.leverage) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="数量" min-width="116" align="right">
        <template #default="{ row }">
          <span>{{ row.quantity }}</span>
        </template>
      </el-table-column>

      <el-table-column label="金额" min-width="132" align="right">
        <template #default="{ row }">
          <span>{{ formatMoney(row.amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="手续费" min-width="108" align="right">
        <template #default="{ row }">
          <span class="fee-cell">{{ formatMoney(row.fee) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="盈亏" min-width="148" align="right">
        <template #default="{ row }">
          <div v-if="row.type === 'close'" class="pnl-cell">
            <span :class="getPnlClass(row.pnl)">
              {{ formatPnl(row.pnl) }}
            </span>
            <span :class="['pnl-percent', getPnlClass(row.pnlPercent)]">
              ({{ formatPercent(row.pnlPercent) }})
            </span>
          </div>
          <span v-else class="empty-cell">-</span>
        </template>
      </el-table-column>

      <el-table-column label="余额" min-width="132" align="right">
        <template #default="{ row }">
          <span class="balance-cell">{{ formatMoney(row.balance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="" width="48" align="center">
        <template #default="{ row }">
          <el-icon
            v-if="row.reasoning || (row.chainOfThought && row.chainOfThought.length)"
            class="reasoning-icon"
            @click.stop="showReasoning(row)"
          >
            <ChatLineRound />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="table-pagination">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        :total="tableTotal"
        layout="total, sizes, prev, pager, next"
        small
      />
    </div>

    <!-- 思维链弹窗 -->
    <el-dialog
      v-model="reasoningDialogVisible"
      title="Agent 决策过程"
      width="600px"
      class="reasoning-dialog"
    >
      <div v-if="selectedTrade" class="reasoning-content">
        <div class="trade-info">
          <div class="info-row">
            <span class="info-label">交易对:</span>
            <span class="info-value">{{ selectedTrade.symbol }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">操作:</span>
            <el-tag
              :type="selectedTrade.side === 'buy' ? 'success' : 'danger'"
              size="small"
            >
              {{ fullTradeActionLabel(selectedTrade) }}
            </el-tag>
          </div>
          <div class="info-row">
            <span class="info-label">成交价格:</span>
            <span class="info-value">{{ selectedTrade.side === 'buy' ? '买入价' : '卖出价' }} {{ formatPrice(selectedTrade.price) }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">杠杆/保证金:</span>
            <span class="info-value">{{ formatLeverage(selectedTrade.leverage) }} / {{ formatMoney(selectedTrade.marginUsed ?? selectedTrade.amount) }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">时间:</span>
            <span class="info-value">{{ formatTime(selectedTrade.timestamp) }}</span>
          </div>
        </div>
        <div class="divider"></div>
        <div class="reasoning-text">
          <h5>决策理由</h5>
          <p>{{ selectedTrade.reasoning || '-' }}</p>
        </div>
        <div v-if="selectedTrade.signals?.length" class="signals-section">
          <h5>触发信号</h5>
          <div class="signals-list">
            <el-tag
              v-for="signal in selectedTrade.signals"
              :key="signal"
              size="small"
              effect="plain"
            >
              {{ signal }}
            </el-tag>
          </div>
        </div>
        <div v-if="selectedTrade.chainOfThought?.length" class="chain-section">
          <h5>Agent 思考过程</h5>
          <div class="thought-steps">
            <div
              v-for="(step, idx) in selectedTrade.chainOfThought"
              :key="idx"
              class="thought-step"
            >
              <span class="step-index">{{ idx + 1 }}</span>
              <div class="step-content">
                <template v-if="typeof step === 'string'">{{ step }}</template>
                <template v-else>
                  <div v-if="step.step" class="step-label">{{ step.step }}</div>
                  <div v-if="step.thought" class="step-thought">{{ step.thought }}</div>
                  <div v-if="step.conclusion" class="step-conclusion">{{ step.conclusion }}</div>
                  <div v-else-if="step.reason" class="step-thought">{{ step.reason }}</div>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Download, ChatLineRound } from '@element-plus/icons-vue'
import type { BacktestTradeRecord } from '@/api/backtest'

const props = defineProps<{
  trades: BacktestTradeRecord[]
  /** 服务端分页：总条数 */
  total?: number
  /** 服务端分页模式（trades 为当前页数据） */
  remote?: boolean
}>()

const emit = defineEmits<{
  select: [trade: BacktestTradeRecord]
  'page-change': [payload: { page: number; pageSize: number }]
}>()

const filterSymbol = ref('')
const filterSide = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const reasoningDialogVisible = ref(false)
const selectedTrade = ref<BacktestTradeRecord | null>(null)

const tradeActionLabels: Record<string, string> = {
  open_long: '开多',
  open_short: '开空',
  add_long: '加多',
  add_short: '加空',
  reduce_long: '减多',
  reduce_short: '减空',
  close_long: '平多',
  close_short: '平空',
}

function resolvedTradeAction(trade: BacktestTradeRecord): string {
  if (trade.action) return trade.action
  if (trade.type === 'open') return trade.side === 'buy' ? 'open_long' : 'open_short'
  return trade.side === 'sell' ? 'close_long' : 'close_short'
}

function tradeActionLabel(trade: BacktestTradeRecord): string {
  const action = resolvedTradeAction(trade)
  return tradeActionLabels[action] ?? action
}

function fullTradeActionLabel(trade: BacktestTradeRecord): string {
  const side = trade.side === 'buy' ? '买入' : '卖出'
  return `${side}${tradeActionLabel(trade)}`
}

function executionSourceLabel(trade: BacktestTradeRecord): string {
  if (trade.signals?.includes('pending_order_fill')) return '挂单成交'
  if (trade.signals?.includes('risk_control')) return '风控自动执行'
  return ''
}

const symbolOptions = computed(() => {
  const symbols = new Set(props.trades.map(t => t.symbol))
  return Array.from(symbols)
})

const filteredTrades = computed(() => {
  if (props.remote) return props.trades
  let result = props.trades
  if (filterSymbol.value) {
    result = result.filter(t => t.symbol === filterSymbol.value)
  }
  if (filterSide.value) {
    result = result.filter(t => t.side === filterSide.value)
  }
  return result
})

const tableTotal = computed(() => {
  if (props.remote) return props.total ?? props.trades.length
  return filteredTrades.value.length
})

const paginatedTrades = computed(() => {
  if (props.remote) return props.trades
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredTrades.value.slice(start, end)
})

watch([filterSymbol, filterSide, pageSize], () => {
  currentPage.value = 1
  if (props.remote) {
    emit('page-change', { page: 1, pageSize: pageSize.value })
  }
})

watch(currentPage, (page) => {
  if (props.remote) {
    emit('page-change', { page, pageSize: pageSize.value })
  }
})

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function formatPrice(price: number): string {
  return price.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function formatMoney(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function formatLeverage(value?: number): string {
  const leverage = Number(value ?? 1)
  return `${Number.isInteger(leverage) ? leverage.toFixed(0) : leverage.toFixed(2)}x`
}

function formatPnl(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${formatMoney(value)}`
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function getPnlClass(value: number): string {
  if (value > 0) return 'positive'
  if (value < 0) return 'negative'
  return ''
}

function getRowClassName({ row }: { row: BacktestTradeRecord }): string {
  if (row.type === 'close') {
    return row.pnl >= 0 ? 'win-row' : 'loss-row'
  }
  return ''
}

function handleRowClick(row: BacktestTradeRecord) {
  emit('select', row)
  if (row.reasoning || (row.chainOfThought && row.chainOfThought.length)) {
    showReasoning(row)
  }
}

function showReasoning(trade: BacktestTradeRecord) {
  selectedTrade.value = trade
  reasoningDialogVisible.value = true
}

function exportTrades() {
  const headers = ['时间', '交易对', '成交动作', '执行来源', '成交价格', '杠杆', '保证金', '数量', '金额', '手续费', '盈亏', '盈亏%', '余额', '决策理由']
  const rows = props.trades.map(t => [
    t.timestamp,
    t.symbol,
    fullTradeActionLabel(t),
    executionSourceLabel(t),
    Number(t.price).toFixed(2),
    formatLeverage(t.leverage),
    Number(t.marginUsed ?? t.amount).toFixed(2),
    t.quantity,
    t.amount,
    t.fee,
    t.pnl,
    t.pnlPercent,
    t.balance,
    t.reasoning || ''
  ])
  
  const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `backtest_trades_${Date.now()}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.trade-log-table {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  padding: 20px;
  border: 1px solid var(--color-border);
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.table-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.table-description {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-muted);
}

.table-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.custom-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.02);
}

.custom-table :deep(.el-table__row) {
  cursor: pointer;
}

.custom-table :deep(.el-table__row:hover > td) {
  background: rgba(255, 255, 255, 0.05) !important;
}

.custom-table :deep(.win-row) {
  background: rgba(103, 194, 58, 0.05);
}

.custom-table :deep(.loss-row) {
  background: rgba(245, 108, 108, 0.05);
}

.time-cell {
  font-size: 12px;
  color: var(--color-text-muted);
  font-family: monospace;
}

.symbol-cell {
  font-weight: 600;
}

.type-cell {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.execution-source {
  display: block;
  margin-top: 4px;
  font-size: 10px;
  line-height: 1.2;
  color: var(--color-text-muted);
}

.trade-price-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  white-space: nowrap;
}

.price-side-label {
  font-size: 10px;
  color: var(--color-text-muted);
}

.price-cell {
  font-family: monospace;
}

.leverage-cell {
  font-family: monospace;
  font-weight: 600;
  color: var(--color-primary);
  white-space: nowrap;
}

.fee-cell {
  font-size: 12px;
  color: var(--color-text-muted);
}

.pnl-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.pnl-percent {
  font-size: 11px;
}

.positive {
  color: var(--color-success);
}

.negative {
  color: var(--color-danger);
}

.balance-cell {
  font-weight: 600;
  font-family: monospace;
}

.empty-cell {
  color: var(--color-text-muted);
}

.reasoning-icon {
  cursor: pointer;
  color: var(--color-text-muted);
  transition: color 0.2s;
}

.reasoning-icon:hover {
  color: var(--color-primary);
}

.table-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 思维链弹窗样式 */
.reasoning-content {
  padding: 8px 0;
}

.trade-info {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-label {
  font-size: 13px;
  color: var(--color-text-muted);
}

.info-value {
  font-weight: 500;
}

.divider {
  height: 1px;
  background: var(--color-border);
  margin: 16px 0;
}

.reasoning-text h5,
.signals-section h5 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.reasoning-text p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.signals-section {
  margin-top: 16px;
}

.chain-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.chain-section h5 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.thought-steps {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 280px;
  overflow-y: auto;
}

.thought-step {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-primary);
}

.step-index {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: var(--color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.step-content {
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.step-label {
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.step-thought,
.step-conclusion {
  margin-top: 4px;
}

.signals-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
