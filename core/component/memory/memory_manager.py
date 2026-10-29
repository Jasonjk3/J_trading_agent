#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
记忆管理器
统一管理所有记忆操作
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from loguru import logger

from core.component.memory.memory_types import Memory, MemoryType
from core.component.memory.memory_store import MemoryStore
from core.component.memory.in_memory_backend import InMemoryBackend
from core.component.memory.database_backend import DatabaseBackend
from core.infrastructure.database.async_database import AsyncDatabase


class MemoryManager:
    """记忆管理器"""
    
    def __init__(
        self,
        agent_id: str,
        backend: str = "database",  # "memory" | "database" | "hybrid"
        db: Optional[AsyncDatabase] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化记忆管理器
        
        Args:
            agent_id: Agent ID
            backend: 存储后端类型
            db: 数据库连接（database 或 hybrid 模式需要）
            config: 配置选项
        """
        self.agent_id = agent_id
        self.backend_type = backend
        self.config = config or {}
        
        # 默认配置
        self.conversation_ttl_hours = self.config.get("conversation_ttl_hours", 24)
        self.working_memory_ttl_hours = self.config.get("working_memory_ttl_hours", 1)
        self.long_term_memory_ttl_days = self.config.get("long_term_memory_ttl_days", 365)
        self.default_retrieve_limit = self.config.get("default_retrieve_limit", 10)
        
        # 初始化存储后端
        self.primary_store: Optional[MemoryStore] = None
        self.secondary_store: Optional[MemoryStore] = None
        
        if backend == "memory":
            self.primary_store = InMemoryBackend()
        elif backend == "database":
            if not db:
                raise ValueError("database 模式需要提供 db 参数")
            self.primary_store = DatabaseBackend(db)
        elif backend == "hybrid":
            # 混合模式：短期记忆用内存，长期记忆用数据库
            if not db:
                raise ValueError("hybrid 模式需要提供 db 参数")
            self.primary_store = InMemoryBackend()
            self.secondary_store = DatabaseBackend(db)
        else:
            raise ValueError(f"不支持的存储后端类型: {backend}")
    
    async def initialize(self) -> bool:
        """初始化记忆管理器"""
        try:
            if self.primary_store:
                result = await self.primary_store.initialize()
                if not result:
                    return False
            
            if self.secondary_store:
                result = await self.secondary_store.initialize()
                if not result:
                    return False
            
            logger.info(f"MemoryManager 初始化成功: agent_id={self.agent_id}, backend={self.backend_type}")
            return True
        except Exception as e:
            logger.error(f"MemoryManager 初始化失败: {e}", exc_info=True)
            return False
    
    def _get_store(self, memory_type: MemoryType) -> MemoryStore:
        """根据记忆类型选择合适的存储后端"""
        if self.backend_type == "hybrid":
            # 短期记忆用内存，长期记忆用数据库
            if memory_type in [MemoryType.CONVERSATION, MemoryType.WORKING]:
                return self.primary_store  # InMemoryBackend
            else:
                return self.secondary_store  # DatabaseBackend
        else:
            return self.primary_store
    
    def _calculate_expires_at(self, memory_type: MemoryType) -> Optional[datetime]:
        """计算过期时间"""
        if memory_type == MemoryType.CONVERSATION:
            return datetime.now() + timedelta(hours=self.conversation_ttl_hours)
        elif memory_type == MemoryType.WORKING:
            return datetime.now() + timedelta(hours=self.working_memory_ttl_hours)
        elif memory_type in [MemoryType.USER_PROFILE, MemoryType.PREFERENCE, MemoryType.KNOWLEDGE, MemoryType.FACT]:
            return datetime.now() + timedelta(days=self.long_term_memory_ttl_days)
        else:
            return None  # 不过期
    
    async def store(
        self,
        memory_type: MemoryType,
        content: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        importance_score: float = 0.5,
        expires_at: Optional[datetime] = None,
        **kwargs
    ) -> Memory:
        """
        存储记忆
        
        Args:
            memory_type: 记忆类型
            content: 记忆内容
            session_id: 会话ID
            user_id: 用户ID
            metadata: 元数据
            importance_score: 重要性评分
            expires_at: 过期时间（如果为None，根据类型自动计算）
            **kwargs: 其他参数
        
        Returns:
            Memory 对象
        """
        # 计算过期时间
        if expires_at is None:
            expires_at = self._calculate_expires_at(memory_type)
        
        # 创建 Memory 对象
        memory = Memory(
            agent_id=self.agent_id,
            session_id=session_id,
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
            importance_score=importance_score,
            expires_at=expires_at
        )
        
        # 选择存储后端
        store = self._get_store(memory_type)
        
        # 保存
        success = await store.save(memory)
        if not success:
            logger.warning(f"存储记忆失败: memory_id={memory.memory_id}")
        
        return memory
    
    async def retrieve(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = None,
        use_semantic_search: bool = False
    ) -> List[Memory]:
        """
        检索记忆
        
        Args:
            query: 查询字符串
            memory_types: 记忆类型过滤
            session_id: 会话ID过滤
            user_id: 用户ID过滤
            limit: 返回数量限制
            use_semantic_search: 是否使用语义搜索（暂不支持）
        
        Returns:
            记忆列表
        """
        if limit is None:
            limit = self.default_retrieve_limit
        
        results = []
        
        # 根据后端类型检索
        if self.backend_type == "hybrid":
            # 混合模式：从两个后端检索
            if self.primary_store:
                primary_results = await self.primary_store.search(
                    agent_id=self.agent_id,
                    query=query,
                    memory_types=memory_types,
                    session_id=session_id,
                    user_id=user_id,
                    limit=limit
                )
                results.extend(primary_results)
            
            if self.secondary_store:
                secondary_results = await self.secondary_store.search(
                    agent_id=self.agent_id,
                    query=query,
                    memory_types=memory_types,
                    session_id=session_id,
                    user_id=user_id,
                    limit=limit
                )
                results.extend(secondary_results)
            
            # 去重并按重要性排序
            seen_ids = set()
            unique_results = []
            for memory in results:
                if memory.memory_id not in seen_ids:
                    seen_ids.add(memory.memory_id)
                    unique_results.append(memory)
            
            # 按重要性评分排序
            unique_results.sort(key=lambda m: m.importance_score, reverse=True)
            results = unique_results[:limit]
        else:
            # 单一后端
            results = await self.primary_store.search(
                agent_id=self.agent_id,
                query=query,
                memory_types=memory_types,
                session_id=session_id,
                user_id=user_id,
                limit=limit
            )
        
        return results
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20
    ) -> List[Memory]:
        """获取对话历史"""
        store = self._get_store(MemoryType.CONVERSATION)
        return await store.get_by_session(
            agent_id=self.agent_id,
            session_id=session_id,
            memory_types=[MemoryType.CONVERSATION],
            limit=limit
        )
    
    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """获取单个记忆"""
        # 尝试从所有后端获取
        stores = [self.primary_store]
        if self.secondary_store:
            stores.append(self.secondary_store)
        
        for store in stores:
            if store:
                memory = await store.get(memory_id)
                if memory:
                    return memory
        
        return None
    
    async def update_importance(
        self,
        memory_id: str,
        importance_score: float
    ) -> bool:
        """更新记忆重要性"""
        memory = await self.get_memory(memory_id)
        if not memory:
            return False
        
        memory.importance_score = max(0.0, min(1.0, importance_score))
        memory.updated_at = datetime.now()
        
        store = self._get_store(memory.memory_type)
        return await store.update(memory)
    
    async def delete(
        self,
        memory_id: str,
        soft_delete: bool = True
    ) -> bool:
        """删除记忆"""
        # 尝试从所有后端删除
        stores = [self.primary_store]
        if self.secondary_store:
            stores.append(self.secondary_store)
        
        for store in stores:
            if store:
                if await store.delete(memory_id, soft_delete=soft_delete):
                    return True
        
        return False
    
    async def get_related_memories(
        self,
        memory_id: str,
        limit: int = 5
    ) -> List[Memory]:
        """获取关联记忆"""
        memory = await self.get_memory(memory_id)
        if not memory or not memory.related_memories:
            return []
        
        related = []
        for related_id in memory.related_memories[:limit]:
            related_memory = await self.get_memory(related_id)
            if related_memory:
                related.append(related_memory)
        
        return related
    
    async def cleanup_expired(self) -> int:
        """清理过期记忆"""
        count = 0
        if self.primary_store:
            count += await self.primary_store.cleanup_expired()
        if self.secondary_store:
            count += await self.secondary_store.cleanup_expired()
        return count

