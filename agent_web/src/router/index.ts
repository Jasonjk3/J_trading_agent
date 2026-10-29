import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/LoginPage.vue'),
    meta: { layout: 'blank', public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'assistant',
        name: 'Assistant',
        component: () => import('@/views/assistant/AssistantPage.vue'),
        meta: { title: '智能助手' },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardPage.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/users/UserListPage.vue'),
        meta: { title: '用户管理' },
      },
      {
        path: 'exchange-accounts',
        name: 'ExchangeAccounts',
        component: () => import('@/views/exchange/ExchangeListPage.vue'),
        meta: { title: '交易所配置' },
      },
      {
        path: 'llm-monitor',
        name: 'LLMMonitor',
        component: () => import('@/views/system/LLMMonitorPage.vue'),
        meta: { title: 'LLM 监控' },
      },
      {
        path: 'model-management',
        name: 'ModelManagement',
        component: () => import('@/views/system/ModelManagementPage.vue'),
        meta: { title: '模型管理' },
      },
      {
        path: 'message-push',
        name: 'MessagePushManagement',
        component: () => import('@/views/system/MessagePushManagementPage.vue'),
        meta: { title: '消息推送管理' },
      },
      {
        path: 'data-monitor',
        name: 'DataMonitor',
        component: () => import('@/views/tools/DataMonitorPage.vue'),
        meta: { title: '数据监控' },
      },
      {
        path: 'positions',
        name: 'Positions',
        component: () => import('@/views/positions/PositionListPage.vue'),
        meta: { title: '持仓管理' },
      },
      {
        path: 'agents',
        name: 'AgentWorkspace',
        component: () => import('@/views/agents/AgentWorkspace.vue'),
        meta: { title: 'Agent 交易' },
      },
      {
        path: 'agents/:id',
        name: 'AgentDetail',
        component: () => import('@/views/agents/AgentWorkspace.vue'),
        meta: { title: 'Agent 交易' },
      },
      {
        path: 'backtest',
        name: 'Backtest',
        component: () => import('@/views/backtest/BacktestListPage.vue'),
        meta: { title: '模拟回测' },
      },
      {
        path: 'paper-trading',
        name: 'PaperTrading',
        component: () => import('@/views/paperTrading/PaperTradingPage.vue'),
        meta: { title: '模拟盘' },
      },
      {
        path: 'backtest/create',
        name: 'BacktestCreate',
        component: () => import('@/views/backtest/BacktestCreatePage.vue'),
        meta: { title: '创建回测' },
      },
      {
        path: 'backtest/:id',
        name: 'BacktestDetail',
        component: () => import('@/views/backtest/BacktestDetailPage.vue'),
        meta: { title: '回测详情' },
      },
      {
        path: 'orders',
        name: 'Orders',
        component: () => import('@/views/orders/OrderListPage.vue'),
        meta: { title: '交易记录' },
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/views/analytics/AnalyticsPage.vue'),
        meta: { title: '收益分析' },
      },
      {
        path: 'technical-analysis/record/:recordId',
        name: 'TechnicalAnalysisRecord',
        component: () => import('@/views/analytics/TechnicalAnalysisReportPage.vue'),
        meta: { title: '技术分析报告' },
      },
      {
        path: 'technical-analysis/report',
        name: 'TechnicalAnalysisReportPreview',
        component: () => import('@/views/analytics/TechnicalAnalysisReportPage.vue'),
        meta: { title: '技术分析报告' },
      },
      {
        path: 'technical-analysis',
        name: 'TechnicalAnalysis',
        component: () => import('@/views/analytics/TechnicalAnalysisPage.vue'),
        meta: { title: '技术指标分析' },
      },
      {
        path: 'market',
        name: 'Market',
        component: () => import('@/views/market/CryptoMarketPage.vue'),
        meta: { title: '大盘走势' },
      },
      {
        path: 'news-intelligence',
        name: 'NewsIntelligence',
        component: () => import('@/views/newsIntelligence/NewsIntelligenceListPage.vue'),
        meta: { title: '消息面分析' },
      },
      {
        path: 'news-intelligence/create',
        name: 'NewsIntelligenceCreate',
        component: () => import('@/views/newsIntelligence/NewsIntelligenceFormPage.vue'),
        meta: { title: '创建消息面采集' },
      },
      {
        path: 'news-intelligence/:id/edit',
        name: 'NewsIntelligenceEdit',
        component: () => import('@/views/newsIntelligence/NewsIntelligenceFormPage.vue'),
        meta: { title: '编辑消息面采集' },
      },
      {
        path: 'news-intelligence/:id',
        name: 'NewsIntelligenceDetail',
        component: () => import('@/views/newsIntelligence/NewsIntelligenceDetailPage.vue'),
        meta: { title: '资讯时间轴' },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/ProfilePage.vue'),
        meta: { title: '个人中心' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/NotFoundPage.vue'),
    meta: { layout: 'blank', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()
  const isPublic = to.meta.public === true
  if (isPublic) {
    if (to.path === '/login' && userStore.token) {
      next({ path: '/' })
    } else {
      next()
    }
    return
  }
  if (to.meta.requiresAuth !== false && !userStore.token) {
    next({ path: '/login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})

export default router
