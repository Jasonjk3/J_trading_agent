"""User-owned market monitoring configuration and delivery history."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text

from models.inner_models.base import Base


class MonitorRuleModel(Base):
    __tablename__ = "data_monitor_rules"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=False, default="")
    metric = Column(String(30), nullable=False)
    operator = Column(String(20), nullable=False)
    threshold = Column(Float, nullable=False)
    rule_type = Column(String(20), nullable=False, default="threshold")
    window_minutes = Column(Integer, nullable=True)
    movement_unit = Column(String(10), nullable=True)
    movement_direction = Column(String(10), nullable=True)
    start_time = Column(String(5), nullable=True)
    end_time = Column(String(5), nullable=True)
    report_interval_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class MonitorTemplateModel(Base):
    __tablename__ = "data_monitor_templates"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    message_type = Column(String(10), nullable=False, default="text")
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class MonitorTaskModel(Base):
    __tablename__ = "data_monitor_tasks"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    exchange = Column(String(20), nullable=False, default="OKX")
    symbol = Column(String(40), nullable=False)
    frequency_seconds = Column(Integer, nullable=False, default=60)
    rule_id = Column(String(36), nullable=True)
    metric = Column(String(30), nullable=False)
    operator = Column(String(20), nullable=False)
    threshold = Column(Float, nullable=False)
    rule_type = Column(String(20), nullable=False, default="threshold")
    window_minutes = Column(Integer, nullable=True)
    movement_unit = Column(String(10), nullable=True)
    movement_direction = Column(String(10), nullable=True)
    start_time = Column(String(5), nullable=True)
    end_time = Column(String(5), nullable=True)
    report_interval_minutes = Column(Integer, nullable=True)
    push_config_id = Column(String(36), nullable=False)
    template_id = Column(String(36), nullable=False)
    cooldown_seconds = Column(Integer, nullable=False, default=900)
    recovery_notice = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    condition_active = Column(Boolean, nullable=False, default=False)
    last_value = Column(Float, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    next_check_at = Column(DateTime, nullable=True, index=True)
    last_triggered_at = Column(DateTime, nullable=True)
    last_error = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class MonitorEventModel(Base):
    __tablename__ = "data_monitor_events"
    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    event_type = Column(String(20), nullable=False)
    value = Column(Float, nullable=False)
    success = Column(Boolean, nullable=False)
    error = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)


class MonitorSampleModel(Base):
    __tablename__ = "data_monitor_samples"
    __table_args__ = (Index("ix_data_monitor_samples_task_time", "task_id", "observed_at"),)
    id = Column(String(36), primary_key=True)
    task_id = Column(String(36), nullable=False)
    observed_at = Column(DateTime, nullable=False)
    price = Column(Float, nullable=False)
