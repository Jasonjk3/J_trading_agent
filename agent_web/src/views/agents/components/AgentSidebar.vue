<template>
  <aside class="agent-sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <template v-if="!collapsed">
        <h3 class="sidebar-title">Agent 列表</h3>
        <el-button
          type="primary"
          size="small"
          :icon="Plus"
          circle
          @click="$emit('create')"
        />
      </template>
      <template v-else>
        <el-button
          type="primary"
          size="small"
          :icon="Plus"
          circle
          @click="$emit('create')"
        />
      </template>
    </div>

    <div v-if="!collapsed" class="sidebar-search">
      <el-input
        v-model="searchText"
        placeholder="搜索Agent..."
        :prefix-icon="Search"
        clearable
        size="small"
      />
    </div>

    <div v-if="!collapsed" class="sidebar-filter">
      <el-radio-group v-model="statusFilter" size="small">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="running">运行中</el-radio-button>
        <el-radio-button value="stopped">已停止</el-radio-button>
      </el-radio-group>
    </div>

    <div class="sidebar-list" v-loading="loading">
      <template v-if="filteredAgents.length > 0">
        <template v-if="!collapsed">
          <AgentCard
            v-for="agent in filteredAgents"
            :key="agent.id"
            :agent="agent"
            :is-active="activeId === agent.id"
            @select="handleSelect"
            @start="handleStart"
            @stop="handleStop"
            @edit="handleEdit"
            @delete="handleDelete"
          />
        </template>
        <template v-else>
          <el-tooltip
            v-for="agent in filteredAgents"
            :key="agent.id"
            :content="agent.name"
            placement="right"
          >
            <div
              class="collapsed-item"
              :class="{ 'is-active': activeId === agent.id, 'is-running': agent.status === 'running' }"
              @click="handleSelect(agent)"
            >
              <span class="status-dot" :class="agent.status"></span>
            </div>
          </el-tooltip>
        </template>
      </template>
      <el-empty v-else-if="!loading" description="暂无Agent" :image-size="60" />
    </div>

    <div class="sidebar-footer">
      <el-button text @click="$emit('toggle-collapse')">
        <el-icon><Expand v-if="collapsed" /><Fold v-else /></el-icon>
      </el-button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Search, Expand, Fold } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentsApi } from '@/api/agents'
import type { AgentListItem, AgentStatus } from '@/api/agents'
import AgentCard from './AgentCard.vue'

const props = defineProps<{
  collapsed: boolean
  activeId: string | null
  agents: AgentListItem[]
  loading: boolean
}>()

const emit = defineEmits<{
  'toggle-collapse': []
  'select': [agent: AgentListItem]
  'create': []
  'edit': [agent: AgentListItem]
  'refresh': []
  'deleted': [agentId: string]
}>()

const searchText = ref('')
const statusFilter = ref<AgentStatus | ''>('')

const filteredAgents = computed(() => {
  let list = [...props.agents]

  if (statusFilter.value) {
    list = list.filter((a) => a.status === statusFilter.value)
  }

  if (searchText.value.trim()) {
    const keyword = searchText.value.toLowerCase()
    list = list.filter((a) => a.name.toLowerCase().includes(keyword))
  }

  list.sort((a, b) => {
    if (a.status === 'running' && b.status !== 'running') return -1
    if (b.status === 'running' && a.status !== 'running') return 1
    const aTime = a.lastRunAt ? new Date(a.lastRunAt).getTime() : 0
    const bTime = b.lastRunAt ? new Date(b.lastRunAt).getTime() : 0
    return bTime - aTime
  })

  return list
})

function handleSelect(agent: AgentListItem) {
  emit('select', agent)
}

async function handleStart(agent: AgentListItem) {
  try {
    const res = await agentsApi.start(agent.id)
    ElMessage.success(res.message ?? '已启动')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '启动失败')
  }
}

async function handleStop(agent: AgentListItem) {
  try {
    const res = await agentsApi.stop(agent.id)
    ElMessage.success(res.message ?? '已停止')
    emit('refresh')
  } catch (e: any) {
    ElMessage.error(e?.message ?? '停止失败')
  }
}

function handleEdit(agent: AgentListItem) {
  emit('edit', agent)
}

async function handleDelete(agent: AgentListItem) {
  try {
    await ElMessageBox.confirm(`确定删除 Agent「${agent.name}」吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await agentsApi.delete(agent.id)
    ElMessage.success('已删除')
    emit('deleted', agent.id)
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message ?? '删除失败')
    }
  }
}
</script>

<style scoped>
.agent-sidebar {
  width: 280px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-card);
  border-right: 1px solid var(--color-border);
  transition: width 0.3s ease;
  overflow: hidden;
}

.agent-sidebar.collapsed {
  width: 60px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.collapsed .sidebar-header {
  justify-content: center;
}

.sidebar-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.sidebar-search {
  padding: 12px 16px 0;
  flex-shrink: 0;
}

.sidebar-filter {
  padding: 12px 16px;
  flex-shrink: 0;
}

.sidebar-filter :deep(.el-radio-button__inner) {
  padding: 5px 10px;
  font-size: 12px;
}

.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.collapsed .sidebar-list {
  padding: 8px;
  align-items: center;
}

.collapsed-item {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid var(--color-border);
}

.collapsed-item:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-active);
}

.collapsed-item.is-active {
  background: var(--color-primary-ghost);
  border-color: var(--color-primary);
}

.collapsed-item .status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.collapsed-item .status-dot.running {
  background: var(--color-success, #10B981);
  box-shadow: 0 0 6px var(--color-success, #10B981);
}

.collapsed-item .status-dot.stopped {
  background: var(--color-text-disabled, #6B7280);
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}
</style>
