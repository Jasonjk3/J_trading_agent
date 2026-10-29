<template>
  <div class="page-content">
    <div class="page-card page-card--header">
      <div class="page-header">
        <h2 class="page-title">消息面分析</h2>
        <p class="page-desc">
          进入页面即可查看已归集的资讯；通过下方切换不同采集 Agent。任务调度与配置可在「任务管理」中操作。
        </p>
      </div>
      <div class="header-actions-top">
        <el-button type="primary" :icon="Plus" @click="router.push('/news-intelligence/create')">
          创建采集 Agent
        </el-button>
      </div>
    </div>

    <div v-if="listLoading" class="loading-block" v-loading="true" />

    <template v-else-if="list.length === 0">
      <div class="page-card empty-cta">
        <el-empty description="暂无采集任务，创建后即可自动归集资讯">
          <el-button type="primary" :icon="Plus" @click="router.push('/news-intelligence/create')">
            创建采集 Agent
          </el-button>
        </el-empty>
      </div>
    </template>

    <template v-else>
      <div class="page-card agent-strip">
        <div class="agent-strip-label">当前 Agent</div>
        <div class="agent-strip-row">
          <el-select
            v-model="selectedId"
            class="agent-select"
            filterable
            placeholder="选择采集 Agent"
            @change="onAgentChange"
          >
            <el-option
              v-for="a in list"
              :key="a.id"
              :label="agentOptionLabel(a)"
              :value="a.id"
            />
          </el-select>
          <template v-if="currentAgent">
            <el-tag :type="currentAgent.status === 'running' ? 'success' : 'info'" size="small" class="status-tag">
              {{ currentAgent.status === 'running' ? '运行中' : '已停止' }}
            </el-tag>
            <span class="agent-meta-inline">
              {{ currentAgent.llmModelName || `模型 ID ${currentAgent.llmModelId}` }}
              <span class="dot">·</span>
              每 {{ currentAgent.intervalMinutes }} 分钟
              <span class="dot">·</span>
              {{ sectorLabels(currentAgent.sectors) }}
            </span>
            <div class="agent-quick-actions">
              <el-button
                type="primary"
                link
                size="small"
                :loading="collectLoadingId === currentAgent.id"
                @click="runCollectNow(currentAgent.id)"
              >
                立即采集
              </el-button>
              <el-button type="primary" link size="small" @click="openEdit(currentAgent)">编辑</el-button>
              <el-button
                type="primary"
                link
                size="small"
                :loading="startStopLoadingId === currentAgent.id"
                @click="toggleStartStop(currentAgent)"
              >
                {{ currentAgent.status === 'running' ? '停止' : '启动' }}
              </el-button>
              <router-link v-if="selectedId" :to="`/news-intelligence/${selectedId}`" class="detail-link">
                独立页打开
              </router-link>
            </div>
          </template>
        </div>
      </div>

      <NewsIntelligenceTimeline
        v-if="selectedId"
        :agent-id="selectedId"
        :reload-nonce="timelineReloadNonce"
      />

      <el-collapse v-model="manageOpen" class="manage-collapse">
        <el-collapse-item name="tasks">
          <template #title>
            <span class="collapse-title">任务管理</span>
            <span class="collapse-hint">筛选、启停与删除采集任务</span>
          </template>

          <div class="toolbar-inner">
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
                  <el-button type="primary" link class="name-btn" @click="selectAgent(row.id)">
                    {{ row.name }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column label="金融方向" min-width="200">
                <template #default="{ row }">
                  <span class="sector-tags">{{ sectorLabels(row.sectors) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="llmModelName" label="模型" min-width="120">
                <template #default="{ row }">{{ row.llmModelName || `ID ${row.llmModelId}` }}</template>
              </el-table-column>
              <el-table-column label="频率" min-width="100" align="center">
                <template #default="{ row }">{{ row.intervalMinutes }} 分钟</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" min-width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'running' ? 'success' : 'info'" size="small">
                    {{ row.status === 'running' ? '运行中' : '已停止' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="lastRunAt" label="最近采集" min-width="176" align="right">
                <template #default="{ row }">{{ formatDate(row.lastRunAt) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="330" fixed="right" align="right">
                <template #default="{ row }">
                  <el-button type="primary" link size="small" @click="selectAgent(row.id)">查看资讯</el-button>
                  <el-button
                    type="primary"
                    link
                    size="small"
                    :loading="collectLoadingId === row.id"
                    @click="runCollectNow(row.id)"
                  >
                    立即采集
                  </el-button>
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

          <div v-if="displayList.length > 0" class="table-footer">共 {{ displayList.length }} 个任务</div>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { newsIntelligenceApi } from '@/api/newsIntelligence'
import { FINANCIAL_SECTOR_OPTIONS } from '@/api/newsIntelligence'
import type { NewsIntelligenceAgentListItem, NewsIntelAgentStatus } from '@/api/newsIntelligence'
import NewsIntelligenceTimeline from './NewsIntelligenceTimeline.vue'

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const listLoading = ref(true)
const list = ref<NewsIntelligenceAgentListItem[]>([])
const selectedId = ref('')
const filter = reactive<{ status?: NewsIntelAgentStatus }>({ status: undefined })
const startStopLoadingId = ref<string | null>(null)
const collectLoadingId = ref<string | null>(null)
const timelineReloadNonce = ref(0)
const manageOpen = ref<string[]>([])

const sectorMap = Object.fromEntries(FINANCIAL_SECTOR_OPTIONS.map((o) => [o.value, o.label]))

const displayList = computed(() => {
  let l = list.value
  if (filter.status) l = l.filter((a) => a.status === filter.status)
  return l
})

const currentAgent = computed(() => list.value.find((a) => a.id === selectedId.value) ?? null)

function agentOptionLabel(a: NewsIntelligenceAgentListItem): string {
  const st = a.status === 'running' ? '运行中' : '已停止'
  return `${a.name}（${st}）`
}

function sectorLabels(sectors: string[]): string {
  if (!sectors?.length) return '-'
  return sectors.map((s) => sectorMap[s] || s).join('、')
}

function formatDate(iso?: string): string {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function applyQueryAgent() {
  if (!list.value.length) {
    selectedId.value = ''
    return
  }
  const q = route.query.agent as string | undefined
  if (q && list.value.some((a) => a.id === q)) {
    selectedId.value = q
    return
  }
  selectedId.value = list.value[0].id
  if (String(route.query.agent ?? '') !== selectedId.value) {
    router.replace({ path: route.path, query: { ...route.query, agent: selectedId.value } })
  }
}

function onAgentChange(id: string) {
  router.replace({ path: route.path, query: { ...route.query, agent: id } })
}

function selectAgent(id: string) {
  selectedId.value = id
  onAgentChange(id)
  manageOpen.value = []
}

async function fetchList(isInitial = false) {
  if (isInitial) listLoading.value = true
  else loading.value = true
  try {
    const res = await newsIntelligenceApi.getList()
    list.value = res.list || []
    applyQueryAgent()
  } catch {
    list.value = []
  } finally {
    if (isInitial) listLoading.value = false
    else loading.value = false
  }
}

function resetFilter() {
  filter.status = undefined
  fetchList()
}

function openEdit(row: NewsIntelligenceAgentListItem) {
  router.push(`/news-intelligence/${row.id}/edit`)
}

async function runCollectNow(agentId: string) {
  collectLoadingId.value = agentId
  try {
    const res = await newsIntelligenceApi.collectNow(agentId)
    ElMessage.success(
      res.message ?? (res.inserted > 0 ? `已写入 ${res.inserted} 条资讯` : '本轮未新增资讯')
    )
    await fetchList()
    if (selectedId.value === agentId) timelineReloadNonce.value += 1
  } catch (e: any) {
    ElMessage.error(e?.message ?? '采集失败')
  } finally {
    collectLoadingId.value = null
  }
}

async function toggleStartStop(row: NewsIntelligenceAgentListItem) {
  startStopLoadingId.value = row.id
  try {
    if (row.status === 'running') {
      await newsIntelligenceApi.stop(row.id)
      ElMessage.success('已停止')
    } else {
      await newsIntelligenceApi.start(row.id)
      ElMessage.success('已启动')
    }
    await fetchList()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '操作失败')
  } finally {
    startStopLoadingId.value = null
  }
}

function handleDelete(row: NewsIntelligenceAgentListItem) {
  ElMessageBox.confirm(`确定删除「${row.name}」吗？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
    .then(async () => {
      await newsIntelligenceApi.delete(row.id)
      ElMessage.success('已删除')
      const was = selectedId.value === row.id
      await fetchList()
      if (was) {
        selectedId.value = list.value[0]?.id ?? ''
        if (selectedId.value) router.replace({ path: route.path, query: { ...route.query, agent: selectedId.value } })
        else router.replace({ path: route.path, query: {} })
      }
    })
    .catch(() => {})
}

watch(
  () => route.query.agent,
  () => {
    if (!list.value.length) return
    applyQueryAgent()
  }
)

onMounted(() => {
  fetchList(true)
})
</script>

<style scoped>
.page-content {
  padding: 0 8px 24px;
  max-width: 960px;
  margin: 0 auto;
}

.page-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px 28px 28px;
  box-shadow: var(--shadow-card);
}

.page-card--header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header {
  flex: 1;
  min-width: 200px;
  margin-bottom: 0;
}

.page-title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.page-desc {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-secondary);
  max-width: 640px;
}

.header-actions-top {
  flex-shrink: 0;
}

.loading-block {
  min-height: 120px;
  margin-bottom: 16px;
  border-radius: var(--radius-lg);
}

.empty-cta {
  text-align: center;
  padding: 40px 24px;
}

.agent-strip {
  margin-bottom: 16px;
  padding-bottom: 20px;
}

.agent-strip-label {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  margin-bottom: 10px;
}

.agent-strip-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
}

.agent-select {
  min-width: 220px;
  max-width: 100%;
}

.status-tag {
  flex-shrink: 0;
}

.agent-meta-inline {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  flex: 1;
  min-width: 160px;
}

.dot {
  margin: 0 6px;
  opacity: 0.45;
}

.agent-quick-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-left: auto;
}

.detail-link {
  font-size: 13px;
  color: var(--color-text-muted);
  text-decoration: none;
}

.detail-link:hover {
  color: var(--color-primary);
}

.manage-collapse {
  margin-top: 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

.manage-collapse :deep(.el-collapse-item__header) {
  padding: 16px 20px;
  font-size: 14px;
}

.manage-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.manage-collapse :deep(.el-collapse-item__content) {
  padding: 0 20px 20px;
}

.collapse-title {
  font-weight: 600;
  color: var(--color-text-primary);
}

.collapse-hint {
  margin-left: 10px;
  font-size: 12px;
  font-weight: normal;
  color: var(--color-text-muted);
}

.toolbar-inner {
  margin-bottom: 16px;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.table-wrap {
  overflow-x: auto;
}

.name-btn {
  font-weight: 500;
  padding: 0;
}

.sector-tags {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.table-footer {
  margin-top: 16px;
  font-size: 13px;
  color: var(--color-text-muted);
}
</style>
