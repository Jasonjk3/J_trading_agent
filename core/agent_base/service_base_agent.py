#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
服务型 Agent 基类
继承 BaseAgent，为服务型 Agent（持续运行）提供标准化的基础实现
注意：Mixin 由 Agent 自己继承，不混进 Base 类里
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from uuid import uuid4
from loguru import logger

from core.agent_base.base_agent import BaseAgent
from core.models.agent_models import AgentStatus
from core.llm.base.base_llm import BaseLLM


class ServiceBaseAgent(BaseAgent, ABC):
    """
    服务型 Agent 基类
    
    继承自 BaseAgent，为服务型 Agent（持续运行的服务）提供标准化的基础实现。
    注意：Mixin（如 ServiceAgentMixin）由 Agent 自己继承，不混进 Base 类里。
    
    服务型 Agent 特点：
    - 持续运行（24小时）
    - 可暂停/恢复
    - 支持定时任务/轮询
    - 状态持久化
    
    使用方式：
    1. 继承 ServiceBaseAgent + ServiceAgentMixin（或其他需要的 Mixin）
    2. 定义类属性：AGENT_TYPE, DEFAULT_CAPABILITIES
    3. 实现系统 Prompt（_get_system_prompt() 或 SYSTEM_PROMPT 类属性）
    4. 实现必需的方法（见下方说明）
    
    示例：
    ```python
    class MyServiceAgent(ServiceAgentMixin, ServiceBaseAgent):
        AGENT_TYPE = "my_service"
        DEFAULT_CAPABILITIES = ["monitoring", "automation"]
        
        SYSTEM_PROMPT = "你是一个服务型Agent..."
        
        def __init__(self, llm: BaseLLM, **kwargs):
            super().__init__(
                agent_name="我的服务Agent",
                agent_type=self.AGENT_TYPE,
                capabilities=self.DEFAULT_CAPABILITIES,
                llm=llm,
                **kwargs
            )
        
        async def _run_service_loop(self):
            # 实现服务主循环
            while self.is_running:
                # 业务逻辑
                await asyncio.sleep(1)
    ```
    """
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "服务型Agent",
        agent_type: Optional[str] = None,
        capabilities: Optional[list] = None,
        max_concurrent_tasks: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
        llm: Optional[BaseLLM] = None,
        **kwargs
    ):
        """
        初始化服务型 Agent
        
        Args:
            agent_id: Agent ID（自动生成）
            agent_name: Agent 名称
            agent_type: Agent 类型（如果未提供，使用类的 AGENT_TYPE）
            capabilities: 能力列表（如果未提供，使用类的 DEFAULT_CAPABILITIES）
            max_concurrent_tasks: 最大并发任务数（服务型 Agent 通常为 1）
            metadata: 元数据
            **kwargs: 其他参数
        """
        agent_id = agent_id or str(uuid4())
        
        # 使用类属性作为默认值
        if agent_type is None:
            agent_type = getattr(self.__class__, 'AGENT_TYPE', 'service_agent')
        if capabilities is None:
            capabilities = getattr(self.__class__, 'DEFAULT_CAPABILITIES', ['service', 'automation'])
        
        # 调用 BaseAgent 初始化
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            capabilities=capabilities,
            max_concurrent_tasks=max_concurrent_tasks,
            metadata=metadata or {}
        )
        
        # 保留外部注入的 LLM；未注入时再由子类/initialize 走默认创建逻辑
        self.llm: Optional[BaseLLM] = llm
        
        # 服务型 Agent 特有属性（由 ServiceAgentMixin 管理）
        # 这些属性在 Mixin 中初始化，这里只是声明
        self.is_running: bool = False
        self.is_paused: bool = False
        self._service_task: Optional[Any] = None  # asyncio.Task
        
        # 构建系统 Prompt
        self.system_prompt = self._build_system_prompt()
    
    async def initialize(self) -> bool:
        """
        初始化 Agent（标准实现）
        
        子类可以覆盖此方法添加特定的初始化逻辑，但应调用 super().initialize()
        """
        try:
            # 确保LLM已初始化（使用BaseAgent的_get_llm方法）
            if not self._get_llm():
                logger.error(f"{self.__class__.__name__}创建LLM实例失败")
                await self.update_status(AgentStatus.ERROR)
                return False
            
            # 更新系统 Prompt（确保是最新的）
            self.system_prompt = self._build_system_prompt()
            
            # 服务型 Agent 初始状态为 STOPPED
            await self.update_status(AgentStatus.STOPPED)
            
            logger.info(f"{self.__class__.__name__}初始化成功: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"{self.__class__.__name__}初始化失败: {e}", exc_info=True)
            await self.update_status(AgentStatus.ERROR)
            return False
    
    async def cleanup(self) -> bool:
        """
        清理资源（标准实现）
        
        子类可以覆盖此方法添加特定的清理逻辑，但应调用 super().cleanup()
        """
        try:
            # 停止服务（如果正在运行且 Mixin 提供了 stop 方法）
            if hasattr(self, 'is_running') and self.is_running:
                if hasattr(self, 'stop'):
                    await self.stop()
            
            # 更新状态为 OFFLINE
            await self.update_status(AgentStatus.OFFLINE)
            
            logger.info(f"{self.__class__.__name__}清理完成: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"{self.__class__.__name__}清理失败: {e}", exc_info=True)
            return False
    
    async def execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        服务型 Agent 的标准执行流程
        
        服务型 Agent 的 execute() 主要用于：
        1. 启动服务（task.action = "start"）
        2. 停止服务（task.action = "stop"）
        3. 暂停服务（task.action = "pause"）
        4. 恢复服务（task.action = "resume"）
        5. 获取状态（task.action = "status"）
        6. 更新配置（task.action = "config"）
        
        注意：此方法在 Base 类中实现标准流程，具体功能由 ServiceAgentMixin 提供。
        如果未继承 ServiceAgentMixin，某些操作可能不可用。
        
        Args:
            task: 任务内容，应包含 action 字段
            context: 上下文信息
            
        Returns:
            执行结果
        """
        action = task.get("action", "").lower()
        
        try:
            # 1. 预处理 (调用 BaseAgent 钩子)
            if not await self._pre_execute(task, context):
                return self._handle_error_internal("任务预处理失败", task)
            
            # 2. 根据 action 路由到对应的处理方法
            if action == "start":
                if not hasattr(self, 'start'):
                    return self._handle_error_internal("start 方法不可用，请继承 ServiceAgentMixin", task)
                success = await self.start()
                return {
                    "success": success,
                    "action": "start",
                    "status": self.status.value,
                    "agent_id": self.agent_id
                }
            
            elif action == "stop":
                if not hasattr(self, 'stop'):
                    return self._handle_error_internal("stop 方法不可用，请继承 ServiceAgentMixin", task)
                success = await self.stop()
                return {
                    "success": success,
                    "action": "stop",
                    "status": self.status.value,
                    "agent_id": self.agent_id
                }
            
            elif action == "pause":
                if not hasattr(self, 'pause'):
                    return self._handle_error_internal("pause 方法不可用，请继承 ServiceAgentMixin", task)
                success = await self.pause()
                return {
                    "success": success,
                    "action": "pause",
                    "status": self.status.value,
                    "agent_id": self.agent_id
                }
            
            elif action == "resume":
                if not hasattr(self, 'resume'):
                    return self._handle_error_internal("resume 方法不可用，请继承 ServiceAgentMixin", task)
                success = await self.resume()
                return {
                    "success": success,
                    "action": "resume",
                    "status": self.status.value,
                    "agent_id": self.agent_id
                }
            
            elif action == "status":
                # 状态查询不需要 Mixin，可以直接返回
                status_info = {
                    "success": True,
                    "action": "status",
                    "status": self.status.value,
                    "agent_id": self.agent_id
                }
                
                # 如果 Mixin 提供了额外信息，添加到结果中
                if hasattr(self, 'is_running'):
                    status_info["is_running"] = self.is_running
                if hasattr(self, 'is_paused'):
                    status_info["is_paused"] = self.is_paused
                if hasattr(self, '_scheduled_tasks'):
                    status_info["scheduled_tasks"] = {
                        name: {
                            "enabled": task.enabled,
                            "interval": task.interval,
                            "last_run": task.last_run.isoformat() if task.last_run else None,
                            "next_run": task.next_run.isoformat() if task.next_run else None
                        }
                        for name, task in self._scheduled_tasks.items()
                    }
                
                return status_info
            
            elif action == "config":
                if not hasattr(self, 'update_config') or not hasattr(self, 'get_all_config'):
                    return self._handle_error_internal("config 方法不可用，请继承 ServiceAgentMixin", task)
                
                config = task.get("config", {})
                if config:
                    self.update_config(config)
                    return {
                        "success": True,
                        "action": "config",
                        "message": "配置已更新",
                        "agent_id": self.agent_id
                    }
                else:
                    return {
                        "success": True,
                        "action": "config",
                        "config": self.get_all_config(),
                        "agent_id": self.agent_id
                    }
            
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作: {action}",
                    "supported_actions": ["start", "stop", "pause", "resume", "status", "config"],
                    "agent_id": self.agent_id
                }
                
        except Exception as e:
            logger.error(f"执行服务控制任务失败: {e}", exc_info=True)
            return await self._handle_error(e, task, context)
    
    def _handle_error_internal(self, error_msg: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """内部错误处理助手"""
        from core.agent_mixin.mixin_utils import build_agent_result
        return build_agent_result(
            self,
            success=False,
            error=error_msg,
            task_id=task.get("task_id")
        )
    
    # ==================== 抽象方法（子类必须实现）====================
    
    @abstractmethod
    async def _run_service_loop(self) -> None:
        """
        运行服务主循环（子类必须实现）
        
        这是服务型 Agent 的核心方法，实现持续运行的业务逻辑。
        方法应该是一个无限循环，直到 is_running 为 False。
        
        注意：
        - 在循环中应检查 is_paused 状态，如果暂停则等待
        - 应定期检查 is_running 状态，如果为 False 则退出循环
        - 应处理异常，避免服务崩溃
        
        示例：
        ```python
        async def _run_service_loop(self):
            while self.is_running:
                if self.is_paused:
                    await asyncio.sleep(1)
                    continue
                
                try:
                    # 业务逻辑
                    await self._do_work()
                except Exception as e:
                    logger.error(f"服务循环错误: {e}")
                
                await asyncio.sleep(1)  # 避免 CPU 占用过高
        ```
        """
        pass
    
    def _get_system_prompt(self) -> str:
        """
        获取系统 Prompt（继承 BaseAgent 的实现）
        
        子类必须（二选一）：
        1. 定义 SYSTEM_PROMPT 类属性（字符串）- 推荐方式
        2. 或覆盖此方法返回系统 Prompt
        
        Returns:
            系统 Prompt 字符串
        """
        # 调用父类实现（BaseAgent 已经提供了完整的实现逻辑）
        return super()._get_system_prompt()

