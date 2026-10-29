#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/07
# @Author : AI Assistant
"""
模型对比 API Schema
定义请求和响应的数据模型
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# 通用模型
# ============================================================================

class TokenUsage(BaseModel):
    """Token 使用量"""
    prompt_tokens: int = Field(..., description="输入 Token 数")
    completion_tokens: int = Field(..., description="输出 Token 数")
    total_tokens: int = Field(..., description="总 Token 数")


class CostInfo(BaseModel):
    """费用信息"""
    prompt: float = Field(..., description="输入价格($/1K tokens)")
    completion: float = Field(..., description="输出价格($/1K tokens)")
    currency: str = Field("USD", description="货币单位")


# ============================================================================
# API 配置相关 Schema (2.0 新增)
# ============================================================================

class ApiConfigCreate(BaseModel):
    """创建 API 配置请求"""
    name: str = Field(..., description="配置名称", min_length=1, max_length=64)
    provider: str = Field(..., description="供应商名称（如 OpenAI, 中转服务商名）", min_length=1, max_length=32)
    api_type: str = Field("generic", description="API 协议类型: openai / deepseek / generic")
    api_key: str = Field(..., description="API Key", min_length=1, max_length=512)
    api_url: Optional[str] = Field(None, description="API URL（完整地址）", max_length=256)
    extra_headers: Optional[Dict[str, str]] = Field(None, description="额外请求头")
    extra_params: Optional[Dict[str, Any]] = Field(None, description="额外请求参数")
    description: Optional[str] = Field(None, description="配置描述", max_length=256)
    is_default: bool = Field(False, description="是否默认配置")
    user_id: Optional[str] = Field(None, description="用户ID")


class ApiConfigUpdate(BaseModel):
    """更新 API 配置请求"""
    name: Optional[str] = Field(None, description="配置名称", max_length=64)
    provider: Optional[str] = Field(None, description="供应商名称", max_length=32)
    api_type: Optional[str] = Field(None, description="API 协议类型: openai / deepseek / generic")
    api_key: Optional[str] = Field(None, description="API Key", max_length=512)
    api_url: Optional[str] = Field(None, description="API URL", max_length=256)
    extra_headers: Optional[Dict[str, str]] = Field(None, description="额外请求头")
    extra_params: Optional[Dict[str, Any]] = Field(None, description="额外请求参数")
    description: Optional[str] = Field(None, description="配置描述", max_length=256)
    is_default: Optional[bool] = Field(None, description="是否默认配置")
    is_active: Optional[bool] = Field(None, description="是否启用")


class ApiConfigResponse(BaseModel):
    """API 配置响应"""
    id: int = Field(..., description="配置ID")
    name: str = Field(..., description="配置名称")
    provider: str = Field(..., description="供应商名称")
    api_type: str = Field("generic", description="API 协议类型")
    api_key: str = Field(..., description="API Key（脱敏显示）")
    api_url: Optional[str] = Field(None, description="API URL")
    extra_headers: Optional[Dict[str, str]] = Field(None, description="额外请求头")
    extra_params: Optional[Dict[str, Any]] = Field(None, description="额外请求参数")
    description: Optional[str] = Field(None, description="配置描述")
    is_default: bool = Field(False, description="是否默认配置")
    is_active: bool = Field(True, description="是否启用")
    user_id: Optional[str] = Field(None, description="用户ID")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class ApiConfigListResponse(BaseModel):
    """API 配置列表响应"""
    items: List[ApiConfigResponse] = Field(..., description="配置列表")
    total: int = Field(..., description="总数")


# ============================================================================
# 模型管理相关 Schema (2.0 新增)
# ============================================================================

class ModelManageCreate(BaseModel):
    """创建模型请求"""
    model_id: str = Field(..., description="模型ID", min_length=1, max_length=64)
    name: str = Field(..., description="模型显示名称", min_length=1, max_length=64)
    provider: str = Field(..., description="提供商显示名称", min_length=1, max_length=32)
    description: Optional[str] = Field(None, description="模型描述", max_length=512)
    max_tokens: Optional[int] = Field(None, description="模型上下文 Token 上限", ge=1)
    max_output_tokens: Optional[int] = Field(None, description="单次请求最大输出 Token 数", ge=1)
    supports_streaming: bool = Field(True, description="是否支持流式输出")
    supports_thinking: bool = Field(False, description="是否支持思考模式")
    use_max_completion_tokens: bool = Field(False, description="是否使用 max_completion_tokens（o1/o3 等模型）")
    input_price_per_1m: float = Field(0.0, description="输入价格（$/1M tokens）", ge=0)
    output_price_per_1m: float = Field(0.0, description="输出价格（$/1M tokens）", ge=0)
    api_config_id: Optional[int] = Field(None, description="关联的 API 配置ID（必须先创建 API 配置）")
    custom_params: Optional[Dict[str, Any]] = Field(None, description="模型特定参数")
    tags: Optional[List[str]] = Field(None, description="标签列表（如：['对话', '视频', '视觉']）")
    sort_order: int = Field(0, description="排序权重")
    user_id: Optional[str] = Field(None, description="用户ID")


class ModelManageUpdate(BaseModel):
    """更新模型请求"""
    name: Optional[str] = Field(None, description="模型显示名称", max_length=64)
    provider: Optional[str] = Field(None, description="提供商显示名称", max_length=32)
    description: Optional[str] = Field(None, description="模型描述", max_length=512)
    max_tokens: Optional[int] = Field(None, description="模型上下文 Token 上限", ge=1)
    max_output_tokens: Optional[int] = Field(None, description="单次请求最大输出 Token 数", ge=1)
    supports_streaming: Optional[bool] = Field(None, description="是否支持流式输出")
    supports_thinking: Optional[bool] = Field(None, description="是否支持思考模式")
    use_max_completion_tokens: Optional[bool] = Field(None, description="是否使用 max_completion_tokens")
    input_price_per_1m: Optional[float] = Field(None, description="输入价格（$/1M tokens）", ge=0)
    output_price_per_1m: Optional[float] = Field(None, description="输出价格（$/1M tokens）", ge=0)
    api_config_id: Optional[int] = Field(None, description="关联的 API 配置ID")
    custom_params: Optional[Dict[str, Any]] = Field(None, description="模型特定参数")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    is_active: Optional[bool] = Field(None, description="是否启用")
    sort_order: Optional[int] = Field(None, description="排序权重")


class ModelManageResponse(BaseModel):
    """模型管理响应"""
    id: int = Field(..., description="记录ID")
    model_id: str = Field(..., description="模型ID")
    name: str = Field(..., description="模型显示名称")
    provider: str = Field(..., description="提供商")
    description: Optional[str] = Field(None, description="模型描述")
    max_tokens: Optional[int] = Field(None, description="模型上下文 Token 上限")
    max_output_tokens: Optional[int] = Field(None, description="单次请求最大输出 Token 数")
    supports_streaming: bool = Field(True, description="是否支持流式输出")
    supports_thinking: bool = Field(False, description="是否支持思考模式")
    use_max_completion_tokens: bool = Field(False, description="是否使用 max_completion_tokens")
    input_price_per_1m: float = Field(0.0, description="输入价格（$/1M tokens）")
    output_price_per_1m: float = Field(0.0, description="输出价格（$/1M tokens）")
    api_config_id: Optional[int] = Field(None, description="关联的 API 配置ID")
    custom_params: Optional[Dict[str, Any]] = Field(None, description="模型特定参数")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    status: str = Field("unknown", description="可用状态: available / unavailable / unknown")
    last_test_at: Optional[datetime] = Field(None, description="最后测试时间")
    last_test_latency_ms: Optional[int] = Field(None, description="最后测试延迟（毫秒）")
    last_test_error: Optional[str] = Field(None, description="最后测试错误信息")
    is_active: bool = Field(True, description="是否启用")
    sort_order: int = Field(0, description="排序权重")
    user_id: Optional[str] = Field(None, description="用户ID")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class ModelManageListResponse(BaseModel):
    """模型管理列表响应"""
    items: List[ModelManageResponse] = Field(..., description="模型列表")
    total: int = Field(..., description="总数")


class ModelTestRequest(BaseModel):
    """模型测试请求"""
    model_ids: Optional[List[int]] = Field(None, description="要测试的模型记录ID列表（为空则测试所有启用的模型）")
    test_prompt: str = Field(
        "Hello, please respond with 'OK' if you can receive this message.", 
        description="测试提示词"
    )
    timeout: int = Field(30, description="超时时间（秒）", ge=5, le=120)


class ModelTestResult(BaseModel):
    """单个模型测试结果"""
    id: int = Field(..., description="模型记录ID")
    model_id: str = Field(..., description="模型ID")
    name: str = Field(..., description="模型名称")
    status: str = Field(..., description="状态: available / unavailable")
    latency_ms: Optional[int] = Field(None, description="响应延迟（毫秒）")
    error: Optional[str] = Field(None, description="错误信息")


class ModelTestResponse(BaseModel):
    """模型测试响应"""
    total: int = Field(..., description="测试模型总数")
    available: int = Field(..., description="可用数量")
    unavailable: int = Field(..., description="不可用数量")
    results: List[ModelTestResult] = Field(..., description="测试结果列表")


# ============================================================================
# 模型信息相关 Schema
# ============================================================================

class ModelInfo(BaseModel):
    """单个模型信息"""
    id: str = Field(..., description="模型ID")
    name: str = Field(..., description="模型显示名称")
    provider: str = Field(..., description="提供商")
    description: Optional[str] = Field(None, description="模型描述")
    enabled: bool = Field(True, description="是否可用")
    max_tokens: Optional[int] = Field(None, description="最大 Token 数")
    supports_streaming: bool = Field(True, description="是否支持流式输出")
    supports_thinking: bool = Field(False, description="是否支持思考模式")
    cost_per_1k_tokens: Optional[CostInfo] = Field(None, description="每千 Token 价格")


class ProviderInfo(BaseModel):
    """提供商信息"""
    name: str = Field(..., description="提供商名称")
    models: List[str] = Field(..., description="该提供商的模型ID列表")


class ModelsListResponse(BaseModel):
    """模型列表响应"""
    models: List[ModelInfo] = Field(..., description="模型列表")
    providers: List[ProviderInfo] = Field(..., description="提供商列表")


# ============================================================================
# API 配置相关 Schema
# ============================================================================

class ApiConfig(BaseModel):
    """API 配置"""
    api_key: Optional[str] = Field(None, description="API Key")
    api_url: Optional[str] = Field(None, description="API Base URL")


# ============================================================================
# 对比测试请求/响应 Schema
# ============================================================================

class ModelCompareRequest(BaseModel):
    """模型对比请求"""
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "models": ["gpt-4o", "deepseek-chat"],
            "system_prompt": "你是一个专业的AI助手",
            "user_prompt": "请介绍一下人工智能的发展历史",
            "temperature": 0.7,
            "max_tokens": 2000,
            "timeout": 60,
            "api_config": {
                "api_key": "sk-xxx",
                "api_url": "https://api.example.com/v1"
            }
        }
    })
    
    models: List[str] = Field(
        ..., 
        description="要对比的模型ID列表",
        min_length=1,
        max_length=10
    )
    system_prompt: Optional[str] = Field(
        None, 
        description="系统提示词",
        max_length=10000
    )
    user_prompt: str = Field(
        ..., 
        description="用户提示词",
        min_length=1,
        max_length=50000
    )
    temperature: Optional[float] = Field(
        0.7, 
        description="温度参数",
        ge=0,
        le=2
    )
    max_tokens: Optional[int] = Field(
        None, 
        description="最大输出 Token 数",
        ge=1,
        le=128000
    )
    timeout: Optional[int] = Field(
        60, 
        description="单个模型超时时间（秒）",
        ge=1,
        le=300
    )
    user_id: Optional[str] = Field(None, description="用户ID")
    save_history: bool = Field(True, description="是否保存到历史记录")
    api_config: Optional[ApiConfig] = Field(
        None, 
        description="自定义 API 配置（如第三方供应商的 API Key 和 URL）"
    )


class ModelResult(BaseModel):
    """单个模型的测试结果"""
    model_id: str = Field(..., description="模型ID")
    model_name: str = Field(..., description="模型显示名称")
    provider: str = Field(..., description="提供商")
    status: str = Field(..., description="状态: success / error / timeout")
    response: Optional[str] = Field(None, description="模型响应内容")
    token_usage: Optional[TokenUsage] = Field(None, description="Token 使用量")
    latency_ms: Optional[int] = Field(None, description="响应延迟（毫秒）")
    cost_usd: Optional[float] = Field(None, description="费用（美元）")
    cost_cny: Optional[float] = Field(None, description="费用（人民币）")
    error: Optional[str] = Field(None, description="错误信息")


class CompareSummary(BaseModel):
    """对比测试摘要统计"""
    total_models: int = Field(..., description="测试模型总数")
    success_count: int = Field(..., description="成功数量")
    failed_count: int = Field(..., description="失败数量")
    avg_latency_ms: Optional[float] = Field(None, description="平均响应延迟（毫秒）")
    min_latency_ms: Optional[int] = Field(None, description="最小响应延迟（毫秒）")
    max_latency_ms: Optional[int] = Field(None, description="最大响应延迟（毫秒）")
    total_tokens: int = Field(0, description="总 Token 使用量")
    total_cost_usd: Optional[float] = Field(None, description="总费用（美元）")
    total_cost_cny: Optional[float] = Field(None, description="总费用（人民币）")


class ModelCompareResponse(BaseModel):
    """模型对比测试响应"""
    task_id: str = Field(..., description="任务ID")
    prompt: str = Field(..., description="用户提示词")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    created_at: datetime = Field(..., description="创建时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    results: List[ModelResult] = Field(..., description="各模型测试结果")
    summary: CompareSummary = Field(..., description="统计摘要")


# ============================================================================
# 异步任务相关 Schema
# ============================================================================

class AsyncTaskResponse(BaseModel):
    """异步任务创建响应"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态: pending / running / completed / failed")
    created_at: datetime = Field(..., description="创建时间")
    estimated_time_seconds: Optional[int] = Field(None, description="预估完成时间（秒）")


class TaskProgress(BaseModel):
    """任务进度"""
    total: int = Field(..., description="总模型数")
    completed: int = Field(..., description="已完成数")
    failed: int = Field(..., description="失败数")
    pending: int = Field(..., description="等待中数")


class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态: pending / running / completed / failed")
    progress: TaskProgress = Field(..., description="进度信息")
    results: List[ModelResult] = Field(default_factory=list, description="已完成的结果")
    created_at: datetime = Field(..., description="创建时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")


# ============================================================================
# 历史记录相关 Schema
# ============================================================================

class HistoryListRequest(BaseModel):
    """历史记录列表请求"""
    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(20, description="每页数量", ge=1, le=100)
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    user_id: Optional[str] = Field(None, description="用户ID")


class HistorySummary(BaseModel):
    """历史记录摘要（列表展示用）"""
    id: str = Field(..., description="记录ID")
    prompt: str = Field(..., description="用户提示词（可能被截断）")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    models: List[str] = Field(..., description="测试的模型ID列表")
    model_names: List[str] = Field(..., description="测试的模型名称列表")
    created_at: datetime = Field(..., description="创建时间")
    summary: CompareSummary = Field(..., description="统计摘要")


class PaginationInfo(BaseModel):
    """分页信息"""
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total: int = Field(..., description="总记录数")
    total_pages: int = Field(..., description="总页数")


class HistoryListResponse(BaseModel):
    """历史记录列表响应"""
    items: List[HistorySummary] = Field(..., description="历史记录列表")
    pagination: PaginationInfo = Field(..., description="分页信息")


class HistoryDetailResponse(BaseModel):
    """历史记录详情响应（完整数据）"""
    id: str = Field(..., description="记录ID")
    prompt: str = Field(..., description="用户提示词")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(None, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大 Token 数")
    created_at: datetime = Field(..., description="创建时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    results: List[ModelResult] = Field(..., description="各模型测试结果")
    summary: CompareSummary = Field(..., description="统计摘要")
    user_id: Optional[str] = Field(None, description="用户ID")


# ============================================================================
# 对比历史相关 Schema (2.0 增强)
# ============================================================================

class CompareHistoryListRequest(BaseModel):
    """对比历史列表请求"""
    page: int = Field(1, description="页码", ge=1)
    page_size: int = Field(20, description="每页数量", ge=1, le=100)
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    user_id: Optional[str] = Field(None, description="用户ID")


class CompareHistoryItem(BaseModel):
    """对比历史列表项"""
    id: int = Field(..., description="记录ID")
    task_id: str = Field(..., description="任务ID")
    user_prompt: str = Field(..., description="用户提示词（可能被截断）")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    model_ids: List[str] = Field(..., description="测试的模型ID列表")
    total_models: int = Field(..., description="测试模型总数")
    success_count: int = Field(..., description="成功数量")
    failed_count: int = Field(..., description="失败数量")
    avg_latency_ms: Optional[int] = Field(None, description="平均响应延迟")
    total_tokens: int = Field(0, description="总 Token 使用量")
    total_cost_cny: float = Field(0.0, description="总费用（人民币）")
    created_at: datetime = Field(..., description="创建时间")


class CompareHistoryListResponse(BaseModel):
    """对比历史列表响应"""
    items: List[CompareHistoryItem] = Field(..., description="历史记录列表")
    pagination: PaginationInfo = Field(..., description="分页信息")


class CompareHistoryDetailResponse(BaseModel):
    """对比历史详情响应"""
    id: int = Field(..., description="记录ID")
    task_id: str = Field(..., description="任务ID")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    user_prompt: str = Field(..., description="用户提示词")
    temperature: Optional[float] = Field(None, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大 Token 数")
    model_ids: List[str] = Field(..., description="测试的模型ID列表")
    api_config_id: Optional[int] = Field(None, description="使用的 API 配置ID")
    total_models: int = Field(..., description="测试模型总数")
    success_count: int = Field(..., description="成功数量")
    failed_count: int = Field(..., description="失败数量")
    avg_latency_ms: Optional[int] = Field(None, description="平均响应延迟")
    total_tokens: int = Field(0, description="总 Token 使用量")
    total_cost_usd: float = Field(0.0, description="总费用（美元）")
    total_cost_cny: float = Field(0.0, description="总费用（人民币）")
    created_at: datetime = Field(..., description="创建时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    results: List[ModelResult] = Field(..., description="各模型测试结果")


# ============================================================================
# 统计相关 Schema (2.0 新增)
# ============================================================================

class CompareStatsResponse(BaseModel):
    """对比统计响应"""
    total_compares: int = Field(..., description="总对比次数")
    total_models_tested: int = Field(..., description="测试模型总次数")
    total_success: int = Field(..., description="成功总数")
    total_failed: int = Field(..., description="失败总数")
    success_rate: float = Field(..., description="成功率")
    total_tokens: int = Field(..., description="总 Token 使用量")
    total_cost_usd: float = Field(..., description="总费用（美元）")
    total_cost_cny: float = Field(..., description="总费用（人民币）")
    avg_latency_ms: int = Field(..., description="平均响应延迟（毫秒）")


class ModelUsageStatsItem(BaseModel):
    """模型使用统计项"""
    model_id: str = Field(..., description="模型ID")
    model_name: str = Field(..., description="模型名称")
    provider: str = Field(..., description="提供商")
    usage_count: int = Field(..., description="使用次数")
    success_count: int = Field(..., description="成功次数")
    success_rate: float = Field(..., description="成功率")
    total_tokens: int = Field(..., description="总 Token 使用量")
    total_cost_cny: float = Field(..., description="总费用（人民币）")
    avg_latency_ms: int = Field(..., description="平均响应延迟（毫秒）")


class ModelUsageStatsResponse(BaseModel):
    """模型使用统计响应"""
    items: List[ModelUsageStatsItem] = Field(..., description="模型使用统计列表")
