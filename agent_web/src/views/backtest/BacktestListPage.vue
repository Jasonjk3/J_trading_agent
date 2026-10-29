<template>
  <div class="backtest-page">
    <!-- 页面头部 -->
    <header class="page-header">
      <div class="header-content">
        <div class="header-info">
          <h1 class="page-title">模拟回测</h1>
          <p class="page-subtitle">使用历史数据测试交易策略，评估策略表现和风险指标</p>
        </div>
        <div class="header-actions">
          <el-button
            v-if="selectedIds.length > 0"
            type="danger"
            plain
            :loading="batchDeleting"
            @click="handleBatchDelete"
          >
            删除选中 ({{ selectedIds.length }})
          </el-button>
          <el-button type="primary" @click="goToCreate">
            <el-icon><Plus /></el-icon>
            创建回测
          </el-button>
        </div>
      </div>
    </header>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-checkbox
          :model-value="allFilteredSelected"
          :indeterminate="selectAllIndeterminate"
          :disabled="filteredList.length === 0"
          @change="onSelectAllChange"
        >
          全选
        </el-checkbox>
      </div>
      <div class="toolbar-right">
        <div class="filter-group">
          <el-select
            v-model="filters.status"
            placeholder="全部状态"
            clearable
            class="status-filter"
          >
            <el-option label="等待中" value="pending">
              <span class="status-option">
                <span class="status-dot status-dot--pending"></span>
                等待中
              </span>
            </el-option>
            <el-option label="运行中" value="running">
              <span class="status-option">
                <span class="status-dot status-dot--running"></span>
                运行中
              </span>
            </el-option>
            <el-option label="已完成" value="completed">
              <span class="status-option">
                <span class="status-dot status-dot--completed"></span>
                已完成
              </span>
            </el-option>
            <el-option label="失败" value="failed">
              <span class="status-option">
                <span class="status-dot status-dot--failed"></span>
                失败
              </span>
            </el-option>
            <el-option label="已取消" value="cancelled" />
          </el-select>
          <el-input
            v-model="filters.keyword"
            placeholder="搜索回测任务..."
            clearable
            class="search-input"
            :prefix-icon="Search"
          />
        </div>
      </div>
    </div>

    <!-- 回测列表 -->
    <div v-loading="loading" class="backtest-grid">
      <template v-if="filteredList.length > 0">
        <div
          v-for="item in filteredList"
          :key="item.id"
          class="backtest-card"
          :class="{ 'is-selected': selectedIds.includes(item.id) }"
          @click="goToDetail(item.id)"
        >
          <!-- 选择框 -->
          <div class="card-select" @click.stop>
            <el-checkbox
              :model-value="selectedIds.includes(item.id)"
              @change="(val: boolean) => toggleItemSelect(item.id, val)"
            />
          </div>

          <!-- 卡片头部 -->
          <div class="card-header">
            <div class="card-title-row">
              <h3 class="card-title">{{ item.name }}</h3>
              <div class="card-title-trail">
                <div class="status-badge" :class="`status-badge--${item.status}`">
                  <span class="status-indicator"></span>
                  {{ getStatusText(item.status) }}
                </div>
                <div class="card-actions" @click.stop>
                  <el-button
                    v-if="item.status === 'running' || item.status === 'pending'"
                    type="danger"
                    text
                    size="small"
                    @click="handleStop(item)"
                  >
                    停止
                  </el-button>
                  <el-button
                    type="danger"
                    text
                    size="small"
                    @click="handleDelete(item)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </div>
            <div class="card-meta">
              <span class="meta-tag">
                <el-icon><Calendar /></el-icon>
                {{ formatDateRange(item.startTime, item.endTime) }}
              </span>
              <span class="meta-tag">
                <el-icon><Coin /></el-icon>
                {{ formatMoney(item.initialCapital) }} USDT
              </span>
            </div>
          </div>

          <!-- 卡片内容 -->
          <div class="card-body">
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">关联 Agent</span>
                <span 
                  class="info-value info-link"
                  @click.stop="goToAgent(item.agentId)"
                >
                  {{ item.agentName || '-' }}
                </span>
              </div>
              <div class="info-item">
                <span class="info-label">交易所</span>
                <span class="info-value">{{ getExchangeText(item.exchange) }}</span>
              </div>
              <div class="info-item info-item--wide">
                <span class="info-label">交易对</span>
                <span class="info-value info-symbols">{{ item.symbols.join(', ') }}</span>
              </div>
            </div>
          </div>

          <!-- 已完成状态 - 显示统计数据 -->
          <div v-if="item.status === 'completed'" class="card-stats">
            <div class="stat-item">
              <span class="stat-label">总收益</span>
              <span
                class="stat-value"
                :class="getReturnClass(item.totalReturn)"
              >
                {{ formatPercent(item.totalReturn) }}
              </span>
            </div>
            <div class="stat-item">
              <span class="stat-label">最大回撤</span>
              <span class="stat-value stat-value--loss">
                {{ formatPercent(item.maxDrawdown) }}
              </span>
            </div>
            <div class="stat-item">
              <span class="stat-label">胜率</span>
              <span class="stat-value">
                {{ item.winRate?.toFixed(1) }}%
              </span>
            </div>
            <div class="stat-item">
              <span class="stat-label">夏普比率</span>
              <span class="stat-value">
                {{ item.sharpeRatio?.toFixed(2) || '-' }}
              </span>
            </div>
          </div>

          <!-- 运行中状态 - 显示进度条 -->
          <div v-else-if="item.status === 'running'" class="card-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: '60%' }"></div>
            </div>
            <span class="progress-text">回测进行中...</span>
          </div>

          <!-- 等待中状态 -->
          <div v-else-if="item.status === 'pending'" class="card-pending">
            <div class="pending-indicator">
              <span class="pending-dot"></span>
              <span class="pending-dot"></span>
              <span class="pending-dot"></span>
            </div>
            <span class="pending-text">等待执行</span>
          </div>

          <!-- 失败状态 -->
          <div v-else-if="item.status === 'failed'" class="card-failed">
            <el-icon class="failed-icon"><WarningFilled /></el-icon>
            <span class="failed-text">执行失败</span>
          </div>
          <div v-else-if="item.status === 'cancelled'" class="card-failed card-cancelled">
            <el-icon class="failed-icon"><WarningFilled /></el-icon>
            <span class="failed-text">用户已取消</span>
          </div>

        </div>
      </template>

      <!-- 空状态 -->
      <div v-else class="empty-state">
        <div class="empty-icon">
          <el-icon><TrendCharts /></el-icon>
        </div>
        <h3 class="empty-title">暂无回测任务</h3>
        <p class="empty-desc">创建一个回测任务来验证您的交易策略</p>
        <el-button type="primary" @click="goToCreate">
          <el-icon><Plus /></el-icon>
          创建回测
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Calendar, Coin, TrendCharts, WarningFilled } from '@element-plus/icons-vue'
import { backtestApi, type BacktestListItem, type BacktestStatus } from '@/api/backtest'
import type { ExchangeCode } from '@/api/agents'

const router = useRouter()
const loading = ref(false)
const batchDeleting = ref(false)
const list = ref<BacktestListItem[]>([])
const selectedIds = ref<string[]>([])

const filters = reactive({
  status: '' as BacktestStatus | '',
  keyword: ''
})

const filteredList = computed(() => {
  return list.value.filter(item => {
    if (filters.status && item.status !== filters.status) return false
    if (filters.keyword && !item.name.toLowerCase().includes(filters.keyword.toLowerCase())) return false
    return true
  })
})

const filteredIds = computed(() => filteredList.value.map(i => i.id))

const allFilteredSelected = computed(() => {
  if (filteredList.value.length === 0) return false
  return filteredIds.value.every(id => selectedIds.value.includes(id))
})

const selectAllIndeterminate = computed(() => {
  const hasAny = filteredIds.value.some(id => selectedIds.value.includes(id))
  return hasAny && !allFilteredSelected.value
})

function toggleItemSelect(id: string, checked: boolean) {
  if (checked) {
    if (!selectedIds.value.includes(id)) {
      selectedIds.value = [...selectedIds.value, id]
    }
  } else {
    selectedIds.value = selectedIds.value.filter(x => x !== id)
  }
}

function onSelectAllChange(checked: boolean) {
  const ids = new Set(filteredIds.value)
  if (checked) {
    selectedIds.value = [...new Set([...selectedIds.value, ...filteredIds.value])]
  } else {
    selectedIds.value = selectedIds.value.filter(id => !ids.has(id))
  }
}

watch([() => filters.status, () => filters.keyword], () => {
  selectedIds.value = []
})

async function fetchList() {
  loading.value = true
  try {
    const res = await backtestApi.getList()
    list.value = res.list
  } catch (error) {
    console.error('Failed to fetch backtest list:', error)
  } finally {
    loading.value = false
  }
}

function goToCreate() {
  router.push('/backtest/create')
}

function goToDetail(id: string) {
  router.push(`/backtest/${id}`)
}

function goToAgent(agentId: string) {
  if (agentId) {
    router.push(`/agents/${agentId}`)
  }
}

async function handleStop(item: BacktestListItem) {
  try {
    await ElMessageBox.confirm(
      `确定要停止回测「${item.name}」吗？`,
      '停止回测',
      { type: 'warning' }
    )
    await backtestApi.stop(item.id)
    ElMessage.success('已停止回测')
    fetchList()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('停止失败')
    }
  }
}

async function handleDelete(item: BacktestListItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除回测「${item.name}」吗？此操作不可恢复。`,
      '删除回测',
      { type: 'warning' }
    )
    await backtestApi.delete(item.id)
    selectedIds.value = selectedIds.value.filter(id => id !== item.id)
    ElMessage.success('已删除')
    fetchList()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function handleBatchDelete() {
  const ids = [...selectedIds.value]
  if (ids.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定要删除已选中的 ${ids.length} 条回测吗？此操作不可恢复。`,
      '批量删除',
      { type: 'warning' }
    )
    batchDeleting.value = true
    await Promise.all(ids.map(id => backtestApi.delete(id)))
    ElMessage.success('已批量删除')
    selectedIds.value = []
    await fetchList()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量删除失败')
      await fetchList()
    }
  } finally {
    batchDeleting.value = false
  }
}

function getStatusText(status: BacktestStatus) {
  const map: Record<BacktestStatus, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status]
}

function getExchangeText(exchange: ExchangeCode) {
  const map: Record<ExchangeCode, string> = {
    binance: 'Binance',
    okx: 'OKX',
    bybit: 'Bybit'
  }
  return map[exchange]
}

function formatDateRange(start: string, end: string) {
  const startDate = new Date(start)
  const endDate = new Date(end)
  const format = (d: Date) => `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
  return `${format(startDate)} - ${format(endDate)}`
}

function formatMoney(value: number) {
  return value.toLocaleString('en-US')
}

function formatPercent(value?: number) {
  if (value === undefined) return '-'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function getReturnClass(value?: number) {
  if (value === undefined) return ''
  return value >= 0 ? 'stat-value--profit' : 'stat-value--loss'
}

onMounted(() => {
  fetchList()
})
</script>

<style scoped>
.backtest-page {
  min-height: 100%;
  padding: 24px;
  background: var(--color-bg-base);
}

/* ========== 页面头部 ========== */
.page-header {
  margin-bottom: 24px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.header-info {
  flex: 1;
}

.page-title {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

.page-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
  line-height: 1.5;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

/* ========== 工具栏 ========== */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 16px 20px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-filter {
  width: 140px;
}

.search-input {
  width: 220px;
}

.status-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-dot--pending {
  background: var(--color-info);
}

.status-dot--running {
  background: var(--color-warning);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot--completed {
  background: var(--color-profit);
}

.status-dot--failed {
  background: var(--color-loss);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ========== 回测卡片网格 ========== */
.backtest-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

/* ========== 回测卡片 ========== */
.backtest-card {
  position: relative;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 20px;
  padding-left: 52px;
  cursor: pointer;
  transition: all var(--transition-normal);
}

.backtest-card:hover {
  border-color: var(--color-border-strong);
  background: var(--color-bg-elevated);
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.backtest-card.is-selected {
  border-color: var(--color-primary);
  background: var(--color-primary-ghost);
}

/* 选择框 */
.card-select {
  position: absolute;
  top: 20px;
  left: 16px;
}

/* 卡片头部 */
.card-header {
  margin-bottom: 16px;
}

.card-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  margin-bottom: 12px;
}

.card-title {
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-title-trail {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 8px;
  margin-left: auto;
}

/* 状态徽章 */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-badge--pending {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.status-badge--pending .status-indicator {
  background: var(--color-info);
}

.status-badge--running {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.status-badge--running .status-indicator {
  background: var(--color-warning);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-badge--completed {
  background: var(--color-profit-bg);
  color: var(--color-profit);
}

.status-badge--completed .status-indicator {
  background: var(--color-profit);
}

.status-badge--failed {
  background: var(--color-loss-bg);
  color: var(--color-loss);
}

.status-badge--failed .status-indicator {
  background: var(--color-loss);
}

.status-badge--cancelled {
  background: var(--color-bg-hover);
  color: var(--color-text-muted);
}

.status-badge--cancelled .status-indicator {
  background: var(--color-text-muted);
}

/* 元信息标签 */
.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.meta-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.meta-tag .el-icon {
  font-size: 14px;
}

/* 卡片主体 */
.card-body {
  padding: 16px 0;
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item--wide {
  grid-column: span 2;
}

.info-label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.info-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.info-link {
  color: var(--color-primary);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.info-link:hover {
  color: var(--color-primary-light);
}

.info-symbols {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 统计数据 */
.card-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding-top: 16px;
}

.stat-item {
  text-align: center;
  padding: 8px 4px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-md);
}

.stat-label {
  display: block;
  font-size: 11px;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.stat-value--profit {
  color: var(--color-profit);
}

.stat-value--loss {
  color: var(--color-loss);
}

/* 进度条 */
.card-progress {
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-bar {
  height: 4px;
  background: var(--color-bg-elevated);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  color: var(--color-text-muted);
  text-align: center;
}

/* 等待中状态 */
.card-pending {
  padding-top: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.pending-indicator {
  display: flex;
  gap: 4px;
}

.pending-dot {
  width: 6px;
  height: 6px;
  background: var(--color-info);
  border-radius: 50%;
  animation: pendingWave 1.4s ease-in-out infinite;
}

.pending-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.pending-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pendingWave {
  0%, 60%, 100% {
    transform: scale(1);
    opacity: 0.5;
  }
  30% {
    transform: scale(1.3);
    opacity: 1;
  }
}

.pending-text {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 失败状态 */
.card-failed {
  padding-top: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-loss);
}

.failed-icon {
  font-size: 18px;
}

.failed-text {
  font-size: 13px;
  font-weight: 500;
}

.card-cancelled {
  color: var(--color-text-muted);
}

/* 卡片操作（与状态徽章同一行，避免与绝对定位重叠） */
.card-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 0;
}

.card-actions :deep(.el-button) {
  padding: 4px 8px;
  margin: 0;
}

/* ========== 空状态 ========== */
.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
  background: var(--color-bg-card);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-xl);
  text-align: center;
}

.empty-icon {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-ghost);
  border-radius: 50%;
  margin-bottom: 24px;
}

.empty-icon .el-icon {
  font-size: 36px;
  color: var(--color-primary);
}

.empty-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.empty-desc {
  margin: 0 0 24px;
  font-size: 14px;
  color: var(--color-text-muted);
}

/* ========== 响应式 ========== */
@media (max-width: 768px) {
  .backtest-page {
    padding: 16px;
  }

  .header-content {
    flex-direction: column;
    gap: 16px;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .toolbar {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .toolbar-left,
  .toolbar-right {
    width: 100%;
  }

  .filter-group {
    flex-direction: column;
    width: 100%;
  }

  .status-filter,
  .search-input {
    width: 100%;
  }

  .backtest-grid {
    grid-template-columns: 1fr;
  }

  .card-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
