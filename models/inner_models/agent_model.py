#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 17:00
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
智能体数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON, Enum as SQLEnum, Index

from core.models.agent_models import AgentStatus
from models.inner_models.base import Base


class AgentModel(Base):
    """智能体表模型"""
    __tablename__ = "agent_manage"

    agent_id = Column(String(36), primary_key=True, comment="智能体ID")
    agent_name = Column(String(100), nullable=False, comment="智能体名称")
    agent_type = Column(String(50), nullable=False, index=True, comment="智能体类型")
    status = Column(SQLEnum(AgentStatus), default=AgentStatus.IDLE, index=True, comment="状态")
    capabilities = Column(JSON, default=list, comment="能力列表")
    current_task_id = Column(String(36), nullable=True, comment="当前任务ID")
    max_concurrent_tasks = Column(Integer, default=1, comment="最大并发任务数")
    current_tasks = Column(Integer, default=0, comment="当前任务数")
    meta_data = Column(JSON, default=dict, comment="元数据")
    performance_metrics = Column(JSON, default=dict, comment="性能指标")
    registered_at = Column(DateTime, default=datetime.now, comment="注册时间")
    last_heartbeat = Column(DateTime, default=datetime.now, index=True, comment="最后心跳时间")

    # 创建索引
    __table_args__ = (
        Index('idx_type_status', 'agent_type', 'status'),
    )

    def __repr__(self):
        return f"<AgentModel(agent_id={self.agent_id}, name={self.agent_name}, status={self.status})>"


class AgentMetricsModel(Base):
    """智能体指标表模型"""
    __tablename__ = "agent_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    agent_id = Column(String(36), nullable=False, index=True, comment="智能体ID")
    cpu_usage = Column(String(10), default="0.0", comment="CPU使用率")
    memory_usage = Column(String(10), default="0.0", comment="内存使用率")
    queue_length = Column(Integer, default=0, comment="队列长度")
    response_time = Column(String(10), default="0.0", comment="响应时间（秒）")
    success_rate = Column(String(10), default="1.0", comment="成功率")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    def __repr__(self):
        return f"<AgentMetricsModel(agent_id={self.agent_id}, cpu={self.cpu_usage}, memory={self.memory_usage})>"

