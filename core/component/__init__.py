#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/12/24 11:32
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Agent 系统组件模块
提供 Agent 注册、执行、消息通信、意图识别等功能
"""
# 直接从各个模块导入，避免循环导入
from core.models.agent_models import (
    Task, Session, AgentInfo, ResourceMetrics,
    TaskStatus, AgentStatus, TaskPriority
)
from core.models.agent_message import (
    AgentMessage, MessageBus, MessageType, MessageStatus
)
from core.models.chain_of_thought import (
    ChainOfThought, ThoughtStep, ThoughtStatus, ThoughtType
)
from core.component.intent.intent_models import (
    Intent, IntentType, IntentConfidence, IntentRoute, ReasoningMode
)

# 导入组件
from core.component.registry import AgentRegistry
from core.component.executor import AgentExecutor, TaskPlanner, ThoughtExecutor, ReActExecutor
from core.component.intent import IntentRecognizer, IntentRouter
from core.component.storage import SessionStore, TaskQueue

__all__ = [
    # 注册和执行
    "AgentRegistry",
    "AgentExecutor",
    # 消息通信
    "AgentMessage",
    "MessageBus",
    "MessageType",
    "MessageStatus",
    # 数据模型
    "Task",
    "Session",
    "AgentInfo",
    "ResourceMetrics",
    "TaskStatus",
    "AgentStatus",
    "TaskPriority",
    # 思维链
    "ChainOfThought",
    "ThoughtStep",
    "ThoughtStatus",
    "ThoughtType",
    "TaskPlanner",
    "ThoughtExecutor",
    "ReActExecutor",
    # 意图识别
    "Intent",
    "IntentType",
    "IntentConfidence",
    "IntentRoute",
    "ReasoningMode",
    "IntentRecognizer",
    "IntentRouter",
    # 存储和队列
    "SessionStore",
    "TaskQueue",
]
