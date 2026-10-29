#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
内存存储后端
快速访问，易失性存储，适合短期记忆
"""
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from core.component.memory.memory_store import MemoryStore
from core.component.memory.memory_types import Memory, MemoryType


class InMemoryBackend(MemoryStore):
    """内存存储后端"""
    
    def __init__(self):
        """初始化内存存储"""
        self._memories: Dict[str, Memory] = {}  # memory_id -> Memory
        self._agent_index: Dict[str, List[str]] = {}  # agent_id -> [memory_id]
        self._session_index: Dict[str, List[str]] = {}  # session_id -> [memory_id]
        self._user_index: Dict[str, List[str]] = {}  # user_id -> [memory_id]
        self._type_index: Dict[MemoryType, List[str]] = {}  # memory_type -> [memory_id]
    
    async def initialize(self) -> bool:
        """初始化存储后端"""
        logger.info("InMemoryBackend 初始化完成")
        return True
    
    async def save(self, memory: Memory) -> bool:
        """保存记忆"""
        try:
            # 保存到主存储
            self._memories[memory.memory_id] = memory
            
            # 更新索引
            if memory.agent_id not in self._agent_index:
                self._agent_index[memory.agent_id] = []
            if memory.memory_id not in self._agent_index[memory.agent_id]:
                self._agent_index[memory.agent_id].append(memory.memory_id)
            
            if memory.session_id:
                if memory.session_id not in self._session_index:
                    self._session_index[memory.session_id] = []
                if memory.memory_id not in self._session_index[memory.session_id]:
                    self._session_index[memory.session_id].append(memory.memory_id)
            
            if memory.user_id:
                if memory.user_id not in self._user_index:
                    self._user_index[memory.user_id] = []
                if memory.memory_id not in self._user_index[memory.user_id]:
                    self._user_index[memory.user_id].append(memory.memory_id)
            
            if memory.memory_type not in self._type_index:
                self._type_index[memory.memory_type] = []
            if memory.memory_id not in self._type_index[memory.memory_type]:
                self._type_index[memory.memory_type].append(memory.memory_id)
            
            return True
        except Exception as e:
            logger.error(f"保存记忆失败: {e}", exc_info=True)
            return False
    
    async def get(self, memory_id: str) -> Optional[Memory]:
        """获取记忆"""
        memory = self._memories.get(memory_id)
        if memory:
            # 检查是否过期
            if memory.is_expired():
                await self.delete(memory_id, soft_delete=False)
                return None
            # 更新访问信息
            memory.update_access()
        return memory
    
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
        # 获取候选记忆ID
        candidate_ids = set()
        
        # 按 agent_id 过滤
        if agent_id in self._agent_index:
            candidate_ids.update(self._agent_index[agent_id])
        
        # 按 session_id 过滤
        if session_id:
            if session_id in self._session_index:
                candidate_ids.intersection_update(self._session_index[session_id])
            else:
                return []
        
        # 按 user_id 过滤
        if user_id:
            if user_id in self._user_index:
                candidate_ids.intersection_update(self._user_index[user_id])
            else:
                return []
        
        # 按 memory_type 过滤
        if memory_types:
            type_ids = set()
            for mem_type in memory_types:
                if mem_type in self._type_index:
                    type_ids.update(self._type_index[mem_type])
            candidate_ids.intersection_update(type_ids)
        
        # 关键词搜索
        query_lower = query.lower()
        results = []
        for mem_id in candidate_ids:
            memory = self._memories.get(mem_id)
            if not memory:
                continue
            
            # 检查是否过期
            if memory.is_expired():
                continue
            
            # 关键词匹配
            if query_lower in memory.content.lower():
                results.append(memory)
        
        # 按重要性评分和访问时间排序
        results.sort(key=lambda m: (m.importance_score, m.accessed_at), reverse=True)
        
        return results[:limit]
    
    async def get_by_session(
        self,
        agent_id: str,
        session_id: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 100
    ) -> List[Memory]:
        """按会话获取记忆"""
        if session_id not in self._session_index:
            return []
        
        memory_ids = self._session_index[session_id]
        results = []
        
        for mem_id in memory_ids:
            memory = self._memories.get(mem_id)
            if not memory:
                continue
            
            # 检查 agent_id
            if memory.agent_id != agent_id:
                continue
            
            # 检查是否过期
            if memory.is_expired():
                continue
            
            # 检查 memory_type
            if memory_types and memory.memory_type not in memory_types:
                continue
            
            results.append(memory)
        
        # 按时间排序
        results.sort(key=lambda m: m.created_at, reverse=False)
        
        return results[:limit]
    
    async def get_by_agent(
        self,
        agent_id: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 100
    ) -> List[Memory]:
        """按 Agent 获取记忆"""
        if agent_id not in self._agent_index:
            return []
        
        memory_ids = self._agent_index[agent_id]
        results = []
        
        for mem_id in memory_ids:
            memory = self._memories.get(mem_id)
            if not memory:
                continue
            
            # 检查是否过期
            if memory.is_expired():
                continue
            
            # 检查 memory_type
            if memory_types and memory.memory_type not in memory_types:
                continue
            
            results.append(memory)
        
        # 按时间排序
        results.sort(key=lambda m: m.created_at, reverse=False)
        
        return results[:limit]
    
    async def delete(self, memory_id: str, soft_delete: bool = True) -> bool:
        """删除记忆"""
        if memory_id not in self._memories:
            return False
        
        memory = self._memories[memory_id]
        
        # 从索引中删除
        if memory.agent_id in self._agent_index:
            if memory_id in self._agent_index[memory.agent_id]:
                self._agent_index[memory.agent_id].remove(memory_id)
        
        if memory.session_id and memory.session_id in self._session_index:
            if memory_id in self._session_index[memory.session_id]:
                self._session_index[memory.session_id].remove(memory_id)
        
        if memory.user_id and memory.user_id in self._user_index:
            if memory_id in self._user_index[memory.user_id]:
                self._user_index[memory.user_id].remove(memory_id)
        
        if memory.memory_type in self._type_index:
            if memory_id in self._type_index[memory.memory_type]:
                self._type_index[memory.memory_type].remove(memory_id)
        
        # 从主存储中删除
        if not soft_delete:
            del self._memories[memory_id]
        
        return True
    
    async def update(self, memory: Memory) -> bool:
        """更新记忆"""
        if memory.memory_id not in self._memories:
            return False
        
        memory.updated_at = datetime.now()
        self._memories[memory.memory_id] = memory
        return True
    
    async def cleanup_expired(self) -> int:
        """清理过期记忆"""
        expired_ids = []
        for mem_id, memory in self._memories.items():
            if memory.is_expired():
                expired_ids.append(mem_id)
        
        count = 0
        for mem_id in expired_ids:
            if await self.delete(mem_id, soft_delete=False):
                count += 1
        
        if count > 0:
            logger.info(f"InMemoryBackend 清理了 {count} 条过期记忆")
        
        return count

