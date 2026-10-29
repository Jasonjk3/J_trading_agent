#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测系统相关 Schema
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from models.inner_models.backtest_model import BacktestStatus, KlineInterval
from app.v1.schemas.trading_agent_schema import StrategyConfigSchema


# ==================== 回测配置 Schema ====================

class BacktestConfigSchema(BaseModel):
    """回测配置"""
    agentId: str = Field(..., description="关联的 Agent ID")
    agentName: Optional[str] = Field(None, description="Agent 名称(冗余)")
    strategyConfig: StrategyConfigSchema = Field(..., description="策略配置")
    startTime: str = Field(..., description="回测开始时间")
    endTime: str = Field(..., description="回测结束时间")
    initialCapital: float = Field(..., ge=100, description="初始资金(USDT)")
    exchange: str = Field(default="okx", description="交易所")
    symbols: List[str] = Field(..., description="交易对列表")
    interval: KlineInterval = Field(default=KlineInterval.M15, description="K线周期")
    makerFee: float = Field(default=0.1, ge=0, le=1, description="Maker手续费率(%)")
    takerFee: float = Field(default=0.1, ge=0, le=1, description="Taker手续费率(%)")
    slippage: float = Field(default=0.05, ge=0, le=1, description="滑点(%)")
    marketImpactBps: float = Field(default=2.0, ge=0, le=100, description="基础市场冲击(bps)")
    impactVolatilityWeight: float = Field(default=0.10, ge=0, le=5, description="波动率冲击权重")
    maxImpactPct: float = Field(default=0.25, ge=0, le=5, description="市场冲击上限(%)")
    maxParticipationRate: float = Field(default=5.0, gt=0, le=100, description="单笔最大成交参与率(%)")
    fundingRatePerInterval: float = Field(default=0.0, ge=-5, le=5, description="每期资金费率(%)")
    fundingIntervalHours: int = Field(default=8, ge=1, le=24, description="资金费率结算周期(小时)")

    class Config:
        from_attributes = True


# ==================== 回测统计 Schema ====================

class BacktestStatisticsSchema(BaseModel):
    """回测结果统计"""
    totalReturn: float = Field(..., description="总收益率(%)")
    annualizedReturn: float = Field(..., description="年化收益率(%)")
    maxDrawdown: float = Field(..., description="最大回撤(%)")
    sharpeRatio: float = Field(..., description="夏普比率")
    sortinoRatio: Optional[float] = Field(None, description="索提诺比率")
    winRate: float = Field(..., description="胜率(%)")
    profitFactor: float = Field(..., description="盈利因子(毛利/毛损)")
    totalTrades: int = Field(..., description="总交易次数")
    winTrades: int = Field(..., description="盈利次数")
    lossTrades: int = Field(..., description="亏损次数")
    avgProfit: float = Field(..., description="平均盈利")
    avgLoss: float = Field(..., description="平均亏损")
    avgHoldingTime: Optional[str] = Field(None, description="平均持仓时间")
    maxConsecutiveWins: int = Field(default=0, description="最大连续盈利次数")
    maxConsecutiveLosses: int = Field(default=0, description="最大连续亏损次数")
    finalCapital: float = Field(..., description="最终资金")
    totalFees: float = Field(default=0.0, description="全部成交手续费")
    totalSlippageCost: float = Field(default=0.0, description="模拟滑点与冲击成本")
    totalFunding: float = Field(default=0.0, description="资金费率净支出")
    totalTradingCosts: float = Field(default=0.0, description="手续费、滑点冲击与资金费率净成本合计")
    experimentMetadata: Optional[Dict[str, Any]] = Field(None, description="可复现实验版本清单")
    autonomyMetrics: Optional[Dict[str, Any]] = Field(
        None,
        description="Trader 自主决策、硬风险拒绝与执行拒绝的消融观测指标",
    )

    class Config:
        from_attributes = True


# ==================== 交易记录 Schema ====================

class BacktestTradeItem(BaseModel):
    """回测交易记录"""
    id: str = Field(..., description="交易记录ID")
    timestamp: str = Field(..., description="交易时间")
    symbol: str = Field(..., description="交易对")
    side: str = Field(..., description="买/卖方向")
    type: str = Field(..., alias="tradeType", description="交易类型(open/close)")
    action: Optional[str] = Field(None, description="最终动作(open/add/reduce/close + long/short)")
    leverage: float = Field(default=1.0, description="实际批准杠杆")
    marginUsed: float = Field(default=0.0, description="本次成交对应保证金")
    price: float = Field(..., description="成交价格")
    quantity: float = Field(..., description="成交数量")
    amount: float = Field(..., description="成交金额")
    fee: float = Field(..., description="手续费")
    pnl: float = Field(..., description="盈亏金额")
    pnlPercent: float = Field(..., description="盈亏百分比")
    balance: float = Field(..., description="交易后余额")
    reasoning: Optional[str] = Field(None, description="LLM 分析理由")
    signals: Optional[List[str]] = Field(None, description="触发信号")

    class Config:
        from_attributes = True
        populate_by_name = True


# ==================== 曲线数据 Schema ====================

class TimeSeriesPoint(BaseModel):
    """时间序列数据点"""
    time: str = Field(..., description="时间")
    value: float = Field(..., description="数值")
    unrealizedPnl: Optional[float] = Field(None, description="持仓未实现盈亏")
    unrealizedPnlRate: Optional[float] = Field(None, description="持仓未实现盈亏率(%)")


# ==================== 回测结果 Schema ====================

class BacktestResultSchema(BaseModel):
    """回测结果"""
    statistics: BacktestStatisticsSchema = Field(..., description="统计数据")
    equityCurve: List[TimeSeriesPoint] = Field(..., description="权益曲线")
    drawdownCurve: List[TimeSeriesPoint] = Field(..., description="回撤曲线")
    benchmarkCurve: List[TimeSeriesPoint] = Field(..., description="基准曲线")
    positionHistory: Optional[List[Dict[str, Any]]] = Field(None, description="持仓历史")
    trades: List[BacktestTradeItem] = Field(..., description="交易记录")
    decisionLog: List[Dict[str, Any]] = Field(default_factory=list, description="决策日志")
    orderEvents: List[Dict[str, Any]] = Field(default_factory=list, description="订单生命周期事件")

    class Config:
        from_attributes = True


# ==================== 回测任务 Schema ====================

class BacktestListParams(BaseModel):
    """回测列表查询参数"""
    status: Optional[BacktestStatus] = Field(None, description="任务状态")
    page: int = Field(default=1, ge=1, description="页码")
    pageSize: int = Field(default=20, ge=1, le=100, description="每页数量")


class BacktestListItem(BaseModel):
    """回测列表项"""
    id: str = Field(..., description="回测任务ID")
    name: str = Field(..., description="回测名称")
    status: BacktestStatus = Field(..., description="任务状态")
    agentId: str = Field(..., description="关联的 Agent ID")
    agentName: Optional[str] = Field(None, description="Agent 名称")
    exchange: str = Field(..., description="交易所")
    symbols: List[str] = Field(..., description="交易对列表")
    startTime: str = Field(..., description="回测开始时间")
    endTime: str = Field(..., description="回测结束时间")
    initialCapital: float = Field(..., description="初始资金")
    totalReturn: Optional[float] = Field(None, description="总收益率(%)")
    maxDrawdown: Optional[float] = Field(None, description="最大回撤(%)")
    winRate: Optional[float] = Field(None, description="胜率(%)")
    createdAt: str = Field(..., description="创建时间")
    completedAt: Optional[str] = Field(None, description="完成时间")

    class Config:
        from_attributes = True


class BacktestListResponse(BaseModel):
    """回测列表响应"""
    list: List[BacktestListItem] = Field(..., description="回测列表")
    total: int = Field(..., description="总数")


class BacktestRunningProgressSchema(BaseModel):
    """运行进度快照；失败后保留最后一次快照用于查看中断前记录。"""
    currentTime: Optional[str] = Field(None, description="当前模拟到的历史时刻 ISO")
    message: Optional[str] = Field(None, description="进度说明")
    currentStep: Optional[int] = Field(None, description="当前步序号")
    totalSteps: Optional[int] = Field(None, description="总步数")
    intervalSeconds: Optional[int] = Field(None, description="每步间隔秒数")
    heartbeatAt: Optional[str] = Field(None, description="最近心跳时间")
    leaseExpiresAt: Optional[str] = Field(None, description="当前租约到期时间")
    workerId: Optional[str] = Field(None, description="执行 worker 标识")
    livePreview: Optional[Dict[str, Any]] = Field(
        None, description="最后一次权益、成交和决策预览"
    )


class BacktestTaskResponse(BaseModel):
    """回测任务详情响应"""
    id: str = Field(..., description="回测任务ID")
    name: str = Field(..., description="回测名称")
    status: BacktestStatus = Field(..., description="任务状态")
    progress: int = Field(..., description="执行进度(0-100)")
    createdAt: str = Field(..., description="创建时间")
    startedAt: Optional[str] = Field(None, description="开始执行时间")
    completedAt: Optional[str] = Field(None, description="完成时间")
    config: BacktestConfigSchema = Field(..., description="回测配置")
    result: Optional[BacktestResultSchema] = Field(None, description="回测结果")
    errorMessage: Optional[str] = Field(None, description="错误信息")
    runningProgress: Optional[BacktestRunningProgressSchema] = Field(
        None, description="运行中或失败时的最后一次执行快照"
    )

    class Config:
        from_attributes = True


# ==================== 创建回测请求 ====================

class CreateBacktestRequest(BaseModel):
    """创建回测请求"""
    name: str = Field(..., description="回测名称", min_length=1, max_length=100)
    config: BacktestConfigSchema = Field(..., description="回测配置")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "BTC趋势策略回测",
                "config": {
                    "agentId": "agent-id",
                    "agentName": "BTC趋势跟踪",
                    "strategyConfig": {
                        "tradingStyle": "balanced",
                        "symbols": ["BTCUSDT"]
                    },
                    "startTime": "2025-01-01",
                    "endTime": "2025-12-31",
                    "initialCapital": 10000,
                    "exchange": "okx",
                    "symbols": ["BTCUSDT"],
                    "interval": "15m",
                    "makerFee": 0.1,
                    "takerFee": 0.1,
                    "slippage": 0.05
                }
            }
        }


class CreateBacktestResponse(BaseModel):
    """创建回测响应"""
    id: str = Field(..., description="回测任务ID")


# ==================== 回测进度 Schema ====================

class BacktestProgressResponse(BaseModel):
    """回测进度响应"""
    status: BacktestStatus = Field(..., description="任务状态")
    progress: int = Field(..., description="执行进度(0-100)")
    currentTime: Optional[str] = Field(None, description="当前模拟历史时刻 ISO")
    message: Optional[str] = Field(None, description="进度消息")
    currentStep: Optional[int] = Field(None, description="当前步序号")
    totalSteps: Optional[int] = Field(None, description="总步数")
    intervalSeconds: Optional[int] = Field(None, description="每步间隔秒数")
    livePreview: Optional[Dict[str, Any]] = Field(
        None, description="运行中权益曲线与统计快照（与 progress_snapshot.livePreview 一致）"
    )


# ==================== 交易明细 Schema ====================

class BacktestTradesResponse(BaseModel):
    """交易明细响应"""
    list: List[BacktestTradeItem] = Field(..., description="交易记录列表")
    total: int = Field(..., description="总数")


# ==================== 权益曲线 Schema ====================

class EquityCurveResponse(BaseModel):
    """权益曲线响应"""
    equityCurve: List[TimeSeriesPoint] = Field(..., description="权益曲线")
    drawdownCurve: List[TimeSeriesPoint] = Field(..., description="回撤曲线")
    benchmarkCurve: List[TimeSeriesPoint] = Field(..., description="基准曲线")
