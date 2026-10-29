"""Durable conversation execution; independent of backtest/order lifecycles."""

from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from models.inner_models.base import Base


class ConversationRunModel(Base):
    __tablename__ = "agent_conversation_runs"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    session_id = Column(String(36), nullable=False)
    trace_id = Column(String(32), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    control = Column(String(10), nullable=True)
    idempotency_key = Column(String(64), unique=True, nullable=True)
    input_digest = Column(String(64), nullable=False)
    active_session = Column(String(64), unique=True, nullable=True)
    payload = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    error_code = Column(String(64), nullable=True)
    error = Column(Text, nullable=True)
    attempt = Column(Integer, nullable=False, default=0)
    lease_token = Column(String(36), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (Index("ix_conversation_owner_created", "user_id", "created_at"),
                      Index("ix_conversation_claim", "status", "lease_expires_at"))


class ConversationStepModel(Base):
    __tablename__ = "agent_conversation_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False)
    step_key = Column(String(100), nullable=False)
    kind = Column(String(20), nullable=False)
    input_digest = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False)
    output = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "step_key", name="uk_conversation_step"),)


class ConversationEventModel(Base):
    __tablename__ = "agent_conversation_events"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False)
    event_type = Column(String(40), nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (Index("ix_conversation_event_cursor", "run_id", "id"),)
