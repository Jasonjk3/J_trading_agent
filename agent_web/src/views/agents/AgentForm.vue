<template>
  <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="agent-form">
    <section class="form-section basic-section">
      <div class="section-head">
        <h3 class="section-title">基础信息</h3>
        <p class="section-hint">名称与交易所用于标识与鉴权；AI 交易员使用的模型在下方策略配置中绑定。</p>
      </div>
      <div class="basic-grid">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如：BTC 趋势 Agent" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="绑定交易所" prop="exchangeId">
          <el-select
            v-model="form.exchangeId"
            placeholder="请选择交易所配置"
            style="width: 100%"
            :loading="loadingExchanges"
          >
            <template v-if="exchangeAccounts.length === 0 && !loadingExchanges" #empty>
              <div class="empty-tip">
                <span>暂无交易所配置</span>
                <a class="config-link" href="#" @click.prevent="emit('navigate', '/exchange-accounts')">去配置</a>
              </div>
            </template>
            <el-option
              v-for="acc in exchangeAccounts"
              :key="acc.id"
              :label="exchangeLabel(acc.exchange) + (acc.remark ? ` - ${acc.remark}` : '')"
              :value="acc.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item class="span-full" label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="选填，便于团队识别用途" />
        </el-form-item>
      </div>
    </section>

    <section class="form-section strategy-section">
      <el-collapse v-model="expandedPanels" class="strategy-collapse">
        <el-collapse-item title="策略配置" name="strategy">
          <template #title>
            <div class="collapse-title">
              <el-icon><Setting /></el-icon>
              <span>策略配置</span>
              <el-tag v-if="hasStrategyConfig" size="small" type="success">已配置</el-tag>
            </div>
          </template>
          <div class="strategy-panel-wrap">
            <p class="strategy-intro">
              核心参数将参与下单与风控推导；交易对、风格与周期对信号频率影响最大。
            </p>
            <StrategyConfigPanel
              ref="strategyConfigRef"
              v-model="form.strategyConfig"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </section>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import { exchangeAccountsApi } from '@/api/exchangeAccounts'
import type { ExchangeAccountListItem, ExchangeCode } from '@/api/exchangeAccounts'
import type { AgentListItem, CreateAgentDto, StrategyConfig } from '@/api/agents'
import { mergeLegacyDecisionLlm, syncAgentLlmFromStrategy } from '@/api/agents'
import StrategyConfigPanel from '@/components/StrategyConfigPanel.vue'

const props = defineProps<{
  /** 非 null 时为编辑模式，表单会同步该记录 */
  editRecord: AgentListItem | null
}>()

const emit = defineEmits<{
  submit: [payload: CreateAgentDto]
  navigate: [path: string]
}>()

const formRef = ref<FormInstance>()
const strategyConfigRef = ref<InstanceType<typeof StrategyConfigPanel>>()
const exchangeAccounts = ref<ExchangeAccountListItem[]>([])
const expandedPanels = ref<string[]>([])
const loadingExchanges = ref(false)

const form = reactive<CreateAgentDto & { strategyConfig?: StrategyConfig }>({
  name: '',
  exchangeId: '',
  remark: '',
  strategyConfig: undefined,
})

const hasStrategyConfig = computed(() => {
  return form.strategyConfig && form.strategyConfig.symbols?.length > 0
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入 Agent 名称', trigger: 'blur' }],
  exchangeId: [{ required: true, message: '请选择绑定交易所', trigger: 'change' }],
}

function exchangeLabel(code: ExchangeCode): string {
  const map: Record<ExchangeCode, string> = { okx: 'OKX' }
  return map[code] ?? code
}

function applyRecord(record: AgentListItem | null) {
  loadExchangeAccounts()
  if (record) {
    form.name = record.name
    form.exchangeId = record.exchangeId
    form.remark = record.remark ?? ''
    form.strategyConfig = record.strategyConfig
      ? mergeLegacyDecisionLlm(record.strategyConfig, record.llmModelId) ?? undefined
      : undefined
    expandedPanels.value = ['strategy']
  } else {
    form.name = ''
    form.exchangeId = ''
    form.remark = ''
    form.strategyConfig = undefined
    expandedPanels.value = ['strategy']
  }
}

watch(() => props.editRecord, applyRecord, { immediate: true })

async function loadExchangeAccounts() {
  loadingExchanges.value = true
  try {
    const res = await exchangeAccountsApi.getList()
    exchangeAccounts.value = res.list || []
  } catch {
    exchangeAccounts.value = []
  } finally {
    loadingExchanges.value = false
  }
}

async function validateAndEmit(): Promise<boolean> {
  if (!formRef.value) return false

  return new Promise(async (resolve) => {
    const baseValid = await new Promise<boolean>((res) => {
      formRef.value!.validate((valid) => res(!!valid))
    })

    if (!baseValid) {
      resolve(false)
      return
    }

    if (expandedPanels.value.includes('strategy') && strategyConfigRef.value) {
      const strategyValid = await strategyConfigRef.value.validate()
      if (!strategyValid) {
        resolve(false)
        return
      }
      form.strategyConfig = strategyConfigRef.value.getConfig()
    }

    emit('submit', syncAgentLlmFromStrategy({ ...form }))
    resolve(true)
  })
}

defineExpose({ validateAndEmit, loadExchangeAccounts })
</script>

<style scoped>
.agent-form {
  padding: 0;
}

.agent-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.agent-form :deep(.el-form-item__label) {
  font-weight: 600;
  font-size: 13px;
  color: var(--color-text-primary);
  margin-bottom: 6px;
}

.form-section {
  margin-bottom: 28px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.section-head {
  margin-bottom: 18px;
}

.section-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title::before {
  content: '';
  width: 3px;
  height: 16px;
  background: var(--color-primary);
  border-radius: 2px;
  flex-shrink: 0;
}

.section-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-muted);
  max-width: 800px;
}

.basic-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 28px;
  align-items: start;
}

.basic-grid .span-full {
  grid-column: 1 / -1;
}

@media (max-width: 768px) {
  .basic-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}

.strategy-section {
  padding-top: 8px;
}

.strategy-collapse {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  overflow: hidden;
}

.strategy-collapse :deep(.el-collapse-item__header) {
  padding: 14px 20px;
  min-height: 52px;
  background: var(--color-primary-ghost);
  border-bottom: 1px solid var(--color-border);
  font-size: 15px;
}

.strategy-collapse :deep(.el-collapse-item__arrow) {
  margin-right: 4px;
}

.strategy-collapse :deep(.el-collapse-item__content) {
  padding: 0;
  border-top: none;
}

.strategy-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
}

.strategy-panel-wrap {
  padding: 20px 20px 8px;
}

.strategy-intro {
  margin: 0 0 16px;
  padding: 10px 14px;
  font-size: 12px;
  line-height: 1.55;
  color: var(--color-text-secondary);
  background: var(--color-primary-ghost);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.collapse-title .el-icon {
  color: var(--color-primary);
  font-size: 18px;
}

.empty-tip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  color: var(--color-text-secondary);
  font-size: 13px;
  gap: 8px;
}

.config-link {
  color: var(--color-primary);
  text-decoration: none;
  font-size: 12px;
}

.config-link:hover {
  text-decoration: underline;
}
</style>
