<template>
  <div class="page-content">
    <div class="page-card">
      <div class="page-header">
        <h2 class="page-title">Agent 交易</h2>
        <p class="page-desc">配置与监控交易 Agent，支持启停与运行监控（收益曲线、持仓/委托、操作记录与思维链）。</p>
      </div>

      <div class="toolbar">
        <el-form :model="filter" inline class="filter-form">
          <el-form-item label="状态">
            <el-select v-model="filter.status" placeholder="全部" clearable style="width: 110px">
              <el-option label="运行中" value="running" />
              <el-option label="已停止" value="stopped" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchList">查询</el-button>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
        <el-button type="primary" :icon="Plus" @click="openAdd">添加 Agent</el-button>
      </div>

      <div class="table-wrap">
        <el-table
          v-loading="loading"
          :data="displayList"
          class="data-table"
          header-cell-class-name="table-header"
          table-layout="auto"
        >
          <el-table-column prop="name" label="名称" min-width="160">
            <template #default="{ row }">
              <router-link :to="`/agents/${row.id}`" class="agent-name-link">
                {{ row.name }}
              </router-link>
            </template>
          </el-table-column>
          <el-table-column prop="exchange" label="交易所" min-width="108">
            <template #default="{ row }">{{ exchangeLabel(row.exchange) }}</template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="120">
            <template #default="{ row }">{{ row.remark || '-' }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" min-width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'running' ? 'success' : 'info'" size="small">
                {{ row.status === 'running' ? '运行中' : '已停止' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="lastRunAt" label="最近运行" min-width="176" align="right">
            <template #default="{ row }">{{ formatDate(row.lastRunAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="288" fixed="right" align="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="goMonitor(row)">运行监控</el-button>
              <el-button
                type="primary"
                link
                size="small"
                :loading="startStopLoadingId === row.id"
                @click="toggleStartStop(row)"
              >
                {{ row.status === 'running' ? '停止' : '启动' }}
              </el-button>
              <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
              <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="displayList.length > 0" class="table-footer">
        共 {{ displayList.length }} 个 Agent
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { agentsApi } from '@/api/agents'
import type { AgentListItem, AgentStatus } from '@/api/agents'
import type { ExchangeCode } from '@/api/agents'

const router = useRouter()
const loading = ref(false)
const list = ref<AgentListItem[]>([])
const filter = reactive<{ status?: AgentStatus }>({ status: undefined })

const startStopLoadingId = ref<string | null>(null)

const displayList = computed(() => {
  let l = list.value
  if (filter.status) l = l.filter((a) => a.status === filter.status)
  return l
})

function exchangeLabel(code?: ExchangeCode): string {
  if (!code) return '-'
  const map: Record<ExchangeCode, string> = { binance: 'Binance', okx: 'OKX', bybit: 'Bybit' }
  return map[code] ?? code
}

function formatDate(iso?: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

async function fetchList() {
  loading.value = true
  try {
    const res = await agentsApi.getList()
    list.value = res.list
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载列表失败')
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  filter.status = undefined
  fetchList()
}

function goMonitor(row: AgentListItem) {
  router.push(`/agents/${row.id}`)
}

function openAdd() {
  router.push('/agents/create')
}

function openEdit(row: AgentListItem) {
  router.push(`/agents/${row.id}/edit`)
}

async function toggleStartStop(row: AgentListItem) {
  startStopLoadingId.value = row.id
  try {
    const api = row.status === 'running' ? agentsApi.stop : agentsApi.start
    const res = await api(row.id)
    ElMessage.success(res.message ?? (row.status === 'running' ? '已停止' : '已启动'))
    row.status = row.status === 'running' ? 'stopped' : 'running'
    row.lastRunAt = new Date().toISOString()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '操作失败')
  } finally {
    startStopLoadingId.value = null
  }
}

function handleDelete(row: AgentListItem) {
  ElMessageBox.confirm(`确定删除 Agent「${row.name}」吗？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await agentsApi.delete(row.id)
      ElMessage.success('已删除')
      fetchList()
    })
    .catch(() => {})
}

onMounted(() => fetchList())
</script>

<style scoped>
.page-card {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}
.page-header {
  margin-bottom: var(--spacing-lg);
}
.page-title {
  margin: 0 0 8px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.filter-form {
  margin-bottom: 0;
}
.data-table {
  width: 100%;
}
.agent-name-link {
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 500;
}
.agent-name-link:hover {
  text-decoration: underline;
  color: var(--color-primary-light);
}
</style>

