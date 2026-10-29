<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="120px"
    class="ni-form"
    @submit.prevent
  >
    <el-form-item label="任务名称" prop="name">
      <el-input v-model="form.name" placeholder="例如：证券板块每日资讯" maxlength="80" show-word-limit />
    </el-form-item>
    <el-form-item label="备注" prop="remark">
      <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="可选" maxlength="500" show-word-limit />
    </el-form-item>

    <el-form-item label="金融方向" prop="sectors">
      <el-select
        v-model="form.sectors"
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="至少选择一个方向"
        style="width: 100%"
      >
        <el-option
          v-for="opt in FINANCIAL_SECTOR_OPTIONS"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </el-form-item>
    <el-form-item label="自定义关键词" prop="customKeywords">
      <el-input v-model="form.customKeywords" placeholder="空格或逗号分隔，可选" />
    </el-form-item>
    <el-form-item label="相关标的代码" prop="symbolCodes">
      <el-input v-model="form.symbolCodes" placeholder="如 600000 / 000001，可选" />
    </el-form-item>

    <el-form-item label="LLM 模型" prop="llmModelId">
      <el-select
        v-model="form.llmModelId"
        placeholder="请选择模型（需支持联网搜索）"
        filterable
        style="width: 100%"
        :loading="loadingModels"
      >
        <template v-if="llmModels.length === 0 && !loadingModels" #empty>
          <span style="padding: 8px 12px; color: var(--el-text-color-secondary)">暂无可用模型，请先在「模型管理」中配置</span>
        </template>
        <el-option
          v-for="model in llmModels"
          :key="model.id"
          :label="`${model.name} (${model.provider})`"
          :value="model.id"
        />
      </el-select>
    </el-form-item>

    <el-form-item label="采集频率" prop="intervalMinutes">
      <div class="freq-row">
        <el-input-number v-model="form.intervalMinutes" :min="1" :max="720" :step="1" controls-position="right" />
        <span class="freq-unit">分钟 / 次</span>
      </div>
      <p class="form-hint">频率过高会增加调用成本，建议不低于 15 分钟。</p>
    </el-form-item>

    <el-form-item label="单次条数上限" prop="maxItemsPerBatch">
      <el-input-number v-model="form.maxItemsPerBatch" :min="1" :max="50" :step="1" controls-position="right" />
    </el-form-item>

    <el-form-item label="温度" prop="temperature">
      <el-slider v-model="form.temperature" :min="0" :max="1" :step="0.1" show-input />
    </el-form-item>

    <el-form-item v-if="!isEdit" label=" ">
      <el-checkbox v-model="form.runOnCreate">创建后立即启动采集</el-checkbox>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { modelManagementApi, type ModelItem } from '@/api/modelManagement'
import {
  FINANCIAL_SECTOR_OPTIONS,
  type NewsIntelligenceAgentListItem,
  type CreateNewsIntelligenceAgentDto,
} from '@/api/newsIntelligence'

const props = defineProps<{
  editRecord?: NewsIntelligenceAgentListItem | null
}>()

const isEdit = computed(() => !!props.editRecord)

const formRef = ref<FormInstance>()
const loadingModels = ref(false)
const llmModels = ref<ModelItem[]>([])

const form = reactive<
  Omit<CreateNewsIntelligenceAgentDto, 'llmModelId'> & { llmModelId?: number; runOnCreate?: boolean }
>({
  name: '',
  remark: '',
  sectors: [],
  customKeywords: '',
  symbolCodes: '',
  llmModelId: undefined,
  intervalMinutes: 60,
  maxItemsPerBatch: 10,
  temperature: 0.3,
  runOnCreate: false,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  sectors: [
    {
      type: 'array',
      required: true,
      message: '请选择至少一个金融方向',
      trigger: 'change',
    },
  ],
  llmModelId: [{ required: true, message: '请选择模型', trigger: 'change' }],
  intervalMinutes: [{ required: true, message: '请设置采集频率', trigger: 'change' }],
}

function syncFromRecord() {
  const r = props.editRecord
  if (!r) {
    form.name = ''
    form.remark = ''
    form.sectors = []
    form.customKeywords = ''
    form.symbolCodes = ''
    form.llmModelId = undefined
    form.intervalMinutes = 60
    form.maxItemsPerBatch = 10
    form.temperature = 0.3
    form.runOnCreate = false
    return
  }
  form.name = r.name
  form.remark = r.remark || ''
  form.sectors = [...(r.sectors || [])]
  form.customKeywords = r.customKeywords || ''
  form.symbolCodes = r.symbolCodes || ''
  form.llmModelId = r.llmModelId
  form.intervalMinutes = r.intervalMinutes
  form.maxItemsPerBatch = r.maxItemsPerBatch ?? 10
  form.temperature = r.temperature ?? 0.3
}

watch(
  () => props.editRecord,
  () => syncFromRecord(),
  { immediate: true }
)

async function loadModels() {
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
  loadModels()
})

async function validateAndEmit(): Promise<boolean> {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return false
  const payload: CreateNewsIntelligenceAgentDto = {
    name: form.name.trim(),
    remark: form.remark?.trim() || undefined,
    sectors: [...form.sectors],
    customKeywords: form.customKeywords?.trim() || undefined,
    symbolCodes: form.symbolCodes?.trim() || undefined,
    llmModelId: form.llmModelId!,
    intervalMinutes: form.intervalMinutes,
    maxItemsPerBatch: form.maxItemsPerBatch,
    temperature: form.temperature,
    runOnCreate: form.runOnCreate,
  }
  emit('submit', payload)
  return true
}

const emit = defineEmits<{
  submit: [payload: CreateNewsIntelligenceAgentDto]
}>()

defineExpose({ validateAndEmit })
</script>

<style scoped>
.ni-form {
  max-width: 640px;
}

.freq-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.freq-unit {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.form-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-text-muted);
  line-height: 1.4;
}
</style>
