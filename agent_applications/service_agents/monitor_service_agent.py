#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
监控服务 Agent 示例
这是一个简单的服务型 Agent 示例，用于演示 ServiceBaseAgent 的使用
"""
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime
from loguru import logger

from core.agent_base.service_base_agent import ServiceBaseAgent
from core.agent_mixin.service_agent_mixin import ServiceAgentMixin
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_models import LLMModels


class MonitorServiceAgent(ServiceAgentMixin, ServiceBaseAgent):
    """
    监控服务 Agent 示例
    
    这是一个简单的服务型 Agent，用于演示 ServiceBaseAgent 的使用。
    功能：
    - 持续运行，定期检查系统状态
    - 支持启动、停止、暂停、恢复
    - 支持定时任务（定期输出监控信息）
    """
    
    AGENT_TYPE = "monitor_service"
    DEFAULT_CAPABILITIES = ["monitoring", "status_check", "logging"]
    
    # 定义系统 Prompt（服务型 Agent 通常不需要 LLM，但这里作为示例保留）
    SYSTEM_PROMPT = """你是一个监控服务 Agent。
你的职责是持续监控系统状态，定期输出监控信息。"""
    
    # ==================== LLM 配置 ====================
    LLM_CONFIG = {
        "model_name": LLMModels.GPT_4O,
        "temperature": 0.7,
        "max_tokens": 2048,
        "api_key_env": LLMModels.OPENAI_API_KEY_ENV
    }
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "监控服务Agent",
        llm: Optional[BaseLLM] = None,
        monitor_interval: float = 10.0,  # 监控间隔（秒）
        **kwargs
    ):
        """
        初始化监控服务 Agent
        
        Args:
            agent_id: Agent ID
            agent_name: Agent 名称
            llm: LLM 实例（可选，服务型 Agent 可能不需要）
            monitor_interval: 监控间隔（秒）
            **kwargs: 其他参数
        """
        # 调用 ServiceBaseAgent 初始化
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=self.AGENT_TYPE,
            capabilities=self.DEFAULT_CAPABILITIES,
            max_concurrent_tasks=1,  # 服务型 Agent 通常为 1
            llm=llm,
            **kwargs
        )
        
        # 监控配置
        self.monitor_interval = monitor_interval
        self.monitor_count = 0
        self.last_check_time: Optional[datetime] = None
    
    async def initialize(self) -> bool:
        """初始化 Agent"""
        try:
            # 调用父类初始化
            result = await super().initialize()
            if not result:
                return False
            
            # 注册定时任务：定期输出监控信息
            self.register_scheduled_task(
                name="monitor_status",
                func=self._monitor_status,
                interval=self.monitor_interval,
                enabled=True
            )
            
            # 设置配置
            self.set_config("monitor_interval", self.monitor_interval)
            self.set_config("started_at", datetime.now().isoformat())
            
            logger.info(f"监控服务 Agent 初始化成功: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"监控服务 Agent 初始化失败: {e}", exc_info=True)
            from core.models.agent_models import AgentStatus
            await self.update_status(AgentStatus.ERROR)
            return False
    
    async def cleanup(self) -> bool:
        """清理资源"""
        try:
            # 停止服务（如果正在运行）
            if self.is_running:
                await self.stop()
            
            # 调用父类清理
            result = await super().cleanup()
            
            logger.info(f"监控服务 Agent 清理完成: {self.agent_id}")
            return result
        except Exception as e:
            logger.error(f"监控服务 Agent 清理失败: {e}", exc_info=True)
            return False
    
    # ==================== 服务主循环实现 ====================
    
    async def _run_service_loop(self) -> None:
        """
        运行服务主循环（ServiceBaseAgent 要求实现）
        
        这是服务型 Agent 的核心方法，实现持续运行的业务逻辑。
        """
        logger.info(f"监控服务 Agent 主循环已启动: {self.agent_id}")
        
        while self.is_running:
            try:
                # 如果暂停，等待恢复
                if self.is_paused:
                    await asyncio.sleep(1)
                    continue
                
                # 主循环逻辑（这里只是示例，实际业务逻辑在定时任务中）
                # 服务型 Agent 的主要工作通常由定时任务完成
                await asyncio.sleep(1)  # 避免 CPU 占用过高
                
            except asyncio.CancelledError:
                logger.info(f"监控服务 Agent 主循环已取消: {self.agent_id}")
                break
            except Exception as e:
                logger.error(f"监控服务 Agent 主循环错误: {e}", exc_info=True)
                await asyncio.sleep(5)  # 错误后等待一段时间再继续
        
        logger.info(f"监控服务 Agent 主循环已退出: {self.agent_id}")
    
    # ==================== 定时任务实现 ====================
    
    async def _monitor_status(self) -> None:
        """
        监控状态任务（定时执行）
        
        定期输出监控信息，演示定时任务的使用。
        """
        try:
            self.monitor_count += 1
            self.last_check_time = datetime.now()
            
            # 获取 Agent 状态信息
            status_value = self.status.value if hasattr(self, 'status') and self.status else "unknown"
            started_at_str = self.get_config("started_at")
            uptime_seconds = 0
            if started_at_str:
                try:
                    started_at = datetime.fromisoformat(started_at_str)
                    uptime_seconds = (self.last_check_time - started_at).total_seconds()
                except Exception:
                    pass
            
            status_info = {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "status": status_value,
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "monitor_count": self.monitor_count,
                "last_check_time": self.last_check_time.isoformat(),
                "uptime_seconds": uptime_seconds
            }
            
            # 输出监控信息（实际应用中可以发送到监控系统、写入日志等）
            logger.info(f"监控服务 Agent 状态检查 #{self.monitor_count}: {status_info}")
            
            # 更新配置
            self.set_config("last_monitor_info", status_info)
            self.set_config("monitor_count", self.monitor_count)
            
        except Exception as e:
            logger.error(f"监控状态任务执行失败: {e}", exc_info=True)
    
    # ==================== 系统 Prompt ====================
    
    def _get_system_prompt(self) -> str:
        """获取系统 Prompt"""
        return self.SYSTEM_PROMPT

