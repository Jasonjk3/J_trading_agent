<template>
  <main class="login-page">
    <section class="brand-panel" aria-label="产品介绍">
      <div class="brand-top">
        <div class="brand-mark" aria-hidden="true">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M4 14.5h3V20H4v-5.5Zm6.5-5h3V20h-3V9.5ZM17 4h3v16h-3V4Z" fill="currentColor" />
          </svg>
        </div>
        <div>
          <div class="brand-name">QuantTrader</div>
          <div class="brand-caption">多智能体量化交易平台</div>
        </div>
      </div>

      <div class="brand-content">
        <span class="eyebrow">AI QUANT WORKSPACE</span>
        <h1>让每一次交易决策<br />都有数据依据</h1>
        <p>聚合行情、策略、回测与风险控制，在一个工作台中管理你的智能交易 Agent。</p>

        <div class="feature-list">
          <div class="feature-item">
            <span class="feature-icon"><DataAnalysis /></span>
            <div><strong>实时洞察</strong><small>持续跟踪行情、收益与风险敞口</small></div>
          </div>
          <div class="feature-item">
            <span class="feature-icon"><Cpu /></span>
            <div><strong>Agent 协作</strong><small>统一配置并监控多种交易策略</small></div>
          </div>
          <div class="feature-item">
            <span class="feature-icon"><TrendCharts /></span>
            <div><strong>策略验证</strong><small>从历史回测到实盘执行完整闭环</small></div>
          </div>
        </div>
      </div>

      <div class="brand-footer">
        <span class="status-dot"></span>
        <span>系统服务运行正常</span>
        <span class="footer-separator"></span>
        <span>安全连接</span>
      </div>
    </section>

    <section class="form-panel">
      <div class="mobile-brand">
        <span class="mobile-mark"><DataLine /></span>
        <span>QuantTrader</span>
      </div>

      <div class="login-card">
        <header class="login-header">
          <span class="welcome-label">欢迎回来</span>
          <h2>登录你的账户</h2>
          <p>请输入账户信息，继续进入交易工作台</p>
        </header>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="login-form"
          @submit.prevent="onSubmit"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              size="large"
              :prefix-icon="User"
              clearable
              autocomplete="username"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              clearable
              autocomplete="current-password"
              @keyup.enter="onSubmit"
            />
          </el-form-item>

          <div class="form-options">
            <el-checkbox v-model="rememberMe">保持登录</el-checkbox>
            <span class="security-copy"><Lock /> 安全加密登录</span>
          </div>

          <el-form-item class="submit-row">
            <el-button
              type="primary"
              size="large"
              :loading="loading"
              class="submit-btn"
              @click="onSubmit"
            >
              <span>{{ loading ? '正在验证' : '登录工作台' }}</span>
              <ArrowRight v-if="!loading" class="submit-arrow" />
            </el-button>
          </el-form-item>
        </el-form>

        <div class="demo-tip">
          <InfoFilled />
          <span>演示环境支持使用任意用户名和密码登录</span>
        </div>
      </div>

      <footer class="form-footer">© 2026 QuantTrader · 智能交易，理性决策</footer>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  ArrowRight,
  Cpu,
  DataAnalysis,
  DataLine,
  InfoFilled,
  Lock,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { authApi } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const rememberMe = ref(true)
const form = reactive({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onSubmit() {
  if (!formRef.value || loading.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await authApi.login(form.username, form.password)
      userStore.setAuth(res.token, res.user)
      ElMessage.success('登录成功')
      const redirect = (route.query.redirect as string) || '/'
      router.push(redirect)
    } catch (e: any) {
      ElMessage.error(e?.message || '登录失败')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(420px, 46%) 1fr;
  background: #fff;
}

.brand-panel {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  padding: 40px clamp(40px, 5vw, 80px);
  color: #fff;
  background: #1d4ed8;
  overflow: hidden;
}

.brand-panel::before,
.brand-panel::after {
  content: '';
  position: absolute;
  pointer-events: none;
}

.brand-panel::before {
  width: 420px;
  height: 420px;
  right: -210px;
  top: 16%;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 50%;
}

.brand-panel::after {
  width: 260px;
  height: 260px;
  right: -130px;
  top: calc(16% + 80px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 50%;
}

.brand-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  color: #2563eb;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.14);
}

.brand-name { font-size: 18px; line-height: 1.2; font-weight: 700; letter-spacing: -0.02em; }
.brand-caption { margin-top: 3px; color: rgba(255, 255, 255, 0.66); font-size: 12px; }

.brand-content {
  position: relative;
  z-index: 1;
  width: min(520px, 100%);
  margin: auto 0;
  padding: 64px 0;
}

.eyebrow {
  display: inline-flex;
  padding: 6px 10px;
  color: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.brand-content h1 {
  margin: 24px 0 18px;
  font-size: clamp(36px, 4vw, 54px);
  line-height: 1.16;
  font-weight: 700;
  letter-spacing: -0.04em;
}

.brand-content > p {
  max-width: 470px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 16px;
  line-height: 1.8;
}

.feature-list { display: grid; gap: 18px; margin-top: 44px; }
.feature-item { display: flex; align-items: center; gap: 14px; }
.feature-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  color: #fff;
  background: rgba(255, 255, 255, 0.11);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 8px;
}
.feature-icon :deep(svg) { width: 18px; height: 18px; }
.feature-item div { display: flex; flex-direction: column; gap: 2px; }
.feature-item strong { font-size: 14px; font-weight: 600; }
.feature-item small { color: rgba(255, 255, 255, 0.62); font-size: 12px; }

.brand-footer {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 12px;
}
.status-dot { width: 7px; height: 7px; background: #4ade80; border-radius: 50%; box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.13); }
.footer-separator { width: 1px; height: 12px; margin: 0 4px; background: rgba(255, 255, 255, 0.24); }

.form-panel {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px clamp(28px, 7vw, 100px) 28px;
  background: #fff;
}

.mobile-brand { display: none; }
.login-card { width: min(420px, 100%); animation: card-enter 420ms cubic-bezier(0.2, 0.8, 0.2, 1) both; }
.welcome-label { color: #2563eb; font-size: 13px; font-weight: 700; }
.login-header h2 { margin: 10px 0 8px; color: #0f172a; font-size: 30px; line-height: 1.2; font-weight: 700; letter-spacing: -0.03em; }
.login-header p { color: #64748b; font-size: 14px; }
.login-form { margin-top: 34px; }
.login-form :deep(.el-form-item) { margin-bottom: 22px; }
.login-form :deep(.el-form-item__label) { padding-bottom: 8px; color: #334155 !important; }
.login-form :deep(.el-input__wrapper) { min-height: 46px; padding: 0 14px; }

.form-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: -4px 0 24px;
}
.security-copy { display: inline-flex; align-items: center; gap: 5px; color: #94a3b8; font-size: 12px; }
.security-copy :deep(svg) { width: 13px; height: 13px; }
.submit-row { margin-bottom: 18px !important; }
.submit-btn { width: 100%; height: 46px; font-size: 14px; }
.submit-btn :deep(span) { width: 100%; display: flex; align-items: center; justify-content: center; gap: 8px; }
.submit-arrow { width: 16px; transition: transform 180ms cubic-bezier(0.2, 0, 0, 1); }
.submit-btn:hover .submit-arrow { transform: translateX(3px); }

.demo-tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 14px;
  color: #475569;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
}
.demo-tip :deep(svg) { width: 15px; height: 15px; margin-top: 1px; flex: 0 0 auto; color: #2563eb; }
.form-footer { margin-top: auto; padding-top: 50px; color: #94a3b8; font-size: 12px; text-align: center; }

@keyframes card-enter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
  .login-page { display: block; background: #f6f8fb; }
  .brand-panel { display: none; }
  .form-panel { min-height: 100vh; justify-content: flex-start; padding: 28px 24px; background: #f6f8fb; }
  .mobile-brand { width: min(420px, 100%); display: flex; align-items: center; gap: 10px; color: #0f172a; font-size: 16px; font-weight: 700; }
  .mobile-mark { width: 34px; height: 34px; display: grid; place-items: center; color: #fff; background: #2563eb; border-radius: 8px; }
  .login-card { margin: auto 0; padding: 28px; background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07); }
  .form-footer { margin-top: 0; padding-top: 28px; }
}

@media (max-width: 480px) {
  .form-panel { padding: 22px 16px; }
  .login-card { padding: 24px 20px; }
  .login-header h2 { font-size: 26px; }
  .form-options { align-items: flex-start; gap: 12px; }
  .security-copy { margin-top: 3px; }
}
</style>
