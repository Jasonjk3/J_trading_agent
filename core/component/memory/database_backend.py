#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库存储后端
持久化存储，适合长期记忆
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, update, delete, func, or_
from loguru import logger

from core.infrastructure.database.async_database import AsyncDatabase
from core.component.memory.memory_store import MemoryStore
from core.component.memory.memory_types import Memory, MemoryType
from models.inner_models.memory_model import MemoryModel


class DatabaseBackend(MemoryStore):
    """数据库存储后端"""
    
    def __init__(self, db: AsyncDatabase):
        """
        初始化数据库存储
        
        Args:
            db: 异步数据库连接
        """
        self.db = db
    
    async def initialize(self) -> bool:
        """初始化存储后端"""
        try:
            # 可以在这里执行数据库迁移等操作
            logger.info("DatabaseBackend 初始化完成")
            return True
        except Exception as e:
            logger.error(f"DatabaseBackend 初始化失败: {e}", exc_info=True)
            return False
    
    def _model_to_memory(self, model: MemoryModel) -> Memory:
        """将数据库模型转换为 Memory 对象"""
        return Memory(
            memory_id=model.memory_id,
            agent_id=model.agent_id,
            session_id=model.session_id,
            user_id=model.user_id,
            memory_type=MemoryType(model.memory_type),
            content=model.content,
            metadata=model.metadata or {},
            related_memories=model.related_memories or [],
            embedding=model.embedding,
            created_at=model.created_at,
            updated_at=model.updated_at,
            accessed_at=model.accessed_at,
            expires_at=model.expires_at,
            importance_score=model.importance_score,
            access_count=model.access_count
        )
    
    def _memory_to_model(self, memory: Memory) -> MemoryModel:
        """将 Memory 对象转换为数据库模型"""
        return MemoryModel(
            memory_id=memory.memory_id,
            agent_id=memory.agent_id,
            session_id=memory.session_id,
            user_id=memory.user_id,
            memory_type=memory.memory_type.value,
            content=memory.content,
            metadata=memory.metadata,
            related_memories=memory.related_memories,
            embedding=memory.embedding,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
            accessed_at=memory.accessed_at,
            expires_at=memory.expires_at,
            importance_score=memory.importance_score,
            access_count=memory.access_count,
            is_deleted=0
        )
    
    async def save(self, memory: Memory) -> bool:
        """保存记忆"""
        try:
            async with self.db.get_session() as db_session:
                # 检查是否已存在
                result = await db_session.execute(
                    select(MemoryModel).where(MemoryModel.memory_id == memory.memory_id)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # 更新
                    existing.agent_id = memory.agent_id
                    existing.session_id = memory.session_id
                    existing.user_id = memory.user_id
                    existing.memory_type = memory.memory_type.value
                    existing.content = memory.content
                    existing.metadata = memory.metadata
                    existing.related_memories = memory.related_memories
                    existing.embedding = memory.embedding
                    existing.updated_at = datetime.now()
                    existing.accessed_at = memory.accessed_at
                    existing.expires_at = memory.expires_at
                    existing.importance_score = memory.importance_score
                    existing.access_count = memory.access_count
                    existing.is_deleted = 0
                else:
                    # 新建
                    memory_model = self._memory_to_model(memory)
                    db_session.add(memory_model)
                
                await db_session.commit()
                return True
        except Exception as e:
            logger.error(f"保存记忆失败: {e}", exc_info=True)
            return False
    
    async def get(self, memory_id: str) -> Optional[Memory]:
        """获取记忆"""
        try:
            async with self.db.get_session() as db_session:
                result = await db_session.execute(
                    select(MemoryModel).where(
                        MemoryModel.memory_id == memory_id,
                        MemoryModel.is_deleted == 0
                    )
                )
                model = result.scalar_one_or_none()
                
                if not model:
                    return None
                
                # 检查是否过期
                if model.expires_at and model.expires_at < datetime.now():
                    # 标记为已删除
                    await db_session.execute(
                        update(MemoryModel)
                        .where(MemoryModel.memory_id == memory_id)
                        .values(is_deleted=1)
                    )
                    await db_session.commit()
                    return None
                
                # 更新访问信息
                await db_session.execute(
                    update(MemoryModel)
                    .where(MemoryModel.memory_id == memory_id)
                    .values(
                        accessed_at=datetime.now(),
                        access_count=MemoryModel.access_count + 1
                    )
                )
                await db_session.commit()
                
                return self._model_to_memory(model)
        except Exception as e:
            logger.error(f"获取记忆失败: {e}", exc_info=True)
            return None
    
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
        try:
            async with self.db.get_session() as db_session:
                # 构建查询
                stmt = select(MemoryModel).where(
                    MemoryModel.agent_id == agent_id,
                    MemoryModel.is_deleted == 0,
                    MemoryModel.content.like(f"%{query}%")
                )
                
                # 过滤条件
                if session_id:
                    stmt = stmt.where(MemoryModel.session_id == session_id)
                
                if user_id:
                    stmt = stmt.where(MemoryModel.user_id == user_id)
                
                if memory_types:
                    type_values = [mt.value for mt in memory_types]
                    stmt = stmt.where(MemoryModel.memory_type.in_(type_values))
                
                # 排除过期记忆
                stmt = stmt.where(
                    or_(
                        MemoryModel.expires_at.is_(None),
                        MemoryModel.expires_at > datetime.now()
                    )
                )
                
                # 排序：按重要性评分和访问时间
                stmt = stmt.order_by(
                    MemoryModel.importance_score.desc(),
                    MemoryModel.accessed_at.desc()
                ).limit(limit)
                
                result = await db_session.execute(stmt)
                models = result.scalars().all()
                
                return [self._model_to_memory(model) for model in models]
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}", exc_info=True)
            return []
    
    async def get_by_session(
        self,
        agent_id: str,
        session_id: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 100
    ) -> List[Memory]:
        """按会话获取记忆"""
        try:
            async with self.db.get_session() as db_session:
                stmt = select(MemoryModel).where(
                    MemoryModel.agent_id == agent_id,
                    MemoryModel.session_id == session_id,
                    MemoryModel.is_deleted == 0
                )
                
                if memory_types:
                    type_values = [mt.value for mt in memory_types]
                    stmt = stmt.where(MemoryModel.memory_type.in_(type_values))
                
                # 排除过期记忆
                stmt = stmt.where(
                    or_(
                        MemoryModel.expires_at.is_(None),
                        MemoryModel.expires_at > datetime.now()
                    )
                )
                
                # 按时间排序
                stmt = stmt.order_by(MemoryModel.created_at.asc()).limit(limit)
                
                result = await db_session.execute(stmt)
                models = result.scalars().all()
                
                return [self._model_to_memory(model) for model in models]
        except Exception as e:
            logger.error(f"按会话获取记忆失败: {e}", exc_info=True)
            return []
    
    async def get_by_agent(
        self,
        agent_id: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 100
    ) -> List[Memory]:
        """按 Agent 获取记忆"""
        try:
            async with self.db.get_session() as db_session:
                stmt = select(MemoryModel).where(
                    MemoryModel.agent_id == agent_id,
                    MemoryModel.is_deleted == 0
                )
                
                if memory_types:
                    type_values = [mt.value for mt in memory_types]
                    stmt = stmt.where(MemoryModel.memory_type.in_(type_values))
                
                # 排除过期记忆
                stmt = stmt.where(
                    or_(
                        MemoryModel.expires_at.is_(None),
                        MemoryModel.expires_at > datetime.now()
                    )
                )
                
                # 按时间排序
                stmt = stmt.order_by(MemoryModel.created_at.asc()).limit(limit)
                
                result = await db_session.execute(stmt)
                models = result.scalars().all()
                
                return [self._model_to_memory(model) for model in models]
        except Exception as e:
            logger.error(f"按 Agent 获取记忆失败: {e}", exc_info=True)
            return []
    
    async def delete(self, memory_id: str, soft_delete: bool = True) -> bool:
        """删除记忆"""
        try:
            async with self.db.get_session() as db_session:
                if soft_delete:
                    # 软删除
                    result = await db_session.execute(
                        update(MemoryModel)
                        .where(MemoryModel.memory_id == memory_id)
                        .values(is_deleted=1, updated_at=datetime.now())
                    )
                else:
                    # 硬删除
                    result = await db_session.execute(
                        delete(MemoryModel).where(MemoryModel.memory_id == memory_id)
                    )
                
                await db_session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"删除记忆失败: {e}", exc_info=True)
            return False
    
    async def update(self, memory: Memory) -> bool:
        """更新记忆"""
        try:
            async with self.db.get_session() as db_session:
                memory.updated_at = datetime.now()
                result = await db_session.execute(
                    update(MemoryModel)
                    .where(MemoryModel.memory_id == memory.memory_id)
                    .values(
                        agent_id=memory.agent_id,
                        session_id=memory.session_id,
                        user_id=memory.user_id,
                        memory_type=memory.memory_type.value,
                        content=memory.content,
                        metadata=memory.metadata,
                        related_memories=memory.related_memories,
                        embedding=memory.embedding,
                        updated_at=memory.updated_at,
                        accessed_at=memory.accessed_at,
                        expires_at=memory.expires_at,
                        importance_score=memory.importance_score,
                        access_count=memory.access_count
                    )
                )
                await db_session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"更新记忆失败: {e}", exc_info=True)
            return False
    
    async def cleanup_expired(self) -> int:
        """清理过期记忆"""
        try:
            async with self.db.get_session() as db_session:
                now = datetime.now()
                result = await db_session.execute(
                    update(MemoryModel)
                    .where(
                        MemoryModel.expires_at < now,
                        MemoryModel.is_deleted == 0
                    )
                    .values(is_deleted=1, updated_at=now)
                )
                await db_session.commit()
                
                count = result.rowcount
                if count > 0:
                    logger.info(f"DatabaseBackend 清理了 {count} 条过期记忆")
                
                return count
        except Exception as e:
            logger.error(f"清理过期记忆失败: {e}", exc_info=True)
            return 0

