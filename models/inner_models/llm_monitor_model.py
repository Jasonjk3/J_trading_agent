#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
LLM 监控数据库模型
包含：调用日志表、每日统计表、模型费用配置表
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Date,
    Text, JSON, DECIMAL, Index
)
from sqlalchemy.dialects.mysql import TINYINT

from models.inner_models.base import Base


class LLMUsageLog(Base):
    """LLM 调用日志表模型"""
    __tablename__ = "llm_usage_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键，自增")
    request_id = Column(String(64), nullable=False, index=True, comment="请求唯一标识（UUID）")
    model_name = Column(String(64), nullable=False, index=True, comment="模型名称（如 deepseek-chat, gpt-4）")
    model_provider = Column(String(32), nullable=False, comment="提供商（deepseek, openai）")
    agent_name = Column(String(128), nullable=True, index=True, comment="调用的 Agent 名称")
    task_type = Column(String(64), nullable=True, comment="任务类型（chat, analysis, extraction 等）")
    prompt_tokens = Column(Integer, nullable=False, default=0, comment="输入 Token 数")
    completion_tokens = Column(Integer, nullable=False, default=0, comment="输出 Token 数")
    total_tokens = Column(Integer, nullable=False, default=0, comment="总 Token 数")
    cost_usd = Column(DECIMAL(10, 6), nullable=False, default=Decimal("0.000000"), comment="费用（美元）")
    cost_cny = Column(DECIMAL(10, 4), nullable=False, default=Decimal("0.0000"), comment="费用（人民币）")
    response_time_ms = Column(Integer, nullable=False, default=0, comment="响应时间（毫秒）")
    status = Column(String(16), nullable=False, default="success", index=True, comment="状态（success, failed, timeout）")
    error_message = Column(Text, nullable=True, comment="错误信息（如有）")
    user_id = Column(String(64), nullable=True, comment="用户标识（可选）")
    session_id = Column(String(64), nullable=True, comment="会话标识（可选）")
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True, comment="创建时间")
    extra_data = Column(JSON, nullable=True, comment="扩展字段（存储其他元数据）")

    # 复合索引
    __table_args__ = (
        Index('idx_user_session', 'user_id', 'session_id'),
    )

    def __repr__(self):
        return (
            f"<LLMUsageLog(id={self.id}, request_id={self.request_id}, "
            f"model={self.model_name}, tokens={self.total_tokens}, status={self.status})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "request_id": self.request_id,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": float(self.cost_usd) if self.cost_usd else 0.0,
            "cost_cny": float(self.cost_cny) if self.cost_cny else 0.0,
            "response_time_ms": self.response_time_ms,
            "status": self.status,
            "error_message": self.error_message,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "extra_data": self.extra_data,
        }


class LLMDailyStats(Base):
    """LLM 每日统计表模型"""
    __tablename__ = "llm_daily_stats"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    stat_date = Column(Date, nullable=False, index=True, comment="统计日期")
    model_name = Column(String(64), nullable=False, index=True, comment="模型名称")
    agent_name = Column(String(128), nullable=False, default="", comment="Agent 名称（空字符串表示汇总）")
    total_requests = Column(Integer, nullable=False, default=0, comment="总请求数")
    success_requests = Column(Integer, nullable=False, default=0, comment="成功请求数")
    failed_requests = Column(Integer, nullable=False, default=0, comment="失败请求数")
    total_prompt_tokens = Column(BigInteger, nullable=False, default=0, comment="总输入 Token")
    total_completion_tokens = Column(BigInteger, nullable=False, default=0, comment="总输出 Token")
    total_tokens = Column(BigInteger, nullable=False, default=0, comment="总 Token")
    total_cost_usd = Column(DECIMAL(12, 6), nullable=False, default=Decimal("0.000000"), comment="总费用（美元）")
    total_cost_cny = Column(DECIMAL(12, 4), nullable=False, default=Decimal("0.0000"), comment="总费用（人民币）")
    avg_response_time_ms = Column(Integer, nullable=False, default=0, comment="平均响应时间")
    p50_response_time_ms = Column(Integer, nullable=False, default=0, comment="P50 响应时间")
    p99_response_time_ms = Column(Integer, nullable=False, default=0, comment="P99 响应时间")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 唯一约束
    __table_args__ = (
        Index('uk_date_model_agent', 'stat_date', 'model_name', 'agent_name', unique=True),
    )

    def __repr__(self):
        return (
            f"<LLMDailyStats(id={self.id}, date={self.stat_date}, "
            f"model={self.model_name}, requests={self.total_requests})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "stat_date": self.stat_date.isoformat() if self.stat_date else None,
            "model_name": self.model_name,
            "agent_name": self.agent_name,
            "total_requests": self.total_requests,
            "success_requests": self.success_requests,
            "failed_requests": self.failed_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": float(self.total_cost_usd) if self.total_cost_usd else 0.0,
            "total_cost_cny": float(self.total_cost_cny) if self.total_cost_cny else 0.0,
            "avg_response_time_ms": self.avg_response_time_ms,
            "p50_response_time_ms": self.p50_response_time_ms,
            "p99_response_time_ms": self.p99_response_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LLMCostConfig(Base):
    """模型费用配置表模型"""
    __tablename__ = "llm_cost_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    model_name = Column(String(64), nullable=False, index=True, comment="模型名称")
    provider = Column(String(32), nullable=False, index=True, comment="提供商")
    input_price_per_1m = Column(DECIMAL(10, 6), nullable=False, default=Decimal("0.000000"), 
                                comment="输入 Token 单价（$/1M tokens）")
    output_price_per_1m = Column(DECIMAL(10, 6), nullable=False, default=Decimal("0.000000"), 
                                 comment="输出 Token 单价（$/1M tokens）")
    currency = Column(String(8), nullable=False, default="USD", comment="货币单位（USD）")
    exchange_rate = Column(DECIMAL(8, 4), nullable=False, default=Decimal("7.2500"), 
                          comment="美元兑人民币汇率")
    effective_date = Column(Date, nullable=False, comment="生效日期")
    is_active = Column(TINYINT, nullable=False, default=1, index=True, comment="是否生效（1=是，0=否）")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 唯一约束
    __table_args__ = (
        Index('uk_model_provider_date', 'model_name', 'provider', 'effective_date', unique=True),
    )

    def __repr__(self):
        return (
            f"<LLMCostConfig(id={self.id}, model={self.model_name}, "
            f"provider={self.provider}, active={self.is_active})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "model_name": self.model_name,
            "provider": self.provider,
            "input_price_per_1m": float(self.input_price_per_1m) if self.input_price_per_1m else 0.0,
            "output_price_per_1m": float(self.output_price_per_1m) if self.output_price_per_1m else 0.0,
            "currency": self.currency,
            "exchange_rate": float(self.exchange_rate) if self.exchange_rate else 7.25,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "is_active": bool(self.is_active),
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


class LLMBudgetAlertRule(Base):
    """预警规则表模型"""
    __tablename__ = "llm_budget_alert_rule"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    rule_name = Column(String(64), nullable=False, comment="规则名称")
    alert_type = Column(String(32), nullable=False, index=True, comment="预警类型（daily_cost/monthly_cost/single_request）")
    threshold_value = Column(DECIMAL(12, 4), nullable=False, comment="阈值（人民币）")
    model_name = Column(String(64), nullable=True, comment="模型名称（可选，为空表示全部）")
    agent_name = Column(String(128), nullable=True, comment="Agent 名称（可选，为空表示全部）")
    notify_channels = Column(JSON, nullable=False, comment="通知渠道配置（飞书webhook/邮件）")
    is_active = Column(TINYINT, nullable=False, default=1, index=True, comment="是否启用")
    cooldown_minutes = Column(Integer, nullable=False, default=60, comment="冷却时间（分钟），避免重复告警")
    last_triggered_at = Column(DateTime, nullable=True, comment="上次触发时间")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def __repr__(self):
        return (
            f"<LLMBudgetAlertRule(id={self.id}, name={self.rule_name}, "
            f"type={self.alert_type}, threshold={self.threshold_value})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "rule_name": self.rule_name,
            "alert_type": self.alert_type,
            "threshold_value": float(self.threshold_value) if self.threshold_value else 0.0,
            "model_name": self.model_name,
            "agent_name": self.agent_name,
            "notify_channels": self.notify_channels,
            "is_active": bool(self.is_active),
            "cooldown_minutes": self.cooldown_minutes,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LLMBudgetAlertHistory(Base):
    """预警历史表模型"""
    __tablename__ = "llm_budget_alert_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    rule_id = Column(Integer, nullable=False, index=True, comment="关联规则ID")
    alert_type = Column(String(32), nullable=False, index=True, comment="预警类型")
    current_value = Column(DECIMAL(12, 4), nullable=False, comment="当前值")
    threshold_value = Column(DECIMAL(12, 4), nullable=False, comment="阈值")
    alert_message = Column(Text, nullable=False, comment="预警消息内容")
    notify_status = Column(String(16), nullable=False, default="pending", index=True, 
                          comment="通知状态（pending/success/failed）")
    notify_result = Column(JSON, nullable=True, comment="通知结果详情")
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True, comment="触发时间")

    def __repr__(self):
        return (
            f"<LLMBudgetAlertHistory(id={self.id}, rule_id={self.rule_id}, "
            f"type={self.alert_type}, status={self.notify_status})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "alert_type": self.alert_type,
            "current_value": float(self.current_value) if self.current_value else 0.0,
            "threshold_value": float(self.threshold_value) if self.threshold_value else 0.0,
            "alert_message": self.alert_message,
            "notify_status": self.notify_status,
            "notify_result": self.notify_result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
