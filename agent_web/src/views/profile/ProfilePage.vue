<template>
  <div class="page-content">
    <div class="profile-cards">
      <div class="page-card card-block">
        <div class="card-title">
          <span class="card-icon" style="--ci: #8B5CF6">
            <el-icon :size="16"><User /></el-icon>
          </span>
          <h2 class="block-title">账号信息</h2>
        </div>
        <div class="info-list" v-if="userStore.user">
          <div class="info-row">
            <span class="label">用户名</span>
            <span class="value">{{ userStore.user.username }}</span>
          </div>
          <div class="info-row">
            <span class="label">角色</span>
            <el-tag :type="roleTagType(userStore.user.role)" size="small">
              {{ roleLabel(userStore.user.role) }}
            </el-tag>
          </div>
          <div class="info-row">
            <span class="label">用户 ID</span>
            <span class="value mono">{{ userStore.user.id }}</span>
          </div>
        </div>
      </div>

      <div class="page-card card-block">
        <div class="card-title">
          <span class="card-icon" style="--ci: #38BDF8">
            <el-icon :size="16"><Lock /></el-icon>
          </span>
          <h2 class="block-title">修改密码</h2>
        </div>
        <el-form
          ref="pwdFormRef"
          :model="pwdForm"
          :rules="pwdRules"
          label-width="100px"
          class="pwd-form"
          @submit.prevent="onSubmitPwd"
        >
          <el-form-item label="当前密码" prop="oldPassword">
            <el-input v-model="pwdForm.oldPassword" type="password" placeholder="请输入当前密码" show-password clearable />
          </el-form-item>
          <el-form-item label="新密码" prop="newPassword">
            <el-input v-model="pwdForm.newPassword" type="password" placeholder="6-32 位字符" show-password clearable />
          </el-form-item>
          <el-form-item label="确认新密码" prop="confirmPassword">
            <el-input v-model="pwdForm.confirmPassword" type="password" placeholder="再次输入新密码" show-password clearable />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="pwdLoading" @click="onSubmitPwd">保存新密码</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div class="page-card card-block">
        <div class="card-title">
          <span class="card-icon" style="--ci: #F59E0B">
            <el-icon :size="16"><Warning /></el-icon>
          </span>
          <h2 class="block-title">安全设置</h2>
        </div>
        <div class="safe-static">
          <div class="safe-item">
            <span class="safe-label">登录设备</span>
            <span class="safe-desc">接入后端后可展示当前登录设备列表</span>
          </div>
          <div class="safe-item">
            <span class="safe-label">最近登录</span>
            <span class="safe-desc">接入后端后可展示最近登录时间与 IP</span>
          </div>
          <div class="safe-item">
            <span class="safe-label">二次验证</span>
            <span class="safe-desc">接入后端后可开启/关闭双因素认证</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Warning } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { authApi } from '@/api/auth'

const userStore = useUserStore()
const pwdFormRef = ref<FormInstance>()
const pwdLoading = ref(false)
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })

const validateConfirm = (_rule: any, value: string, callback: (e?: Error) => void) => {
  if (value !== pwdForm.newPassword) callback(new Error('两次输入的新密码不一致'))
  else callback()
}

const pwdRules: FormRules = {
  oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 32, message: '长度 6-32 个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

function roleLabel(role: string) { return ({ admin: '管理员', user: '普通用户' } as Record<string, string>)[role] ?? role }
function roleTagType(role: string) { return ({ admin: 'danger', user: 'primary' } as Record<string, string>)[role] ?? '' }

async function onSubmitPwd() {
  if (!pwdFormRef.value || !userStore.user) return
  await pwdFormRef.value.validate(async (valid) => {
    if (!valid) return
    pwdLoading.value = true
    try {
      await authApi.resetPassword(userStore.user!.username, pwdForm.oldPassword, pwdForm.newPassword)
      ElMessage.success('密码已修改，请使用新密码重新登录')
      pwdForm.oldPassword = ''; pwdForm.newPassword = ''; pwdForm.confirmPassword = ''
      pwdFormRef.value?.resetFields()
    } catch (e: any) { ElMessage.error(e?.message ?? '修改失败') }
    finally { pwdLoading.value = false }
  })
}
</script>

<style scoped>
.profile-cards {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}
.page-card.card-block {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}
.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--ci) 15%, transparent);
  color: var(--ci);
}
.block-title {
  margin: 0;
  font-size: var(--font-size-card-title);
  font-weight: 600;
  color: var(--color-text-primary);
}
.info-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.info-row {
  display: flex;
  align-items: center;
  gap: 16px;
}
.info-row .label {
  width: 80px;
  font-size: var(--font-size-body);
  color: var(--color-text-muted);
}
.info-row .value {
  font-size: var(--font-size-body);
  color: var(--color-text-primary);
}
.info-row .value.mono {
  font-family: ui-monospace, monospace;
  font-size: var(--font-size-desc);
  color: var(--color-text-muted);
}
.pwd-form {
  max-width: 420px;
}
.safe-static {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.safe-item {
  padding: 14px 0;
  border-bottom: 1px solid var(--color-border);
}
.safe-item:last-child {
  border-bottom: none;
}
.safe-label {
  display: block;
  font-size: var(--font-size-body);
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}
.safe-desc {
  font-size: var(--font-size-desc);
  color: var(--color-text-disabled);
}
</style>

