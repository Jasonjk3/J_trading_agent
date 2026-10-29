#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
会话存储管理器
负责会话的创建、更新、查询和过期清理
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger
from sqlalchemy import select, update, delete, func

from core.models.agent_models import Session
from models.inner_models.session_model import SessionModel
from models.inner_models.message_model import MessageModel
from core.infrastructure.database.async_database import AsyncDatabase


class SessionStore:
    """会话存储管理器"""

    def __init__(self, db: AsyncDatabase, default_ttl_hours: int = 24):
        """
        初始化会话存储

        Args:
            db: 数据库连接
            default_ttl_hours: 默认会话过期时间（小时）
        """
        self.db = db
        self.default_ttl_hours = default_ttl_hours
        self._cleanup_task: Optional[asyncio.Task] = None

    def _model_to_session(self, model: SessionModel) -> Session:
        """将数据库模型转换为Session对象"""
        return Session(
            session_id=model.session_id,
            user_id=model.user_id,
            title=model.title,
            context=model.context or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
            expires_at=model.expires_at,
            is_active=model.is_active
        )

    async def create_session(
        self,
        user_id: Optional[str] = None,
        context: Optional[Dict] = None,
        ttl_hours: Optional[int] = None
    ) -> Session:
        """
        创建新会话

        Args:
            user_id: 用户ID
            context: 初始上下文
            ttl_hours: 过期时间（小时），None则使用默认值

        Returns:
            会话对象
        """
        session = Session(
            user_id=user_id,
            context=context or {},
            expires_at=datetime.now() + timedelta(hours=ttl_hours or self.default_ttl_hours)
        )

        # 保存到数据库
        async with self.db.get_session() as db_session:
            session_model = SessionModel(
                session_id=session.session_id,
                user_id=session.user_id,
                title=session.title,
                context=session.context,
                is_active=session.is_active,
                created_at=session.created_at,
                updated_at=session.updated_at,
                expires_at=session.expires_at
            )
            db_session.add(session_model)
            await db_session.commit()

        logger.info(f"会话已创建: {session.session_id}, 用户: {user_id}")
        return session

    async def get_session(self, session_id: str, user_id: Optional[str] = None) -> Optional[Session]:
        """
        获取会话

        Args:
            session_id: 会话ID
            user_id: 用户ID（可选，如果提供则验证会话所有权）

        Returns:
            会话对象，如果不存在、已过期或不属于指定用户则返回None
        """
        async with self.db.get_session() as db_session:
            query = select(SessionModel).where(SessionModel.session_id == session_id)
            # 如果提供了user_id，添加用户过滤条件（数据隔离）
            if user_id:
                query = query.where(SessionModel.user_id == user_id)
            
            result = await db_session.execute(query)
            session_model = result.scalar_one_or_none()
            
            if not session_model:
                return None

            # 检查是否过期
            if session_model.expires_at and session_model.expires_at < datetime.now():
                logger.info(f"会话已过期: {session_id}")
                # 删除过期会话
                await db_session.execute(
                    delete(SessionModel).where(SessionModel.session_id == session_id)
                )
                await db_session.commit()
                return None

            if not session_model.is_active:
                return None

            return self._model_to_session(session_model)

    async def update_session(
        self,
        session_id: str,
        context: Optional[Dict] = None,
        history: Optional[List] = None,
        extend_ttl: bool = True,
        title: Optional[str] = None
    ) -> bool:
        """
        更新会话

        Args:
            session_id: 会话ID
            context: 要更新的上下文（会合并到现有上下文）
            history: 要添加的历史记录（已迁移到MessageModel，保留参数以兼容）
            extend_ttl: 是否延长过期时间
            title: 会话名称

        Returns:
            是否更新成功
        """
        async with self.db.get_session() as db_session:
            result = await db_session.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            session_model = result.scalar_one_or_none()
            
            if not session_model:
                logger.warning(f"会话不存在: {session_id}")
                return False

            # 更新会话名称
            if title is not None:
                session_model.title = title

            # 更新上下文
            if context:
                current_context = session_model.context or {}
                current_context.update(context)
                session_model.context = current_context

            # 添加历史记录（使用消息表）
            if history:
                for msg in history:
                    message_model = MessageModel(
                        session_id=session_id,
                        user_id=session_model.user_id,  # 从会话中获取user_id
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                        images=msg.get("images"),  # 保存图片列表
                        timestamp=datetime.fromisoformat(msg.get("timestamp", datetime.now().isoformat())) if msg.get("timestamp") else datetime.now()
                    )
                    db_session.add(message_model)

            # 延长过期时间
            if extend_ttl:
                session_model.expires_at = datetime.now() + timedelta(hours=self.default_ttl_hours)

            session_model.updated_at = datetime.now()
            await db_session.commit()
            logger.debug(f"会话已更新: {session_id}")
            return True

    async def add_history(self, session_id: str, message: Dict, user_id: Optional[str] = None) -> bool:
        """
        添加历史记录（使用消息表存储，避免并发问题）

        Args:
            session_id: 会话ID
            message: 消息内容（包含role, content等）
            user_id: 用户ID（用于数据隔离，如果提供则从会话中获取）

        Returns:
            是否添加成功
        """
        async with self.db.get_session() as db_session:
            # 检查会话是否存在
            query = select(SessionModel).where(SessionModel.session_id == session_id)
            if user_id:
                query = query.where(SessionModel.user_id == user_id)
            
            result = await db_session.execute(query)
            session_model = result.scalar_one_or_none()
            
            if not session_model:
                logger.warning(f"会话不存在: {session_id}")
                return False

            # 如果提供了user_id，使用它；否则从会话中获取
            message_user_id = user_id or session_model.user_id

            # 使用消息表存储消息（避免JSON字段的并发问题）
            message_model = MessageModel(
                session_id=session_id,
                user_id=message_user_id,  # 保存用户ID用于数据隔离
                role=message.get("role", "user"),
                content=message.get("content", ""),
                images=message.get("images"),  # 保存图片列表
                timestamp=datetime.fromisoformat(message.get("timestamp", datetime.now().isoformat())) if message.get("timestamp") else datetime.now()
            )
            db_session.add(message_model)
            
            # 更新会话的更新时间
            session_model.updated_at = datetime.now()
            
            await db_session.commit()
            logger.debug(f"已添加历史记录到会话 {session_id}: role={message.get('role')}, content_length={len(message.get('content', ''))}, user_id={message_user_id}")
            return True

    async def get_history(self, session_id: str, user_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """
        获取会话历史记录（从消息表查询，返回最新的N条）

        Args:
            session_id: 会话ID
            user_id: 用户ID（可选，如果提供则只返回该用户的消息，用于数据隔离）
            limit: 返回数量限制

        Returns:
            历史记录列表（按时间顺序）
        """
        async with self.db.get_session() as db_session:
            # 如果提供了user_id，先验证会话是否属于该用户
            if user_id:
                session = await self.get_session(session_id, user_id=user_id)
                if not session:
                    logger.warning(f"会话 {session_id} 不属于用户 {user_id}")
                    return []
            
            # 构建查询条件
            query_conditions = [MessageModel.session_id == session_id]
            if user_id:
                query_conditions.append(MessageModel.user_id == user_id)
            
            # 先查询总数
            count_result = await db_session.execute(
                select(func.count(MessageModel.id)).where(*query_conditions)
            )
            total_count = count_result.scalar() or 0
            
            if total_count == 0:
                return []
            
            # 如果需要限制数量且总数超过限制，只取最后N条
            if total_count > limit:
                # 计算偏移量
                offset = total_count - limit
                # 按时间升序查询，跳过前面的消息
                result = await db_session.execute(
                    select(MessageModel)
                    .where(*query_conditions)
                    .order_by(MessageModel.timestamp.asc(), MessageModel.id.asc())
                    .offset(offset)
                    .limit(limit)
                )
            else:
                # 如果总数不超过限制，返回所有消息
                result = await db_session.execute(
                    select(MessageModel)
                    .where(*query_conditions)
                    .order_by(MessageModel.timestamp.asc(), MessageModel.id.asc())
                )
            
            messages = result.scalars().all()
            
            # 转换为字典格式
            history = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "images": msg.images,  # 返回图片列表
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
                }
                for msg in messages
            ]
            
            return history

    async def delete_session(self, session_id: str) -> bool:
        """
        删除会话（同时删除相关消息）

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        async with self.db.get_session() as db_session:
            # 先删除相关消息
            await db_session.execute(
                delete(MessageModel).where(MessageModel.session_id == session_id)
            )
            
            # 再删除会话
            result = await db_session.execute(
                delete(SessionModel).where(SessionModel.session_id == session_id)
            )
            await db_session.commit()
            
            if result.rowcount > 0:
                logger.info(f"会话已删除: {session_id}")
                return True
            return False

    async def deactivate_session(self, session_id: str) -> bool:
        """
        停用会话（软删除）

        Args:
            session_id: 会话ID

        Returns:
            是否停用成功
        """
        async with self.db.get_session() as db_session:
            result = await db_session.execute(
                update(SessionModel)
                .where(SessionModel.session_id == session_id)
                .values(is_active=False, updated_at=datetime.now())
            )
            await db_session.commit()
            
            if result.rowcount > 0:
                logger.info(f"会话已停用: {session_id}")
                return True
            return False

    async def get_user_sessions(self, user_id: str, active_only: bool = True) -> List[Session]:
        """
        获取用户的所有会话

        Args:
            user_id: 用户ID
            active_only: 是否只返回活跃会话

        Returns:
            会话列表
        """
        async with self.db.get_session() as db_session:
            query = select(SessionModel).where(SessionModel.user_id == user_id)
            if active_only:
                query = query.where(SessionModel.is_active == True)
            query = query.order_by(SessionModel.updated_at.desc())
            
            result = await db_session.execute(query)
            session_models = result.scalars().all()
            
            return [self._model_to_session(model) for model in session_models]

    async def get_all_sessions(self, active_only: bool = True, limit: int = 100) -> List[Session]:
        """
        获取所有会话

        Args:
            active_only: 是否只返回活跃会话
            limit: 返回数量限制

        Returns:
            会话列表
        """
        async with self.db.get_session() as db_session:
            query = select(SessionModel)
            if active_only:
                query = query.where(SessionModel.is_active == True)
            query = query.order_by(SessionModel.updated_at.desc()).limit(limit)
            
            result = await db_session.execute(query)
            session_models = result.scalars().all()
            
            return [self._model_to_session(model) for model in session_models]

    async def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话（同时删除相关消息）

        Returns:
            清理的会话数量
        """
        async with self.db.get_session() as db_session:
            now = datetime.now()
            
            # 先查询过期会话的ID
            expired_result = await db_session.execute(
                select(SessionModel.session_id).where(
                    SessionModel.expires_at < now
                )
            )
            expired_session_ids = [row[0] for row in expired_result.fetchall()]
            
            if expired_session_ids:
                # 删除相关消息
                await db_session.execute(
                    delete(MessageModel).where(
                        MessageModel.session_id.in_(expired_session_ids)
                    )
                )
                
                # 删除过期会话
                result = await db_session.execute(
                    delete(SessionModel).where(
                        SessionModel.expires_at < now
                    )
                )
                await db_session.commit()
                
                count = result.rowcount
                if count > 0:
                    logger.info(f"已清理 {count} 个过期会话及其相关消息")
                
                return count
            
            return 0

    async def start_cleanup_task(self, interval_seconds: int = 3600):
        """
        启动定期清理任务

        Args:
            interval_seconds: 清理间隔（秒）
        """
        if self._cleanup_task and not self._cleanup_task.done():
            return

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    await self.cleanup_expired_sessions()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"清理任务出错: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("会话清理任务已启动")

    async def stop_cleanup_task(self):
        """停止清理任务"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("会话清理任务已停止")

    async def get_stats(self) -> Dict:
        """
        获取存储统计信息

        Returns:
            统计信息字典
        """
        async with self.db.get_session() as db_session:
            # 总数
            from sqlalchemy import func
            total_result = await db_session.execute(
                select(func.count(SessionModel.session_id))
            )
            total = total_result.scalar() or 0
            
            # 活跃会话数
            active_result = await db_session.execute(
                select(func.count(SessionModel.session_id)).where(SessionModel.is_active == True)
            )
            active = active_result.scalar() or 0
            
            # 过期会话数
            now = datetime.now()
            expired_result = await db_session.execute(
                select(func.count(SessionModel.session_id)).where(SessionModel.expires_at < now)
            )
            expired = expired_result.scalar() or 0

            return {
                "total_sessions": total,
                "active_sessions": active,
                "expired_sessions": expired
            }

