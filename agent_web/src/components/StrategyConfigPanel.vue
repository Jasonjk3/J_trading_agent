<template>
  <div class="strategy-config-panel">
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="config-form"
    >
      <div class="config-section">
        <h4 class="section-title">核心配置</h4>

        <el-row :gutter="24">
          <el-col :xs="24" :md="12">
            <el-form-item label="交易对" prop="symbols">
              <el-select
                v-model="form.symbols"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="请至少选择一个交易对（如 BTCUSDT）"
                style="width: 100%"
              >
                <el-option
                  v-for="symbol in commonSymbols"
                  :key="symbol"
                  :label="symbol"
                  :value="symbol"
                />
              </el-select>
              <div class="field-hint">系统会基于你的选择推导完整风控与交易参数；止盈/止损由策略引擎执行</div>
            </el-form-item>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-form-item label="交易风格" prop="tradingStyle">
              <el-radio-group v-model="form.tradingStyle" class="style-radio-group">
                <el-radio-button value="conservative">
                  <div class="style-option">
                    <span class="style-name">稳定</span>
                    <span class="style-desc">低风险，仅允许 1x</span>
                  </div>
                </el-radio-button>
                <el-radio-button value="balanced">
                  <div class="style-option">
                    <span class="style-name">均衡</span>
                    <span class="style-desc">杠杆可用可不用</span>
                  </div>
                </el-radio-button>
                <el-radio-button value="aggressive">
                  <div class="style-option">
                    <span class="style-name">激进</span>
                    <span class="style-desc">每笔至少使用 2x</span>
                  </div>
                </el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="24">
          <el-col :xs="24" :md="12">
            <el-form-item label="初始本金" prop="initialCapital">
              <div class="input-with-unit">
                <el-input-number
                  v-model="form.initialCapital"
                  :min="10"
                  :max="100000000"
                  :precision="2"
                  :step="100"
                  :controls="true"
                  controls-position="right"
                />
                <span class="input-unit">USDT</span>
              </div>
            </el-form-item>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-form-item label="交易周期">
              <div class="fixed-mode-card">
                <div class="fixed-mode-card__title">短线</div>
                <div class="fixed-mode-card__desc">当前策略统一按短线执行，重点捕捉日内到 1 天内的趋势延续与震荡回归机会。</div>
              </div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="24">
          <el-col :xs="24" :md="12">
            <el-form-item label="目标利润" prop="targetProfit.value">
              <div class="target-profit-row">
                <el-radio-group v-model="form.targetProfit.type" class="target-profit-type">
                  <el-radio-button value="percentage">本金百分比</el-radio-button>
                  <el-radio-button value="fixed">固定金额</el-radio-button>
                </el-radio-group>

                <div class="input-with-unit">
                  <el-input-number
                    v-model="form.targetProfit.value"
                    :min="0"
                    :max="100000000"
                    :precision="2"
                    :step="1"
                    :controls="true"
                    controls-position="right"
                  />
                  <span class="input-unit">{{ form.targetProfit.type === 'percentage' ? '%' : 'USDT' }}</span>
                </div>
              </div>
            </el-form-item>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-form-item label="最小单次交易金额" prop="minOrderAmount">
              <div class="input-with-unit">
                <el-input-number
                  v-model="form.minOrderAmount"
                  :min="1"
                  :max="form.maxOrderAmount || 100000000"
                  :precision="2"
                  :step="10"
                  :controls="true"
                  controls-position="right"
                />
                <span class="input-unit">USDT</span>
              </div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="24">
          <el-col :xs="24" :md="12">
            <el-form-item label="单笔最大保证金" prop="maxOrderAmount">
              <div class="input-with-unit">
                <el-input-number
                  v-model="form.maxOrderAmount"
                  :min="form.minOrderAmount || 1"
                  :max="100000000"
                  :precision="2"
                  :step="100"
                  :controls="true"
                  controls-position="right"
                />
                <span class="input-unit">USDT</span>
              </div>
              <div class="field-hint">限制单笔占用保证金；订单名义价值可按最终批准杠杆放大。</div>
            </el-form-item>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-form-item label="最大保证金占用" prop="maxPositionRatio">
              <div class="input-with-unit">
                <el-input-number
                  v-model="form.maxPositionRatio"
                  :min="1"
                  :max="100"
                  :precision="1"
                  :step="5"
                  :controls="true"
                  controls-position="right"
                />
                <span class="input-unit">%</span>
              </div>
              <div class="field-hint">全部持仓保证金合计不得超过账户权益的该比例；独立于交易风格设置。</div>
            </el-form-item>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-form-item label="默认减仓比例" prop="reducePositionRatio">
              <div class="input-with-unit">
                <el-input-number
                  v-model="form.reducePositionRatio"
                  :min="1"
                  :max="100"
                  :precision="1"
                  :step="5"
                  :controls="true"
                  controls-position="right"
                />
                <span class="input-unit">%</span>
              </div>
              <div class="field-hint">触发减仓时，系统按当前持仓数量的该比例执行；模型不能自拟数量。</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="24">
          <el-col :xs="24" :md="12">
            <el-form-item label="最大杠杆倍数" prop="maxLeverage">
              <el-select
                v-model="form.maxLeverage"
                placeholder="选择最大杠杆"
                style="width: 100%"
                :disabled="form.tradingStyle === 'conservative'"
              >
                <el-option :value="1" label="1x（无杠杆）" :disabled="form.tradingStyle === 'aggressive'" />
                <el-option :value="2" label="2x" />
                <el-option :value="3" label="3x" />
                <el-option :value="5" label="5x" />
                <el-option :value="10" label="10x" />
                <el-option :value="20" label="20x" />
                <el-option :value="50" label="50x" />
                <el-option :value="100" label="100x" />
                <el-option :value="125" label="125x" />
              </el-select>
              <div class="field-hint">{{ leveragePolicyHint }}</div>
            </el-form-item>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-form-item label="持仓方向" prop="positionDirection">
              <el-radio-group v-model="form.positionDirection" class="style-radio-group">
                <el-radio-button value="both">
                  <div class="style-option">
                    <span class="style-name">均可</span>
                    <span class="style-desc">做多、做空均可</span>
                  </div>
                </el-radio-button>
                <el-radio-button value="long_only">
                  <div class="style-option">
                    <span class="style-name">仅做多</span>
                    <span class="style-desc">只开多单</span>
                  </div>
                </el-radio-button>
                <el-radio-button value="short_only">
                  <div class="style-option">
                    <span class="style-name">仅做空</span>
                    <span class="style-desc">只开空单</span>
                  </div>
                </el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
      </div>

      <div class="config-section">
        <h4 class="section-title">市场策略</h4>

        <el-row :gutter="24">
          <el-col :xs="24" :md="24">
            <el-form-item label="市场模式" prop="marketMode">
              <el-radio-group v-model="form.marketMode" class="style-radio-group">
                <el-radio-button value="auto">
                  <div class="style-option">
                    <span class="style-name">自动识别</span>
                    <span class="style-desc">在趋势与震荡之间切换</span>
                  </div>
                </el-radio-button>
                <el-radio-button value="trend_only">
                  <div class="style-option">
                    <span class="style-name">仅趋势</span>
                    <span class="style-desc">只做顺势跟随</span>
                  </div>
                </el-radio-button>
                <el-radio-button value="range_only">
                  <div class="style-option">
                    <span class="style-name">仅震荡</span>
                    <span class="style-desc">只做区间回归</span>
                  </div>
                </el-radio-button>
              </el-radio-group>
              <div class="field-hint">`auto` 会先判断更像趋势市还是震荡市，再选择对应策略；具体震荡阈值、轨道容忍和止盈方式由系统按交易风格自动设定。</div>
            </el-form-item>
          </el-col>
        </el-row>
      </div>

      <div class="config-section decision-mode-section">
        <h4 class="section-title">决策模式</h4>
        <p class="section-kicker">选择 Agent 如何生成交易决策；规则模式可复现、无大模型费用。</p>

        <el-form-item label="模式" prop="decisionMode">
          <div class="decision-options">
            <button
              type="button"
              class="decision-card"
              :class="{ 'decision-card--active': form.decisionMode === 'trader' }"
              @click="form.decisionMode = 'trader'"
            >
              <span class="decision-card__title">AI 交易员</span>
              <span class="decision-card__desc">自主形成观点和交易计划，仅受账户硬风控约束</span>
            </button>
            <button
              type="button"
              class="decision-card"
              :class="{ 'decision-card--active': form.decisionMode === 'rule' }"
              @click="form.decisionMode = 'rule'"
            >
              <span class="decision-card__title">规则策略</span>
              <span class="decision-card__desc">传统指标规则组合，回测可复现、无 API 费用</span>
            </button>
          </div>
        </el-form-item>

        <template v-if="form.decisionMode === 'trader'">
          <el-form-item label="订单执行">
            <el-radio-group v-model="traderExecutionMode">
              <el-radio-button value="shadow">影子观察</el-radio-button>
              <el-radio-button value="live">允许实盘</el-radio-button>
            </el-radio-group>
            <p class="field-hint">
              影子观察只保存观点、计划和订单意图；允许实盘后仍必须通过 RiskKernel。
            </p>
          </el-form-item>
          <el-row :gutter="20">
            <el-col :xs="24" :md="14">
              <el-form-item label="决策 LLM" prop="decisionLlmModelId">
                <el-select
                  v-model="form.decisionLlmModelId"
                  placeholder="请选择决策用大模型"
                  class="decision-llm-select"
                  clearable
                  filterable
                  :loading="loadingLlmModels"
                >
                  <template v-if="llmModels.length === 0 && !loadingLlmModels" #empty>
                    <div class="empty-tip">
                      <span>暂无可用模型</span>
                      <button type="button" class="config-link" @click="emit('navigate', '/model-management')">
                        去配置
                      </button>
                    </div>
                  </template>
                  <el-option
                    v-for="model in llmModels"
                    :key="model.id"
                    :label="`${model.name} (${model.provider})`"
                    :value="model.id"
                  >
                    <div class="model-option">
                      <span class="model-option__name">{{ model.name }}</span>
                      <el-tag size="small" :type="model.status === 'available' ? 'success' : 'info'">
                        {{ model.provider }}
                      </el-tag>
                    </div>
                  </el-option>
                </el-select>
                <p class="field-hint">
                  从模型管理选择决策用大模型；规则模式下无需配置。
                </p>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :md="10">
              <el-form-item label="决策温度" prop="decisionLlmTemperature">
                <el-slider
                  v-model="form.decisionLlmTemperature"
                  :min="0"
                  :max="1"
                  :step="0.1"
                  show-input
                  :show-input-controls="false"
                />
                <p class="field-hint">越低越稳定；回测默认会压到 0 以提高可复现性。</p>
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <template v-if="form.decisionMode === 'rule'">
          <el-form-item label="规则预设">
            <el-select
              v-model="rulePreset"
              class="decision-preset-select"
              placeholder="选择预设"
              @change="applyRulePreset"
            >
              <el-option
                v-for="preset in rulePresets"
                :key="preset.id"
                :label="preset.name"
                :value="preset.id"
              >
                <div class="preset-option">
                  <span class="preset-option__name">{{ preset.name }}</span>
                  <span class="preset-option__desc">{{ preset.description }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>

          <el-form-item label="启用规则">
            <el-checkbox-group
              v-model="enabledRules"
              class="rule-checkbox-grid"
              :disabled="rulePreset !== 'custom'"
              @change="syncRuleConfigToForm"
            >
              <el-checkbox
                v-for="rule in ruleCatalog"
                :key="rule.id"
                :value="rule.id"
                class="rule-checkbox-item"
              >
                <span class="rule-checkbox__name">{{ rule.name }}</span>
                <span class="rule-checkbox__desc">{{ rule.description }}</span>
              </el-checkbox>
            </el-checkbox-group>
            <p v-if="rulePreset !== 'custom'" class="field-hint">切换为「自定义」预设后可单独勾选规则。</p>
          </el-form-item>
        </template>
      </div>

      <div class="config-section analysis-section">
        <header class="analysis-section__head">
          <h4 class="section-title analysis-section__title">决策分析来源</h4>
          <p class="analysis-section__kicker">
            <template v-if="form.decisionMode === 'rule'">
              规则模式主要使用 K 线指标，以下库表注入为可选项；若仅需指标规则可保持关闭。
            </template>
            <template v-else>
              勾选后由服务层从库中读取数据写入决策上下文；回测按当前 K 线时间对齐历史记录。LLM 模式请在上方配置决策模型。
            </template>
          </p>
        </header>

        <el-row :gutter="20" class="analysis-panels-row">
          <el-col :xs="24" :lg="12">
            <div
              class="analysis-panel"
              :class="{ 'analysis-panel--on': form.useNewsAnalysis }"
            >
              <div class="analysis-panel__header">
                <el-checkbox v-model="form.useNewsAnalysis" class="analysis-panel__checkbox">
                  消息面
                </el-checkbox>
                <span class="analysis-panel__tag">资讯时间轴</span>
              </div>

              <div v-show="form.useNewsAnalysis" class="analysis-panel__body">
                <el-form-item
                  label="采集任务"
                  prop="newsIntelligenceAgentId"
                  class="analysis-field"
                >
                  <el-select
                    v-model="form.newsIntelligenceAgentId"
                    placeholder="选择消息面采集 Agent"
                    class="analysis-panel__control"
                    filterable
                    clearable
                    :loading="loadingNewsAgents"
                  >
                    <template v-if="newsAgents.length === 0 && !loadingNewsAgents" #empty>
                      <div class="analysis-empty">
                        <span>暂无任务</span>
                        <a class="analysis-empty__link" href="#" @click.prevent="emit('navigate', '/news-intelligence')">去创建</a>
                      </div>
                    </template>
                    <el-option
                      v-for="a in newsAgents"
                      :key="a.id"
                      :label="a.name + (a.remark ? ` — ${a.remark}` : '')"
                      :value="a.id"
                    />
                  </el-select>
                </el-form-item>

                <el-form-item
                  label="单次最多引用条数"
                  prop="newsContextMaxItems"
                  class="analysis-field"
                >
                  <div class="analysis-num-row">
                    <el-input-number
                      v-model="form.newsContextMaxItems"
                      class="analysis-input-num"
                      :min="1"
                      :max="50"
                      :step="1"
                      controls-position="right"
                    />
                    <span class="analysis-num-suffix">条</span>
                  </div>
                  <p class="analysis-hint">
                    按资讯排序时间倒序，且不超过当前决策时刻；范围 1～50。
                  </p>
                </el-form-item>
              </div>

              <p v-show="!form.useNewsAnalysis" class="analysis-panel__placeholder">
                关闭时不读取资讯库
              </p>
            </div>
          </el-col>

          <el-col :xs="24" :lg="12">
            <div
              class="analysis-panel"
              :class="{ 'analysis-panel--on': form.useTechnicalAnalysis }"
            >
              <div class="analysis-panel__header">
                <el-checkbox v-model="form.useTechnicalAnalysis" class="analysis-panel__checkbox">
                  技术面
                </el-checkbox>
                <span class="analysis-panel__tag">分析记录</span>
              </div>

              <div v-show="form.useTechnicalAnalysis" class="analysis-panel__body">
                <el-form-item
                  label="执行周期"
                  prop="technicalAnalysisTimeframe"
                  class="analysis-field"
                >
                  <el-select
                    v-model="form.technicalAnalysisTimeframe"
                    placeholder="默认 15m"
                    class="analysis-panel__control"
                    clearable
                  >
                    <el-option
                      v-for="tf in technicalTimeframeOptions"
                      :key="tf.value"
                      :label="tf.label"
                      :value="tf.value"
                    />
                  </el-select>
                  <p class="analysis-hint">
                    决定短线执行节奏。当前技术面 LLM（含多周期并行生成）已暂停：决策仅使用 K 线指标结构化事实 + 决策 Agent。
                  </p>
                </el-form-item>

                <el-form-item
                  label="高周期背景"
                  prop="technicalAnalysisContextTimeframes"
                  class="analysis-field"
                >
                  <el-select
                    v-model="form.technicalAnalysisContextTimeframes"
                    multiple
                    collapse-tags
                    collapse-tags-tooltip
                    :placeholder="`默认自动补 ${defaultBackgroundSummary}`"
                    class="analysis-panel__control"
                    clearable
                    disabled
                  >
                    <el-option
                      v-for="tf in filteredBackgroundTimeframeOptions"
                      :key="tf.value"
                      :label="tf.label"
                      :value="tf.value"
                    />
                  </el-select>
                  <p class="analysis-hint">
                    多周期技术面 LLM 已暂停，此项暂不可用；恢复后将按各自周期独立缓存与过期。
                  </p>
                </el-form-item>
              </div>

              <p v-show="!form.useTechnicalAnalysis" class="analysis-panel__placeholder">
                关闭时不读取技术面；开启后由决策 Agent 使用 K 线指标结构化事实（技术面 LLM 已暂停）
              </p>
            </div>
          </el-col>
        </el-row>
      </div>

      <div class="config-section">
        <el-form-item label="策略备注" prop="remark">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="2"
            placeholder="选填，策略说明或注意事项"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
/*
import { ref, reactive, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { StrategyConfig, TradingStyle, TechnicalAnalysisTimeframe } from '@/api/agents'

const props = defineProps<{
  modelValue?: StrategyConfig | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: StrategyConfig]
}>()

const formRef = ref<FormInstance>()

const commonSymbols = [
  'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
  'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT',
  'MATICUSDT', 'LTCUSDT', 'ATOMUSDT', 'UNIUSDT', 'APTUSDT'
]

const defaultConfig: StrategyConfig = {
  tradingStyle: 'balanced',
  symbols: ['BTCUSDT', 'ETHUSDT'],
  minOrderAmount: 10,
  maxOrderAmount: 1000,
  priceDeviationUpper: 1,
  priceDeviationLower: 1,
  maxDailyTrades: 50,
  maxPositionRatio: 30,
  leverage: 1,
  trailingStopEnabled: false,
  trailingStopRatio: 1,
}

const form = reactive<StrategyConfig>({ ...defaultConfig })

// 仅交易对必填，其余使用默认值以降低门槛
const rules: FormRules = {
  symbols: [{ required: true, type: 'array', min: 1, message: '请至少选择一个交易对', trigger: 'change' }],
}

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      Object.assign(form, val)
    } else {
      Object.assign(form, defaultConfig)
    }
  },
  { immediate: true }
)

watch(
  form,
  (newForm) => {
    emit('update:modelValue', { ...newForm })
  },
  { deep: true }
)

async function validate(): Promise<boolean> {
  if (!formRef.value) return false
  return new Promise((resolve) => {
    formRef.value!.validate((valid) => {
      resolve(!!valid)
    })
  })
}

function getConfig(): StrategyConfig {
  return { ...form }
}

function resetConfig() {
  Object.assign(form, defaultConfig)
}

defineExpose({ validate, getConfig, resetConfig })
*/

import { computed, ref, reactive, watch, onMounted, nextTick } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { StrategyConfig, TradingStyle, TechnicalAnalysisTimeframe } from '@/api/agents'
import {
  RULE_CATALOG,
  RULE_PRESETS,
  DEFAULT_ENABLED_RULES,
  resolveEnabledRules,
} from '@/constants/ruleDecision'
import {
  newsIntelligenceApi,
  type NewsIntelligenceAgentListItem,
} from '@/api/newsIntelligence'
import { modelManagementApi, type ModelItem } from '@/api/modelManagement'

const props = defineProps<{
  modelValue?: StrategyConfig | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: StrategyConfig]
  'navigate': [path: string]
}>()

const formRef = ref<FormInstance>()
const newsAgents = ref<NewsIntelligenceAgentListItem[]>([])
const loadingNewsAgents = ref(false)
const loadingLlmModels = ref(false)
const llmModels = ref<ModelItem[]>([])

const technicalTimeframeOptions = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '1h', label: '1h' },
  { value: '2h', label: '2h' },
  { value: '4h', label: '4h' },
  { value: '6h', label: '6h' },
  { value: '12h', label: '12h' },
  { value: '1d', label: '1d' },
  { value: '1w', label: '1w' },
] as Array<{ value: TechnicalAnalysisTimeframe; label: string }>

function defaultBackgroundTimeframes(executionTf: TechnicalAnalysisTimeframe): TechnicalAnalysisTimeframe[] {
  if (['1m', '5m', '15m'].includes(executionTf)) return ['1h', '4h', '1d']
  if (['30m', '1h', '2h'].includes(executionTf)) return ['4h', '1d']
  if (['4h', '6h', '12h'].includes(executionTf)) return ['1d', '1w']
  if (executionTf === '1d') return ['1w']
  return []
}

const effectiveExecutionTimeframe = computed<TechnicalAnalysisTimeframe>(
  () => form.technicalAnalysisTimeframe || '15m'
)

const filteredBackgroundTimeframeOptions = computed(() =>
  technicalTimeframeOptions.filter((item) => item.value !== effectiveExecutionTimeframe.value)
)

const defaultBackgroundSummary = computed(() => {
  const items = defaultBackgroundTimeframes(effectiveExecutionTimeframe.value)
  return items.length ? items.join(' / ') : '无额外高周期'
})

const commonSymbols = [
  'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
  'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT',
  'MATICUSDT', 'LTCUSDT', 'ATOMUSDT', 'UNIUSDT', 'APTUSDT'
]

const stylePresets: Record<TradingStyle, { rangeLong: number; rangeShort: number; tolerance: number; takeProfitMode: NonNullable<StrategyConfig['rangeTakeProfitMode']> }> = {
  conservative: { rangeLong: 32, rangeShort: 68, tolerance: 0.003, takeProfitMode: 'mid_band' },
  balanced: { rangeLong: 35, rangeShort: 65, tolerance: 0.005, takeProfitMode: 'mid_band' },
  aggressive: { rangeLong: 38, rangeShort: 62, tolerance: 0.008, takeProfitMode: 'opposite_band' },
}

function applyStylePreset(style: TradingStyle) {
  const preset = stylePresets[style]
  if (!preset) return
  form.tradingCycle = 'short_term'
  form.rangeRsiLongThreshold = preset.rangeLong
  form.rangeRsiShortThreshold = preset.rangeShort
  form.rangeEntryBandTolerance = preset.tolerance
  form.rangeTakeProfitMode = preset.takeProfitMode
}

const ruleCatalog = RULE_CATALOG
const rulePresets = RULE_PRESETS
const rulePreset = ref('balanced_auto')
const enabledRules = ref<string[]>([...DEFAULT_ENABLED_RULES])

function syncRuleConfigToForm() {
  const nextRuleConfig = {
    preset: rulePreset.value,
    enabledRules: [...enabledRules.value],
    composition: 'priority_stack' as const,
  }
  if (JSON.stringify(form.ruleConfig ?? {}) !== JSON.stringify(nextRuleConfig)) {
    form.ruleConfig = nextRuleConfig
  }
}

function normalizeStrategyConfig(raw: StrategyConfig): StrategyConfig {
  const config = { ...raw } as StrategyConfig
  if (config.tradingStyle === 'conservative') {
    config.maxLeverage = 1
  } else if (config.tradingStyle === 'aggressive' && Number(config.maxLeverage || 1) < 2) {
    config.maxLeverage = 2
  }
  if (config.maxPositionRatio == null) {
    const styleDefaults: Record<TradingStyle, number> = {
      conservative: 20,
      balanced: 30,
      aggressive: 50,
    }
    config.maxPositionRatio = styleDefaults[config.tradingStyle || 'balanced']
  }
  if (config.reducePositionRatio == null) config.reducePositionRatio = 50
  if (config.decisionMode === 'rule') {
    delete config.decisionLlmModelId
    delete config.decisionLlmTemperature
  } else if (config.decisionLlmTemperature == null) {
    config.decisionLlmTemperature = 0.3
  }
  if (!config.useNewsAnalysis) {
    delete config.newsIntelligenceAgentId
    delete config.newsContextMaxItems
  }
  if (!config.useTechnicalAnalysis) {
    delete config.technicalAnalysisTimeframe
    delete config.technicalAnalysisContextTimeframes
  } else if (!config.technicalAnalysisContextTimeframes || config.technicalAnalysisContextTimeframes.length === 0) {
    delete config.technicalAnalysisContextTimeframes
  } else {
    const effectiveTf = config.technicalAnalysisTimeframe || '15m'
    config.technicalAnalysisContextTimeframes = config.technicalAnalysisContextTimeframes.filter(
      (tf) => tf !== effectiveTf
    )
    if (config.technicalAnalysisContextTimeframes.length === 0) {
      delete config.technicalAnalysisContextTimeframes
    }
  }
  return config
}

function configsEqual(
  a: StrategyConfig | null | undefined,
  b: StrategyConfig | null | undefined
): boolean {
  const left = a ? normalizeStrategyConfig(a) : null
  const right = b ? normalizeStrategyConfig(b) : null
  return JSON.stringify(left) === JSON.stringify(right)
}

function applyRulePreset(presetId: string) {
  const preset = RULE_PRESETS.find((p) => p.id === presetId)
  if (!preset) return
  enabledRules.value = [...preset.enabledRules]
  syncRuleConfigToForm()
}

function hydrateRuleStateFromConfig(cfg: StrategyConfig) {
  const rc = cfg.ruleConfig
  rulePreset.value = rc?.preset || 'balanced_auto'
  enabledRules.value = resolveEnabledRules(rc)
  if (!cfg.decisionMode) form.decisionMode = 'trader'
}

const defaultConfig: StrategyConfig = {
  tradingStyle: 'balanced',
  symbols: ['BTCUSDT', 'ETHUSDT'],
  initialCapital: 1000,
  targetProfit: { type: 'percentage', value: 10 },
  tradingCycle: 'short_term',
  minOrderAmount: 10,
  maxOrderAmount: 1000,
  maxPositionRatio: 30,
  reducePositionRatio: 50,
  maxLeverage: 5,
  positionDirection: 'both',
  marketMode: 'auto',
  rangeRsiLongThreshold: 35,
  rangeRsiShortThreshold: 65,
  rangeEntryBandTolerance: 0.005,
  rangeTakeProfitMode: 'mid_band',
  remark: undefined,
  useNewsAnalysis: false,
  newsIntelligenceAgentId: undefined,
  newsContextMaxItems: 15,
  useTechnicalAnalysis: false,
  technicalAnalysisTimeframe: undefined,
  technicalAnalysisContextTimeframes: undefined,
  decisionMode: 'trader',
  traderConfig: {
    executionMode: 'shadow',
    maxToolCallsPerTurn: 6,
    maxOrderRevisionsPerTurn: 2,
    turnTimeoutSeconds: 60,
    defaultReviewIntervalMinutes: 15,
  },
  decisionLlmModelId: undefined,
  decisionLlmTemperature: 0.3,
  ruleConfig: {
    preset: 'balanced_auto',
    enabledRules: [...DEFAULT_ENABLED_RULES],
    composition: 'priority_stack',
  },
}

const form = reactive<StrategyConfig>({ ...defaultConfig })

const leveragePolicyHint = computed(() => {
  if (form.tradingStyle === 'aggressive') {
    return `激进风格每笔开仓/加仓必须申请 2x 至 ${form.maxLeverage}x；RiskKernel 仍可按风险缩量。`
  }
  if (form.tradingStyle === 'conservative') {
    return '稳定风格固定 1x，LLM 和执行层均不允许使用杠杆。'
  }
  return `均衡风格可逐单选择 1x 至 ${form.maxLeverage}x，允许不使用杠杆。`
})

function applyLeveragePolicy(style: TradingStyle) {
  if (style === 'conservative') {
    form.maxLeverage = 1
  } else if (style === 'aggressive' && Number(form.maxLeverage || 1) < 2) {
    form.maxLeverage = 2
  }
}

const traderExecutionMode = computed<'shadow' | 'live'>({
  get: () => form.traderConfig?.executionMode ?? 'shadow',
  set: (value) => {
    form.traderConfig = {
      ...(form.traderConfig || { executionMode: 'shadow' }),
      executionMode: value,
    }
  },
})

/** 从 props 回填表单时跳过向父组件 emit，避免 v-model 与 form 深度 watch 死循环 */
let syncingFromProps = false

const rules: FormRules = {
  symbols: [{ required: true, type: 'array', min: 1, message: '请至少选择一个交易对', trigger: 'change' }],
  initialCapital: [
    { required: true, message: '请输入初始本金', trigger: 'blur' },
    { type: 'number', min: 10, message: '初始本金最小为 10 USDT', trigger: 'blur' }
  ],
  'targetProfit.value': [
    { required: true, message: '请输入目标利润数值', trigger: 'blur' },
    { type: 'number', min: 0, message: '目标利润不能小于 0', trigger: 'blur' }
  ],
  minOrderAmount: [
    { required: true, message: '请输入最小单次交易金额', trigger: 'blur' },
    { type: 'number', min: 1, message: '最小交易金额最小为 1 USDT', trigger: 'blur' }
  ],
  maxOrderAmount: [
    { required: true, message: '请输入单笔最大保证金', trigger: 'blur' },
    { type: 'number', min: 1, message: '最大交易金额最小为 1 USDT', trigger: 'blur' },
    {
      validator: (_rule, value: number, callback) => {
        if (value < form.minOrderAmount) {
          callback(new Error('最大交易金额必须大于等于最小交易金额'))
          return
        }
        callback()
      },
      trigger: 'blur'
    }
  ],
  maxPositionRatio: [
    { required: true, message: '请输入最大保证金占用', trigger: 'blur' },
    { type: 'number', min: 1, max: 100, message: '最大保证金占用必须在 1% 到 100% 之间', trigger: 'blur' }
  ],
  reducePositionRatio: [
    { required: true, message: '请输入默认减仓比例', trigger: 'blur' },
    { type: 'number', min: 1, max: 100, message: '减仓比例必须在 1% 到 100% 之间', trigger: 'blur' }
  ],
  newsIntelligenceAgentId: [
    {
      validator: (_rule, value: string | undefined, callback) => {
        if (form.useNewsAnalysis && !value) {
          callback(new Error('请选择消息面采集任务'))
          return
        }
        callback()
      },
      trigger: 'change'
    }
  ],
  decisionLlmModelId: [
    {
      validator: (_rule, value: number | undefined, callback) => {
        if (form.decisionMode !== 'trader') {
          callback()
          return
        }
        if (!value) {
          callback(new Error('请选择决策 LLM'))
          return
        }
        callback()
      },
      trigger: 'change'
    }
  ]
}

watch(
  () => props.modelValue,
  async (val) => {
    syncingFromProps = true
    try {
      if (val) {
        Object.assign(
          form,
          normalizeStrategyConfig({
            ...defaultConfig,
            ...val,
            // 旧配置没有该字段时交给 normalizeStrategyConfig 按原交易风格补 20/30/50，
            // 避免 aggressive/conservative 被前端默认 30% 覆盖。
            maxPositionRatio: val.maxPositionRatio,
          })
        )
        hydrateRuleStateFromConfig(form)
      } else {
        Object.assign(form, normalizeStrategyConfig({ ...defaultConfig }))
        rulePreset.value = 'balanced_auto'
        enabledRules.value = [...DEFAULT_ENABLED_RULES]
      }
      applyStylePreset(form.tradingStyle)
      syncRuleConfigToForm()
      Object.assign(form, normalizeStrategyConfig({ ...form } as StrategyConfig))
    } finally {
      await nextTick()
      syncingFromProps = false
    }
  },
  { immediate: true }
)

watch(
  () => form.tradingStyle,
  (style) => {
    if (syncingFromProps) return
    applyStylePreset(style)
    applyLeveragePolicy(style)
  }
)

watch(
  () => form.decisionMode,
  (mode) => {
    if (syncingFromProps) return
    if (mode === 'rule') {
      form.decisionLlmModelId = undefined
    }
    syncRuleConfigToForm()
  }
)

watch(
  () => form.marketMode,
  (mode) => {
    if (form.decisionMode !== 'rule') return
    if (mode === 'trend_only' && rulePreset.value === 'balanced_auto') {
      rulePreset.value = 'trend_rider'
      applyRulePreset('trend_rider')
    } else if (mode === 'range_only' && rulePreset.value === 'balanced_auto') {
      rulePreset.value = 'range_scalper'
      applyRulePreset('range_scalper')
    }
  }
)

watch(
  form,
  () => {
    if (syncingFromProps) return
    syncRuleConfigToForm()
    const next = getConfig()
    if (configsEqual(next, props.modelValue)) return
    emit('update:modelValue', next)
  },
  { deep: true }
)

watch(
  () => form.useNewsAnalysis,
  (on) => {
    if (syncingFromProps) return
    if (!on) {
      form.newsIntelligenceAgentId = undefined
    }
  }
)

watch(
  () => form.useTechnicalAnalysis,
  (on) => {
    if (syncingFromProps) return
    if (!on) {
      form.technicalAnalysisTimeframe = undefined
      form.technicalAnalysisContextTimeframes = undefined
    }
  }
)

watch(
  () => form.technicalAnalysisTimeframe,
  (executionTf) => {
    const effectiveTf = executionTf || '15m'
    if (!form.technicalAnalysisContextTimeframes?.length) return
    form.technicalAnalysisContextTimeframes = form.technicalAnalysisContextTimeframes.filter(
      (tf) => tf !== effectiveTf
    )
  }
)

async function loadNewsAgents() {
  loadingNewsAgents.value = true
  try {
    const res = await newsIntelligenceApi.getList()
    newsAgents.value = res.list || []
  } catch {
    newsAgents.value = []
  } finally {
    loadingNewsAgents.value = false
  }
}

async function loadLlmModels() {
  loadingLlmModels.value = true
  try {
    const res = await modelManagementApi.getModels({ is_active: true })
    llmModels.value = res.items || []
  } catch {
    llmModels.value = []
  } finally {
    loadingLlmModels.value = false
  }
}

onMounted(() => {
  loadNewsAgents()
  loadLlmModels()
})

async function validate(): Promise<boolean> {
  if (!formRef.value) return false
  return new Promise((resolve) => {
    formRef.value!.validate((valid) => resolve(!!valid))
  })
}

function getConfig(): StrategyConfig {
  return normalizeStrategyConfig({ ...form } as StrategyConfig)
}

function resetConfig() {
  Object.assign(form, defaultConfig)
}

defineExpose({ validate, getConfig, resetConfig })
</script>

<style scoped>
.strategy-config-panel {
  padding: 0;
}

.config-form {
  max-width: 100%;
}

.config-section {
  margin-bottom: 28px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--color-border);
}

.config-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}

.section-title {
  margin: 0 0 20px;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title::before {
  content: '';
  display: inline-block;
  width: 3px;
  height: 16px;
  background: var(--color-primary);
  border-radius: 2px;
}

.style-radio-group {
  display: flex;
  gap: 12px;
  width: 100%;
}

.style-radio-group :deep(.el-radio-button) {
  flex: 1;
}

.style-radio-group :deep(.el-radio-button__inner) {
  width: 100%;
  padding: 12px 16px;
  height: auto;
  border-radius: var(--radius-md) !important;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}

.style-radio-group :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: rgba(var(--color-primary-rgb), 0.08) !important;
  border-color: var(--color-primary) !important;
  color: var(--color-primary) !important;
  box-shadow: none !important;
}

.style-radio-group :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) .style-name {
  color: var(--color-primary);
  font-weight: 700;
}

.style-radio-group :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) .style-desc {
  color: var(--color-text-secondary);
}

.style-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.style-name {
  font-size: 14px;
  font-weight: 600;
}

.style-desc {
  font-size: 12px;
  color: var(--color-text-muted);
  font-weight: 400;
}

/* 输入框带单位样式 */
.input-with-unit {
  display: flex;
  align-items: center;
  gap: 8px;
}

.input-with-unit .el-input-number {
  flex: 1;
}

.input-with-unit.compact .el-input-number {
  width: 120px;
  flex: none;
}

.input-unit {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--color-text-muted);
  min-width: 40px;
}

/* 滑块行样式 */
.slider-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.config-slider {
  flex: 1;
}

.slider-value {
  flex-shrink: 0;
  min-width: 50px;
  text-align: right;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
}

/* 追踪止损行样式 */
.trailing-stop-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.trailing-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* 表单项样式 */
.config-form :deep(.el-form-item) {
  margin-bottom: 20px;
}

.config-form :deep(.el-form-item__label) {
  color: var(--color-text-secondary);
  font-weight: 500;
  padding-bottom: 8px;
}

.config-form :deep(.el-input-number) {
  width: 100%;
}

.config-form :deep(.el-input-number .el-input__inner) {
  text-align: left;
}

.config-form :deep(.el-input-number--small) {
  width: 100%;
}

.config-form :deep(.el-slider__runway) {
  background: var(--color-bg-elevated);
}

.field-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 6px;
  line-height: 1.4;
}

.fixed-mode-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(var(--color-primary-rgb), 0.22);
  background: rgba(var(--color-primary-rgb), 0.06);
}

.fixed-mode-card__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.fixed-mode-card__desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

/* —— 决策分析来源：双栏卡片 —— */
.analysis-section {
  padding-top: 4px;
}

.analysis-section__head {
  margin-bottom: 18px;
}

.analysis-section__title {
  margin-bottom: 6px;
}

.analysis-section__kicker {
  margin: 0;
  max-width: 920px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--color-text-muted);
  font-weight: 400;
}

.analysis-panels-row {
  align-items: stretch;
}

.analysis-panels-row :deep(.el-col) {
  display: flex;
}

.analysis-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 100%;
  padding: 16px 18px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  box-sizing: border-box;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    background 0.2s ease;
}

.analysis-panel--on {
  border-color: rgba(var(--color-primary-rgb), 0.35);
  box-shadow: 0 0 0 1px rgba(var(--color-primary-rgb), 0.1);
  background: rgba(var(--color-primary-rgb), 0.05);
}

.analysis-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 0;
}

.analysis-panel__checkbox {
  font-weight: 600;
  font-size: 14px;
  color: var(--color-text-primary);
}

.analysis-panel__checkbox :deep(.el-checkbox__label) {
  font-weight: 600;
}

.analysis-panel__tag {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--color-text-muted);
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-primary-ghost);
  border: 1px solid var(--color-border);
}

.analysis-panel__body {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.analysis-field {
  margin-bottom: 14px !important;
}

.analysis-field:last-child {
  margin-bottom: 0 !important;
}

.analysis-field :deep(.el-form-item__label) {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  padding-bottom: 6px;
  line-height: 1.3;
}

.analysis-panel__control {
  width: 100%;
}

.analysis-num-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.analysis-input-num {
  flex-shrink: 0;
}

/* 覆盖表单内「数字输入 100% 宽」规则，本条数控件保持固定宽度 */
.analysis-num-row :deep(.el-input-number) {
  width: 132px !important;
  max-width: 132px;
}

.analysis-num-suffix {
  font-size: 13px;
  color: var(--color-text-muted);
  user-select: none;
}

.analysis-hint {
  margin: 8px 0 0;
  padding: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-muted);
  max-width: 100%;
}

.analysis-panel__placeholder {
  margin: 10px 0 0;
  padding: 10px 0 2px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--color-text-muted);
  text-align: center;
  opacity: 0.85;
}

.analysis-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.analysis-empty__link {
  color: var(--color-primary);
  text-decoration: none;
  font-size: 12px;
}

.analysis-empty__link:hover {
  text-decoration: underline;
}

/* ========== 决策模式 ========== */
.decision-llm-select {
  width: 100%;
}

.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.model-option__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--color-text-muted);
}

.config-link {
  border: none;
  background: none;
  padding: 0;
  color: var(--color-primary);
  font-size: 13px;
  cursor: pointer;
}

.config-link:hover {
  text-decoration: underline;
}

.decision-mode-section .section-kicker {
  margin: 0 0 16px;
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.5;
}

.decision-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
}

.decision-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 14px 16px;
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

.decision-card__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.decision-card__desc {
  font-size: 12px;
  line-height: 1.45;
  color: var(--color-text-muted);
}

.decision-preset-select {
  width: 100%;
  max-width: 360px;
}

.preset-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 0;
}

.preset-option__name {
  font-size: 13px;
  font-weight: 600;
}

.preset-option__desc {
  font-size: 12px;
  color: var(--color-text-muted);
}

.rule-checkbox-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
  width: 100%;
}

.rule-checkbox-item {
  display: flex;
  align-items: flex-start;
  height: auto;
  margin-right: 0;
  white-space: normal;
}

.rule-checkbox-item :deep(.el-checkbox__label) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.4;
  white-space: normal;
}

.rule-checkbox__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.rule-checkbox__desc {
  font-size: 12px;
  color: var(--color-text-muted);
}

@media (max-width: 768px) {
  .decision-options,
  .rule-checkbox-grid {
    grid-template-columns: 1fr;
  }
}

.empty-tip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.config-link {
  color: var(--color-primary);
  text-decoration: none;
  font-size: 12px;
}

.config-link:hover {
  text-decoration: underline;
}

.target-profit-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.target-profit-type {
  width: 100%;
  display: flex;
  gap: 8px;
}

.target-profit-type :deep(.el-radio-button) {
  flex: 1;
}

.advanced-collapse {
  margin-bottom: 20px;
  border: none;
}

.advanced-collapse :deep(.el-collapse-item__header) {
  border: none;
  height: auto;
  padding: 12px 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.advanced-collapse :deep(.el-collapse-item__wrap) {
  border: none;
}

.advanced-collapse :deep(.el-collapse-item__content) {
  padding: 0 0 16px;
}

.collapse-title {
  font-weight: 600;
  color: var(--color-text-primary);
  margin-right: 8px;
}

.collapse-desc {
  font-size: 12px;
  color: var(--color-text-muted);
  font-weight: 400;
}

/* 行布局间距 */
.config-form :deep(.el-row) {
  margin-bottom: 0;
}

.config-form :deep(.el-col) {
  margin-bottom: 0;
}

@media (max-width: 991px) {
  .analysis-panels-row :deep(.el-col:not(:last-child)) {
    margin-bottom: 16px;
  }
}

@media (max-width: 992px) {
  .config-form :deep(.el-row) {
    row-gap: 4px;
  }

  .style-radio-group {
    flex-direction: column;
    gap: 10px;
  }

  .style-radio-group :deep(.el-radio-button) {
    flex: none;
    width: 100%;
  }

  .style-radio-group :deep(.el-radio-button__inner) {
    justify-content: center;
  }
}
</style>
