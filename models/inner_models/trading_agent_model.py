#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交易 Agent 数据库模型
"""
from datetime import datetime
from enum import Enum as PyEnum
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, DateTime, JSON, Boolean,
    Enum as SQLEnum, Index, Text, DECIMAL
)

from models.inner_models.base import Base


class TradingAgentStatus(str, PyEnum):
    """交易 Agent 运行状态"""
    RUNNING = "running"
    STOPPED = "stopped"


class StrategyType(str, PyEnum):
    """策略类型"""
    MOMENTUM = "momentum"      # 趋势跟踪
    GRID = "grid"              # 网格
    ARBITRAGE = "arbitrage"    # 套利
    CUSTOM = "custom"          # 自定义


class TradingStyle(str, PyEnum):
    """交易风格"""
    CONSERVATIVE = "conservative"  # 稳定
    BALANCED = "balanced"          # 均衡
    AGGRESSIVE = "aggressive"      # 激进


class TradingCycle(str, PyEnum):
    """交易周期"""
    SHORT_TERM = "short_term"      # 短线（日内/几天）
    MEDIUM_TERM = "medium_term"    # 中线（数周）
    LONG_TERM = "long_term"        # 长线（数月）


class PositionDirection(str, PyEnum):
    """持仓方向限制"""
    LONG_ONLY = "long_only"        # 仅做多
    SHORT_ONLY = "short_only"      # 仅做空
    BOTH = "both"                  # 均可


class OperationType(str, PyEnum):
    """操作类型"""
    OPEN_LONG = "open_long"        # 开多
    OPEN_SHORT = "open_short"      # 开空
    CLOSE_LONG = "close_long"      # 平多
    CLOSE_SHORT = "close_short"    # 平空
    ADJUST = "adjust"              # 调仓
    CANCEL_ORDER = "cancel_order"  # 撤单
    OTHER = "other"                # 其他


class OperationResult(str, PyEnum):
    """操作结果"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # 部分成交


class TradingAgentModel(Base):
    """交易 Agent 表模型"""
    __tablename__ = "trading_agents"

    id = Column(String(36), primary_key=True, comment="Agent ID")
    user_id = Column(String(36), nullable=False, index=True, comment="所属用户ID")
    name = Column(String(100), nullable=False, comment="Agent 名称")
    strategy_type = Column(
        SQLEnum(StrategyType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=StrategyType.MOMENTUM,
        comment="策略类型"
    )
    exchange_account_id = Column(String(36), nullable=True, index=True, comment="绑定的交易所账户ID")
    llm_model_id = Column(Integer, nullable=True, comment="绑定的 LLM 模型ID")
    status = Column(
        SQLEnum(TradingAgentStatus, values_callable=lambda x: [e.value for e in x]),
        default=TradingAgentStatus.STOPPED,
        index=True,
        comment="运行状态"
    )
    strategy_config = Column(JSON, default=dict, comment="策略配置参数")
    remark = Column(String(255), nullable=True, comment="备注")
    last_run_at = Column(DateTime, nullable=True, comment="最近运行时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    __table_args__ = (
        Index('idx_trading_agent_user_status', 'user_id', 'status'),
    )

    def __repr__(self):
        return f"<TradingAgentModel(id={self.id}, name={self.name}, status={self.status})>"

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.status == TradingAgentStatus.RUNNING


class AgentOperationModel(Base):
    """Agent 操作记录表模型"""
    __tablename__ = "agent_operations"

    id = Column(String(36), primary_key=True, comment="记录ID")
    agent_id = Column(String(36), nullable=False, index=True, comment="所属 Agent ID")
    type = Column(
        SQLEnum(OperationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        comment="操作类型"
    )
    symbol = Column(String(20), nullable=True, comment="交易对")
    side = Column(String(10), nullable=True, comment="买/卖方向")
    quantity = Column(String(50), nullable=True, comment="数量")
    price = Column(String(50), nullable=True, comment="价格")
    reason = Column(Text, nullable=True, comment="操作原因（LLM分析结果）")
    result = Column(
        SQLEnum(OperationResult, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        comment="执行结果"
    )
    chain_of_thought = Column(JSON, default=list, comment="思维链详情")
    order_id = Column(String(100), nullable=True, comment="交易所订单ID")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    __table_args__ = (
        Index('idx_operation_agent_time', 'agent_id', 'created_at'),
    )

    def __repr__(self):
        return f"<AgentOperationModel(id={self.id}, agent_id={self.agent_id}, type={self.type})>"


class AgentProfitRecordModel(Base):
    """Agent 收益记录表模型"""
    __tablename__ = "agent_profit_records"

    id = Column(String(36), primary_key=True, comment="记录ID")
    agent_id = Column(String(36), nullable=False, index=True, comment="所属 Agent ID")
    record_time = Column(DateTime, nullable=False, index=True, comment="记录时间")
    value = Column(DECIMAL(20, 8), default=Decimal('0'), comment="当期收益")
    cumulative = Column(DECIMAL(20, 8), default=Decimal('0'), comment="累计收益")
    equity = Column(DECIMAL(20, 8), nullable=True, comment="账户权益")
    unrealized_pnl = Column(DECIMAL(20, 8), nullable=True, comment="持仓未实现盈亏")
    unrealized_pnl_rate = Column(DECIMAL(10, 4), nullable=True, comment="持仓未实现盈亏率(%)")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index('idx_profit_agent_time', 'agent_id', 'record_time'),
    )

    def __repr__(self):
        return f"<AgentProfitRecordModel(id={self.id}, agent_id={self.agent_id}, value={self.value})>"
