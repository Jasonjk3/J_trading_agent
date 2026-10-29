<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="90px"
    class="user-form"
  >
    <el-form-item label="用户名" prop="username">
      <el-input
        v-model="form.username"
        placeholder="请输入用户名"
        :disabled="isEdit"
        clearable
      />
      <p v-if="isEdit" class="form-tip">编辑时不可修改用户名</p>
    </el-form-item>
    <el-form-item label="邮箱" prop="email">
      <el-input
        v-model="form.email"
        placeholder="请输入邮箱（选填）"
        clearable
      />
    </el-form-item>
    <el-form-item :label="isEdit ? '新密码' : '密码'" prop="password">
      <el-input
        v-model="form.password"
        type="password"
        :placeholder="isEdit ? '不修改请留空' : '请输入密码'"
        show-password
        clearable
      />
    </el-form-item>
    <el-form-item label="角色" prop="role">
      <el-select v-model="form.role" placeholder="请选择角色" style="width: 100%">
        <el-option label="管理员" value="admin" />
        <el-option label="普通用户" value="user" />
      </el-select>
    </el-form-item>
    <el-form-item label="状态" prop="status">
      <el-radio-group v-model="form.status">
        <el-radio value="active">启用</el-radio>
        <el-radio value="disabled">禁用</el-radio>
      </el-radio-group>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { UserListItem } from '@/api/users'

const props = defineProps<{
  modelValue: boolean
  editRecord?: UserListItem | null
}>()

const emit = defineEmits<{
  submit: [payload: { username: string; password?: string; email?: string; role: string; status: string }]
}>()

const isEdit = computed(() => !!props.editRecord)

const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  email: '',
  password: '',
  role: 'user',
  status: 'active',
})

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 32, message: '长度 2-32 个字符', trigger: 'blur' },
  ],
  email: [
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' },
  ],
  password: [
    {
      validator: (_rule: any, value: string, callback: (e?: Error) => void) => {
        if (isEdit.value && !value) {
          callback()
          return
        }
        if (!isEdit.value && !value) {
          callback(new Error('请输入密码'))
          return
        }
        if (value && (value.length < 6 || value.length > 32)) {
          callback(new Error('密码长度 6-32 个字符'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

watch(
  () => [props.modelValue, props.editRecord] as const,
  ([visible, record]) => {
    if (visible) {
      form.username = record?.username ?? ''
      form.email = record?.email ?? ''
      form.password = ''
      form.role = record?.role ?? 'user'
      form.status = record?.status ?? 'active'
      formRef.value?.clearValidate()
    }
  },
  { immediate: true }
)

function validateAndEmit(): Promise<boolean> {
  return new Promise((resolve) => {
    if (!formRef.value) {
      resolve(false)
      return
    }
    formRef.value.validate((valid) => {
      if (valid) {
        emit('submit', {
          username: form.username.trim(),
          ...(form.email ? { email: form.email.trim() } : {}),
          ...(form.password ? { password: form.password } : {}),
          role: form.role,
          status: form.status,
        })
        resolve(true)
      } else {
        resolve(false)
      }
    })
  })
}

defineExpose({ validateAndEmit })
</script>

<style scoped>
.user-form {
  padding-right: 8px;
}
.form-tip {
  margin: 4px 0 0;
  font-size: var(--font-size-caption);
  color: var(--color-text-placeholder);
}
</style>
