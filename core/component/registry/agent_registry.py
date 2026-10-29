#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Agent注册中心
管理智能体的注册、发现和生命周期
"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from core.agent_base.base_agent import BaseAgent
from core.models.agent_models import AgentInfo, AgentStatus


class AgentRegistry:
    """智能体注册中心"""

    def __init__(self, heartbeat_timeout_seconds: int = 60):
        """
        初始化注册中心

        Args:
            heartbeat_timeout_seconds: 心跳超时时间（秒）
        """
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._agents: Dict[str, BaseAgent] = {}  # 智能体存储
        self._lock = asyncio.Lock()  # 操作锁
        self._monitor_task: Optional[asyncio.Task] = None

    async def register(self, agent: BaseAgent) -> bool:
        """
        注册智能体

        Args:
            agent: 智能体实例

        Returns:
            是否注册成功
        """
        async with self._lock:
            if agent.agent_id in self._agents:
                logger.warning(f"智能体已存在: {agent.agent_id}")
                return False

            # 初始化智能体
            try:
                success = await agent.initialize()
                if not success:
                    logger.error(f"智能体初始化失败: {agent.agent_id}")
                    return False
            except Exception as e:
                logger.error(f"智能体初始化异常: {agent.agent_id}, 错误: {e}")
                return False

            self._agents[agent.agent_id] = agent
            logger.info(f"智能体已注册: {agent.agent_id} ({agent.agent_name})")
            return True

    async def unregister(self, agent_id: str) -> bool:
        """
        注销智能体

        Args:
            agent_id: 智能体ID

        Returns:
            是否注销成功
        """
        async with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                logger.warning(f"智能体不存在: {agent_id}")
                return False

            # 清理资源
            try:
                await agent.cleanup()
            except Exception as e:
                logger.error(f"智能体清理异常: {agent_id}, 错误: {e}")

            del self._agents[agent_id]
            logger.info(f"智能体已注销: {agent_id}")
            return True

    async def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        获取智能体

        Args:
            agent_id: 智能体ID

        Returns:
            智能体实例
        """
        return self._agents.get(agent_id)

    async def get_all_agents(self) -> List[BaseAgent]:
        """
        获取所有智能体

        Returns:
            智能体列表
        """
        return list(self._agents.values())

    async def get_available_agents(
        self,
        agent_type: Optional[str] = None,
        capabilities: Optional[List[str]] = None
    ) -> List[BaseAgent]:
        """
        获取可用的智能体

        Args:
            agent_type: 智能体类型过滤
            capabilities: 所需能力列表

        Returns:
            可用智能体列表
        """
        available = []
        for agent in self._agents.values():
            # 检查状态：如果处于错误或离线状态，不可用
            if agent.status == AgentStatus.ERROR or agent.status == AgentStatus.OFFLINE:
                continue

            # 检查并发数：只要当前任务数未达到上限，就可以接受新任务
            # 状态可以是 BUSY（有任务在执行）或 IDLE（没有任务），都可以接受新任务
            if agent.current_tasks >= agent.max_concurrent_tasks:
                continue

            # 检查类型
            if agent_type and agent.agent_type != agent_type:
                continue

            # 检查能力
            if capabilities:
                if not all(cap in agent.capabilities for cap in capabilities):
                    continue

            available.append(agent)

        return available

    async def find_agent_by_capability(self, capability: str) -> List[BaseAgent]:
        """
        根据能力查找智能体

        Args:
            capability: 能力名称

        Returns:
            智能体列表
        """
        return [
            agent for agent in self._agents.values()
            if capability in agent.capabilities
        ]

    async def update_heartbeat(self, agent_id: str) -> bool:
        """
        更新智能体心跳

        Args:
            agent_id: 智能体ID

        Returns:
            是否更新成功
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        await agent.update_heartbeat()
        return True

    async def check_heartbeat(self) -> List[str]:
        """
        检查心跳，返回超时的智能体ID列表

        Returns:
            超时的智能体ID列表
        """
        timeout_agents = []
        now = datetime.now()

        async with self._lock:
            for agent_id, agent in self._agents.items():
                time_since_heartbeat = (now - agent.last_heartbeat).total_seconds()
                if time_since_heartbeat > self.heartbeat_timeout_seconds:
                    timeout_agents.append(agent_id)
                    # 标记为离线
                    await agent.update_status(AgentStatus.OFFLINE)
                    logger.warning(f"智能体心跳超时: {agent_id}, 超时时间: {time_since_heartbeat:.2f}秒")

        return timeout_agents

    async def start_monitor(self, interval_seconds: int = 60):
        """
        启动心跳监控任务

        Args:
            interval_seconds: 检查间隔（秒）
        """
        if self._monitor_task and not self._monitor_task.done():
            return

        async def monitor_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    timeout_agents = await self.check_heartbeat()
                    if timeout_agents:
                        logger.warning(f"检测到 {len(timeout_agents)} 个心跳超时的智能体")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"心跳监控任务出错: {e}")

        self._monitor_task = asyncio.create_task(monitor_loop())
        logger.info("智能体心跳监控任务已启动")

    async def stop_monitor(self):
        """停止心跳监控任务"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("智能体心跳监控任务已停止")

    async def get_stats(self) -> Dict:
        """
        获取注册中心统计信息

        Returns:
            统计信息字典
        """
        async with self._lock:
            total = len(self._agents)
            status_count = {}
            for agent in self._agents.values():
                status = agent.status.value
                status_count[status] = status_count.get(status, 0) + 1

            return {
                "total_agents": total,
                "status_distribution": status_count,
                "heartbeat_timeout": self.heartbeat_timeout_seconds
            }

    async def get_agent_info(self, agent_id: str) -> Optional[AgentInfo]:
        """
        获取智能体信息

        Args:
            agent_id: 智能体ID

        Returns:
            AgentInfo对象
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        return agent.to_info()

    async def get_all_agents_info(self) -> List[AgentInfo]:
        """
        获取所有智能体信息

        Returns:
            AgentInfo列表
        """
        return [agent.to_info() for agent in self._agents.values()]

