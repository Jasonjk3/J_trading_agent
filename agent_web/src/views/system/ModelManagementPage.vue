<template>
  <div class="model-management-page page-content">
    <!-- 健康状态卡片 -->
    <div class="health-overview">
      <div class="health-card">
        <div class="health-icon" :class="healthStatus">
          <el-icon :size="24"><Monitor /></el-icon>
        </div>
        <div class="health-info">
          <span class="health-label">服务状态</span>
          <span class="health-value" :class="healthStatus">{{ healthStatusText }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="--sc: #38BDF8">
          <el-icon :size="20"><Cpu /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">模型总数</span>
          <span class="stat-value">{{ healthData?.total_models ?? 0 }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="--sc: #22C55E">
          <el-icon :size="20"><CircleCheck /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">可用模型</span>
          <span class="stat-value">{{ healthData?.available_models ?? 0 }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="--sc: #F59E0B">
          <el-icon :size="20"><Key /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">API 配置</span>
          <span class="stat-value">{{ healthData?.total_api_configs ?? 0 }}</span>
        </div>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="page-card">
      <el-tabs v-model="activeTab" class="management-tabs">
        <!-- 模型列表 Tab -->
        <el-tab-pane label="模型列表" name="models">
          <div class="tab-content">
            <div class="toolbar">
              <div class="toolbar-left">
                <el-button type="primary" @click="showModelDialog()">
                  <el-icon><Plus /></el-icon>添加模型
                </el-button>
                <el-button @click="handleTestAllModels" :loading="testingAll">
                  <el-icon><VideoPlay /></el-icon>测试全部
                </el-button>
              </div>
              <div class="toolbar-right">
                <el-select v-model="modelFilter.provider" placeholder="供应商" clearable style="width: 120px">
                  <el-option v-for="p in providers" :key="p" :label="p" :value="p" />
                </el-select>
                <el-select v-model="modelFilter.status" placeholder="状态" clearable style="width: 100px">
                  <el-option label="可用" value="available" />
                  <el-option label="不可用" value="unavailable" />
                  <el-option label="未知" value="unknown" />
                </el-select>
              </div>
            </div>

            <el-table table-layout="auto" :data="filteredModels" class="data-table" stripe row-key="id">
              <el-table-column prop="name" label="模型名称" min-width="180">
                <template #default="{ row }">
                  <div class="model-name-cell">
                    <span class="model-name">{{ row.name }}</span>
                    <span class="model-id">{{ row.model_id }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="provider" label="供应商" min-width="108" />
              <el-table-column prop="status" label="状态" min-width="108" align="center">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" size="small">
                    {{ statusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="tags" label="标签" min-width="188">
                <template #default="{ row }">
                  <el-tag
                    v-for="tag in (row.tags || []).slice(0, 3)"
                    :key="tag"
                    size="small"
                    class="model-tag"
                  >
                    {{ tag }}
                  </el-tag>
                  <span v-if="(row.tags || []).length > 3" class="more-tags">
                    +{{ row.tags.length - 3 }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="价格($/M)" min-width="148" align="right">
                <template #default="{ row }">
                  <div class="price-cell">
                    <span>入: {{ row.input_price_per_1m.toFixed(2) }}</span>
                    <span>出: {{ row.output_price_per_1m.toFixed(2) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="max_output_tokens" label="输出上限" min-width="108" align="right">
                <template #default="{ row }">
                  {{ row.max_output_tokens ?? row.max_tokens ?? '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="last_test_latency_ms" label="延迟" min-width="96" align="right">
                <template #default="{ row }">
                  {{ row.last_test_latency_ms ? `${row.last_test_latency_ms}ms` : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="is_active" label="启用" min-width="88" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.is_active" size="small" @change="handleToggleModel(row)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="180" align="center" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="handleTestModel(row)">测试</el-button>
                  <el-button link type="primary" size="small" @click="showModelDialog(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="handleDeleteModel(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- API 配置 Tab -->
        <el-tab-pane label="API 配置" name="api-configs">
          <div class="tab-content">
            <div class="toolbar">
              <el-button type="primary" @click="showApiConfigDialog()">
                <el-icon><Plus /></el-icon>添加配置
              </el-button>
            </div>

            <el-table table-layout="auto" :data="apiConfigs" class="data-table" stripe>
              <el-table-column prop="name" label="配置名称" min-width="150" />
              <el-table-column prop="provider" label="供应商" min-width="128" />
              <el-table-column prop="api_type" label="API 类型" min-width="116" />
              <el-table-column prop="api_key" label="API Key" min-width="208">
                <template #default="{ row }">
                  <span class="api-key-masked">{{ maskApiKey(row.api_key) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="api_url" label="API URL" min-width="200">
                <template #default="{ row }">
                  <span class="api-url">{{ row.api_url || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="is_default" label="默认" min-width="88" align="center">
                <template #default="{ row }">
                  <el-icon v-if="row.is_default" class="default-icon"><Select /></el-icon>
                </template>
              </el-table-column>
              <el-table-column prop="is_active" label="启用" min-width="88" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.is_active" size="small" @change="handleToggleApiConfig(row)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="180" align="center" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="handleSetDefaultConfig(row)" :disabled="row.is_default">
                    设为默认
                  </el-button>
                  <el-button link type="primary" size="small" @click="showApiConfigDialog(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="handleDeleteApiConfig(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>

        <!-- 标签管理 Tab -->
        <el-tab-pane label="标签管理" name="tags">
          <div class="tab-content">
            <div class="toolbar">
              <el-button type="primary" @click="showTagDialog()">
                <el-icon><Plus /></el-icon>添加标签
              </el-button>
            </div>

            <el-table table-layout="auto" :data="tags" class="data-table" stripe>
              <el-table-column prop="name" label="标签名称" min-width="156">
                <template #default="{ row }">
                  <el-tag :color="row.color" effect="dark" size="default">{{ row.name }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="color" label="颜色" min-width="108">
                <template #default="{ row }">
                  <div class="color-preview" :style="{ background: row.color || '#909399' }"></div>
                </template>
              </el-table-column>
              <el-table-column prop="description" label="描述" min-width="200">
                <template #default="{ row }">{{ row.description || '-' }}</template>
              </el-table-column>
              <el-table-column prop="sort_order" label="排序" min-width="96" align="center" />
              <el-table-column prop="is_active" label="启用" min-width="88" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.is_active" size="small" @change="handleToggleTag(row)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="140" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="showTagDialog(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="handleDeleteTag(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 模型编辑对话框 -->
    <el-dialog
      v-model="modelDialogVisible"
      :title="modelForm.id ? '编辑模型' : '添加模型'"
      width="760px"
      class="model-editor-dialog"
      destroy-on-close
    >
      <el-form
        ref="modelFormRef"
        :model="modelForm"
        :rules="modelRules"
        label-position="top"
        class="model-editor-form"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="模型 ID" prop="model_id">
              <el-input v-model="modelForm.model_id" :disabled="!!modelForm.id" placeholder="如 gpt-4o" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="显示名称" prop="name">
              <el-input v-model="modelForm.name" placeholder="如 GPT-4o" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="供应商" prop="provider">
              <el-input v-model="modelForm.provider" placeholder="如 OpenAI" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="API 配置">
              <el-select v-model="modelForm.api_config_id" placeholder="选择 API 配置" clearable style="width: 100%">
                <el-option
                  v-for="c in apiConfigs"
                  :key="c.id"
                  :label="`${c.name} (${c.provider})`"
                  :value="c.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="描述">
          <el-input v-model="modelForm.description" type="textarea" :rows="2" placeholder="模型描述" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="输入价格($/M)">
              <el-input-number v-model="modelForm.input_price_per_1m" :precision="4" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="输出价格($/M)">
              <el-input-number v-model="modelForm.output_price_per_1m" :precision="4" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="上下文 Tokens">
              <el-input-number v-model="modelForm.max_tokens" :min="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="输出 Tokens">
              <el-input-number
                v-model="modelForm.max_output_tokens"
                :min="1"
                placeholder="如 16384"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="排序权重">
              <el-input-number v-model="modelForm.sort_order" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-select v-model="modelForm.tags" multiple placeholder="选择标签" style="width: 100%">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.name" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12" class="capability-row">
          <el-col :span="8">
            <el-form-item label="流式输出">
              <el-switch v-model="modelForm.supports_streaming" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="思考模式">
              <el-switch v-model="modelForm.supports_thinking" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="max_completion">
              <el-switch v-model="modelForm.use_max_completion_tokens" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveModel">保存</el-button>
      </template>
    </el-dialog>

    <!-- API 配置对话框 -->
    <el-dialog
      v-model="apiConfigDialogVisible"
      :title="apiConfigForm.id ? '编辑 API 配置' : '添加 API 配置'"
      width="550px"
      destroy-on-close
    >
      <el-form :model="apiConfigForm" :rules="apiConfigRules" ref="apiConfigFormRef" label-width="100px">
        <el-form-item label="配置名称" prop="name">
          <el-input v-model="apiConfigForm.name" placeholder="如 OpenAI 官方" />
        </el-form-item>
        <el-form-item label="供应商" prop="provider">
          <el-input v-model="apiConfigForm.provider" placeholder="如 OpenAI" />
        </el-form-item>
        <el-form-item label="API 类型" prop="api_type">
          <el-select v-model="apiConfigForm.api_type" style="width: 100%">
            <el-option label="OpenAI 兼容" value="openai" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="通用" value="generic" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="apiConfigForm.api_key" type="password" show-password placeholder="sk-xxx" />
        </el-form-item>
        <el-form-item label="API URL">
          <el-input v-model="apiConfigForm.api_url" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="apiConfigForm.description" type="textarea" :rows="2" placeholder="配置描述" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="apiConfigForm.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="apiConfigDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveApiConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 标签对话框 -->
    <el-dialog
      v-model="tagDialogVisible"
      :title="tagForm.id ? '编辑标签' : '添加标签'"
      width="450px"
      destroy-on-close
    >
      <el-form :model="tagForm" :rules="tagRules" ref="tagFormRef" label-width="80px">
        <el-form-item label="标签名称" prop="name">
          <el-input v-model="tagForm.name" placeholder="如 对话" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="tagForm.color" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="tagForm.description" type="textarea" :rows="2" placeholder="标签描述" />
        </el-form-item>
        <el-form-item label="排序权重">
          <el-input-number v-model="tagForm.sort_order" :min="0" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tagDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveTag">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Monitor, Cpu, CircleCheck, Key, VideoPlay, Select } from '@element-plus/icons-vue'
import { modelManagementApi } from '@/api/modelManagement'
import type {
  ModelItem,
  ApiConfigItem,
  TagItem,
  HealthCheckResponse,
} from '@/api/modelManagement'

// ============================================================================
// 状态定义
// ============================================================================

const activeTab = ref('models')
const testingAll = ref(false)

// 健康数据
const healthData = ref<HealthCheckResponse | null>(null)

// 模型列表
const models = ref<ModelItem[]>([])
const modelFilter = ref({ provider: '', status: '' })

// API 配置
const apiConfigs = ref<ApiConfigItem[]>([])

// 标签
const tags = ref<TagItem[]>([])

// 模型对话框
const modelDialogVisible = ref(false)
const modelFormRef = ref<FormInstance>()
const modelForm = ref({
  id: null as number | null,
  model_id: '',
  name: '',
  provider: '',
  description: '',
  max_tokens: undefined as number | undefined,
  max_output_tokens: undefined as number | undefined,
  supports_streaming: true,
  supports_thinking: false,
  use_max_completion_tokens: false,
  input_price_per_1m: 0,
  output_price_per_1m: 0,
  api_config_id: undefined as number | undefined,
  tags: [] as string[],
  sort_order: 0,
})
const modelRules: FormRules = {
  model_id: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
  name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  provider: [{ required: true, message: '请输入供应商', trigger: 'blur' }],
}

// API 配置对话框
const apiConfigDialogVisible = ref(false)
const apiConfigFormRef = ref<FormInstance>()
const apiConfigForm = ref({
  id: null as number | null,
  name: '',
  provider: '',
  api_type: 'openai',
  api_key: '',
  api_url: '',
  description: '',
  is_default: false,
})
const apiConfigRules: FormRules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  provider: [{ required: true, message: '请输入供应商', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
}

// 标签对话框
const tagDialogVisible = ref(false)
const tagFormRef = ref<FormInstance>()
const tagForm = ref({
  id: null as number | null,
  name: '',
  color: '#409EFF',
  description: '',
  sort_order: 0,
})
const tagRules: FormRules = {
  name: [{ required: true, message: '请输入标签名称', trigger: 'blur' }],
}

// ============================================================================
// 计算属性
// ============================================================================

const healthStatus = computed(() => {
  if (!healthData.value) return 'unknown'
  return healthData.value.status === 'healthy' ? 'healthy' : 'unhealthy'
})

const healthStatusText = computed(() => {
  if (!healthData.value) return '加载中...'
  return healthData.value.status === 'healthy' ? '正常' : '异常'
})

const providers = computed(() => {
  const set = new Set(models.value.map((m) => m.provider))
  return Array.from(set)
})

const filteredModels = computed(() => {
  let result = models.value
  if (modelFilter.value.provider) {
    result = result.filter((m) => m.provider === modelFilter.value.provider)
  }
  if (modelFilter.value.status) {
    result = result.filter((m) => m.status === modelFilter.value.status)
  }
  return result
})

// ============================================================================
// 工具函数
// ============================================================================

function statusTagType(status: string): 'success' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'danger' | 'info'> = {
    available: 'success',
    unavailable: 'danger',
    unknown: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    available: '可用',
    unavailable: '不可用',
    unknown: '未知',
  }
  return map[status] || status
}

function maskApiKey(key: string): string {
  if (!key || key.length < 10) return key
  return key.slice(0, 6) + '****' + key.slice(-4)
}

// ============================================================================
// 数据获取
// ============================================================================

async function fetchHealthData() {
  try {
    healthData.value = await modelManagementApi.healthCheck()
  } catch (e: any) {
    console.error('获取健康数据失败', e)
  }
}

async function fetchModels() {
  try {
    const res = await modelManagementApi.getModels()
    models.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取模型列表失败')
  }
}

async function fetchApiConfigs() {
  try {
    const res = await modelManagementApi.getApiConfigs()
    apiConfigs.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取 API 配置失败')
  }
}

async function fetchTags() {
  try {
    const res = await modelManagementApi.getTags()
    tags.value = res.items || []
  } catch (e: any) {
    ElMessage.error(e?.message ?? '获取标签失败')
  }
}

// ============================================================================
// 模型操作
// ============================================================================

function showModelDialog(item?: ModelItem) {
  if (item) {
    modelForm.value = {
      id: item.id,
      model_id: item.model_id,
      name: item.name,
      provider: item.provider,
      description: item.description || '',
      max_tokens: item.max_tokens,
      max_output_tokens: item.max_output_tokens,
      supports_streaming: item.supports_streaming,
      supports_thinking: item.supports_thinking,
      use_max_completion_tokens: item.use_max_completion_tokens,
      input_price_per_1m: item.input_price_per_1m,
      output_price_per_1m: item.output_price_per_1m,
      api_config_id: item.api_config_id,
      tags: item.tags || [],
      sort_order: item.sort_order,
    }
  } else {
    modelForm.value = {
      id: null,
      model_id: '',
      name: '',
      provider: '',
      description: '',
      max_tokens: undefined,
      max_output_tokens: undefined,
      supports_streaming: true,
      supports_thinking: false,
      use_max_completion_tokens: false,
      input_price_per_1m: 0,
      output_price_per_1m: 0,
      api_config_id: undefined,
      tags: [],
      sort_order: 0,
    }
  }
  modelDialogVisible.value = true
}

async function handleSaveModel() {
  const valid = await modelFormRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    if (modelForm.value.id) {
      await modelManagementApi.updateModel(modelForm.value.id, {
        name: modelForm.value.name,
        provider: modelForm.value.provider,
        description: modelForm.value.description,
        max_tokens: modelForm.value.max_tokens,
        max_output_tokens: modelForm.value.max_output_tokens,
        supports_streaming: modelForm.value.supports_streaming,
        supports_thinking: modelForm.value.supports_thinking,
        use_max_completion_tokens: modelForm.value.use_max_completion_tokens,
        input_price_per_1m: modelForm.value.input_price_per_1m,
        output_price_per_1m: modelForm.value.output_price_per_1m,
        api_config_id: modelForm.value.api_config_id,
        tags: modelForm.value.tags,
        sort_order: modelForm.value.sort_order,
      })
      ElMessage.success('更新成功')
    } else {
      await modelManagementApi.createModel({
        model_id: modelForm.value.model_id,
        name: modelForm.value.name,
        provider: modelForm.value.provider,
        description: modelForm.value.description,
        max_tokens: modelForm.value.max_tokens,
        max_output_tokens: modelForm.value.max_output_tokens,
        supports_streaming: modelForm.value.supports_streaming,
        supports_thinking: modelForm.value.supports_thinking,
        use_max_completion_tokens: modelForm.value.use_max_completion_tokens,
        input_price_per_1m: modelForm.value.input_price_per_1m,
        output_price_per_1m: modelForm.value.output_price_per_1m,
        api_config_id: modelForm.value.api_config_id,
        tags: modelForm.value.tags,
        sort_order: modelForm.value.sort_order,
      })
      ElMessage.success('创建成功')
    }
    modelDialogVisible.value = false
    fetchModels()
    fetchHealthData()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  }
}

async function handleToggleModel(item: ModelItem) {
  try {
    await modelManagementApi.updateModel(item.id, { is_active: item.is_active })
    ElMessage.success(item.is_active ? '已启用' : '已停用')
    fetchHealthData()
  } catch (e: any) {
    item.is_active = !item.is_active
    ElMessage.error(e?.message ?? '操作失败')
  }
}

async function handleDeleteModel(item: ModelItem) {
  try {
    await ElMessageBox.confirm(`确定删除模型「${item.name}」吗？`, '删除确认', { type: 'warning' })
    await modelManagementApi.deleteModel(item.id)
    ElMessage.success('删除成功')
    fetchModels()
    fetchHealthData()
  } catch {
    // cancelled
  }
}

async function handleTestModel(item: ModelItem) {
  try {
    ElMessage.info(`正在测试模型「${item.name}」...`)
    const res = await modelManagementApi.testModels({ model_ids: [item.id] })
    const result = res.results[0]
    if (result.status === 'available') {
      ElMessage.success(`模型可用，延迟 ${result.latency_ms}ms`)
    } else {
      ElMessage.error(`模型不可用: ${result.error}`)
    }
    fetchModels()
    fetchHealthData()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '测试失败')
  }
}

async function handleTestAllModels() {
  testingAll.value = true
  try {
    ElMessage.info('正在测试所有模型...')
    const res = await modelManagementApi.testModels({})
    ElMessage.success(`测试完成：${res.available} 可用，${res.unavailable} 不可用`)
    fetchModels()
    fetchHealthData()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '测试失败')
  } finally {
    testingAll.value = false
  }
}

// ============================================================================
// API 配置操作
// ============================================================================

function showApiConfigDialog(item?: ApiConfigItem) {
  if (item) {
    apiConfigForm.value = {
      id: item.id,
      name: item.name,
      provider: item.provider,
      api_type: item.api_type,
      api_key: '',
      api_url: item.api_url || '',
      description: item.description || '',
      is_default: item.is_default,
    }
  } else {
    apiConfigForm.value = {
      id: null,
      name: '',
      provider: '',
      api_type: 'openai',
      api_key: '',
      api_url: '',
      description: '',
      is_default: false,
    }
  }
  apiConfigDialogVisible.value = true
}

async function handleSaveApiConfig() {
  const valid = await apiConfigFormRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    if (apiConfigForm.value.id) {
      const updateData: Record<string, any> = {
        name: apiConfigForm.value.name,
        provider: apiConfigForm.value.provider,
        api_type: apiConfigForm.value.api_type,
        api_url: apiConfigForm.value.api_url,
        description: apiConfigForm.value.description,
        is_default: apiConfigForm.value.is_default,
      }
      if (apiConfigForm.value.api_key) {
        updateData.api_key = apiConfigForm.value.api_key
      }
      await modelManagementApi.updateApiConfig(apiConfigForm.value.id, updateData)
      ElMessage.success('更新成功')
    } else {
      await modelManagementApi.createApiConfig({
        name: apiConfigForm.value.name,
        provider: apiConfigForm.value.provider,
        api_type: apiConfigForm.value.api_type,
        api_key: apiConfigForm.value.api_key,
        api_url: apiConfigForm.value.api_url,
        description: apiConfigForm.value.description,
        is_default: apiConfigForm.value.is_default,
      })
      ElMessage.success('创建成功')
    }
    apiConfigDialogVisible.value = false
    fetchApiConfigs()
    fetchHealthData()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  }
}

async function handleToggleApiConfig(item: ApiConfigItem) {
  try {
    await modelManagementApi.updateApiConfig(item.id, { is_active: item.is_active })
    ElMessage.success(item.is_active ? '已启用' : '已停用')
  } catch (e: any) {
    item.is_active = !item.is_active
    ElMessage.error(e?.message ?? '操作失败')
  }
}

async function handleSetDefaultConfig(item: ApiConfigItem) {
  try {
    await modelManagementApi.setDefaultApiConfig(item.id)
    ElMessage.success('设置成功')
    fetchApiConfigs()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '设置失败')
  }
}

async function handleDeleteApiConfig(item: ApiConfigItem) {
  try {
    await ElMessageBox.confirm(`确定删除配置「${item.name}」吗？`, '删除确认', { type: 'warning' })
    await modelManagementApi.deleteApiConfig(item.id)
    ElMessage.success('删除成功')
    fetchApiConfigs()
    fetchHealthData()
  } catch {
    // cancelled
  }
}

// ============================================================================
// 标签操作
// ============================================================================

function showTagDialog(item?: TagItem) {
  if (item) {
    tagForm.value = {
      id: item.id,
      name: item.name,
      color: item.color || '#409EFF',
      description: item.description || '',
      sort_order: item.sort_order,
    }
  } else {
    tagForm.value = {
      id: null,
      name: '',
      color: '#409EFF',
      description: '',
      sort_order: 0,
    }
  }
  tagDialogVisible.value = true
}

async function handleSaveTag() {
  const valid = await tagFormRef.value?.validate().catch(() => false)
  if (!valid) return

  try {
    if (tagForm.value.id) {
      await modelManagementApi.updateTag(tagForm.value.id, {
        name: tagForm.value.name,
        color: tagForm.value.color,
        description: tagForm.value.description,
        sort_order: tagForm.value.sort_order,
      })
      ElMessage.success('更新成功')
    } else {
      await modelManagementApi.createTag({
        name: tagForm.value.name,
        color: tagForm.value.color,
        description: tagForm.value.description,
        sort_order: tagForm.value.sort_order,
      })
      ElMessage.success('创建成功')
    }
    tagDialogVisible.value = false
    fetchTags()
  } catch (e: any) {
    ElMessage.error(e?.message ?? '保存失败')
  }
}

async function handleToggleTag(item: TagItem) {
  try {
    await modelManagementApi.updateTag(item.id, { is_active: item.is_active })
    ElMessage.success(item.is_active ? '已启用' : '已停用')
  } catch (e: any) {
    item.is_active = !item.is_active
    ElMessage.error(e?.message ?? '操作失败')
  }
}

async function handleDeleteTag(item: TagItem) {
  try {
    await ElMessageBox.confirm(`确定删除标签「${item.name}」吗？`, '删除确认', { type: 'warning' })
    await modelManagementApi.deleteTag(item.id)
    ElMessage.success('删除成功')
    fetchTags()
  } catch {
    // cancelled
  }
}

// ============================================================================
// Tab 切换加载
// ============================================================================

watch(activeTab, (tab) => {
  if (tab === 'models') {
    fetchModels()
  } else if (tab === 'api-configs') {
    fetchApiConfigs()
  } else if (tab === 'tags') {
    fetchTags()
  }
})

// ============================================================================
// 初始化
// ============================================================================

onMounted(async () => {
  await Promise.all([fetchHealthData(), fetchModels(), fetchApiConfigs(), fetchTags()])
})
</script>

<style scoped>
.model-management-page {
  max-width: 1400px;
}

.page-card {
  background: var(--color-bg-card);
  
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}

/* 健康状态区域 */
.health-overview {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.health-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: 14px;
}

.health-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-normal);
}

.health-icon.healthy {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.health-icon.unhealthy {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.health-icon.unknown {
  background: rgba(148, 163, 184, 0.15);
  color: #94a3b8;
}

.health-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.health-label {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
}

.health-value {
  font-size: 18px;
  font-weight: 600;
}

.health-value.healthy {
  color: #22c55e;
}

.health-value.unhealthy {
  color: #ef4444;
}

.health-value.unknown {
  color: #94a3b8;
}

.stat-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--sc) 15%, transparent);
  color: var(--sc);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-label {
  font-size: var(--font-size-caption);
  color: var(--color-text-muted);
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary);
}

/* Tab 内容 */
.tab-content {
  min-height: 400px;
}

/* 工具栏 */
.toolbar {
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

/* 表格 */
.data-table {
  width: 100%;
}

/* 模型名称单元格 */
.model-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-name {
  font-weight: 500;
  color: var(--color-text-primary);
}

.model-id {
  font-size: 12px;
  color: var(--color-text-muted);
  font-family: 'Monaco', 'Menlo', monospace;
}

/* 标签 */
.model-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.more-tags {
  font-size: 12px;
  color: var(--color-text-muted);
}

/* 价格单元格 */
.price-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

/* API Key 显示 */
.api-key-masked {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.api-url {
  font-size: 12px;
  color: var(--color-text-muted);
  word-break: break-all;
}

/* 默认图标 */
.default-icon {
  color: #22c55e;
  font-size: 18px;
}

/* 颜色预览 */
.color-preview {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid var(--color-border);
}


/* 模型编辑弹窗：顶部标签避免数字输入控件被标签挤压 */
:global(.model-editor-dialog) {
  max-width: calc(100vw - 32px);
}
:global(.model-editor-dialog .el-dialog__body) {
  max-height: min(70vh, 680px);
  overflow-y: auto;
}
:global(.model-editor-form .el-form-item) { margin-bottom: 18px; }
:global(.model-editor-form .el-form-item__label) {
  height: auto;
  padding: 0 0 7px;
  line-height: 1.3;
}
:global(.model-editor-form .el-input-number),
:global(.model-editor-form .el-select) { width: 100%; }
:global(.model-editor-form .el-input-number .el-input__wrapper),
:global(.model-editor-form .el-input__wrapper),
:global(.model-editor-form .el-select__wrapper) { min-height: 38px; }
:global(.model-editor-form .capability-row) {
  margin-top: 2px;
  padding: 12px 8px 0;
  background: #f8fafc;
  border: 1px solid var(--color-border);
  border-radius: 9px;
}
:global(.model-editor-form .capability-row .el-form-item) { margin-bottom: 12px; }
:global(.model-editor-form .capability-row .el-form-item__content) { min-height: 24px; }
/* 响应式 */
@media (max-width: 1200px) {
  .health-overview {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .health-overview {
    grid-template-columns: 1fr;
  }

  .toolbar {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }
}
</style>


