#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
任务式 Agent 基类
继承 BaseAgent，为任务式 Agent 提供标准化的基础实现
注意：Mixin 由 Agent 自己继承，不混进 Base 类里
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from uuid import uuid4
from loguru import logger

from core.agent_base.base_agent import BaseAgent
from core.models.agent_models import AgentStatus
from core.llm.base.base_llm import BaseLLM


class TaskBaseAgent(BaseAgent, ABC):
    """
    任务式 Agent 基类
    
    继承自 BaseAgent，为任务式 Agent 提供标准化的基础实现。
    注意：Mixin（如 TaskAgentMixin）由 Agent 自己继承，不混进 Base 类里。
    
    使用方式：
    1. 继承 TaskBaseAgent + TaskAgentMixin（或其他需要的 Mixin）
    2. 定义类属性：AGENT_TYPE, DEFAULT_CAPABILITIES
    3. 实现必需的方法（见下方说明）
    4. 定义系统 Prompt（_get_system_prompt() 或 SYSTEM_PROMPT 类属性）
    
    示例：
    ```python
    class MyTaskAgent(TaskAgentMixin, TaskBaseAgent):
        AGENT_TYPE = "my_task"
        DEFAULT_CAPABILITIES = ["processing"]
        
        SYSTEM_PROMPT = "你是一个任务处理助手..."
        
        def __init__(self, llm: BaseLLM, **kwargs):
            super().__init__(
                agent_name="我的任务Agent",
                agent_type=self.AGENT_TYPE,
                capabilities=self.DEFAULT_CAPABILITIES,
                llm=llm,
                **kwargs
            )
        
        # 实现 TaskBaseAgent 要求的抽象方法
        def _validate_task(self, task: Dict[str, Any]) -> bool:
            return "input" in task
        
        def _extract_task_params(self, task: Dict[str, Any]) -> Dict[str, Any]:
            return {"input": task.get("input")}
        
        def _build_user_input_prompt(self, params, context=None):
            return f"处理：{params.get('input')}"
        
        def _parse_llm_response(self, response, params, context=None):
            return {"result": response}
        
        # 实现执行方法（选择一种或两种模式）
        async def _execute_normal_mode(self, params, context=None):
            # 普通模式业务逻辑
            user_message = self._build_user_input_prompt(params, context)
            messages = self._build_messages(user_message, include_system_prompt=True)
            llm_response = await self._call_llm_with_messages(messages)
            return self._parse_llm_response(llm_response, params, context)
    ```
    """
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "任务式Agent",
        agent_type: Optional[str] = None,
        capabilities: Optional[list] = None,
        max_concurrent_tasks: int = 10,
        metadata: Optional[Dict[str, Any]] = None,
        llm: Optional[BaseLLM] = None,
        **kwargs
    ):
        """
        初始化任务式 Agent
        
        Args:
            agent_id: Agent ID（自动生成）
            agent_name: Agent 名称
            agent_type: Agent 类型（如果未提供，使用类的 AGENT_TYPE）
            capabilities: 能力列表（如果未提供，使用类的 DEFAULT_CAPABILITIES）
            max_concurrent_tasks: 最大并发任务数
            metadata: 元数据
            **kwargs: 其他参数
        """
        agent_id = agent_id or str(uuid4())
        
        # 使用类属性作为默认值
        if agent_type is None:
            agent_type = getattr(self.__class__, 'AGENT_TYPE', 'task_agent')
        if capabilities is None:
            capabilities = getattr(self.__class__, 'DEFAULT_CAPABILITIES', ['task_processing'])
        
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
            
            await self.update_status(AgentStatus.IDLE)
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
            await self.update_status(AgentStatus.IDLE)
            return True
        except Exception as e:
            logger.error(f"{self.__class__.__name__}清理失败: {e}")
            return False
    
    async def execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        任务式 Agent 的标准执行流程
        实现 BaseAgent.execute 接口
        """
        try:
            # 1. 预处理 (调用 BaseAgent 钩子)
            if not await self._pre_execute(task, context):
                return self._handle_error_internal("任务预处理失败", task)

            # 2. 验证任务
            if not self._validate_task(task):
                return self._handle_error_internal("任务格式验证失败", task)

            # 3. 提取参数
            params = self._extract_task_params(task)
            
            # 4. 执行业务逻辑 (支持思维模式路由)
            result = await self._process_task_with_routing(params, context)
            
            # 5. 格式化结果
            from core.agent_mixin.mixin_utils import build_agent_result
            if isinstance(result, dict):
                # 准备参数，优先使用 result 中的值，避免重复传递导致 TypeError
                res_copy = result.copy()
                res_success = res_copy.pop("success", True)
                res_task_id = res_copy.pop("task_id", task.get("task_id"))
                res_response = res_copy.pop("response", None)
                res_error = res_copy.pop("error", None)
                res_session_id = res_copy.pop("session_id", None)
                
                formatted_result = build_agent_result(
                    self, 
                    success=res_success, 
                    task_id=res_task_id,
                    response=res_response,
                    error=res_error,
                    session_id=res_session_id,
                    **res_copy
                )
            else:
                formatted_result = build_agent_result(self, success=True, response=result, task_id=task.get("task_id"))
            
            # 6. 执行后钩子
            return await self._post_execute(formatted_result, task, context)

        except Exception as e:
            logger.error(f"任务执行异常: {e}", exc_info=True)
            return await self._handle_error(e, task, context)

    async def _process_task_with_routing(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Any:
        """执行业务逻辑（带思考模式路由）"""
        # 获取思考模式 (上下文优先)
        thinking_mode = "normal"
        if context:
            thinking_mode = context.get("thinking_mode", "normal")
        if thinking_mode == "normal" and "thinking_mode" in params:
            thinking_mode = params.get("thinking_mode", "normal")
        
        # 路由到 CoT/ReAct (如果混入了 ThinkingModeMixin)
        if thinking_mode == "deep" and hasattr(self, '_execute_cot_mode'):
            return await self._execute_cot_mode(params, context)
        elif thinking_mode == "react" and hasattr(self, '_execute_react_mode'):
            return await self._execute_react_mode(params, context)
            
        # 默认执行普通模式
        return await self._execute_normal_mode(params, context)

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
    def _validate_task(self, task: Dict[str, Any]) -> bool:
        """
        验证任务格式（子类必须实现）
        
        此方法用于验证任务是否包含必需的字段和格式是否正确。
        通常与 TaskAgentMixin 配合使用。
        
        Args:
            task: 任务内容
            
        Returns:
            验证是否通过
        """
        pass
    
    @abstractmethod
    def _extract_task_params(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取任务参数（子类必须实现）
        
        此方法用于从任务中提取业务逻辑所需的参数。
        通常与 TaskAgentMixin 配合使用。
        
        Args:
            task: 任务内容
            
        Returns:
            提取的参数字典
        """
        pass
    
    # 注意：不抽象 _execute_normal_core() 等具体执行方法
    # 执行模式（normal/cot）应该由参数决定，由 TaskAgentMixin 负责路由
    # Agent 可以选择实现 _execute_normal_mode() 或 _execute_cot_mode() 或两者
    
    @abstractmethod
    def _build_user_input_prompt(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        构建用户输入 Prompt（子类必须实现）
        
        此方法用于构建发送给 LLM 的用户消息内容。
        通常与 TaskAgentMixin 配合使用。
        
        Args:
            params: 任务参数
            context: 上下文信息
            
        Returns:
            用户输入 Prompt 字符串
        """
        pass
    
    @abstractmethod
    def _parse_llm_response(
        self,
        llm_response: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        解析 LLM 响应（子类必须实现）
        
        此方法用于解析 LLM 返回的文本，转换为结构化的结果字典。
        通常与 TaskAgentMixin 配合使用。
        
        Args:
            llm_response: LLM 返回的文本
            params: 任务参数（可用于备用提取等）
            context: 上下文信息
            
        Returns:
            解析后的结果字典
        """
        pass
    
    # 注意：execute() 方法已在 BaseAgent 中定义为抽象方法
    # 子类需要继承 TaskAgentMixin 或自己实现 execute() 方法
