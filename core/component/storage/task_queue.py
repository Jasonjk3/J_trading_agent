#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
任务队列管理器
负责任务的入队、出队、优先级排序等操作
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger
from sqlalchemy import select, delete

from core.models.agent_models import Task, TaskStatus, TaskPriority
from models.inner_models.task_model import TaskModel
from core.infrastructure.database.async_database import AsyncDatabase


class TaskQueue:
    """任务队列管理器"""

    def __init__(self, db: Optional[AsyncDatabase] = None, max_size: int = 10000):
        """
        初始化任务队列

        Args:
            db: 数据库连接（可选）
            max_size: 队列最大容量
        """
        self.db = db
        self.max_size = max_size
        self._queues: Dict[TaskPriority, asyncio.Queue] = {
            TaskPriority.URGENT: asyncio.Queue(maxsize=max_size),
            TaskPriority.HIGH: asyncio.Queue(maxsize=max_size),
            TaskPriority.NORMAL: asyncio.Queue(maxsize=max_size),
            TaskPriority.LOW: asyncio.Queue(maxsize=max_size),
        }
        self._task_registry: Dict[str, Task] = {}  # 任务注册表（内存缓存）
        self._lock = asyncio.Lock()  # 队列操作锁

    def _task_to_model(self, task: Task) -> TaskModel:
        """将Task对象转换为TaskModel"""
        return TaskModel(
            task_id=task.task_id,
            session_id=task.session_id,
            agent_id=task.agent_id,
            content=task.content,
            # TaskPriority 是 int 枚举，需要存储 .value (整数值)
            priority=task.priority.value if isinstance(task.priority, TaskPriority) else task.priority,
            # TaskStatus 是 str 枚举，需要存储 .value (字符串值)
            status=task.status.value if isinstance(task.status, TaskStatus) else task.status,
            meta_data=task.metadata,
            result=task.result,
            error_message=task.error_message,
            created_at=task.created_at,
            updated_at=task.updated_at,
            started_at=task.started_at,
            completed_at=task.completed_at
        )

    def _model_to_task(self, model: TaskModel) -> Task:
        """将TaskModel转换为Task对象"""
        return Task(
            task_id=model.task_id,
            session_id=model.session_id,
            agent_id=model.agent_id,
            content=model.content,
            # 从整数值转换回 TaskPriority 枚举
            priority=TaskPriority(model.priority) if isinstance(model.priority, int) else model.priority,
            # 从字符串值转换回 TaskStatus 枚举
            status=TaskStatus(model.status) if isinstance(model.status, str) and not isinstance(model.status, TaskStatus) else model.status,
            metadata=model.meta_data or {},
            result=model.result,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
            started_at=model.started_at,
            completed_at=model.completed_at
        )

    async def enqueue(self, task: Task) -> bool:
        """
        将任务加入队列

        Args:
            task: 任务对象

        Returns:
            是否成功入队
        """
        async with self._lock:
            if len(self._task_registry) >= self.max_size:
                logger.warning(f"任务队列已满，无法入队任务: {task.task_id}")
                return False

            try:
                # 更新任务状态
                task.status = TaskStatus.QUEUED
                task.updated_at = datetime.now()

                # 注册任务到内存
                self._task_registry[task.task_id] = task

                # 保存到数据库
                if self.db:
                    async with self.db.get_session() as db_session:
                        task_model = self._task_to_model(task)
                        db_session.add(task_model)
                        await db_session.commit()

                # 根据优先级加入对应队列
                queue = self._queues[task.priority]
                await queue.put(task)
                logger.info(f"任务已入队: {task.task_id}, 优先级: {task.priority.name}")
                return True
            except asyncio.QueueFull:
                logger.error(f"优先级队列已满: {task.priority.name}")
                return False
            except Exception as e:
                logger.error(f"任务入队失败: {task.task_id}, 错误: {e}")
                return False

    async def dequeue(self, timeout: Optional[float] = None) -> Optional[Task]:
        """
        从队列中取出任务（按优先级顺序）

        Args:
            timeout: 超时时间（秒）

        Returns:
            任务对象，如果超时则返回None
        """
        # 按优先级顺序尝试从各个队列取任务
        for priority in [TaskPriority.URGENT, TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]:
            queue = self._queues[priority]
            try:
                task = await asyncio.wait_for(queue.get(), timeout=timeout if timeout else 0.1)
                if task:
                    task.status = TaskStatus.ASSIGNED
                    task.updated_at = datetime.now()
                    logger.debug(f"任务已出队: {task.task_id}, 优先级: {priority.name}")
                    return task
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"任务出队失败，优先级: {priority.name}, 错误: {e}")
                continue

        return None

    async def get_task(self, task_id: str) -> Optional[Task]:
        """
        获取任务信息

        Args:
            task_id: 任务ID

        Returns:
            任务对象
        """
        # 先从内存缓存获取
        task = self._task_registry.get(task_id)
        if task:
            return task
        
        # 如果内存中没有，从数据库加载
        if self.db:
            try:
                async with self.db.get_session() as db_session:
                    result = await db_session.execute(
                        select(TaskModel).where(TaskModel.task_id == task_id)
                    )
                    task_model = result.scalar_one_or_none()
                    if task_model:
                        task = self._model_to_task(task_model)
                        # 缓存到内存
                        self._task_registry[task.task_id] = task
                        return task
            except Exception as e:
                logger.error(f"从数据库加载任务失败: {task_id}, 错误: {e}")
        
        return None

    async def update_task(self, task: Task) -> bool:
        """
        更新任务信息

        Args:
            task: 任务对象

        Returns:
            是否更新成功
        """
        async with self._lock:
            task.updated_at = datetime.now()
            
            # 更新内存缓存
            self._task_registry[task.task_id] = task
            
            # 更新数据库
            if self.db:
                try:
                    async with self.db.get_session() as db_session:
                        result = await db_session.execute(
                            select(TaskModel).where(TaskModel.task_id == task.task_id)
                        )
                        task_model = result.scalar_one_or_none()
                        if task_model:
                            # 更新字段
                            task_model.status = task.status.value if isinstance(task.status, TaskStatus) else task.status
                            task_model.agent_id = task.agent_id
                            task_model.priority = task.priority.value if isinstance(task.priority, TaskPriority) else task.priority
                            task_model.meta_data = task.metadata
                            task_model.result = task.result
                            task_model.error_message = task.error_message
                            task_model.updated_at = task.updated_at
                            task_model.started_at = task.started_at
                            task_model.completed_at = task.completed_at
                            await db_session.commit()
                        else:
                            # 如果不存在，创建新记录
                            task_model = self._task_to_model(task)
                            db_session.add(task_model)
                            await db_session.commit()
                except Exception as e:
                    logger.error(f"更新任务到数据库失败: {task.task_id}, 错误: {e}")
            
            logger.debug(f"任务已更新: {task.task_id}, 状态: {task.status}")
            return True

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否取消成功
        """
        async with self._lock:
            task = self._task_registry.get(task_id)
            if not task:
                logger.warning(f"任务不存在: {task_id}")
                return False

            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                logger.warning(f"任务已完成或已取消，无法取消: {task_id}")
                return False

            task.status = TaskStatus.CANCELLED
            task.updated_at = datetime.now()
            logger.info(f"任务已取消: {task_id}")
            return True

    async def get_queue_stats(self) -> Dict[str, int]:
        """
        获取队列统计信息

        Returns:
            各优先级队列的长度
        """
        stats = {}
        for priority, queue in self._queues.items():
            stats[priority.name] = queue.qsize()
        stats["total"] = len(self._task_registry)
        return stats

    async def get_pending_tasks(self, limit: int = 100) -> List[Task]:
        """
        获取等待中的任务列表

        Args:
            limit: 返回数量限制

        Returns:
            任务列表
        """
        pending_tasks = [
            task for task in self._task_registry.values()
            if task.status in [TaskStatus.PENDING, TaskStatus.QUEUED]
        ]
        # 按优先级和创建时间排序
        pending_tasks.sort(
            key=lambda t: (t.priority.value, t.created_at),
            reverse=True
        )
        return pending_tasks[:limit]

    async def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """
        清理已完成的任务（超过指定时间的）

        Args:
            max_age_hours: 最大保留时间（小时）
        """
        async with self._lock:
            now = datetime.now()
            to_remove = []
            for task_id, task in self._task_registry.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    age = (now - task.updated_at).total_seconds() / 3600
                    if age > max_age_hours:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._task_registry[task_id]

            # 从数据库清理
            if self.db and to_remove:
                try:
                    async with self.db.get_session() as db_session:
                        # 计算过期时间
                        expire_time = now - timedelta(hours=max_age_hours)
                        result = await db_session.execute(
                            delete(TaskModel).where(
                                TaskModel.status.in_([
                                    TaskStatus.COMPLETED,
                                    TaskStatus.FAILED,
                                    TaskStatus.CANCELLED
                                ]),
                                TaskModel.updated_at < expire_time
                            )
                        )
                        await db_session.commit()
                        logger.info(f"已从数据库清理 {result.rowcount} 个已完成的任务")
                except Exception as e:
                    logger.error(f"清理数据库任务失败: {e}")

            if to_remove:
                logger.info(f"已清理 {len(to_remove)} 个已完成的任务")

