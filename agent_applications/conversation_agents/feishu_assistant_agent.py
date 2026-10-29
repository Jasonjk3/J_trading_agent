#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/20 16:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
飞书助手Agent
专注于处理飞书相关操作
"""
from typing import Any, Dict, Optional, List
from uuid import uuid4

from core.agent_base.conversational_base_agent import ConversationalBaseAgent
from core.agent_mixin.thinking_mode_mixin import ThinkingModeMixin
from core.agent_mixin.tool_loader_mixin import ToolLoaderMixin
from core.agent_mixin.conversational_agent_mixin import ConversationalAgentMixin
from core.llm.base.base_llm import BaseLLM
from core.tools.base.base_tool import BaseTool
from core.models.agent_models import AgentStatus
from core.llm.llm_models import LLMModels
from loguru import logger


class FeishuAssistantAgent(ConversationalAgentMixin, ToolLoaderMixin, ThinkingModeMixin, ConversationalBaseAgent):
    """
    飞书助手Agent - 专注于处理飞书相关操作
    
    继承自 ConversationalAgentMixin，只需定义：
    1. 配置属性（AGENT_TYPE, DEFAULT_TOOLS, DEFAULT_CAPABILITIES）
    2. 业务特定的系统提示词（_get_system_prompt 或 SYSTEM_PROMPT 类属性）
    """

    # ==================== 配置 ====================
    AGENT_TYPE = "feishu_assistant"
    DEFAULT_TOOLS = ['feishu_contact', 'feishu_approval', 'feishu_bitable', 'feishu_im', 'feishu_task', 'text2sql']
    DEFAULT_CAPABILITIES = ["feishu_operations", "tool_calling"]
    FEISHU_TOOL_TYPES = ['feishu_contact', 'feishu_approval', 'feishu_bitable', 'feishu_im', 'feishu_task']
    
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
        agent_name: str = "飞书助手",
        llm: Optional[BaseLLM] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[BaseTool]] = None,
        auto_load_tools: Optional[List[Dict[str, Any]]] = None,
        enable_tool_calling: bool = True,
        **kwargs
    ):
        """初始化飞书助手Agent"""
        agent_id = agent_id or str(uuid4())
        
        # 调用 BaseAgent 初始化
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=self.AGENT_TYPE,
            capabilities=self.DEFAULT_CAPABILITIES.copy(),
            max_concurrent_tasks=kwargs.get("max_concurrent_tasks", 10),
            metadata=kwargs.get("metadata", {})
        )
        
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
        """飞书助手的基础系统提示词"""
        return """你是一个专业的飞书助手，专门处理飞书相关的操作。
你可以帮助用户完成以下任务：
1. 查询飞书用户信息（通过手机号、邮箱、用户名等）
2. 查询和管理部门信息
3. 查询审批实例信息
4. 操作多维表格（创建、查询、更新、删除记录）
5. 上传图片和文件
6. 向飞书用户或群发送消息
7. 创建和管理飞书任务（包括创建任务、更新任务、获取任务详情、删除任务、设置任务标题、描述、负责人、截止时间、提醒、完成任务等）

注意事项：
1. 注意向飞书用户发送消息需要获取飞书的user_id而不是open_id

【重要：工具使用优先级规则】
1. 查询用户信息（user_id、open_id、用户名等）：**必须优先使用 text2sql 工具**
   - 正确做法：使用 text2sql 查询 feishu_user 表，例如 "从 feishu_user 表查询用户名包含'张三'的 open_id"
   - 原因：text2sql 直接查询本地数据库，速度更快、更准确、无需API调用限制
   - 错误做法：直接使用 feishu_contact 的 search_user 功能（仅作为备选方案）
2. 只有在以下情况才使用 feishu_contact 查询用户：
   - text2sql 工具未注册
   - text2sql 查询无结果或报错

请遵循以下原则：
1. 准确理解用户需求
2. 按照上述工具优先级规则选择工具
3. 清晰地向用户展示结果
4. 如果操作失败，要说明原因并提供建议"""

    async def initialize(self) -> bool:
        """初始化智能体"""
        try:
            # 确保LLM已初始化（使用BaseAgent的_get_llm方法）
            if not self._get_llm():
                logger.error("飞书助手Agent创建LLM实例失败")
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
            logger.error(f"飞书助手Agent初始化失败: {e}", exc_info=True)
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
