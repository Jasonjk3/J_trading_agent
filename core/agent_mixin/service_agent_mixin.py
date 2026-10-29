#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
服务型 Agent Mixin
提供持续运行、定时任务调度、状态控制等功能
"""
import asyncio
from typing import Any, Dict, Optional, Callable, List
from datetime import datetime, timedelta
from loguru import logger

from core.models.agent_models import AgentStatus


class ScheduledTask:
    """定时任务定义"""
    
    def __init__(
        self,
        name: str,
        func: Callable,
        interval: float,  # 执行间隔（秒）
        enabled: bool = True,
        last_run: Optional[datetime] = None,
        next_run: Optional[datetime] = None
    ):
        self.name = name
        self.func = func
        self.interval = interval
        self.enabled = enabled
        self.last_run = last_run
        self.next_run = next_run or datetime.now()
    
    def update_next_run(self):
        """更新下次执行时间"""
        self.last_run = datetime.now()
        self.next_run = self.last_run + timedelta(seconds=self.interval)


class ServiceAgentMixin:
    """
    服务型 Agent Mixin
    
    提供以下功能：
    - 服务生命周期管理（启动、停止、暂停、恢复）
    - 定时任务调度
    - 状态控制
    - 配置管理
    
    使用方式：
    ```python
    class MyServiceAgent(ServiceAgentMixin, ServiceBaseAgent):
        async def initialize(self):
            result = await super().initialize()
            if result:
                # 注册定时任务
                self.register_scheduled_task(
                    name="market_data",
                    func=self._fetch_market_data,
                    interval=60.0  # 每60秒执行一次
                )
            return result
        
        async def _fetch_market_data(self):
            # 获取市场数据
            pass
    ```
    """
    
    def __init__(self, *args, **kwargs):
        """
        初始化服务型 Agent Mixin
        
        注意：此方法会被多重继承调用，应使用 super() 调用父类初始化
        """
        # 服务状态
        self.is_running: bool = False
        self.is_paused: bool = False
        self._service_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # 定时任务管理
        self._scheduled_tasks: Dict[str, ScheduledTask] = {}
        
        # 配置管理
        self._config: Dict[str, Any] = {}
        
        # 事件监听器
        self._event_listeners: Dict[str, List[Callable]] = {}
        
        # 调用父类初始化（如果存在）
        if hasattr(super(), '__init__'):
            super().__init__(*args, **kwargs)
    
    # ==================== 服务生命周期管理 ====================
    
    async def start(self) -> bool:
        """
        启动服务
        
        Returns:
            是否启动成功
        """
        if self.is_running:
            logger.warning(f"Agent {getattr(self, 'agent_id', 'unknown')} 已经在运行中")
            return True
        
        try:
            # 更新状态
            await self.update_status(AgentStatus.RUNNING)
            self.is_running = True
            self.is_paused = False
            
            # 启动服务主循环
            self._service_task = asyncio.create_task(self._run_service_loop())
            
            # 启动定时任务调度器
            self._scheduler_task = asyncio.create_task(self._run_scheduler())
            
            logger.info(f"Agent {getattr(self, 'agent_id', 'unknown')} 服务已启动")
            await self._emit_event("started", {})
            return True
            
        except Exception as e:
            logger.error(f"启动服务失败: {e}", exc_info=True)
            await self.update_status(AgentStatus.ERROR)
            self.is_running = False
            return False
    
    async def stop(self) -> bool:
        """
        停止服务
        
        Returns:
            是否停止成功
        """
        if not self.is_running:
            logger.warning(f"Agent {getattr(self, 'agent_id', 'unknown')} 未在运行")
            return True
        
        try:
            # 更新状态
            self.is_running = False
            self.is_paused = False
            
            # 取消服务任务
            if self._service_task and not self._service_task.done():
                self._service_task.cancel()
                try:
                    await self._service_task
                except asyncio.CancelledError:
                    pass
            
            # 取消调度器任务
            if self._scheduler_task and not self._scheduler_task.done():
                self._scheduler_task.cancel()
                try:
                    await self._scheduler_task
                except asyncio.CancelledError:
                    pass
            
            # 更新状态
            await self.update_status(AgentStatus.STOPPED)
            
            logger.info(f"Agent {getattr(self, 'agent_id', 'unknown')} 服务已停止")
            await self._emit_event("stopped", {})
            return True
            
        except Exception as e:
            logger.error(f"停止服务失败: {e}", exc_info=True)
            return False
    
    async def pause(self) -> bool:
        """
        暂停服务（保持连接，不执行任务）
        
        Returns:
            是否暂停成功
        """
        if not self.is_running:
            logger.warning(f"Agent {getattr(self, 'agent_id', 'unknown')} 未在运行，无法暂停")
            return False
        
        if self.is_paused:
            logger.warning(f"Agent {getattr(self, 'agent_id', 'unknown')} 已经暂停")
            return True
        
        try:
            self.is_paused = True
            await self.update_status(AgentStatus.PAUSED)
            
            logger.info(f"Agent {getattr(self, 'agent_id', 'unknown')} 服务已暂停")
            await self._emit_event("paused", {})
            return True
            
        except Exception as e:
            logger.error(f"暂停服务失败: {e}", exc_info=True)
            return False
    
    async def resume(self) -> bool:
        """
        恢复服务（从暂停状态恢复）
        
        Returns:
            是否恢复成功
        """
        if not self.is_running:
            logger.warning(f"Agent {getattr(self, 'agent_id', 'unknown')} 未在运行，无法恢复")
            return False
        
        if not self.is_paused:
            logger.warning(f"Agent {getattr(self, 'agent_id', 'unknown')} 未暂停，无需恢复")
            return True
        
        try:
            self.is_paused = False
            await self.update_status(AgentStatus.RUNNING)
            
            logger.info(f"Agent {getattr(self, 'agent_id', 'unknown')} 服务已恢复")
            await self._emit_event("resumed", {})
            return True
            
        except Exception as e:
            logger.error(f"恢复服务失败: {e}", exc_info=True)
            return False
    
    # ==================== 定时任务调度 ====================
    
    def register_scheduled_task(
        self,
        name: str,
        func: Callable,
        interval: float,
        enabled: bool = True
    ) -> bool:
        """
        注册定时任务
        
        Args:
            name: 任务名称
            func: 任务函数（异步函数）
            interval: 执行间隔（秒）
            enabled: 是否启用
            
        Returns:
            是否注册成功
        """
        if name in self._scheduled_tasks:
            logger.warning(f"定时任务 {name} 已存在，将被覆盖")
        
        task = ScheduledTask(
            name=name,
            func=func,
            interval=interval,
            enabled=enabled
        )
        
        self._scheduled_tasks[name] = task
        logger.info(f"注册定时任务: {name}, 间隔: {interval}秒")
        return True
    
    def unregister_scheduled_task(self, name: str) -> bool:
        """
        注销定时任务
        
        Args:
            name: 任务名称
            
        Returns:
            是否注销成功
        """
        if name not in self._scheduled_tasks:
            logger.warning(f"定时任务 {name} 不存在")
            return False
        
        del self._scheduled_tasks[name]
        logger.info(f"注销定时任务: {name}")
        return True
    
    def enable_scheduled_task(self, name: str) -> bool:
        """启用定时任务"""
        if name not in self._scheduled_tasks:
            logger.warning(f"定时任务 {name} 不存在")
            return False
        
        self._scheduled_tasks[name].enabled = True
        logger.info(f"启用定时任务: {name}")
        return True
    
    def disable_scheduled_task(self, name: str) -> bool:
        """禁用定时任务"""
        if name not in self._scheduled_tasks:
            logger.warning(f"定时任务 {name} 不存在")
            return False
        
        self._scheduled_tasks[name].enabled = False
        logger.info(f"禁用定时任务: {name}")
        return True
    
    async def _run_scheduler(self):
        """运行定时任务调度器"""
        logger.info("定时任务调度器已启动")
        
        while self.is_running:
            try:
                if not self.is_paused:
                    # 检查所有定时任务
                    now = datetime.now()
                    for task in self._scheduled_tasks.values():
                        if not task.enabled:
                            continue
                        
                        # 检查是否到了执行时间
                        if now >= task.next_run:
                            try:
                                # 执行任务
                                if asyncio.iscoroutinefunction(task.func):
                                    await task.func()
                                else:
                                    task.func()
                                
                                # 更新下次执行时间
                                task.update_next_run()
                                
                                logger.debug(f"定时任务 {task.name} 执行完成")
                                
                            except Exception as e:
                                logger.error(f"定时任务 {task.name} 执行失败: {e}", exc_info=True)
                
                # 等待一小段时间再检查（避免 CPU 占用过高）
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                logger.info("定时任务调度器已停止")
                break
            except Exception as e:
                logger.error(f"定时任务调度器错误: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    # ==================== 配置管理 ====================
    
    def set_config(self, key: str, value: Any) -> None:
        """设置配置项"""
        self._config[key] = value
        logger.debug(f"设置配置: {key} = {value}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)
    
    def update_config(self, config: Dict[str, Any]) -> None:
        """批量更新配置"""
        self._config.update(config)
        logger.debug(f"更新配置: {len(config)} 项")
    
    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()
    
    # ==================== 事件监听 ====================
    
    def add_event_listener(self, event: str, listener: Callable) -> None:
        """
        添加事件监听器
        
        Args:
            event: 事件名称（如 "started", "stopped", "paused", "resumed"）
            listener: 监听器函数（异步函数）
        """
        if event not in self._event_listeners:
            self._event_listeners[event] = []
        
        self._event_listeners[event].append(listener)
        logger.debug(f"添加事件监听器: {event}")
    
    def remove_event_listener(self, event: str, listener: Callable) -> None:
        """移除事件监听器"""
        if event in self._event_listeners:
            if listener in self._event_listeners[event]:
                self._event_listeners[event].remove(listener)
                logger.debug(f"移除事件监听器: {event}")
    
    async def _emit_event(self, event: str, data: Dict[str, Any]) -> None:
        """触发事件"""
        if event in self._event_listeners:
            for listener in self._event_listeners[event]:
                try:
                    if asyncio.iscoroutinefunction(listener):
                        await listener(data)
                    else:
                        listener(data)
                except Exception as e:
                    logger.error(f"事件监听器 {event} 执行失败: {e}", exc_info=True)
    

