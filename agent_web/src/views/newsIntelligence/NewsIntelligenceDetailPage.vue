<template>
  <div v-loading="loadingAgent" class="ni-detail">
    <header class="page-header">
      <div class="header-row">
        <el-button class="back-btn" text @click="router.push('/news-intelligence')">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
      </div>
      <div v-if="agent" class="header-main">
        <div class="title-row">
          <h1 class="page-title">{{ agent.name }}</h1>
          <el-tag :type="agent.status === 'running' ? 'success' : 'info'" size="small">
            {{ agent.status === 'running' ? '运行中' : '已停止' }}
          </el-tag>
        </div>
        <p class="page-meta">
          <span>模型：{{ agent.llmModelName || `ID ${agent.llmModelId}` }}</span>
          <span class="sep">·</span>
          <span>每 {{ agent.intervalMinutes }} 分钟采集</span>
          <span class="sep">·</span>
          <span>方向：{{ sectorLabels(agent.sectors) }}</span>
        </p>
        <div class="header-actions">
          <el-button type="primary" size="small" @click="router.push(`/news-intelligence/${id}/edit`)">
            编辑配置
          </el-button>
          <el-button size="small" :loading="collectLoading" @click="runCollectNow">
            立即采集
          </el-button>
          <el-button
            size="small"
            :loading="toggleLoading"
            @click="toggleRun"
          >
            {{ agent.status === 'running' ? '停止采集' : '启动采集' }}
          </el-button>
        </div>
      </div>
    </header>

    <NewsIntelligenceTimeline v-if="id" :agent-id="id" :reload-nonce="timelineReloadNonce" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { newsIntelligenceApi } from '@/api/newsIntelligence'
import { FINANCIAL_SECTOR_OPTIONS } from '@/api/newsIntelligence'
import type { NewsIntelligenceAgentListItem } from '@/api/newsIntelligence'
import NewsIntelligenceTimeline from './NewsIntelligenceTimeline.vue'

const route = useRoute()
const router = useRouter()

const id = computed(() => route.params.id as string)

const agent = ref<NewsIntelligenceAgentListItem | null>(null)
const loadingAgent = ref(false)
const toggleLoading = ref(false)
const collectLoading = ref(false)
const timelineReloadNonce = ref(0)

const sectorMap = Object.fromEntries(FINANCIAL_SECTOR_OPTIONS.map((o) => [o.value, o.label]))

function sectorLabels(sectors: string[]): string {
  if (!sectors?.length) return '-'
  return sectors.map((s) => sectorMap[s] || s).join('、')
}

async function loadAgent() {
  loadingAgent.value = true
  try {
    agent.value = await newsIntelligenceApi.getById(id.value)
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载失败')
    router.replace('/news-intelligence')
  } finally {
    loadingAgent.value = false
  }
}

async function runCollectNow() {
  if (!id.value) return
  collectLoading.value = true
  try {
    const res = await newsIntelligenceApi.collectNow(id.value)
    ElMessage.success(
      res.message ?? (res.inserted > 0 ? `已写入 ${res.inserted} 条资讯` : '本轮未新增资讯')
    )
    await loadAgent()
    timelineReloadNonce.value += 1
  } catch (e: any) {
    ElMessage.error(e?.message ?? '采集失败')
  } finally {
    collectLoading.value = false
  }
}

async function toggleRun() {
  if (!agent.value) return
  toggleLoading.value = true
  try {
    if (agent.value.status === 'running') {
      await newsIntelligenceApi.stop(agent.value.id)
      ElMessage.success('已停止')
    } else {
      await newsIntelligenceApi.start(agent.value.id)
      ElMessage.success('已启动')
    }
    await loadAgent()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '操作失败')
  } finally {
    toggleLoading.value = false
  }
}

onMounted(() => {
  loadAgent()
})

watch(
  () => route.params.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      loadAgent()
    }
  }
)
</script>

<style scoped>
.ni-detail {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 8px 32px;
}

.page-header {
  margin-bottom: 24px;
}

.back-btn {
  padding-left: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.back-btn:hover {
  color: var(--color-primary);
}

.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.page-meta {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.sep {
  margin: 0 6px;
  opacity: 0.5;
}

.header-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
