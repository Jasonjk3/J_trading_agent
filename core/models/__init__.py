#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/12/24 11:32
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Agent 系统数据模型模块
提供 Agent、任务、思维链、消息等数据模型

注意：意图相关模型（Intent, IntentType等）请从 core.component.intent.intent_models 直接导入，
避免循环导入问题。
"""
from core.models.agent_models import (
    Task, Session, AgentInfo, ResourceMetrics,
    TaskStatus, AgentStatus, TaskPriority
)
# 不导入 intent_models，避免循环导入
# 意图相关模型请从 core.component.intent.intent_models 直接导入
from core.models.chain_of_thought import (
    ChainOfThought, ThoughtStep, ThoughtStatus, ThoughtType
)
from core.models.agent_message import (
    AgentMessage, MessageBus, MessageType, MessageStatus
)

__all__ = [
    # Agent相关模型
    "Task",
    "Session",
    "AgentInfo",
    "ResourceMetrics",
    "TaskStatus",
    "AgentStatus",
    "TaskPriority",
    # 思维链模型
    "ChainOfThought",
    "ThoughtStep",
    "ThoughtStatus",
    "ThoughtType",
    # 消息模型
    "AgentMessage",
    "MessageBus",
    "MessageType",
    "MessageStatus",
]
