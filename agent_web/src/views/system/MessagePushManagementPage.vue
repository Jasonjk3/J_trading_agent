<template>
  <div class="message-push-page page-content">
    <header class="page-heading">
      <div>
        <div class="title-row">
          <h1 class="page-title">消息推送管理</h1>
          <el-tag size="small" effect="plain">首期 · 飞书</el-tag>
        </div>
        <p class="page-desc">统一配置消息推送渠道，用于接收交易信号、风险告警和任务状态通知。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增机器人</el-button>
    </header>

    <section class="overview-grid" aria-label="消息推送概览">
      <article class="overview-card">
        <div class="metric-icon brand"><Promotion /></div>
        <div>
          <span class="metric-label">机器人配置</span>
          <strong class="metric-value">{{ configs.length }}</strong>
        </div>
      </article>
      <article class="overview-card">
        <div class="metric-icon success"><CircleCheck /></div>
        <div>
          <span class="metric-label">已启用</span>
          <strong class="metric-value">{{ enabledCount }}</strong>
        </div>
      </article>
      <article class="overview-card status-card">
        <div class="status-main">
          <span class="status-dot" :class="enabledCount ? 'online' : 'idle'"></span>
          <div>
            <span class="metric-label">推送服务</span>
            <strong class="service-status">{{ enabledCount ? '运行正常' : '等待配置' }}</strong>
          </div>
        </div>
        <span class="status-note">凭据已加密保存至服务端</span>
      </article>
    </section>

    <section v-loading="loading" class="content-card">
      <div class="section-header">
        <div>
          <h2>推送渠道</h2>
          <p>支持飞书群自定义机器人与企业自建应用机器人。</p>
        </div>
        <div class="channel-filter">
          <span>全部渠道</span>
          <el-tag type="success" size="small">飞书 {{ configs.length }}</el-tag>
        </div>
      </div>

      <div v-if="configs.length" class="config-list">
        <article v-for="item in configs" :key="item.id" class="config-item">
          <div class="channel-logo" aria-hidden="true">
            <Promotion />
          </div>
          <div class="config-main">
            <div class="config-title-row">
              <strong>{{ item.name }}</strong>
              <el-tag size="small" type="success" effect="light">飞书</el-tag>
              <el-tag size="small" type="info" effect="plain">{{ botTypeLabel(item.botType) }}</el-tag>
              <span class="enabled-state" :class="{ active: item.enabled }">
                <i></i>{{ item.enabled ? '已启用' : '已停用' }}
              </span>
            </div>
            <p class="config-desc">{{ item.description || '暂无备注' }}</p>
            <div class="config-meta">
              <template v-if="item.botType === 'webhook'">
                <span><Link />{{ item.webhookMasked || '未配置' }}</span>
                <span><Lock />{{ item.hasSecret ? '签名校验已开启' : '未配置签名校验' }}</span>
              </template>
              <template v-else>
                <span><Key />App ID：{{ item.appIdMasked || '未配置' }}</span>
                <span><User />默认接收：{{ receiverTypeLabel(item.receiveType) }} · {{ item.receiveIdMasked || '未配置' }}</span>
              </template>
              <span><Clock />最近测试：{{ formatDate(item.lastTestAt) }}</span>
            </div>
          </div>
          <div class="config-actions">
            <el-switch
              :model-value="item.enabled"
              inline-prompt
              active-text="开"
              inactive-text="关"
              @change="(value: boolean) => toggleConfig(item, value)"
            />
            <span class="action-divider"></span>
            <el-button :icon="VideoPlay" @click="openTest(item)">测试发送</el-button>
            <el-dropdown trigger="click" @command="(command: string) => handleCommand(command, item)">
              <el-button class="more-button" :icon="MoreFilled" aria-label="更多操作" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit" :icon="Edit">编辑配置</el-dropdown-item>
                  <el-dropdown-item command="delete" :icon="Delete" divided>删除配置</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </article>
      </div>

      <div v-else class="empty-state">
        <div class="empty-icon"><Bell /></div>
        <h3>还没有推送机器人</h3>
        <p>添加飞书机器人后，即可将交易信号和系统告警推送到群聊。</p>
        <el-button type="primary" :icon="Plus" @click="openCreate">添加飞书机器人</el-button>
      </div>
    </section>

    <aside class="help-card">
      <div class="help-icon"><InfoFilled /></div>
      <div>
        <strong>如何获取 Webhook 地址？</strong>
        <p>自定义机器人使用群 Webhook；应用机器人需在飞书开放平台创建企业自建应用并开通消息权限。</p>
      </div>
      <el-button link type="primary" @click="showGuide = true">查看配置指引</el-button>
    </aside>

    <el-dialog
      v-model="editorVisible"
      :title="editingId ? '编辑飞书机器人' : '添加飞书机器人'"
      width="580px"
      destroy-on-close
      class="push-editor-dialog"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="editor-form">
        <el-form-item label="机器人类型">
          <el-radio-group v-model="form.botType" class="bot-type-grid">
            <el-radio value="webhook" border>
              <span class="type-option"><Link /><i><b>自定义机器人</b><small>Webhook 推送到固定群聊</small></i></span>
            </el-radio>
            <el-radio value="app" border>
              <span class="type-option"><Grid /><i><b>应用机器人</b><small>应用身份推送给用户或群聊</small></i></span>
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="配置名称" prop="name">
          <el-input v-model="form.name" maxlength="30" show-word-limit placeholder="例如：交易风控通知群" />
        </el-form-item>
        <template v-if="form.botType === 'webhook'">
          <el-form-item label="Webhook 地址" prop="webhook">
            <el-input v-model="form.webhook" :placeholder="editingId ? '留空表示不修改 Webhook' : 'https://open.feishu.cn/open-apis/bot/v2/hook/...'">
              <template #prefix><Link /></template>
            </el-input>
            <div class="field-hint">地址将被脱敏展示，请勿将 Webhook 分享给无关人员。</div>
          </el-form-item>
          <el-form-item label="签名密钥" prop="secret">
            <el-input v-model="form.secret" type="password" show-password :placeholder="editingId ? '留空表示不修改签名密钥' : '选填，建议开启飞书机器人签名校验'">
              <template #prefix><Lock /></template>
            </el-input>
          </el-form-item>
        </template>
        <template v-else>
          <div class="form-grid">
            <el-form-item label="App ID" prop="appId">
              <el-input v-model="form.appId" :placeholder="editingId ? '留空表示不修改 App ID' : 'cli_xxxxxxxxxxxxx'">
                <template #prefix><Key /></template>
              </el-input>
            </el-form-item>
            <el-form-item label="App Secret" prop="appSecret">
              <el-input v-model="form.appSecret" type="password" show-password :placeholder="editingId ? '留空表示不修改 App Secret' : '请输入应用密钥'">
                <template #prefix><Lock /></template>
              </el-input>
            </el-form-item>
          </div>
          <div class="form-grid receiver-grid">
            <el-form-item label="默认接收对象" prop="receiveType">
              <el-select v-model="form.receiveType" style="width: 100%">
                <el-option label="群聊 Chat ID" value="chat_id" />
                <el-option label="用户 Open ID" value="open_id" />
                <el-option label="用户 User ID" value="user_id" />
                <el-option label="用户邮箱" value="email" />
              </el-select>
            </el-form-item>
            <el-form-item label="接收 ID" prop="receiveId">
              <el-input v-model="form.receiveId" :placeholder="editingId ? '留空表示不修改接收 ID' : receiverPlaceholder(form.receiveType)" />
            </el-form-item>
          </div>
          <div class="app-permission-note"><InfoFilled />需在飞书开放平台开通“获取与发送单聊、群组消息”权限，并发布应用版本。</div>
        </template>
        <el-form-item label="用途备注">
          <el-input v-model="form.description" type="textarea" :rows="3" maxlength="100" show-word-limit placeholder="说明该机器人接收哪些类型的消息" />
        </el-form-item>
        <div class="form-switch-row">
          <div>
            <strong>保存后立即启用</strong>
            <span>启用后业务消息可通过此机器人推送</span>
          </div>
          <el-switch v-model="form.enabled" />
        </div>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button :loading="testingWebhook" @click="validateConnection">验证连接</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testVisible" title="测试发送" width="620px" destroy-on-close>
      <div class="test-target">
        <div class="channel-logo small"><Promotion /></div>
        <div>
          <span>发送到</span>
          <strong>{{ testingConfig?.name }}</strong>
          <span>{{ testingConfig ? botTypeLabel(testingConfig.botType) : '' }}</span>
        </div>
        <el-tag type="success" size="small">飞书</el-tag>
      </div>
      <el-form label-position="top">
        <div v-if="testingConfig?.botType === 'app'" class="form-grid receiver-grid">
          <el-form-item label="接收对象">
            <el-select v-model="testForm.receiveType" style="width: 100%">
              <el-option label="群聊 Chat ID" value="chat_id" />
              <el-option label="用户 Open ID" value="open_id" />
              <el-option label="用户 User ID" value="user_id" />
              <el-option label="用户邮箱" value="email" />
            </el-select>
          </el-form-item>
          <el-form-item label="接收 ID">
            <el-input v-model="testForm.receiveId" placeholder="留空使用配置中的默认接收 ID" />
            <div class="field-hint">当前默认值：{{ testingConfig?.receiveIdMasked || '未配置' }}</div>
          </el-form-item>
        </div>
        <el-form-item label="消息类型">
          <el-radio-group v-model="testForm.type">
            <el-radio-button value="text">文本消息</el-radio-button>
            <el-radio-button value="card">消息卡片</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="testForm.type === 'card'" label="卡片标题">
          <el-input v-model="testForm.title" maxlength="40" />
        </el-form-item>
        <el-form-item label="消息内容">
          <el-input v-model="testForm.content" type="textarea" :rows="4" maxlength="300" show-word-limit />
        </el-form-item>
      </el-form>
      <div class="message-preview">
        <span class="preview-label">消息预览</span>
        <div class="feishu-preview" :class="{ card: testForm.type === 'card' }">
          <div v-if="testForm.type === 'card'" class="preview-title">{{ testForm.title || '测试通知' }}</div>
          <p>{{ testForm.content || '请输入消息内容' }}</p>
          <span>来自 QuantTrader 消息推送</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="testVisible = false">取消</el-button>
        <el-button type="primary" :icon="Promotion" :loading="sending" @click="sendTest">发送测试消息</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showGuide" title="飞书机器人配置指引" width="560px">
      <ol class="guide-list">
        <li><b>选择机器人类型</b><span>固定群聊通知可选自定义机器人；需要向不同用户或群聊推送时选择应用机器人。</span></li>
        <li><b>获取连接信息</b><span>从群机器人复制 Webhook，或从飞书开放平台获取应用 App ID 与 App Secret。</span></li>
        <li><b>完成安全与权限设置</b><span>自定义机器人建议开启签名；应用机器人需开通消息权限并发布版本。</span></li>
        <li><b>验证并测试</b><span>保存前验证连接，再向目标群聊或用户发送测试消息。</span></li>
      </ol>
      <template #footer><el-button type="primary" @click="showGuide = false">我知道了</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Bell,
  CircleCheck,
  Clock,
  Delete,
  Edit,
  Grid,
  InfoFilled,
  Key,
  Link,
  Lock,
  MoreFilled,
  Plus,
  Promotion,
  User,
  VideoPlay,
} from '@element-plus/icons-vue'
import { messagePushApi } from '@/api/messagePush'
import type {
  BotType,
  MessagePushConfig,
  MessagePushConfigPayload,
  ReceiveType,
  TestMessagePayload,
} from '@/api/messagePush'

const configs = ref<MessagePushConfig[]>([])
const loading = ref(false)
const saving = ref(false)
const enabledCount = computed(() => configs.value.filter(item => item.enabled).length)
const editorVisible = ref(false)
const editingId = ref<string | null>(null)
const editingOriginalType = ref<BotType | null>(null)
const formRef = ref<FormInstance>()
const testingWebhook = ref(false)
const testVisible = ref(false)
const testingConfig = ref<MessagePushConfig | null>(null)
const sending = ref(false)
const showGuide = ref(false)

const form = reactive({
  botType: 'webhook' as BotType,
  name: '',
  webhook: '',
  secret: '',
  appId: '',
  appSecret: '',
  receiveType: 'chat_id' as ReceiveType,
  receiveId: '',
  description: '',
  enabled: true,
})
const testForm = reactive({
  receiveType: 'chat_id' as ReceiveType,
  receiveId: '',
  type: 'card' as 'text' | 'card',
  title: 'QuantTrader 测试通知',
  content: '这是一条测试消息，收到此消息表示飞书机器人配置成功。',
})

const needsNewCredential = (type: BotType) => !editingId.value || editingOriginalType.value !== type
const rules: FormRules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  webhook: [{
    validator: (_rule, value: string, callback) => {
      if (form.botType !== 'webhook') callback()
      else if (!value && needsNewCredential('webhook')) callback(new Error('请输入 Webhook 地址'))
      else if (value && !/^https:\/\/open\.feishu\.cn\/open-apis\/bot\/v2\/hook\/.+/.test(value)) callback(new Error('请输入有效的飞书机器人 Webhook 地址'))
      else callback()
    },
    trigger: 'blur',
  }],
  appId: [{ validator: (_rule, value: string, callback) => form.botType === 'app' && !value && needsNewCredential('app') ? callback(new Error('请输入 App ID')) : callback(), trigger: 'blur' }],
  appSecret: [{ validator: (_rule, value: string, callback) => form.botType === 'app' && !value && needsNewCredential('app') ? callback(new Error('请输入 App Secret')) : callback(), trigger: 'blur' }],
  receiveId: [{ validator: (_rule, value: string, callback) => form.botType === 'app' && !value && needsNewCredential('app') ? callback(new Error('请输入默认接收 ID')) : callback(), trigger: 'blur' }],
}

async function fetchConfigs() {
  loading.value = true
  try {
    const result = await messagePushApi.getList()
    configs.value = result.list
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    botType: 'webhook', name: '', webhook: '', secret: '', appId: '', appSecret: '',
    receiveType: 'chat_id', receiveId: '', description: '', enabled: true,
  })
}

function openCreate() {
  editingId.value = null
  editingOriginalType.value = null
  resetForm()
  editorVisible.value = true
  nextTick(() => formRef.value?.clearValidate())
}

function openEdit(item: MessagePushConfig) {
  editingId.value = item.id
  editingOriginalType.value = item.botType
  Object.assign(form, {
    botType: item.botType,
    name: item.name,
    webhook: '',
    secret: '',
    appId: '',
    appSecret: '',
    receiveType: item.receiveType || 'chat_id',
    receiveId: '',
    description: item.description,
    enabled: item.enabled,
  })
  editorVisible.value = true
  nextTick(() => formRef.value?.clearValidate())
}

function formPayload(): MessagePushConfigPayload {
  const payload: MessagePushConfigPayload = {
    botType: form.botType,
    name: form.name.trim(),
    description: form.description.trim(),
    enabled: form.enabled,
  }
  if (form.botType === 'webhook') {
    if (form.webhook) payload.webhook = form.webhook.trim()
    if (form.secret) payload.secret = form.secret
  } else {
    if (form.appId) payload.appId = form.appId.trim()
    if (form.appSecret) payload.appSecret = form.appSecret
    payload.receiveType = form.receiveType
    if (form.receiveId) payload.receiveId = form.receiveId.trim()
  }
  return payload
}

async function saveConfig() {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  try {
    const payload = formPayload()
    if (editingId.value) await messagePushApi.update(editingId.value, payload)
    else await messagePushApi.create(payload)
    editorVisible.value = false
    ElMessage.success(editingId.value ? '配置已更新' : '机器人已添加')
    await fetchConfigs()
  } finally {
    saving.value = false
  }
}

async function validateConnection() {
  testingWebhook.value = true
  try {
    const credentialsEmpty = form.botType === 'webhook'
      ? !form.webhook && !form.secret
      : !form.appId && !form.appSecret
    let result
    if (editingId.value && editingOriginalType.value === form.botType && credentialsEmpty) {
      result = await messagePushApi.validateSaved(editingId.value)
    } else {
      const fields = form.botType === 'webhook' ? ['webhook'] : ['appId', 'appSecret']
      if (!await formRef.value?.validateField(fields).then(() => true).catch(() => false)) return
      result = await messagePushApi.validateDraft({
        botType: form.botType,
        webhook: form.webhook || undefined,
        secret: form.secret || undefined,
        appId: form.appId || undefined,
        appSecret: form.appSecret || undefined,
      })
    }
    result.success ? ElMessage.success(result.message) : ElMessage.warning(result.message)
    if (editingId.value) await fetchConfigs()
  } finally {
    testingWebhook.value = false
  }
}

async function toggleConfig(item: MessagePushConfig, value: boolean) {
  try {
    await messagePushApi.update(item.id, { enabled: value })
    item.enabled = value
    ElMessage.success(value ? '推送渠道已启用' : '推送渠道已停用')
  } catch {
    item.enabled = !value
  }
}

function openTest(item: MessagePushConfig) {
  testingConfig.value = item
  testForm.receiveType = item.receiveType || 'chat_id'
  testForm.receiveId = ''
  testVisible.value = true
}

async function sendTest() {
  if (!testingConfig.value || !testForm.content.trim()) {
    ElMessage.warning('请输入测试消息内容')
    return
  }
  sending.value = true
  try {
    const payload: TestMessagePayload = {
      messageType: testForm.type,
      title: testForm.type === 'card' ? testForm.title : undefined,
      content: testForm.content.trim(),
    }
    if (testingConfig.value.botType === 'app') {
      payload.receiveType = testForm.receiveType
      if (testForm.receiveId.trim()) payload.receiveId = testForm.receiveId.trim()
    }
    const result = await messagePushApi.sendTest(testingConfig.value.id, payload)
    if (result.success) {
      testVisible.value = false
      ElMessage.success(result.message)
    } else {
      ElMessage.warning(result.message)
    }
    await fetchConfigs()
  } finally {
    sending.value = false
  }
}

function handleCommand(command: string, item: MessagePushConfig) {
  if (command === 'edit') openEdit(item)
  if (command === 'delete') {
    ElMessageBox.confirm(`确定删除「${item.name}」吗？删除后将无法继续推送消息。`, '删除配置', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    }).then(async () => {
      await messagePushApi.remove(item.id)
      ElMessage.success('配置已删除')
      await fetchConfigs()
    }).catch(() => {})
  }
}

function botTypeLabel(value: BotType) {
  return value === 'app' ? '应用机器人' : '自定义机器人'
}

function receiverTypeLabel(value?: ReceiveType) {
  if (!value) return '未配置'
  return ({ chat_id: '群聊', open_id: 'Open ID', user_id: 'User ID', email: '邮箱' } as Record<ReceiveType, string>)[value]
}

function receiverPlaceholder(value: ReceiveType) {
  return ({ chat_id: 'oc_xxxxxxxxx', open_id: 'ou_xxxxxxxxx', user_id: 'xxxxxxxxx', email: 'name@example.com' } as Record<ReceiveType, string>)[value]
}

function formatDate(value?: string) {
  if (!value) return '尚未测试'
  return new Date(value).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

onMounted(fetchConfigs)
</script>

<style scoped>
.message-push-page { max-width: 1440px; margin: 0 auto; }

.page-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
}
.title-row { display: flex; align-items: center; gap: 10px; margin-bottom: 7px; }
.page-title { margin: 0; }
.page-desc { margin: 0; line-height: 1.65; }

.overview-grid {
  display: grid;
  grid-template-columns: minmax(180px, 0.7fr) minmax(180px, 0.7fr) minmax(320px, 1.4fr);
  gap: 14px;
  margin-bottom: 16px;
}
.overview-card {
  min-height: 94px;
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}
.metric-icon {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 11px;
  font-size: 22px;
}
.metric-icon.brand { color: #3370ff; background: #eef3ff; }
.metric-icon.success { color: var(--color-profit); background: var(--color-profit-bg); }
.metric-label { display: block; color: var(--color-text-muted); font-size: 12px; margin-bottom: 3px; }
.metric-value { color: var(--color-text-primary); font-size: 25px; line-height: 1.15; }
.status-card { justify-content: space-between; }
.status-main { display: flex; align-items: center; gap: 12px; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; box-shadow: 0 0 0 5px #f1f5f9; }
.status-dot.online { background: var(--color-profit); box-shadow: 0 0 0 5px var(--color-profit-bg); }
.status-dot.idle { background: var(--color-text-disabled); }
.service-status { display: block; color: var(--color-text-primary); font-size: 16px; }
.status-note { color: var(--color-text-muted); font-size: 12px; }

.content-card {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.section-header {
  min-height: 78px;
  padding: 18px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border-bottom: 1px solid var(--color-border);
}
.section-header h2 { margin: 0 0 4px; color: var(--color-text-primary); font-size: 16px; }
.section-header p { margin: 0; color: var(--color-text-muted); font-size: 12px; }
.channel-filter { display: flex; align-items: center; gap: 9px; color: var(--color-text-secondary); font-size: 12px; }
.config-list { padding: 8px 20px; }
.config-item {
  min-height: 130px;
  padding: 20px 2px;
  display: flex;
  align-items: flex-start;
  gap: 16px;
  border-bottom: 1px solid var(--color-border-light);
}
.config-item:last-child { border-bottom: 0; }
.channel-logo {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  color: #fff;
  background: #3370ff;
  border-radius: 13px;
  font-size: 24px;
  box-shadow: 0 6px 16px rgba(51, 112, 255, 0.18);
}
.channel-logo.small { width: 40px; height: 40px; border-radius: 10px; font-size: 20px; box-shadow: none; }
.config-main { flex: 1; min-width: 0; }
.config-title-row { display: flex; align-items: center; gap: 9px; margin-bottom: 7px; }
.config-title-row strong { color: var(--color-text-primary); font-size: 15px; }
.enabled-state { display: inline-flex; align-items: center; gap: 5px; color: var(--color-text-muted); font-size: 12px; }
.enabled-state i { width: 6px; height: 6px; border-radius: 50%; background: var(--color-text-disabled); }
.enabled-state.active { color: var(--color-profit); }
.enabled-state.active i { background: var(--color-profit); }
.config-desc { margin: 0 0 14px; color: var(--color-text-secondary); font-size: 13px; }
.config-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; color: var(--color-text-muted); font-size: 12px; }
.config-meta span { display: inline-flex; align-items: center; gap: 5px; }
.config-meta svg { width: 14px; height: 14px; }
.config-actions { display: flex; align-items: center; gap: 10px; align-self: center; }
.action-divider { width: 1px; height: 24px; margin: 0 2px; background: var(--color-border); }
.more-button { width: 36px; padding: 0 !important; }

.empty-state { padding: 64px 24px 72px; text-align: center; }
.empty-icon { width: 60px; height: 60px; display: grid; place-items: center; margin: 0 auto 16px; color: var(--color-primary); background: var(--color-primary-ghost); border-radius: 18px; font-size: 27px; }
.empty-state h3 { margin: 0 0 7px; color: var(--color-text-primary); font-size: 16px; }
.empty-state p { margin: 0 0 20px; color: var(--color-text-muted); font-size: 13px; }
.help-card { margin-top: 14px; padding: 15px 18px; display: flex; align-items: center; gap: 12px; color: var(--color-text-secondary); background: #f8fbff; border: 1px solid #dbeafe; border-radius: var(--radius-lg); }
.help-icon { color: var(--color-primary); font-size: 20px; }
.help-card div:nth-child(2) { flex: 1; }
.help-card strong { display: block; margin-bottom: 2px; color: var(--color-text-primary); font-size: 13px; }
.help-card p { margin: 0; color: var(--color-text-muted); font-size: 12px; }

.dialog-channel-banner, .test-target {
  margin-bottom: 22px;
  padding: 13px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  background: #f8fafc;
  border: 1px solid var(--color-border);
  border-radius: 10px;
}
.dialog-channel-banner > div:nth-child(2), .test-target > div:nth-child(2) { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.dialog-channel-banner strong, .test-target strong { color: var(--color-text-primary); font-size: 13px; }
.dialog-channel-banner span, .test-target span { color: var(--color-text-muted); font-size: 12px; }
.field-hint { margin-top: 6px; color: var(--color-text-muted); font-size: 11px; line-height: 1.5; }
.bot-type-grid { width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.bot-type-grid :deep(.el-radio) { width: 100%; height: auto; min-height: 70px; margin: 0; padding: 12px 14px; display: flex; align-items: center; }
.bot-type-grid :deep(.el-radio__label) { flex: 1; padding-left: 10px; }
.type-option { display: flex; align-items: center; gap: 10px; white-space: normal; }
.type-option > svg { width: 22px; height: 22px; color: var(--color-primary); flex: 0 0 auto; }
.type-option i { display: flex; flex-direction: column; gap: 3px; font-style: normal; }
.type-option b { color: var(--color-text-primary); font-size: 13px; }
.type-option small { color: var(--color-text-muted); font-size: 11px; line-height: 1.4; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.app-permission-note { margin: -2px 0 18px; padding: 10px 12px; display: flex; align-items: flex-start; gap: 7px; color: #1e40af; background: #eff6ff; border: 1px solid #dbeafe; border-radius: 8px; font-size: 11px; line-height: 1.55; }
.app-permission-note svg { width: 15px; height: 15px; flex: 0 0 auto; margin-top: 1px; }
.form-switch-row { padding: 13px 14px; display: flex; align-items: center; justify-content: space-between; gap: 20px; background: #f8fafc; border: 1px solid var(--color-border); border-radius: 10px; }
.form-switch-row strong { display: block; margin-bottom: 2px; color: var(--color-text-primary); font-size: 13px; }
.form-switch-row span { color: var(--color-text-muted); font-size: 11px; }
.message-preview { margin-top: 4px; padding: 16px; background: #f5f7fa; border-radius: 10px; }
.preview-label { display: block; margin-bottom: 10px; color: var(--color-text-muted); font-size: 11px; font-weight: 600; }
.feishu-preview { max-width: 430px; margin: 0 auto; padding: 14px 16px; background: #fff; border: 1px solid var(--color-border); border-radius: 9px; box-shadow: var(--shadow-sm); }
.feishu-preview.card { border-top: 4px solid #3370ff; }
.preview-title { margin-bottom: 10px; color: var(--color-text-primary); font-weight: 600; }
.feishu-preview p { margin: 0 0 12px; color: var(--color-text-secondary); font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
.feishu-preview span { color: var(--color-text-muted); font-size: 10px; }
.guide-list { list-style: none; counter-reset: step; }
.guide-list li { position: relative; padding: 0 0 22px 42px; counter-increment: step; }
.guide-list li:not(:last-child)::after { content: ''; position: absolute; left: 14px; top: 30px; bottom: 3px; width: 1px; background: var(--color-border); }
.guide-list li::before { content: counter(step); position: absolute; left: 0; top: 0; width: 28px; height: 28px; display: grid; place-items: center; color: var(--color-primary); background: var(--color-primary-ghost); border-radius: 50%; font-size: 12px; font-weight: 700; }
.guide-list b { display: block; margin-bottom: 3px; color: var(--color-text-primary); font-size: 13px; }
.guide-list span { color: var(--color-text-muted); font-size: 12px; }

@media (max-width: 1000px) {
  .overview-grid { grid-template-columns: 1fr 1fr; }
  .status-card { grid-column: 1 / -1; }
  .config-item { flex-wrap: wrap; }
  .config-actions { width: 100%; justify-content: flex-end; padding-left: 64px; }
}

@media (max-width: 700px) {
  .message-push-page { padding: 18px 16px 28px; }
  .page-heading { align-items: stretch; flex-direction: column; }
  .overview-grid { grid-template-columns: 1fr; }
  .status-card { grid-column: auto; }
  .status-note, .channel-filter { display: none; }
  .section-header { align-items: flex-start; }
  .config-main { width: calc(100% - 64px); }
  .config-meta { flex-direction: column; gap: 7px; }
  .config-actions { padding-left: 0; justify-content: flex-start; flex-wrap: wrap; }
  .help-card { align-items: flex-start; flex-wrap: wrap; }
  .bot-type-grid, .form-grid { grid-template-columns: 1fr; }
}
</style>
