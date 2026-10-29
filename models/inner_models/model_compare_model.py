#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/07
# @Author : AI Assistant
"""
模型对比 2.0 数据库模型
包含：API配置表、模型管理表、对比记录表、模型结果表
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime,
    Text, JSON, DECIMAL, Index, ForeignKey
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import relationship

from models.inner_models.base import Base


class ModelCompareApiConfig(Base):
    """API 配置表 - 存储第三方供应商的 API 配置"""
    __tablename__ = "model_compare_api_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(64), nullable=False, comment="配置名称")
    provider = Column(String(32), nullable=False, index=True, comment="供应商名称（如 OpenAI, 中转服务商名）")
    api_type = Column(String(16), nullable=False, default="generic", 
                      comment="API 协议类型: openai / deepseek / generic")
    api_key = Column(String(512), nullable=False, comment="API Key")
    api_url = Column(String(256), nullable=True, comment="API URL（完整地址，如 https://api.xxx.com/v1/chat/completions）")
    extra_headers = Column(JSON, nullable=True, comment="额外请求头（JSON格式）")
    extra_params = Column(JSON, nullable=True, comment="额外请求参数（JSON格式）")
    description = Column(String(256), nullable=True, comment="配置描述")
    is_default = Column(TINYINT, nullable=False, default=0, comment="是否默认配置")
    is_active = Column(TINYINT, nullable=False, default=1, index=True, comment="是否启用")
    user_id = Column(String(64), nullable=True, index=True, comment="用户ID（可选，支持多租户）")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 唯一约束
    __table_args__ = (
        Index('uk_name_user', 'name', 'user_id', unique=True),
    )

    def __repr__(self):
        return f"<ModelCompareApiConfig(id={self.id}, name={self.name}, provider={self.provider})>"

    def to_dict(self, hide_key: bool = True) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "api_type": self.api_type,
            "api_key": "***" if hide_key else self.api_key,
            "api_url": self.api_url,
            "extra_headers": self.extra_headers,
            "extra_params": self.extra_params,
            "description": self.description,
            "is_default": bool(self.is_default),
            "is_active": bool(self.is_active),
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ModelCompareModel(Base):
    """模型管理表 - 存储可用模型配置"""
    __tablename__ = "model_compare_model"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    model_id = Column(String(64), nullable=False, index=True, comment="模型ID（如 gpt-4o, deepseek-chat）")
    name = Column(String(64), nullable=False, comment="模型显示名称")
    provider = Column(String(32), nullable=False, index=True, comment="提供商显示名称")
    description = Column(String(512), nullable=True, comment="模型描述")
    max_tokens = Column(Integer, nullable=True, comment="模型上下文 Token 上限")
    max_output_tokens = Column(Integer, nullable=True, comment="单次请求最大输出 Token 数")
    supports_streaming = Column(TINYINT, nullable=False, default=1, comment="是否支持流式输出")
    supports_thinking = Column(TINYINT, nullable=False, default=0, comment="是否支持思考模式")
    use_max_completion_tokens = Column(TINYINT, nullable=False, default=0, 
                                       comment="是否使用 max_completion_tokens（o1/o3 等模型需要）")
    input_price_per_1m = Column(DECIMAL(10, 6), nullable=False, default=Decimal("0.000000"), 
                                comment="输入价格（$/1M tokens）")
    output_price_per_1m = Column(DECIMAL(10, 6), nullable=False, default=Decimal("0.000000"), 
                                 comment="输出价格（$/1M tokens）")
    api_config_id = Column(Integer, ForeignKey("model_compare_api_config.id", ondelete="SET NULL"),
                          nullable=True, index=True, comment="关联的 API 配置ID")
    custom_params = Column(JSON, nullable=True, comment="模型特定参数（JSON格式）")
    tags = Column(JSON, nullable=True, comment="标签列表（JSON数组，如 ['对话', '视频', '视觉']）")
    status = Column(String(16), nullable=False, default="unknown", index=True, 
                   comment="可用状态: available / unavailable / unknown")
    last_test_at = Column(DateTime, nullable=True, comment="最后测试时间")
    last_test_latency_ms = Column(Integer, nullable=True, comment="最后测试延迟（毫秒）")
    last_test_error = Column(Text, nullable=True, comment="最后测试错误信息")
    is_active = Column(TINYINT, nullable=False, default=1, index=True, comment="是否启用")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序权重")
    user_id = Column(String(64), nullable=True, index=True, comment="用户ID（可选）")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联 API 配置
    api_config = relationship("ModelCompareApiConfig", foreign_keys=[api_config_id])

    # 唯一约束
    __table_args__ = (
        Index('uk_model_user', 'model_id', 'user_id', unique=True),
    )

    def __repr__(self):
        return f"<ModelCompareModel(id={self.id}, model_id={self.model_id}, status={self.status})>"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "model_id": self.model_id,
            "name": self.name,
            "provider": self.provider,
            "description": self.description,
            "max_tokens": self.max_tokens,
            "max_output_tokens": self.max_output_tokens,
            "supports_streaming": bool(self.supports_streaming),
            "supports_thinking": bool(self.supports_thinking),
            "use_max_completion_tokens": bool(self.use_max_completion_tokens),
            "input_price_per_1m": float(self.input_price_per_1m) if self.input_price_per_1m else 0.0,
            "output_price_per_1m": float(self.output_price_per_1m) if self.output_price_per_1m else 0.0,
            "api_config_id": self.api_config_id,
            "custom_params": self.custom_params,
            "tags": self.tags if self.tags else [],
            "status": self.status,
            "last_test_at": self.last_test_at.isoformat() if self.last_test_at else None,
            "last_test_latency_ms": self.last_test_latency_ms,
            "last_test_error": self.last_test_error,
            "is_active": bool(self.is_active),
            "sort_order": self.sort_order,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def input_price_per_1k(self) -> float:
        """获取每 1K tokens 的输入价格"""
        return float(self.input_price_per_1m) / 1000 if self.input_price_per_1m else 0.0

    @property
    def output_price_per_1k(self) -> float:
        """获取每 1K tokens 的输出价格"""
        return float(self.output_price_per_1m) / 1000 if self.output_price_per_1m else 0.0


class ModelCompareHistory(Base):
    """模型对比历史记录表"""
    __tablename__ = "model_compare_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    task_id = Column(String(64), nullable=False, unique=True, index=True, comment="任务ID")
    system_prompt = Column(Text, nullable=True, comment="系统提示词")
    user_prompt = Column(Text, nullable=False, comment="用户提示词")
    temperature = Column(DECIMAL(3, 2), nullable=True, comment="温度参数")
    max_tokens = Column(Integer, nullable=True, comment="最大 Token 数")
    timeout = Column(Integer, nullable=True, comment="超时时间（秒）")
    model_ids = Column(JSON, nullable=False, comment="测试的模型ID列表")
    api_config_id = Column(Integer, nullable=True, comment="使用的 API 配置ID")
    total_models = Column(Integer, nullable=False, default=0, comment="测试模型总数")
    success_count = Column(Integer, nullable=False, default=0, comment="成功数量")
    failed_count = Column(Integer, nullable=False, default=0, comment="失败数量")
    avg_latency_ms = Column(Integer, nullable=True, comment="平均响应延迟")
    total_tokens = Column(Integer, nullable=False, default=0, comment="总 Token 使用量")
    total_cost_usd = Column(DECIMAL(10, 6), nullable=False, default=Decimal("0.000000"), comment="总费用（美元）")
    total_cost_cny = Column(DECIMAL(10, 4), nullable=False, default=Decimal("0.0000"), comment="总费用（人民币）")
    user_id = Column(String(64), nullable=True, index=True, comment="用户ID")
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True, comment="创建时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    # 关联模型结果
    results = relationship("ModelCompareResult", back_populates="history", lazy="dynamic")

    def __repr__(self):
        return f"<ModelCompareHistory(id={self.id}, task_id={self.task_id})>"

    def to_dict(self, include_results: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "id": self.id,
            "task_id": self.task_id,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "temperature": float(self.temperature) if self.temperature else None,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "model_ids": self.model_ids,
            "api_config_id": self.api_config_id,
            "total_models": self.total_models,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "avg_latency_ms": self.avg_latency_ms,
            "total_tokens": self.total_tokens,
            "total_cost_usd": float(self.total_cost_usd) if self.total_cost_usd else 0.0,
            "total_cost_cny": float(self.total_cost_cny) if self.total_cost_cny else 0.0,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_results:
            data["results"] = [r.to_dict() for r in self.results]
        return data


class ModelTag(Base):
    """模型标签管理表 - 存储可用的标签"""
    __tablename__ = "model_tag"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name = Column(String(32), nullable=False, unique=True, comment="标签名称（如：对话、视频、视觉）")
    color = Column(String(16), nullable=True, comment="标签颜色（可选，用于UI显示）")
    description = Column(String(256), nullable=True, comment="标签描述")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序权重")
    is_active = Column(TINYINT, nullable=False, default=1, comment="是否启用")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return f"<ModelTag(id={self.id}, name={self.name})>"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "description": self.description,
            "sort_order": self.sort_order,
            "is_active": bool(self.is_active),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ModelCompareResult(Base):
    """模型对比结果详情表"""
    __tablename__ = "model_compare_result"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    history_id = Column(BigInteger, ForeignKey("model_compare_history.id", ondelete="CASCADE"), 
                       nullable=False, index=True, comment="关联的历史记录ID")
    model_id = Column(String(64), nullable=False, index=True, comment="模型ID")
    model_name = Column(String(64), nullable=False, comment="模型显示名称")
    provider = Column(String(32), nullable=False, comment="提供商")
    status = Column(String(16), nullable=False, comment="状态: success / error / timeout")
    response = Column(Text, nullable=True, comment="模型响应内容")
    thinking_content = Column(Text, nullable=True, comment="思考内容（如支持）")
    prompt_tokens = Column(Integer, nullable=False, default=0, comment="输入 Token 数")
    completion_tokens = Column(Integer, nullable=False, default=0, comment="输出 Token 数")
    total_tokens = Column(Integer, nullable=False, default=0, comment="总 Token 数")
    latency_ms = Column(Integer, nullable=True, comment="响应延迟（毫秒）")
    cost_usd = Column(DECIMAL(10, 6), nullable=False, default=Decimal("0.000000"), comment="费用（美元）")
    cost_cny = Column(DECIMAL(10, 4), nullable=False, default=Decimal("0.0000"), comment="费用（人民币）")
    error = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    # 关联历史记录
    history = relationship("ModelCompareHistory", back_populates="results")

    def __repr__(self):
        return f"<ModelCompareResult(id={self.id}, model_id={self.model_id}, status={self.status})>"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "history_id": self.history_id,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "provider": self.provider,
            "status": self.status,
            "response": self.response,
            "thinking_content": self.thinking_content,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "cost_usd": float(self.cost_usd) if self.cost_usd else 0.0,
            "cost_cny": float(self.cost_cny) if self.cost_cny else 0.0,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
