#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Agent间消息传递机制
支持Multi-Agent协作通信
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, List
from uuid import uuid4
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """消息类型"""
    TASK_REQUEST = "task_request"  # 任务请求
    TASK_RESPONSE = "task_response"  # 任务响应
    INTERMEDIATE_RESULT = "intermediate_result"  # 中间结果
    STATUS_UPDATE = "status_update"  # 状态更新
    COORDINATION = "coordination"  # 协调消息
    REFLECTION = "reflection"  # 反思消息


class MessageStatus(str, Enum):
    """消息状态"""
    PENDING = "pending"  # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class AgentMessage(BaseModel):
    """Agent间消息"""
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    message_type: MessageType  # 消息类型
    from_agent_id: str  # 发送方Agent ID
    to_agent_id: str  # 接收方Agent ID
    task_id: Optional[str] = None  # 关联的任务ID
    step_id: Optional[str] = None  # 关联的步骤ID
    content: Dict[str, Any]  # 消息内容
    status: MessageStatus = MessageStatus.PENDING  # 消息状态
    created_at: datetime = Field(default_factory=datetime.now)
    processed_at: Optional[datetime] = None
    response: Optional[Dict[str, Any]] = None  # 响应内容
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MessageBus:
    """消息总线 - Agent间通信中心"""
    
    def __init__(self):
        """初始化消息总线"""
        self._messages: Dict[str, AgentMessage] = {}  # 消息存储
        self._message_queues: Dict[str, List[str]] = {}  # Agent消息队列 {agent_id: [message_ids]}
        self._subscribers: Dict[str, List[str]] = {}  # 订阅者 {message_type: [agent_ids]}
    
    async def send_message(self, message: AgentMessage) -> bool:
        """
        发送消息
        
        Args:
            message: 消息对象
            
        Returns:
            是否发送成功
        """
        self._messages[message.message_id] = message
        
        # 添加到接收方的消息队列
        if message.to_agent_id not in self._message_queues:
            self._message_queues[message.to_agent_id] = []
        self._message_queues[message.to_agent_id].append(message.message_id)
        
        return True
    
    async def receive_messages(
        self,
        agent_id: str,
        message_type: Optional[MessageType] = None,
        limit: int = 10
    ) -> List[AgentMessage]:
        """
        接收消息
        
        Args:
            agent_id: Agent ID
            message_type: 消息类型过滤（可选）
            limit: 最大返回数量
            
        Returns:
            消息列表
        """
        message_ids = self._message_queues.get(agent_id, [])
        messages = []
        
        for msg_id in message_ids[:limit]:
            msg = self._messages.get(msg_id)
            if msg and msg.status == MessageStatus.PENDING:
                if message_type is None or msg.message_type == message_type:
                    messages.append(msg)
        
        return messages
    
    async def mark_message_processed(
        self,
        message_id: str,
        response: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        标记消息为已处理
        
        Args:
            message_id: 消息ID
            response: 响应内容（可选）
            
        Returns:
            是否标记成功
        """
        message = self._messages.get(message_id)
        if not message:
            return False
        
        message.status = MessageStatus.COMPLETED
        message.processed_at = datetime.now()
        if response:
            message.response = response
        
        return True
    
    async def subscribe(self, agent_id: str, message_type: MessageType) -> bool:
        """
        订阅消息类型
        
        Args:
            agent_id: Agent ID
            message_type: 消息类型
            
        Returns:
            是否订阅成功
        """
        if message_type.value not in self._subscribers:
            self._subscribers[message_type.value] = []
        
        if agent_id not in self._subscribers[message_type.value]:
            self._subscribers[message_type.value].append(agent_id)
        
        return True
    
    async def get_message(self, message_id: str) -> Optional[AgentMessage]:
        """
        获取消息
        
        Args:
            message_id: 消息ID
            
        Returns:
            消息对象
        """
        return self._messages.get(message_id)
    
    async def clear_processed_messages(self, agent_id: str) -> int:
        """
        清理已处理的消息
        
        Args:
            agent_id: Agent ID
            
        Returns:
            清理的消息数量
        """
        message_ids = self._message_queues.get(agent_id, [])
        cleared = 0
        
        for msg_id in message_ids[:]:
            msg = self._messages.get(msg_id)
            if msg and msg.status == MessageStatus.COMPLETED:
                message_ids.remove(msg_id)
                del self._messages[msg_id]
                cleared += 1
        
        return cleared
