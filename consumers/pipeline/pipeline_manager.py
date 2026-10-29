#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
管道管理器
协调消息消费者、任务解析器、执行器和结果存储
"""
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger

from core.component.registry.agent_registry import AgentRegistry
from core.component.executor.agent_executor import AgentExecutor
from core.component.storage.task_queue import TaskQueue
from core.models.agent_models import Task, TaskStatus
from consumers.pipeline.config import PipelineConfig
from consumers.pipeline.message_consumer import MessageConsumer
from consumers.pipeline.task_parser import TaskParser
from consumers.pipeline.result_storage import ResultStorage


class PipelineManager:
    """管道管理器"""
    
    def __init__(
        self,
        config: PipelineConfig,
        agent_registry: AgentRegistry,
        agent_executor: AgentExecutor,
        task_queue: TaskQueue
    ):
        """
        初始化管道管理器
        
        Args:
            config: 管道配置
            agent_registry: Agent注册中心
            agent_executor: Agent执行器
            task_queue: 任务队列管理器
        """
        self.config = config
        self.agent_registry = agent_registry
        self.agent_executor = agent_executor
        self.task_queue = task_queue
        
        # 初始化组件
        self.consumer = MessageConsumer(
            redis_config=config.redis,
            queue_configs=config.queues,
            poll_interval=config.poll_interval
        )
        
        self.parser = TaskParser(
            agent_registry=agent_registry,
            task_type_agent_mapping=config.task_type_agent_mapping
        )
        
        self.storage = ResultStorage(task_queue=task_queue)
        
        # 运行状态
        self._running = False
        self._workers: List[asyncio.Task] = []
        
        # 指标统计
        self.metrics = {
            "total_processed": 0,
            "total_succeeded": 0,
            "total_failed": 0,
            "total_errors": 0,
            "start_time": None,
            "last_processed_time": None
        }
    
    async def start(self):
        """启动管道"""
        if self._running:
            logger.warning("管道已在运行")
            return
        
        try:
            # 连接Redis
            await self.consumer.connect()
            
            # 启动消费者
            self.consumer.start()
            
            # 启动工作线程
            self._running = True
            self.metrics["start_time"] = datetime.now()
            
            for i in range(self.config.worker_count):
                worker = asyncio.create_task(
                    self._worker_loop(f"worker-{i+1}")
                )
                self._workers.append(worker)
            
            logger.info(f"管道已启动，工作线程数: {self.config.worker_count}")
            
        except Exception as e:
            logger.error(f"启动管道失败: {e}")
            self._running = False
            raise
    
    async def stop(self, timeout: float = 30.0):
        """
        停止管道
        
        Args:
            timeout: 停止超时时间（秒）
        """
        if not self._running:
            return
        
        logger.info("正在停止管道...")
        self._running = False
        self.consumer.stop()
        
        # 等待所有工作线程完成当前任务
        if self._workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"停止管道超时，强制取消工作线程")
                for worker in self._workers:
                    worker.cancel()
        
        self._workers.clear()
        
        # 断开Redis连接
        await self.consumer.disconnect()
        
        logger.info("管道已停止")
    
    async def _worker_loop(self, worker_name: str):
        """
        工作线程循环
        
        Args:
            worker_name: 工作线程名称
        """
        logger.info(f"工作线程 {worker_name} 已启动")
        
        while self._running:
            try:
                # 消费消息（单个或批量）
                if self.config.max_batch_size > 1:
                    messages = await self.consumer.consume_batch(
                        max_batch_size=self.config.max_batch_size
                    )
                    if messages:
                        await self._process_batch(messages)
                    else:
                        await asyncio.sleep(self.config.poll_interval)
                else:
                    message = await self.consumer.consume()
                    if message:
                        await self._process_message(message)
                    else:
                        await asyncio.sleep(self.config.poll_interval)
                
            except asyncio.CancelledError:
                logger.info(f"工作线程 {worker_name} 被取消")
                break
            except Exception as e:
                logger.error(f"工作线程 {worker_name} 发生错误: {e}")
                self.metrics["total_errors"] += 1
                await asyncio.sleep(self.config.poll_interval)
        
        logger.info(f"工作线程 {worker_name} 已停止")
    
    async def _process_message(self, message: Dict[str, Any]):
        """
        处理单个消息
        
        Args:
            message: 消息字典
        """
        task = None
        try:
            # 解析消息（异步）
            task = await self.parser.parse_message(message)
            if not task:
                logger.warning(f"消息解析失败: {message.get('task_id', 'unknown')}")
                self.metrics["total_failed"] += 1
                return
            
            # 验证任务（异步）
            is_valid, error_msg = await self.parser.validate_task(task)
            if not is_valid:
                logger.warning(f"任务验证失败: {task.task_id}, 错误: {error_msg}")
                await self.storage.save_execution_error(
                    task=task,
                    error=ValueError(error_msg),
                    error_message=error_msg
                )
                self.metrics["total_failed"] += 1
                return
            
            # 保存任务到队列（如果还没有保存）
            await self.task_queue.enqueue(task)
            
            # 执行任务
            await self._execute_task(task)
            
        except Exception as e:
            logger.error(f"处理消息时发生错误: {e}")
            self.metrics["total_errors"] += 1
            if task:
                await self.storage.save_execution_error(task=task, error=e)
                self.metrics["total_failed"] += 1
    
    async def _process_batch(self, messages: List[Dict[str, Any]]):
        """
        批量处理消息
        
        Args:
            messages: 消息列表
        """
        tasks = []
        
        # 解析所有消息（异步）
        for message in messages:
            try:
                task = await self.parser.parse_message(message)
                if task:
                    is_valid, error_msg = await self.parser.validate_task(task)
                    if is_valid:
                        tasks.append(task)
                    else:
                        logger.warning(f"任务验证失败: {task.task_id}, 错误: {error_msg}")
                        await self.storage.save_execution_error(
                            task=task,
                            error=ValueError(error_msg),
                            error_message=error_msg
                        )
                        self.metrics["total_failed"] += 1
                else:
                    self.metrics["total_failed"] += 1
            except Exception as e:
                logger.error(f"解析消息时发生错误: {e}")
                self.metrics["total_errors"] += 1
        
        # 批量保存任务到队列
        for task in tasks:
            try:
                await self.task_queue.enqueue(task)
            except Exception as e:
                logger.error(f"任务入队失败: {task.task_id}, 错误: {e}")
                self.metrics["total_errors"] += 1
        
        # 并发执行任务
        if tasks:
            await asyncio.gather(
                *[self._execute_task(task) for task in tasks],
                return_exceptions=True
            )
    
    async def _execute_task(self, task: Task):
        """
        执行任务
        
        Args:
            task: 任务对象
        """
        try:
            # 获取Agent
            if not task.agent_id:
                logger.error(f"任务 {task.task_id} 没有指定Agent ID")
                await self.storage.save_execution_error(
                    task=task,
                    error=ValueError("未指定Agent ID"),
                    error_message="未指定Agent ID"
                )
                self.metrics["total_failed"] += 1
                return
            
            agent = await self.agent_registry.get_agent(task.agent_id)
            if not agent:
                logger.error(f"Agent不存在: {task.agent_id}")
                await self.storage.save_execution_error(
                    task=task,
                    error=ValueError(f"Agent不存在: {task.agent_id}"),
                    error_message=f"Agent不存在: {task.agent_id}"
                )
                self.metrics["total_failed"] += 1
                return
            
            # 保存开始执行时间
            await self.storage.save_execution_start(task)
            
            # 执行任务
            task_dict = {
                "task_id": task.task_id,
                "content": task.content,
                "session_id": task.session_id,
                **task.metadata
            }
            
            result = await asyncio.wait_for(
                self.agent_executor.execute(
                    agent=agent,
                    task=task_dict,
                    context={"session_id": task.session_id},
                    task_id=task.task_id
                ),
                timeout=self.config.task_timeout
            )
            
            # 保存结果
            if result.get("status") == TaskStatus.COMPLETED.value:
                await self.storage.save_result(
                    task=task,
                    result=result.get("result"),
                    status=TaskStatus.COMPLETED
                )
                self.metrics["total_succeeded"] += 1
            else:
                error_msg = result.get("error", "任务执行失败")
                await self.storage.save_result(
                    task=task,
                    result=None,
                    status=TaskStatus.FAILED,
                    error_message=error_msg
                )
                self.metrics["total_failed"] += 1
            
            self.metrics["total_processed"] += 1
            self.metrics["last_processed_time"] = datetime.now()
            
            logger.info(f"任务执行完成: {task.task_id}, 状态: {result.get('status')}")
            
        except asyncio.TimeoutError:
            logger.error(f"任务执行超时: {task.task_id}")
            await self.storage.save_execution_error(
                task=task,
                error=TimeoutError(f"任务执行超时（{self.config.task_timeout}秒）"),
                error_message=f"任务执行超时（{self.config.task_timeout}秒）"
            )
            self.metrics["total_failed"] += 1
            self.metrics["total_processed"] += 1
            
        except Exception as e:
            logger.error(f"任务执行失败: {task.task_id}, 错误: {e}")
            await self.storage.save_execution_error(task=task, error=e)
            self.metrics["total_failed"] += 1
            self.metrics["total_processed"] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        获取指标统计
        
        Returns:
            指标字典
        """
        metrics = self.metrics.copy()
        
        # 计算成功率
        if metrics["total_processed"] > 0:
            metrics["success_rate"] = metrics["total_succeeded"] / metrics["total_processed"]
        else:
            metrics["success_rate"] = 0.0
        
        # 计算运行时间
        if metrics["start_time"]:
            metrics["uptime_seconds"] = (
                datetime.now() - metrics["start_time"]
            ).total_seconds()
        else:
            metrics["uptime_seconds"] = 0.0
        
        # 添加队列长度信息
        metrics["queue_lengths"] = {}
        for queue_config in self.config.queues:
            # 这里需要异步获取，但为了简化，先返回空字典
            # 实际使用时可以通过异步方法获取
            metrics["queue_lengths"][queue_config.queue_name] = 0
        
        return metrics
    
    async def get_queue_stats(self) -> Dict[str, int]:
        """
        获取队列统计信息
        
        Returns:
            队列名称到长度的映射
        """
        stats = {}
        for queue_config in self.config.queues:
            length = await self.consumer.get_queue_length(queue_config.queue_name)
            stats[queue_config.queue_name] = length
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态字典
        """
        redis_healthy = await self.consumer.health_check()
        
        return {
            "healthy": redis_healthy and self._running,
            "redis_connected": redis_healthy,
            "pipeline_running": self._running,
            "worker_count": len(self._workers),
            "metrics": self.get_metrics()
        }

