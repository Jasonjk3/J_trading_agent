<template>
  <div
    class="agent-card"
    :class="{ 'is-active': isActive, 'is-running': agent.status === 'running' }"
    @click="$emit('select', agent)"
    @contextmenu.prevent="showContextMenu"
  >
    <div class="card-header">
      <span class="status-dot" :class="agent.status"></span>
      <span class="agent-name">{{ agent.name }}</span>
    </div>
    <div class="card-meta">
      <span class="exchange">{{ exchangeLabel(agent.exchange) }}</span>
      <span class="divider">·</span>
      <span class="status-text">{{ agent.status === 'running' ? '运行中' : '已停止' }}</span>
    </div>
    <div class="card-stats">
      <template v-if="agent.status === 'running' && agent.todayProfit !== undefined">
        <span class="profit" :class="profitClass">
          💰 {{ formatProfit(agent.todayProfit) }} 今日
        </span>
      </template>
      <template v-else>
        <span class="last-run">最近：{{ formatDate(agent.lastRunAt) }}</span>
      </template>
    </div>

    <el-dropdown
      ref="dropdownRef"
      class="card-actions"
      trigger="click"
      placement="bottom-end"
      @command="handleCommand"
      @click.stop
    >
      <el-button
        text
        circle
        size="small"
        :icon="MoreFilled"
        aria-label="Agent 操作"
        title="更多操作"
        @click.stop
      />
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item :command="agent.status === 'running' ? 'stop' : 'start'">
            <el-icon><VideoPlay v-if="agent.status !== 'running'" /><VideoPause v-else /></el-icon>
            {{ agent.status === 'running' ? '停止' : '启动' }}
          </el-dropdown-item>
          <el-dropdown-item command="edit">
            <el-icon><Edit /></el-icon>
            编辑
          </el-dropdown-item>
          <el-dropdown-item command="delete" divided :disabled="agent.status === 'running'">
            <el-icon><Delete /></el-icon>
            {{ agent.status === 'running' ? '删除（请先停止）' : '删除' }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { VideoPlay, VideoPause, Edit, Delete, MoreFilled } from '@element-plus/icons-vue'
import type { AgentListItem, ExchangeCode } from '@/api/agents'

const props = defineProps<{
  agent: AgentListItem
  isActive: boolean
}>()

const emit = defineEmits<{
  select: [agent: AgentListItem]
  start: [agent: AgentListItem]
  stop: [agent: AgentListItem]
  edit: [agent: AgentListItem]
  delete: [agent: AgentListItem]
}>()

const dropdownRef = ref()

const profitClass = computed(() => {
  const profit = props.agent.todayProfit
  if (profit === undefined) return ''
  const val = parseFloat(String(profit))
  if (val > 0) return 'positive'
  if (val < 0) return 'negative'
  return ''
})

function exchangeLabel(code?: ExchangeCode): string {
  if (!code) return '-'
  const map: Record<ExchangeCode, string> = { binance: 'Binance', okx: 'OKX', bybit: 'Bybit' }
  return map[code] ?? code
}

function formatProfit(val: number | string | undefined): string {
  if (val === undefined) return '-'
  const n = parseFloat(String(val))
  if (Number.isNaN(n)) return String(val)
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function formatDate(iso?: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function showContextMenu() {
  dropdownRef.value?.handleOpen?.()
}

function handleCommand(cmd: string) {
  switch (cmd) {
    case 'start':
      emit('start', props.agent)
      break
    case 'stop':
      emit('stop', props.agent)
      break
    case 'edit':
      emit('edit', props.agent)
      break
    case 'delete':
      emit('delete', props.agent)
      break
  }
}
</script>

<style scoped>
.agent-card {
  position: relative;
  padding: 12px 14px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.agent-card:hover {
  border-color: var(--color-border-active);
  background: var(--color-bg-hover);
}

.agent-card.is-active {
  border-color: var(--color-primary);
  background: var(--color-primary-ghost);
}

.agent-card.is-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--gradient-primary);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.running {
  background: var(--color-success, #10B981);
  box-shadow: 0 0 6px var(--color-success, #10B981);
  animation: pulse 2s infinite;
}

.status-dot.stopped {
  background: var(--color-text-disabled, #6B7280);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-muted);
  margin-bottom: 8px;
}

.divider {
  opacity: 0.5;
}

.card-stats {
  font-size: 12px;
}

.profit {
  font-weight: 500;
}

.profit.positive {
  color: var(--color-profit, #10B981);
}

.profit.negative {
  color: var(--color-loss, #EF4444);
}

.last-run {
  color: var(--color-text-muted);
}

.card-actions {
  position: absolute;
  top: 7px;
  right: 7px;
  z-index: 2;
  opacity: 0.55;
  transition: opacity var(--transition-fast);
}

.agent-card:hover .card-actions,
.agent-card:focus-within .card-actions,
.agent-card.is-active .card-actions {
  opacity: 1;
}

.card-actions :deep(.el-button) {
  color: var(--color-text-muted);
}

.card-actions :deep(.el-button:hover) {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}
</style>
