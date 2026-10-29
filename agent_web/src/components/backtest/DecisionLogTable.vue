<template>
  <div class="decision-log-table">
    <div class="table-header">
      <h4 class="table-title">决策记录</h4>
      <p class="table-desc">每次 Agent 决策时的分析结论、规则命中与当时价格（含观望）</p>
    </div>

    <el-table
      :data="paginatedDecisions"
      :row-key="getRowKey"
      :expand-row-keys="expandedRowKeys"
      class="custom-table"
      table-layout="fixed"
      @expand-change="handleExpandChange"
    >
      <el-table-column type="expand" width="56">
        <template #default="{ row }">
          <div class="analysis-detail">
            <div v-if="ruleMeta(row).decisionMode" class="meta-row">
              <el-tag size="small" effect="plain" type="info">
                {{ ruleMeta(row).decisionMode === 'rule' ? '规则策略' : 'AI 交易员' }}
              </el-tag>
              <el-tag v-if="ruleMeta(row).regime" size="small" effect="plain">
                {{ regimeLabel(ruleMeta(row).regime) }}
              </el-tag>
            </div>

            <div class="analysis-block">
              <div class="analysis-label">决策分析</div>
              <div class="analysis-content">{{ row.decisionAnalysis || row.reasoning || '-' }}</div>
            </div>

            <div v-if="row.executionResult" class="analysis-block">
              <div class="analysis-label">最终操作结果</div>
              <div class="analysis-content">{{ executionSummary(row) }}</div>
            </div>

            <div v-if="ruleMeta(row).signals?.length" class="analysis-block">
              <div class="analysis-label">信号标签</div>
              <div class="signal-tags">
                <el-tag
                  v-for="signal in ruleMeta(row).signals"
                  :key="signal"
                  size="small"
                  effect="plain"
                >
                  {{ signal }}
                </el-tag>
              </div>
            </div>

            <div v-if="ruleMeta(row).ruleHits?.length" class="analysis-block">
              <div class="analysis-label">规则命中</div>
              <pre class="analysis-content">{{ formatRuleHits(ruleMeta(row).ruleHits) }}</pre>
            </div>

            <div v-if="hasIndicatorSnapshot(row)" class="analysis-block">
              <div class="analysis-label">指标快照</div>
              <pre class="analysis-content">{{ formatIndicators(ruleMeta(row).indicatorsSnapshot) }}</pre>
            </div>

            <template v-if="ruleMeta(row).decisionMode !== 'rule'">
              <div class="analysis-block">
                <div class="analysis-label">多周期摘要</div>
                <pre class="analysis-content analysis-content--technical">{{
                  parseTechnicalAnalysis(row.technicalAnalysis).summary
                }}</pre>
              </div>
              <div class="analysis-block">
                <div class="analysis-label">关键位</div>
                <pre class="analysis-content">{{
                  parseTechnicalAnalysis(row.technicalAnalysis).keyLevels
                }}</pre>
              </div>
              <div class="analysis-block">
                <div class="analysis-label">风险</div>
                <pre class="analysis-content">{{ parseTechnicalAnalysis(row.technicalAnalysis).risk }}</pre>
              </div>
            </template>

            <div v-if="resolveDecisionPrompt(row)" class="analysis-block">
              <div class="analysis-label">决策 Prompt</div>
              <pre class="analysis-content analysis-content--prompt">{{ resolveDecisionPrompt(row) }}</pre>
            </div>

            <div v-if="resolveLlmRawResponse(row)" class="analysis-block">
              <div class="analysis-label">LLM 原始响应</div>
              <pre class="analysis-content analysis-content--prompt">{{ resolveLlmRawResponse(row) }}</pre>
            </div>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="时间" width="180">
        <template #default="{ row }">
          <span class="time-cell">{{ formatTime(row.timestamp) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="决策" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="getActionTagType(row.action)" size="small" effect="plain">
            {{ actionLabel(row.action) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="模式" width="88" align="center">
        <template #default="{ row }">
          <span class="mode-cell">{{ modeShortLabel(row) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="交易对" width="124" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="symbol-cell">{{ row.symbol || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="当时价格" min-width="136" align="right">
        <template #default="{ row }">
          <span class="price-cell">{{ formatPrice(row.currentPrice) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="最终操作结果" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">
          <span :class="['execution-cell', `is-${row.executionResult?.status || 'legacy'}`]">
            {{ executionSummary(row) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="简述" min-width="280" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="reasoning-cell">{{ summarizeDecision(row) }}</span>
        </template>
      </el-table-column>
    </el-table>

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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { backtestApi } from '@/api/backtest'
import type { BacktestDecisionRecord, RuleHitRecord } from '@/api/backtest'

const props = defineProps<{
  backtestId: string
  decisions: BacktestDecisionRecord[]
  total?: number
  remote?: boolean
}>()

const emit = defineEmits<{
  select: [decision: BacktestDecisionRecord]
  'page-change': [payload: { page: number; pageSize: number }]
}>()

const currentPage = ref(1)
const pageSize = ref(20)
const expandedRowKeys = ref<string[]>([])
const decisionDetails = reactive<Record<string, BacktestDecisionRecord>>({})

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
  close_short: '平空'
}

interface RuleAuditMeta {
  decisionMode?: 'trader' | 'rule'
  regime?: string
  ruleHits?: RuleHitRecord[]
  signals?: string[]
  indicatorsSnapshot?: Record<string, unknown>
}

function ruleMeta(row: BacktestDecisionRecord): RuleAuditMeta {
  if (row.decisionMode || row.ruleHits?.length || row.regime) {
    return {
      decisionMode: row.decisionMode,
      regime: row.regime,
      ruleHits: row.ruleHits,
      signals: row.signals,
      indicatorsSnapshot: row.indicatorsSnapshot,
    }
  }
  const audit = row.chainOfThought?.find(
    (item) => typeof item === 'object' && item && (item as { type?: string }).type === 'rule_audit'
  ) as {
    decisionMode?: 'trader' | 'rule'
    regime?: string
    ruleHits?: RuleHitRecord[]
    signals?: string[]
    indicatorsSnapshot?: Record<string, unknown>
  } | undefined
  return {
    decisionMode: audit?.decisionMode,
    regime: audit?.regime,
    ruleHits: audit?.ruleHits,
    signals: audit?.signals,
    indicatorsSnapshot: audit?.indicatorsSnapshot,
  }
}

function actionLabel(action: string): string {
  return actionLabels[action] ?? action
}

function formatNumber(value?: number): string {
  if (value == null || Number.isNaN(value)) return '-'
  return value.toLocaleString(undefined, { maximumFractionDigits: 8 })
}

function executionSummary(row: BacktestDecisionRecord): string {
  const result = row.executionResult
  if (!result) {
    if (row.action === 'hold') return '未操作'
    if (row.action === 'system_error') return '系统错误，未执行'
    return row.quantity != null ? `历史记录：计划数量 ${formatNumber(row.quantity)}` : '历史记录无执行回执'
  }
  if (result.status === 'filled') {
    const action = actionLabel(result.finalAction || row.action)
    const parts = [
      `${action} ${formatNumber(result.quantity)} @ ${formatNumber(result.price)}`,
      `杠杆 ${formatNumber(result.approvedLeverage ?? result.requestedLeverage)}x`,
      `保证金 ${formatNumber(result.marginUsed)}`,
      `金额 ${formatNumber(result.amount)}`,
      `手续费 ${formatNumber(result.fee)}`,
      `操作后持仓 ${formatNumber(result.positionQuantityAfter)}`,
    ]
    return parts.join('；')
  }
  if (result.status === 'rejected') {
    return `未执行：${result.message || '风控或撮合复核拒绝'}`
  }
  if (result.status === 'error') return result.message || '系统错误，未执行'
  if (result.status === 'pending') return '等待执行'
  return result.message || '未操作'
}

function regimeLabel(regime?: string): string {
  if (regime === 'trending') return '趋势市'
  if (regime === 'ranging') return '震荡市'
  return regime || '-'
}

function modeShortLabel(row: BacktestDecisionRecord): string {
  const mode = ruleMeta(row).decisionMode
  if (mode === 'rule') return '规则'
  if (mode === 'trader') return '交易员'
  return row.technicalAnalysis ? '交易员' : '-'
}

function getActionTagType(action: string): 'info' | 'success' | 'danger' | 'warning' {
  if (action === 'hold') return 'info'
  if (action === 'system_error') return 'danger'
  if (action?.startsWith('open') || action?.startsWith('add')) return 'success'
  if (action?.startsWith('close')) return 'danger'
  return 'warning'
}

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function formatPrice(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return '-'
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 })
}

function summarizeDecision(row: BacktestDecisionRecord): string {
  const meta = ruleMeta(row)
  const base = row.decisionAnalysis || row.reasoning || ''
  if (meta.decisionMode === 'rule' && meta.regime) {
    return base ? `${base}（${regimeLabel(meta.regime)}）` : regimeLabel(meta.regime)
  }
  return base || row.technicalAnalysis || '-'
}

function formatRuleHits(hits?: RuleHitRecord[]): string {
  if (!hits?.length) return '-'
  return hits
    .map((hit) => {
      const parts = [hit.rule_id, hit.action, hit.reason].filter(Boolean)
      return `- ${parts.join(' | ')}`
    })
    .join('\n')
}

function hasIndicatorSnapshot(row: BacktestDecisionRecord): boolean {
  const snap = ruleMeta(row).indicatorsSnapshot
  return !!snap && Object.keys(snap).length > 0
}

function findChainItem(row: BacktestDecisionRecord, type: string) {
  return row.chainOfThought?.find(
    (item) => typeof item === 'object' && item && (item as { type?: string }).type === type,
  ) as Record<string, unknown> | undefined
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

function formatIndicators(snapshot?: Record<string, unknown>): string {
  if (!snapshot || !Object.keys(snapshot).length) return '-'
  return JSON.stringify(snapshot, null, 2)
}

function getRowKey(row: BacktestDecisionRecord): string {
  return [row.timestamp, row.action, row.symbol || '-', row.quantity ?? '-'].join('__')
}

async function handleExpandChange(row: BacktestDecisionRecord, expandedRows: BacktestDecisionRecord[]) {
  expandedRowKeys.value = expandedRows.length ? [getRowKey(row)] : []
  if (!expandedRows.length) return

  emit('select', row)
  if (!row.id || decisionDetails[row.id]) return
  try {
    const detail = await backtestApi.getDecision(props.backtestId, row.id)
    decisionDetails[row.id] = detail
    emit('select', detail)
  } catch {
    ElMessage.error('加载决策详情失败')
  }
}

function parseTechnicalAnalysis(text?: string): { summary: string; keyLevels: string; risk: string } {
  if (!text?.trim()) {
    return {
      summary: '-',
      keyLevels: '-',
      risk: '-',
    }
  }

  const blocks = text
    .split(/\n\s*\n+/)
    .map((block) => block.trim())
    .filter(Boolean)

  const summaryParts: string[] = []
  const keyLevelParts: string[] = []
  const riskParts: string[] = []

  for (const block of blocks) {
    const lines = block
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)

    const summaryLines: string[] = []
    const keyLines: string[] = []
    const riskLines: string[] = []

    for (const line of lines) {
      if (/^-\s*大级别关键位/.test(line)) {
        keyLines.push(line.replace(/^-+\s*/, ''))
        continue
      }
      if (/^-\s*关键风险/.test(line)) {
        riskLines.push(line.replace(/^-+\s*/, ''))
        continue
      }
      summaryLines.push(line)
    }

    if (summaryLines.length) summaryParts.push(summaryLines.join('\n'))
    if (keyLines.length) keyLevelParts.push(keyLines.join('\n'))
    if (riskLines.length) riskParts.push(riskLines.join('\n'))
  }

  return {
    summary: summaryParts.join('\n\n') || text.trim(),
    keyLevels: keyLevelParts.join('\n\n') || '-',
    risk: riskParts.join('\n\n') || '-',
  }
}

const paginatedDecisions = computed(() => {
  const rows = props.decisions.map((row) => (
    row.id && decisionDetails[row.id]
      ? { ...row, ...decisionDetails[row.id] }
      : row
  ))
  if (props.remote) return rows
  const start = (currentPage.value - 1) * pageSize.value
  return rows.slice(start, start + pageSize.value)
})

const tableTotal = computed(() => {
  if (props.remote) return props.total ?? props.decisions.length
  return props.decisions.length
})

watch([currentPage, pageSize], () => {
  expandedRowKeys.value = []
  if (props.remote) {
    emit('page-change', { page: currentPage.value, pageSize: pageSize.value })
  }
})

watch(
  () => props.backtestId,
  () => {
    expandedRowKeys.value = []
    for (const key of Object.keys(decisionDetails)) delete decisionDetails[key]
  },
)
</script>

<style scoped>
.decision-log-table {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  padding: 20px;
  border: 1px solid var(--color-border);
}

.table-header {
  margin-bottom: 16px;
}

.table-title {
  margin: 0 0 4px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.table-desc {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.5;
}

.custom-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(255, 255, 255, 0.02);
  --el-table-border-color: var(--table-border-color, rgba(255, 255, 255, 0.06));
  cursor: default;
}

.custom-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.custom-table :deep(.el-table__row:hover > td) {
  background: rgba(255, 255, 255, 0.05) !important;
}

.custom-table :deep(th.el-table__cell) {
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.custom-table :deep(td.el-table__cell) {
  color: var(--color-text-primary);
}

.custom-table :deep(.el-table__expanded-cell) {
  background: rgba(255, 255, 255, 0.02) !important;
  padding: 16px 20px !important;
}

.time-cell {
  white-space: nowrap;
  font-size: 12px;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.mode-cell {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.symbol-cell {
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.price-cell {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, 'SF Mono', Monaco, monospace;
}

.reasoning-cell {
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.analysis-detail {
  display: grid;
  gap: 12px;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.signal-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.analysis-block {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  padding: 12px 14px;
}

.analysis-label {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.analysis-content {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.analysis-content--technical {
  max-height: 360px;
  overflow: auto;
}

.analysis-content--prompt {
  max-height: 420px;
  overflow: auto;
  font-family: ui-monospace, 'SF Mono', Monaco, monospace;
  font-size: 12px;
}

.table-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
