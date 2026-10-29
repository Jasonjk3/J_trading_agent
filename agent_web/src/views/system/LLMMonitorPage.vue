<template>
  <div class="llm-monitor-page page-content">
    <!-- 总览统计卡片 -->
    <div class="stats-overview">
      <div class="stat-card" v-for="card in overviewCards" :key="card.label">
        <div class="stat-icon" :style="{ '--sc': card.color }">
          <el-icon :size="22"><component :is="card.icon" /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">{{ card.label }}</span>
          <span class="stat-value">{{ card.value }}</span>
          <span class="stat-sub" v-if="card.sub">{{ card.sub }}</span>
        </div>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="page-card">
      <el-tabs v-model="activeTab" class="monitor-tabs">
        <!-- 费用概览 Tab -->
        <el-tab-pane label="费用概览" name="cost">
          <div class="tab-content">
            <!-- 时间筛选 -->
            <div class="toolbar">
              <el-form :model="costFilter" inline class="filter-form">
                <el-form-item label="时间范围">
                  <el-date-picker
                    v-model="costFilter.dateRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    value-format="YYYY-MM-DD"
                    :shortcuts="dateShortcuts"
                    style="width: 280px"
                  />
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="fetchCostData">查询</el-button>
                </el-form-item>
              </el-form>
            </div>

            <!-- 费用趋势图 -->
            <div class="chart-section">
              <h3 class="section-title">费用趋势</h3>
              <div ref="costTrendChartRef" class="chart-wrap"></div>
            </div>

            <!-- 费用分布 -->
            <div class="distribution-row">
              <div class="distribution-card">
                <h3 class="section-title">按模型分布</h3>
                <div ref="modelPieChartRef" class="chart-wrap chart-pie"></div>
                <el-table table-layout="auto" :data="costSummary?.by_model || []" class="data-table" size="small">
                  <el-table-column prop="model_name" label="模型" />
                  <el-table-column prop="cost_cny" label="费用(¥)" align="right">
                    <template #default="{ row }">{{ formatMoney(row.cost_cny) }}</template>
                  </el-table-column>
                  <el-table-column prop="percentage" label="占比" align="right" min-width="96">
                    <template #default="{ row }">{{ row.percentage.toFixed(1) }}%</template>
                  </el-table-column>
                </el-table>
              </div>
              <div class="distribution-card">
                <h3 class="section-title">按 Agent 分布</h3>
                <div ref="agentPieChartRef" class="chart-wrap chart-pie"></div>
                <el-table table-layout="auto" :data="costSummary?.by_agent || []" class="data-table" size="small">
                  <el-table-column prop="agent_name" label="Agent" />
                  <el-table-column prop="cost_cny" label="费用(¥)" align="right">
                    <template #default="{ row }">{{ formatMoney(row.cost_cny) }}</template>
                  </el-table-column>
                  <el-table-column prop="percentage" label="占比" align="right" min-width="96">
                    <template #default="{ row }">{{ row.percentage.toFixed(1) }}%</template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- 模型统计 Tab -->
        <el-tab-pane label="模型统计" name="model">
          <div class="tab-content">
            <el-table table-layout="auto" :data="modelStats" class="data-table" stripe>
              <el-table-column prop="model_name" label="模型名称" min-width="180" />
              <el-table-column prop="model_provider" label="提供商" width="100" />
              <el-table-column prop="total_requests" label="请求数" align="right" width="100" />
              <el-table-column prop="total_tokens" label="Token 数" align="right" width="120">
                <template #default="{ row }">{{ formatNumber(row.total_tokens) }}</template>
              </el-table-column>
              <el-table-column prop="cost_cny" label="费用(¥)" align="right" width="100">
                <template #default="{ row }">{{ formatMoney(row.cost_cny) }}</template>
              </el-table-column>
              <el-table-column prop="avg_response_time_ms" label="平均响应" align="right" width="100">
                <template #default="{ row }">{{ row.avg_response_time_ms }}ms</template>
              </el-table-column>
              <el-table-column prop="success_rate" label="成功率" align="right" width="90">
                <template #default="{ row }">
                  <span :class="successRateClass(row.success_rate)">
                    {{ (row.success_rate * 100).toFixed(1) }}%
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Agent 统计 Tab -->
        <el-tab-pane label="Agent 统计" name="agent">
          <div class="tab-content">
            <el-table table-layout="auto" :data="agentStats" class="data-table" stripe>
              <el-table-column prop="agent_name" label="Agent 名称" min-width="180" />
              <el-table-column prop="primary_model" label="主要模型" width="150" />
              <el-table-column prop="total_requests" label="请求数" align="right" width="100" />
              <el-table-column prop="total_tokens" label="Token 数" align="right" width="120">
                <template #default="{ row }">{{ formatNumber(row.total_tokens) }}</template>
              </el-table-column>
              <el-table-column prop="cost_cny" label="费用(¥)" align="right" width="100">
                <template #default="{ row }">{{ formatMoney(row.cost_cny) }}</template>
              </el-table-column>
              <el-table-column prop="avg_response_time_ms" label="平均响应" align="right" width="100">
                <template #default="{ row }">{{ row.avg_response_time_ms }}ms</template>
              </el-table-column>
              <el-table-column prop="success_rate" label="成功率" align="right" width="90">
                <template #default="{ row }">
                  <span :class="successRateClass(row.success_rate)">
                    {{ (row.success_rate * 100).toFixed(1) }}%
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- 调用记录 Tab -->
        <el-tab-pane label="调用记录" name="history">
          <div class="tab-content">
            <div class="toolbar">
              <el-form :model="historyFilter" inline class="filter-form">
                <el-form-item label="时间范围">
                  <el-date-picker
                    v-model="historyFilter.dateRange"
                    type="datetimerange"
                    range-separator="至"
                    start-placeholder="开始时间"
                    end-placeholder="结束时间"
                    value-format="YYYY-MM-DD HH:mm:ss"
                    style="width: 360px"
                  />
                </el-form-item>
                <el-form-item label="模型">
                  <el-select v-model="historyFilter.model_name" placeholder="全部" clearable style="width: 160px">
                    <el-option v-for="m in activeModels" :key="m" :label="m" :value="m" />
                  </el-select>
                </el-form-item>
                <el-form-item label="状态">
                  <el-select v-model="historyFilter.status" placeholder="全部" clearable style="width: 100px">
                    <el-option label="成功" value="success" />
                    <el-option label="失败" value="failed" />
                    <el-option label="超时" value="timeout" />
                  </el-select>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="fetchUsageHistory">查询</el-button>
                  <el-button @click="resetHistoryFilter">重置</el-button>
                </el-form-item>
              </el-form>
            </div>

            <el-table table-layout="auto" :data="usageHistory" class="data-table" stripe>
              <el-table-column prop="created_at" label="时间" width="170">
                <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column prop="model_name" label="模型" min-width="150" />
              <el-table-column prop="agent_name" label="Agent" width="140">
                <template #default="{ row }">{{ row.agent_name || '-' }}</template>
              </el-table-column>
              <el-table-column prop="total_tokens" label="Tokens" align="right" width="90">
                <template #default="{ row }">{{ formatNumber(row.total_tokens) }}</template>
              </el-table-column>
              <el-table-column prop="cost_cny" label="费用(¥)" align="right" width="80">
                <template #default="{ row }">{{ row.cost_cny.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column prop="response_time_ms" label="响应" align="right" width="80">
                <template #default="{ row }">{{ row.response_time_ms }}ms</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" align="center" width="80">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" size="small">
                    {{ statusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>

            <div class="pagination-wrap">
              <el-pagination
                v-model:current-page="historyPagination.page"
                v-model:page-size="historyPagination.pageSize"
                :total="historyPagination.total"
                :page-sizes="[20, 50, 100]"
                layout="total, sizes, prev, pager, next"
                @size-change="fetchUsageHistory"
                @current-change="fetchUsageHistory"
              />
            </div>
          </div>
        </el-tab-pane>

        <!-- 模型配置 Tab -->
        <el-tab-pane label="模型配置" name="config">
          <div class="tab-content">
            <div class="toolbar">
              <el-button type="primary" @click="showConfigDialog()">
                <el-icon><Plus /></el-icon>新增配置
              </el-button>
            </div>

            <el-table table-layout="auto" :data="modelConfigs" class="data-table" stripe>
              <el-table-column prop="model_name" label="模型名称" min-width="180" />
              <el-table-column prop="provider" label="提供商" width="100" />
              <el-table-column prop="input_price_per_1m" label="输入价格($/M)" align="right" width="120">
                <template #default="{ row }">{{ row.input_price_per_1m.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="output_price_per_1m" label="输出价格($/M)" align="right" width="120">
                <template #default="{ row }">{{ row.output_price_per_1m.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="exchange_rate" label="汇率" align="right" width="80">
                <template #default="{ row }">{{ row.exchange_rate.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="is_active" label="状态" align="center" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                    {{ row.is_active ? '生效' : '停用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="140" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="showConfigDialog(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="handleDeleteConfig(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- 预警规则 Tab -->
        <el-tab-pane label="预警规则" name="alert">
          <div class="tab-content">
            <div class="toolbar">
              <el-button type="primary" @click="showAlertDialog()">
                <el-icon><Plus /></el-icon>新增规则
              </el-button>
            </div>

            <el-table table-layout="auto" :data="alertRules" class="data-table" stripe>
              <el-table-column prop="rule_name" label="规则名称" min-width="150" />
              <el-table-column prop="alert_type" label="预警类型" width="120">
                <template #default="{ row }">{{ alertTypeLabel(row.alert_type) }}</template>
              </el-table-column>
              <el-table-column prop="threshold_value" label="阈值(¥)" align="right" width="100">
                <template #default="{ row }">{{ formatMoney(row.threshold_value) }}</template>
              </el-table-column>
              <el-table-column prop="model_name" label="模型" width="120">
                <template #default="{ row }">{{ row.model_name || '全部' }}</template>
              </el-table-column>
              <el-table-column prop="cooldown_minutes" label="冷却时间" align="right" width="100">
                <template #default="{ row }">{{ row.cooldown_minutes }}分钟</template>
              </el-table-column>
              <el-table-column prop="is_active" label="状态" align="center" width="80">
                <template #default="{ row }">
                  <el-switch v-model="row.is_active" @change="handleToggleAlert(row)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="140" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="showAlertDialog(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="handleDeleteAlert(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 模型配置对话框 -->
    <el-dialog
      v-model="configDialogVisible"
      :title="configForm.id ? '编辑模型配置' : '新增模型配置'"
      width="500px"
    >
      <el-form :model="configForm" :rules="configRules" ref="configFormRef" label-width="120px">
        <el-form-item label="模型名称" prop="model_name">
          <el-input v-model="configForm.model_name" :disabled="!!configForm.id" placeholder="如 gpt-4o" />
        </el-form-item>
        <el-form-item label="提供商" prop="provider">
          <el-input v-model="configForm.provider" :disabled="!!configForm.id" placeholder="如 openai" />
        </el-form-item>
        <el-form-item label="输入价格($/M)" prop="input_price_per_1m">
          <el-input-number v-model="configForm.input_price_per_1m" :precision="4" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="输出价格($/M)" prop="output_price_per_1m">
          <el-input-number v-model="configForm.output_price_per_1m" :precision="4" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="汇率" prop="exchange_rate">
          <el-input-number v-model="configForm.exchange_rate" :precision="2" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="生效日期" prop="effective_date" v-if="!configForm.id">
          <el-date-picker v-model="configForm.effective_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="configForm.is_active" active-text="生效" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 预警规则对话框 -->
    <el-dialog
      v-model="alertDialogVisible"
      :title="alertForm.id ? '编辑预警规则' : '新增预警规则'"
      width="500px"
    >
      <el-form :model="alertForm" :rules="alertFormRules" ref="alertFormRef" label-width="100px">
        <el-form-item label="规则名称" prop="rule_name">
          <el-input v-model="alertForm.rule_name" placeholder="如 日费用预警" />
        </el-form-item>
        <el-form-item label="预警类型" prop="alert_type">
          <el-select v-model="alertForm.alert_type" style="width: 100%">
            <el-option label="日费用预警" value="daily_cost" />
            <el-option label="月费用预警" value="monthly_cost" />
            <el-option label="单次请求预警" value="single_request" />
          </el-select>
        </el-form-item>
        <el-form-item label="阈值(¥)" prop="threshold_value">
          <el-input-number v-model="alertForm.threshold_value" :precision="2" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="冷却时间" prop="cooldown_minutes">
          <el-input-number v-model="alertForm.cooldown_minutes" :min="1" style="width: 100%">
            <template #append>分钟</template>
          </el-input-number>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="alertForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="alertDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveAlert">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, markRaw, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Money, TrendCharts, Timer, Coin, Plus } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { chartTheme } from '@/styles/chartTheme'
import { llmMonitorApi } from '@/api/llmMonitor'
import type {
  OverviewStatsResponse,
  CostSummaryResponse,
  CostTrendItem,
  ModelStatsItem,
  AgentStatsItem,
  UsageLogItem,
  ModelCostConfigItem,
  AlertRuleItem,
} from '@/api/llmMonitor'

// ============================================================================
// 状态定义
// ============================================================================

const activeTab = ref('cost')
const loading = ref(false)

// 总览数据
const overviewStats = ref<OverviewStatsResponse | null>(null)
const realtimeData = ref<{ today: any; active_models: string[] } | null>(null)

// 费用数据
const costFilter = ref<{ dateRange: [string, string] | null }>({ dateRange: null })
const costSummary = ref<CostSummaryResponse | null>(null)
const costTrend = ref<CostTrendItem[]>([])

// 模型/Agent 统计
const modelStats = ref<ModelStatsItem[]>([])
const agentStats = ref<AgentStatsItem[]>([])

// 调用记录
const historyFilter = ref({
  dateRange: null as [string, string] | null,
  model_name: '',
  status: '',
})
const usageHistory = ref<UsageLogItem[]>([])
const historyPagination = ref({ page: 1, pageSize: 20, total: 0 })
const activeModels = ref<string[]>([])

// 模型配置
const modelConfigs = ref<ModelCostConfigItem[]>([])
const configDialogVisible = ref(false)
const configFormRef = ref<FormInstance>()
const configForm = ref({
  id: null as number | null,
  model_name: '',
  provider: '',
  input_price_per_1m: 0,
  output_price_per_1m: 0,
  exchange_rate: 7.25,
  effective_date: '',
  is_active: true,
})
const configRules: FormRules = {
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  provider: [{ required: true, message: '请输入提供商', trigger: 'blur' }],
  input_price_per_1m: [{ required: true, message: '请输入输入价格', trigger: 'blur' }],
  output_price_per_1m: [{ required: true, message: '请输入输出价格', trigger: 'blur' }],
  effective_date: [{ required: true, message: '请选择生效日期', trigger: 'change' }],
}

// 预警规则
const alertRules = ref<AlertRuleItem[]>([])
const alertDialogVisible = ref(false)
const alertFormRef = ref<FormInstance>()
const alertForm = ref({
  id: null as number | null,
  rule_name: '',
  alert_type: 'daily_cost',
  threshold_value: 100,
  cooldown_minutes: 60,
  is_active: true,
  notify_channels: {} as Record<string, any>,
})
const alertFormRules: FormRules = {
  rule_name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }],
  alert_type: [{ required: true, message: '请选择预警类型', trigger: 'change' }],
  threshold_value: [{ required: true, message: '请输入阈值', trigger: 'blur' }],
}

// 图表
const costTrendChartRef = ref<HTMLElement | null>(null)
const modelPieChartRef = ref<HTMLElement | null>(null)
const agentPieChartRef = ref<HTMLElement | null>(null)
let costTrendChart: ECharts | null = null
let modelPieChart: ECharts | null = null
let agentPieChart: ECharts | null = null

// ============================================================================
// 计算属性
// ============================================================================

const overviewCards = computed(() => [
  {
    label: '今日费用',
    icon: markRaw(Money),
    color: '#38BDF8',
    value: `¥${formatMoney(costSummary.value?.today?.cost_cny ?? 0)}`,
    sub: `${formatNumber(costSummary.value?.today?.tokens ?? 0)} tokens`,
  },
  {
    label: '本周费用',
    icon: markRaw(TrendCharts),
    color: '#22C55E',
    value: `¥${formatMoney(costSummary.value?.this_week?.cost_cny ?? 0)}`,
    sub: `${formatNumber(costSummary.value?.this_week?.tokens ?? 0)} tokens`,
  },
  {
    label: '本月费用',
    icon: markRaw(Coin),
    color: '#F59E0B',
    value: `¥${formatMoney(costSummary.value?.this_month?.cost_cny ?? 0)}`,
    sub: `${formatNumber(costSummary.value?.this_month?.tokens ?? 0)} tokens`,
  },
  {
    label: '平均响应',
    icon: markRaw(Timer),
    color: '#8B5CF6',
    value: `${overviewStats.value?.avg_response_time_ms ?? 0}ms`,
    sub: `成功率 ${((overviewStats.value?.success_rate ?? 0) * 100).toFixed(1)}%`,
  },
])

// ============================================================================
// 日期快捷选项
// ============================================================================

const dateShortcuts = [
  {
    text: '近 7 天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 7)
      return [start, end]
    },
  },
  {
    text: '近 30 天',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(start.getDate() - 30)
      return [start, end]
    },
  },
  {
    text: '本月',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(1)
      return [start, end]
    },
  },
]

// ============================================================================
// 工具函数
// ============================================================================

function formatMoney(val: number | string): string {
  const n = typeof val === 'string' ? parseFloat(val) : val
  if (Number.isNaN(n)) return '0.00'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatNumber(val: number): string {
  if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`
  if (val >= 1000) return `${(val / 1000).toFixed(1)}K`
  return val.toString()
}

function formatDateTime(isoStr: string): string {
  try {
    const date = new Date(isoStr)
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return isoStr
  }
}

function successRateClass(rate: number): string {
  if (rate >= 0.95) return 'text-success'
  if (rate >= 0.8) return 'text-warning'
  return 'text-danger'
}

function statusTagType(status: string): 'success' | 'danger' | 'warning' | 'info' {
  const map: Record<string, 'success' | 'danger' | 'warning' | 'info'> = {
    success: 'success',
    failed: 'danger',
    timeout: 'warning',
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = { success: '成功', failed: '失败', timeout: '超时' }
  return map[status] || status
}

function alertTypeLabel(type: string): string {
  const map: Record<string, string> = {
    daily_cost: '日费用',
    monthly_cost: '月费用',
    single_request: '单次请求',
  }
  return map[type] || type
}

function getDateRange(): { start_date: string; end_date: string } {
  if (costFilter.value.dateRange && costFilter.value.dateRange.length === 2) {
    return { start_date: costFilter.value.dateRange[0], end_date: costFilter.value.dateRange[1] }
  }
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 30)
  return {
    start_date: start.toISOString().slice(0, 10),
    end_date: end.toISOString().slice(0, 10),
  }
}

// ============================================================================
// 数据获取
// ============================================================================

async function fetchOverviewData() {
  try {
    const [overview, realtime, summary] = await Promise.all([
      llmMonitorApi.getOverviewStats(),
      llmMonitorApi.getRealtimeUsage(),
      llmMonitorApi.getCostSummary(),
    ])
    overviewStats.value = overview
    realtimeData.value = realtime
    activeModels.value = realtime.active_models || []
    costSummary.value = summary
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取总览数据失败')
  }
}

async function fetchCostData() {
  loading.value = true
  const { start_date, end_date } = getDateRange()
  try {
    const [summary, trend] = await Promise.all([
      llmMonitorApi.getCostSummary({ start_date, end_date }),
      llmMonitorApi.getCostTrend({ start_date, end_date, granularity: 'day' }),
    ])
    costSummary.value = summary
    costTrend.value = trend.items || []
    await nextTick()
    renderCostTrendChart()
    renderModelPieChart()
    renderAgentPieChart()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取费用数据失败')
  } finally {
    loading.value = false
  }
}

async function fetchModelStats() {
  try {
    const res = await llmMonitorApi.getStatsByModel()
    modelStats.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取模型统计失败')
  }
}

async function fetchAgentStats() {
  try {
    const res = await llmMonitorApi.getStatsByAgent()
    agentStats.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取 Agent 统计失败')
  }
}

async function fetchUsageHistory() {
  try {
    const params: Record<string, any> = {
      page: historyPagination.value.page,
      page_size: historyPagination.value.pageSize,
    }
    if (historyFilter.value.dateRange && historyFilter.value.dateRange.length === 2) {
      params.start_time = historyFilter.value.dateRange[0]
      params.end_time = historyFilter.value.dateRange[1]
    }
    if (historyFilter.value.model_name) params.model_name = historyFilter.value.model_name
    if (historyFilter.value.status) params.status = historyFilter.value.status

    const res = await llmMonitorApi.getUsageHistory(params)
    usageHistory.value = res.items || []
    historyPagination.value.total = res.pagination.total
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取调用记录失败')
  }
}

function resetHistoryFilter() {
  historyFilter.value = { dateRange: null, model_name: '', status: '' }
  historyPagination.value.page = 1
  fetchUsageHistory()
}

async function fetchModelConfigs() {
  try {
    const res = await llmMonitorApi.getModelConfigs()
    modelConfigs.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取模型配置失败')
  }
}

async function fetchAlertRules() {
  try {
    const res = await llmMonitorApi.getAlertRules()
    alertRules.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取预警规则失败')
  }
}

// ============================================================================
// 图表渲染
// ============================================================================

const chartText = '#64748B'
const chartGrid = 'rgba(148,163,184,0.08)'

function renderCostTrendChart() {
  if (!costTrendChartRef.value || !costTrend.value.length) return
  if (costTrendChart) costTrendChart.dispose()
  costTrendChart = echarts.init(costTrendChartRef.value, chartTheme)

  const dates = costTrend.value.map((p) => p.period)
  const costs = costTrend.value.map((p) => p.cost_cny)
  const tokens = costTrend.value.map((p) => p.tokens)

  costTrendChart.setOption({
    grid: { left: 60, right: 60, top: 40, bottom: 36 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(17,24,39,0.95)',
      borderColor: 'rgba(148,163,184,0.15)',
      textStyle: { color: '#F1F5F9', fontSize: 12 },
    },
    legend: { data: ['费用(¥)', 'Tokens'], textStyle: { color: chartText } },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { color: chartText, fontSize: 11 },
      axisLine: { lineStyle: { color: chartGrid } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: '费用(¥)',
        nameTextStyle: { color: chartText },
        axisLabel: { color: chartText, fontSize: 11 },
        splitLine: { lineStyle: { color: chartGrid } },
      },
      {
        type: 'value',
        name: 'Tokens',
        nameTextStyle: { color: chartText },
        axisLabel: { color: chartText, fontSize: 11 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '费用(¥)',
        type: 'bar',
        data: costs,
        barWidth: '40%',
        itemStyle: {
          color: '#2563EB',
          borderRadius: [4, 4, 0, 0],
        },
      },
      {
        name: 'Tokens',
        type: 'line',
        yAxisIndex: 1,
        data: tokens,
        smooth: true,
        showSymbol: false,
        lineStyle: {
          width: 2,
          color: '#16A34A',
        },
      },
    ],
  })
}

function renderModelPieChart() {
  if (!modelPieChartRef.value || !costSummary.value?.by_model?.length) return
  if (modelPieChart) modelPieChart.dispose()
  modelPieChart = echarts.init(modelPieChartRef.value, chartTheme)

  const data = costSummary.value.by_model.map((item) => ({
    name: item.model_name,
    value: item.cost_cny,
  }))

  modelPieChart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(17,24,39,0.95)',
      borderColor: 'rgba(148,163,184,0.15)',
      textStyle: { color: '#F1F5F9', fontSize: 12 },
      formatter: '{b}: ¥{c} ({d}%)',
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '50%'],
        data,
        label: { show: false },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' },
        },
      },
    ],
  })
}

function renderAgentPieChart() {
  if (!agentPieChartRef.value || !costSummary.value?.by_agent?.length) return
  if (agentPieChart) agentPieChart.dispose()
  agentPieChart = echarts.init(agentPieChartRef.value, chartTheme)

  const data = costSummary.value.by_agent.map((item) => ({
    name: item.agent_name,
    value: item.cost_cny,
  }))

  agentPieChart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(17,24,39,0.95)',
      borderColor: 'rgba(148,163,184,0.15)',
      textStyle: { color: '#F1F5F9', fontSize: 12 },
      formatter: '{b}: ¥{c} ({d}%)',
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '50%'],
        data,
        label: { show: false },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' },
        },
      },
    ],
  })
}

// ============================================================================
// 模型配置操作
// ============================================================================

function showConfigDialog(item?: ModelCostConfigItem) {
  if (item) {
    configForm.value = {
      id: item.id,
      model_name: item.model_name,
      provider: item.provider,
      input_price_per_1m: item.input_price_per_1m,
      output_price_per_1m: item.output_price_per_1m,
      exchange_rate: item.exchange_rate,
      effective_date: item.effective_date,
      is_active: item.is_active,
    }
  } else {
    configForm.value = {
      id: null,
      model_name: '',
      provider: '',
      input_price_per_1m: 0,
      output_price_per_1m: 0,
      exchange_rate: 7.25,
      effective_date: new Date().toISOString().slice(0, 10),
      is_active: true,
    }
  }
  configDialogVisible.value = true
}

async function handleSaveConfig() {
  const valid = await configFormRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    if (configForm.value.id) {
      await llmMonitorApi.updateModelConfig(configForm.value.id, {
        input_price_per_1m: configForm.value.input_price_per_1m,
        output_price_per_1m: configForm.value.output_price_per_1m,
        exchange_rate: configForm.value.exchange_rate,
        is_active: configForm.value.is_active,
      })
      ElMessage.success('更新成功')
    } else {
      await llmMonitorApi.createModelConfig({
        model_name: configForm.value.model_name,
        provider: configForm.value.provider,
        input_price_per_1m: configForm.value.input_price_per_1m,
        output_price_per_1m: configForm.value.output_price_per_1m,
        exchange_rate: configForm.value.exchange_rate,
        effective_date: configForm.value.effective_date,
        is_active: configForm.value.is_active,
      })
      ElMessage.success('创建成功')
    }
    configDialogVisible.value = false
    fetchModelConfigs()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  }
}

async function handleDeleteConfig(item: ModelCostConfigItem) {
  try {
    await ElMessageBox.confirm(`确定删除配置「${item.model_name}」吗？`, '删除确认', {
      type: 'warning',
    })
    await llmMonitorApi.deleteModelConfig(item.id)
    ElMessage.success('删除成功')
    fetchModelConfigs()
  } catch {
    // cancelled
  }
}

// ============================================================================
// 预警规则操作
// ============================================================================

function showAlertDialog(item?: AlertRuleItem) {
  if (item) {
    alertForm.value = {
      id: item.id,
      rule_name: item.rule_name,
      alert_type: item.alert_type,
      threshold_value: item.threshold_value,
      cooldown_minutes: item.cooldown_minutes,
      is_active: item.is_active,
      notify_channels: item.notify_channels,
    }
  } else {
    alertForm.value = {
      id: null,
      rule_name: '',
      alert_type: 'daily_cost',
      threshold_value: 100,
      cooldown_minutes: 60,
      is_active: true,
      notify_channels: {},
    }
  }
  alertDialogVisible.value = true
}

async function handleSaveAlert() {
  const valid = await alertFormRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    if (alertForm.value.id) {
      await llmMonitorApi.updateAlertRule(alertForm.value.id, {
        rule_name: alertForm.value.rule_name,
        threshold_value: alertForm.value.threshold_value,
        cooldown_minutes: alertForm.value.cooldown_minutes,
        is_active: alertForm.value.is_active,
        notify_channels: alertForm.value.notify_channels,
      })
      ElMessage.success('更新成功')
    } else {
      await llmMonitorApi.createAlertRule({
        rule_name: alertForm.value.rule_name,
        alert_type: alertForm.value.alert_type as 'daily_cost' | 'monthly_cost' | 'single_request',
        threshold_value: alertForm.value.threshold_value,
        cooldown_minutes: alertForm.value.cooldown_minutes,
        is_active: alertForm.value.is_active,
        notify_channels: alertForm.value.notify_channels,
      })
      ElMessage.success('创建成功')
    }
    alertDialogVisible.value = false
    fetchAlertRules()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  }
}

async function handleToggleAlert(item: AlertRuleItem) {
  try {
    await llmMonitorApi.updateAlertRule(item.id, { is_active: item.is_active })
    ElMessage.success(item.is_active ? '已启用' : '已停用')
  } catch (e: any) {
    item.is_active = !item.is_active
    ElMessage.error(e?.message ?? '操作失败')
  }
}

async function handleDeleteAlert(item: AlertRuleItem) {
  try {
    await ElMessageBox.confirm(`确定删除规则「${item.rule_name}」吗？`, '删除确认', {
      type: 'warning',
    })
    await llmMonitorApi.deleteAlertRule(item.id)
    ElMessage.success('删除成功')
    fetchAlertRules()
  } catch {
    // cancelled
  }
}

// ============================================================================
// Tab 切换加载
// ============================================================================

watch(activeTab, (tab) => {
  if (tab === 'cost') {
    fetchCostData()
  } else if (tab === 'model') {
    fetchModelStats()
  } else if (tab === 'agent') {
    fetchAgentStats()
  } else if (tab === 'history') {
    fetchUsageHistory()
  } else if (tab === 'config') {
    fetchModelConfigs()
  } else if (tab === 'alert') {
    fetchAlertRules()
  }
})

// ============================================================================
// 初始化
// ============================================================================

onMounted(async () => {
  await fetchOverviewData()
  fetchCostData()
})
</script>

<style scoped>
.llm-monitor-page {
  max-width: 1400px;
}

.page-card {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}

/* 总览统计卡片 */
.stats-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.stat-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: 14px;
  transition: all var(--transition-normal);
}

.stat-card:hover {
  border-color: var(--color-border-active);
  transform: translateY(-2px);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--sc) 15%, transparent);
  color: var(--sc);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.stat-label {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.stat-sub {
  font-size: var(--font-size-caption);
  color: var(--color-text-secondary);
}

/* Tab 样式 */
.monitor-tabs :deep(.el-tabs__header) {
  margin-bottom: var(--spacing-md);
}

.tab-content {
  min-height: 400px;
}

/* 工具栏 */
.toolbar {
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 0;
}

/* 图表 */
.chart-section {
  margin-bottom: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-card-title);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 16px;
}

.chart-wrap {
  height: 300px;
  width: 100%;
}

.chart-pie {
  height: 200px;
}

/* 分布行 */
.distribution-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-lg);
}

.distribution-card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
}

/* 表格 */
.data-table {
  width: 100%;
}

/* 分页 */
.pagination-wrap {
  margin-top: var(--spacing-md);
  display: flex;
  justify-content: flex-end;
}

/* 状态文字 */
.text-success {
  color: #22c55e;
}

.text-warning {
  color: #f59e0b;
}

.text-danger {
  color: #ef4444;
}

/* 响应式 */
@media (max-width: 1200px) {
  .stats-overview {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .stats-overview {
    grid-template-columns: 1fr;
  }

  .distribution-row {
    grid-template-columns: 1fr;
  }
}
</style>
