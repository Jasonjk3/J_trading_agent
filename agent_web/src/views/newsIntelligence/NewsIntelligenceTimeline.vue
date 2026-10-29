<template>
  <div class="timeline-card">
    <div class="timeline-toolbar">
      <h2 class="section-title">资讯时间轴</h2>
      <div class="toolbar-right">
        <el-radio-group v-model="order" size="small" @change="onOrderChange">
          <el-radio-button label="desc">最新优先</el-radio-button>
          <el-radio-button label="asc">时间正序</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="keyword"
          placeholder="搜索标题/摘要"
          clearable
          style="width: 200px"
          @clear="resetPageAndFetch"
          @keyup.enter="resetPageAndFetch"
        />
        <el-button type="primary" size="small" @click="resetPageAndFetch">查询</el-button>
      </div>
    </div>

    <div v-loading="loading" class="timeline-body">
      <template v-if="grouped.length">
        <div v-for="group in grouped" :key="group.dayKey" class="day-group">
          <div class="day-label">{{ group.dayLabel }}</div>
          <div class="day-items">
            <div v-for="item in group.items" :key="item.id" class="timeline-item">
              <div class="time-col">
                <span class="time-main">{{ formatTime(item.sortTime) }}</span>
                <span v-if="item.eventTime" class="time-sub">发布 {{ formatTime(item.eventTime) }}</span>
                <span class="time-sub">创建 {{ formatTime(item.ingestedAt) }}</span>
              </div>
              <div class="content-col">
                <div class="item-title">{{ item.title }}</div>
                <p v-if="item.summary" class="item-summary">{{ item.summary }}</p>
                <div class="item-footer">
                  <a
                    v-if="item.sourceUrl && item.sourceName"
                    :href="item.sourceUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="source source-link"
                  >{{ item.sourceName }}</a>
                  <span v-else-if="item.sourceName" class="source">{{ item.sourceName }}</span>
                  <a
                    v-else-if="item.sourceUrl"
                    :href="item.sourceUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="source-link"
                  >打开原文</a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
      <el-empty v-else description="暂无资讯，请启动采集或稍后再试" />
    </div>

    <div v-if="total > pageSize" class="pager-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        background
        @current-change="fetchItems"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { newsIntelligenceApi } from '@/api/newsIntelligence'
import type { NewsTimelineItem } from '@/api/newsIntelligence'

const props = withDefaults(
  defineProps<{ agentId: string; reloadNonce?: number }>(),
  { reloadNonce: 0 }
)

const loading = ref(false)
const items = ref<NewsTimelineItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const order = ref<'asc' | 'desc'>('desc')
const keyword = ref('')

interface DayGroup {
  dayKey: string
  dayLabel: string
  items: NewsTimelineItem[]
}

const grouped = computed((): DayGroup[] => {
  const list = sortForDisplay(items.value)
  const map = new Map<string, NewsTimelineItem[]>()
  for (const it of list) {
    const d = new Date(it.sortTime)
    const key = d.toISOString().slice(0, 10)
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(it)
  }
  const keys = [...map.keys()].sort((a, b) => (order.value === 'desc' ? b.localeCompare(a) : a.localeCompare(b)))
  return keys.map((k) => ({
    dayKey: k,
    dayLabel: formatDayLabel(k),
    items: map.get(k)!,
  }))
})

function sortForDisplay(list: NewsTimelineItem[]): NewsTimelineItem[] {
  const copy = [...list]
  copy.sort((a, b) => {
    const ta = new Date(a.sortTime).getTime()
    const tb = new Date(b.sortTime).getTime()
    return order.value === 'desc' ? tb - ta : ta - tb
  })
  return copy
}

function formatDayLabel(isoDate: string): string {
  const d = new Date(isoDate + 'T12:00:00')
  const now = new Date()
  const today = now.toISOString().slice(0, 10)
  const y = new Date(now)
  y.setDate(y.getDate() - 1)
  const yesterday = y.toISOString().slice(0, 10)
  if (isoDate === today) return '今天'
  if (isoDate === yesterday) return '昨天'
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' })
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

async function fetchItems() {
  if (!props.agentId) return
  loading.value = true
  try {
    const res = await newsIntelligenceApi.getTimelineItems(props.agentId, {
      order: order.value,
      page: page.value,
      pageSize,
      keyword: keyword.value.trim() || undefined,
    })
    items.value = res.list || []
    total.value = res.total ?? 0
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function resetPageAndFetch() {
  page.value = 1
  fetchItems()
}

function onOrderChange() {
  resetPageAndFetch()
}

watch(
  () => props.agentId,
  (id) => {
    if (!id) {
      items.value = []
      total.value = 0
      return
    }
    page.value = 1
    keyword.value = ''
    order.value = 'desc'
    fetchItems()
  },
  { immediate: true }
)

/** 父组件在「立即采集」成功后递增，用于同 Agent 下刷新列表 */
watch(
  () => props.reloadNonce,
  (n, prev) => {
    if (!props.agentId || prev === undefined || n === prev) return
    fetchItems()
  }
)
</script>

<style scoped>
.timeline-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 24px 28px 28px;
  box-shadow: var(--shadow-card);
}

.timeline-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
}

.section-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.timeline-body {
  min-height: 200px;
}

.day-group {
  margin-bottom: 28px;
}

.day-group:last-child {
  margin-bottom: 0;
}

.day-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border);
}

.timeline-item {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--color-border-subtle, rgba(148, 163, 184, 0.12));
}

.timeline-item:last-child {
  border-bottom: none;
}

.time-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.time-main {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.time-sub {
  font-size: 12px;
  opacity: 0.85;
}

.content-col {
  min-width: 0;
}

.item-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.45;
  margin-bottom: 6px;
}

.item-summary {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--color-text-secondary);
}

.item-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
}

.source {
  color: var(--color-text-muted);
}

.source.source-link {
  color: var(--color-primary);
}

.source-link {
  color: var(--color-primary);
  text-decoration: none;
}

.source-link:hover {
  text-decoration: underline;
}

.pager-wrap {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}
</style>
