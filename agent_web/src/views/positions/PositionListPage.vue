<template>
  <div class="positions-page">
    <header class="page-heading"><div><h1>持仓管理</h1><p>清晰掌握每一笔仓位</p></div><div class="heading-actions"><el-button :icon="Refresh" :loading="loading" @click="refreshAll">刷新</el-button><el-button type="primary" :icon="Plus" @click="tradingOpen = true">手动交易</el-button></div></header>
    <section class="overview" aria-label="持仓概览">
      <div><span>{{ activeTab === 'current' ? '持仓总市值' : '已实现盈亏' }}</span><strong :class="activeTab === 'history' ? pnlClass(historySummary?.totalPnl) : ''">{{ activeTab === 'current' ? money(currentSummary?.totalNotional) : signed(historySummary?.totalPnl) }} <small>USDT</small></strong></div>
      <div v-if="activeTab === 'current'"><span>未实现盈亏</span><strong :class="pnlClass(currentSummary?.totalUnrealizedPnl)">{{ signed(currentSummary?.totalUnrealizedPnl) }} <small>USDT</small></strong></div>
      <div><span>{{ activeTab === 'current' ? '当前持仓' : '历史持仓' }}</span><strong>{{ loading ? '—' : pagination.total }} <small>笔</small></strong><span class="scope">当前筛选范围</span></div>
    </section>
    <PositionChart v-if="activeTab === 'current' && currentList.length" ref="chartRef" :positions="currentList" :selected-id="selectedId" @select="selectedId = $event" />
    <el-tabs v-model="activeTab" class="position-tabs"><el-tab-pane label="当前持仓" name="current" /><el-tab-pane label="历史持仓" name="history" /></el-tabs>
    <form class="filters" @submit.prevent="search">
      <el-input v-model="filter.symbol" :prefix-icon="Search" placeholder="搜索交易对" clearable aria-label="搜索交易对" />
      <el-select v-model="filter.exchange" placeholder="全部交易所" clearable aria-label="筛选交易所" @change="search"><el-option label="OKX" value="okx" /><el-option label="Binance" value="binance" /><el-option label="Bybit" value="bybit" /></el-select>
      <el-select v-model="filter.side" placeholder="全部方向" clearable aria-label="筛选方向" @change="search"><el-option label="多头" value="long" /><el-option label="空头" value="short" /></el-select>
      <el-button native-type="submit">查询</el-button><el-button class="reset" @click="resetFilter">重置</el-button>
    </form>
    <div v-if="loadError" class="load-error" role="alert">{{ loadError }}<el-button link type="primary" @click="fetchList">重新加载</el-button></div>
    <el-alert v-if="queryWarnings.length" :title="queryWarnings.join('；')" type="warning" :closable="false" show-icon style="margin-bottom: 12px" />
    <section v-loading="loading" class="positions-table">
      <el-table v-if="activeTab === 'current'" :data="currentList" :row-class-name="rowClass" empty-text="暂无符合条件的持仓" @row-click="selectPosition">
        <el-table-column label="交易对 / 方向" min-width="200"><template #default="{ row }"><button class="symbol-button" @click.stop="selectPosition(row)">{{ row.symbol }}</button><div class="asset-meta">{{ exchangeName(row.exchange) }}<el-tag :type="row.side === 'long' ? 'success' : 'danger'" size="small">{{ row.side === 'long' ? '多头' : '空头' }}</el-tag></div></template></el-table-column>
        <el-table-column label="持仓数量" min-width="120" align="right"><template #default="{ row }">{{ quantity(row.quantity) }}</template></el-table-column>
        <el-table-column label="成本价 / 当前价" min-width="150" align="right"><template #default="{ row }"><div>{{ money(row.costPrice) }}</div><div class="secondary">{{ money(row.markPrice) }}</div></template></el-table-column>
        <el-table-column label="市值 (USDT)" min-width="140" align="right"><template #default="{ row }">{{ money(row.notional) }}</template></el-table-column>
        <el-table-column label="未实现盈亏 / 收益率" min-width="180" align="right"><template #default="{ row }"><strong :class="pnlClass(row.unrealizedPnl)">{{ signed(row.unrealizedPnl) }}</strong><div :class="pnlClass(row.unrealizedPnl)">{{ percent(row.unrealizedPnlRate) }}</div></template></el-table-column>
        <el-table-column label="操作" width="170" align="right" fixed="right"><template #default="{ row }"><div @click.stop><el-button link type="primary" :disabled="row.exchange !== 'okx'" @click="openTrade(row, 'add')">加仓</el-button><el-button size="small" :disabled="row.exchange !== 'okx'" @click="openTrade(row, 'close')">平仓</el-button></div></template></el-table-column>
      </el-table>
      <el-table v-else :data="historyList" empty-text="暂无符合条件的历史持仓">
        <el-table-column label="交易对 / 方向" min-width="190"><template #default="{ row }"><strong>{{ row.symbol }}</strong><div class="asset-meta">{{ exchangeName(row.exchange) }}<el-tag :type="row.side === 'long' ? 'success' : 'danger'" size="small">{{ row.side === 'long' ? '多头' : '空头' }}</el-tag></div></template></el-table-column>
        <el-table-column label="数量 / 杠杆" min-width="120" align="right"><template #default="{ row }">{{ quantity(row.quantity) }}<div class="secondary">{{ row.lever }}x</div></template></el-table-column>
        <el-table-column label="开仓 / 平仓均价" min-width="140" align="right"><template #default="{ row }">{{ money(row.openAvgPrice) }}<div class="secondary">{{ money(row.closeAvgPrice) }}</div></template></el-table-column>
        <el-table-column label="已实现盈亏 / 收益率" min-width="175" align="right"><template #default="{ row }"><strong :class="pnlClass(row.pnl)">{{ signed(row.pnl) }}</strong><div :class="pnlClass(row.pnl)">{{ percent(row.pnlRate) }}</div></template></el-table-column>
        <el-table-column label="开仓 / 平仓时间" min-width="170" align="right"><template #default="{ row }">{{ date(row.openTime) }}<div class="secondary">{{ date(row.closeTime) }}</div></template></el-table-column>
        <el-table-column label="平仓类型" min-width="110" align="right"><template #default="{ row }">{{ closeTypeName(row.closeType) }}</template></el-table-column>
      </el-table>
      <footer class="table-footer"><span>共 {{ pagination.total }} 笔{{ activeTab === 'current' ? '持仓' : '历史持仓' }}</span><el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.pageSize" :page-sizes="[10, 20, 50]" :total="pagination.total" layout="sizes, prev, pager, next" @size-change="search" @current-change="fetchList" /></footer>
    </section>
    <p class="page-note">盈亏随行情变化，交易前请核对仓位信息。当前手动交易仅支持 OKX。<span v-if="updatedAt">列表更新于 {{ updatedAt }}</span></p>
    <el-drawer v-model="tradingOpen" title="手动交易" size="min(1100px, 96vw)" :close-on-click-modal="false" @opened="applyPendingTrade">
      <ManualTradingPanel v-if="tradingOpen" ref="manualTradingRef" @submitted="refreshAll" />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Refresh, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { positionsApi, type PositionListItem, type PositionHistoryItem, type ExchangeCode, type PositionSide, type CloseType } from '@/api/positions'
import ManualTradingPanel from './components/ManualTradingPanel.vue'
import PositionChart from './components/PositionChart.vue'
const activeTab = ref<'current' | 'history'>('current'), loading = ref(false), loadError = ref(''), selectedId = ref(''), updatedAt = ref('')
const currentList = ref<PositionListItem[]>([]), historyList = ref<PositionHistoryItem[]>([])
const currentSummary = ref<{ totalNotional: string; totalUnrealizedPnl: string; warnings?: string[] } | null>(null)
const historySummary = ref<{ totalPnl: string; warnings?: string[] } | null>(null)
const queryWarnings = computed(() => (activeTab.value === 'current' ? currentSummary.value?.warnings : historySummary.value?.warnings) || [])
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })
const filter = reactive<{ exchange?: ExchangeCode; symbol?: string; side?: PositionSide }>({})
const chartRef = ref<{ refresh: () => Promise<void> }>()
const tradingOpen = ref(false)
const manualTradingRef = ref<{ openWithPosition: (row: PositionListItem, action: 'close' | 'add') => Promise<void> }>()
let pendingTrade: { row: PositionListItem; action: 'close' | 'add' } | undefined
let requestId = 0, disposed = false
function exchangeName(code: ExchangeCode) { return { okx: 'OKX', binance: 'Binance', bybit: 'Bybit' }[code] || code }
function money(value?: string) { if (value == null || !Number.isFinite(Number(value))) return '—'; return Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: Number(value) !== 0 && Math.abs(Number(value)) < 1 ? 8 : 2 }) }
function signed(value?: string) { return value == null ? '—' : `${Number(value) > 0 ? '+' : ''}${money(value)}` }
function quantity(value: string) { return Number(value).toLocaleString('en-US', { maximumFractionDigits: 8 }) }
function percent(value: string) { return Number.isFinite(Number(value)) ? `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(2)}%` : '—' }
function pnlClass(value?: string) { return Number(value) > 0 ? 'positive' : Number(value) < 0 ? 'negative' : '' }
function date(value?: string) { return value ? new Date(value).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) : '—' }
function closeTypeName(value?: CloseType) { return value ? ({ liquidation: '强平', partial_liquidation: '部分强平', adl: 'ADL减仓', delivery: '交割', manual: '手动平仓' }[value] || value) : '—' }
function rowClass({ row }: { row: PositionListItem }) { return row.id === selectedId.value ? 'selected-position' : '' }
function selectPosition(row: PositionListItem) { selectedId.value = row.id }
async function fetchList() {
  const id = ++requestId, tab = activeTab.value
  loading.value = true; loadError.value = ''
  try {
    const params = { ...filter, exchange: filter.exchange || undefined, side: filter.side || undefined, symbol: filter.symbol?.trim() || undefined, page: pagination.page, pageSize: pagination.pageSize }
    if (tab === 'current') {
      const result = await positionsApi.getList(params)
      if (id !== requestId || disposed) return
      currentList.value = result.list; pagination.total = result.total; currentSummary.value = result.summary ?? null
      if (!result.list.some(row => row.id === selectedId.value)) selectedId.value = result.list[0]?.id ?? ''
    } else {
      const result = await positionsApi.getHistory(params)
      if (id !== requestId || disposed) return
      historyList.value = result.list; pagination.total = result.total; historySummary.value = result.summary ?? null
    }
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch { if (id === requestId && !disposed) { loadError.value = '持仓加载失败，请重新加载'; currentList.value = []; historyList.value = []; currentSummary.value = null; historySummary.value = null; pagination.total = 0; updatedAt.value = '' } }
  finally { if (id === requestId && !disposed) loading.value = false }
}
function search() { pagination.page = 1; void fetchList() }
function resetFilter() { filter.exchange = undefined; filter.symbol = undefined; filter.side = undefined; search() }
async function refreshAll() { await fetchList(); await chartRef.value?.refresh() }
function openTrade(row: PositionListItem, action: 'close' | 'add') { if (row.exchange !== 'okx') return; pendingTrade = { row, action }; tradingOpen.value = true }
async function applyPendingTrade() { const pending = pendingTrade; pendingTrade = undefined; if (pending) { try { await manualTradingRef.value?.openWithPosition(pending.row, pending.action) } catch { ElMessage.error('交易面板加载失败，请检查账户与行情后重试') } } }
watch(activeTab, () => { currentList.value = []; historyList.value = []; currentSummary.value = null; historySummary.value = null; pagination.total = 0; search() })
watch(tradingOpen, value => { if (!value) pendingTrade = undefined })
onMounted(fetchList)
onBeforeUnmount(() => { disposed = true; requestId++ })
</script>

<style scoped>
.positions-page{padding:24px 28px;max-width:1920px;margin:auto;font-variant-numeric:tabular-nums;color:#182230}.page-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.page-heading h1{font-size:28px;font-weight:650;letter-spacing:-.8px;margin:0}.page-heading p{color:#8893a3;margin-top:4px;font-size:12px}.heading-actions{display:flex;align-items:center}.overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));background:#fff;border:1px solid #e8edf3;border-radius:12px;padding:20px 0;margin-bottom:16px}.overview>div{padding:0 26px;border-right:1px solid #edf0f5}.overview>div:last-child{border:0}.overview span{display:block;font-size:12px;color:#7b8798}.overview strong{display:block;font-size:28px;font-weight:650;letter-spacing:-.6px;margin-top:6px}.overview small{font-size:12px;font-weight:400;color:#64748b;letter-spacing:0}.overview .scope{font-size:10px;margin-top:2px}.position-tabs :deep(.el-tabs__header){margin-bottom:14px}.filters{display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}.filters>.el-input{width:280px}.filters>.el-select{width:180px}.filters .reset{margin-left:auto}.positions-table{border:1px solid #e8edf3;border-radius:12px;overflow:hidden;background:#fff}.symbol-button{font:inherit;font-size:14px;font-weight:600;color:#182230;cursor:pointer;border:0;background:transparent;padding:0;text-align:left}.symbol-button:hover{color:#2563eb}.symbol-button:focus-visible{outline:2px solid #2563eb;outline-offset:3px}.asset-meta{display:flex;gap:10px;align-items:center;margin-top:5px;font-size:11px;color:#8490a1}.secondary{margin-top:4px;color:#8490a1;font-size:12px}.positive{color:#0b9966!important}.negative{color:#dc4654!important}.positions-table :deep(.el-table td.el-table__cell){padding:12px 10px}.positions-table :deep(.el-table th.el-table__cell){background:#f8fafc;color:#788496;font-size:12px;font-weight:500;padding:10px}.positions-table :deep(.el-table .selected-position td.el-table__cell){background:#f0f5ff!important}.positions-table :deep(.el-table .selected-position td:first-child){box-shadow:inset 3px 0 #2563eb}.positions-table :deep(.el-table__row){cursor:pointer}.positions-table :deep(.el-table__inner-wrapper::before){display:none}.positions-table :deep(.el-button.is-link){color:#2563eb!important}.table-footer{padding:12px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:#8490a1;border-top:1px solid #edf0f5}.page-note{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:11px;color:#94a0af;margin-top:12px}.load-error{padding:12px 16px;background:#fff7f7;color:#bc3442;border-radius:8px;margin-bottom:12px;display:flex;gap:12px}.positions-page :deep(.el-drawer__body){overflow:auto}.positions-page :deep(.manual-panel){margin-bottom:0}.positions-page :deep(.el-tag){border:0}@media(max-width:900px){.positions-page{padding:18px}.overview>div{padding:0 16px}.overview strong{font-size:23px}.filters>.el-input{width:230px}.filters>.el-select{width:145px}}@media(max-width:600px){.page-heading{align-items:flex-start;flex-wrap:wrap}.overview{grid-template-columns:1fr;gap:16px}.overview>div{border:0}.filters>.el-input{width:100%}.filters>.el-select{flex:1}.table-footer{align-items:flex-start;flex-direction:column;overflow:auto}.page-heading h1{font-size:24px}}@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<style scoped>
.positions-page{padding:18px 28px}.page-heading{margin-bottom:12px}.page-heading h1{font-size:26px}.page-heading p{display:none}.overview{padding:14px 0;margin-bottom:14px}.overview strong{font-size:26px}.positions-table :deep(.el-table td.el-table__cell){padding:8px 10px}
@media(max-width:600px){.positions-page{padding:16px}.overview strong{font-size:23px}}
</style>
