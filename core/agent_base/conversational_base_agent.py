#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
对话式 Agent 基类
继承 BaseAgent，为对话式 Agent 提供标准化的基础实现
注意：Mixin 由 Agent 自己继承，不混进 Base 类里
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from uuid import uuid4
from loguru import logger

from core.agent_base.base_agent import BaseAgent
from core.models.agent_models import AgentStatus
from core.llm.base.base_llm import BaseLLM


class ConversationalBaseAgent(BaseAgent, ABC):
    """
    对话式 Agent 基类
    
    继承自 BaseAgent，为对话式 Agent 提供标准化的基础实现。
    注意：Mixin（如 ConversationalAgentMixin）由 Agent 自己继承，不混进 Base 类里。
    
    使用方式：
    1. 继承 ConversationalBaseAgent + ConversationalAgentMixin（或其他需要的 Mixin）
    2. 定义类属性：AGENT_TYPE, DEFAULT_TOOLS, DEFAULT_CAPABILITIES
    3. 实现系统 Prompt（_get_system_prompt() 或 SYSTEM_PROMPT 类属性）
    4. 可选：覆盖 execute() 添加业务特定逻辑
    
    示例：
    ```python
    class MyChatAgent(ConversationalAgentMixin, ConversationalBaseAgent):
        AGENT_TYPE = "my_chat"
        DEFAULT_TOOLS = ['text2datetime']
        DEFAULT_CAPABILITIES = ["chat", "conversation"]
        
        SYSTEM_PROMPT = "你是一个友好的聊天助手..."
        
        def __init__(self, llm: BaseLLM, **kwargs):
            super().__init__(
                agent_name="我的聊天Agent",
                agent_type=self.AGENT_TYPE,
                capabilities=self.DEFAULT_CAPABILITIES,
                llm=llm,
                auto_load_tools=self.DEFAULT_TOOLS,
                **kwargs
            )
    ```
    """
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "对话式Agent",
        agent_type: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        max_concurrent_tasks: int = 10,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        初始化对话式 Agent
        
        Args:
            agent_id: Agent ID（自动生成）
            agent_name: Agent 名称
            agent_type: Agent 类型（如果未提供，使用类的 AGENT_TYPE）
            capabilities: 能力列表（如果未提供，使用类的 DEFAULT_CAPABILITIES）
            max_concurrent_tasks: 最大并发任务数
            metadata: 元数据
            **kwargs: 其他参数（传递给 Mixin 的初始化方法）
        """
        agent_id = agent_id or str(uuid4())
        
        # 使用类属性作为默认值
        if agent_type is None:
            agent_type = getattr(self.__class__, 'AGENT_TYPE', 'conversational_agent')
        if capabilities is None:
            capabilities = getattr(self.__class__, 'DEFAULT_CAPABILITIES', ['chat', 'conversation'])
        
        # 调用 BaseAgent 初始化
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=agent_type,
            capabilities=capabilities,
            max_concurrent_tasks=max_concurrent_tasks,
            metadata=metadata or {}
        )
        
        # LLM 实例将在 initialize() 中创建
        self.llm: Optional[BaseLLM] = None
        
        # 构建系统 Prompt
        self.system_prompt = self._build_system_prompt()
    
    async def _create_llm_from_model_id(self, model_id: str, db_session) -> None:
        """
        根据model_id创建LLM实例
        
        Args:
            model_id: 模型ID
            db_session: 数据库会话
        """
        try:
            from core.llm.llm_factory import LLMFactory
            from app.v1.crud.model_management_crud import get_model_by_model_id, get_api_config_by_id
            
            # 查询模型信息
            model = await get_model_by_model_id(db_session, model_id)
            if not model:
                logger.warning(f"Agent未找到模型ID: {model_id}，使用默认LLM")
                return
            
            # 获取API配置
            api_config = None
            if model.api_config_id:
                api_config = await get_api_config_by_id(db_session, model.api_config_id)
            
            if not api_config or not api_config.api_key:
                logger.warning(f"Agent模型 {model_id} 的API配置无效，使用默认LLM")
                return
            
            # 创建LLM实例
            self.llm = LLMFactory.create_llm_direct(
                model_name=model.model_id,
                api_key=api_config.api_key,
                api_type=LLMFactory._infer_api_type(model.model_id),
                api_url=api_config.api_url,
                temperature=0.7,
                max_tokens=model.max_tokens or 2048
            )
            
            if self.llm:
                logger.info(f"Agent使用模型 {model_id} ({model.name}) 创建LLM实例成功")
            else:
                logger.error(f"Agent使用模型 {model_id} 创建LLM实例失败")
        except Exception as e:
            logger.error(f"Agent创建模型LLM实例失败: {e}", exc_info=True)
    
    async def initialize(self) -> bool:
        """
        初始化 Agent（标准实现）
        
        子类可以覆盖此方法添加特定的初始化逻辑，但应调用 super().initialize()
        或使用 Mixin 提供的初始化方法
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
        或使用 Mixin 提供的清理方法
        """
        try:
            await self.update_status(AgentStatus.IDLE)
            return True
        except Exception as e:
            logger.error(f"{self.__class__.__name__}清理失败: {e}")
            return False
    
    async def execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        对话式 Agent 的标准执行流程
        实现 BaseAgent.execute 接口
        """
        message = task.get("message") or task.get("content", "")
        session_id = task.get("session_id", "default")
        images = task.get("images")  # 获取图片列表
        
        if not message and not images:
            return self._handle_error_internal("消息内容不能为空", task, context)

        try:
            # 1. 预处理 (调用 BaseAgent 钩子)
            if not await self._pre_execute(task, context):
                return self._handle_error_internal("任务预处理失败", task, context)

            # 将图片添加到context中，以便传递给LLM
            if context is None:
                context = {}
            if images:
                context["images"] = images

            # 如果context中有model_id，使用指定的模型创建LLM实例
            # 需要重置self.llm为None，确保使用新模型
            model_id = context.get("model_id")
            db_session = context.get("db_session")
            if model_id and db_session:
                # 重置LLM实例，强制使用新模型
                self.llm = None
                await self._create_llm_from_model_id(model_id, db_session)

            # 2. 业务逻辑 (调用子类实现的 _process_message)
            # 优先调用具体的 _process_message，如果未实现则使用默认逻辑
            try:
                response = await self._process_message(message, session_id, context)
            except NotImplementedError:
                response = await self._default_process_message(message, session_id, context, images)

            # 3. 后处理逻辑 (更新历史等)
            # 只有混入了 HistoryMixin 的类才会有 _update_history 方法
            if hasattr(self, '_update_history'):
                self._update_history(session_id, "user", message)
                self._update_history(session_id, "assistant", response)

            # 4. 统一构建结果
            from core.agent_mixin.mixin_utils import build_agent_result
            result = build_agent_result(
                self, 
                success=True, 
                response=response, 
                session_id=session_id,
                task_id=task.get("task_id")
            )

            # 5. 执行后钩子
            return await self._post_execute(result, task, context)

        except Exception as e:
            logger.error(f"对话执行异常: {e}", exc_info=True)
            return await self._handle_error(e, task, context)

    async def _default_process_message(self, message: str, session_id: str, context: Optional[Dict[str, Any]] = None, images: Optional[List[str]] = None) -> str:
        """默认的对话逻辑（构建消息 -> LLM -> 工具处理）"""
        # 获取历史消息
        history = []
        if hasattr(self, 'get_history'):
            history = await self.get_history(session_id)
        
        # 从context中获取图片（如果未直接传递）
        if not images and context:
            images = context.get("images")
        
        # 如果有图片，直接调用LLM并传递图片
        if images:
            llm = self._get_llm()
            if llm:
                # 构建包含图片的prompt
                prompt = message if message else "请分析图片"
                # 使用ainvoke调用，通过kwargs传递images
                try:
                    from core.llm.base.usage_tracker import track_context
                    agent_name = getattr(self, 'agent_name', None)
                    task_type = getattr(self, 'agent_type', None)
                    with track_context(agent_name=agent_name, task_type=task_type):
                        # 调用_call方法，传递images参数
                        response = llm._call(prompt, images=images)
                    return response if isinstance(response, str) else str(response)
                except Exception as e:
                    logger.warning(f"使用图片调用LLM失败: {e}，降级到普通文本模式")
                    # 降级到普通文本模式
                    messages = self._build_messages(user_message=message, history=history)
                    response = await self._call_llm_with_messages(messages)
                    return response
        
        # 构建消息列表（无图片的情况）
        messages = self._build_messages(user_message=message, history=history)
        
        # 调用 LLM
        response = await self._call_llm_with_messages(messages)
        
        # 处理工具调用
        if getattr(self, 'enable_tool_calling', False) and hasattr(self, '_handle_tool_calling'):
            response = await self._handle_tool_calling(response, messages, session_id)
            
        return response

    def _handle_error_internal(self, error_msg: str, task: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """内部错误处理助手"""
        from core.agent_mixin.mixin_utils import build_agent_result
        return build_agent_result(
            self,
            success=False,
            error=error_msg,
            task_id=task.get("task_id")
        )

    # ==================== 抽象方法 ====================
    
    @abstractmethod
    async def _process_message(
        self,
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        处理单条消息（核心业务逻辑，子类必须实现）
        
        这是对话式Agent的核心方法，负责处理用户消息并返回响应。
        子类必须实现此方法。
        
        Args:
            message: 用户消息
            session_id: 会话ID
            context: 上下文信息
            
        Returns:
            响应文本
        """
        pass
    
    def _format_response(
        self,
        response: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        格式化响应（可选实现）
        
        子类可以覆盖此方法自定义响应格式。
        默认实现返回标准格式。
        
        Args:
            response: 响应文本
            session_id: 会话ID
            context: 上下文信息
            
        Returns:
            格式化的响应字典
        """
        return {
            "success": True,
            "response": response,
            "session_id": session_id
        }
    
    # ==================== 工具方法（子类可使用）====================
    
    def get_conversation_history(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        获取会话历史
        
        Args:
            session_id: 会话ID
            limit: 返回的历史记录数量限制
            
        Returns:
            会话历史列表，格式为 [{"role": "user/assistant", "content": "..."}]
        """
        # 如果 Mixin 提供了会话历史，使用 Mixin 的
        if hasattr(self, 'conversation_history'):
            history = self.conversation_history.get(session_id, [])
            return history[-limit * 2:] if limit > 0 else history
        
        # 否则返回空列表
        return []
    
    def clear_conversation_history(self, session_id: str):
        """
        清除会话历史
        
        Args:
            session_id: 会话ID
        """
        if hasattr(self, 'conversation_history'):
            if session_id in self.conversation_history:
                del self.conversation_history[session_id]
                logger.info(f"已清除会话历史: {session_id}")
    
    def _build_conversation_messages(
        self,
        message: str,
        session_id: str,
        include_history: bool = True,
        include_system_prompt: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建对话消息列表（包含历史）
        
        Args:
            message: 当前用户消息
            session_id: 会话ID
            include_history: 是否包含历史消息
            include_system_prompt: 是否包含系统提示词
            
        Returns:
            消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
        """
        messages = []
        
        # 1. 添加系统提示词
        if include_system_prompt:
            system_prompt = getattr(self, 'system_prompt', None)
            if not system_prompt:
                system_prompt = self._build_system_prompt()
            messages.append({"role": "system", "content": system_prompt})
        
        # 2. 添加历史消息
        if include_history:
            history = self.get_conversation_history(session_id, limit=10)
            messages.extend(history)
        
        # 3. 添加当前用户消息
        messages.append({"role": "user", "content": message})
        
        return messages
    
    # 注意：execute() 方法已在 BaseAgent 中定义为抽象方法
    # 子类需要继承 ConversationalAgentMixin 或自己实现 execute() 方法
