"""交易员工作状态、回合和审计事件数据库模型。"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String

from models.inner_models.base import Base


class TraderStateModel(Base):
    __tablename__ = "trader_states"

    session_id = Column(String(100), primary_key=True, comment="隔离后的交易员会话ID")
    agent_id = Column(String(36), nullable=False, index=True, comment="交易Agent ID")
    revision = Column(Integer, nullable=False, default=0, comment="乐观版本号")
    state_json = Column(JSON, nullable=False, comment="当前工作记忆")
    next_review_at = Column(DateTime, nullable=True, index=True, comment="下一次定时复核")
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class TraderTurnModel(Base):
    __tablename__ = "trader_turns"

    decision_id = Column(String(36), primary_key=True, comment="交易员决策ID")
    session_id = Column(String(100), nullable=False, index=True)
    as_of = Column(DateTime, nullable=False, index=True)
    status = Column(String(30), nullable=False)
    turn_json = Column(JSON, nullable=False, comment="完整 TraderTurn")
    next_review_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_trader_turn_session_asof", "session_id", "as_of"),
    )


class TraderEventModel(Base):
    __tablename__ = "trader_events"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(100), nullable=False, index=True)
    decision_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    occurred_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_trader_event_session_time", "session_id", "occurred_at"),
    )


class TraderOrderProposalModel(Base):
    __tablename__ = "trader_order_proposals"

    proposal_id = Column(String(36), primary_key=True)
    decision_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    status = Column(String(30), nullable=False)
    commit_status = Column(String(30), nullable=False)
    proposal_json = Column(JSON, nullable=False)
    as_of = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class TraderExecutionEventModel(Base):
    __tablename__ = "trader_execution_events"

    id = Column(String(36), primary_key=True)
    proposal_id = Column(String(36), nullable=True, index=True)
    client_intent_id = Column(String(36), nullable=True, index=True)
    exchange_order_id = Column(String(100), nullable=True, index=True)
    event_type = Column(String(40), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    occurred_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
