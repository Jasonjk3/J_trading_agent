#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
记忆类型定义和 Memory 数据模型
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """记忆类型枚举"""
    # 短期记忆（易失性，会话级别）
    CONVERSATION = "conversation"        # 对话历史
    WORKING = "working"                  # 工作记忆（当前任务上下文）
    
    # 长期记忆（持久化，用户/Agent级别）
    USER_PROFILE = "user_profile"       # 用户画像
    PREFERENCE = "preference"            # 用户偏好
    KNOWLEDGE = "knowledge"              # 知识片段
    FACT = "fact"                        # 事实信息
    TASK_CONTEXT = "task_context"        # 任务上下文
    SUMMARY = "summary"                  # 总结摘要


class Memory(BaseModel):
    """记忆单元"""
    memory_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str                       # Agent ID
    session_id: Optional[str] = None    # 会话ID（可选）
    user_id: Optional[str] = None       # 用户ID（可选）
    
    memory_type: MemoryType             # 记忆类型
    content: str                       # 记忆内容
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据（标签、重要性等）
    
    # 关联信息
    related_memories: List[str] = Field(default_factory=list)  # 关联的记忆ID
    embedding: Optional[List[float]] = None  # 向量嵌入（用于语义搜索）
    
    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    accessed_at: datetime = Field(default_factory=datetime.now)  # 最后访问时间
    expires_at: Optional[datetime] = None  # 过期时间
    
    # 重要性评分
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)  # 重要性评分 (0-1)
    access_count: int = Field(default=0)  # 访问次数
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def update_access(self):
        """更新访问时间和次数"""
        self.accessed_at = datetime.now()
        self.access_count += 1
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "memory_id": self.memory_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "related_memories": self.related_memories,
            "embedding": self.embedding,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            "accessed_at": self.accessed_at.isoformat() if isinstance(self.accessed_at, datetime) else self.accessed_at,
            "expires_at": self.expires_at.isoformat() if isinstance(self.expires_at, datetime) and self.expires_at else None,
            "importance_score": self.importance_score,
            "access_count": self.access_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Memory":
        """从字典创建 Memory 对象"""
        # 处理时间字符串
        for time_field in ["created_at", "updated_at", "accessed_at", "expires_at"]:
            if time_field in data and isinstance(data[time_field], str):
                data[time_field] = datetime.fromisoformat(data[time_field])
        
        # 处理 memory_type
        if isinstance(data.get("memory_type"), str):
            data["memory_type"] = MemoryType(data["memory_type"])
        
        return cls(**data)

