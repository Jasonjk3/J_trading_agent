<template>
  <div class="page-content">
    <div class="page-card">
      <div class="page-header">
        <h2 class="page-title">用户管理</h2>
        <p class="page-desc">管理系统用户账号、角色与状态。</p>
      </div>

      <div class="toolbar">
        <el-form :model="filter" inline class="filter-form">
          <el-form-item label="用户名">
            <el-input v-model="filter.username" placeholder="搜索用户名" clearable style="width: 160px" @keyup.enter="fetchList" />
          </el-form-item>
          <el-form-item label="角色">
            <el-select v-model="filter.role" placeholder="全部" clearable style="width: 120px">
              <el-option label="管理员" value="admin" />
              <el-option label="普通用户" value="user" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filter.status" placeholder="全部" clearable style="width: 100px">
              <el-option label="启用" value="active" />
              <el-option label="禁用" value="disabled" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="fetchList">查询</el-button>
            <el-button @click="resetFilter">重置</el-button>
          </el-form-item>
        </el-form>
        <el-button type="primary" :icon="Plus" @click="openAdd">新增用户</el-button>
      </div>

      <div class="table-wrap">
        <el-table
          v-loading="loading"
          :data="list"
          class="data-table"
          header-cell-class-name="table-header"
          table-layout="auto"
        >
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column prop="email" label="邮箱" min-width="160" show-overflow-tooltip />
          <el-table-column prop="role" label="角色" min-width="108">
            <template #default="{ row }">
              <el-tag :type="roleTagType(row.role)" size="small">{{ roleLabel(row.role) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" min-width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === 'active' ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="createdAt" label="创建时间" min-width="188" align="right">
            <template #default="{ row }">{{ formatDate(row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right" align="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
              <el-button type="danger" link size="small" :disabled="row.id === currentUserId" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pagination-wrap">
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

    <el-dialog
      v-model="dialogVisible"
      :title="editRecord ? '编辑用户' : '新增用户'"
      width="480px"
      destroy-on-close
      @closed="editRecord = null"
    >
      <UserForm ref="userFormRef" :model-value="dialogVisible" :edit-record="editRecord" @submit="onFormSubmit" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleDialogConfirm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { usersApi } from '@/api/users'
import type { UserListItem, CreateUserDto, UpdateUserDto, UserListParams } from '@/api/users'
import UserForm from './UserForm.vue'

const userStore = useUserStore()
const currentUserId = computed(() => userStore.user?.id ?? '')
const loading = ref(false)
const list = ref<UserListItem[]>([])
const filter = reactive<{
  username: string
  role: UserListParams['role'] | ''
  status: UserListParams['status'] | ''
}>({ username: '', role: '', status: '' })
const pagination = reactive({ page: 1, pageSize: 10, total: 0 })
const dialogVisible = ref(false)
const editRecord = ref<UserListItem | null>(null)
const userFormRef = ref<InstanceType<typeof UserForm>>()
const submitLoading = ref(false)

function roleLabel(role: string) { return ({ admin: '管理员', user: '普通用户' } as Record<string, string>)[role] ?? role }
function roleTagType(role: string) { return ({ admin: 'danger', user: 'primary' } as Record<string, string>)[role] ?? '' }
function formatDate(iso: string) { if (!iso) return '-'; return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) }

async function fetchList() {
  loading.value = true
  try {
    const res = await usersApi.getList({ username: filter.username || undefined, role: filter.role || undefined, status: filter.status || undefined, page: pagination.page, pageSize: pagination.pageSize })
    list.value = res.list; pagination.total = res.total
  } catch (e: any) { ElMessage.error(e?.message ?? '加载用户列表失败') }
  finally { loading.value = false }
}

function resetFilter() { filter.username = ''; filter.role = ''; filter.status = ''; pagination.page = 1; fetchList() }
function openAdd() { editRecord.value = null; dialogVisible.value = true }
function openEdit(row: UserListItem) { editRecord.value = { ...row }; dialogVisible.value = true }
async function handleDialogConfirm() { const ok = await userFormRef.value?.validateAndEmit(); if (!ok) return }

function onFormSubmit(payload: { username: string; password?: string; email?: string; role: string; status: string }) {
  submitLoading.value = true
  const isEdit = !!editRecord.value; const id = editRecord.value?.id
  const p = isEdit && id ? usersApi.update(id, payload as UpdateUserDto) : usersApi.create(payload as CreateUserDto)
  p.then(() => { ElMessage.success(isEdit ? '保存成功' : '新增成功'); dialogVisible.value = false; fetchList() })
    .catch((e: any) => ElMessage.error(e?.message ?? (isEdit ? '保存失败' : '新增失败')))
    .finally(() => { submitLoading.value = false })
}

function handleDelete(row: UserListItem) {
  if (row.id === currentUserId.value) { ElMessage.warning('不能删除当前登录用户'); return }
  ElMessageBox.confirm(`确定删除用户「${row.username}」吗？`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    .then(async () => { await usersApi.remove(row.id); ElMessage.success('已删除'); fetchList() })
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
</style>

