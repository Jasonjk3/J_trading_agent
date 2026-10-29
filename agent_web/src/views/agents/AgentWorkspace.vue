<template>
  <div class="agent-workspace">
    <AgentSidebar
      :collapsed="sidebarCollapsed"
      :active-id="activeAgentId"
      :agents="agents"
      :loading="loadingAgents"
      @toggle-collapse="sidebarCollapsed = !sidebarCollapsed"
      @select="handleSelectAgent"
      @create="openCreateDialog"
      @edit="openEditDialog"
      @refresh="fetchAgents"
      @deleted="handleAgentDeleted"
    />

    <div class="workspace-main">
      <template v-if="agents.length === 0 && !loadingAgents">
        <div class="empty-workspace">
          <div class="empty-content">
            <div class="empty-icon">🤖</div>
            <h2 class="empty-title">您还没有创建任何交易Agent</h2>
            <p class="empty-desc">
              Agent可以7x24小时自动分析行情并执行交易<br>
              基于AI大模型，实现智能化交易决策
            </p>
            <el-button type="primary" size="large" @click="openCreateDialog">
              + 创建第一个Agent
            </el-button>
            <p class="empty-tip">
              💡 建议先配置交易所API →
              <router-link to="/exchange-accounts" class="tip-link">去配置</router-link>
            </p>
          </div>
        </div>
      </template>

      <template v-else>
        <AgentMonitor
          ref="monitorRef"
          :agent-id="activeAgentId"
          @open-strategy="openStrategyDialog"
          @refresh="fetchAgents"
        />
      </template>
    </div>

    <AgentFormDialog
      v-model="formDialogVisible"
      :edit-id="editAgentId"
      @success="handleFormSuccess"
    />

    <StrategyDialog
      v-model="strategyDialogVisible"
      :agent-id="activeAgentId"
      @success="handleStrategySuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { agentsApi } from '@/api/agents'
import type { AgentListItem } from '@/api/agents'
import AgentSidebar from './components/AgentSidebar.vue'
import AgentMonitor from './components/AgentMonitor.vue'
import AgentFormDialog from './components/AgentFormDialog.vue'
import StrategyDialog from './components/StrategyDialog.vue'

const route = useRoute()
const router = useRouter()

const sidebarCollapsed = ref(false)
const loadingAgents = ref(false)
const agents = ref<AgentListItem[]>([])
const activeAgentId = ref<string | null>(null)
const monitorRef = ref<InstanceType<typeof AgentMonitor>>()

const formDialogVisible = ref(false)
const editAgentId = ref<string | null>(null)

const strategyDialogVisible = ref(false)

async function fetchAgents() {
  loadingAgents.value = true
  try {
    const res = await agentsApi.getList()
    agents.value = res.list || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载列表失败')
    agents.value = []
  } finally {
    loadingAgents.value = false
  }
}

function getDefaultAgentId(): string | null {
  if (agents.value.length === 0) return null

  const sorted = [...agents.value].sort((a, b) => {
    if (a.status === 'running' && b.status !== 'running') return -1
    if (b.status === 'running' && a.status !== 'running') return 1
    const aTime = a.lastRunAt ? new Date(a.lastRunAt).getTime() : 0
    const bTime = b.lastRunAt ? new Date(b.lastRunAt).getTime() : 0
    return bTime - aTime
  })

  return sorted[0]?.id ?? null
}

function handleSelectAgent(agent: AgentListItem) {
  activeAgentId.value = agent.id
  router.replace({ path: `/agents/${agent.id}` })
}

function openCreateDialog() {
  editAgentId.value = null
  formDialogVisible.value = true
}

function openEditDialog(agent: AgentListItem) {
  editAgentId.value = agent.id
  formDialogVisible.value = true
}

function openStrategyDialog() {
  strategyDialogVisible.value = true
}

async function handleFormSuccess() {
  await fetchAgents()
  if (!activeAgentId.value && agents.value.length > 0) {
    const defaultId = getDefaultAgentId()
    if (defaultId) {
      activeAgentId.value = defaultId
      router.replace({ path: `/agents/${defaultId}` })
    }
  }
  monitorRef.value?.refresh()
}

async function handleAgentDeleted(agentId: string) {
  await fetchAgents()

  if (activeAgentId.value !== agentId && agents.value.some((agent) => agent.id === activeAgentId.value)) {
    return
  }

  const defaultId = getDefaultAgentId()
  activeAgentId.value = defaultId
  if (defaultId) {
    router.replace({ path: `/agents/${defaultId}` })
  } else {
    router.replace({ path: '/agents' })
  }
}

async function handleStrategySuccess() {
  monitorRef.value?.refresh()
}

function syncRouteToActive() {
  const idFromRoute = route.params.id as string | undefined
  if (idFromRoute) {
    activeAgentId.value = idFromRoute
  } else if (agents.value.length > 0) {
    const defaultId = getDefaultAgentId()
    if (defaultId) {
      activeAgentId.value = defaultId
      router.replace({ path: `/agents/${defaultId}` })
    }
  }
}

watch(
  () => route.params.id,
  (id) => {
    if (id) {
      activeAgentId.value = id as string
    }
  }
)

onMounted(async () => {
  await fetchAgents()
  await nextTick()
  syncRouteToActive()
})
</script>

<style scoped>
.agent-workspace {
  display: flex;
  height: calc(100vh - 70px);
  background: var(--color-bg-base);
  overflow: hidden;
}

.workspace-main {
  flex: 1;
  min-width: 0;
  padding: 16px;
  overflow: auto;
}

.empty-workspace {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
}

.empty-content {
  text-align: center;
  max-width: 400px;
  padding: 40px;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 24px;
}

.empty-title {
  margin: 0 0 12px;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.empty-desc {
  margin: 0 0 24px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.empty-tip {
  margin: 20px 0 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

.tip-link {
  color: var(--color-primary);
  text-decoration: none;
}

.tip-link:hover {
  text-decoration: underline;
}
</style>
