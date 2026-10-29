<template>
  <div class="ni-form-page">
    <header class="page-header">
      <div class="header-row">
        <el-button class="back-btn" text @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回列表
        </el-button>
      </div>
      <div class="header-main">
        <h1 class="page-title">{{ isEdit ? '编辑采集任务' : '创建消息面采集 Agent' }}</h1>
        <p class="page-desc">
          {{
            isEdit
              ? '修改金融方向、模型与采集频率；保存后将在下一轮调度生效。'
              : '选择关注的金融板块与 LLM 模型，系统将按频率通过联网检索汇总资讯。'
          }}
        </p>
      </div>
    </header>

    <div v-loading="loadingAgent" class="form-shell">
      <NewsIntelligenceForm
        v-if="!isEdit || agent"
        ref="formRef"
        :edit-record="isEdit ? agent : null"
        @submit="onSubmit"
      />
      <footer class="form-actions">
        <el-button size="large" @click="goBack">取消</el-button>
        <el-button type="primary" size="large" :loading="submitLoading" @click="handleConfirm">
          {{ isEdit ? '保存' : '创建' }}
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
import { newsIntelligenceApi } from '@/api/newsIntelligence'
import type { NewsIntelligenceAgentListItem, CreateNewsIntelligenceAgentDto, UpdateNewsIntelligenceAgentDto } from '@/api/newsIntelligence'
import NewsIntelligenceForm from './NewsIntelligenceForm.vue'

const route = useRoute()
const router = useRouter()

const formRef = ref<InstanceType<typeof NewsIntelligenceForm>>()
const submitLoading = ref(false)
const loadingAgent = ref(false)
const agent = ref<NewsIntelligenceAgentListItem | null>(null)

const isEdit = computed(() => route.name === 'NewsIntelligenceEdit')

async function loadAgent() {
  const id = route.params.id as string
  if (!id) {
    router.replace('/news-intelligence')
    return
  }
  loadingAgent.value = true
  try {
    agent.value = await newsIntelligenceApi.getById(id)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载失败')
    router.replace('/news-intelligence')
  } finally {
    loadingAgent.value = false
  }
}

function goBack() {
  router.push('/news-intelligence')
}

async function handleConfirm() {
  const ok = await formRef.value?.validateAndEmit()
  if (!ok) return
}

function onSubmit(payload: CreateNewsIntelligenceAgentDto) {
  submitLoading.value = true
  const run = isEdit.value && route.params.id
    ? newsIntelligenceApi.update(route.params.id as string, payload as UpdateNewsIntelligenceAgentDto)
    : newsIntelligenceApi.create(payload)

  run
    .then(() => {
      ElMessage.success(isEdit.value ? '保存成功' : '创建成功')
      router.push('/news-intelligence')
    })
    .catch((e: any) => ElMessage.error(e?.message ?? (isEdit.value ? '保存失败' : '创建失败')))
    .finally(() => {
      submitLoading.value = false
    })
}

async function syncRoute() {
  if (route.name === 'NewsIntelligenceEdit') {
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
.ni-form-page {
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
</style>

