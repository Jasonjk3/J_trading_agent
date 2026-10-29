#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Memory 功能 Mixin
为 Agent 提供记忆管理能力
"""
from typing import Any, Dict, List, Optional
from loguru import logger

from core.component.memory.memory_manager import MemoryManager
from core.component.memory.memory_types import Memory, MemoryType
from core.infrastructure.database.async_database import AsyncDatabase


class MemoryMixin:
    """Memory 功能 Mixin"""
    
    def __init__(self, *args, **kwargs):
        """初始化 Memory Mixin"""
        super().__init__(*args, **kwargs)
        
        # Memory 配置
        self.enable_memory: bool = kwargs.get('enable_memory', True)
        self.memory_config: Dict = kwargs.get('memory_config', {})
        self.memory_backend: str = kwargs.get('memory_backend', 'database')  # memory | database | hybrid
        self.memory_db: Optional[AsyncDatabase] = kwargs.get('memory_db', None)
        
        # Memory 管理器（延迟初始化）
        self.memory_manager: Optional[MemoryManager] = None
    
    async def initialize(self) -> bool:
        """初始化 Memory"""
        # 先调用父类的 initialize
        result = await super().initialize()
        if not result:
            return False
        
        # 初始化 Memory
        if self.enable_memory:
            try:
                # 如果没有提供 db，尝试从 kwargs 或全局获取
                db = self.memory_db
                if not db and hasattr(self, 'db'):
                    db = getattr(self, 'db')
                
                self.memory_manager = MemoryManager(
                    agent_id=self.agent_id,
                    backend=self.memory_backend,
                    db=db,
                    config=self.memory_config
                )
                
                memory_init_result = await self.memory_manager.initialize()
                if not memory_init_result:
                    logger.warning(f"{self.__class__.__name__} Memory 初始化失败，但继续运行")
                    self.memory_manager = None
                else:
                    logger.info(f"{self.__class__.__name__} Memory 初始化成功")
            except Exception as e:
                logger.error(f"{self.__class__.__name__} Memory 初始化异常: {e}", exc_info=True)
                self.memory_manager = None
        
        return True
    
    async def cleanup(self) -> bool:
        """清理 Memory 资源"""
        if self.memory_manager:
            try:
                # 可以在这里执行清理操作，如保存未持久化的记忆
                pass
            except Exception as e:
                logger.error(f"清理 Memory 资源失败: {e}")
        
        return await super().cleanup()
    
    async def store_memory(
        self,
        memory_type: MemoryType,
        content: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        importance_score: float = 0.5,
        metadata: Optional[Dict] = None,
        **kwargs
    ) -> Optional[Memory]:
        """
        存储记忆
        
        Args:
            memory_type: 记忆类型
            content: 记忆内容
            session_id: 会话ID
            user_id: 用户ID
            importance_score: 重要性评分
            metadata: 元数据
            **kwargs: 其他参数
        
        Returns:
            Memory 对象，如果未启用 Memory 则返回 None
        """
        if not self.memory_manager:
            return None
        
        try:
            return await self.memory_manager.store(
                memory_type=memory_type,
                content=content,
                session_id=session_id,
                user_id=user_id,
                importance_score=importance_score,
                metadata=metadata,
                **kwargs
            )
        except Exception as e:
            logger.error(f"存储记忆失败: {e}", exc_info=True)
            return None
    
    async def retrieve_memories(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Memory]:
        """
        检索记忆
        
        Args:
            query: 查询字符串
            memory_types: 记忆类型过滤
            session_id: 会话ID过滤
            user_id: 用户ID过滤
            limit: 返回数量限制
        
        Returns:
            记忆列表
        """
        if not self.memory_manager:
            return []
        
        try:
            return await self.memory_manager.retrieve(
                query=query,
                memory_types=memory_types,
                session_id=session_id,
                user_id=user_id,
                limit=limit
            )
        except Exception as e:
            logger.error(f"检索记忆失败: {e}", exc_info=True)
            return []
    
    async def get_relevant_context(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5
    ) -> str:
        """
        获取相关上下文（用于构建 Prompt）
        
        Args:
            query: 查询字符串
            session_id: 会话ID
            limit: 返回数量限制
        
        Returns:
            上下文文本
        """
        memories = await self.retrieve_memories(
            query=query,
            session_id=session_id,
            limit=limit
        )
        
        if not memories:
            return ""
        
        context_parts = []
        for memory in memories:
            context_parts.append(f"[{memory.memory_type.value}] {memory.content}")
        
        return "\n".join(context_parts)
    
    async def get_conversation_memories(
        self,
        session_id: str,
        limit: int = 20
    ) -> List[Memory]:
        """获取对话记忆"""
        if not self.memory_manager:
            return []
        
        try:
            return await self.memory_manager.get_conversation_history(
                session_id=session_id,
                limit=limit
            )
        except Exception as e:
            logger.error(f"获取对话记忆失败: {e}", exc_info=True)
            return []
    
    async def store_conversation(
        self,
        session_id: str,
        role: str,
        content: str,
        **kwargs
    ) -> Optional[Memory]:
        """存储对话记忆"""
        return await self.store_memory(
            memory_type=MemoryType.CONVERSATION,
            content=f"{role}: {content}",
            session_id=session_id,
            importance_score=0.3,  # 对话记忆重要性较低
            **kwargs
        )
    
    async def store_fact(
        self,
        content: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        importance_score: float = 0.7,
        **kwargs
    ) -> Optional[Memory]:
        """存储事实记忆"""
        return await self.store_memory(
            memory_type=MemoryType.FACT,
            content=content,
            session_id=session_id,
            user_id=user_id,
            importance_score=importance_score,
            **kwargs
        )
    
    async def store_preference(
        self,
        content: str,
        user_id: str,
        importance_score: float = 0.8,
        **kwargs
    ) -> Optional[Memory]:
        """存储用户偏好"""
        return await self.store_memory(
            memory_type=MemoryType.PREFERENCE,
            content=content,
            user_id=user_id,
            importance_score=importance_score,
            **kwargs
        )
    
    async def update_memory_importance(
        self,
        memory_id: str,
        importance_score: float
    ) -> bool:
        """更新记忆重要性"""
        if not self.memory_manager:
            return False
        
        try:
            return await self.memory_manager.update_importance(
                memory_id=memory_id,
                importance_score=importance_score
            )
        except Exception as e:
            logger.error(f"更新记忆重要性失败: {e}", exc_info=True)
            return False
    
    async def delete_memory(
        self,
        memory_id: str,
        soft_delete: bool = True
    ) -> bool:
        """删除记忆"""
        if not self.memory_manager:
            return False
        
        try:
            return await self.memory_manager.delete(
                memory_id=memory_id,
                soft_delete=soft_delete
            )
        except Exception as e:
            logger.error(f"删除记忆失败: {e}", exc_info=True)
            return False

