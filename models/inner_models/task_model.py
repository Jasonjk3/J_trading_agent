#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 17:00
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
任务数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON

from models.inner_models.base import Base
from core.models.agent_models import TaskStatus, TaskPriority


class TaskModel(Base):
    """任务表模型"""
    __tablename__ = "agent_tasks"

    task_id = Column(String(36), primary_key=True, comment="任务ID")
    session_id = Column(String(36), nullable=False, index=True, comment="会话ID")
    agent_id = Column(String(36), nullable=True, index=True, comment="分配的智能体ID")
    content = Column(Text, nullable=False, comment="任务内容")
    # TaskPriority 是 int 枚举，使用 Integer 类型存储整数值
    priority = Column(Integer, default=TaskPriority.NORMAL.value, comment="优先级")
    # TaskStatus 是 str 枚举，使用 String 类型存储字符串值
    status = Column(String(20), default=TaskStatus.PENDING.value, index=True, comment="状态")
    meta_data = Column(JSON, default=dict, comment="元数据")
    result = Column(JSON, nullable=True, comment="任务结果")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")

    def __repr__(self):
        return f"<TaskModel(task_id={self.task_id}, status={self.status}, agent_id={self.agent_id})>"

