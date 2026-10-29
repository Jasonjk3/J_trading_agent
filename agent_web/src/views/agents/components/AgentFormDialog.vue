<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑 Agent' : '添加 Agent'"
    width="680px"
    :close-on-click-modal="false"
    class="agent-form-dialog"
    @closed="handleClosed"
  >
    <div v-loading="loadingAgent" class="dialog-body">
      <AgentForm
        v-if="!isEdit || agent"
        ref="formRef"
        :edit-record="isEdit ? agent : null"
        @submit="onSubmit"
        @navigate="handleNavigate"
      />
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitLoading" @click="handleConfirm">
        {{ isEdit ? '保存' : '创建 Agent' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { agentsApi } from '@/api/agents'
import type { AgentListItem, CreateAgentDto, UpdateAgentDto } from '@/api/agents'
import AgentForm from '../AgentForm.vue'

const router = useRouter()

const props = defineProps<{
  modelValue: boolean
  editId?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'success': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const formRef = ref<InstanceType<typeof AgentForm>>()
const submitLoading = ref(false)
const loadingAgent = ref(false)
const agent = ref<AgentListItem | null>(null)

const isEdit = computed(() => !!props.editId)

async function loadAgent() {
  if (!props.editId) {
    agent.value = null
    return
  }
  loadingAgent.value = true
  try {
    agent.value = await agentsApi.getById(props.editId)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载 Agent 失败')
    visible.value = false
  } finally {
    loadingAgent.value = false
  }
}

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      if (props.editId) {
        loadAgent()
      } else {
        agent.value = null
      }
    }
  },
  { immediate: true }
)

async function handleConfirm() {
  const ok = await formRef.value?.validateAndEmit()
  if (!ok) return
}

function onSubmit(payload: CreateAgentDto) {
  submitLoading.value = true
  const run = isEdit.value && props.editId
    ? agentsApi.update(props.editId, payload as UpdateAgentDto)
    : agentsApi.create(payload)

  run
    .then(() => {
      ElMessage.success(isEdit.value ? '保存成功' : '添加成功')
      visible.value = false
      emit('success')
    })
    .catch((e: any) => ElMessage.error(e?.message ?? (isEdit.value ? '保存失败' : '添加失败')))
    .finally(() => {
      submitLoading.value = false
    })
}

function handleClosed() {
  agent.value = null
}

function handleNavigate(path: string) {
  visible.value = false
  router.push(path)
}
</script>

<style scoped>
.agent-form-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
  max-height: 70vh;
  overflow-y: auto;
}

.dialog-body {
  min-height: 200px;
}
</style>
