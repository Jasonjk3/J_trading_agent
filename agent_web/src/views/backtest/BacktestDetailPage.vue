<template>
  <div class="backtest-detail-page">
    <header class="page-header">
      <div class="header-left">
        <el-button class="back-btn" text @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
        <div class="title-group">
          <div class="title-row">
            <h1 class="page-title" :title="backtest?.name || '回测详情'">{{ backtest?.name || '回测详情' }}</h1>
            <div
              v-if="backtest"
              class="status-badge"
              :class="`status-badge--${backtest.status}`"
            >
              <span class="status-dot"></span>
              {{ getStatusText(backtest.status) }}
            </div>
            <template v-if="backtest && isLivePhase">
              <span class="header-chip">{{ backtest.config.symbols.join(' / ') }}</span>
              <span class="header-chip">{{ formatIntervalText(backtest.config.interval) }}</span>
              <span class="header-chip mono">{{ formatMoney(backtest.config.initialCapital) }} USDT</span>
              <span class="header-chip header-chip--range mono">{{ backtest.config.startTime }} → {{ backtest.config.endTime }}</span>
            </template>
          </div>
          <p v-if="!isLivePhase" class="page-subtitle">{{ statusLeadText }}</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button
          v-if="backtest?.status === 'completed' || backtest?.status === 'failed' || backtest?.status === 'cancelled'"
          type="primary"
          :loading="rerunning"
          @click="handleRerun"
        >
          <el-icon><RefreshRight /></el-icon>
          重新回测
        </el-button>
        <el-button
          v-if="backtest?.status === 'completed'"
          :loading="exporting"
          @click="handleExport"
        >
          <el-icon><Download /></el-icon>
          导出报告
        </el-button>
        <el-button
          v-if="backtest?.status === 'running' || backtest?.status === 'pending'"
          type="danger"
          plain
          @click="handleStop"
        >
          {{ backtest?.status === 'pending' ? '取消任务' : '停止回测' }}
        </el-button>
      </div>
    </header>

    <div v-loading="loading" class="detail-content">
      <!-- 失败信息置顶展示，但不再遮挡中断前已经生成的执行记录。 -->
      <div v-if="backtest?.status === 'failed' || backtest?.status === 'cancelled'" class="failed-panel">
        <div class="failed-icon-wrap">
          <el-icon class="failed-icon"><CircleClose /></el-icon>
        </div>
        <div class="failed-content">
          <h3 class="failed-title">{{ backtest.status === 'cancelled' ? '回测已取消' : '回测失败' }}</h3>
          <p class="failed-message">{{ backtest.errorMessage || '未知错误' }}</p>
          <p v-if="hasHistoricalRecords" class="failed-history-hint">
            已保留失败前产生的执行记录，可在下方继续查看。
          </p>
          <p v-else class="failed-history-hint">
            本次任务在产生可查看的执行记录前结束。
          </p>
          <el-button type="primary" :loading="rerunning" @click="handleRerun">
            <el-icon><RefreshRight /></el-icon>
            重新回测
          </el-button>
        </div>
      </div>

      <!-- ========== 运行中：作战台 ========== -->
      <template v-if="backtest && isLivePhase">
        <LiveProgressStrip
          :status="backtest.status"
          :progress="progress"
          :message="progressMessage"
          :current-time="runningDetail.currentTime"
          :current-step="runningDetail.currentStep"
          :total-steps="runningDetail.totalSteps"
          :last-action="liveLastAction"
          @focus-action="handleFocusAction"
        />

        <div class="mission-grid">
          <div class="mission-col mission-col--center chart-panel chart-panel--mission">
            <div class="panel-header panel-header--compact">
              <div class="live-chart-tabs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  class="live-chart-tab"
                  :class="{ 'is-active': liveChartTab === 'equity' }"
                  :aria-selected="liveChartTab === 'equity'"
                  @click="liveChartTab = 'equity'"
                >
                  <span class="tab-eyebrow">CHART</span>
                  <span class="tab-label">实时收益曲线</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  class="live-chart-tab"
                  :class="{ 'is-active': liveChartTab === 'market' }"
                  :aria-selected="liveChartTab === 'market'"
                  @click="liveChartTab = 'market'"
                >
                  <span class="tab-eyebrow">MARKET</span>
                  <span class="tab-label">标的走势</span>
                </button>
              </div>
              <div v-if="liveChartTab === 'market'" class="panel-actions">
                <el-checkbox
                  v-model="showFutureKlines"
                  class="future-kline-toggle"
                  title="仅影响图表展示，不会把未来行情传给交易决策"
                >
                  显示未来K线
                </el-checkbox>
                <el-select
                  v-if="(backtest.config.symbols?.length ?? 0) > 1"
                  v-model="selectedKlineSymbol"
                  size="small"
                  class="symbol-select"
                >
                  <el-option
                    v-for="sym in backtest.config.symbols"
                    :key="sym"
                    :label="positionSymbolLabel(sym)"
                    :value="sym"
                  />
                </el-select>
                <el-button
                  v-if="runningDetail.currentTime"
                  size="small"
                  text
                  type="primary"
                  @click="jumpToSimTime"
                >
                  定位 NOW
                </el-button>
                <span class="panel-hint">
                  最终决策用紫色定位线显示 · B 表示买入 · S 表示卖出
                </span>
              </div>
              <span v-else class="panel-hint">累计总收益 / 权益随回测推进更新</span>
            </div>

            <div v-show="liveChartTab === 'equity'" class="live-chart-pane">
              <div v-if="currentEquityCurve.length > 0" class="chart-container chart-container--live">
                <EquityCurveChart
                  title="实时收益曲线"
                  :equity-curve="currentEquityCurve"
                  :initial-capital="backtest.config.initialCapital || 0"
                />
              </div>
              <div v-else class="chart-empty chart-empty--live">
                <el-icon class="empty-icon"><TrendCharts /></el-icon>
                <span class="empty-text">等待收益曲线数据生成...</span>
              </div>
            </div>

            <div v-show="liveChartTab === 'market'" class="live-chart-pane">
              <BacktestKlineChart
                v-if="selectedKlineSymbol"
                ref="liveKlineRef"
                :backtest-id="backtest.id"
                :symbol="selectedKlineSymbol"
                :interval="backtest.config.interval"
                :start-time="backtest.config.startTime"
                :end-time="backtest.config.endTime"
                :trades="klineTrades"
                :positions="liveOpenPositions"
                :current-time="runningDetail.currentTime || backtest.config.startTime"
                :show-future-klines="showFutureKlines"
                :focus-time="klineFocusTime"
                :focus-decision="klineFocusDecision"
                @trade-click="handleTradeClick"
              />
            </div>
          </div>

          <DecisionStreamPanel
            class="mission-col mission-col--right"
            :backtest-id="backtest.id"
            :decisions="currentDecisionLog"
            :total="currentDecisionTotal"
            :page="remoteDecisionsPage"
            :page-size="remoteDecisionsPageSize"
            :truncated-hint="liveDecisionTruncatedHint"
            :auto-follow="true"
            :active-orders="liveActiveOrders"
            @focus-symbol="onSelectSymbol"
            @focus-decision="handleFocusDecision"
            @page-change="onLiveDecisionsPage"
          />
        </div>

        <LiveTradeManagerPanel
          :positions="liveOpenPositions"
          :orders="liveActiveOrders"
          :balance="liveBalance"
          :equity="liveEquity"
          :active-symbol="selectedKlineSymbol"
          :current-time="runningDetail.currentTime || backtest.config.startTime"
          @select-symbol="onSelectPosition"
        />

        <div class="live-footer">
          <div class="live-stats-strip">
            <div class="live-stat">
              <span class="live-stat-label">当前权益</span>
              <span class="live-stat-value mono">{{ formatMoney(liveEquity) }}</span>
            </div>
            <div class="live-stat">
              <span class="live-stat-label">累计收益</span>
              <span
                class="live-stat-value mono"
                :class="liveReturnPct >= 0 ? 'text-profit' : 'text-loss'"
              >
                {{ liveReturnPct >= 0 ? '+' : '' }}{{ liveReturnPct.toFixed(2) }}%
              </span>
            </div>
            <div class="live-stat">
              <span class="live-stat-label">成交</span>
              <span class="live-stat-value mono">{{ currentTradeTotal }}</span>
            </div>
            <div class="live-stat">
              <span class="live-stat-label">已平仓</span>
              <span class="live-stat-value mono">{{ currentStatistics?.closedTrades ?? 0 }}</span>
            </div>
            <el-button
              class="footer-toggle"
              text
              size="small"
              @click="liveFooterExpanded = !liveFooterExpanded"
            >
              {{ liveFooterExpanded ? '收起成交' : '展开成交' }}
            </el-button>
          </div>

          <div v-if="liveFooterExpanded" class="live-footer-body">
            <div class="chart-panel chart-panel--nested">
              <div class="panel-header panel-header--compact">
                <div class="panel-title-group">
                  <span class="panel-eyebrow">TRADES</span>
                  <h2 class="panel-title">成交记录</h2>
                </div>
              </div>
              <TradeLogTable
                v-if="currentTradeTotal > 0"
                :trades="currentTrades"
                :total="remoteTradesTotal"
                :remote="remoteTradesLoaded"
                @page-change="onRemoteTradesPage"
                @select="handleTradeClick"
              />
              <div v-else class="tab-empty tab-empty--sm">
                <span class="empty-text">等待成交记录生成...</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- ========== 完成或失败后：结果/中断前记录 ========== -->
      <template
        v-else-if="backtest && (
          (backtest.status === 'completed' && backtest.result)
          || ((backtest.status === 'failed' || backtest.status === 'cancelled') && hasHistoricalRecords)
        )"
      >
        <div
          v-if="backtest.status === 'completed'"
          class="metrics-row metrics-row--performance"
        >
          <div
            v-for="metric in performanceHeroMetrics"
            :key="metric.label"
            class="metric-card"
            :class="metric.toneClass"
          >
            <span class="metric-label">{{ metric.label }}</span>
            <span class="metric-value">{{ metric.value }}</span>
            <span class="metric-hint">{{ metric.hint }}</span>
          </div>
        </div>

        <div class="live-context-bar">
          <span class="ctx-chip">{{ backtest.config.symbols.join(' / ') }}</span>
          <span class="ctx-chip">{{ formatIntervalText(backtest.config.interval) }}</span>
          <span class="ctx-chip">{{ backtest.config.startTime }} → {{ backtest.config.endTime }}</span>
          <span class="ctx-chip">{{ backtest.config.agentName || 'Agent' }}</span>
          <span class="ctx-chip">初始 {{ formatMoney(backtest.config.initialCapital) }} USDT</span>
        </div>

        <div v-if="backtest.status === 'failed' || backtest.status === 'cancelled'" class="partial-records-summary">
          <div>
            <span class="partial-records-eyebrow">PARTIAL HISTORY</span>
            <h2 class="partial-records-title">{{ backtest.status === 'cancelled' ? '取消前已执行记录' : '失败前已执行记录' }}</h2>
            <p class="partial-records-desc">
              以下数据仅反映任务中断前的执行情况，不代表完整回测结果。
            </p>
          </div>
          <div class="partial-records-stats">
            <span>进度 {{ backtest.progress ?? 0 }}%</span>
            <span>成交 {{ reportTradesTotal }} 条</span>
            <span>决策 {{ reportDecisionsTotal }} 条</span>
            <span v-if="runningDetail.currentTime">执行至 {{ formatDateTime(runningDetail.currentTime) }}</span>
          </div>
        </div>

        <div v-if="backtest.status === 'completed' && currentStatistics" class="stats-panel">
          <div class="panel-header">
            <div class="panel-title-group">
              <span class="panel-eyebrow">PERFORMANCE</span>
              <h2 class="panel-title">收益概览</h2>
            </div>
            <span class="panel-hint">最终结果</span>
          </div>
          <BacktestSummaryCard
            :statistics="currentStatistics"
            :execution-count="reportTradesTotal"
          />
        </div>

        <div class="report-charts report-charts--split">
          <div class="chart-panel">
            <div class="panel-header">
              <div class="panel-title-group">
                <span class="panel-eyebrow">CHART</span>
                <h2 class="panel-title">收益曲线</h2>
              </div>
              <span class="panel-hint">
                {{ currentEquityCurve.length > 0 ? '总收益 / 权益对比 / 回撤' : '等待数据' }}
              </span>
            </div>
            <div v-if="currentEquityCurve.length > 0" class="chart-container chart-container--report">
              <EquityCurveChart
                title="收益曲线"
                :equity-curve="currentEquityCurve"
                :benchmark-curve="currentBenchmarkCurve"
                :drawdown-curve="currentDrawdownCurve"
                :initial-capital="backtest.config.initialCapital || 0"
                :show-benchmark="true"
                :show-drawdown="true"
              />
            </div>
            <div v-else class="chart-empty">
              <el-icon class="empty-icon"><TrendCharts /></el-icon>
              <span class="empty-text">暂无收益曲线数据</span>
            </div>
          </div>

          <div class="chart-panel">
            <div class="panel-header">
              <div class="panel-title-group">
                <span class="panel-eyebrow">MARKET</span>
                <h2 class="panel-title">交易标的 K 线</h2>
              </div>
              <div class="panel-actions">
                <el-select
                  v-if="(backtest.config.symbols?.length ?? 0) > 1"
                  v-model="selectedKlineSymbol"
                  size="small"
                  class="symbol-select"
                >
                  <el-option
                    v-for="sym in backtest.config.symbols"
                    :key="sym"
                    :label="sym"
                    :value="sym"
                  />
                </el-select>
                <span class="panel-hint">
                  最终决策用紫色定位线显示 · 成交图标仅表示实际成交
                </span>
              </div>
            </div>
            <BacktestKlineChart
              v-if="selectedKlineSymbol"
              :backtest-id="backtest.id"
              :symbol="selectedKlineSymbol"
              :interval="backtest.config.interval"
              :start-time="backtest.config.startTime"
              :end-time="backtest.config.endTime"
              :trades="klineTrades"
              :positions="completedOpenPositions"
              :focus-time="klineFocusTime"
              :focus-decision="klineFocusDecision"
              @trade-click="handleTradeClick"
            />
          </div>
        </div>

        <div class="tabs-panel">
          <el-tabs v-model="detailMainTab" class="detail-tabs" @tab-change="onReportTabChange">
            <el-tab-pane label="配置详情" name="context">
              <div class="context-grid">
                <div
                  class="context-card context-card--clickable"
                  @click="goToAgent(backtest?.config.agentId)"
                >
                  <span class="context-label">关联 Agent</span>
                  <span class="context-value">{{ backtest?.config.agentName || '-' }}</span>
                  <span class="context-hint">
                    <el-icon><ArrowRight /></el-icon>
                    查看详情
                  </span>
                </div>
                <div class="context-card">
                  <span class="context-label">回测区间</span>
                  <span class="context-value context-value--small">
                    {{ backtest?.config.startTime }} 至 {{ backtest?.config.endTime }}
                  </span>
                  <span class="context-hint">创建于 {{ formatDateTime(backtest?.createdAt) }}</span>
                </div>
                <div class="context-card">
                  <span class="context-label">市场配置</span>
                  <span class="context-value">{{ getExchangeText(backtest?.config.exchange) }}</span>
                  <span class="context-hint">{{ formatIntervalText(backtest?.config.interval) }} K线</span>
                </div>
                <div class="context-card">
                  <span class="context-label">交易标的</span>
                  <span class="context-value context-value--small">
                    {{ backtest?.config.symbols.join(', ') }}
                  </span>
                  <span class="context-hint">共 {{ backtest?.config.symbols.length }} 个交易对</span>
                </div>
                <div class="context-card">
                  <span class="context-label">初始资金</span>
                  <span class="context-value context-value--highlight">
                    {{ formatMoney(backtest?.config.initialCapital || 0) }} USDT
                  </span>
                  <span class="context-hint">作为收益率基线</span>
                </div>
                <div class="context-card">
                  <span class="context-label">费用模型</span>
                  <span class="context-value context-value--small">
                    Maker {{ backtest?.config.makerFee }}% / Taker {{ backtest?.config.takerFee }}%
                  </span>
                  <span class="context-hint">滑点 {{ backtest?.config.slippage }}%</span>
                </div>
              </div>

              <div
                v-if="backtest?.result?.statistics.symbolPrices && Object.keys(backtest.result.statistics.symbolPrices).length"
                class="data-section"
              >
                <div class="section-header">
                  <h3 class="section-title">价格区间</h3>
                  <span class="section-desc">回测区间内各交易对的价格变动</span>
                </div>
                <div class="table-container">
                  <el-table
                    :data="symbolPriceRows(backtest.result.statistics)"
                    class="data-table"
                  >
                    <el-table-column prop="symbol" label="交易对" width="140" />
                    <el-table-column label="开始价格" align="right" min-width="120">
                      <template #default="{ row }">
                        <span class="mono">{{ formatPrice(row.startPrice) }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="结束价格" align="right" min-width="120">
                      <template #default="{ row }">
                        <span class="mono">{{ formatPrice(row.endPrice) }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="涨跌幅" align="right" min-width="100">
                      <template #default="{ row }">
                        <span
                          class="mono"
                          :class="row.changePercent >= 0 ? 'text-profit' : 'text-loss'"
                        >
                          {{ row.changePercent >= 0 ? '+' : '' }}{{ row.changePercent.toFixed(2) }}%
                        </span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </div>

              <div
                v-if="backtest?.result && hasOpenPositions(backtest.result.statistics)"
                class="data-section"
              >
                <div class="section-header">
                  <h3 class="section-title">未平仓持仓</h3>
                  <span class="section-desc">回测结束时的浮动盈亏</span>
                </div>
                <div class="table-container">
                  <el-table
                    :data="backtest.result.statistics.openPositions"
                    class="data-table"
                  >
                    <el-table-column prop="symbol" label="交易对" width="140" />
                    <el-table-column label="方向" width="80" align="center">
                      <template #default="{ row }">
                        <span :class="row.side === 'long' ? 'text-profit' : 'text-loss'">
                          {{ row.side === 'long' ? '多' : '空' }}
                        </span>
                      </template>
                    </el-table-column>
                    <el-table-column label="数量" align="right" min-width="100">
                      <template #default="{ row }">
                        <span class="mono">{{ row.quantity }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="开仓价" align="right" min-width="120">
                      <template #default="{ row }">
                        <span class="mono">{{ formatPrice(row.entryPrice) }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="未实现盈亏" align="right" min-width="120">
                      <template #default="{ row }">
                        <span
                          class="mono"
                          :class="row.unrealizedPnl >= 0 ? 'text-profit' : 'text-loss'"
                        >
                          {{ row.unrealizedPnl >= 0 ? '+' : '' }}{{ row.unrealizedPnl.toFixed(2) }}
                        </span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>

                <div class="summary-row">
                  <div class="summary-item">
                    <span class="summary-label">现金余额</span>
                    <span class="summary-value">
                      {{ formatMoney(backtest.result.statistics.balanceAtEnd ?? 0) }} USDT
                    </span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">未实现盈亏</span>
                    <span
                      class="summary-value"
                      :class="(backtest.result.statistics.unrealizedPnlTotal ?? 0) >= 0 ? 'text-profit' : 'text-loss'"
                    >
                      {{ (backtest.result.statistics.unrealizedPnlTotal ?? 0) >= 0 ? '+' : '' }}
                      {{ (backtest.result.statistics.unrealizedPnlTotal ?? 0).toFixed(2) }} USDT
                    </span>
                  </div>
                  <div class="summary-item summary-item--highlight">
                    <span class="summary-label">最终资金</span>
                    <span class="summary-value summary-value--primary">
                      {{ formatMoney(backtest.result.statistics.finalCapital) }} USDT
                    </span>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="交易记录" name="trades">
              <TradeLogTable
                v-if="reportTrades.length > 0 || useRemoteTrades"
                :trades="reportTrades"
                :remote="useRemoteTrades"
                :total="remoteTradesTotal"
                @select="handleTradeClick"
                @page-change="onRemoteTradesPage"
              />
              <div v-else class="tab-empty">
                <el-icon class="empty-icon"><Document /></el-icon>
                <span class="empty-text">本次回测未产生成交</span>
              </div>
            </el-tab-pane>

            <el-tab-pane v-if="showDecisionTab || useRemoteDecisions" label="决策记录" name="decisions">
              <DecisionLogTable
                v-if="reportDecisions.length > 0 || useRemoteDecisions"
                :backtest-id="backtest.id"
                :decisions="reportDecisions"
                :remote="useRemoteDecisions"
                :total="remoteDecisionsTotal"
                @select="handleFocusDecision"
                @page-change="onRemoteDecisionsPage"
              />
              <div v-else class="tab-empty">
                <el-icon class="empty-icon"><List /></el-icon>
                <span class="empty-text">本次回测未产生决策记录</span>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </template>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowLeft, ArrowRight, Download, CircleClose, RefreshRight,
  TrendCharts, Document, List,
} from '@element-plus/icons-vue'
import BacktestSummaryCard from '@/components/backtest/BacktestSummaryCard.vue'
import EquityCurveChart from '@/components/backtest/EquityCurveChart.vue'
import BacktestKlineChart from '@/components/backtest/BacktestKlineChart.vue'
import DecisionLogTable from '@/components/backtest/DecisionLogTable.vue'
import TradeLogTable from '@/components/backtest/TradeLogTable.vue'
import LiveProgressStrip from '@/components/backtest/LiveProgressStrip.vue'
import LiveTradeManagerPanel from '@/components/backtest/LiveTradeManagerPanel.vue'
import DecisionStreamPanel from '@/components/backtest/DecisionStreamPanel.vue'
import {
  backtestApi,
  type BacktestTask,
  type BacktestStatus,
  type BacktestRunningProgress,
  type BacktestTradeRecord,
  type BacktestLivePreviewPayload,
  type BacktestStatistics,
  type TimeSeriesPoint,
  type BacktestDecisionRecord,
  type LiveOpenPosition,
  type BacktestActiveOrder,
  type LiveLastAction,
} from '@/api/backtest'
import type { ExchangeCode } from '@/api/agents'

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const exporting = ref(false)
const rerunning = ref(false)
const backtest = ref<BacktestTask | null>(null)
const progress = ref(0)
const progressMessage = ref('')
const runningDetail = ref<BacktestRunningProgress>({})
const livePreviewPayload = ref<BacktestLivePreviewPayload | null>(null)
const detailMainTab = ref('context')
const selectedKlineSymbol = ref('')
const liveChartTab = ref<'equity' | 'market'>('market')
const showFutureKlines = ref(false)
const liveFooterExpanded = ref(false)
const klineFocusTime = ref<string | null>(null)
const klineFocusDecision = ref<BacktestDecisionRecord | null>(null)
const liveKlineRef = ref<{ zoomToCurrentTime: () => void } | null>(null)

/** 详情未内嵌数据时走服务端分页 */
const remoteTrades = ref<BacktestTradeRecord[]>([])
const remoteTradesTotal = ref(0)
const remoteDecisions = ref<BacktestDecisionRecord[]>([])
const remoteDecisionsTotal = ref(0)
const remoteEquityCurve = ref<TimeSeriesPoint[]>([])
const remoteDrawdownCurve = ref<TimeSeriesPoint[]>([])
const remoteBenchmarkCurve = ref<TimeSeriesPoint[]>([])
const remoteTradesLoaded = ref(false)
const remoteDecisionsLoaded = ref(false)
const remoteTradesPage = ref(1)
const remoteTradesPageSize = ref(20)
const remoteDecisionsPage = ref(1)
const remoteDecisionsPageSize = ref(10)
let remoteDecisionsRequestSeq = 0

const useRemoteTrades = computed(() => {
  if (isLivePhase.value) return false
  const embedded = backtest.value?.result?.trades?.length ?? 0
  const hinted = backtest.value?.result?.statistics?.totalTrades ?? 0
  // 失败态可能没有完整 statistics，但增量成交已经落库。
  return embedded === 0 && (hinted > 0 || remoteTradesTotal.value > 0)
})

const useRemoteDecisions = computed(() => {
  if (isLivePhase.value) return false
  const embedded = backtest.value?.result?.decisionLog?.length ?? 0
  // 完整决策不再内嵌到详情响应，进入决策页时通过 /decisions 分页加载。
  return embedded === 0 || (remoteDecisionsLoaded.value && remoteDecisionsTotal.value > 0)
})

const reportTrades = computed(() => {
  if (useRemoteTrades.value) return remoteTrades.value
  return currentTrades.value
})

const reportDecisions = computed(() => {
  if (useRemoteDecisions.value) return remoteDecisions.value
  return currentDecisionLog.value
})

const reportTradesTotal = computed(() => {
  if (useRemoteTrades.value) return remoteTradesTotal.value
  return currentTrades.value.length
})

const reportDecisionsTotal = computed(() => {
  if (useRemoteDecisions.value) return remoteDecisionsTotal.value
  return Math.max(
    currentDecisionLog.value.length,
    livePreviewPayload.value?.decisionLogTotal ?? 0,
  )
})

const completedOpenPositions = computed((): LiveOpenPosition[] => {
  const list = backtest.value?.result?.statistics?.openPositions
  if (!Array.isArray(list)) return []
  return list.map((p) => ({
    symbol: p.symbol,
    side: p.side,
    quantity: p.quantity,
    entryPrice: p.entryPrice,
    leverage: p.leverage,
    marginUsed: p.marginUsed,
    currentPrice: p.endPrice,
    endPrice: p.endPrice,
    unrealizedPnl: p.unrealizedPnl,
  }))
})

watch(
  () => backtest.value?.config.symbols,
  (symbols) => {
    if (!symbols?.length) {
      selectedKlineSymbol.value = ''
      return
    }
    if (!symbols.includes(selectedKlineSymbol.value)) {
      selectedKlineSymbol.value = symbols[0]
    }
  },
  { immediate: true },
)

watch(liveChartTab, async () => {
  await nextTick()
  // 侧栏折叠 / tab 切换后容器尺寸变化，通知图表重算
  window.dispatchEvent(new Event('resize'))
})

const hasDecisionLog = computed(() => {
  const log = backtest.value?.result?.decisionLog
  return (
    (Array.isArray(log) && log.length > 0)
    || displayLiveDecisionLog.value.length > 0
    || remoteDecisionsTotal.value > 0
  )
})

const isLivePhase = computed(
  () => backtest.value?.status === 'pending' || backtest.value?.status === 'running',
)
const isInterruptedPhase = computed(
  () => backtest.value?.status === 'failed' || backtest.value?.status === 'cancelled',
)

const currentStatistics = computed((): BacktestStatistics | null => {
  if (isLivePhase.value) return displayLiveStatistics.value
  return backtest.value?.result?.statistics
    ?? (isInterruptedPhase.value && livePreviewPayload.value
      ? displayLiveStatistics.value
      : null)
})

const currentEquityCurve = computed((): TimeSeriesPoint[] => {
  if (isLivePhase.value) return displayLiveEquityCurve.value
  if (remoteEquityCurve.value.length) return remoteEquityCurve.value
  const result = backtest.value?.result?.equityCurve
  if (result?.length) return result
  return isInterruptedPhase.value ? displayLiveEquityCurve.value : []
})

const currentBenchmarkCurve = computed((): TimeSeriesPoint[] => {
  if (isLivePhase.value) return livePreviewPayload.value?.benchmarkCurve ?? []
  if (remoteBenchmarkCurve.value.length) return remoteBenchmarkCurve.value
  const result = backtest.value?.result?.benchmarkCurve
  if (result?.length) return result
  return isInterruptedPhase.value
    ? livePreviewPayload.value?.benchmarkCurve ?? []
    : []
})

const currentDrawdownCurve = computed((): TimeSeriesPoint[] => {
  if (isLivePhase.value) return livePreviewPayload.value?.drawdownCurve ?? []
  if (remoteDrawdownCurve.value.length) return remoteDrawdownCurve.value
  const result = backtest.value?.result?.drawdownCurve
  if (result?.length) return result
  return isInterruptedPhase.value
    ? livePreviewPayload.value?.drawdownCurve ?? []
    : []
})

const currentDecisionLog = computed((): BacktestDecisionRecord[] => {
  if (isLivePhase.value) return displayLiveDecisionLog.value
  const raw = backtest.value?.result?.decisionLog
  if (Array.isArray(raw) && raw.length > 0) return raw
  return isInterruptedPhase.value ? displayLiveDecisionLog.value : []
})

const currentTrades = computed((): BacktestTradeRecord[] => {
  if (isLivePhase.value) return displayLiveTrades.value
  const result = backtest.value?.result?.trades
  if (result?.length) return result
  return isInterruptedPhase.value ? displayLiveTrades.value : []
})

const currentTradeTotal = computed(() => {
  if (isLivePhase.value && remoteTradesLoaded.value) return remoteTradesTotal.value
  return currentTrades.value.length
})

const hasHistoricalRecords = computed(() => (
  currentEquityCurve.value.length > 0
  || currentTrades.value.length > 0
  || currentDecisionLog.value.length > 0
  || remoteTradesTotal.value > 0
  || remoteDecisionsTotal.value > 0
))

const klineTrades = computed((): BacktestTradeRecord[] => {
  const sym = selectedKlineSymbol.value
  if (!sym) return []
  const norm = sym.replace(/[-_/]/g, '').toUpperCase()
  return currentTrades.value.filter(
    (t) => t.symbol.replace(/[-_/]/g, '').toUpperCase() === norm,
  )
})

const showDecisionTab = computed(() => !isLivePhase.value || hasDecisionLog.value)

const liveOpenPositions = computed((): LiveOpenPosition[] => {
  const fromRoot = livePreviewPayload.value?.openPositions
  if (Array.isArray(fromRoot)) return fromRoot
  const fromStats = livePreviewPayload.value?.statistics?.openPositions
  if (!Array.isArray(fromStats)) return []
  return fromStats.map((p) => ({
    symbol: p.symbol,
    side: p.side,
    quantity: p.quantity,
    entryPrice: p.entryPrice,
    leverage: p.leverage,
    marginUsed: p.marginUsed,
    currentPrice: (p as LiveOpenPosition).currentPrice ?? p.endPrice,
    endPrice: p.endPrice,
    unrealizedPnl: p.unrealizedPnl,
    unrealizedPnlPercent: (p as LiveOpenPosition).unrealizedPnlPercent,
    roiPercent: (p as LiveOpenPosition).roiPercent,
    entryTime: (p as LiveOpenPosition).entryTime,
    notional: (p as LiveOpenPosition).notional,
    tradePlan: (p as LiveOpenPosition).tradePlan,
  }))
})

const liveActiveOrders = computed((): BacktestActiveOrder[] => {
  const rows = livePreviewPayload.value?.activeOrders
  return Array.isArray(rows) ? rows : []
})

const liveBalance = computed(() => {
  const lp = livePreviewPayload.value
  if (lp?.balance != null) return lp.balance
  return lp?.statistics?.balanceAtEnd ?? backtest.value?.config.initialCapital ?? 0
})

const liveEquity = computed(() => {
  const lp = livePreviewPayload.value
  if (lp?.equity != null) return lp.equity
  return lp?.statistics?.finalCapital ?? liveBalance.value
})

const liveReturnPct = computed(() => {
  const ic = backtest.value?.config.initialCapital ?? 0
  if (!ic) return currentStatistics.value?.totalReturn ?? 0
  if (currentStatistics.value?.totalReturn != null) return currentStatistics.value.totalReturn
  return ((liveEquity.value - ic) / ic) * 100
})

const liveLastAction = computed((): LiveLastAction | null => {
  return livePreviewPayload.value?.lastAction ?? null
})

const statusLeadText = computed(() => {
  if (!backtest.value) return '正在加载回测数据...'

  const statusMessages: Record<BacktestStatus, string> = {
    pending: '任务已进入队列，页面会在回放开始后自动更新',
    running: '聚焦进展、仓位与决策逻辑；完成后可查看完整收益报告',
    completed: '回测已完成，以下是完整的收益表现和交易记录',
    failed: '任务执行未能完成，可查看错误信息、失败前记录并重新发起回测',
    cancelled: '任务已由用户取消，可查看取消前记录并重新发起回测',
  }
  return statusMessages[backtest.value.status]
})

const heroMetrics = computed(() => {
  if (!backtest.value) return []
  const task = backtest.value

  return [
    {
      label: '任务状态',
      value: getStatusText(task.status),
      hint: task.status === 'completed' ? '已生成完整结果' : '执行中断',
      toneClass: '',
    },
    {
      label: '回测区间',
      value: `${task.config.startTime} → ${task.config.endTime}`,
      hint: `${formatIntervalText(task.config.interval)} K线`,
      toneClass: '',
    },
    {
      label: '交易标的',
      value: task.config.symbols.join(' / '),
      hint: `${getExchangeText(task.config.exchange)} · ${task.config.symbols.length} 个交易对`,
      toneClass: '',
    },
    {
      label: '初始资金',
      value: `${formatMoney(task.config.initialCapital)} USDT`,
      hint: `Maker ${task.config.makerFee}% / Taker ${task.config.takerFee}%`,
      toneClass: '',
    },
  ]
})

const performanceHeroMetrics = computed(() => {
  const s = currentStatistics.value
  if (!s) return heroMetrics.value

  const ret = s.totalReturn ?? 0
  const dd = s.maxDrawdown ?? 0
  const sharpe = s.sharpeRatio
  const winRate = s.winRate ?? 0

  return [
    {
      label: '总收益率',
      value: `${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%`,
      hint: `最终资金 ${formatMoney(s.finalCapital ?? 0)} USDT`,
      toneClass: ret >= 0 ? 'metric-card--profit' : 'metric-card--loss',
    },
    {
      label: '最大回撤',
      value: `${dd.toFixed(2)}%`,
      hint: '区间内最大权益回撤',
      toneClass: 'metric-card--loss',
    },
    {
      label: '夏普比率',
      value: sharpe == null ? '-' : Number(sharpe).toFixed(2),
      hint: '风险调整后收益',
      toneClass: '',
    },
    {
      label: '胜率',
      value: `${winRate.toFixed(1)}%`,
      hint: `已平仓 ${s.closedTrades ?? 0} 笔 · 成交 ${reportTradesTotal.value} 次`,
      toneClass: winRate >= 50 ? 'metric-card--profit' : '',
    },
  ]
})

function formatIntervalText(interval?: string) {
  const map: Record<string, string> = {
    '1m': '1分钟', '5m': '5分钟', '15m': '15分钟',
    '1h': '1小时', '4h': '4小时', '1d': '日线',
  }
  return interval ? (map[interval] ?? interval) : '-'
}

function defaultLiveStatistics(initialCapital: number): BacktestStatistics {
  return {
    totalReturn: 0, annualizedReturn: 0, maxDrawdown: 0,
    sharpeRatio: 0, sortinoRatio: 0, winRate: 0,
    profitFactor: 0, totalTrades: 0, closedTrades: 0,
    winTrades: 0, lossTrades: 0, avgProfit: 0, avgLoss: 0,
    avgHoldingTime: '-', maxConsecutiveWins: 0,
    maxConsecutiveLosses: 0, finalCapital: initialCapital,
  }
}

const displayLiveStatistics = computed((): BacktestStatistics => {
  const ic = backtest.value?.config.initialCapital ?? 0
  const base = defaultLiveStatistics(ic)
  const s = livePreviewPayload.value?.statistics
  if (!s) return base
  return { ...base, ...s, avgHoldingTime: (s.avgHoldingTime as string) ?? base.avgHoldingTime }
})

const displayLiveEquityCurve = computed(() => livePreviewPayload.value?.equityCurve ?? [])
const displayLiveDecisionLog = computed(() => {
  // 运行中以 /decisions 最新一页为准；进度快照只用于首次加载兜底。
  if (remoteDecisionsLoaded.value) return remoteDecisions.value
  const raw = livePreviewPayload.value?.decisionLog
  if (Array.isArray(raw) && raw.length > 0) return raw
  return remoteDecisions.value
})
const currentDecisionTotal = computed(() => {
  if (remoteDecisionsLoaded.value) return remoteDecisionsTotal.value
  return livePreviewPayload.value?.decisionLogTotal
    ?? displayLiveDecisionLog.value.length
})
const displayLiveTrades = computed((): BacktestTradeRecord[] => {
  if (remoteTradesLoaded.value) return remoteTrades.value
  const raw = livePreviewPayload.value?.trades
  return Array.isArray(raw) ? raw : []
})

const liveDecisionTruncatedHint = computed(() => {
  // 已通过 /decisions 获取服务端分页后，所有历史决策都可翻页查看，不再属于截断展示。
  if (remoteDecisionsLoaded.value) return ''
  const lp = livePreviewPayload.value
  if (!lp?.decisionLogTruncated || !lp.decisionLogTotal) return ''
  return `运行中仅同步最近 ${lp.decisionLog?.length ?? 0} 条，共已产生 ${lp.decisionLogTotal} 条；完成后可查看全部。`
})

function hasLivePreviewPayload(lp: BacktestLivePreviewPayload | null | undefined): boolean {
  if (!lp) return false
  return (
    Array.isArray(lp.equityCurve)
    || Array.isArray(lp.decisionLog)
    || Array.isArray(lp.trades)
    || Array.isArray(lp.openPositions)
    || Array.isArray(lp.activeOrders)
  )
}

function hydrateLiveFromRunningProgress(rp: BacktestRunningProgress | null | undefined) {
  if (!rp) {
    runningDetail.value = {}
    return
  }
  runningDetail.value = {
    currentTime: rp.currentTime, message: rp.message,
    currentStep: rp.currentStep, totalSteps: rp.totalSteps,
    intervalSeconds: rp.intervalSeconds,
  }
  const lp = rp?.livePreview
  if (hasLivePreviewPayload(lp as BacktestLivePreviewPayload | undefined)) {
    livePreviewPayload.value = lp as BacktestLivePreviewPayload
  }
}

const PROGRESS_POLL_INTERVAL_MS = 10_000
let pollTimer: ReturnType<typeof setTimeout> | null = null
let pollingActive = false
let pollingGeneration = 0
let detailRequestEpoch = 0

function currentRouteId(): string {
  const value = route.params.id
  return Array.isArray(value) ? (value[0] ?? '') : (value ?? '')
}

function isCurrentBacktest(id: string): boolean {
  return currentRouteId() === id
}

function resetBacktestViewState() {
  stopPolling()
  // 使旧任务尚未返回的详情请求失效，避免其覆盖新任务页面。
  detailRequestEpoch += 1
  backtest.value = null
  progress.value = 0
  progressMessage.value = ''
  runningDetail.value = {}
  livePreviewPayload.value = null
  detailMainTab.value = 'context'
  selectedKlineSymbol.value = ''
  liveChartTab.value = 'market'
  showFutureKlines.value = false
  liveFooterExpanded.value = false
  klineFocusTime.value = null
  klineFocusDecision.value = null
  remoteTrades.value = []
  remoteTradesTotal.value = 0
  remoteTradesPage.value = 1
  remoteTradesPageSize.value = 20
  remoteDecisions.value = []
  remoteDecisionsTotal.value = 0
  remoteDecisionsPage.value = 1
  remoteDecisionsPageSize.value = 10
  remoteDecisionsRequestSeq += 1
  remoteEquityCurve.value = []
  remoteDrawdownCurve.value = []
  remoteBenchmarkCurve.value = []
  remoteTradesLoaded.value = false
  remoteDecisionsLoaded.value = false
}

async function fetchBacktest(targetId = currentRouteId()) {
  const id = targetId
  if (!id) return
  const requestEpoch = ++detailRequestEpoch
  loading.value = true
  try {
    const data = await backtestApi.getById(id)
    if (requestEpoch !== detailRequestEpoch || !isCurrentBacktest(id)) return
    backtest.value = data
    remoteTrades.value = []
    remoteTradesTotal.value = 0
    remoteTradesPage.value = 1
    remoteTradesPageSize.value = 20
    remoteDecisions.value = []
    remoteDecisionsTotal.value = 0
    remoteDecisionsPage.value = 1
    remoteDecisionsPageSize.value = 10
    remoteDecisionsRequestSeq += 1
    remoteEquityCurve.value = []
    remoteDrawdownCurve.value = []
    remoteBenchmarkCurve.value = []
    remoteTradesLoaded.value = false
    remoteDecisionsLoaded.value = false
    klineFocusTime.value = null
    klineFocusDecision.value = null
    if (backtest.value.status === 'pending' || backtest.value.status === 'running') {
      progress.value = backtest.value.progress ?? 0
      if (backtest.value.status === 'running') {
        hydrateLiveFromRunningProgress(backtest.value.runningProgress ?? undefined)
        progressMessage.value = backtest.value.runningProgress?.message || `正在回测... ${progress.value}%`
      } else {
        runningDetail.value = {}
        livePreviewPayload.value = null
        progressMessage.value = '等待执行...'
      }
      startPolling()
    } else if (backtest.value.status === 'failed' || backtest.value.status === 'cancelled') {
      stopPolling()
      progress.value = backtest.value.progress ?? 0
      progressMessage.value = backtest.value.errorMessage
        || (backtest.value.status === 'cancelled' ? '回测已取消' : '回测失败')
      hydrateLiveFromRunningProgress(backtest.value.runningProgress ?? undefined)
      // 兼容旧任务：即使失败时没有保留快照，增量成交/决策仍可能已经落库。
      await Promise.all([
        fetchRemoteEquityCurve(id),
        fetchRemoteTrades(1, 20, id),
        fetchRemoteDecisions(1, 20, id, true),
      ])
      if (reportDecisionsTotal.value > 0) {
        detailMainTab.value = 'decisions'
      } else if (reportTradesTotal.value > 0) {
        detailMainTab.value = 'trades'
      }
    } else {
      stopPolling()
      runningDetail.value = {}
      livePreviewPayload.value = null
      await Promise.all([
        fetchRemoteEquityCurve(id),
        fetchRemoteTrades(1, 20, id, true),
        fetchRemoteDecisions(1, 20, id, true),
      ])
    }
  } catch {
    if (requestEpoch === detailRequestEpoch && isCurrentBacktest(id)) {
      ElMessage.error('获取回测详情失败')
    }
  } finally {
    if (requestEpoch === detailRequestEpoch && isCurrentBacktest(id)) {
      loading.value = false
    }
  }
}

async function refreshBacktestSilent() {
  const id = currentRouteId()
  if (!id) return
  try {
    const data = await backtestApi.getById(id)
    if (!isCurrentBacktest(id)) return
    backtest.value = data
    if (
      (data.status === 'running' || data.status === 'failed' || data.status === 'cancelled')
      && data.runningProgress
    ) {
      hydrateLiveFromRunningProgress(data.runningProgress)
    }
  } catch { /* ignore */ }
}

async function pollProgressOnce() {
  const id = currentRouteId()
  if (!id) return
  try {
    const progressRes = await backtestApi.getProgress(id)
    if (!isCurrentBacktest(id)) return
    if (
      progressRes.status === 'completed'
      || progressRes.status === 'failed'
      || progressRes.status === 'cancelled'
    ) {
      stopPolling()
      await fetchBacktest(id)
      return
    }
    progress.value = progressRes.progress
    progressMessage.value = progressRes.message || ''
    if (progressRes.status === 'running') {
      runningDetail.value = {
        currentTime: progressRes.currentTime, message: progressRes.message,
        currentStep: progressRes.currentStep, totalSteps: progressRes.totalSteps,
        intervalSeconds: progressRes.intervalSeconds,
      }
      if (progressRes.livePreview && hasLivePreviewPayload(progressRes.livePreview as BacktestLivePreviewPayload)) {
        livePreviewPayload.value = progressRes.livePreview as BacktestLivePreviewPayload
      }
      // /progress 不再携带决策正文；刷新用户当前查看的决策页，避免翻页后被轮询拉回第一页。
      await Promise.all([
        fetchRemoteDecisions(
          remoteDecisionsPage.value,
          remoteDecisionsPageSize.value,
          id,
          true,
        ),
        fetchRemoteTrades(
          remoteTradesPage.value,
          remoteTradesPageSize.value,
          id,
          true,
        ),
      ])
    } else {
      runningDetail.value = {}
      livePreviewPayload.value = null
    }
    if (progressRes.status !== backtest.value?.status) {
      await refreshBacktestSilent()
    }
  } catch (error) {
    console.error('Failed to fetch progress:', error)
  }
}

async function runProgressPolling(generation: number) {
  if (!pollingActive || generation !== pollingGeneration) return

  await pollProgressOnce()

  // 从上一次请求完成后开始等待，确保慢请求不会与下一轮重叠。
  if (!pollingActive || generation !== pollingGeneration) return
  pollTimer = setTimeout(() => {
    pollTimer = null
    void runProgressPolling(generation)
  }, PROGRESS_POLL_INTERVAL_MS)
}

function startPolling() {
  if (pollingActive) return
  pollingActive = true
  const generation = ++pollingGeneration
  void runProgressPolling(generation)
}

function stopPolling() {
  pollingActive = false
  pollingGeneration += 1
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function goBack() { router.push('/backtest') }
function goToAgent(agentId?: string) { if (agentId) router.push(`/agents/${agentId}`) }

function onSelectSymbol(symbol: string) {
  if (!symbol) return
  selectedKlineSymbol.value = symbol
}

function switchToMarketTab() {
  liveChartTab.value = 'market'
}

function onSelectPosition(symbol: string) {
  onSelectSymbol(symbol)
  switchToMarketTab()
  klineFocusDecision.value = null
  const pos = liveOpenPositions.value.find((p) => p.symbol === symbol)
  klineFocusTime.value = pos?.entryTime ?? runningDetail.value.currentTime ?? null
}

function handleFocusDecision(decision: BacktestDecisionRecord) {
  if (decision.symbol) onSelectSymbol(decision.symbol)
  if (isLivePhase.value) switchToMarketTab()
  // 使用后端记录的最终 action（已完成规则/风控复核），绝不从 LLM 原始响应反解。
  klineFocusDecision.value = decision
  klineFocusTime.value = decision.timestamp || null
}

function handleFocusAction(action: LiveLastAction) {
  if (action.symbol) onSelectSymbol(action.symbol)
  switchToMarketTab()
  klineFocusDecision.value = null
  if (action.timestamp) {
    klineFocusTime.value = action.timestamp
  } else {
    jumpToSimTime()
  }
}

function handleTradeClick(trade: BacktestTradeRecord) {
  if (trade.symbol) onSelectSymbol(trade.symbol)
  if (isLivePhase.value) switchToMarketTab()
  klineFocusDecision.value = null
  klineFocusTime.value = trade.timestamp || null
}

function jumpToSimTime() {
  switchToMarketTab()
  klineFocusDecision.value = null
  klineFocusTime.value = runningDetail.value.currentTime ?? null
  // 下一帧再调 zoom，确保 focusTime 已传到子组件
  void nextTick(() => {
    liveKlineRef.value?.zoomToCurrentTime()
  })
}

function positionSymbolLabel(sym: string) {
  const hasPos = liveOpenPositions.value.some((p) => p.symbol === sym)
  return hasPos ? `${sym} · 持仓` : sym
}

async function fetchRemoteTrades(
  page = 1,
  pageSize = 20,
  targetId = currentRouteId(),
  silent = false,
) {
  const id = targetId
  if (!id) return
  try {
    const res = await backtestApi.getTrades(id, {
      skip: (page - 1) * pageSize,
      limit: pageSize,
      order: isLivePhase.value ? 'desc' : 'asc',
    })
    if (!isCurrentBacktest(id)) return
    remoteTrades.value = res.list ?? []
    remoteTradesTotal.value = res.total ?? 0
    remoteTradesLoaded.value = true
    remoteTradesPage.value = page
    remoteTradesPageSize.value = pageSize
  } catch {
    if (!silent && isCurrentBacktest(id)) ElMessage.error('加载成交记录失败')
  }
}

async function fetchRemoteEquityCurve(targetId = currentRouteId()) {
  const id = targetId
  if (!id) return
  try {
    const res = await backtestApi.getEquityCurve(id)
    if (!isCurrentBacktest(id)) return
    remoteEquityCurve.value = res.equityCurve ?? []
    remoteDrawdownCurve.value = res.drawdownCurve ?? []
    remoteBenchmarkCurve.value = res.benchmarkCurve ?? []
  } catch {
    if (isCurrentBacktest(id)) ElMessage.error('加载权益曲线失败')
  }
}

async function fetchRemoteDecisions(
  page = 1,
  pageSize = 10,
  targetId = currentRouteId(),
  silent = false,
) {
  const id = targetId
  if (!id) return
  const requestSeq = ++remoteDecisionsRequestSeq
  try {
    const res = await backtestApi.getDecisions(id, {
      skip: (page - 1) * pageSize,
      limit: pageSize,
    })
    const rows = [...(res.list ?? [])].sort((left, right) => (
      new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime()
    ))
    if (!isCurrentBacktest(id) || requestSeq !== remoteDecisionsRequestSeq) return
    const total = res.total ?? 0
    const lastPage = Math.max(1, Math.ceil(total / pageSize))
    if (page > lastPage) {
      remoteDecisionsPage.value = lastPage
      remoteDecisionsPageSize.value = pageSize
      await fetchRemoteDecisions(lastPage, pageSize, id, silent)
      return
    }
    remoteDecisions.value = rows
    remoteDecisionsTotal.value = total
    remoteDecisionsPage.value = page
    remoteDecisionsPageSize.value = pageSize
    remoteDecisionsLoaded.value = true
  } catch {
    if (!silent && isCurrentBacktest(id)) ElMessage.error('加载决策记录失败')
  }
}

function onRemoteTradesPage(payload: { page: number; pageSize: number }) {
  remoteTradesPage.value = payload.page
  remoteTradesPageSize.value = payload.pageSize
  void fetchRemoteTrades(payload.page, payload.pageSize)
}

function onRemoteDecisionsPage(payload: { page: number; pageSize: number }) {
  void fetchRemoteDecisions(payload.page, payload.pageSize)
}

function onLiveDecisionsPage(payload: { page: number; pageSize: number }) {
  remoteDecisionsPage.value = payload.page
  remoteDecisionsPageSize.value = payload.pageSize
  void fetchRemoteDecisions(payload.page, payload.pageSize)
}

function onReportTabChange(name: string | number) {
  if (name === 'trades' && useRemoteTrades.value && !remoteTradesLoaded.value) {
    void fetchRemoteTrades(1, 20)
  }
  if (name === 'decisions' && !isLivePhase.value && !remoteDecisionsLoaded.value) {
    void fetchRemoteDecisions(1, 20)
  }
}

async function handleStop() {
  const isPending = backtest.value?.status === 'pending'
  try {
    await ElMessageBox.confirm(
      isPending ? '确定要取消尚未开始的回测任务吗？' : '确定要停止当前回测吗？',
      isPending ? '取消任务' : '停止回测',
      { type: 'warning' },
    )
    await backtestApi.stop(route.params.id as string)
    ElMessage.success('已停止回测')
    stopPolling()
    fetchBacktest()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('停止失败')
  }
}

async function handleExport() {
  const id = route.params.id as string
  if (!id) return
  exporting.value = true
  try {
    const blob = await backtestApi.exportReport(id, 'csv')
    if (!(blob instanceof Blob)) {
      ElMessage.error('导出失败')
      return
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const safeName = (backtest.value?.name || 'backtest').replace(/[\\/:*?"<>|]/g, '_')
    link.download = `${safeName}_${id.slice(0, 8)}.csv`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

async function handleRerun() {
  const id = currentRouteId()
  if (!id) return
  try {
    await ElMessageBox.confirm('将基于当前配置创建新的回测任务，是否继续？', '重新回测', { type: 'info' })
    rerunning.value = true
    const res = await backtestApi.rerun(id)
    if (!res.id || res.id === id) {
      throw new Error('重测接口未返回新的任务 ID')
    }
    await router.push(`/backtest/${res.id}`)
    ElMessage.success('重测任务已创建')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('重测失败')
  } finally {
    rerunning.value = false
  }
}

function symbolPriceRows(statistics: { symbolPrices?: Record<string, { startPrice: number; endPrice: number }> }) {
  const sp = statistics.symbolPrices
  if (!sp) return []
  return Object.entries(sp).map(([symbol, p]) => ({
    symbol, startPrice: p.startPrice, endPrice: p.endPrice,
    changePercent: p.startPrice ? ((p.endPrice - p.startPrice) / p.startPrice) * 100 : 0,
  }))
}

function hasOpenPositions(statistics: { openPositions?: unknown[] }) {
  return Array.isArray(statistics.openPositions) && statistics.openPositions.length > 0
}

function formatPrice(value: number) {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 })
}

function getStatusText(status: BacktestStatus) {
  const map: Record<BacktestStatus, string> = {
    pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消',
  }
  return map[status]
}

function getExchangeText(exchange?: ExchangeCode) {
  const map: Record<ExchangeCode, string> = { binance: 'Binance', okx: 'OKX', bybit: 'Bybit' }
  return exchange ? map[exchange] : '-'
}

function formatMoney(value: number) {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDateTime(isoStr?: string) {
  if (!isoStr) return '-'
  return new Date(isoStr).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

watch(
  () => currentRouteId(),
  (id, previousId) => {
    if (!id || id === previousId) return
    resetBacktestViewState()
    void fetchBacktest(id)
  },
  { immediate: true },
)
onUnmounted(() => { stopPolling() })
</script>

<style scoped>
.backtest-detail-page {
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  min-height: 100%;
  min-width: 0;
  padding: 18px 22px 24px;
  background: var(--color-bg-base);
  overflow-x: hidden;
}

.detail-content {
  width: 100%;
  min-width: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
  margin-bottom: 14px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.back-btn {
  width: fit-content;
  color: var(--color-text-muted);
  padding: 7px 8px;
}

.back-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  min-width: 0;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
  max-width: 440px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status-badge--pending { background: var(--color-info-bg); color: var(--color-info); }
.status-badge--running { background: var(--color-warning-bg); color: var(--color-warning); }
.status-badge--running .status-dot { animation: pulse 1.5s ease-in-out infinite; }
.status-badge--completed { background: var(--color-profit-bg); color: var(--color-profit); }
.status-badge--failed { background: var(--color-loss-bg); color: var(--color-loss); }
.status-badge--cancelled { background: var(--color-bg-hover); color: var(--color-text-muted); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.page-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-muted);
  line-height: 1.5;
}

.header-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-size: 11px;
  white-space: nowrap;
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

/* 运行中上下文条 */
.live-context-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.ctx-chip {
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  color: var(--color-text-secondary);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
}

/* 作战台：曲线/K线 + 决策 */
.mission-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 330px);
  gap: 12px;
  width: 100%;
  min-width: 0;
  height: clamp(460px, calc(100vh - 500px), 530px);
  min-height: 460px;
  margin-bottom: 12px;
  align-items: stretch;
}

.mission-col {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.mission-col--right {
  width: 100%;
  min-height: 0;
  max-height: none;
  overflow: hidden;
}

.chart-panel--mission {
  display: flex;
  flex-direction: column;
  margin-bottom: 0;
  height: 100%;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  padding: 12px;
  border-radius: var(--radius-lg);
}

.chart-panel--mission :deep(.backtest-kline-chart),
.chart-panel--mission :deep(.equity-chart) {
  flex: 1;
  min-height: 0;
  min-width: 0;
}

.chart-panel--mission :deep(.equity-chart .chart-container) {
  height: min(46vh, 440px);
  min-height: 360px;
}
.chart-panel--mission :deep(.backtest-kline-chart .chart-container) {
  height: 100%;
  min-height: 360px;
}

.panel-header--compact {
  margin-bottom: 10px;
  gap: 12px;
  flex-wrap: nowrap;
  align-items: center;
}

.chart-panel--mission .panel-hint {
  display: none;
}

.live-chart-tabs {
  display: inline-flex;
  align-items: stretch;
  gap: 4px;
  padding: 2px;
  border-radius: var(--radius-md);
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border);
}

.live-chart-tab {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 5px 11px;
  border: none;
  border-radius: calc(var(--radius-md) - 2px);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.live-chart-tab:hover {
  color: var(--color-text-primary);
}

.live-chart-tab.is-active {
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.live-chart-tab .tab-eyebrow {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--color-primary);
  opacity: 0.7;
}

.live-chart-tab.is-active .tab-eyebrow {
  opacity: 1;
}

.live-chart-tab .tab-label {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
}

.live-chart-pane {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chart-container--live {
  flex: 1;
  min-height: 360px;
  min-width: 0;
}

.chart-empty--live {
  flex: 1;
  min-height: 360px;
}

/* 底部轻量统计 */
.live-footer {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.live-stats-strip {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  min-height: 52px;
  padding: 8px 14px;
}

.live-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.live-stat-label {
  font-size: 11px;
  color: var(--color-text-muted);
}

.live-stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.footer-toggle {
  margin-left: auto;
}

.live-footer-body {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
  border-top: 1px solid var(--color-border);
}

.chart-panel--nested {
  margin: 0;
  border: none;
  border-radius: 0;
}

.tab-empty--sm {
  min-height: 160px;
}

.report-charts {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.report-charts--split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}

.report-charts--split .chart-panel {
  margin-bottom: 0;
  min-width: 0;
}

.chart-container--report {
  min-height: 360px;
}

.chart-container--report :deep(.chart-container) {
  min-height: 320px;
  height: min(42vh, 420px);
}

/* 指标卡片行 */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 20px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.metric-card--profit .metric-value {
  color: var(--color-profit);
}

.metric-card--loss .metric-value {
  color: var(--color-loss);
}

.metric-label {
  font-size: 12px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metric-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.3;
  word-break: break-word;
}

.metric-hint {
  font-size: 12px;
  color: var(--color-text-disabled);
  line-height: 1.4;
}

.stats-panel,
.chart-panel,
.tabs-panel {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 24px;
  margin-bottom: 24px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.panel-title-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel-eyebrow {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-primary);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.panel-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.panel-hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

.trade-marker-legend {
  margin-left: 4px;
  color: var(--color-text-disabled);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.symbol-select {
  width: 160px;
}

.future-kline-toggle {
  margin-right: 0;
  white-space: nowrap;
}

.chart-container {
  min-height: 400px;
}

.chart-empty,
.tab-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 12px;
}

.empty-icon {
  font-size: 48px;
  color: var(--color-text-disabled);
}

.empty-text {
  font-size: 14px;
  color: var(--color-text-muted);
}

.tabs-panel {
  padding: 0;
}

.detail-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 24px;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-xl) var(--radius-xl) 0 0;
}

.detail-tabs :deep(.el-tabs__content) {
  padding: 24px;
}

.context-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.context-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
}

.context-card--clickable {
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.context-card--clickable:hover {
  border-color: var(--color-border-active);
  background: var(--color-primary-ghost);
}

.context-label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.context-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.context-value--small {
  font-size: 13px;
  font-weight: 500;
}

.context-value--highlight {
  color: var(--color-primary);
}

.context-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-disabled);
}

.data-section {
  margin-top: 28px;
}

.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.section-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.section-desc {
  font-size: 12px;
  color: var(--color-text-muted);
}

.table-container {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.mono {
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.text-profit { color: var(--color-profit); }
.text-loss { color: var(--color-loss); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-md);
}

.summary-item--highlight {
  background: var(--color-primary-ghost);
  border: 1px solid var(--color-profit-border);
}

.summary-label {
  font-size: 12px;
  color: var(--color-text-muted);
}

.summary-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.summary-value--primary {
  color: var(--color-primary);
}

.failed-panel {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 28px;
  margin-bottom: 20px;
  background: var(--color-loss-bg);
  border: 1px solid var(--color-loss-border);
  border-radius: var(--radius-xl);
}

.failed-icon-wrap {
  flex-shrink: 0;
}

.failed-icon {
  font-size: 36px;
  color: var(--color-loss);
}

.failed-title {
  margin: 0 0 8px;
  font-size: 18px;
  color: var(--color-text-primary);
}

.failed-message {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.failed-history-hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--color-text-muted);
  line-height: 1.5;
}

.partial-records-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
  padding: 20px 24px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.partial-records-eyebrow {
  display: block;
  margin-bottom: 5px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--color-loss);
}

.partial-records-title {
  margin: 0 0 4px;
  font-size: 18px;
  color: var(--color-text-primary);
}

.partial-records-desc {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

.partial-records-stats {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.partial-records-stats span {
  padding: 6px 10px;
  font-size: 12px;
  color: var(--color-text-secondary);
  background: var(--color-bg-hover);
  border-radius: var(--radius-md);
  white-space: nowrap;
}

@media (max-width: 980px) {
  .mission-grid {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
  }

  .chart-panel--mission {
    min-height: 520px;
  }

  .mission-col--right {
    min-height: 420px;
    max-height: 520px;
  }

}

@media (max-width: 1200px) {
  .report-charts--split {
    grid-template-columns: 1fr;
  }

  .metrics-row,
  .context-grid,
  .summary-row {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 1500px) {
  .header-chip--range {
    display: none;
  }
}

@media (max-width: 720px) {
  .metrics-row,
  .context-grid,
  .summary-row {
    grid-template-columns: 1fr;
  }

  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .header-left {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .title-row {
    align-items: flex-start;
  }

  .partial-records-summary {
    flex-direction: column;
  }

  .partial-records-stats {
    justify-content: flex-start;
  }
}
</style>
