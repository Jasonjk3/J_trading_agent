#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
监控服务业务逻辑
处理监控服务相关的业务逻辑
"""
from typing import Dict, Any
from loguru import logger

from core.component.registry.agent_registry import AgentRegistry
from app.v1.schemas.service_monitor_schema import (
    ServiceMonitorRequest
)


class ServiceMonitorService:
    """监控服务业务逻辑"""

    def __init__(
        self,
        agent_registry: AgentRegistry
    ):
        """
        初始化监控服务

        Args:
            agent_registry: 智能体注册中心
        """
        self.agent_registry = agent_registry

    async def control(
        self,
        request: ServiceMonitorRequest
    ) -> Dict[str, Any]:
        """
        控制监控服务（启动、停止、暂停、恢复、获取状态、更新配置）

        Args:
            request: 监控服务请求

        Returns:
            监控服务响应
        """
        try:
            # 获取监控服务 Agent
            agents = await self.agent_registry.get_available_agents(
                agent_type="monitor_service"
            )
            
            if not agents:
                logger.error("监控服务 Agent 不可用")
                return {
                    "success": False,
                    "error": "监控服务 Agent 不可用，请检查服务配置",
                    "action": request.action
                }
            
            monitor_agent = agents[0]
            logger.info(f"使用监控服务 Agent: {monitor_agent.agent_id}")
            
            # 构建任务
            task = {
                "action": request.action
            }
            
            # 如果是配置操作，添加配置信息
            if request.action == "config" and request.config:
                task["config"] = request.config
            
            logger.info(f"执行监控服务操作: action={request.action}, agent_id={monitor_agent.agent_id}")
            
            # 执行操作
            result = await monitor_agent.execute(task)
            
            # 确保返回结果包含 success 字段
            if "success" not in result:
                result["success"] = True
            
            logger.info(f"监控服务操作完成: action={request.action}, success={result.get('success')}")
            
            return result
            
        except Exception as e:
            logger.error(f"监控服务执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"处理请求失败: {str(e)}",
                "action": request.action
            }

