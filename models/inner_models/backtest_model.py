#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测系统数据库模型
"""
from datetime import datetime
from enum import Enum as PyEnum
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, DateTime, JSON, Boolean,
    Enum as SQLEnum, Index, Text, DECIMAL, BigInteger
)

from models.inner_models.base import Base


class BacktestStatus(str, PyEnum):
    """回测任务状态"""
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 运行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 用户取消


class KlineInterval(str, PyEnum):
    """K线周期"""
    M1 = "1m"      # 1分钟
    M5 = "5m"      # 5分钟
    M15 = "15m"    # 15分钟
    H1 = "1h"      # 1小时
    H4 = "4h"      # 4小时
    D1 = "1d"      # 日线


class BacktestTaskModel(Base):
    """回测任务表模型"""
    __tablename__ = "backtest_tasks"

    id = Column(String(36), primary_key=True, comment="回测任务ID")
    user_id = Column(String(36), nullable=False, index=True, comment="所属用户ID")
    name = Column(String(100), nullable=False, comment="回测名称")
    status = Column(
        SQLEnum(BacktestStatus, values_callable=lambda x: [e.value for e in x]),
        default=BacktestStatus.PENDING,
        index=True,
        comment="任务状态"
    )
    progress = Column(Integer, default=0, comment="执行进度(0-100)")
    # 运行中写入：模拟时钟、步进、文案等，完成后清空（需 DB 增加列，见 scripts/sql/add_backtest_progress_snapshot.sql）
    progress_snapshot = Column(JSON, nullable=True, comment="运行中进度快照")
    
    # 关联 Agent
    agent_id = Column(String(36), nullable=False, index=True, comment="关联的 Agent ID")
    agent_name = Column(String(100), nullable=True, comment="Agent 名称(冗余)")
    strategy_type = Column(String(20), nullable=False, comment="策略类型")
    strategy_config = Column(JSON, default=dict, comment="策略配置")
    
    # 回测配置
    exchange = Column(String(20), nullable=False, default="okx", comment="交易所")
    symbols = Column(JSON, default=list, comment="交易对列表")
    interval = Column(
        SQLEnum(KlineInterval, values_callable=lambda x: [e.value for e in x]),
        default=KlineInterval.M15,
        comment="K线周期"
    )
    start_time = Column(DateTime, nullable=False, comment="回测开始时间")
    end_time = Column(DateTime, nullable=False, comment="回测结束时间")
    initial_capital = Column(DECIMAL(20, 2), nullable=False, comment="初始资金(USDT)")
    
    # 费用配置
    maker_fee = Column(DECIMAL(10, 4), default=Decimal('0.1'), comment="Maker手续费率(%)")
    taker_fee = Column(DECIMAL(10, 4), default=Decimal('0.1'), comment="Taker手续费率(%)")
    slippage = Column(DECIMAL(10, 4), default=Decimal('0.05'), comment="滑点(%)")
    
    # 回测结果统计
    result_statistics = Column(JSON, nullable=True, comment="回测结果统计")
    
    # 错误信息
    error_message = Column(Text, nullable=True, comment="错误信息")
    
    # 时间戳
    started_at = Column(DateTime, nullable=True, comment="开始执行时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    __table_args__ = (
        Index('idx_backtest_user_status', 'user_id', 'status'),
        Index('idx_backtest_user_created', 'user_id', 'created_at'),
        Index('idx_backtest_agent', 'agent_id'),
    )

    def __repr__(self):
        return f"<BacktestTaskModel(id={self.id}, name={self.name}, status={self.status})>"


class BacktestTradeModel(Base):
    """回测交易记录表模型"""
    __tablename__ = "backtest_trades"

    id = Column(String(36), primary_key=True, comment="交易记录ID")
    backtest_id = Column(String(36), nullable=False, index=True, comment="所属回测任务ID")
    
    # 交易信息
    timestamp = Column(DateTime, nullable=False, index=True, comment="交易时间")
    symbol = Column(String(20), nullable=False, comment="交易对")
    side = Column(String(10), nullable=False, comment="买/卖方向(buy/sell)")
    trade_type = Column(String(10), nullable=False, comment="交易类型(open/close)")
    action = Column(String(20), nullable=True, comment="最终动作(open/add/reduce/close + long/short)")
    leverage = Column(DECIMAL(10, 4), nullable=False, default=Decimal('1'), comment="实际批准杠杆")
    margin_used = Column(DECIMAL(20, 8), nullable=False, default=Decimal('0'), comment="本次成交对应保证金")
    
    # 价格和数量
    price = Column(DECIMAL(20, 8), nullable=False, comment="成交价格")
    quantity = Column(DECIMAL(20, 8), nullable=False, comment="成交数量")
    amount = Column(DECIMAL(20, 8), nullable=False, comment="成交金额")
    fee = Column(DECIMAL(20, 8), default=Decimal('0'), comment="手续费")
    
    # 盈亏
    pnl = Column(DECIMAL(20, 8), default=Decimal('0'), comment="盈亏金额")
    pnl_percent = Column(DECIMAL(10, 4), default=Decimal('0'), comment="盈亏百分比")
    balance = Column(DECIMAL(20, 8), nullable=False, comment="交易后余额")
    
    # LLM 决策信息
    reasoning = Column(Text, nullable=True, comment="LLM 分析理由")
    signals = Column(JSON, nullable=True, comment="触发信号列表")
    chain_of_thought = Column(JSON, nullable=True, comment="思维链详情")
    
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index('idx_trade_backtest_time', 'backtest_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<BacktestTradeModel(id={self.id}, symbol={self.symbol}, side={self.side})>"


class BacktestEquityModel(Base):
    """回测权益曲线表模型"""
    __tablename__ = "backtest_equity_records"

    id = Column(String(36), primary_key=True, comment="记录ID")
    backtest_id = Column(String(36), nullable=False, index=True, comment="所属回测任务ID")
    
    timestamp = Column(DateTime, nullable=False, index=True, comment="记录时间")
    equity = Column(DECIMAL(20, 8), nullable=False, comment="账户权益")
    drawdown = Column(DECIMAL(10, 4), default=Decimal('0'), comment="回撤百分比")
    benchmark = Column(DECIMAL(20, 8), nullable=True, comment="基准权益(买入持有)")
    unrealized_pnl = Column(DECIMAL(20, 8), nullable=True, comment="持仓未实现盈亏")
    unrealized_pnl_rate = Column(DECIMAL(10, 4), nullable=True, comment="持仓未实现盈亏率(%)")
    
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index('idx_equity_backtest_time', 'backtest_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<BacktestEquityModel(id={self.id}, equity={self.equity})>"


class BacktestDecisionModel(Base):
    """回测决策记录表模型（每次决策含 hold，用于前端决策表格）"""
    __tablename__ = "backtest_decisions"

    id = Column(String(36), primary_key=True, comment="记录ID")
    backtest_id = Column(String(36), nullable=False, index=True, comment="所属回测任务ID")

    timestamp = Column(DateTime, nullable=False, index=True, comment="决策时间")
    action = Column(String(20), nullable=False, default="hold", comment="最终决策动作(hold/open/add/reduce/close + long/short/system_error)")
    symbol = Column(String(20), nullable=True, comment="交易对")
    quantity = Column(DECIMAL(20, 8), nullable=True, comment="数量")
    reasoning = Column(Text, nullable=True, comment="决策理由")
    decision_analysis = Column(Text, nullable=True, comment="决策分析结果")
    technical_analysis = Column(Text, nullable=True, comment="技术分析结果")
    chain_of_thought = Column(JSON, nullable=True, comment="思维链详情")
    reference_price = Column(DECIMAL(20, 8), nullable=True, comment="决策时点该交易对参考价")
    execution_result = Column(JSON, nullable=True, comment="最终执行结果（成交/拒绝/无操作及成交明细）")

    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index('idx_decision_backtest_time', 'backtest_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<BacktestDecisionModel(id={self.id}, action={self.action})>"


class HistoricalKlineModel(Base):
    """历史K线数据表模型"""
    __tablename__ = "historical_klines"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="记录ID")
    exchange = Column(String(20), nullable=False, comment="交易所")
    symbol = Column(String(20), nullable=False, comment="交易对")
    interval = Column(String(10), nullable=False, comment="K线周期")
    
    timestamp = Column(DateTime, nullable=False, comment="K线时间")
    open_price = Column(DECIMAL(20, 8), nullable=False, comment="开盘价")
    high_price = Column(DECIMAL(20, 8), nullable=False, comment="最高价")
    low_price = Column(DECIMAL(20, 8), nullable=False, comment="最低价")
    close_price = Column(DECIMAL(20, 8), nullable=False, comment="收盘价")
    volume = Column(DECIMAL(30, 8), nullable=False, comment="成交量")
    quote_volume = Column(DECIMAL(30, 8), nullable=True, comment="成交额")
    
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index('idx_kline_unique', 'exchange', 'symbol', 'interval', 'timestamp', unique=True),
        Index('idx_kline_query', 'exchange', 'symbol', 'interval'),
    )

    def __repr__(self):
        return f"<HistoricalKlineModel(symbol={self.symbol}, timestamp={self.timestamp})>"
