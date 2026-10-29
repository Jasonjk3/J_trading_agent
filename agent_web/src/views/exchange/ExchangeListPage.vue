<template>
  <div class="page-content">
    <div class="page-card">
      <div class="page-header">
        <h2 class="page-title">交易所配置</h2>
        <p class="page-desc">管理用于量化交易的交易所 API 密钥，支持连接测试与启用/禁用。</p>
      </div>

      <div class="toolbar">
        <el-form :model="filter" inline class="filter-form">
          <el-form-item label="交易所">
            <el-select v-model="filter.exchange" placeholder="全部" clearable style="width: 120px">
              <el-option label="Binance" value="binance" />
              <el-option label="OKX" value="okx" />
              <el-option label="Bybit" value="bybit" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filter.enabled" placeholder="全部" clearable style="width: 100px">
              <el-option label="启用" :value="true" />
              <el-option label="禁用" :value="false" />
            </el-select>
          </el-form-item>
          <el-form-item label="绑定">
            <el-select v-model="filter.bindStatus" placeholder="全部" clearable style="width: 110px">
              <el-option label="成功" value="success" />
              <el-option label="失败" value="failed" />
              <el-option label="未校验" value="never" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchList">查询</el-button>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
        <el-button type="primary" :icon="Plus" @click="openAdd">添加配置</el-button>
      </div>

      <div class="table-wrap">
        <el-table
          v-loading="loading"
          :data="list"
          class="data-table"
          header-cell-class-name="table-header"
          table-layout="auto"
        >
          <el-table-column prop="exchange" label="交易所" min-width="116">
            <template #default="{ row }">
              <span class="exchange-name">{{ exchangeLabel(row.exchange) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注名" min-width="120">
            <template #default="{ row }">{{ row.remark || '-' }}</template>
          </el-table-column>
          <el-table-column prop="apiKeyMasked" label="API Key" min-width="108">
            <template #default="{ row }">
              <span class="api-masked">{{ row.apiKeyMasked || '****' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bindStatus" label="绑定状态" min-width="112">
            <template #default="{ row }">
              <el-tag :type="bindStatusTagType(row.bindStatus)" size="small">
                {{ bindStatusLabel(row.bindStatus) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="lastVerifiedAt" label="最后校验时间" min-width="188" align="right">
            <template #default="{ row }">{{ formatDate(row.lastVerifiedAt) }}</template>
          </el-table-column>
          <el-table-column prop="readOnly" label="仅读" min-width="88" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.readOnly" type="info" size="small">是</el-tag>
              <span v-else class="text-muted">否</span>
            </template>
          </el-table-column>
          <el-table-column prop="enabled" label="启用" min-width="96" align="center">
            <template #default="{ row }">
              <el-switch :model-value="row.enabled" @change="(v: boolean) => toggleEnabled(row, v)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right" align="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
              <el-button type="primary" link size="small" :loading="verifyLoadingId === row.id" @click="handleVerify(row)">测试连接</el-button>
              <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="list.length > 0" class="table-footer">
        共 {{ list.length }} 条配置
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editRecord ? '编辑配置' : '添加交易所配置'"
      width="520px"
      destroy-on-close
      @closed="editRecord = null"
    >
      <ExchangeForm ref="formRef" :model-value="dialogVisible" :edit-record="editRecord" @submit="onFormSubmit" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleDialogConfirm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { exchangeAccountsApi } from '@/api/exchangeAccounts'
import type { ExchangeAccountListItem, ExchangeCode, BindStatus, CreateExchangeAccountDto, UpdateExchangeAccountDto } from '@/api/exchangeAccounts'
import ExchangeForm from './ExchangeForm.vue'

const loading = ref(false)
const list = ref<ExchangeAccountListItem[]>([])
const filter = reactive<{ exchange?: ExchangeCode; enabled?: boolean; bindStatus?: BindStatus }>({})
const dialogVisible = ref(false)
const editRecord = ref<ExchangeAccountListItem | null>(null)
const formRef = ref<InstanceType<typeof ExchangeForm>>()
const submitLoading = ref(false)
const verifyLoadingId = ref<string | null>(null)

function exchangeLabel(code: ExchangeCode): string {
  return ({ binance: 'Binance', okx: 'OKX', bybit: 'Bybit' } as Record<ExchangeCode, string>)[code] ?? code
}
function bindStatusLabel(status: BindStatus): string {
  return ({ success: '成功', failed: '失败', pending: '校验中', never: '未校验' } as Record<BindStatus, string>)[status] ?? status
}
function bindStatusTagType(status: BindStatus): 'success' | 'danger' | 'warning' | 'info' {
  return ({ success: 'success', failed: 'danger', pending: 'warning', never: 'info' } as Record<BindStatus, any>)[status] ?? 'info'
}
function formatDate(iso?: string): string {
  if (!iso) return '-'; return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

async function fetchList() {
  loading.value = true
  try { const res = await exchangeAccountsApi.getList({ exchange: filter.exchange, enabled: filter.enabled, bindStatus: filter.bindStatus }); list.value = res.list }
  catch (e: any) { ElMessage.error(e?.message ?? '加载配置列表失败') }
  finally { loading.value = false }
}

function resetFilter() { filter.exchange = undefined; filter.enabled = undefined; filter.bindStatus = undefined; fetchList() }
function openAdd() { editRecord.value = null; dialogVisible.value = true }
function openEdit(row: ExchangeAccountListItem) { editRecord.value = { ...row }; dialogVisible.value = true }
async function handleDialogConfirm() { const ok = await formRef.value?.validateAndEmit(); if (!ok) return }

function onFormSubmit(payload: { exchange: ExchangeCode; apiKey?: string; apiSecret?: string; passphrase?: string; remark?: string; readOnly: boolean; enabled: boolean }) {
  submitLoading.value = true
  const isEdit = !!editRecord.value; const id = editRecord.value?.id
  const run = isEdit && id
    ? exchangeAccountsApi.update(id, { ...(payload.apiKey && { apiKey: payload.apiKey }), ...(payload.apiSecret && { apiSecret: payload.apiSecret }), ...(payload.passphrase !== undefined && { passphrase: payload.passphrase }), remark: payload.remark, readOnly: payload.readOnly, enabled: payload.enabled } as UpdateExchangeAccountDto)
    : exchangeAccountsApi.create({ exchange: payload.exchange, apiKey: payload.apiKey ?? '', apiSecret: payload.apiSecret ?? '', passphrase: payload.passphrase, remark: payload.remark, readOnly: payload.readOnly, enabled: payload.enabled } as CreateExchangeAccountDto)
  run.then(() => { ElMessage.success(isEdit ? '保存成功' : '添加成功'); dialogVisible.value = false; fetchList() })
    .catch((e: any) => ElMessage.error(e?.message ?? (isEdit ? '保存失败' : '添加失败')))
    .finally(() => { submitLoading.value = false })
}

async function handleVerify(row: ExchangeAccountListItem) {
  verifyLoadingId.value = row.id
  try { const res = await exchangeAccountsApi.verify(row.id); res.success ? ElMessage.success(res.message ?? '连接成功') : ElMessage.warning(res.message ?? '连接失败'); fetchList() }
  catch (e: any) { ElMessage.error(e?.message ?? '校验请求失败') }
  finally { verifyLoadingId.value = null }
}

async function toggleEnabled(row: ExchangeAccountListItem, enabled: boolean) {
  try { await exchangeAccountsApi.update(row.id, { enabled }); ElMessage.success(enabled ? '已启用' : '已禁用'); row.enabled = enabled }
  catch (e: any) { ElMessage.error(e?.message ?? '操作失败') }
}

function handleDelete(row: ExchangeAccountListItem) {
  const name = row.remark || exchangeLabel(row.exchange)
  ElMessageBox.confirm(`确定删除配置「${name}」吗？删除后需重新填写 API 密钥。`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    .then(async () => { await exchangeAccountsApi.remove(row.id); ElMessage.success('已删除'); fetchList() })
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
.page-header { margin-bottom: var(--spacing-lg); }
.page-title { margin: 0 0 8px; }
.toolbar {
  display: flex; flex-wrap: wrap; align-items: flex-start;
  justify-content: space-between; gap: 16px; margin-bottom: 16px;
}
.filter-form { margin-bottom: 0; }
.data-table { width: 100%; }
.exchange-name { font-weight: 500; color: var(--color-text-primary); }
.api-masked { font-family: ui-monospace, monospace; color: var(--color-text-muted); font-size: var(--font-size-caption); }
.text-muted { color: var(--color-text-muted); font-size: var(--font-size-desc); }
</style>

