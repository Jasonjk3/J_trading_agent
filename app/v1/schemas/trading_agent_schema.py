#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交易 Agent 相关 Schema
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator

from models.inner_models.trading_agent_model import (
    TradingAgentStatus,
    TradingStyle,
    TradingCycle,
    PositionDirection,
    OperationType,
    OperationResult
)


# ==================== 策略配置 Schema ====================

class RuleConfigSchema(BaseModel):
    """传统规则决策配置"""
    preset: Optional[str] = Field(
        default=None,
        description="规则预设: balanced_auto, trend_rider, range_scalper, conservative",
    )
    enabledRules: Optional[List[str]] = Field(
        default=None,
        description="启用的规则 ID 列表；不填则使用预设或默认全集",
    )
    disabledRules: Optional[List[str]] = Field(
        default=None,
        description="从预设/默认集中排除的规则 ID",
    )
    composition: str = Field(
        default="priority_stack",
        description="规则组合策略: priority_stack（一期仅支持此项）",
    )
    overrides: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="按规则 ID 覆盖参数",
    )


class TraderConfigSchema(BaseModel):
    """交易员回合运行配置；这些限制资源和执行权限，不评价交易质量。"""

    executionMode: Literal["shadow", "live"] = Field(
        default="shadow",
        description="shadow=只记录订单意图；live=允许送入风险内核和执行层",
    )
    maxToolCallsPerTurn: int = Field(default=6, ge=0, le=20)
    maxOrderRevisionsPerTurn: int = Field(default=1, ge=0, le=3)
    turnTimeoutSeconds: int = Field(default=60, ge=5, le=300)
    defaultReviewIntervalMinutes: int = Field(default=15, ge=1, le=1440)


class TargetProfitConfig(BaseModel):
    """目标利润配置"""
    type: str = Field(
        default="percentage",
        description="目标利润类型: 'fixed'=固定金额, 'percentage'=本金百分比"
    )
    value: float = Field(
        default=10.0,
        description="目标利润值（fixed时为USDT金额，percentage时为百分比）"
    )


class StrategyConfigSchema(BaseModel):
    """
    简化的策略配置 - 用户只需配置6个核心参数
    系统会根据这些参数自动推导其他交易策略细节
    """

    @model_validator(mode="before")
    @classmethod
    def reject_removed_llm_mode(cls, value: Any) -> Any:
        if isinstance(value, dict) and "useLLM" in value:
            raise ValueError("useLLM 已废弃；请显式使用 decisionMode=trader 或 rule")
        return value

    # 1. 交易对
    symbols: List[str] = Field(
        default_factory=list, 
        description="交易对列表，如 ['BTCUSDT', 'ETHUSDT']"
    )
    
    # 2. 交易风格（激进/均衡/稳定）
    tradingStyle: TradingStyle = Field(
        default=TradingStyle.BALANCED, 
        description="交易风格: aggressive=激进, balanced=均衡, conservative=稳定"
    )
    
    # 3. 初始本金
    initialCapital: float = Field(
        default=1000.0, 
        ge=10.0,
        description="初始本金(USDT)"
    )
    
    # 4. 目标利润（具体值或本金的百分比）
    targetProfit: TargetProfitConfig = Field(
        default_factory=TargetProfitConfig,
        description="目标利润配置"
    )
    
    # 5. 交易周期（当前系统统一按短线执行，保留字段做兼容）
    tradingCycle: TradingCycle = Field(
        default=TradingCycle.SHORT_TERM,
        description="交易周期（兼容字段）：当前系统统一按 short_term=短线 执行"
    )
    
    # 6. 单次交易上下限
    minOrderAmount: float = Field(
        default=10.0, 
        ge=1.0,
        description="单笔最小交易金额(USDT)"
    )
    maxOrderAmount: float = Field(
        default=1000.0, 
        description="单笔最大保证金(USDT)；订单名义价值可按 RiskKernel 批准杠杆放大"
    )
    pendingOrderMaxBars: int = Field(
        default=6,
        ge=1,
        le=24,
        description="短线限价挂单最多存活的执行周期数，默认 6 根 K 线",
    )
    pendingOrderMaxDistancePct: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=20.0,
        description="活动挂单允许偏离现价的最大百分比；不填时随交易风格推导",
    )
    aggressiveTrendStarterFraction: float = Field(
        default=0.35,
        ge=0.2,
        le=0.5,
        description="激进风格强趋势两段入场中，主动首仓占单笔风险预算的比例",
    )

    # 独立持仓上限；为空时兼容旧配置，继续按交易风格推导。
    maxPositionRatio: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=100.0,
        description="全部持仓最大保证金占账户权益的比例(%)；配置后优先于交易风格预设",
    )

    reducePositionRatio: float = Field(
        default=50.0,
        ge=1.0,
        le=100.0,
        description="模型选择 reduce_long/reduce_short 时，单次减少当前仓位的比例(%)",
    )
    
    # 7. 最大杠杆倍数
    maxLeverage: float = Field(
        default=5.0,
        ge=1.0,
        le=125.0,
        description="最大杠杆倍数；激进至少 2x，均衡允许 1x 到上限，稳定固定 1x"
    )
    
    # 8. 持仓方向限制
    positionDirection: PositionDirection = Field(
        default=PositionDirection.BOTH,
        description="持仓方向: long_only=仅做多, short_only=仅做空, both=均可"
    )
    
    # 备注（可选）
    remark: Optional[str] = Field(
        default=None, 
        description="备注"
    )
    
    decisionMode: Literal["trader", "rule"] = Field(
        default="trader",
        description="决策模式: trader=自主交易员, rule=传统规则引擎",
    )

    traderConfig: TraderConfigSchema = Field(
        default_factory=TraderConfigSchema,
        description="交易员回合预算、复核节奏等运行配置",
    )
    hardRiskPolicy: Optional[Dict[str, Any]] = Field(
        default=None,
        description="不可由交易员绕过的账户、仓位、损失和订单硬约束",
    )
    preferences: Optional[Dict[str, Any]] = Field(
        default=None,
        description="仅供交易员参考的目标、持有周期和交易偏好，不作为代码否决条件",
    )

    llmCacheMode: Literal["fresh", "record"] = Field(
        default="fresh",
        description=(
            "回测 LLM 响应处理: fresh=每次调用模型且不读缓存（默认）；"
            "record=每次调用模型并仅保存解析成功的响应，同样不读缓存"
        ),
    )

    ruleConfig: Optional[RuleConfigSchema] = Field(
        default=None,
        description="规则模式配置（decisionMode=rule 时生效）",
    )
    
    # 交易员使用的模型配置（模型是推理引擎，不再对应旧 decisionMode=llm）
    llm: Optional[Dict[str, Any]] = Field(
        default=None,
        description="交易员模型配置；未提供时由运行时使用默认托管模型配置"
    )
    decisionLlmModelId: Optional[int] = Field(
        default=None,
        description="决策 LLM 模型管理主键；优先于 Agent 表 llm_model_id 与环境变量 llm 配置",
    )
    decisionLlmTemperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="决策 LLM 温度",
    )

    # 消息面 / 技术事实（作为交易员可用事实，不是固定信号规则）
    useNewsAnalysis: bool = Field(
        default=False,
        description="是否使用消息面：为 true 时由服务层按 newsIntelligenceAgentId 查询资讯并注入决策 Prompt",
    )
    newsIntelligenceAgentId: Optional[str] = Field(
        default=None,
        description="消息面采集任务 ID（news_intelligence_agents.id），须属于同一用户",
    )
    newsContextMaxItems: int = Field(
        default=15,
        ge=1,
        le=50,
        description="注入决策时最多携带的资讯条数（按 sort_time 倒序，且 sort_time<=决策时点）",
    )
    useTechnicalAnalysis: bool = Field(
        default=False,
        description="是否使用技术面：为 true 时按交易对查询 technical_analysis_records 成功记录并注入",
    )
    marketMode: str = Field(
        default="auto",
        description="市场模式: auto=自动识别趋势/震荡, trend_only=仅做趋势, range_only=仅做震荡",
    )
    rangeRsiLongThreshold: float = Field(
        default=35.0,
        ge=10.0,
        le=50.0,
        description="震荡策略做多 RSI 阈值，低于该值才考虑接下沿做多",
    )
    rangeRsiShortThreshold: float = Field(
        default=65.0,
        ge=50.0,
        le=90.0,
        description="震荡策略做空 RSI 阈值，高于该值才考虑摸上沿做空",
    )
    rangeEntryBandTolerance: float = Field(
        default=0.005,
        ge=0.0,
        le=0.05,
        description="震荡策略入场时距离布林上下轨的容忍比例，例如 0.005 表示 0.5%",
    )
    rangeTakeProfitMode: str = Field(
        default="mid_band",
        description="震荡策略止盈模式: mid_band=布林中轨止盈, opposite_band=对侧轨道止盈",
    )
    technicalAnalysisTimeframe: Optional[str] = Field(
        default=None,
        description=(
            "决策执行节奏参考周期；未配置时回测对齐 K 线 interval，实盘默认 15m；"
            "1m/5m/15m 不单独生成技术报告，仅用于标注执行层"
        ),
    )
    technicalAnalysisContextTimeframes: Optional[List[str]] = Field(
        default=None,
        description="额外纳入决策的高周期背景列表，如 ['1h', '4h', '1d', '1w']；不填则按执行周期自动推导",
    )
    technicalAnalysisLlmModelId: Optional[int] = Field(
        default=None,
        description=(
            "库中无技术面记录时自动拉取分析所用的模型管理主键；"
            "当前 TECHNICAL_ANALYSIS_LLM_ENABLED=False，该字段暂不生效"
        ),
    )
    technicalAnalysisLookbackDays: int = Field(
        default=30,
        ge=1,
        le=365,
        description="自动技术分析 K 线回溯天数",
    )
    technicalAnalysisTemperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="自动技术分析 LLM 温度",
    )

    @model_validator(mode="after")
    def enforce_style_leverage_policy(self) -> "StrategyConfigSchema":
        if self.tradingStyle == TradingStyle.CONSERVATIVE:
            self.maxLeverage = 1.0
        elif self.tradingStyle == TradingStyle.AGGRESSIVE and self.maxLeverage < 2:
            raise ValueError("激进交易风格必须允许至少 2x 杠杆")
        return self

    class Config:
        from_attributes = True

    def get_derived_params(self) -> Dict[str, Any]:
        """
        根据用户配置的核心参数，自动推导其他交易策略参数
        这些推导参数供交易引擎内部使用
        """
        derived = {}
        
        # 根据交易风格推导参数
        if self.tradingStyle == TradingStyle.AGGRESSIVE:
            derived["maxPositionRatio"] = 50.0       # 最大持仓比例
            derived["maxDailyTrades"] = 100          # 单日最大交易次数
            derived["priceDeviationUpper"] = 2.0     # 挂单价格偏离上限
            derived["priceDeviationLower"] = 2.0     # 挂单价格偏离下限
            derived["leverage"] = 5.0                # 默认杠杆
        elif self.tradingStyle == TradingStyle.CONSERVATIVE:
            derived["maxPositionRatio"] = 20.0
            derived["maxDailyTrades"] = 20
            derived["priceDeviationUpper"] = 0.5
            derived["priceDeviationLower"] = 0.5
            derived["leverage"] = 1.0
        else:  # BALANCED
            derived["maxPositionRatio"] = 30.0
            derived["maxDailyTrades"] = 50
            derived["priceDeviationUpper"] = 1.0
            derived["priceDeviationLower"] = 1.0
            derived["leverage"] = 2.0

        # 用户显式配置的持仓比例优先；旧配置缺失时保持 20/30/50 的风格预设。
        if self.maxPositionRatio is not None:
            derived["maxPositionRatio"] = float(self.maxPositionRatio)
        derived["reducePositionRatio"] = float(self.reducePositionRatio)
        
        # 交易风格定义杠杆权限：激进必须使用，均衡可选，稳定固定 1x。
        derived["leverage"] = min(derived["leverage"], self.maxLeverage)
        derived["maxLeverage"] = (
            1.0 if self.tradingStyle == TradingStyle.CONSERVATIVE
            else self.maxLeverage
        )
        derived["positionDirection"] = self.positionDirection.value
        derived["pendingOrderMaxBars"] = self.pendingOrderMaxBars
        derived["pendingOrderMaxDistancePct"] = (
            self.pendingOrderMaxDistancePct
            if self.pendingOrderMaxDistancePct is not None
            else derived["priceDeviationUpper"]
        )
        derived["aggressiveTrendStarterFraction"] = float(
            self.aggressiveTrendStarterFraction
        )
        derived["marketMode"] = self.marketMode
        derived["rangeRsiLongThreshold"] = self.rangeRsiLongThreshold
        derived["rangeRsiShortThreshold"] = self.rangeRsiShortThreshold
        derived["rangeEntryBandTolerance"] = self.rangeEntryBandTolerance
        derived["rangeTakeProfitMode"] = self.rangeTakeProfitMode
        
        # 当前策略统一收敛为短线：忽略中线/长线输入，统一输出更高频的分析参数
        derived["tradingCycle"] = TradingCycle.SHORT_TERM.value
        derived["holdingPeriodHours"] = 8
        derived["analysisTimeframe"] = "15m"
        derived["signalSensitivity"] = "high"
        
        # 计算目标利润的绝对值
        if self.targetProfit.type == "percentage":
            derived["targetProfitAmount"] = self.initialCapital * self.targetProfit.value / 100
        else:
            derived["targetProfitAmount"] = self.targetProfit.value
        
        derived["targetProfitPercentage"] = (derived["targetProfitAmount"] / self.initialCapital) * 100
        
        return derived


def expand_strategy_config_for_backtest(
    config: Optional[Dict[str, Any]],
    *,
    interval: Optional[str] = None,
) -> Dict[str, Any]:
    """
    将用户保存的策略 JSON 与 get_derived_params 合并，供回测引擎使用。

    数据库存的是「简化配置」；leverage 等字段仍由系统推导，maxPositionRatio
    可由用户显式配置，旧配置缺失时按交易风格推导；
    若不合并，VirtualAccount 会按 leverage=1、风控按默认阈值执行。

    若传入 interval 且用户未显式配置 technicalAnalysisTimeframe，
    将执行/分析周期对齐到回测 K 线周期，避免 1h 回测却默认用 15m 语义。
    """
    raw = dict(config or {})
    try:
        schema = StrategyConfigSchema(**raw)
        derived = schema.get_derived_params()
        merged = {**raw, **derived}
    except Exception:
        merged = dict(raw)

    if interval:
        interval_norm = str(interval).strip().lower()
        merged.setdefault("interval", interval_norm)
        if not raw.get("technicalAnalysisTimeframe"):
            merged["technicalAnalysisTimeframe"] = interval_norm
            # get_derived_params 对短线硬编码 analysisTimeframe=15m，回测需覆盖以对齐步进
            merged["analysisTimeframe"] = interval_norm
    return merged


# ==================== Trading Agent Schema ====================

class TradingAgentListParams(BaseModel):
    """列表查询参数"""
    status: Optional[TradingAgentStatus] = Field(None, description="运行状态")


class TradingAgentListItem(BaseModel):
    """交易 Agent 列表项"""
    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    exchangeId: Optional[str] = Field(None, description="交易所账户ID")
    exchange: Optional[str] = Field(None, description="交易所标识")
    llmModelId: Optional[int] = Field(None, description="LLM 模型ID")
    llmModelName: Optional[str] = Field(None, description="LLM 模型名称")
    status: TradingAgentStatus = Field(..., description="运行状态")
    remark: Optional[str] = Field(None, description="备注")
    lastRunAt: Optional[str] = Field(None, description="最近运行时间")
    createdAt: str = Field(..., description="创建时间")
    updatedAt: Optional[str] = Field(None, description="更新时间")
    strategyConfig: Optional[StrategyConfigSchema] = Field(None, description="策略配置")

    class Config:
        from_attributes = True


class TradingAgentListResponse(BaseModel):
    """列表响应"""
    list: List[TradingAgentListItem] = Field(..., description="Agent 列表")
    total: int = Field(..., description="总数")


class CreateTradingAgentRequest(BaseModel):
    """创建交易 Agent 请求"""
    name: str = Field(..., description="Agent 名称", min_length=1, max_length=100)
    exchangeId: Optional[str] = Field(None, description="交易所账户ID")
    llmModelId: Optional[int] = Field(None, description="LLM 模型ID")
    remark: Optional[str] = Field(None, description="备注", max_length=255)
    strategyConfig: Optional[StrategyConfigSchema] = Field(None, description="策略配置")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "BTC趋势跟踪",
                "exchangeId": "exchange-account-id",
                "llmModelId": 1,
                "remark": "测试Agent",
                "strategyConfig": {
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "tradingStyle": "balanced",
                    "initialCapital": 1000,
                    "targetProfit": {
                        "type": "percentage",
                        "value": 10
                    },
                    "tradingCycle": "short_term",
                    "minOrderAmount": 10,
                    "maxOrderAmount": 500,
                    "maxLeverage": 5,
                    "positionDirection": "both"
                }
            }
        }


class UpdateTradingAgentRequest(BaseModel):
    """更新交易 Agent 请求"""
    name: Optional[str] = Field(None, description="Agent 名称", max_length=100)
    exchangeId: Optional[str] = Field(None, description="交易所账户ID")
    llmModelId: Optional[int] = Field(None, description="LLM 模型ID")
    remark: Optional[str] = Field(None, description="备注", max_length=255)
    strategyConfig: Optional[StrategyConfigSchema] = Field(None, description="策略配置")


class UpdateStrategyConfigRequest(BaseModel):
    """更新策略配置请求"""
    strategyConfig: StrategyConfigSchema = Field(..., description="策略配置")


# ==================== 操作记录 Schema ====================

class ChainOfThoughtStep(BaseModel):
    """思维链单步"""
    step: int = Field(..., description="步骤序号")
    thought: str = Field(..., description="当前步骤的分析思考")
    conclusion: Optional[str] = Field(None, description="该步骤的结论")


class AgentOperationItem(BaseModel):
    """Agent 操作记录项"""
    id: str = Field(..., description="记录ID")
    agentId: str = Field(..., description="Agent ID")
    type: OperationType = Field(..., description="操作类型")
    symbol: Optional[str] = Field(None, description="交易对")
    side: Optional[str] = Field(None, description="买/卖方向")
    quantity: Optional[str] = Field(None, description="数量")
    price: Optional[str] = Field(None, description="价格")
    reason: Optional[str] = Field(None, description="操作原因")
    result: Optional[OperationResult] = Field(None, description="执行结果")
    createdAt: str = Field(..., description="创建时间")
    chainOfThought: Optional[List[ChainOfThoughtStep]] = Field(None, description="思维链详情")

    class Config:
        from_attributes = True


class AgentOperationsResponse(BaseModel):
    """操作记录列表响应"""
    list: List[AgentOperationItem] = Field(..., description="操作记录列表")
    total: int = Field(..., description="总数")


# ==================== 收益曲线 Schema ====================

class ProfitCurvePoint(BaseModel):
    """收益曲线数据点"""
    time: str = Field(..., description="时间")
    value: str = Field(..., description="当期收益")
    cumulative: Optional[str] = Field(None, description="累计收益")


class AgentProfitCurveResponse(BaseModel):
    """收益曲线响应"""
    points: List[ProfitCurvePoint] = Field(..., description="收益数据点")
    period: Optional[str] = Field(None, description="时间周期")


# ==================== 启停操作响应 ====================

class AgentActionResponse(BaseModel):
    """Agent 启停操作响应"""
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="消息")
