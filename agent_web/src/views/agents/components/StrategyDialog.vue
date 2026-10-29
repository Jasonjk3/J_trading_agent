<template>
  <el-dialog
    v-model="visible"
    title="策略配置"
    width="760px"
    :close-on-click-modal="false"
    destroy-on-close
    class="strategy-dialog"
    @closed="handleClosed"
  >
    <div v-loading="loading" class="strategy-dialog-body">
      <StrategyConfigPanel
        v-if="visible && !loading"
        ref="strategyConfigRef"
        v-model="currentConfig"
        @navigate="handleNavigate"
      />
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        保存配置
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { agentsApi, mergeLegacyDecisionLlm } from '@/api/agents'
import type { StrategyConfig } from '@/api/agents'
import StrategyConfigPanel from '@/components/StrategyConfigPanel.vue'

const router = useRouter()

const props = defineProps<{
  modelValue: boolean
  agentId: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'success': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = ref(false)
const saving = ref(false)
const strategyConfigRef = ref<InstanceType<typeof StrategyConfigPanel>>()
const currentConfig = ref<StrategyConfig | null>(null)
const pendingNavigate = ref<string | null>(null)

watch(
  () => props.modelValue,
  async (val) => {
    if (val && props.agentId) {
      loading.value = true
      try {
        const [configRes, agentRes] = await Promise.all([
          agentsApi.getStrategyConfig(props.agentId),
          agentsApi.getById(props.agentId),
        ])
        const raw = configRes.strategyConfig
        currentConfig.value = raw
          ? mergeLegacyDecisionLlm(raw, agentRes.llmModelId)
          : null
      } catch (e: any) {
        ElMessage.error(e?.message ?? '加载策略配置失败')
        currentConfig.value = null
      } finally {
        loading.value = false
      }
    }
  },
  { immediate: true }
)

async function handleSave() {
  if (!strategyConfigRef.value || !props.agentId) return
  const valid = await strategyConfigRef.value.validate()
  if (!valid) return

  saving.value = true
  try {
    const config = strategyConfigRef.value.getConfig()
    await agentsApi.updateStrategyConfig(props.agentId, { strategyConfig: config })
    ElMessage.success('策略配置保存成功')
    visible.value = false
    emit('success')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  } finally {
    saving.value = false
  }
}

function handleNavigate(path: string) {
  pendingNavigate.value = path
  visible.value = false
}

function handleClosed() {
  currentConfig.value = null
  if (pendingNavigate.value) {
    const path = pendingNavigate.value
    pendingNavigate.value = null
    router.push(path)
  }
}
</script>

<style scoped>
.strategy-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
  max-height: 65vh;
  overflow-y: auto;
}

.strategy-dialog-body {
  min-height: 200px;
}
</style>
