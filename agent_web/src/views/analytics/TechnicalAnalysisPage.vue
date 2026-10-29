<template>
  <div class="ta-page page-content">
    <div class="page-card main-card">
      <div class="page-header">
        <div class="header-copy">
          <div class="header-kicker">
            <span class="kicker-icon"><DataAnalysis /></span>
            <span>AI 技术研究</span>
          </div>
          <h2 class="page-title">技术指标分析</h2>
          <p class="page-desc">聚合 OKX 历史 K 线与多周期指标，使用大模型生成结构化市场研判。</p>
        </div>
        <div class="header-meta" aria-label="分析能力">
          <span><i class="meta-dot"></i>OKX 行情已连接</span>
          <span>8 个分析周期</span>
        </div>
      </div>

      <div class="form-section">
        <div class="form-section-header">
          <div>
            <h3>创建分析任务</h3>
            <p>选择市场参数和推理模型，通常需要 30–90 秒完成。</p>
          </div>
          <span class="step-badge">01 / 参数配置</span>
        </div>
        <div class="form-grid">
          <div class="form-item">
            <label class="form-label">交易对</label>
            <el-select
              v-model="form.symbol"
              filterable
              remote
              clearable
              :remote-method="loadSymbols"
              :loading="symbolLoading"
              placeholder="如 BTCUSDT"
              class="form-control"
            >
              <el-option
                v-for="item in symbolOptions"
                :key="item.symbol"
                :label="item.symbol"
                :value="item.symbol"
              />
            </el-select>
          </div>
          <div class="form-item">
            <label class="form-label">截止日期</label>
            <el-date-picker
              v-model="form.analysisDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="默认今天"
              class="form-control"
            />
          </div>
          <div class="form-item">
            <label class="form-label">K 线周期</label>
            <el-select v-model="form.timeframe" class="form-control">
              <el-option v-for="tf in timeframeOptions" :key="tf" :label="tf" :value="tf" />
            </el-select>
          </div>
          <div class="form-item">
            <label class="form-label">回溯天数</label>
            <el-input-number v-model="form.lookbackDays" :min="7" :max="365" :step="1" class="form-control" />
          </div>
          <div class="form-item form-item-wide">
            <label class="form-label">分析模型</label>
            <el-select
              v-model="form.llmModelId"
              clearable
              filterable
              placeholder="默认（环境变量 DeepSeek）"
              class="form-control"
              :loading="loadingModels"
            >
              <template v-if="llmModels.length === 0 && !loadingModels" #empty>
                <span class="select-empty">暂无可用模型，请先在「模型管理」中配置</span>
              </template>
              <el-option
                v-for="m in llmModels"
                :key="m.id"
                :label="`${m.name} (${m.provider})`"
                :value="m.id"
              />
            </el-select>
          </div>
          <div class="form-item">
            <label class="form-label">温度</label>
            <el-input-number
              v-model="form.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              :precision="1"
              controls-position="right"
              class="form-control"
            />
          </div>
        </div>
        <div class="form-actions">
          <div class="form-hint">
            <span class="hint-dot"></span>
            报告将保存到下方历史记录
          </div>
          <el-button type="primary" size="large" :loading="loading" @click="runAnalyze">
            <el-icon v-if="!loading" class="btn-icon"><DataAnalysis /></el-icon>
            {{ loading ? '正在生成分析' : '生成分析报告' }}
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="errorMsg"
        type="error"
        :closable="true"
        show-icon
        class="error-alert"
        :title="errorMsg"
        @close="errorMsg = ''"
      />
    </div>

    <div class="page-card records-card">
      <div class="records-header">
        <div class="records-title-row">
          <div class="section-icon"><Document /></div>
          <div>
            <h3 class="section-title">分析记录</h3>
            <p class="section-desc">查看近期生成的技术分析报告</p>
          </div>
          <span class="records-count">{{ recordsTotal }} 份报告</span>
        </div>
        <el-button class="refresh-btn" :loading="loadingRecords" @click="loadRecords">
          <el-icon v-if="!loadingRecords"><Refresh /></el-icon>
          刷新
        </el-button>
      </div>

      <div class="records-table-wrap" v-loading="loadingRecords">
        <el-table
          :data="recordRows"
          class="records-table"
          row-class-name="record-row"
        >
          <el-table-column prop="createdAt" label="生成时间" min-width="160">
            <template #default="{ row }">
              <span class="cell-time">{{ formatRecordTime(row.createdAt) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="symbol" label="交易对" min-width="110">
            <template #default="{ row }">
              <span class="cell-symbol">{{ row.symbol }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="analysisDate" label="截止日" min-width="100">
            <template #default="{ row }">
              {{ row.analysisDate || '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="timeframe" label="周期" min-width="70" />
          <el-table-column prop="lookbackDays" label="回溯" min-width="70">
            <template #default="{ row }">
              {{ row.lookbackDays }}天
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="80">
            <template #default="{ row }">
              <span :class="['status-badge', row.success ? 'status-success' : 'status-fail']">
                {{ row.success ? '成功' : '失败' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="summaryPreview" label="摘要" min-width="240">
            <template #default="{ row }">
              <span class="cell-summary" :title="row.summaryPreview">{{ row.summaryPreview || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link class="detail-link" @click="goRecordDetail(row.id)">
                查看详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="records-footer">
        <el-pagination
          v-model:current-page="recordsPage"
          v-model:page-size="recordsPageSize"
          :total="recordsTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="loadRecords"
          @size-change="onRecordsPageSizeChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataAnalysis, Document, Refresh } from '@element-plus/icons-vue'
import { technicalAnalysisApi } from '@/api/technicalAnalysis'
import type { TechnicalAnalysisRecordItem } from '@/api/technicalAnalysis'
import { modelManagementApi, type ModelItem } from '@/api/modelManagement'
import { marketApi } from '@/api/market'
import type { MarketSymbolItem } from '@/api/market'

const SESSION_PREVIEW_KEY = 'technicalAnalysisPreview'

const router = useRouter()

const timeframeOptions = ['15m', '1h', '2h', '4h', '6h', '12h', '1d', '1w']

const form = ref({
  symbol: 'BTCUSDT',
  analysisDate: '' as string | undefined,
  timeframe: '4h',
  lookbackDays: 30,
  llmModelId: undefined as number | undefined,
  temperature: 0.3,
})

const loading = ref(false)
const errorMsg = ref('')

const symbolLoading = ref(false)
const symbolOptions = ref<MarketSymbolItem[]>([])

const loadingModels = ref(false)
const llmModels = ref<ModelItem[]>([])

const recordRows = ref<TechnicalAnalysisRecordItem[]>([])
const loadingRecords = ref(false)
const recordsTotal = ref(0)
const recordsPage = ref(1)
const recordsPageSize = ref(20)

async function loadSymbols(q: string) {
  if (!q?.trim()) return
  symbolLoading.value = true
  try {
    const res = await marketApi.searchSymbols(q.trim())
    symbolOptions.value = res.list ?? []
  } finally {
    symbolLoading.value = false
  }
}

function formatRecordTime(iso?: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 19)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadRecords() {
  loadingRecords.value = true
  try {
    const data = await technicalAnalysisApi.listRecords({
      page: recordsPage.value,
      pageSize: recordsPageSize.value,
    })
    recordRows.value = data.items ?? []
    recordsTotal.value = data.total ?? 0
  } catch {
    recordRows.value = []
    recordsTotal.value = 0
  } finally {
    loadingRecords.value = false
  }
}

function onRecordsPageSizeChange() {
  recordsPage.value = 1
  loadRecords()
}

function goRecordDetail(id: string) {
  router.push({ name: 'TechnicalAnalysisRecord', params: { recordId: id } })
}

async function runAnalyze() {
  if (!form.value.symbol?.trim()) {
    ElMessage.warning('请选择或输入交易对')
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await technicalAnalysisApi.analyze({
      symbol: form.value.symbol.trim(),
      analysisDate: form.value.analysisDate || undefined,
      timeframe: form.value.timeframe,
      lookbackDays: form.value.lookbackDays,
      llmModelId: form.value.llmModelId,
      temperature: form.value.temperature,
    })
    if (!data.success) {
      errorMsg.value = data.error || '分析失败'
      await loadRecords()
      return
    }
    await loadRecords()
    if (data.recordId) {
      router.push({ name: 'TechnicalAnalysisRecord', params: { recordId: data.recordId } })
    } else {
      try {
        sessionStorage.setItem(SESSION_PREVIEW_KEY, JSON.stringify(data))
      } catch {
        /* ignore */
      }
      router.push({ name: 'TechnicalAnalysisReportPreview' })
    }
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : '请求失败'
  } finally {
    loading.value = false
  }
}

async function loadLlmModels() {
  loadingModels.value = true
  try {
    const res = await modelManagementApi.getModels({ is_active: true })
    llmModels.value = res.items || []
  } catch {
    llmModels.value = []
  } finally {
    loadingModels.value = false
  }
}

onMounted(() => {
  loadSymbols('BTC')
  loadLlmModels()
  loadRecords()
})
</script>

<style scoped>
.ta-page {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-card {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.main-card { padding: 28px; }

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 24px;
}

.header-copy { min-width: 0; }
.header-kicker {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 10px;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .04em;
}
.kicker-icon {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  color: #fff;
  background: var(--color-primary);
  border-radius: 6px;
}
.kicker-icon :deep(svg) { width: 14px; height: 14px; }
.page-title { margin: 0 0 8px; font-size: 26px; font-weight: 700; color: var(--color-text-primary); letter-spacing: -.025em; }
.page-desc { margin: 0; max-width: 760px; font-size: 14px; color: var(--color-text-muted); line-height: 1.65; }
.header-meta { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.header-meta span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  padding: 0 10px;
  color: var(--color-text-secondary);
  background: #f8fafc;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  font-size: 12px;
}
.meta-dot { width: 7px; height: 7px; background: var(--color-profit); border-radius: 50%; }

.form-section { background: #f8fafc; border: 1px solid var(--color-border); border-radius: 10px; overflow: hidden; }
.form-section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px;
  background: #fff;
  border-bottom: 1px solid var(--color-border);
}
.form-section-header h3 { margin: 0 0 3px; color: var(--color-text-primary); font-size: 15px; font-weight: 650; }
.form-section-header p { margin: 0; color: var(--color-text-muted); font-size: 12px; }
.step-badge { padding: 5px 8px; color: var(--color-primary); background: var(--color-primary-ghost); border: 1px solid #dbeafe; border-radius: 6px; font-size: 11px; font-weight: 700; }
.form-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px 20px; padding: 22px 20px; }
.form-item { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.form-item-wide { grid-column: span 2; }
.form-label { font-size: 12px; font-weight: 650; color: var(--color-text-secondary); }
.form-control { width: 100%; }
.form-section :deep(.el-input__wrapper),
.form-section :deep(.el-select__wrapper) { min-height: 40px; background: #fff !important; }
.form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 20px;
  background: #fff;
  border-top: 1px solid var(--color-border);
}
.form-actions .el-button { min-width: 172px; height: 40px; }
.form-hint { display: flex; align-items: center; gap: 8px; color: var(--color-text-muted); font-size: 12px; }
.hint-dot { width: 6px; height: 6px; background: #94a3b8; border-radius: 50%; }
.btn-icon { margin-right: 6px; }
.select-empty { padding: 8px 12px; color: var(--color-text-muted); }
.error-alert { margin-top: 16px; }

.records-card { padding: 0; overflow: hidden; }
.records-header {
  min-height: 76px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}
.records-title-row { display: flex; align-items: center; gap: 12px; }
.section-icon { width: 36px; height: 36px; display: grid; place-items: center; color: var(--color-primary); background: var(--color-primary-ghost); border-radius: 8px; }
.section-icon :deep(svg) { width: 18px; }
.section-title { margin: 0; color: var(--color-text-primary); font-size: 16px; font-weight: 650; }
.section-desc { margin: 2px 0 0; color: var(--color-text-muted); font-size: 12px; }
.records-count { margin-left: 4px; padding: 4px 8px; color: var(--color-text-secondary); background: #f1f5f9; border-radius: 6px; font-size: 11px; font-weight: 600; }
.refresh-btn .el-icon { margin-right: 5px; }
.records-table-wrap { min-height: 180px; overflow: hidden; }
.records-table { width: 100%; }
:deep(.records-table th.el-table__cell) { height: 44px; background: #f8fafc !important; }
:deep(.records-table td.el-table__cell) { height: 54px; }
:deep(.record-row) { transition: background var(--transition-fast); }
.cell-time { font-size: 12px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
.cell-symbol { font-weight: 650; color: var(--color-text-primary); }
.cell-summary { display: block; overflow: hidden; color: var(--color-text-secondary); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.status-badge { display: inline-flex; align-items: center; padding: 4px 9px; border: 1px solid transparent; border-radius: 6px; font-size: 11px; font-weight: 650; }
.status-success { color: var(--color-profit); background: var(--color-profit-bg); border-color: var(--color-profit-border); }
.status-fail { color: var(--color-loss); background: var(--color-loss-bg); border-color: var(--color-loss-border); }
.detail-link { font-weight: 600; }
.records-footer { min-height: 64px; display: flex; align-items: center; justify-content: flex-end; padding: 12px 20px; border-top: 1px solid var(--color-border); }
:deep(.el-pagination) { --el-pagination-bg-color: transparent; }

@media (max-width: 1100px) {
  .form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .header-meta { display: none; }
}

@media (max-width: 680px) {
  .main-card { padding: 20px; }
  .page-header { align-items: flex-start; }
  .page-title { font-size: 23px; }
  .form-grid { grid-template-columns: 1fr; }
  .form-item-wide { grid-column: span 1; }
  .form-actions { align-items: stretch; flex-direction: column; }
  .form-actions .el-button { width: 100%; }
  .records-header { align-items: flex-start; gap: 12px; }
  .records-count { display: none; }
  .records-footer { justify-content: center; overflow-x: auto; }
}
</style>


