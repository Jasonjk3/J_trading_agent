#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
记忆存储接口
定义统一的存储接口，支持多种存储后端
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from core.component.memory.memory_types import Memory, MemoryType


class MemoryStore(ABC):
    """记忆存储接口"""
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化存储后端"""
        pass
    
    @abstractmethod
    async def save(self, memory: Memory) -> bool:
        """保存记忆"""
        pass
    
    @abstractmethod
    async def get(self, memory_id: str) -> Optional[Memory]:
        """获取记忆"""
        pass
    
    @abstractmethod
    async def search(
        self,
        agent_id: str,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Memory]:
        """搜索记忆（关键词）"""
        pass
    
    @abstractmethod
    async def get_by_session(
        self,
        agent_id: str,
        session_id: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 100
    ) -> List[Memory]:
        """按会话获取记忆"""
        pass
    
    @abstractmethod
    async def get_by_agent(
        self,
        agent_id: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 100
    ) -> List[Memory]:
        """按 Agent 获取记忆"""
        pass
    
    @abstractmethod
    async def delete(self, memory_id: str, soft_delete: bool = True) -> bool:
        """删除记忆"""
        pass
    
    @abstractmethod
    async def update(self, memory: Memory) -> bool:
        """更新记忆"""
        pass
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """清理过期记忆"""
        pass

