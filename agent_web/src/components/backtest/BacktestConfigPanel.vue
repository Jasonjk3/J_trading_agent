<template>
  <div class="config-panel">
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="config-form"
    >
      <!-- Agent 选择 -->
      <div class="form-section">
        <div class="section-header">
          <h4 class="section-title">选择 Agent</h4>
        </div>
        <el-form-item prop="agentId">
          <el-select
            v-model="form.agentId"
            placeholder="选择要回测的 Agent"
            class="full-width"
            filterable
            @change="handleAgentChange"
          >
            <el-option
              v-for="agent in agentList"
              :key="agent.id"
              :label="agent.name"
              :value="agent.id"
            >
              <div class="agent-option">
                <span class="agent-name">{{ agent.name }}</span>
                <span class="agent-exchange">{{ getExchangeText(agent.exchange) }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <!-- Agent 详情卡片 -->
        <div v-if="selectedAgent" class="agent-card">
          <div class="agent-header">
            <div class="agent-info">
              <el-icon class="agent-icon"><Monitor /></el-icon>
              <div class="agent-text">
                <span class="agent-name">{{ selectedAgent.name }}</span>
                <span class="agent-meta">
                  {{ getExchangeText(selectedAgent.exchange) }} · {{ selectedAgent.strategyConfig?.symbols?.join(', ') || '未配置交易对' }}
                </span>
              </div>
            </div>
            <div 
              class="agent-status"
              :class="selectedAgent.status === 'running' ? 'agent-status--active' : ''"
            >
              <span class="status-dot"></span>
              {{ selectedAgent.status === 'running' ? '运行中' : '已停止' }}
            </div>
          </div>
          
          <div class="agent-details">
            <div class="detail-item">
              <span class="detail-label">交易风格</span>
              <span class="detail-value">{{ getTradingStyleText(selectedAgent.strategyConfig?.tradingStyle) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">交易周期</span>
              <span class="detail-value">短线</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">市场模式</span>
              <span class="detail-value">{{ getMarketModeText(selectedAgent.strategyConfig?.marketMode) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">Agent 决策</span>
              <span class="detail-value">{{ getAgentDecisionModeText(selectedAgent.strategyConfig) }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">策略参数</span>
              <span class="detail-value">{{ getRangeRuleText(selectedAgent.strategyConfig) }}</span>
            </div>
          </div>

          <!-- 数据注入 -->
          <div class="injection-section">
            <span class="injection-label">决策数据注入</span>
            <div class="injection-tags">
              <span class="inject-tag" :class="{ 'inject-tag--active': injectionSummary.newsOn }">
                消息面 {{ injectionSummary.newsOn ? '开' : '关' }}
              </span>
              <span class="inject-tag" :class="{ 'inject-tag--active': injectionSummary.techOn }">
                技术面 {{ injectionSummary.techOn ? '开' : '关' }}
              </span>
            </div>
            <p class="injection-hint">{{ injectionSummary.detail }}</p>
          </div>
        </div>
      </div>

      <!-- 时间与资金 -->
      <div class="form-section">
        <div class="section-header">
          <h4 class="section-title">时间与资金</h4>
        </div>
        
        <el-form-item label="回测名称" prop="name">
          <el-input
            v-model="form.name"
            placeholder="例如：BTC 趋势策略 — 近三月"
            maxlength="50"
            show-word-limit
          />
        </el-form-item>

        <div class="form-row">
          <el-form-item label="回测时间范围" prop="timeRange" class="form-item--large">
            <el-date-picker
              v-model="form.timeRange"
              type="daterange"
              range-separator="—"
              start-placeholder="开始"
              end-placeholder="结束"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              class="full-width"
              :disabled-date="disabledDate"
            />
          </el-form-item>
          <el-form-item label="初始资金" prop="initialCapital" class="form-item--small">
            <div class="input-suffix">
              <el-input-number
                v-model="form.initialCapital"
                :min="100"
                :max="10000000"
                :step="1000"
                :precision="2"
                controls-position="right"
              />
              <span class="suffix-text">USDT</span>
            </div>
          </el-form-item>
        </div>

        <el-form-item label="K 线周期" prop="interval">
          <div class="interval-group">
            <button
              v-for="opt in intervalOptions"
              :key="opt.value"
              type="button"
              class="interval-btn"
              :class="{ 'interval-btn--active': form.interval === opt.value }"
              @click="form.interval = opt.value"
            >
              {{ opt.label }}
            </button>
          </div>
        </el-form-item>
      </div>

      <!-- 决策模式 -->
      <div class="form-section">
        <div class="section-header">
          <h4 class="section-title">决策模式</h4>
          <p class="section-hint">默认继承 Agent 策略，可在回测任务级覆盖</p>
        </div>

        <div class="decision-options">
          <button
            type="button"
            class="decision-card"
            :class="{ 'decision-card--active': form.decisionMode === 'rule' }"
            @click="form.decisionMode = 'rule'"
          >
            <span class="decision-title">规则策略</span>
            <span class="decision-desc">传统指标规则，可复现、无大模型费用</span>
          </button>
          <button
            type="button"
            class="decision-card"
            :class="{ 'decision-card--active': form.decisionMode === 'trader' }"
            @click="form.decisionMode = 'trader'"
          >
            <span class="decision-title">AI 交易员</span>
            <span class="decision-desc">自主维护观点与计划，仅由硬风险内核限制执行</span>
          </button>
        </div>

        <div v-if="form.decisionMode === 'trader'" class="llm-warning">
          <el-icon class="warning-icon"><WarningFilled /></el-icon>
          <span>回测步数多时会多次调用 LLM，耗时与费用显著增加</span>
        </div>
        <div v-if="form.decisionMode === 'trader'" class="llm-cache-config">
          <div class="section-header section-header--compact">
            <h4 class="section-title">LLM 响应处理</h4>
            <p class="section-hint">两种模式都会实时调用模型，不读取历史缓存</p>
          </div>
          <div class="decision-options">
            <button
              type="button"
              class="decision-card"
              :class="{ 'decision-card--active': form.llmCacheMode === 'fresh' }"
              @click="form.llmCacheMode = 'fresh'"
            >
              <span class="decision-title">始终调用模型（默认）</span>
              <span class="decision-desc">不读取、不保存响应，适合验证新 Prompt 或模型配置</span>
            </button>
            <button
              type="button"
              class="decision-card"
              :class="{ 'decision-card--active': form.llmCacheMode === 'record' }"
              @click="form.llmCacheMode = 'record'"
            >
              <span class="decision-title">调用并保存成功响应</span>
              <span class="decision-desc">仍然每次调用模型，仅保存解析成功的响应供审计</span>
            </button>
          </div>
        </div>
        <div v-else class="rule-info">
          <span>将使用 Agent 配置的规则集；若未配置则使用系统默认规则模板。</span>
        </div>
      </div>

      <!-- 高级设置 -->
      <el-collapse class="advanced-section">
        <el-collapse-item name="cost">
          <template #title>
            <div class="collapse-header">
              <span class="collapse-title">交易成本</span>
              <span class="collapse-hint">Maker / Taker / 滑点</span>
            </div>
          </template>
          <div class="cost-grid">
            <el-form-item label="Maker 费率" prop="makerFee">
              <div class="input-suffix">
                <el-input-number
                  v-model="form.makerFee"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="3"
                  controls-position="right"
                />
                <span class="suffix-text">%</span>
              </div>
            </el-form-item>
            <el-form-item label="Taker 费率" prop="takerFee">
              <div class="input-suffix">
                <el-input-number
                  v-model="form.takerFee"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="3"
                  controls-position="right"
                />
                <span class="suffix-text">%</span>
              </div>
            </el-form-item>
            <el-form-item label="滑点" prop="slippage">
              <div class="input-suffix">
                <el-input-number
                  v-model="form.slippage"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  :precision="3"
                  controls-position="right"
                />
                <span class="suffix-text">%</span>
              </div>
            </el-form-item>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { Monitor, WarningFilled } from '@element-plus/icons-vue'
import { agentsApi, type AgentListItem, type ExchangeCode, type TradingStyle, type StrategyConfig } from '@/api/agents'
import type { KlineInterval } from '@/api/backtest'
import { decisionModeLabel, resolveDecisionMode, type DecisionMode } from '@/constants/ruleDecision'

interface BacktestFormData {
  agentId: string
  name: string
  timeRange: [string, string] | null
  interval: KlineInterval
  initialCapital: number
  makerFee: number
  takerFee: number
  slippage: number
  decisionMode: DecisionMode
  llmCacheMode: 'fresh' | 'record'
}

const props = defineProps<{
  modelValue?: Partial<BacktestFormData> | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: BacktestFormData]
}>()

const formRef = ref<FormInstance>()
const agentList = ref<AgentListItem[]>([])
const loading = ref(false)

const intervalOptions = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1h' },
] as const

const defaultForm: BacktestFormData = {
  agentId: '',
  name: '',
  timeRange: null,
  interval: '15m',
  initialCapital: 10000,
  makerFee: 0.1,
  takerFee: 0.1,
  slippage: 0.05,
  decisionMode: 'trader',
  llmCacheMode: 'fresh',
}

const form = reactive<BacktestFormData>({ ...defaultForm })

const selectedAgent = computed(() => agentList.value.find(a => a.id === form.agentId))

const injectionSummary = computed(() => {
  const cfg = selectedAgent.value?.strategyConfig
  if (!selectedAgent.value) {
    return {
      newsOn: false,
      techOn: false,
      detail: '选择 Agent 后显示。消息面/技术面在「交易 Agent → 策略配置」中维护。',
    }
  }
  if (!cfg) {
    return {
      newsOn: false,
      techOn: false,
      detail: '该 Agent 暂无策略配置，请先完善 Agent。',
    }
  }
  const newsOn = !!cfg.useNewsAnalysis
  const techOn = !!cfg.useTechnicalAnalysis
  const bits: string[] = []
  if (newsOn) {
    bits.push(cfg.newsIntelligenceAgentId
      ? `资讯：已绑定采集任务，单次最多 ${cfg.newsContextMaxItems ?? 15} 条`
      : '资讯：已开启但未选采集任务，请回 Agent 补齐')
  }
  if (techOn) {
    bits.push(cfg.technicalAnalysisTimeframe
      ? `技术：仅使用 ${cfg.technicalAnalysisTimeframe} 周期记录`
      : '技术：不按周期过滤，取各交易对最新成功记录')
  }
  if (!newsOn && !techOn) {
    bits.push(form.decisionMode === 'trader'
      ? '未启用库表注入，交易员基于实时盘面自主判断。'
      : '规则模式主要使用 K 线指标。')
  }
  return { newsOn, techOn, detail: bits.join('；') }
})

const rules: FormRules = {
  agentId: [{ required: true, message: '请选择要回测的 Agent', trigger: 'change' }],
  name: [
    { required: true, message: '请输入回测名称', trigger: 'blur' },
    { min: 2, max: 50, message: '名称长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  timeRange: [{ required: true, message: '请选择回测时间范围', trigger: 'change' }],
  interval: [{ required: true, message: '请选择K线周期', trigger: 'change' }],
  initialCapital: [{ required: true, message: '请输入初始资金', trigger: 'blur' }],
}

const disabledDate = (time: Date) => time.getTime() > Date.now()

async function fetchAgents() {
  loading.value = true
  try {
    const res = await agentsApi.getList()
    agentList.value = res.list
  } catch (error) {
    console.error('Failed to fetch agents:', error)
  } finally {
    loading.value = false
  }
}

function handleAgentChange(agentId: string) {
  const agent = agentList.value.find(a => a.id === agentId)
  if (agent && !form.name) form.name = `${agent.name} 回测`
  if (agent?.strategyConfig) {
    form.decisionMode = resolveDecisionMode(agent.strategyConfig)
  }
}

function getAgentDecisionModeText(cfg?: StrategyConfig) {
  return decisionModeLabel(resolveDecisionMode(cfg))
}

function getExchangeText(exchange?: ExchangeCode) {
  const map: Record<ExchangeCode, string> = { binance: 'Binance', okx: 'OKX', bybit: 'Bybit' }
  return exchange ? map[exchange] : '-'
}

function getTradingStyleText(style?: TradingStyle) {
  const map: Record<TradingStyle, string> = { conservative: '保守型', balanced: '平衡型', aggressive: '激进型' }
  return style ? map[style] : '-'
}

function getMarketModeText(mode?: StrategyConfig['marketMode']) {
  const map: Record<NonNullable<StrategyConfig['marketMode']>, string> = { auto: '自动识别', trend_only: '仅趋势', range_only: '仅震荡' }
  return mode ? map[mode] : '自动识别'
}

function getRangeRuleText(cfg?: StrategyConfig) {
  if (!cfg) return '-'
  const styleMap: Record<NonNullable<StrategyConfig['tradingStyle']>, string> = { conservative: '稳健预设', balanced: '均衡预设', aggressive: '积极预设' }
  return `${styleMap[cfg.tradingStyle ?? 'balanced']} · 震荡细节由系统自动设定`
}

watch(() => props.modelValue, (val) => {
  Object.assign(form, val ? { ...defaultForm, ...val } : defaultForm)
}, { immediate: true })

watch(form, (newForm) => {
  emit('update:modelValue', { ...newForm })
}, { deep: true })

onMounted(() => fetchAgents())

async function validate(): Promise<boolean> {
  if (!formRef.value) return false
  return new Promise((resolve) => formRef.value!.validate((valid) => resolve(!!valid)))
}

function getSelectedAgent(): AgentListItem | undefined {
  return selectedAgent.value
}

function getConfig() {
  return { ...form }
}

function reset() {
  Object.assign(form, defaultForm)
  formRef.value?.resetFields()
}

defineExpose({ validate, getConfig, getSelectedAgent, reset })
</script>

<style scoped>
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ========== 表单区块 ========== */
.form-section {
  padding: 20px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.section-header {
  margin-bottom: 16px;
}

.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.section-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
}

.full-width {
  width: 100%;
}

/* ========== Agent 选项 ========== */
.agent-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 4px 0;
}

.agent-option .agent-name {
  font-weight: 500;
  color: var(--color-text-primary);
}

.agent-option .agent-exchange {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* ========== Agent 卡片 ========== */
.agent-card {
  margin-top: 12px;
  padding: 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
}

.agent-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.agent-info {
  display: flex;
  gap: 12px;
}

.agent-icon {
  font-size: 20px;
  color: var(--color-primary);
}

.agent-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-text .agent-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.agent-text .agent-meta {
  font-size: 12px;
  color: var(--color-text-muted);
}

.agent-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  background: var(--color-bg-hover);
  color: var(--color-text-muted);
}

.agent-status--active {
  background: var(--color-profit-bg);
  color: var(--color-profit);
}

.agent-status .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.agent-details {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 12px 0;
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 11px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.detail-value {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

/* ========== 数据注入 ========== */
.injection-section {
  margin-top: 12px;
}

.injection-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 8px;
}

.injection-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.inject-tag {
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: var(--radius-full);
  background: var(--color-bg-hover);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.inject-tag--active {
  background: var(--color-primary-ghost);
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.injection-hint {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

/* ========== 表单行 ========== */
.form-row {
  display: flex;
  gap: 16px;
}

.form-item--large {
  flex: 1.5;
}

.form-item--small {
  flex: 1;
}

.input-suffix {
  display: flex;
  align-items: center;
  gap: 8px;
}

.input-suffix .el-input-number {
  flex: 1;
}

.suffix-text {
  font-size: 13px;
  color: var(--color-text-muted);
  min-width: 36px;
}

/* ========== K线周期 ========== */
.interval-group {
  display: flex;
  gap: 8px;
}

.interval-btn {
  flex: 1;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.interval-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.interval-btn--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #000;
}

/* ========== 决策模式 ========== */
.decision-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.decision-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 16px;
  text-align: left;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.decision-card:hover {
  border-color: var(--color-primary);
}

.decision-card--active {
  background: var(--color-primary-ghost);
  border-color: var(--color-primary);
  box-shadow: inset 0 0 0 1px var(--color-primary);
}

.decision-title {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.decision-desc {
  display: block;
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.4;
}

.rule-info {
  margin-top: 12px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.llm-info {
  padding: 16px;
  background: var(--color-primary-ghost);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
}

.llm-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 12px 16px;
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--color-warning);
}

.llm-cache-config {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.section-header--compact {
  margin-bottom: 10px;
}

.warning-icon {
  font-size: 18px;
}

/* ========== 高级设置 ========== */
.advanced-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--color-bg-elevated);
}

.advanced-section :deep(.el-collapse-item__header) {
  padding: 16px 20px;
  background: transparent;
  border: none;
}

.advanced-section :deep(.el-collapse-item__wrap) {
  border: none;
}

.advanced-section :deep(.el-collapse-item__content) {
  padding: 0 20px 16px;
}

.collapse-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.collapse-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.collapse-hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

.cost-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

/* ========== 响应式 ========== */
@media (max-width: 768px) {
  .form-row {
    flex-direction: column;
  }

  .decision-options,
  .cost-grid {
    grid-template-columns: 1fr;
  }

  .agent-details {
    grid-template-columns: 1fr;
  }
}
</style>
