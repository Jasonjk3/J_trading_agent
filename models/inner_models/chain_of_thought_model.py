#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
思维链数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON, Float, Index, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import JSON

from models.inner_models.base import Base


class ChainOfThoughtModel(Base):
    """思维链表模型"""
    __tablename__ = "chain_of_thoughts"

    thought_id = Column(String(36), primary_key=True, comment="思维链ID")
    task_id = Column(String(36), nullable=True, index=True, comment="关联的任务ID")
    session_id = Column(String(36), nullable=False, index=True, comment="会话ID")
    original_task = Column(Text, nullable=False, comment="原始任务描述")
    goal = Column(Text, nullable=True, comment="任务目标")
    status = Column(String(20), default="planning", index=True, comment="状态：planning/executing/completed/failed")
    current_step = Column(Integer, default=0, comment="当前执行的步骤序号")
    progress = Column(Float, default=0.0, comment="执行进度（0.0-1.0）")
    context = Column(JSON, default=dict, comment="上下文信息")
    intermediate_results = Column(JSON, default=dict, comment="中间结果")
    final_result = Column(Text, nullable=True, comment="最终结果")
    error = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    
    # Multi-Agent支持字段
    is_global_chain = Column(Integer, default=0, comment="是否为全局思维链（Multi-Agent支持）")
    parent_thought_id = Column(String(36), nullable=True, index=True, comment="父思维链ID（如果是子任务）")
    coordinator_agent_id = Column(String(36), nullable=True, index=True, comment="协调Agent ID（Multi-Agent支持）")
    child_thought_ids = Column(JSON, nullable=True, comment="子思维链ID列表（Multi-Agent支持）")
    subtasks = Column(JSON, nullable=True, comment="子任务列表（Multi-Agent支持）")
    agent_results = Column(JSON, nullable=True, comment="Agent执行结果字典（Multi-Agent支持）")

    # 关联关系
    steps = relationship("ThoughtStepModel", back_populates="chain", cascade="all, delete-orphan", order_by="ThoughtStepModel.step_number")
    logs = relationship("ThoughtLogModel", back_populates="chain", cascade="all, delete-orphan", order_by="ThoughtLogModel.created_at")

    # 创建索引
    __table_args__ = (
        Index('idx_session_status', 'session_id', 'status'),
        Index('idx_task_id', 'task_id'),
        Index('idx_created_at', 'created_at'),
        Index('idx_parent_thought_id', 'parent_thought_id'),
        Index('idx_coordinator_agent_id', 'coordinator_agent_id'),
    )

    def __repr__(self):
        return f"<ChainOfThoughtModel(thought_id={self.thought_id}, status={self.status}, progress={self.progress:.0%})>"


class ThoughtStepModel(Base):
    """思维步骤表模型"""
    __tablename__ = "thought_steps"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    step_id = Column(String(36), nullable=False, unique=True, index=True, comment="步骤ID")
    thought_id = Column(String(36), ForeignKey("chain_of_thoughts.thought_id", ondelete="CASCADE"), nullable=False, index=True, comment="思维链ID")
    step_number = Column(Integer, nullable=False, comment="步骤序号")
    thought_type = Column(String(50), nullable=False, comment="步骤类型：analysis/tool_call/reasoning/decision/synthesis/validation/intent_recognition/agent_routing/task_decomposition/agent_execution/result_integration")
    description = Column(Text, nullable=False, comment="步骤描述")
    reasoning = Column(Text, nullable=True, comment="推理过程")
    status = Column(String(20), default="pending", index=True, comment="状态：pending/thinking/executing/completed/failed/skipped")
    tool_name = Column(String(100), nullable=True, comment="工具名称")
    tool_parameters = Column(JSON, nullable=True, comment="工具参数")
    result = Column(JSON, nullable=True, comment="执行结果")
    error = Column(Text, nullable=True, comment="错误信息")
    dependencies = Column(JSON, default=list, comment="依赖的步骤序号列表")
    meta_data = Column(JSON, default=dict, comment="元数据")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    
    # Multi-Agent支持字段
    assigned_agent_id = Column(String(36), nullable=True, index=True, comment="分配的Agent ID（Multi-Agent支持）")
    assigned_agent_type = Column(String(50), nullable=True, index=True, comment="分配的Agent类型（Multi-Agent支持）")
    subtask_id = Column(String(50), nullable=True, index=True, comment="关联的子任务ID（Multi-Agent支持）")
    parent_thought_id = Column(String(36), nullable=True, index=True, comment="父思维链ID（Multi-Agent支持）")

    # 关联关系
    chain = relationship("ChainOfThoughtModel", back_populates="steps")

    # 创建索引
    __table_args__ = (
        Index('idx_thought_step_number', 'thought_id', 'step_number'),
        Index('idx_thought_status', 'thought_id', 'status'),
        Index('idx_assigned_agent_id', 'assigned_agent_id'),
        Index('idx_assigned_agent_type', 'assigned_agent_type'),
        Index('idx_subtask_id', 'subtask_id'),
        Index('idx_step_parent_thought_id', 'parent_thought_id'),
    )

    def __repr__(self):
        return f"<ThoughtStepModel(step_id={self.step_id}, step_number={self.step_number}, status={self.status})>"


class ThoughtLogModel(Base):
    """思维链日志表模型"""
    __tablename__ = "thought_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    thought_id = Column(String(36), ForeignKey("chain_of_thoughts.thought_id", ondelete="CASCADE"), nullable=False, index=True, comment="思维链ID")
    step_id = Column(String(36), nullable=True, index=True, comment="关联的步骤ID（如果适用）")
    log_level = Column(String(20), default="info", index=True, comment="日志级别：debug/info/warning/error")
    log_type = Column(String(50), nullable=False, comment="日志类型：planning/step_start/step_complete/step_error/tool_call/result_synthesis等")
    message = Column(Text, nullable=False, comment="日志消息")
    details = Column(JSON, default=dict, comment="详细信息")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    # 关联关系
    chain = relationship("ChainOfThoughtModel", back_populates="logs")

    # 创建索引
    __table_args__ = (
        Index('idx_thought_created', 'thought_id', 'created_at'),
        Index('idx_log_level', 'log_level'),
    )

    def __repr__(self):
        return f"<ThoughtLogModel(id={self.id}, thought_id={self.thought_id}, log_type={self.log_type}, log_level={self.log_level})>"

