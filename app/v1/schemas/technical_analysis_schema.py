#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标分析 Schema
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


class TechnicalAnalysisRequest(BaseModel):
    """技术分析请求（前端 camelCase 与后端 snake_case 均可解析）"""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(..., description="交易对，如 BTC-USDT 或 BTCUSDT")
    analysis_date: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("analysisDate", "analysis_date"),
        serialization_alias="analysisDate",
        description="分析截止日期，格式 YYYY-MM-DD，默认当前时间",
    )
    timeframe: str = Field(
        "4h",
        description="K线周期: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w",
    )
    lookback_days: int = Field(
        30,
        ge=7,
        le=365,
        validation_alias=AliasChoices("lookbackDays", "lookback_days"),
        serialization_alias="lookbackDays",
        description="回溯天数",
    )
    llm_model_id: Optional[int] = Field(
        None,
        validation_alias=AliasChoices("llmModelId", "llm_model_id"),
        serialization_alias="llmModelId",
        description="模型管理中的模型 ID；不传则使用环境变量默认 DeepSeek",
    )
    temperature: float = Field(
        0.3,
        ge=0,
        le=2,
        description="LLM 温度（仅在选择模型时生效；规则模式不调用 LLM）",
    )


class TrendAnalysis(BaseModel):
    """趋势分析"""
    direction: str = Field(..., description="趋势方向: bullish/bearish/neutral")
    strength: str = Field(..., description="趋势强度: strong/moderate/weak")
    description: str = Field(..., description="趋势描述")


class MomentumAnalysis(BaseModel):
    """动量分析"""
    rsi_status: str = Field(..., description="RSI状态: overbought/oversold/neutral")
    macd_status: str = Field(..., description="MACD状态: bullish/bearish/neutral")
    description: str = Field(..., description="动量描述")


class VolatilityAnalysis(BaseModel):
    """波动性分析"""
    status: str = Field(..., description="波动状态: high/medium/low")
    bollinger_position: str = Field(..., description="布林带位置: upper/middle/lower")
    description: str = Field(..., description="波动性描述")


class SupportResistance(BaseModel):
    """支撑阻力位"""
    key_support: List[float] = Field(default_factory=list, description="关键支撑位")
    key_resistance: List[float] = Field(default_factory=list, description="关键阻力位")
    fibonacci_levels: Optional[str] = Field(None, description="斐波那契位置描述")


class TradingSignal(BaseModel):
    """交易信号"""
    type: str = Field(..., description="信号类型: bullish/bearish")
    indicator: str = Field(..., description="产生信号的指标")
    description: str = Field(..., description="信号描述")


class Recommendation(BaseModel):
    """交易建议"""
    action: str = Field(..., description="建议操作: buy/sell/hold/wait")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    entry_zone: Optional[str] = Field(None, description="建议入场区间")
    stop_loss: Optional[str] = Field(None, description="建议止损位")
    take_profit: Optional[str] = Field(None, description="建议止盈位")
    risk_warning: Optional[str] = Field(None, description="风险提示")


class TechnicalAnalysisResult(BaseModel):
    """技术分析结果"""
    summary: str = Field(..., description="分析摘要")
    trend: Optional[TrendAnalysis] = Field(None, description="趋势分析")
    momentum: Optional[MomentumAnalysis] = Field(None, description="动量分析")
    volatility: Optional[VolatilityAnalysis] = Field(None, description="波动性分析")
    support_resistance: Optional[SupportResistance] = Field(None, description="支撑阻力位")
    signals: List[TradingSignal] = Field(default_factory=list, description="交易信号列表")
    recommendation: Optional[Recommendation] = Field(None, description="交易建议")


class TechnicalAnalysisResponse(BaseModel):
    """技术分析响应"""
    success: bool = Field(..., description="是否成功")
    symbol: str = Field(..., description="交易对")
    analysis_date: str = Field(..., description="分析日期")
    timeframe: str = Field(..., description="K线周期")
    analysis: Optional[TechnicalAnalysisResult] = Field(None, description="分析结果")
    raw_indicators: Optional[Dict[str, Any]] = Field(None, description="原始指标数据")
    analysis_mode: Optional[str] = Field(None, description="分析模式: llm/rule_based")
    error: Optional[str] = Field(None, description="错误信息")


class IndicatorDetailRequest(BaseModel):
    """指标详情请求"""
    symbol: str = Field(..., description="交易对")
    timeframe: str = Field("4h", description="K线周期")
    lookback_days: int = Field(30, ge=7, le=365, description="回溯天数")


class IndicatorDetailResponse(BaseModel):
    """指标详情响应"""
    success: bool
    symbol: str
    timeframe: str
    indicators: Dict[str, Any] = Field(default_factory=dict, description="指标详情")
    kline_count: int = Field(0, description="K线数量")
    error: Optional[str] = None
