#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/11
# @Author : AI Assistant
"""
模型管理 API Schema
定义模型管理和 API 配置相关的请求/响应数据模型
从 model_compare_schema.py 中抽离，作为独立的公共模块
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# API 配置相关 Schema
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
# 模型管理相关 Schema
# ============================================================================

class ModelCreate(BaseModel):
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


class ModelUpdate(BaseModel):
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


class ModelResponse(BaseModel):
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


class ModelListResponse(BaseModel):
    """模型管理列表响应"""
    items: List[ModelResponse] = Field(..., description="模型列表")
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
# 标签管理相关 Schema
# ============================================================================

class TagCreate(BaseModel):
    """创建标签请求"""
    name: str = Field(..., description="标签名称", min_length=1, max_length=32)
    color: Optional[str] = Field(None, description="标签颜色", max_length=16)
    description: Optional[str] = Field(None, description="标签描述", max_length=256)
    sort_order: int = Field(0, description="排序权重")


class TagUpdate(BaseModel):
    """更新标签请求"""
    name: Optional[str] = Field(None, description="标签名称", max_length=32)
    color: Optional[str] = Field(None, description="标签颜色", max_length=16)
    description: Optional[str] = Field(None, description="标签描述", max_length=256)
    sort_order: Optional[int] = Field(None, description="排序权重")
    is_active: Optional[bool] = Field(None, description="是否启用")


class TagResponse(BaseModel):
    """标签响应"""
    id: int = Field(..., description="标签ID")
    name: str = Field(..., description="标签名称")
    color: Optional[str] = Field(None, description="标签颜色")
    description: Optional[str] = Field(None, description="标签描述")
    sort_order: int = Field(0, description="排序权重")
    is_active: bool = Field(True, description="是否启用")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class TagListResponse(BaseModel):
    """标签列表响应"""
    items: List[TagResponse] = Field(..., description="标签列表")
    total: int = Field(..., description="总数")
