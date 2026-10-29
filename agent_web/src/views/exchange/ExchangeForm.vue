<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="100px"
    class="exchange-form"
  >
    <el-form-item label="交易所" prop="exchange">
      <el-select
        v-model="form.exchange"
        placeholder="请选择交易所"
        style="width: 100%"
        :disabled="isEdit"
        @change="onExchangeChange"
      >
        <el-option label="Binance" value="binance" />
        <el-option label="OKX" value="okx" />
        <el-option label="Bybit" value="bybit" />
      </el-select>
      <p v-if="isEdit" class="form-tip">编辑时不可修改交易所</p>
    </el-form-item>
    <el-form-item label="API Key" prop="apiKey">
      <el-input
        v-model="form.apiKey"
        :placeholder="isEdit ? '不修改请留空' : '请输入 API Key'"
        clearable
        show-password
        autocomplete="off"
      />
    </el-form-item>
    <el-form-item label="API Secret" prop="apiSecret">
      <el-input
        v-model="form.apiSecret"
        type="password"
        :placeholder="isEdit ? '不修改请留空' : '请输入 API Secret'"
        show-password
        clearable
        autocomplete="off"
      />
      <p class="form-tip">前端不存储明文，仅通过 HTTPS 提交后端</p>
    </el-form-item>
    <el-form-item v-if="needPassphrase" label="Passphrase" prop="passphrase">
      <el-input
        v-model="form.passphrase"
        type="password"
        :placeholder="isEdit ? '不修改请留空' : 'OKX 等交易所必填'"
        show-password
        clearable
        autocomplete="off"
      />
    </el-form-item>
    <el-form-item label="备注" prop="remark">
      <el-input
        v-model="form.remark"
        placeholder="选填，如：主账户 / 子账户"
        clearable
        maxlength="64"
        show-word-limit
      />
    </el-form-item>
    <el-form-item label="仅读权限" prop="readOnly">
      <el-switch v-model="form.readOnly" />
      <span class="form-tip inline">仅读权限不可下单，仅可查询</span>
    </el-form-item>
    <el-form-item label="启用" prop="enabled">
      <el-switch v-model="form.enabled" />
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import type { ExchangeAccountListItem, ExchangeCode } from '@/api/exchangeAccounts'

const EXCHANGE_NEEDS_PASSPHRASE: ExchangeCode[] = ['okx']

const props = defineProps<{
  modelValue: boolean
  editRecord?: ExchangeAccountListItem | null
}>()

const emit = defineEmits<{
  submit: [payload: {
    exchange: ExchangeCode
    apiKey?: string
    apiSecret?: string
    passphrase?: string
    remark?: string
    readOnly: boolean
    enabled: boolean
  }]
}>()

const isEdit = computed(() => !!props.editRecord)

const needPassphrase = computed(() => EXCHANGE_NEEDS_PASSPHRASE.includes(form.exchange))

const formRef = ref<FormInstance>()
const form = reactive({
  exchange: 'binance' as ExchangeCode,
  apiKey: '',
  apiSecret: '',
  passphrase: '',
  remark: '',
  readOnly: false,
  enabled: true,
})

const rules: FormRules = {
  exchange: [{ required: true, message: '请选择交易所', trigger: 'change' }],
  apiKey: [
    {
      validator: (_rule: any, value: string, callback: (e?: Error) => void) => {
        if (isEdit.value && !value) {
          callback()
          return
        }
        if (!isEdit.value && !value?.trim()) {
          callback(new Error('请输入 API Key'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  apiSecret: [
    {
      validator: (_rule: any, value: string, callback: (e?: Error) => void) => {
        if (isEdit.value && !value) {
          callback()
          return
        }
        if (!isEdit.value && !value?.trim()) {
          callback(new Error('请输入 API Secret'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

function onExchangeChange() {
  form.passphrase = ''
}

watch(
  () => [props.modelValue, props.editRecord] as const,
  ([visible, record]) => {
    if (visible) {
      form.exchange = (record?.exchange ?? 'binance') as ExchangeCode
      form.apiKey = ''
      form.apiSecret = ''
      form.passphrase = ''
      form.remark = record?.remark ?? ''
      form.readOnly = record?.readOnly ?? false
      form.enabled = record?.enabled ?? true
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
          exchange: form.exchange,
          ...(form.apiKey?.trim() ? { apiKey: form.apiKey.trim() } : {}),
          ...(form.apiSecret?.trim() ? { apiSecret: form.apiSecret.trim() } : {}),
          ...(form.passphrase?.trim() ? { passphrase: form.passphrase.trim() } : {}),
          remark: form.remark?.trim() || undefined,
          readOnly: form.readOnly,
          enabled: form.enabled,
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
.exchange-form {
  padding-right: 8px;
}
.form-tip {
  margin: 4px 0 0;
  font-size: var(--font-size-caption);
  color: var(--color-text-placeholder);
}
.form-tip.inline {
  margin-left: 8px;
  display: inline;
}
</style>
