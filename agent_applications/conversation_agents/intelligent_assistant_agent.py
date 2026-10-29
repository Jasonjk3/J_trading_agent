#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 18:10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
智能助手Agent
提供聊天对话能力
"""
from typing import Any, Dict, Optional, List
from uuid import uuid4

from core.agent_base.conversational_base_agent import ConversationalBaseAgent
from core.component.registry.agent_registry import AgentRegistry
from core.agent_mixin.thinking_mode_mixin import ThinkingModeMixin
from core.agent_mixin.tool_loader_mixin import ToolLoaderMixin
from core.agent_mixin.conversational_agent_mixin import ConversationalAgentMixin
from core.llm.base.base_llm import BaseLLM
from core.tools.base.base_tool import BaseTool
from core.models.agent_models import AgentStatus
from core.llm.llm_models import LLMModels
from loguru import logger


class IntelligentAssistantAgent(ConversationalAgentMixin, ToolLoaderMixin, ThinkingModeMixin, ConversationalBaseAgent):
    """
    智能助手Agent - 提供通用聊天对话能力
    
    继承自 ConversationalBaseAgent，只需定义：
    1. 配置属性（AGENT_TYPE, DEFAULT_TOOLS, DEFAULT_CAPABILITIES）
    2. 业务特定的系统提示词（_get_system_prompt 或 SYSTEM_PROMPT 类属性）
    """

    # ==================== 配置 ====================
    AGENT_TYPE = "intelligent_assistant"
    DEFAULT_TOOLS = ['text2datetime']
    DEFAULT_CAPABILITIES = ["chat", "conversation", "qa", "intent_routing"]
    
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
        agent_name: str = "智能助手",
        llm: Optional[BaseLLM] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[BaseTool]] = None,
        auto_load_tools: Optional[List[Dict[str, Any]]] = None,
        enable_tool_calling: bool = True,
        agent_registry: Optional[AgentRegistry] = None,
        **kwargs
    ):
        """初始化智能助手Agent"""
        agent_id = agent_id or str(uuid4())
        
        # 动态添加 tool_calling 能力
        capabilities = self.DEFAULT_CAPABILITIES.copy()
        if tools or auto_load_tools:
            if "tool_calling" not in capabilities:
                capabilities.append("tool_calling")
        
        # 调用 BaseAgent 初始化
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=self.AGENT_TYPE,
            capabilities=capabilities,
            max_concurrent_tasks=kwargs.get("max_concurrent_tasks", 10),
            metadata=kwargs.get("metadata", {})
        )
        
        # 保存额外属性
        self.agent_registry = agent_registry
        
        # 初始化属性
        self.enable_tool_calling = enable_tool_calling
        self.auto_load_tools = auto_load_tools
        self._custom_system_prompt = system_prompt
        self._init_tools = tools
        self.kwargs = kwargs
        
        # 初始系统提示词
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            self.system_prompt = self._build_system_prompt()
        
        # 注意：思维链组件将在initialize()中初始化，因为需要先创建LLM实例

    def _get_system_prompt(self) -> str:
        """智能助手的基础系统提示词"""
        return """你是一个智能助手，能够友好、专业地回答用户的问题。
请遵循以下原则：
1. 回答要准确、有帮助
2. 语言要自然、友好
3. 如果不确定答案，要诚实说明
4. 保持对话的连贯性"""

    async def initialize(self) -> bool:
        """初始化智能体"""
        try:
            # 确保LLM已初始化（使用BaseAgent的_get_llm方法）
            if not self._get_llm():
                logger.error("智能助手Agent创建LLM实例失败")
                await self.update_status(AgentStatus.ERROR)
                return False
            
            # 初始化工具
            if hasattr(self, '_initialize_tools'):
                await self._initialize_tools()
            
            # 更新系统提示词
            self.system_prompt = self._build_system_prompt()
            
            # 初始化思维链组件（需要在LLM创建后）
            llm = self._get_llm()
            if llm:
                self._init_thinking_components(llm, self.tools, self.system_prompt)
            
            await self.update_status(AgentStatus.IDLE)
            return True
        except Exception as e:
            logger.error(f"智能助手Agent初始化失败: {e}", exc_info=True)
            await self.update_status(AgentStatus.ERROR)
            return False

    async def cleanup(self) -> bool:
        """清理资源"""
        await self._cleanup_tools()
        self.conversation_history.clear()
        return True

    async def _process_message(self, message: str, session_id: str, context: Optional[Dict[str, Any]] = None) -> str:
        """核心消息处理逻辑"""
        return await self._default_process_message(message, session_id, context)

    async def execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        from core.agent_runtime.contracts import RuntimeInvocation

        invocation = (context or {}).get("_conversation_runtime")
        if isinstance(invocation, RuntimeInvocation):
            # Request-local model and authoritative database history; no writes
            # to the singleton Agent's llm or in-memory conversation history.
            return await invocation.execute()
        return await super().execute(task, context)
