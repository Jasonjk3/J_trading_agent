<template>
  <div class="page-content">
    <div class="page-card">
      <div class="page-header">
        <h2 class="page-title">交易记录</h2>
        <p class="page-desc">历史订单与成交记录查询，支持筛选、分页与导出。</p>
      </div>

      <el-tabs v-model="activeTab" class="page-tabs" @tab-change="onTabChange">
        <el-tab-pane label="订单" name="orders" />
        <el-tab-pane label="成交" name="trades" />
      </el-tabs>

      <div class="toolbar">
        <el-form :model="filter" inline class="filter-form">
          <el-form-item label="时间范围">
            <el-date-picker
              v-model="filter.dateRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始"
              end-placeholder="结束"
              value-format="YYYY-MM-DDTHH:mm:ss.SSSZ"
              :shortcuts="dateShortcuts"
              style="width: 360px"
            />
          </el-form-item>
          <el-form-item label="交易所">
            <el-select v-model="filter.exchange" placeholder="全部" clearable style="width: 120px">
              <el-option label="Binance" value="binance" />
              <el-option label="OKX" value="okx" />
              <el-option label="Bybit" value="bybit" />
            </el-select>
          </el-form-item>
          <el-form-item label="交易对">
            <el-input
              v-model="filter.symbol"
              placeholder="如 BTC、ETH"
              clearable
              style="width: 140px"
              @keyup.enter="fetchList"
            />
          </el-form-item>
          <el-form-item label="方向">
            <el-select v-model="filter.side" placeholder="全部" clearable style="width: 100px">
              <el-option label="买入" value="buy" />
              <el-option label="卖出" value="sell" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="activeTab === 'orders'" label="状态">
            <el-select v-model="filter.status" placeholder="全部" clearable style="width: 110px">
              <el-option label="待成交" value="pending" />
              <el-option label="部分成交" value="partial" />
              <el-option label="已成交" value="filled" />
              <el-option label="已取消" value="cancelled" />
              <el-option label="失败" value="failed" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchList">查询</el-button>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
        <el-button :icon="Download" @click="handleExportCsv">导出 CSV</el-button>
      </div>

      <div v-show="activeTab === 'orders'" class="table-wrap">
        <el-table
          v-loading="loading"
          :data="orderList"
          class="data-table"
          header-cell-class-name="table-header"
          table-layout="auto"
        >
          <el-table-column prop="createdAt" label="时间" min-width="184" align="right">
            <template #default="{ row }">{{ formatDate(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column prop="exchange" label="交易所" min-width="108">
            <template #default="{ row }">{{ exchangeLabel(row.exchange) }}</template>
          </el-table-column>
          <el-table-column prop="symbol" label="交易对" min-width="124" />
          <el-table-column prop="side" label="方向" min-width="96" align="center">
            <template #default="{ row }">
              <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                {{ row.side === 'buy' ? '买' : '卖' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" min-width="96" align="center">
            <template #default="{ row }">{{ orderTypeLabel(row.type) }}</template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" min-width="108" align="right">
            <template #default="{ row }">{{ formatNum(row.quantity) }}</template>
          </el-table-column>
          <el-table-column prop="price" label="价格" min-width="116" align="right">
            <template #default="{ row }">{{ row.price ? formatMoney(row.price) : '-' }}</template>
          </el-table-column>
          <el-table-column prop="amount" label="成交额" min-width="124" align="right">
            <template #default="{ row }">{{ row.amount ? formatMoney(row.amount) : '-' }}</template>
          </el-table-column>
          <el-table-column prop="fee" label="手续费" min-width="104" align="right">
            <template #default="{ row }">{{ row.fee ? formatMoney(row.fee) : '-' }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" min-width="104" align="center">
            <template #default="{ row }">
              <el-tag :type="orderStatusTagType(row.status)" size="small">
                {{ orderStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-show="activeTab === 'trades'" class="table-wrap">
        <el-table
          v-loading="loading"
          :data="tradeList"
          class="data-table"
          header-cell-class-name="table-header"
          table-layout="auto"
        >
          <el-table-column prop="createdAt" label="时间" min-width="184" align="right">
            <template #default="{ row }">{{ formatDate(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column prop="exchange" label="交易所" min-width="108">
            <template #default="{ row }">{{ exchangeLabel(row.exchange) }}</template>
          </el-table-column>
          <el-table-column prop="symbol" label="交易对" min-width="124" />
          <el-table-column prop="side" label="方向" min-width="96" align="center">
            <template #default="{ row }">
              <el-tag :type="row.side === 'buy' ? 'success' : 'danger'" size="small">
                {{ row.side === 'buy' ? '买' : '卖' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" min-width="120" align="right">
            <template #default="{ row }">{{ formatNum(row.quantity) }}</template>
          </el-table-column>
          <el-table-column prop="price" label="价格" min-width="124" align="right">
            <template #default="{ row }">{{ formatMoney(row.price) }}</template>
          </el-table-column>
          <el-table-column prop="amount" label="成交额" min-width="124" align="right">
            <template #default="{ row }">{{ formatMoney(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="fee" label="手续费" min-width="104" align="right">
            <template #default="{ row }">{{ formatMoney(row.fee) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="(activeTab === 'orders' ? orderList.length : tradeList.length) > 0" class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchList"
          @current-change="fetchList"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { ordersApi } from '@/api/orders'
import type { OrderListItem, TradeListItem, ExchangeCode, OrderSide, OrderStatus } from '@/api/orders'

const activeTab = ref<'orders' | 'trades'>('orders')
const loading = ref(false)
const orderList = ref<OrderListItem[]>([])
const tradeList = ref<TradeListItem[]>([])
const filter = reactive<{
  dateRange?: [string, string]
  exchange?: ExchangeCode
  symbol?: string
  side?: OrderSide
  status?: OrderStatus
}>({})
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })

const dateShortcuts = [
  { text: '最近 24 小时', value: () => { const e = new Date(); return [new Date(e.getTime() - 86400000), e] as [Date, Date] }},
  { text: '最近 7 天', value: () => { const e = new Date(); return [new Date(e.getTime() - 7 * 86400000), e] as [Date, Date] }},
  { text: '最近 30 天', value: () => { const e = new Date(); return [new Date(e.getTime() - 30 * 86400000), e] as [Date, Date] }},
]

function exchangeLabel(code: ExchangeCode): string {
  return ({ binance: 'Binance', okx: 'OKX', bybit: 'Bybit' } as Record<ExchangeCode, string>)[code] ?? code
}
function orderTypeLabel(type: string): string {
  return ({ market: '市价', limit: '限价' } as Record<string, string>)[type] ?? type
}
function orderStatusLabel(status: OrderStatus): string {
  return ({ pending: '待成交', partial: '部分成交', filled: '已成交', cancelled: '已取消', failed: '失败' } as Record<OrderStatus, string>)[status] ?? status
}
function orderStatusTagType(status: OrderStatus): 'success' | 'warning' | 'info' | 'danger' {
  return ({ pending: 'warning', partial: 'primary', filled: 'success', cancelled: 'info', failed: 'danger' } as Record<OrderStatus, any>)[status] ?? 'info'
}
function formatDate(iso: string): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}
function formatNum(s: string): string {
  const n = parseFloat(s); if (Number.isNaN(n)) return s; return n >= 1 ? n.toFixed(4) : n.toFixed(8)
}
function formatMoney(s: string): string {
  const n = parseFloat(s); if (Number.isNaN(n)) return s
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onTabChange() { pagination.page = 1; fetchList() }

async function fetchList() {
  loading.value = true
  try {
    const [startTime, endTime] = filter.dateRange ?? []
    const params = {
      startTime: startTime || undefined, endTime: endTime || undefined,
      exchange: filter.exchange, symbol: filter.symbol?.trim() || undefined,
      side: filter.side, page: pagination.page, pageSize: pagination.pageSize,
    }
    if (activeTab.value === 'orders') {
      const res = await ordersApi.getList({ ...params, status: filter.status } as any)
      orderList.value = res.list; pagination.total = res.total
    } else {
      const res = await ordersApi.getTrades(params as any)
      tradeList.value = res.list; pagination.total = res.total
    }
  } catch (e: any) {
    ElMessage.error(e?.message ?? '加载列表失败')
  } finally { loading.value = false }
}

function resetFilter() {
  filter.dateRange = undefined; filter.exchange = undefined; filter.symbol = undefined
  filter.side = undefined; filter.status = undefined; pagination.page = 1; fetchList()
}

function handleExportCsv() {
  const BOM = '\uFEFF'; let csv = ''; let filename = ''
  if (activeTab.value === 'orders') {
    csv = [['时间','交易所','交易对','方向','类型','数量','价格','成交额','手续费','状态'].join(',')].concat(
      orderList.value.map(r => [formatDate(r.createdAt),exchangeLabel(r.exchange),r.symbol,r.side==='buy'?'买':'卖',orderTypeLabel(r.type),r.quantity,r.price??'',r.amount??'',r.fee??'',orderStatusLabel(r.status)].join(','))
    ).join('\r\n'); filename = `orders_${new Date().toISOString().slice(0,10)}.csv`
  } else {
    csv = [['时间','交易所','交易对','方向','数量','价格','成交额','手续费'].join(',')].concat(
      tradeList.value.map(r => [formatDate(r.createdAt),exchangeLabel(r.exchange),r.symbol,r.side==='buy'?'买':'卖',r.quantity,r.price,r.amount,r.fee].join(','))
    ).join('\r\n'); filename = `trades_${new Date().toISOString().slice(0,10)}.csv`
  }
  const blob = new Blob([BOM + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob); const a = document.createElement('a')
  a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
  ElMessage.success('已导出 CSV')
}

watch(activeTab, () => { pagination.total = 0; orderList.value = []; tradeList.value = [] })
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
.page-header { margin-bottom: var(--spacing-lg); }
.page-title { margin: 0 0 8px; }
.page-tabs { margin-bottom: 16px; }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.filter-form { margin-bottom: 0; }
.data-table { width: 100%; }
</style>

