#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
LLM 监控 API Schema
定义请求和响应的数据模型

注意：为避免 Pydantic 2.x 的 model_ 前缀保留问题，
字段使用 llm_model 代替 model_name，llm_provider 代替 model_provider
使用 serialization_alias 保持 API 响应兼容性
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 通用响应模型
# ============================================================================

class PaginationInfo(BaseModel):
    """分页信息"""
    page: int = Field(..., description="当前页码", ge=1)
    page_size: int = Field(..., description="每页条数", ge=1, le=100)
    total: int = Field(..., description="总记录数", ge=0)
    total_pages: int = Field(..., description="总页数", ge=0)


# ============================================================================
# 使用量相关 Schema
# ============================================================================

class UsageLogItem(BaseModel):
    """单条使用记录"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: int = Field(..., description="记录ID")
    request_id: str = Field(..., description="请求ID")
    llm_model: str = Field(..., description="模型名称", serialization_alias="model_name")
    llm_provider: str = Field(..., description="提供商", serialization_alias="model_provider")
    agent_name: Optional[str] = Field(None, description="Agent名称")
    task_type: Optional[str] = Field(None, description="任务类型")
    prompt_tokens: int = Field(..., description="输入Token数")
    completion_tokens: int = Field(..., description="输出Token数")
    total_tokens: int = Field(..., description="总Token数")
    cost_usd: float = Field(..., description="费用(美元)")
    cost_cny: float = Field(..., description="费用(人民币)")
    response_time_ms: int = Field(..., description="响应时间(毫秒)")
    status: str = Field(..., description="状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    user_id: Optional[str] = Field(None, description="用户ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    created_at: datetime = Field(..., description="创建时间")
    extra_data: Optional[Dict[str, Any]] = Field(None, description="扩展数据")


class UsageHistoryRequest(BaseModel):
    """历史调用记录请求"""
    model_config = ConfigDict(populate_by_name=True)
    
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    llm_model: Optional[str] = Field(None, description="模型名称", validation_alias="model_name")
    agent_name: Optional[str] = Field(None, description="Agent名称")
    status: Optional[str] = Field(None, description="状态筛选(success/failed/timeout)")
    user_id: Optional[str] = Field(None, description="用户ID")
    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(20, description="每页条数", ge=1, le=100)


class UsageHistoryResponse(BaseModel):
    """历史调用记录响应"""
    items: List[UsageLogItem] = Field(..., description="记录列表")
    pagination: PaginationInfo = Field(..., description="分页信息")


class RealtimeUsageData(BaseModel):
    """实时使用情况数据"""
    total_requests: int = Field(..., description="总请求数")
    total_tokens: int = Field(..., description="总Token数")
    total_cost_cny: float = Field(..., description="总费用(人民币)")
    success_rate: float = Field(..., description="成功率")
    avg_response_time_ms: Optional[int] = Field(None, description="平均响应时间")


class TopAgentItem(BaseModel):
    """Top Agent 项"""
    name: str = Field(..., description="Agent名称")
    requests: int = Field(..., description="请求数")


class RealtimeUsageResponse(BaseModel):
    """实时使用情况响应"""
    today: RealtimeUsageData = Field(..., description="今日数据")
    current_hour: RealtimeUsageData = Field(..., description="当前小时数据")
    active_models: List[str] = Field(..., description="活跃模型列表")
    top_agents: List[TopAgentItem] = Field(..., description="Top Agent列表")


# ============================================================================
# 统计相关 Schema
# ============================================================================

class DailyStatsRequest(BaseModel):
    """每日统计请求"""
    model_config = ConfigDict(populate_by_name=True)
    
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    llm_model: Optional[str] = Field(None, description="模型名称", validation_alias="model_name")
    agent_name: Optional[str] = Field(None, description="Agent名称")
    group_by: Optional[str] = Field(None, description="分组方式: model/agent/none")


class DailyStatsItem(BaseModel):
    """每日统计项"""
    model_config = ConfigDict(populate_by_name=True)
    
    stat_date: date = Field(..., description="日期", serialization_alias="date")
    llm_model: Optional[str] = Field(None, description="模型名称", serialization_alias="model_name")
    agent_name: Optional[str] = Field(None, description="Agent名称")
    total_requests: int = Field(..., description="总请求数")
    success_requests: int = Field(..., description="成功请求数")
    failed_requests: int = Field(..., description="失败请求数")
    total_tokens: int = Field(..., description="总Token数")
    prompt_tokens: int = Field(..., description="输入Token数")
    completion_tokens: int = Field(..., description="输出Token数")
    cost_usd: float = Field(..., description="费用(美元)")
    cost_cny: float = Field(..., description="费用(人民币)")
    avg_response_time_ms: int = Field(..., description="平均响应时间")
    p50_response_time_ms: Optional[int] = Field(None, description="P50响应时间")
    p99_response_time_ms: Optional[int] = Field(None, description="P99响应时间")


class DailyStatsSummary(BaseModel):
    """每日统计汇总"""
    total_requests: int = Field(..., description="总请求数")
    total_tokens: int = Field(..., description="总Token数")
    total_cost_usd: float = Field(..., description="总费用(美元)")
    total_cost_cny: float = Field(..., description="总费用(人民币)")


class DailyStatsResponse(BaseModel):
    """每日统计响应"""
    items: List[DailyStatsItem] = Field(..., description="统计列表")
    summary: DailyStatsSummary = Field(..., description="汇总")


class OverviewStatsResponse(BaseModel):
    """总览统计响应"""
    today: DailyStatsSummary = Field(..., description="今日统计")
    this_week: DailyStatsSummary = Field(..., description="本周统计")
    this_month: DailyStatsSummary = Field(..., description="本月统计")
    success_rate: float = Field(..., description="总体成功率")
    avg_response_time_ms: int = Field(..., description="平均响应时间")


class ModelStatsItem(BaseModel):
    """模型统计项"""
    model_config = ConfigDict(populate_by_name=True)
    
    llm_model: str = Field(..., description="模型名称", serialization_alias="model_name")
    llm_provider: str = Field(..., description="提供商", serialization_alias="model_provider")
    total_requests: int = Field(..., description="总请求数")
    total_tokens: int = Field(..., description="总Token数")
    cost_cny: float = Field(..., description="费用(人民币)")
    avg_response_time_ms: int = Field(..., description="平均响应时间")
    success_rate: float = Field(..., description="成功率")


class ModelStatsResponse(BaseModel):
    """按模型统计响应"""
    items: List[ModelStatsItem] = Field(..., description="模型统计列表")
    total_models: int = Field(..., description="模型总数")


class AgentStatsItem(BaseModel):
    """Agent统计项"""
    agent_name: str = Field(..., description="Agent名称")
    total_requests: int = Field(..., description="总请求数")
    total_tokens: int = Field(..., description="总Token数")
    cost_cny: float = Field(..., description="费用(人民币)")
    avg_response_time_ms: int = Field(..., description="平均响应时间")
    success_rate: float = Field(..., description="成功率")
    primary_model: str = Field(..., description="主要使用的模型")


class AgentStatsResponse(BaseModel):
    """按Agent统计响应"""
    items: List[AgentStatsItem] = Field(..., description="Agent统计列表")
    total_agents: int = Field(..., description="Agent总数")


# ============================================================================
# 费用相关 Schema
# ============================================================================

class CostSummaryRequest(BaseModel):
    """费用汇总请求"""
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期")
    group_by: Optional[str] = Field(None, description="分组方式: model/agent/none")


class CostBreakdownItem(BaseModel):
    """费用分解项"""
    name: str = Field(..., description="名称(模型/Agent)")
    cost_usd: float = Field(..., description="费用(美元)")
    cost_cny: float = Field(..., description="费用(人民币)")
    percentage: float = Field(..., description="占比(%)")


class CostPeriodSummary(BaseModel):
    """费用周期汇总"""
    cost_cny: float = Field(0, description="费用(人民币)")
    cost_usd: float = Field(0, description="费用(美元)")
    tokens: int = Field(0, description="Token数")


class CostModelItem(BaseModel):
    """按模型分组的费用项"""
    model_config = ConfigDict(populate_by_name=True)
    
    llm_model: str = Field(..., description="模型名称", serialization_alias="model_name")
    cost_cny: float = Field(..., description="费用(人民币)")
    percentage: float = Field(..., description="占比(%)")


class CostAgentItem(BaseModel):
    """按Agent分组的费用项"""
    agent_name: str = Field(..., description="Agent名称")
    cost_cny: float = Field(..., description="费用(人民币)")
    percentage: float = Field(..., description="占比(%)")


class CostSummaryResponse(BaseModel):
    """费用汇总响应 - 兼容前端期望的结构"""
    # 新增：周期汇总（前端期望的结构）
    today: CostPeriodSummary = Field(default_factory=CostPeriodSummary, description="今日费用")
    this_week: CostPeriodSummary = Field(default_factory=CostPeriodSummary, description="本周费用")
    this_month: CostPeriodSummary = Field(default_factory=CostPeriodSummary, description="本月费用")
    by_model: List[CostModelItem] = Field(default_factory=list, description="按模型分组")
    by_agent: List[CostAgentItem] = Field(default_factory=list, description="按Agent分组")
    # 保留原有字段以向后兼容
    total_cost_usd: float = Field(0, description="总费用(美元)")
    total_cost_cny: float = Field(0, description="总费用(人民币)")
    breakdown: List[CostBreakdownItem] = Field(default_factory=list, description="费用分解(已废弃)")


class CostTrendRequest(BaseModel):
    """费用趋势请求"""
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    granularity: str = Field("day", description="粒度: hour/day/week/month")


class CostTrendItem(BaseModel):
    """费用趋势项"""
    period: str = Field(..., description="时间段")
    cost_usd: float = Field(..., description="费用(美元)")
    cost_cny: float = Field(..., description="费用(人民币)")
    tokens: int = Field(..., description="Token数")
    requests: int = Field(..., description="请求数")


class CostTrendResponse(BaseModel):
    """费用趋势响应"""
    items: List[CostTrendItem] = Field(..., description="趋势数据")
    total_cost_cny: float = Field(..., description="总费用(人民币)")


# ============================================================================
# 配置管理 Schema
# ============================================================================

class ModelCostConfigItem(BaseModel):
    """模型费用配置项"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: int = Field(..., description="配置ID")
    llm_model: str = Field(..., description="模型名称", serialization_alias="model_name")
    provider: str = Field(..., description="提供商")
    input_price_per_1m: float = Field(..., description="输入价格($/1M tokens)")
    output_price_per_1m: float = Field(..., description="输出价格($/1M tokens)")
    currency: str = Field("USD", description="货币单位")
    exchange_rate: float = Field(..., description="汇率")
    effective_date: date = Field(..., description="生效日期")
    is_active: bool = Field(..., description="是否生效")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class ModelCostConfigListResponse(BaseModel):
    """模型费用配置列表响应"""
    items: List[ModelCostConfigItem] = Field(..., description="配置列表")
    total: int = Field(..., description="总数")


class ModelCostConfigCreateRequest(BaseModel):
    """创建模型费用配置请求"""
    model_config = ConfigDict(populate_by_name=True)
    
    llm_model: str = Field(..., description="模型名称", min_length=1, max_length=64, validation_alias="model_name")
    provider: str = Field(..., description="提供商", min_length=1, max_length=32)
    input_price_per_1m: float = Field(..., description="输入价格($/1M tokens)", ge=0)
    output_price_per_1m: float = Field(..., description="输出价格($/1M tokens)", ge=0)
    exchange_rate: float = Field(7.25, description="汇率", gt=0)
    effective_date: date = Field(..., description="生效日期")
    is_active: bool = Field(True, description="是否生效")


class ModelCostConfigUpdateRequest(BaseModel):
    """更新模型费用配置请求"""
    input_price_per_1m: Optional[float] = Field(None, description="输入价格($/1M tokens)", ge=0)
    output_price_per_1m: Optional[float] = Field(None, description="输出价格($/1M tokens)", ge=0)
    exchange_rate: Optional[float] = Field(None, description="汇率", gt=0)
    is_active: Optional[bool] = Field(None, description="是否生效")


# ============================================================================
# 预警相关 Schema
# ============================================================================

class AlertRuleItem(BaseModel):
    """预警规则项"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: int = Field(..., description="规则ID")
    rule_name: str = Field(..., description="规则名称")
    alert_type: str = Field(..., description="预警类型(daily_cost/monthly_cost/single_request)")
    threshold_value: float = Field(..., description="阈值(人民币)")
    llm_model: Optional[str] = Field(None, description="模型名称(空表示全部)", serialization_alias="model_name")
    agent_name: Optional[str] = Field(None, description="Agent名称(空表示全部)")
    notify_channels: Dict[str, Any] = Field(..., description="通知渠道配置")
    is_active: bool = Field(..., description="是否启用")
    cooldown_minutes: int = Field(..., description="冷却时间(分钟)")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class AlertRuleListResponse(BaseModel):
    """预警规则列表响应"""
    items: List[AlertRuleItem] = Field(..., description="规则列表")
    total: int = Field(..., description="总数")


class AlertRuleCreateRequest(BaseModel):
    """创建预警规则请求"""
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "rule_name": "日费用预警",
                "alert_type": "daily_cost",
                "threshold_value": 100.0,
                "model_name": None,
                "agent_name": None,
                "notify_channels": {
                    "feishu_webhook": "https://open.feishu.cn/xxx",
                    "email": ["admin@example.com"]
                },
                "is_active": True,
                "cooldown_minutes": 60
            }
        }
    )
    
    rule_name: str = Field(..., description="规则名称", min_length=1, max_length=64)
    alert_type: str = Field(..., description="预警类型(daily_cost/monthly_cost/single_request)")
    threshold_value: float = Field(..., description="阈值(人民币)", gt=0)
    llm_model: Optional[str] = Field(None, description="模型名称(空表示全部)", max_length=64, validation_alias="model_name")
    agent_name: Optional[str] = Field(None, description="Agent名称(空表示全部)", max_length=128)
    notify_channels: Dict[str, Any] = Field(..., description="通知渠道配置")
    is_active: bool = Field(True, description="是否启用")
    cooldown_minutes: int = Field(60, description="冷却时间(分钟)", ge=1)


class AlertRuleUpdateRequest(BaseModel):
    """更新预警规则请求"""
    rule_name: Optional[str] = Field(None, description="规则名称", max_length=64)
    threshold_value: Optional[float] = Field(None, description="阈值(人民币)", gt=0)
    notify_channels: Optional[Dict[str, Any]] = Field(None, description="通知渠道配置")
    is_active: Optional[bool] = Field(None, description="是否启用")
    cooldown_minutes: Optional[int] = Field(None, description="冷却时间(分钟)", ge=1)


class AlertHistoryItem(BaseModel):
    """预警历史项"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="记录ID")
    rule_id: int = Field(..., description="规则ID")
    rule_name: Optional[str] = Field(None, description="规则名称")
    alert_type: str = Field(..., description="预警类型")
    current_value: float = Field(..., description="当前值")
    threshold_value: float = Field(..., description="阈值")
    alert_message: str = Field(..., description="预警消息")
    notify_status: str = Field(..., description="通知状态(success/failed)")
    notify_result: Optional[Dict[str, Any]] = Field(None, description="通知结果")
    created_at: datetime = Field(..., description="触发时间")


class AlertHistoryRequest(BaseModel):
    """预警历史请求"""
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    rule_id: Optional[int] = Field(None, description="规则ID")
    alert_type: Optional[str] = Field(None, description="预警类型")
    notify_status: Optional[str] = Field(None, description="通知状态")
    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(20, description="每页条数", ge=1, le=100)


class AlertHistoryResponse(BaseModel):
    """预警历史响应"""
    items: List[AlertHistoryItem] = Field(..., description="历史记录")
    pagination: PaginationInfo = Field(..., description="分页信息")
