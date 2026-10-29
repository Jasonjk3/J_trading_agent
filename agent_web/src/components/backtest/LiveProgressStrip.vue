<template>
  <div class="live-progress-strip" :class="{ 'is-pending': status === 'pending' }">
    <div class="strip-main">
      <div class="strip-status">
        <span class="live-pill">LIVE</span>
        <span class="status-text">{{ message || (status === 'pending' ? '等待执行...' : '回测进行中') }}</span>
      </div>

      <div v-if="status === 'running'" class="strip-meta">
        <span v-if="currentTime" class="meta-item">
          <span class="meta-label">模拟时间</span>
          <span class="meta-value">{{ formatSimTime(currentTime) }}</span>
        </span>
        <span
          v-if="currentStep != null && totalSteps != null"
          class="meta-item"
        >
          <span class="meta-label">步进</span>
          <span class="meta-value mono">{{ currentStep }}/{{ totalSteps }}</span>
        </span>
        <span class="meta-item">
          <span class="meta-label">进度</span>
          <span class="meta-value mono">{{ progress }}%</span>
        </span>
      </div>

      <button
        v-if="lastAction?.summary"
        type="button"
        class="last-action"
        :title="lastAction.summary"
        @click="$emit('focus-action', lastAction)"
      >
        <span class="action-kind">{{ lastAction.kind === 'trade' ? '成交' : '决策' }}</span>
        <span class="action-summary">{{ lastAction.summary }}</span>
      </button>
    </div>

    <div class="progress-track">
      <div
        class="progress-fill"
        :class="{ 'is-indeterminate': status === 'pending' }"
        :style="{ width: status === 'pending' ? '100%' : `${progress}%` }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BacktestStatus, LiveLastAction } from '@/api/backtest'

defineProps<{
  status: BacktestStatus
  progress: number
  message?: string
  currentTime?: string
  currentStep?: number | null
  totalSteps?: number | null
  lastAction?: LiveLastAction | null
}>()

defineEmits<{
  'focus-action': [action: LiveLastAction]
}>()

function formatSimTime(isoStr?: string) {
  if (!isoStr) return '—'
  const d = new Date(isoStr)
  if (Number.isNaN(d.getTime())) return isoStr
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.live-progress-strip {
  position: sticky;
  top: 0;
  z-index: 20;
  margin-bottom: 16px;
  padding: 12px 16px 0;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.strip-main {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding-bottom: 12px;
}

.strip-status {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.live-pill {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--color-warning);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  animation: pulse-soft 1.6s ease-in-out infinite;
}

.is-pending .live-pill {
  color: var(--color-info);
  background: var(--color-info-bg);
  border-color: var(--color-info-border);
}

.status-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.strip-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.meta-item {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}

.meta-label {
  font-size: 11px;
  color: var(--color-text-muted);
}

.meta-value {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.mono {
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.last-action {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: min(420px, 100%);
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.last-action:hover {
  border-color: var(--color-border-strong);
  background: var(--color-bg-active);
}

.action-kind {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
}

.action-summary {
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.progress-track {
  height: 3px;
  background: var(--color-border-light);
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.35s ease;
}

.progress-fill.is-indeterminate {
  width: 40% !important;
  animation: indeterminate 1.4s ease-in-out infinite;
}

@keyframes pulse-soft {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

@media (max-width: 900px) {
  .last-action {
    margin-left: 0;
    max-width: 100%;
    width: 100%;
  }
}
</style>
