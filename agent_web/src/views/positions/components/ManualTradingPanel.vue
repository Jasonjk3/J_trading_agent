<template>
  <div ref="panelRef" class="manual-panel">
    <div class="panel-header">
      <div>
        <h3 class="panel-title">实盘交易</h3>
        <p class="panel-desc">参考 OKX 交易面板，支持现货与永续合约快速委托。</p>
      </div>
      <div class="panel-controls">
        <el-select v-model="selectedAccountId" placeholder="选择 OKX 账户" style="width: 240px">
          <el-option
            v-for="account in accounts"
            :key="account.id"
            :label="accountLabel(account)"
            :value="account.id"
          />
        </el-select>
        <el-radio-group v-model="instType" size="small">
          <el-radio-button label="SPOT">现货</el-radio-button>
          <el-radio-button label="SWAP">合约</el-radio-button>
        </el-radio-group>
        <el-button :loading="refreshing" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <div v-if="!selectedAccountId" class="panel-empty">
      <el-empty description="请先选择一个已校验的 OKX 账户" />
    </div>

    <template v-else>
      <div class="trade-toolbar">
        <el-select
          v-model="form.instId"
          filterable
          remote
          reserve-keyword
          clearable
          placeholder="搜索交易对，如 BTC-USDT / BTC-USDT-SWAP"
          :remote-method="searchInstruments"
          :loading="searchingInstruments"
          class="symbol-select"
        >
          <el-option
            v-for="item in instruments"
            :key="item.instId"
            :label="item.instId"
            :value="item.instId"
          >
            <div class="symbol-option">
              <span>{{ item.instId }}</span>
              <span class="symbol-meta">{{ item.baseCcy || '-' }}/{{ item.quoteCcy || '-' }}</span>
            </div>
          </el-option>
        </el-select>
        <div v-if="selectedInstrument" class="toolbar-meta">
          <span>最小 {{ selectedInstrument.minSz || '-' }}</span>
          <span>精度 {{ selectedInstrument.lotSz || '-' }}</span>
        </div>
        <span v-if="isReadonlyAccount" class="readonly-tag">只读账户</span>
      </div>

      <div class="compact-grid">
        <div class="compact-card quote-panel">
          <div class="compact-card-head">
            <div>
              <div class="card-title">行情</div>
              <div class="card-subtitle">{{ form.instId || '未选择交易对' }}</div>
            </div>
            <div v-if="snapshot" class="quote-main" :class="priceClass(snapshot.ticker.change24h)">
              <strong>{{ formatMoney(snapshot.ticker.last) }}</strong>
              <span>{{ formatPercent(snapshot.ticker.change24h) }}</span>
            </div>
          </div>

          <el-skeleton v-if="!snapshot" :rows="4" animated :loading="loadingSnapshot" />

          <template v-else>
            <div class="quote-stats">
              <div class="quote-stat">
                <span>买一</span>
                <strong>{{ formatMoney(snapshot.ticker.bidPx) }}</strong>
              </div>
              <div class="quote-stat">
                <span>卖一</span>
                <strong>{{ formatMoney(snapshot.ticker.askPx) }}</strong>
              </div>
              <div class="quote-stat">
                <span>24H 高</span>
                <strong>{{ formatMoney(snapshot.ticker.high24h) }}</strong>
              </div>
              <div class="quote-stat">
                <span>24H 低</span>
                <strong>{{ formatMoney(snapshot.ticker.low24h) }}</strong>
              </div>
            </div>

            <div class="book-board">
              <div class="book-column">
                <div class="book-column-head sell-text">卖盘</div>
                <div v-for="(item, idx) in asks" :key="`ask-${idx}`" class="book-line">
                  <span class="sell-text">{{ formatMoney(item.price) }}</span>
                  <span>{{ formatNum(item.size) }}</span>
                </div>
              </div>
              <div class="book-column">
                <div class="book-column-head buy-text">买盘</div>
                <div v-for="(item, idx) in bids" :key="`bid-${idx}`" class="book-line">
                  <span class="buy-text">{{ formatMoney(item.price) }}</span>
                  <span>{{ formatNum(item.size) }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="compact-card ticket-panel">
          <div class="compact-card-head">
            <div>
              <div class="card-title">委托下单</div>
              <div class="card-subtitle">{{ instType === 'SPOT' ? '现货交易' : '永续合约' }}</div>
            </div>
            <div class="action-badge">{{ activeActionLabel }}</div>
          </div>

          <div class="action-buttons compact-actions">
            <el-button
              v-for="item in actionOptions"
              :key="item.value"
              :type="form.tradeAction === item.value ? item.type : 'default'"
              :plain="form.tradeAction !== item.value"
              size="small"
              @click="form.tradeAction = item.value"
            >
              {{ item.label }}
            </el-button>
          </div>

          <div class="ticket-grid">
            <div class="ticket-field">
              <label>订单类型</label>
              <el-radio-group v-model="form.ordType" size="small">
                <el-radio-button label="limit">限价</el-radio-button>
                <el-radio-button label="market">市价</el-radio-button>
              </el-radio-group>
            </div>

            <div class="ticket-field">
              <label>交易模式</label>
              <el-radio-group v-model="form.tdMode" size="small">
                <el-radio-button v-for="item in modeOptions" :key="item.value" :label="item.value">
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </div>

            <div v-if="instType === 'SWAP'" class="ticket-field">
              <label>杠杆倍数</label>
              <el-input v-model="form.leverage" size="small" placeholder="如 10" />
            </div>

            <div v-if="instType === 'SPOT' && form.ordType === 'market'" class="ticket-field">
              <label>数量单位</label>
              <el-radio-group v-model="form.tgtCcy" size="small">
                <el-radio-button label="base_ccy">按币</el-radio-button>
                <el-radio-button label="quote_ccy">按金额</el-radio-button>
              </el-radio-group>
            </div>

            <div v-if="form.ordType === 'limit'" class="ticket-field ticket-field-span">
              <label>委托价格</label>
              <el-input v-model="form.px" size="small" placeholder="请输入价格">
                <template #append>
                  <el-button @click="fillPriceFromTicker">现价</el-button>
                </template>
              </el-input>
            </div>

            <div class="ticket-field ticket-field-span">
              <label>{{ sizeLabel }}</label>
              <el-input v-model="form.sz" size="small" placeholder="请输入数量" />
            </div>
          </div>

          <div class="submit-row">
            <div class="submit-info">
              <span>动作：{{ activeActionLabel }}</span>
              <span v-if="snapshot">最新价 {{ formatMoney(snapshot.ticker.last) }}</span>
            </div>
            <el-button
              class="submit-button"
              :type="submitButtonType"
              :loading="submitting"
              :disabled="!canSubmit"
              @click="submitOrder"
            >
              {{ activeActionLabel }}
            </el-button>
          </div>
        </div>

        <div class="compact-card side-panel">
          <div class="compact-card-head">
            <div>
              <div class="card-title">账户侧栏</div>
              <div class="card-subtitle">挂单 / 余额 / 持仓</div>
            </div>
          </div>

          <el-tabs v-model="sideTab" class="side-tabs">
            <el-tab-pane :label="`挂单 ${pendingOrders.length}`" name="orders">
              <div v-loading="loadingPending">
                <el-table :data="pendingOrders" size="small" max-height="208" empty-text="暂无未成交委托">
                  <el-table-column prop="side" label="方向" width="58">
                    <template #default="{ row }">
                      <span :class="row.side === 'buy' ? 'buy-text' : 'sell-text'">{{ row.side === 'buy' ? '买' : '卖' }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="px" label="价格" min-width="80">
                    <template #default="{ row }">{{ row.px ? formatMoney(row.px) : '市价' }}</template>
                  </el-table-column>
                  <el-table-column prop="sz" label="数量" min-width="74">
                    <template #default="{ row }">{{ formatNum(row.sz) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="64" align="right">
                    <template #default="{ row }">
                      <el-button link type="danger" :disabled="isReadonlyAccount" @click="cancelOrder(row)">撤单</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="`余额 ${overview.balances.length}`" name="balances">
              <div v-loading="loadingOverview">
                <el-table :data="overview.balances" size="small" max-height="208" empty-text="暂无余额数据">
                  <el-table-column prop="ccy" label="币种" width="64" />
                  <el-table-column prop="availBal" label="可用" min-width="88">
                    <template #default="{ row }">{{ formatNum(row.availBal) }}</template>
                  </el-table-column>
                  <el-table-column prop="eqUsd" label="USDT" min-width="92">
                    <template #default="{ row }">{{ formatMoney(row.eqUsd) }}</template>
                  </el-table-column>
                </el-table>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="`持仓 ${overview.positions.length}`" name="positions">
              <div v-loading="loadingOverview">
                <el-table :data="overview.positions" size="small" max-height="208" empty-text="暂无持仓">
                  <el-table-column prop="instId" label="产品" min-width="120" />
                  <el-table-column prop="posSide" label="方向" width="62" />
                  <el-table-column prop="pos" label="数量" min-width="74">
                    <template #default="{ row }">{{ formatNum(row.pos) }}</template>
                  </el-table-column>
                  <el-table-column prop="upl" label="盈亏" min-width="90">
                    <template #default="{ row }">
                      <span :class="priceClass(row.upl)">{{ formatSignedMoney(row.upl) }}</span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { exchangeAccountsApi, type ExchangeAccountListItem } from '@/api/exchangeAccounts'
import { manualTradingApi, type InstrumentType, type PendingOrderItem, type PlaceManualOrderDto, type TradeAction, type TradingAccountOverview, type TradingInstrumentItem, type TradingSnapshot } from '@/api/manualTrading'

interface PositionBridgeRow {
  id: string
  symbol: string
  side: string
}

const emit = defineEmits<{
  (e: 'submitted'): void
}>()

const panelRef = ref<HTMLElement>()
const accounts = ref<ExchangeAccountListItem[]>([])
const selectedAccountId = ref('')
const instType = ref<InstrumentType>('SWAP')
const instruments = ref<TradingInstrumentItem[]>([])
const searchingInstruments = ref(false)
const loadingSnapshot = ref(false)
const loadingOverview = ref(false)
const loadingPending = ref(false)
const refreshing = ref(false)
const submitting = ref(false)
const syncingFromPosition = ref(false)
const sideTab = ref<'orders' | 'balances' | 'positions'>('orders')
const snapshot = ref<TradingSnapshot | null>(null)
const overview = ref<TradingAccountOverview>({ balances: [], positions: [] })
const pendingOrders = ref<PendingOrderItem[]>([])

const form = reactive<PlaceManualOrderDto>({
  accountId: '',
  instId: '',
  instType: 'SWAP',
  tradeAction: 'open_long',
  ordType: 'limit',
  sz: '',
  px: '',
  tdMode: 'cross',
  leverage: '10',
})

const selectedInstrument = computed(() => instruments.value.find((item) => item.instId === form.instId))
const bids = computed(() => snapshot.value?.bids ?? [])
const asks = computed(() => snapshot.value?.asks ?? [])
const isReadonlyAccount = computed(() => accounts.value.find((item) => item.id === selectedAccountId.value)?.readOnly === true)
const canSubmit = computed(() => {
  if (isReadonlyAccount.value) return false
  if (!form.accountId || !form.instId || !form.sz) return false
  if (form.ordType === 'limit' && !form.px) return false
  return true
})

const actionOptions = computed(() => {
  if (instType.value === 'SPOT') {
    return [
      { value: 'buy' as TradeAction, label: '买入', type: 'success' as const },
      { value: 'sell' as TradeAction, label: '卖出', type: 'danger' as const },
    ]
  }

  return [
    { value: 'open_long' as TradeAction, label: '开多', type: 'success' as const },
    { value: 'open_short' as TradeAction, label: '开空', type: 'danger' as const },
    { value: 'close_long' as TradeAction, label: '平多', type: 'warning' as const },
    { value: 'close_short' as TradeAction, label: '平空', type: 'warning' as const },
  ]
})

const modeOptions = computed(() => {
  return instType.value === 'SPOT'
    ? [{ value: 'cash', label: '现货' }]
    : [
        { value: 'cross', label: '全仓' },
        { value: 'isolated', label: '逐仓' },
      ]
})

const activeActionLabel = computed(() => actionOptions.value.find((item) => item.value === form.tradeAction)?.label ?? '提交委托')
const submitButtonType = computed(() => {
  if (['sell', 'open_short'].includes(form.tradeAction)) return 'danger'
  if (['close_long', 'close_short'].includes(form.tradeAction)) return 'warning'
  return 'success'
})
const sizeLabel = computed(() => {
  if (instType.value === 'SPOT' && form.ordType === 'market' && form.tgtCcy === 'quote_ccy') return '委托金额'
  return '委托数量'
})

function accountLabel(account: ExchangeAccountListItem) {
  const suffix = account.readOnly ? '（只读）' : ''
  return `${account.remark || account.apiKeyMasked || account.id}${suffix}`
}

function applyDefaultsByInstType() {
  form.instType = instType.value
  form.tradeAction = instType.value === 'SPOT' ? 'buy' : 'open_long'
  form.tdMode = instType.value === 'SPOT' ? 'cash' : 'cross'
  form.tgtCcy = instType.value === 'SPOT' ? 'base_ccy' : undefined
  form.leverage = instType.value === 'SWAP' ? (form.leverage || '10') : undefined
  form.sz = ''
  form.px = ''
}

async function loadAccounts() {
  const res = await exchangeAccountsApi.getList({ exchange: 'okx', enabled: true, bindStatus: 'success' })
  accounts.value = (res.list || []).filter((item) => item.exchange === 'okx' && item.enabled && item.bindStatus === 'success')
  if (!selectedAccountId.value && accounts.value.length > 0) {
    selectedAccountId.value = accounts.value[0].id
  }
}

async function searchInstruments(keyword = '') {
  if (!selectedAccountId.value) return
  searchingInstruments.value = true
  try {
    const res = await manualTradingApi.searchInstruments({
      accountId: selectedAccountId.value,
      instType: instType.value,
      keyword: keyword.trim() || undefined,
    })
    instruments.value = res.list || []
  } finally {
    searchingInstruments.value = false
  }
}

async function refreshOverview() {
  if (!selectedAccountId.value) return
  loadingOverview.value = true
  try {
    overview.value = await manualTradingApi.getOverview({
      accountId: selectedAccountId.value,
      instType: instType.value,
    })
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取账户概览失败')
  } finally {
    loadingOverview.value = false
  }
}

async function refreshSnapshot() {
  if (!selectedAccountId.value || !form.instId) {
    snapshot.value = null
    return
  }
  loadingSnapshot.value = true
  try {
    snapshot.value = await manualTradingApi.getSnapshot({
      accountId: selectedAccountId.value,
      instId: form.instId,
    })
    if (form.ordType === 'limit' && !form.px) {
      form.px = snapshot.value.ticker.last
    }
  } catch (e: any) {
    snapshot.value = null
    ElMessage.error(e?.message ?? '获取行情失败')
  } finally {
    loadingSnapshot.value = false
  }
}

async function refreshPendingOrders() {
  if (!selectedAccountId.value || !form.instId) {
    pendingOrders.value = []
    return
  }
  loadingPending.value = true
  try {
    const res = await manualTradingApi.getPendingOrders({
      accountId: selectedAccountId.value,
      instType: instType.value,
      instId: form.instId,
      limit: 20,
    })
    pendingOrders.value = res.list || []
  } catch (e: any) {
    pendingOrders.value = []
    ElMessage.error(e?.message ?? '获取未成交委托失败')
  } finally {
    loadingPending.value = false
  }
}

async function refreshAll() {
  if (!selectedAccountId.value) return
  refreshing.value = true
  try {
    await Promise.all([refreshOverview(), refreshSnapshot(), refreshPendingOrders()])
  } finally {
    refreshing.value = false
  }
}

function fillPriceFromTicker() {
  if (snapshot.value?.ticker.last) {
    form.px = snapshot.value.ticker.last
  }
}

async function submitOrder() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const result = await manualTradingApi.placeOrder({
      ...form,
      accountId: selectedAccountId.value,
      instType: instType.value,
      px: form.ordType === 'limit' ? form.px : undefined,
      leverage: instType.value === 'SWAP' ? form.leverage : undefined,
      tgtCcy: instType.value === 'SPOT' && form.ordType === 'market' ? form.tgtCcy : undefined,
      tdMode: form.tdMode,
    })
    ElMessage.success(result?.sMsg || '委托已提交')
    form.sz = ''
    emit('submitted')
    await Promise.all([refreshOverview(), refreshPendingOrders(), refreshSnapshot()])
  } catch (e: any) {
    ElMessage.error(e?.message ?? '委托提交失败')
  } finally {
    submitting.value = false
  }
}

async function cancelOrder(row: PendingOrderItem) {
  try {
    await ElMessageBox.confirm(`确认撤销 ${row.instId} 的该笔委托吗？`, '撤单确认', { type: 'warning' })
    await manualTradingApi.cancelOrder({
      accountId: selectedAccountId.value,
      instId: row.instId,
      ordId: row.ordId,
    })
    ElMessage.success('撤单成功')
    emit('submitted')
    await Promise.all([refreshPendingOrders(), refreshOverview()])
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error(e?.message ?? '撤单失败')
  }
}

function normalizeInstType(symbol: string): InstrumentType {
  return symbol.endsWith('-SWAP') ? 'SWAP' : 'SPOT'
}

function ensureInstrument(instId: string, type: InstrumentType) {
  if (!instId) return
  if (!instruments.value.some((item) => item.instId === instId)) {
    const parts = instId.split('-')
    instruments.value.unshift({
      instId,
      instType: type,
      baseCcy: parts[0],
      quoteCcy: parts[1],
    })
  }
}

async function openWithPosition(row: PositionBridgeRow, action: 'close' | 'add') {
  const accountId = row.id.split('_')[0]
  const accountChanged = !!accountId && selectedAccountId.value !== accountId
  syncingFromPosition.value = accountChanged
  if (accountChanged) selectedAccountId.value = accountId

  const nextInstType = normalizeInstType(row.symbol)
  if (instType.value !== nextInstType) {
    instType.value = nextInstType
  } else {
    applyDefaultsByInstType()
  }

  form.instId = row.symbol
  ensureInstrument(row.symbol, nextInstType)

  if (nextInstType === 'SPOT') {
    form.tradeAction = action === 'close' ? 'sell' : 'buy'
  } else {
    if (action === 'close') {
      form.tradeAction = row.side === 'short' ? 'close_short' : 'close_long'
    } else {
      form.tradeAction = row.side === 'short' ? 'open_short' : 'open_long'
    }
  }

  await refreshAll()
  panelRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function formatMoney(value?: string) {
  const n = Number(value)
  if (!Number.isFinite(n)) return value || '-'
  if (Math.abs(n) >= 1000) return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (Math.abs(n) >= 1) return n.toFixed(2)
  return n.toFixed(6)
}

function formatNum(value?: string) {
  const n = Number(value)
  if (!Number.isFinite(n)) return value || '-'
  if (Math.abs(n) >= 1) return n.toFixed(4)
  return n.toFixed(8)
}

function formatPercent(value?: string) {
  const n = Number(value)
  if (!Number.isFinite(n)) return value || '-'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function formatSignedMoney(value?: string) {
  const n = Number(value)
  if (!Number.isFinite(n)) return value || '-'
  const abs = Math.abs(n)
  const formatted = abs >= 1000
    ? abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : abs.toFixed(2)
  return `${n >= 0 ? '+' : '-'}${formatted}`
}

function priceClass(value?: string) {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  if (n > 0) return 'buy-text'
  if (n < 0) return 'sell-text'
  return ''
}

watch(selectedAccountId, async (value) => {
  try {
    form.accountId = value
    instruments.value = []
    const preserveInstId = syncingFromPosition.value && !!form.instId
    if (!preserveInstId) {
      form.instId = ''
      snapshot.value = null
      pendingOrders.value = []
    }
    if (value) {
      await searchInstruments(preserveInstId ? form.instId : '')
      await refreshOverview()
      if (preserveInstId && form.instId) {
        await Promise.all([refreshSnapshot(), refreshPendingOrders()])
      }
    }
  } finally {
    syncingFromPosition.value = false
  }
})

watch(instType, async () => {
  applyDefaultsByInstType()
  instruments.value = []
  if (selectedAccountId.value) {
    await searchInstruments()
    await refreshOverview()
  }
})

watch(
  () => form.instId,
  async (value) => {
    if (!value) {
      snapshot.value = null
      pendingOrders.value = []
      return
    }
    ensureInstrument(value, instType.value)
    await Promise.all([refreshSnapshot(), refreshPendingOrders()])
  }
)

watch(
  () => form.ordType,
  (value) => {
    if (value === 'market') form.px = undefined
    else if (!form.px && snapshot.value?.ticker.last) form.px = snapshot.value.ticker.last
  }
)

defineExpose({
  openWithPosition,
})

onMounted(async () => {
  applyDefaultsByInstType()
  try {
    await loadAccounts()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取 OKX 账户失败')
  }
})
</script>

<style scoped>
.manual-panel {
  margin-bottom: 14px;
  padding: 14px 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-card);
}

.panel-header,
.panel-controls,
.trade-toolbar,
.toolbar-meta,
.compact-card-head,
.quote-main,
.quote-stats,
.book-line,
.submit-info,
.submit-row {
  display: flex;
  align-items: center;
}

.panel-header,
.trade-toolbar,
.compact-card-head,
.submit-row {
  justify-content: space-between;
}

.panel-header {
  gap: 12px;
}

.panel-controls {
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.panel-title {
  margin: 0 0 2px;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
}

.panel-desc,
.card-subtitle,
.toolbar-meta,
.readonly-tag,
.submit-info {
  color: var(--color-text-muted);
}

.panel-desc {
  margin: 0;
  font-size: 12px;
}

.panel-empty {
  padding: 20px 0 8px;
}

.trade-toolbar {
  margin-top: 12px;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-start;
}

.symbol-select {
  width: 320px;
}

.toolbar-meta {
  gap: 10px;
  font-size: 12px;
}

.readonly-tag {
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  font-size: 12px;
}

.symbol-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.symbol-meta {
  color: var(--color-text-muted);
  font-size: 12px;
}

.compact-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.95fr) minmax(340px, 1.1fr) minmax(280px, 0.95fr);
  gap: 12px;
  margin-top: 12px;
}

.compact-card {
  min-height: 292px;
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
}

.compact-card-head {
  gap: 10px;
  margin-bottom: 10px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.card-subtitle {
  margin-top: 2px;
  font-size: 12px;
}

.quote-main {
  gap: 10px;
}

.quote-main strong {
  font-size: 24px;
  line-height: 1;
  color: var(--color-text-primary);
}

.quote-main span {
  font-size: 13px;
  font-weight: 600;
}

.quote-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.quote-stat {
  padding: 8px 10px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-bg-card) 82%, transparent);
  border: 1px solid var(--color-border);
}

.quote-stat span {
  display: block;
  margin-bottom: 2px;
  font-size: 11px;
  color: var(--color-text-muted);
}

.quote-stat strong {
  font-size: 13px;
  color: var(--color-text-primary);
}

.book-board {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.book-column {
  padding: 10px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-bg-card) 88%, transparent);
  border: 1px solid var(--color-border);
}

.book-column-head {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
}

.book-line {
  justify-content: space-between;
  height: 24px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.buy-text {
  color: var(--color-success, #10b981);
}

.sell-text {
  color: var(--color-danger, #ef4444);
}

.action-badge {
  padding: 4px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primary) 10%, transparent);
  color: var(--color-primary);
  font-size: 12px;
}

.compact-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.ticket-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
}

.ticket-field {
  min-width: 0;
}

.ticket-field-span {
  grid-column: 1 / -1;
}

.ticket-field label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.submit-row {
  gap: 10px;
  margin-top: 12px;
}

.submit-info {
  flex: 1;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  min-width: 0;
}

.submit-button {
  min-width: 120px;
}

.side-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
}

.side-tabs :deep(.el-tabs__item) {
  color: var(--color-text-muted);
  font-size: 12px;
}

.side-tabs :deep(.el-tabs__item.is-active) {
  color: var(--color-text-primary);
}

.manual-panel :deep(.el-radio-group) {
  gap: 6px;
}

.manual-panel :deep(.el-radio-button__inner) {
  border-radius: 999px;
  border-color: var(--color-border);
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  box-shadow: none;
}

.manual-panel :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-bg-card));
  border-color: color-mix(in srgb, var(--color-primary) 36%, var(--color-border));
  color: var(--color-primary);
  box-shadow: none;
}

.manual-panel :deep(.el-input__wrapper) {
  background: var(--color-bg-card);
  box-shadow: 0 0 0 1px var(--color-border) inset;
}

.manual-panel :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--color-primary) inset;
}

.manual-panel :deep(.el-input__inner) {
  color: var(--color-text-primary);
}

.manual-panel :deep(.el-input-group__append),
.manual-panel :deep(.el-input-group__prepend) {
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  border-color: var(--color-border);
}

.manual-panel :deep(.el-select__wrapper) {
  background: var(--color-bg-card);
  box-shadow: 0 0 0 1px var(--color-border) inset;
}

.manual-panel :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-border-color: var(--color-border);
  --el-table-header-bg-color: color-mix(in srgb, var(--color-bg-card) 92%, transparent);
  --el-table-header-text-color: var(--color-text-muted);
  --el-table-text-color: var(--color-text-secondary);
}

.manual-panel :deep(.el-table th.el-table__cell),
.manual-panel :deep(.el-table tr),
.manual-panel :deep(.el-table td.el-table__cell) {
  background: transparent;
}

.manual-panel :deep(.el-tabs__nav-wrap::after) {
  background-color: var(--color-border);
}

.manual-panel :deep(.el-tabs__active-bar) {
  background-color: var(--color-primary);
}

.manual-panel :deep(.el-button--default) {
  border-color: var(--color-border);
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
}

.manual-panel :deep(.el-button--default:hover) {
  color: var(--color-primary);
  border-color: color-mix(in srgb, var(--color-primary) 32%, var(--color-border));
  background: color-mix(in srgb, var(--color-primary) 8%, var(--color-bg-card));
}

.manual-panel :deep(.el-button--success),
.manual-panel :deep(.el-button--danger),
.manual-panel :deep(.el-button--warning),
.manual-panel :deep(.el-button--primary) {
  box-shadow: none;
}

@media (max-width: 1380px) {
  .compact-grid {
    grid-template-columns: 1fr 1fr;
  }

  .side-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 980px) {
  .compact-grid {
    grid-template-columns: 1fr;
  }

  .quote-stats,
  .ticket-grid {
    grid-template-columns: 1fr;
  }

  .submit-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
