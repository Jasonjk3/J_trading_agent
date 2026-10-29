<template>
  <div class="backtest-create-page">
    <!-- 页面头部 -->
    <header class="page-header">
      <el-button class="back-btn" text @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        返回
      </el-button>
      <h1 class="page-title">创建回测任务</h1>
    </header>

    <!-- 主内容区 -->
    <div class="create-container">
      <!-- 步骤指示器 -->
      <div class="steps-wrapper">
        <div class="steps-line">
          <div class="steps-progress" :style="{ width: currentStep === 0 ? '0%' : '100%' }"></div>
        </div>
        <div class="step-indicators">
          <div 
            class="step-indicator"
            :class="{ 'is-active': currentStep >= 0, 'is-completed': currentStep > 0 }"
          >
            <div class="step-number">
              <el-icon v-if="currentStep > 0"><Check /></el-icon>
              <span v-else>1</span>
            </div>
            <div class="step-info">
              <span class="step-title">配置参数</span>
              <span class="step-desc">选择 Agent 与时间范围</span>
            </div>
          </div>
          <div 
            class="step-indicator"
            :class="{ 'is-active': currentStep >= 1 }"
          >
            <div class="step-number">2</div>
            <div class="step-info">
              <span class="step-title">确认创建</span>
              <span class="step-desc">核对配置后启动</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 步骤内容 -->
      <div class="step-content">
        <!-- 步骤1: 配置 -->
        <div v-show="currentStep === 0" class="step-panel">
          <BacktestConfigPanel ref="backtestConfigRef" v-model="backtestFormData" />
        </div>

        <!-- 步骤2: 确认 -->
        <div v-show="currentStep === 1" class="step-panel confirm-panel">
          <!-- Agent 信息卡片 -->
          <div class="confirm-section">
            <div class="section-header">
              <div class="section-icon">
                <el-icon><Monitor /></el-icon>
              </div>
              <h3 class="section-title">回测 Agent</h3>
            </div>
            <div v-if="selectedAgent" class="agent-card">
              <div class="agent-header">
                <span class="agent-name">{{ selectedAgent.name }}</span>
                <div 
                  class="agent-status"
                  :class="selectedAgent.status === 'running' ? 'agent-status--active' : 'agent-status--inactive'"
                >
                  <span class="status-dot"></span>
                  {{ selectedAgent.status === 'running' ? '运行中' : '已停止' }}
                </div>
              </div>
              <div class="agent-details">
                <div class="detail-item">
                  <span class="detail-label">交易所</span>
                  <span class="detail-value">{{ getExchangeText(selectedAgent.exchange) }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">交易对</span>
                  <span class="detail-value">{{ selectedAgent.strategyConfig?.symbols?.join(', ') || '-' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">交易风格</span>
                  <span class="detail-value">{{ getTradingStyleText(selectedAgent.strategyConfig?.tradingStyle) }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">市场模式</span>
                  <span class="detail-value">{{ getMarketModeText(selectedAgent.strategyConfig?.marketMode) }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">止盈/止损</span>
                  <span class="detail-value">由 AI 判断</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">交易周期</span>
                  <span class="detail-value">短线（系统统一）</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 回测配置卡片 -->
          <div class="confirm-section">
            <div class="section-header">
              <div class="section-icon">
                <el-icon><Setting /></el-icon>
              </div>
              <h3 class="section-title">回测配置</h3>
            </div>
            <div class="config-grid">
              <div class="config-item">
                <span class="config-label">回测名称</span>
                <span class="config-value">{{ backtestFormData.name }}</span>
              </div>
              <div class="config-item">
                <span class="config-label">时间范围</span>
                <span class="config-value">
                  {{ backtestFormData.timeRange?.[0] }} 至 {{ backtestFormData.timeRange?.[1] }}
                </span>
              </div>
              <div class="config-item config-item--highlight">
                <span class="config-label">初始资金</span>
                <span class="config-value config-value--primary">
                  {{ formatMoney(backtestFormData.initialCapital) }} USDT
                </span>
              </div>
              <div class="config-item">
                <span class="config-label">K线周期</span>
                <span class="config-value">{{ getIntervalText(backtestFormData.interval) }}</span>
              </div>
              <div class="config-item">
                <span class="config-label">手续费</span>
                <span class="config-value">
                  Maker {{ backtestFormData.makerFee }}% / Taker {{ backtestFormData.takerFee }}%
                </span>
              </div>
              <div class="config-item">
                <span class="config-label">滑点</span>
                <span class="config-value">{{ backtestFormData.slippage }}%</span>
              </div>
              <div class="config-item config-item--wide config-item--highlight">
                <span class="config-label">决策模式</span>
                <span class="config-value config-value--primary">
                  {{ decisionModeLabel(backtestFormData.decisionMode) }}
                </span>
              </div>
              <div v-if="backtestFormData.decisionMode === 'trader'" class="config-item config-item--wide">
                <span class="config-label">LLM 响应处理</span>
                <span class="config-value">
                  {{ backtestFormData.llmCacheMode === 'record' ? '调用模型并保存成功响应' : '始终调用模型，不读缓存' }}
                </span>
              </div>
              <div class="config-item config-item--wide">
                <span class="config-label">消息面 / 技术面</span>
                <span class="config-value">{{ confirmInjectionText }}</span>
              </div>
              <div class="config-item config-item--wide">
                <span class="config-label">市场策略</span>
                <span class="config-value">{{ confirmMarketModeText }}</span>
              </div>
            </div>
          </div>

          <!-- 提示信息 -->
          <div class="info-banner">
            <el-icon class="banner-icon"><InfoFilled /></el-icon>
            <div class="banner-content">
              <span class="banner-title">回测说明</span>
              <span class="banner-text">
                回测将使用选中 Agent 的策略配置，基于历史数据模拟交易。结果仅供参考，不代表实际收益。
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作栏 -->
      <div class="action-bar">
        <div class="action-left">
          <el-button v-if="currentStep > 0" @click="prevStep">
            <el-icon><ArrowLeft /></el-icon>
            上一步
          </el-button>
        </div>
        <div class="action-right">
          <el-button v-if="currentStep < 1" type="primary" @click="nextStep">
            下一步
            <el-icon><ArrowRight /></el-icon>
          </el-button>
          <el-button
            v-if="currentStep === 1"
            type="primary"
            :loading="submitting"
            @click="handleSubmit"
          >
            <el-icon><VideoPlay /></el-icon>
            开始回测
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  ArrowLeft, ArrowRight, Setting, Monitor, VideoPlay, 
  Check, InfoFilled 
} from '@element-plus/icons-vue'
import BacktestConfigPanel from '@/components/backtest/BacktestConfigPanel.vue'
import { backtestApi, type KlineInterval } from '@/api/backtest'
import type { AgentListItem, ExchangeCode, TradingStyle, StrategyConfig } from '@/api/agents'
import { decisionModeLabel } from '@/constants/ruleDecision'

const router = useRouter()
const currentStep = ref(0)
const submitting = ref(false)

const backtestConfigRef = ref<InstanceType<typeof BacktestConfigPanel>>()

interface BacktestFormData {
  agentId: string
  name: string
  timeRange: [string, string] | null
  interval: KlineInterval
  initialCapital: number
  makerFee: number
  takerFee: number
  slippage: number
  decisionMode: 'trader' | 'rule'
  llmCacheMode: 'fresh' | 'record'
}

const backtestFormData = reactive<BacktestFormData>({
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
})

const selectedAgent = ref<AgentListItem | null>(null)

const confirmInjectionText = computed(() => {
  const cfg = selectedAgent.value?.strategyConfig
  if (!cfg) return '—'
  const n = cfg.useNewsAnalysis ? `消息面开（≤${cfg.newsContextMaxItems ?? 15} 条）` : '消息面关'
  const t = cfg.useTechnicalAnalysis
    ? `技术面开${cfg.technicalAnalysisTimeframe ? ` · ${cfg.technicalAnalysisTimeframe}` : ''}`
    : '技术面关'
  return `${n}；${t}`
})

const confirmMarketModeText = computed(() => {
  const cfg = selectedAgent.value?.strategyConfig
  if (!cfg) return '—'
  return `${getMarketModeText(cfg.marketMode)}；趋势/震荡的具体阈值、轨道容忍与止盈方式由系统按交易风格自动设定`
})

function goBack() {
  router.push('/backtest')
}

async function nextStep() {
  if (currentStep.value === 0) {
    const valid = await backtestConfigRef.value?.validate()
    if (!valid) {
      ElMessage.warning('请完善回测配置')
      return
    }
    selectedAgent.value = backtestConfigRef.value?.getSelectedAgent() || null
    if (!selectedAgent.value) {
      ElMessage.warning('请选择要回测的 Agent')
      return
    }
  }
  currentStep.value++
}

function prevStep() {
  currentStep.value--
}

async function handleSubmit() {
  if (!selectedAgent.value || !selectedAgent.value.strategyConfig) {
    ElMessage.error('Agent 策略配置无效')
    return
  }
  if (!selectedAgent.value.strategyConfig.symbols?.length) {
    ElMessage.error('请先在 Agent 中配置至少一个交易对')
    return
  }

  submitting.value = true
  try {
    const mode = backtestFormData.decisionMode
    const strategyConfig: StrategyConfig = {
      ...selectedAgent.value.strategyConfig,
      decisionMode: mode,
      llmCacheMode: backtestFormData.llmCacheMode,
    }
    
    const res = await backtestApi.create({
      name: backtestFormData.name,
      config: {
        agentId: selectedAgent.value.id,
        agentName: selectedAgent.value.name,
        strategyConfig: strategyConfig,
        startTime: backtestFormData.timeRange?.[0] || '',
        endTime: backtestFormData.timeRange?.[1] || '',
        initialCapital: backtestFormData.initialCapital,
        exchange: selectedAgent.value.exchange || 'okx',
        symbols: selectedAgent.value.strategyConfig.symbols,
        interval: backtestFormData.interval,
        makerFee: backtestFormData.makerFee,
        takerFee: backtestFormData.takerFee,
        slippage: backtestFormData.slippage,
      }
    })
    ElMessage.success('已创建，正在进入详情页')
    router.push(`/backtest/${res.id}`)
  } catch (error) {
    ElMessage.error('创建失败，请重试')
  } finally {
    submitting.value = false
  }
}

function getExchangeText(exchange?: ExchangeCode) {
  const map: Record<ExchangeCode, string> = {
    binance: 'Binance',
    okx: 'OKX',
    bybit: 'Bybit'
  }
  return exchange ? map[exchange] : '-'
}

function getIntervalText(interval?: KlineInterval) {
  const map: Record<KlineInterval, string> = {
    '1m': '1分钟',
    '5m': '5分钟',
    '15m': '15分钟',
    '1h': '1小时',
    '4h': '4小时',
    '1d': '日线'
  }
  return interval ? map[interval] : '-'
}

function getTradingStyleText(style?: TradingStyle) {
  const map: Record<TradingStyle, string> = {
    conservative: '保守型',
    balanced: '平衡型',
    aggressive: '激进型'
  }
  return style ? map[style] : '-'
}

function getMarketModeText(mode?: StrategyConfig['marketMode']) {
  const map: Record<NonNullable<StrategyConfig['marketMode']>, string> = {
    auto: '自动识别',
    trend_only: '仅趋势',
    range_only: '仅震荡'
  }
  return mode ? map[mode] : '自动识别'
}

function formatMoney(value?: number) {
  return value?.toLocaleString('en-US') || '-'
}
</script>

<style scoped>
.backtest-create-page {
  min-height: 100%;
  padding: 24px;
  background: var(--color-bg-base);
}

/* ========== 页面头部 ========== */
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
}

.back-btn {
  color: var(--color-text-muted);
  padding: 8px 12px;
}

.back-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

/* ========== 主容器 ========== */
.create-container {
  max-width: 900px;
  margin: 0 auto;
}

/* ========== 步骤指示器 ========== */
.steps-wrapper {
  position: relative;
  margin-bottom: 40px;
}

.steps-line {
  position: absolute;
  top: 20px;
  left: 80px;
  right: 80px;
  height: 2px;
  background: var(--color-border);
  border-radius: 1px;
}

.steps-progress {
  height: 100%;
  background: var(--color-primary);
  border-radius: 1px;
  transition: width 0.3s ease;
}

.step-indicators {
  display: flex;
  justify-content: space-between;
  position: relative;
}

.step-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  transition: all var(--transition-normal);
}

.step-indicator.is-active {
  border-color: var(--color-primary);
  background: var(--color-primary-ghost);
}

.step-indicator.is-completed .step-number {
  background: var(--color-primary);
  color: #000;
}

.step-number {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-elevated);
  border: 2px solid var(--color-border);
  border-radius: 50%;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-muted);
  transition: all var(--transition-normal);
}

.step-indicator.is-active .step-number {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.step-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.step-indicator:not(.is-active) .step-title {
  color: var(--color-text-muted);
}

.step-desc {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* ========== 步骤内容 ========== */
.step-content {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 32px;
  margin-bottom: 24px;
  min-height: 400px;
}

.step-panel {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ========== 确认面板 ========== */
.confirm-panel {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.confirm-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
}

.section-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-ghost);
  border-radius: var(--radius-md);
}

.section-icon .el-icon {
  font-size: 20px;
  color: var(--color-primary);
}

.section-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* Agent 卡片 */
.agent-card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.agent-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--color-bg-hover);
  border-bottom: 1px solid var(--color-border);
}

.agent-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.agent-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
}

.agent-status--active {
  background: var(--color-profit-bg);
  color: var(--color-profit);
}

.agent-status--inactive {
  background: var(--color-bg-active);
  color: var(--color-text-muted);
}

.agent-status .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.agent-details {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--color-border);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px 16px;
  background: var(--color-bg-elevated);
}

.detail-label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.detail-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
}

/* 配置网格 */
.config-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.config-item--wide {
  grid-column: span 3;
}

.config-item--highlight {
  border-color: var(--color-primary);
  background: var(--color-primary-ghost);
}

.config-label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.config-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.config-value--primary {
  color: var(--color-primary);
  font-weight: 600;
}

/* 信息横幅 */
.info-banner {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  border-radius: var(--radius-lg);
}

.banner-icon {
  font-size: 20px;
  color: var(--color-info);
  flex-shrink: 0;
  margin-top: 2px;
}

.banner-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.banner-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-info);
}

.banner-text {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

/* ========== 操作栏 ========== */
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.action-left,
.action-right {
  display: flex;
  gap: 12px;
}

/* ========== 响应式 ========== */
@media (max-width: 768px) {
  .backtest-create-page {
    padding: 16px;
  }

  .steps-line {
    display: none;
  }

  .step-indicators {
    flex-direction: column;
    gap: 12px;
  }

  .step-content {
    padding: 20px;
  }

  .agent-details,
  .config-grid {
    grid-template-columns: 1fr;
  }

  .config-item--wide {
    grid-column: span 1;
  }

  .action-bar {
    flex-direction: column-reverse;
    gap: 12px;
  }

  .action-left,
  .action-right {
    width: 100%;
  }

  .action-left .el-button,
  .action-right .el-button {
    flex: 1;
  }
}
</style>
