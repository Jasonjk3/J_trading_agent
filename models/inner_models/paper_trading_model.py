#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模拟盘数据库模型。"""
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Column, DateTime, DECIMAL, Enum as SQLEnum, Index, String, Text

from models.inner_models.base import Base


class PaperAccountType(str, PyEnum):
    HUMAN = "human"
    AGENT = "agent"


class PaperAccountStatus(str, PyEnum):
    RUNNING = "running"
    PAUSED = "paused"


class PaperTradeSide(str, PyEnum):
    BUY = "buy"
    SELL = "sell"


class PaperTradingAccountModel(Base):
    __tablename__ = "paper_trading_accounts"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    source_agent_id = Column(String(36), nullable=True, index=True)
    account_type = Column(
        SQLEnum(PaperAccountType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PaperAccountType.HUMAN,
    )
    name = Column(String(100), nullable=False)
    status = Column(
        SQLEnum(PaperAccountStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PaperAccountStatus.RUNNING,
        index=True,
    )
    currency = Column(String(10), nullable=False, default="CNY")
    initial_capital = Column(DECIMAL(20, 8), nullable=False, default=Decimal("0"))
    cash_balance = Column(DECIMAL(20, 8), nullable=False, default=Decimal("0"))
    realized_pnl = Column(DECIMAL(20, 8), nullable=False, default=Decimal("0"))
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_paper_account_user_status", "user_id", "status"),
        Index("uq_paper_account_user_agent", "user_id", "source_agent_id", unique=True),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class PaperPositionModel(Base):
    __tablename__ = "paper_trading_positions"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    symbol = Column(String(30), nullable=False)
    quantity = Column(DECIMAL(28, 12), nullable=False, default=Decimal("0"))
    average_price = Column(DECIMAL(20, 8), nullable=False, default=Decimal("0"))
    last_price = Column(DECIMAL(20, 8), nullable=False, default=Decimal("0"))
    realized_pnl = Column(DECIMAL(20, 8), nullable=False, default=Decimal("0"))
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("uq_paper_position_account_symbol", "account_id", "symbol", unique=True),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class PaperDecisionModel(Base):
    __tablename__ = "paper_trading_decisions"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    source_agent_id = Column(String(36), nullable=True, index=True)
    symbol = Column(String(30), nullable=False)
    action = Column(String(20), nullable=False)
    title = Column(String(120), nullable=True)
    summary = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    reference_price = Column(DECIMAL(20, 8), nullable=True)
    confidence = Column(DECIMAL(8, 4), nullable=True)
    result = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)

    __table_args__ = (
        Index("idx_paper_decision_account_time", "account_id", "created_at"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class PaperTradeModel(Base):
    __tablename__ = "paper_trading_trades"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    decision_id = Column(String(36), nullable=True, index=True)
    symbol = Column(String(30), nullable=False)
    side = Column(
        SQLEnum(PaperTradeSide, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    price = Column(DECIMAL(20, 8), nullable=False)
    quantity = Column(DECIMAL(28, 12), nullable=False)
    amount = Column(DECIMAL(20, 8), nullable=False)
    realized_pnl = Column(DECIMAL(20, 8), nullable=False, default=Decimal("0"))
    executed_at = Column(DateTime, nullable=False, default=datetime.now, index=True)

    __table_args__ = (
        Index("idx_paper_trade_account_time", "account_id", "executed_at"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )


class PaperEquityRecordModel(Base):
    __tablename__ = "paper_trading_equity_records"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(36), nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    equity = Column(DECIMAL(20, 8), nullable=False)
    return_rate = Column(DECIMAL(12, 6), nullable=False, default=Decimal("0"))

    __table_args__ = (
        Index("idx_paper_equity_account_time", "account_id", "recorded_at"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )
