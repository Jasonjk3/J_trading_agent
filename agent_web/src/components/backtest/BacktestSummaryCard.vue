<template>
  <div class="summary-card">
    <!-- 主要指标 -->
    <div class="stats-primary">
      <div class="stat-box stat-box--large">
        <span class="stat-label">总收益率</span>
        <span class="stat-value" :class="getValueClass(statistics.totalReturn)">
          {{ formatPercent(statistics.totalReturn) }}
        </span>
      </div>
      <div class="stat-box stat-box--large">
        <span class="stat-label">年化收益</span>
        <span class="stat-value" :class="getValueClass(statistics.annualizedReturn)">
          {{ formatPercent(statistics.annualizedReturn) }}
        </span>
      </div>
      <div class="stat-box stat-box--large">
        <span class="stat-label">最大回撤</span>
        <span class="stat-value stat-value--loss">
          {{ formatPercent(statistics.maxDrawdown) }}
        </span>
      </div>
      <div class="stat-box stat-box--large">
        <span class="stat-label">夏普比率</span>
        <span class="stat-value" :class="getSharpeClass(statistics.sharpeRatio)">
          {{ statistics.sharpeRatio.toFixed(2) }}
        </span>
      </div>
    </div>

    <!-- 分隔线 -->
    <div class="divider"></div>

    <!-- 次要指标 -->
    <div class="stats-secondary">
      <div class="stat-box">
        <span class="stat-label">成交次数</span>
        <span class="stat-value">{{ executionCount ?? statistics.totalTrades }}</span>
      </div>
      <div v-if="statistics.closedTrades != null" class="stat-box">
        <span class="stat-label">已平仓交易</span>
        <span class="stat-value">{{ statistics.closedTrades }}</span>
      </div>
      <div class="stat-box">
        <span class="stat-label">已平仓胜率</span>
        <span class="stat-value" :class="getWinRateClass(statistics.winRate)">
          {{ formatPercent(statistics.winRate) }}
        </span>
      </div>
      <div class="stat-box">
        <span class="stat-label">盈利因子</span>
        <span class="stat-value" :class="getProfitFactorClass(statistics.profitFactor)">
          {{ statistics.profitFactor != null ? statistics.profitFactor.toFixed(2) : '-' }}
        </span>
      </div>
      <div class="stat-box">
        <span class="stat-label">平均持仓</span>
        <span class="stat-value">{{ statistics.avgHoldingTime ?? '-' }}</span>
      </div>
      <div class="stat-box">
        <span class="stat-label">盈利/亏损</span>
        <span class="stat-value">
          <span class="text-profit">{{ statistics.winTrades }}</span>
          <span class="text-muted"> / </span>
          <span class="text-loss">{{ statistics.lossTrades }}</span>
        </span>
      </div>
      <div class="stat-box">
        <span class="stat-label">最终资金</span>
        <span class="stat-value stat-value--highlight">{{ formatMoney(statistics.finalCapital) }}</span>
      </div>
    </div>

    <!-- 未实现盈亏说明 -->
    <div v-if="hasUnrealized(statistics)" class="unrealized-note">
      最终资金 = 现金 {{ formatMoney(statistics.balanceAtEnd ?? 0) }} + 未实现盈亏 
      <span :class="(statistics.unrealizedPnlTotal ?? 0) >= 0 ? 'text-profit' : 'text-loss'">
        {{ (statistics.unrealizedPnlTotal ?? 0) >= 0 ? '+' : '' }}{{ (statistics.unrealizedPnlTotal ?? 0).toFixed(2) }}
      </span>
    </div>

    <!-- 展开更多 -->
    <el-collapse-transition>
      <div v-if="expanded" class="stats-expanded">
        <div class="divider"></div>
        <div class="stats-secondary">
          <div class="stat-box">
            <span class="stat-label">索提诺比率</span>
            <span class="stat-value">{{ statistics.sortinoRatio != null ? statistics.sortinoRatio.toFixed(2) : '-' }}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">平均盈利</span>
            <span class="stat-value text-profit">{{ formatMoney(statistics.avgProfit) }}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">平均亏损</span>
            <span class="stat-value text-loss">{{ formatMoney(statistics.avgLoss) }}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">最大连胜</span>
            <span class="stat-value">{{ statistics.maxConsecutiveWins }} 次</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">最大连亏</span>
            <span class="stat-value">{{ statistics.maxConsecutiveLosses }} 次</span>
          </div>
        </div>
      </div>
    </el-collapse-transition>

    <!-- 展开按钮 -->
    <button class="expand-btn" @click="expanded = !expanded">
      <span>{{ expanded ? '收起' : '更多指标' }}</span>
      <el-icon :class="{ 'is-rotated': expanded }">
        <ArrowDown />
      </el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import type { BacktestStatistics } from '@/api/backtest'

defineProps<{
  statistics: BacktestStatistics
  executionCount?: number
}>()

const expanded = ref(false)

function hasUnrealized(statistics: BacktestStatistics): boolean {
  return statistics.unrealizedPnlTotal != null && statistics.unrealizedPnlTotal !== 0
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function formatMoney(value: number): string {
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function getValueClass(value: number): string {
  if (value > 0) return 'stat-value--profit'
  if (value < 0) return 'stat-value--loss'
  return ''
}

function getSharpeClass(value: number): string {
  if (value >= 2) return 'stat-value--excellent'
  if (value >= 1) return 'stat-value--good'
  if (value >= 0) return ''
  return 'stat-value--loss'
}

function getWinRateClass(value: number): string {
  if (value >= 60) return 'stat-value--excellent'
  if (value >= 50) return 'stat-value--good'
  return 'stat-value--warning'
}

function getProfitFactorClass(value: number): string {
  if (value >= 2) return 'stat-value--excellent'
  if (value >= 1.5) return 'stat-value--good'
  if (value >= 1) return ''
  return 'stat-value--loss'
}
</script>

<style scoped>
.summary-card {
  background: transparent;
}

/* ========== 主要指标 ========== */
.stats-primary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.stat-box--large {
  padding: 20px;
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.stat-box:not(.stat-box--large) .stat-value {
  font-size: 16px;
  font-weight: 600;
}

.stat-value--profit { color: var(--color-profit); }
.stat-value--loss { color: var(--color-loss); }
.stat-value--excellent { color: var(--color-profit); }
.stat-value--good { color: var(--color-primary); }
.stat-value--warning { color: var(--color-warning); }
.stat-value--highlight { color: var(--color-primary); }

/* ========== 分隔线 ========== */
.divider {
  height: 1px;
  background: var(--color-border);
  margin: 20px 0;
}

/* ========== 次要指标 ========== */
.stats-secondary {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 12px;
}

/* ========== 未实现盈亏说明 ========== */
.unrealized-note {
  margin-top: 16px;
  padding: 12px 16px;
  font-size: 13px;
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

/* ========== 展开区域 ========== */
.stats-expanded {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ========== 展开按钮 ========== */
.expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-top: 16px;
  padding: 12px;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.expand-btn:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: var(--color-primary-ghost);
}

.expand-btn .el-icon {
  transition: transform 0.2s ease;
}

.expand-btn .el-icon.is-rotated {
  transform: rotate(180deg);
}

/* ========== 响应式 ========== */
@media (max-width: 1200px) {
  .stats-secondary {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 900px) {
  .stats-primary {
    grid-template-columns: repeat(2, 1fr);
  }

  .stats-secondary {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .stats-primary,
  .stats-secondary {
    grid-template-columns: repeat(2, 1fr);
  }

  .stat-box--large {
    padding: 16px;
  }

  .stat-value {
    font-size: 20px;
  }
}
</style>
