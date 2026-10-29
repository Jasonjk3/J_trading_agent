<template>
  <div class="agent-form-page">
    <header class="page-header">
      <div class="header-row">
        <el-button class="back-btn" text @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回列表
        </el-button>
      </div>
      <div class="header-main">
        <h1 class="page-title">{{ isEdit ? '编辑 Agent' : '添加 Agent' }}</h1>
        <p class="page-desc">
          {{ isEdit ? '修改基础信息与策略参数，保存后立即生效（运行中 Agent 部分项可能受限）。' : '填写基础信息并配置策略，创建后可前往运行监控启停与查看收益。' }}
        </p>
      </div>
    </header>

    <div v-loading="loadingAgent" class="form-shell">
      <AgentForm
        v-if="!isEdit || agent"
        ref="formRef"
        :edit-record="isEdit ? agent : null"
        @submit="onSubmit"
        @navigate="handleNavigate"
      />
      <footer class="form-actions">
        <el-button size="large" @click="goBack">取消</el-button>
        <el-button type="primary" size="large" :loading="submitLoading" @click="handleConfirm">
          {{ isEdit ? '保存' : '创建 Agent' }}
        </el-button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { agentsApi } from '@/api/agents'
import type { AgentListItem, CreateAgentDto, UpdateAgentDto } from '@/api/agents'
import AgentForm from './AgentForm.vue'

const route = useRoute()
const router = useRouter()

const formRef = ref<InstanceType<typeof AgentForm>>()
const submitLoading = ref(false)
const loadingAgent = ref(false)
const agent = ref<AgentListItem | null>(null)

const isEdit = computed(() => route.name === 'AgentEdit')

async function loadAgent() {
  const id = route.params.id as string
  if (!id) {
    router.replace('/agents')
    return
  }
  loadingAgent.value = true
  try {
    agent.value = await agentsApi.getById(id)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载 Agent 失败')
    router.replace('/agents')
  } finally {
    loadingAgent.value = false
  }
}

function goBack() {
  router.push('/agents')
}

function handleNavigate(path: string) {
  router.push(path)
}

async function handleConfirm() {
  const ok = await formRef.value?.validateAndEmit()
  if (!ok) return
}

function onSubmit(payload: CreateAgentDto) {
  submitLoading.value = true
  const run = isEdit.value && route.params.id
    ? agentsApi.update(route.params.id as string, payload as UpdateAgentDto)
    : agentsApi.create(payload)

  run
    .then(() => {
      ElMessage.success(isEdit.value ? '保存成功' : '添加成功')
      router.push('/agents')
    })
    .catch((e: any) => ElMessage.error(e?.message ?? (isEdit.value ? '保存失败' : '添加失败')))
    .finally(() => {
      submitLoading.value = false
    })
}

async function syncRoute() {
  if (route.name === 'AgentEdit') {
    await loadAgent()
  } else {
    agent.value = null
  }
}

onMounted(() => {
  syncRoute()
})

watch(
  () => route.fullPath,
  () => {
    syncRoute()
  }
)
</script>

<style scoped>
.agent-form-page {
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 8px 32px;
  box-sizing: border-box;
}

.page-header {
  margin-bottom: 24px;
}

.header-row {
  margin-bottom: 8px;
}

.back-btn {
  padding-left: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.back-btn:hover {
  color: var(--color-primary);
}

.page-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.page-desc {
  margin: 10px 0 0;
  max-width: 720px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-secondary);
}

.form-shell {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 28px 32px 0;
  border: 1px solid var(--color-border);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin: 0 -32px;
  padding: 20px 32px 24px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-card);
  box-shadow: 0 -12px 24px rgba(0, 0, 0, 0.12);
  position: sticky;
  bottom: 0;
  z-index: 2;
}

@media (max-width: 768px) {
  .form-shell {
    padding: 20px 16px 0;
  }

  .form-actions {
    margin: 0 -16px;
    padding: 16px 16px 20px;
    flex-direction: column-reverse;
    align-items: stretch;
  }

  .form-actions .el-button {
    width: 100%;
    margin-left: 0;
  }
}
</style>

