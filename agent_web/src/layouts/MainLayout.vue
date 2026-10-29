<template>
  <el-container class="main-layout">
    <el-aside :width="asideWidth" class="aside">
      <div class="logo">
        <div class="logo-mark">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5z" fill="#2563EB" />
            <path d="M2 17l10 5 10-5" stroke="#2563EB" stroke-width="2" fill="none" />
            <path d="M2 12l10 5 10-5" stroke="#2563EB" stroke-width="2" fill="none" />
          </svg>
        </div>
        <transition name="fade-text">
          <span v-if="!collapsed" class="logo-text">QuantTrader</span>
        </transition>
      </div>
      <el-menu
        :default-active="activeMenu"
        :default-openeds="defaultOpeneds"
        :collapse="collapsed"
        :collapse-transition="false"
        :unique-opened="false"
        popper-effect="light"
        router
        class="aside-menu"
      >
        <el-menu-item index="/market">
          <el-icon><Histogram /></el-icon>
          <template #title>大盘走势</template>
        </el-menu-item>

        <el-menu-item index="/assistant">
          <el-icon><ChatDotRound /></el-icon>
          <template #title>智能助手</template>
        </el-menu-item>

        <!-- 工作台 -->
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon>
          <template #title>工作台</template>
        </el-menu-item>

        <!-- 交易中心 -->
        <el-sub-menu index="trade">
          <template #title>
            <el-icon><Briefcase /></el-icon>
            <span>交易中心</span>
          </template>
          <el-menu-item index="/agents">
            <el-icon><Cpu /></el-icon>
            <template #title>Agent 交易</template>
          </el-menu-item>
          <el-menu-item index="/backtest">
            <el-icon><Timer /></el-icon>
            <template #title>模拟回测</template>
          </el-menu-item>
          <el-menu-item index="/paper-trading">
            <el-icon><Wallet /></el-icon>
            <template #title>模拟盘</template>
          </el-menu-item>
          <el-menu-item index="/positions">
            <el-icon><TrendCharts /></el-icon>
            <template #title>持仓管理</template>
          </el-menu-item>
          <el-menu-item index="/orders">
            <el-icon><List /></el-icon>
            <template #title>交易记录</template>
          </el-menu-item>
        </el-sub-menu>

        <!-- 数据分析 -->
        <el-sub-menu index="analysis">
          <template #title>
            <el-icon><DataAnalysis /></el-icon>
            <span>数据分析</span>
          </template>
          <el-menu-item index="/analytics">
            <el-icon><PieChart /></el-icon>
            <template #title>收益分析</template>
          </el-menu-item>
          <el-menu-item index="/technical-analysis">
            <el-icon><TrendCharts /></el-icon>
            <template #title>技术指标分析</template>
          </el-menu-item>
          <el-menu-item index="/news-intelligence">
            <el-icon><Reading /></el-icon>
            <template #title>消息面分析</template>
          </el-menu-item>
        </el-sub-menu>

        <!-- 工具 -->
        <el-sub-menu index="tools">
          <template #title>
            <el-icon><ToolsIcon /></el-icon>
            <span>工具</span>
          </template>
          <el-menu-item index="/data-monitor">
            <el-icon><Aim /></el-icon>
            <template #title>数据监控</template>
          </el-menu-item>
        </el-sub-menu>

        <!-- 系统管理 -->
        <el-sub-menu index="system">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/users">
            <el-icon><User /></el-icon>
            <template #title>用户管理</template>
          </el-menu-item>
          <el-menu-item index="/exchange-accounts">
            <el-icon><Connection /></el-icon>
            <template #title>交易所配置</template>
          </el-menu-item>
          <el-menu-item index="/llm-monitor">
            <el-icon><Odometer /></el-icon>
            <template #title>LLM 监控</template>
          </el-menu-item>
          <el-menu-item index="/model-management">
            <el-icon><Cpu /></el-icon>
            <template #title>模型管理</template>
          </el-menu-item>
          <el-menu-item index="/message-push">
            <el-icon><Bell /></el-icon>
            <template #title>消息推送</template>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
      <div class="aside-footer">
        <div class="collapse-trigger" @click="collapsed = !collapsed">
          <el-icon v-if="collapsed"><Expand /></el-icon>
          <el-icon v-else><Fold /></el-icon>
        </div>
      </div>
    </el-aside>
    <el-container direction="vertical">
      <el-header class="header">
        <div class="header-left">
          <el-breadcrumb separator="/" class="breadcrumb">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentTitle">{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <span class="username">{{ userStore.user?.username }}</span>
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="avatar-wrap">
              <el-icon class="avatar-icon"><UserFilled /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DataLine,
  ChatDotRound,
  User,
  Connection,
  TrendCharts,
  Cpu,
  List,
  PieChart,
  Histogram,
  Expand,
  Fold,
  UserFilled,
  Briefcase,
  DataAnalysis,
  Setting,
  Timer,
  Odometer,
  Reading,
  Wallet,
  Bell,
  Aim,
  Tools as ToolsIcon,
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const collapsed = ref(false)
const asideWidth = computed(() => (collapsed.value ? '68px' : '230px'))
const activeMenu = computed(() => {
  const p = route.path
  if (p.startsWith('/technical-analysis')) return '/technical-analysis'
  return p
})
const currentTitle = computed(() => (route.meta.title as string) ?? '')

const defaultOpeneds = computed(() => {
  const path = route.path
  if (['/agents', '/backtest', '/paper-trading', '/positions', '/orders'].some(p => path.startsWith(p))) {
    return ['trade']
  }
  if (['/analytics', '/technical-analysis', '/news-intelligence'].some(p => path.startsWith(p))) {
    return ['analysis']
  }
  if (path.startsWith('/data-monitor')) return ['tools']
  if (['/users', '/exchange-accounts', '/llm-monitor', '/model-management', '/message-push'].includes(path)) {
    return ['system']
  }
  return []
})

function handleCommand(cmd: string) {
  if (cmd === 'logout') {
    userStore.logout()
    router.push('/login')
  } else if (cmd === 'profile') {
    router.push('/profile')
  }
}
</script>

<style scoped>
.main-layout {
  height: 100vh;
  width: 100%;
  max-width: 100vw;
  overflow: hidden;
  background: var(--color-bg-base);
}

/* ---- 侧边栏 ---- */
.aside {
  background: #FFFFFF;
  border-right: 1px solid var(--color-border);
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.logo-mark {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
}
.logo-text {
  font-weight: 700;
  font-size: 16px;
  color: var(--color-text-primary);
  white-space: nowrap;
  letter-spacing: -0.02em;
}

.aside-menu {
  flex: 1;
  border-right: none;
  background: transparent !important;
  padding: 12px 8px;
  overflow-y: auto;
}

.aside-menu :deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin-bottom: 2px;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
  font-size: var(--font-size-nav);
}

.aside-menu :deep(.el-menu-item:hover) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.aside-menu :deep(.el-menu-item.is-active) {
  background: var(--color-primary-ghost) !important;
  color: var(--color-primary) !important;
  font-weight: 600;
  position: relative;
}
.aside-menu :deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  border-radius: 0 2px 2px 0;
  background: var(--color-primary);
}

.aside-menu :deep(.el-menu-item .el-icon) {
  font-size: 18px;
}

/* 子菜单样式 */
.aside-menu :deep(.el-sub-menu) {
  margin-bottom: 2px;
}

.aside-menu :deep(.el-sub-menu__title) {
  height: 44px;
  line-height: 44px;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
  font-size: var(--font-size-nav);
}

.aside-menu :deep(.el-sub-menu__title:hover) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.aside-menu :deep(.el-sub-menu__title .el-icon) {
  font-size: 18px;
}

.aside-menu :deep(.el-sub-menu.is-opened > .el-sub-menu__title) {
  color: var(--color-text-primary);
}

.aside-menu :deep(.el-sub-menu .el-menu) {
  background: transparent !important;
}

.aside-menu :deep(.el-sub-menu .el-menu-item) {
  height: 40px;
  line-height: 40px;
  padding-left: 48px !important;
  font-size: 13px;
}

.aside-menu :deep(.el-sub-menu .el-menu-item .el-icon) {
  font-size: 16px;
}

/* 折叠状态下的子菜单弹出样式 */
.aside-menu :deep(.el-menu--collapse .el-sub-menu__title span) {
  display: none;
}

.aside-menu :deep(.el-menu--collapse .el-sub-menu__title .el-sub-menu__icon-arrow) {
  display: none;
}

.aside-footer {
  padding: 12px;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}
.collapse-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--color-text-muted);
  transition: all var(--transition-fast);
}
.collapse-trigger:hover {
  background: var(--color-bg-hover);
  color: var(--color-primary);
}

/* ---- 顶栏 ---- */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 64px;
  background: #FFFFFF;
  
  border-bottom: 1px solid var(--color-border);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.username {
  font-size: var(--font-size-body);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.avatar-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-primary);
  cursor: pointer;
  transition: box-shadow var(--transition-fast);
}
.avatar-wrap:hover {
  box-shadow: var(--shadow-glow);
}
.avatar-icon {
  font-size: 18px;
  color: #fff;
}

/* ---- 内容区 ---- */
.main {
  background: var(--color-bg-base);
  padding: 0;
  overflow: auto;
  min-width: 0;
}

.main-layout :deep(.el-container) {
  min-width: 0;
}

/* ---- 过渡动画 ---- */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-fade-leave-to {
  opacity: 0;
}

.fade-text-enter-active,
.fade-text-leave-active {
  transition: opacity 0.2s ease;
}
.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
}
</style>



