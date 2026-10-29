#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Agent执行器
负责执行智能体的任务，管理任务生命周期
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional
from loguru import logger

from core.agent_base.base_agent import BaseAgent
from core.models.agent_models import AgentStatus, TaskStatus


class AgentExecutor:
    """智能体执行器"""

    def __init__(self, timeout_seconds: int = 300):
        """
        初始化执行器

        Args:
            timeout_seconds: 任务超时时间（秒）
        """
        self.timeout_seconds = timeout_seconds
        self._running_tasks: Dict[str, asyncio.Task] = {}  # 运行中的任务
        self._agent_locks: Dict[str, asyncio.Lock] = {}  # 每个Agent的锁，用于保护并发控制

    async def execute(
        self,
        agent: BaseAgent,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行任务

        Args:
            agent: 智能体实例
            task: 任务内容
            context: 上下文信息
            task_id: 任务ID

        Returns:
            执行结果
        """
        task_id = task_id or f"{agent.agent_id}_{datetime.now().timestamp()}"

        # 获取或创建Agent的锁，确保每个Agent有独立的锁
        if agent.agent_id not in self._agent_locks:
            self._agent_locks[agent.agent_id] = asyncio.Lock()

        # 使用锁保护并发检查和更新操作，确保原子性
        async with self._agent_locks[agent.agent_id]:
            # 检查智能体是否可用（在锁保护下检查，避免竞争条件）
            if not await agent.can_handle(task):
                raise ValueError(f"智能体 {agent.agent_id} 无法处理该任务，当前任务数: {agent.current_tasks}/{agent.max_concurrent_tasks}")

            # 更新智能体状态和任务计数（在锁保护下更新，确保原子性）
            await agent.update_status(AgentStatus.BUSY)
            agent.current_task_id = task_id
            agent.current_tasks += 1
            logger.debug(f"Agent {agent.agent_id} 任务计数更新: {agent.current_tasks}/{agent.max_concurrent_tasks}, 任务ID: {task_id}")

        # 注意：任务执行在锁外进行，避免长时间持有锁影响并发性能
        try:
            # 执行任务
            logger.info(f"开始执行任务: {task_id}, Agent: {agent.agent_id}")
            start_time = datetime.now()

            # 在 context 中传递标志和 task_id，告知 Agent 任务计数已由 Executor 管理
            if context is None:
                context = {}
            context['_managed_by_executor'] = True
            context['task_id'] = task_id  # 传递统一的 task_id 给 Agent

            # ==================== 执行流程管理（钩子函数调用）====================
            # 1. 执行前处理
            if not await agent._pre_execute(task, context):
                logger.warning(f"任务执行前处理失败: {task_id}")
                return {
                    "task_id": task_id,
                    "status": TaskStatus.FAILED.value,
                    "error": "执行前处理失败",
                    "agent_id": agent.agent_id
                }
            
            try:
                # 2. 执行核心业务逻辑（Agent 只负责业务逻辑）
                result = await asyncio.wait_for(
                    agent.execute(task, context),
                    timeout=self.timeout_seconds
                )
                
                # 3. 执行后处理
                result = await agent._post_execute(result, task, context)
                
            except asyncio.TimeoutError as e:
                # 超时错误处理
                logger.error(f"任务执行超时: {task_id}")
                result = await agent._handle_error(e, task, context)
                # 如果钩子函数没有处理超时，返回默认错误
                if not isinstance(result, dict) or result.get("success") is not False:
                    result = {
                        "success": False,
                        "error": "任务执行超时",
                        "task_id": task.get("task_id", task_id),
                        "agent_id": agent.agent_id
                    }
                    
            except Exception as e:
                # 4. 其他错误处理
                result = await agent._handle_error(e, task, context)
            # ==================== 执行流程管理结束 ====================

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # 更新性能指标
            await agent.update_metrics({
                "last_execution_time": duration,
                "total_executions": agent.performance_metrics.get("total_executions", 0) + 1
            })

            logger.info(f"任务执行完成: {task_id}, 耗时: {duration:.2f}秒")
            
            # 根据结果判断任务状态
            if isinstance(result, dict) and result.get("success") is False:
                status = TaskStatus.FAILED.value
            else:
                status = TaskStatus.COMPLETED.value
            
            return {
                "task_id": task_id,
                "status": status,
                "result": result,
                "duration": duration,
                "agent_id": agent.agent_id
            }

        except asyncio.TimeoutError:
            # 超时错误已在 try 块中处理，这里不应该到达
            logger.error(f"任务执行超时（外层捕获）: {task_id}")
            return {
                "task_id": task_id,
                "status": TaskStatus.FAILED.value,
                "error": "任务执行超时",
                "agent_id": agent.agent_id
            }

        except Exception as e:
            # 其他异常已在 try 块中处理，这里不应该到达
            logger.error(f"任务执行失败（外层捕获）: {task_id}, 错误: {e}")
            return {
                "task_id": task_id,
                "status": TaskStatus.FAILED.value,
                "error": str(e),
                "agent_id": agent.agent_id
            }

        finally:
            # 在锁保护下恢复智能体状态和任务计数
            # 确保锁存在（理论上应该存在，因为前面已经创建）
            if agent.agent_id in self._agent_locks:
                async with self._agent_locks[agent.agent_id]:
                    agent.current_tasks -= 1
                    logger.debug(f"Agent {agent.agent_id} 任务完成，任务计数更新: {agent.current_tasks}/{agent.max_concurrent_tasks}, 任务ID: {task_id}")
                    
                    if agent.current_tasks == 0:
                        await agent.update_status(AgentStatus.IDLE)
                        agent.current_task_id = None
                    else:
                        # 如果还有其他任务，保持忙碌状态
                        await agent.update_status(AgentStatus.BUSY)
            else:
                # 如果锁不存在（异常情况），直接更新但不保证线程安全
                logger.warning(f"Agent {agent.agent_id} 的锁不存在，直接更新任务计数（可能存在并发问题）")
                agent.current_tasks = max(0, agent.current_tasks - 1)
                if agent.current_tasks == 0:
                    await agent.update_status(AgentStatus.IDLE)
                    agent.current_task_id = None

    async def execute_async(
        self,
        agent: BaseAgent,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        callback: Optional[callable] = None
    ) -> str:
        """
        异步执行任务（不等待结果）

        Args:
            agent: 智能体实例
            task: 任务内容
            context: 上下文信息
            task_id: 任务ID
            callback: 完成后的回调函数

        Returns:
            任务ID
        """
        task_id = task_id or f"{agent.agent_id}_{datetime.now().timestamp()}"

        async def _execute_with_callback():
            try:
                result = await self.execute(agent, task, context, task_id)
                if callback:
                    await callback(result)
            finally:
                if task_id in self._running_tasks:
                    del self._running_tasks[task_id]

        # 创建异步任务
        asyncio_task = asyncio.create_task(_execute_with_callback())
        self._running_tasks[task_id] = asyncio_task

        logger.info(f"任务已提交异步执行: {task_id}")
        return task_id

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否取消成功
        """
        task = self._running_tasks.get(task_id)
        if not task:
            return False

        if task.done():
            return False

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        del self._running_tasks[task_id]
        logger.info(f"任务已取消: {task_id}")
        return True

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态信息
        """
        task = self._running_tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task_id,
            "done": task.done(),
            "cancelled": task.cancelled()
        }

    def get_running_tasks_count(self) -> int:
        """获取运行中的任务数量"""
        return len(self._running_tasks)

    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        等待任务完成

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）

        Returns:
            任务结果
        """
        task = self._running_tasks.get(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        try:
            await asyncio.wait_for(task, timeout=timeout)
            # 任务完成后会从_running_tasks中移除
            # 这里需要从任务结果中获取返回值
            return {"status": "completed"}
        except asyncio.TimeoutError:
            raise TimeoutError(f"等待任务超时: {task_id}")
        except asyncio.CancelledError:
            return {"status": "cancelled"}

