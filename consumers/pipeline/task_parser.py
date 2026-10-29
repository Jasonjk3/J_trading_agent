#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
任务解析器
负责解析和验证从消息队列接收的任务
"""
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

from core.models.agent_models import Task, TaskStatus, TaskPriority
from core.component.registry.agent_registry import AgentRegistry


class TaskParser:
    """任务解析器"""
    
    def __init__(
        self,
        agent_registry: AgentRegistry,
        task_type_agent_mapping: Optional[Dict[str, str]] = None
    ):
        """
        初始化任务解析器
        
        Args:
            agent_registry: Agent注册中心
            task_type_agent_mapping: 任务类型到Agent ID的映射
        """
        self.agent_registry = agent_registry
        self.task_type_agent_mapping = task_type_agent_mapping or {}
    
    async def parse_message(self, message: Dict[str, Any]) -> Optional[Task]:
        """
        解析消息为Task对象
        
        Args:
            message: 消息字典
            
        Returns:
            Task对象，如果解析失败则返回None
        
        必填字段:
            - task_id: 任务唯一标识
            - task_type: 任务类型，用于路由到对应Agent
            - metadata: 元数据（可以为空对象）
        """
        try:
            # 提取必填字段
            task_id = message.get("task_id")
            if not task_id:
                logger.error("消息缺少task_id字段")
                return None
            
            task_type = message.get("task_type")
            if not task_type:
                logger.error(f"任务 {task_id} 缺少task_type字段")
                return None
            
            if "metadata" not in message:
                logger.error(f"任务 {task_id} 缺少metadata字段")
                return None
            
            # 提取可选字段
            content = message.get("content", "")  # content可选，默认为空字符串
            session_id = message.get("session_id", task_id)  # 如果没有session_id，使用task_id
            agent_id = message.get("agent_id")
            
            # 如果没有提供agent_id，尝试根据task_type查找
            if not agent_id and task_type:
                agent_id = self.task_type_agent_mapping.get(task_type)
                if not agent_id:
                    # 尝试根据task_type从注册中心查找Agent
                    agent_id = await self._find_agent_by_task_type(task_type)
            
            # 解析优先级
            priority = self._parse_priority(message.get("metadata", {}).get("priority"))
            
            # 创建Task对象
            task = Task(
                task_id=task_id,
                session_id=session_id,
                agent_id=agent_id,
                content=content,
                priority=priority,
                status=TaskStatus.QUEUED,
                metadata=message.get("metadata", {}),
                created_at=self._parse_datetime(message.get("created_at")) or datetime.now()
            )
            
            logger.debug(f"任务解析成功: {task_id}, agent_id: {agent_id}")
            return task
            
        except Exception as e:
            logger.error(f"解析任务消息失败: {e}, 消息: {message}")
            return None
    
    def _parse_priority(self, priority: Any) -> TaskPriority:
        """
        解析优先级
        
        Args:
            priority: 优先级值（可以是字符串或整数）
            
        Returns:
            TaskPriority枚举
        """
        if priority is None:
            return TaskPriority.NORMAL
        
        if isinstance(priority, int):
            try:
                return TaskPriority(priority)
            except ValueError:
                return TaskPriority.NORMAL
        
        if isinstance(priority, str):
            priority_map = {
                "low": TaskPriority.LOW,
                "normal": TaskPriority.NORMAL,
                "high": TaskPriority.HIGH,
                "urgent": TaskPriority.URGENT
            }
            return priority_map.get(priority.lower(), TaskPriority.NORMAL)
        
        return TaskPriority.NORMAL
    
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """
        解析日期时间字符串
        
        Args:
            dt_str: 日期时间字符串
            
        Returns:
            datetime对象
        """
        if not dt_str:
            return None
        
        try:
            if isinstance(dt_str, str):
                # 尝试ISO格式
                return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"解析日期时间失败: {dt_str}, 错误: {e}")
        
        return None
    
    async def _find_agent_by_task_type(self, task_type: str) -> Optional[str]:
        """
        根据任务类型查找Agent ID
        
        Args:
            task_type: 任务类型
            
        Returns:
            Agent ID，如果找不到则返回None
        """
        # 任务类型到Agent名称的映射
        task_type_to_agent_name = {
            "competitor_analysis": "竞品分析Agent",
            "chat": "智能助手",
            "feishu": "飞书助手"
        }
        
        agent_name = task_type_to_agent_name.get(task_type)
        if not agent_name:
            return None
        
        # 从注册中心查找Agent（异步调用）
        agents = await self.agent_registry.get_all_agents()
        for agent in agents:
            if agent.agent_name == agent_name:
                return agent.agent_id
        
        return None
    
    async def validate_task(self, task: Task) -> tuple[bool, Optional[str]]:
        """
        验证任务
        
        Args:
            task: Task对象
            
        Returns:
            (是否有效, 错误信息)
        """
        if not task.task_id:
            return False, "任务ID不能为空"
        
        if not task.session_id:
            return False, "会话ID不能为空"
        
        # 如果指定了agent_id，验证Agent是否存在
        if task.agent_id:
            agent = await self.agent_registry.get_agent(task.agent_id)
            if not agent:
                return False, f"Agent不存在: {task.agent_id}"
        else:
            return False, "未能根据task_type找到对应的Agent"
        
        return True, None

