#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
结果存储层
负责将任务执行结果存储到数据库
"""
from typing import Optional, Any
from datetime import datetime
from loguru import logger

from core.models.agent_models import Task, TaskStatus
from core.component.storage.task_queue import TaskQueue


class ResultStorage:
    """结果存储层"""
    
    def __init__(self, task_queue: TaskQueue):
        """
        初始化结果存储层
        
        Args:
            task_queue: 任务队列管理器
        """
        self.task_queue = task_queue
    
    async def save_result(
        self,
        task: Task,
        result: Any,
        status: TaskStatus = TaskStatus.COMPLETED,
        error_message: Optional[str] = None
    ) -> bool:
        """
        保存任务结果
        
        Args:
            task: 任务对象
            result: 执行结果
            status: 任务状态
            error_message: 错误信息（如果失败）
            
        Returns:
            是否保存成功
        """
        try:
            # 更新任务信息
            task.status = status
            task.result = result
            task.error_message = error_message
            task.completed_at = datetime.now()
            task.updated_at = datetime.now()
            
            # 如果任务还没有开始时间，设置开始时间
            if not task.started_at:
                task.started_at = datetime.now()
            
            # 保存到数据库
            success = await self.task_queue.update_task(task)
            
            if success:
                logger.info(f"任务结果已保存: {task.task_id}, 状态: {status.value}")
            else:
                logger.error(f"任务结果保存失败: {task.task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"保存任务结果时发生错误: {task.task_id}, 错误: {e}")
            return False
    
    async def save_execution_start(self, task: Task) -> bool:
        """
        保存任务开始执行的时间
        
        Args:
            task: 任务对象
            
        Returns:
            是否保存成功
        """
        try:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            task.updated_at = datetime.now()
            
            success = await self.task_queue.update_task(task)
            
            if success:
                logger.debug(f"任务开始时间已保存: {task.task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"保存任务开始时间时发生错误: {task.task_id}, 错误: {e}")
            return False
    
    async def save_execution_error(
        self,
        task: Task,
        error: Exception,
        error_message: Optional[str] = None
    ) -> bool:
        """
        保存任务执行错误
        
        Args:
            task: 任务对象
            error: 异常对象
            error_message: 错误消息（可选）
            
        Returns:
            是否保存成功
        """
        error_msg = error_message or str(error)
        return await self.save_result(
            task=task,
            result=None,
            status=TaskStatus.FAILED,
            error_message=error_msg
        )

