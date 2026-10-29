#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Agent调度中心数据模型
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"  # 等待中
    QUEUED = "queued"  # 已入队
    ASSIGNED = "assigned"  # 已分配
    RUNNING = "running"  # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class AgentStatus(str, Enum):
    """智能体状态枚举"""
    IDLE = "idle"  # 空闲
    BUSY = "busy"  # 忙碌
    OFFLINE = "offline"  # 离线
    ERROR = "error"  # 错误
    # 服务型 Agent 状态
    RUNNING = "running"  # 运行中（持续运行的服务）
    PAUSED = "paused"  # 已暂停（暂停执行但保持连接）
    STOPPED = "stopped"  # 已停止（完全停止）


class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class Task(BaseModel):
    """任务模型"""
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str  # 会话ID
    agent_id: Optional[str] = None  # 分配的智能体ID
    content: str  # 任务内容
    priority: TaskPriority = TaskPriority.NORMAL  # 优先级
    status: TaskStatus = TaskStatus.PENDING  # 状态
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[Any] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Session(BaseModel):
    """会话模型"""
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: Optional[str] = None  # 用户ID
    title: Optional[str] = None  # 会话名称
    context: Dict[str, Any] = Field(default_factory=dict)  # 上下文信息
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # 过期时间
    is_active: bool = True  # 是否活跃

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentInfo(BaseModel):
    """智能体信息模型"""
    agent_id: str
    agent_name: str
    agent_type: str  # 智能体类型
    status: AgentStatus = AgentStatus.IDLE
    capabilities: List[str] = Field(default_factory=list)  # 能力列表
    current_task_id: Optional[str] = None  # 当前任务ID
    max_concurrent_tasks: int = 1  # 最大并发任务数
    current_tasks: int = 0  # 当前任务数
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据
    registered_at: datetime = Field(default_factory=datetime.now)
    last_heartbeat: datetime = Field(default_factory=datetime.now)
    performance_metrics: Dict[str, float] = Field(default_factory=dict)  # 性能指标

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ResourceMetrics(BaseModel):
    """资源指标模型"""
    agent_id: str
    cpu_usage: float = 0.0  # CPU使用率
    memory_usage: float = 0.0  # 内存使用率
    queue_length: int = 0  # 队列长度
    response_time: float = 0.0  # 响应时间（秒）
    success_rate: float = 1.0  # 成功率
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

