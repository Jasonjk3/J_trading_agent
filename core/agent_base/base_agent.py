#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Agent基类
定义智能体的基本接口和行为
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger
import json

from core.models.agent_models import AgentInfo, AgentStatus
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_models import LLMModels


class BaseAgent(ABC):
    """智能体基类"""
    
    # ==================== 全局默认 LLM 配置 ====================
    LLM_CONFIG: Dict[str, Any] = {
        "model_name": LLMModels.GPT_4O,  # 默认使用 GPT-4O
        "temperature": 0.7,
        "max_tokens": 2048,
        "api_key_env": LLMModels.OPENAI_API_KEY_ENV
    }

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        capabilities: Optional[List[str]] = None,
        max_concurrent_tasks: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
        llm_config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化智能体

        Args:
            agent_id: 智能体唯一标识
            agent_name: 智能体名称
            agent_type: 智能体类型
            capabilities: 能力列表
            max_concurrent_tasks: 最大并发任务数
            metadata: 元数据
            llm_config: LLM配置（可选，覆盖类级别配置）
        """
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.capabilities = capabilities or []
        self.max_concurrent_tasks = max_concurrent_tasks
        self.metadata = metadata or {}
        self._instance_llm_config = llm_config  # 保存运行时配置
        
        self.status = AgentStatus.IDLE
        self.current_task_id: Optional[str] = None
        self.current_tasks = 0
        self.registered_at = datetime.now()
        self.last_heartbeat = datetime.now()
        self.performance_metrics: Dict[str, float] = {}
        
        # 初始化LLM属性（延迟初始化，在_get_llm()中创建）
        self.llm: Optional[BaseLLM] = None

    @abstractmethod
    async def execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行任务（抽象方法，子类必须实现）

        Args:
            task: 任务内容
            context: 上下文信息

        Returns:
            执行结果
        """
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化智能体（抽象方法，子类必须实现）

        Returns:
            是否初始化成功
        """
        pass

    @abstractmethod
    async def cleanup(self) -> bool:
        """
        清理资源（抽象方法，子类必须实现）

        Returns:
            是否清理成功
        """
        pass

    async def can_handle(self, task: Dict[str, Any]) -> bool:
        """
        判断是否能处理该任务

        Args:
            task: 任务内容

        Returns:
            是否能处理
        """
        # 检查状态：如果处于错误或离线状态，不能处理
        if self.status == AgentStatus.ERROR or self.status == AgentStatus.OFFLINE:
            return False
        
        # 检查并发数：只要当前任务数未达到上限，就可以接受新任务
        # 状态可以是 BUSY（有任务在执行）或 IDLE（没有任务），都可以接受新任务
        if self.current_tasks >= self.max_concurrent_tasks:
            return False
        
        return True

    async def update_status(self, status: AgentStatus):
        """
        更新状态

        Args:
            status: 新状态
        """
        old_status = self.status
        self.status = status
        logger.debug(f"Agent {self.agent_id} 状态更新: {old_status} -> {status}")
    
    async def _update_status_by_tasks(self):
        """
        根据当前任务数自动更新状态
        当有任务时设置为 BUSY，没有任务时设置为 IDLE
        """
        if self.current_tasks > 0:
            if self.status != AgentStatus.BUSY:
                await self.update_status(AgentStatus.BUSY)
        else:
            if self.status != AgentStatus.IDLE:
                await self.update_status(AgentStatus.IDLE)
                self.current_task_id = None

    async def update_heartbeat(self):
        """更新心跳时间"""
        self.last_heartbeat = datetime.now()

    async def update_metrics(self, metrics: Dict[str, float]):
        """
        更新性能指标

        Args:
            metrics: 性能指标字典
        """
        self.performance_metrics.update(metrics)

    def to_info(self) -> AgentInfo:
        """
        转换为AgentInfo对象

        Returns:
            AgentInfo对象
        """
        return AgentInfo(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            agent_type=self.agent_type,
            status=self.status,
            capabilities=self.capabilities,
            current_task_id=self.current_task_id,
            max_concurrent_tasks=self.max_concurrent_tasks,
            current_tasks=self.current_tasks,
            metadata=self.metadata,
            registered_at=self.registered_at,
            last_heartbeat=self.last_heartbeat,
            performance_metrics=self.performance_metrics
        )

    async def handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理消息（可选实现，用于智能体间通信）

        Args:
            message: 消息内容

        Returns:
            响应消息，如果不需要响应则返回None
        """
        # 默认实现：不处理消息
        logger.debug(f"Agent {self.agent_id} 收到消息: {message}")
        return None
    
    # ==================== 标准化执行流程（模板方法）====================
    
    async def _pre_execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> bool:
        """
        执行前处理（钩子方法）
        
        子类可以覆盖此方法，在执行前进行额外的处理。
        如果返回 False，将跳过执行。
        
        
        Args:
            task: 任务内容
            context: 上下文信息
            
        Returns:
            是否继续执行（False 表示跳过执行）
        """
        # 任务计数和状态管理已由 AgentExecutor 统一管理
        # 子类可以覆盖此方法添加业务特定的前置处理逻辑
        return True
    
    async def _post_execute(
        self, 
        result: Dict[str, Any], 
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行后处理（钩子方法）
        
        子类可以覆盖此方法，在执行后进行额外的处理。
        
        Args:
            result: 执行结果
            task: 任务内容
            context: 上下文信息
            
        Returns:
            处理后的结果
        """
        # 任务计数和状态管理已由 AgentExecutor 统一管理
        # 统一结果格式：添加 Agent 信息和 success 字段
        if isinstance(result, dict):
            result.setdefault("agent_id", self.agent_id)
            result.setdefault("agent_type", self.agent_type)
            # 如果结果中没有 success 字段，默认设为 True（表示执行成功）
            if "success" not in result:
                result.setdefault("success", True)
        
        return result
    
    async def _handle_error(
        self, 
        error: Exception, 
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        统一错误处理（钩子方法）
        
        子类可以覆盖此方法，自定义错误处理逻辑。
        
        注意：
        - 任务计数和状态管理已由 AgentExecutor 统一管理，此方法不再处理
        - 钩子函数的调用已由 AgentExecutor 统一管理，Agent 的 execute() 方法不再需要调用此方法
        
        Args:
            error: 异常对象
            task: 任务内容
            context: 上下文信息
            
        Returns:
            错误结果字典
        """
        logger.error(f"Agent {self.agent_id} 执行任务失败: {error}", exc_info=True)
        
        # 任务计数和状态管理已由 AgentExecutor 统一管理
        
        return {
            "success": False,
            "error": str(error),
            "task_id": task.get("task_id", ""),
            "agent_id": self.agent_id,
            "agent_type": self.agent_type
        }

    # ==================== Prompt 构建（标准化）====================
    
    def _get_system_prompt(self) -> str:
        """
        获取系统 Prompt（统一实现，子类必须覆盖或定义 SYSTEM_PROMPT 类属性）
        
        这是 Prompt 构建的统一入口，所有 Mixin 和子类都应使用此方法。
        
        子类必须（二选一）：
        1. 定义 SYSTEM_PROMPT 类属性（字符串）- 推荐方式
        2. 或覆盖此方法返回系统 Prompt
        
        注意：
        - 此方法只返回基础 Prompt，工具说明会由 _build_system_prompt() 自动添加
        - 所有 Prompt 构建逻辑都集中在此类和 _build_system_prompt() 中，避免代码重复
        - Mixin 中不应重复实现此方法
        - 如果子类没有实现，会抛出 NotImplementedError
        
        Returns:
            基础系统 Prompt 字符串
            
        Raises:
            NotImplementedError: 如果子类既没有定义 SYSTEM_PROMPT 也没有覆盖此方法
        """
        # 优先检查类属性 SYSTEM_PROMPT
        if hasattr(self.__class__, 'SYSTEM_PROMPT'):
            system_prompt = getattr(self.__class__, 'SYSTEM_PROMPT')
            if system_prompt:
                return system_prompt
        
        # 检查子类是否覆盖了此方法
        # 通过检查 MRO 中是否有非 BaseAgent 的类定义了此方法
        # 这样可以正确处理 Mixin 的情况
        method_defined_in_subclass = False
        for cls in self.__class__.__mro__:
            if cls is BaseAgent:
                # 遍历到 BaseAgent，如果还没找到子类实现，说明子类没有覆盖
                break
            if '_get_system_prompt' in cls.__dict__:
                # 找到了子类或 Mixin 的实现
                method_defined_in_subclass = True
                break
        
        if not method_defined_in_subclass:
            # 子类既没有定义 SYSTEM_PROMPT，也没有覆盖方法
            raise NotImplementedError(
                f"子类 {self.__class__.__name__} 必须实现 _get_system_prompt() 方法 "
                f"或定义 SYSTEM_PROMPT 类属性。\n"
                f"实现方式：\n"
                f"1. 定义类属性：SYSTEM_PROMPT = \"你的系统提示词\"\n"
                f"2. 或覆盖方法：def _get_system_prompt(self) -> str: return \"你的系统提示词\""
            )
        
        # 如果执行到这里，说明：
        # 1. 子类覆盖了 _get_system_prompt() 方法
        # 2. 子类的方法中调用了 super()._get_system_prompt() 或 BaseAgent._get_system_prompt()
        # 这种情况下，我们返回默认实现，供子类扩展使用
        # 注意：由于 MRO 机制，如果子类直接调用 self._get_system_prompt()，会递归调用子类自己的方法
        # 只有通过 super() 调用才会执行到这里
        return """你是一个智能助手，能够友好、专业地回答用户的问题。
请遵循以下原则：
1. 回答要准确、有帮助
2. 语言要自然、友好
3. 如果不确定答案，要诚实说明
4. 保持对话的连贯性"""
    
    def _build_system_prompt(self) -> str:
        """
        构建完整的系统 Prompt（统一入口）
        
        标准流程：
        1. 调用 _get_system_prompt() 获取基础 prompt
        2. 调用 _add_tools_description() 添加工具说明（如果启用工具）
        3. 调用 _add_custom_instructions() 添加自定义指令（可选）
        
        Returns:
            完整的系统 prompt
        """
        # 1. 获取基础 Prompt
        base_prompt = self._get_system_prompt()
        
        # 2. 添加工具说明
        prompt_with_tools = self._add_tools_description(base_prompt)
        
        # 3. 添加自定义指令
        final_prompt = self._add_custom_instructions(prompt_with_tools)
        
        return final_prompt
    
    def _add_tools_description(self, base_prompt: str) -> str:
        """
        添加工具说明（统一实现，子类无需覆盖）
        
        Args:
            base_prompt: 基础 Prompt
            
        Returns:
            添加工具说明后的 Prompt
        """
        # 检查是否有工具
        tools = getattr(self, 'tools', {})
        enable_tool_calling = getattr(self, 'enable_tool_calling', False)
        
        if not tools or not enable_tool_calling:
            return base_prompt
        
        # 导入 BaseTool（延迟导入避免循环依赖）
        try:
            from core.tools.base.base_tool import BaseTool
        except ImportError:
            logger.warning("无法导入 BaseTool，跳过工具说明添加")
            return base_prompt
        
        # 构建工具说明
        tools_prompt = "\n\n你可以使用以下工具来帮助完成任务：\n"
        for tool_name, tool in tools.items():
            if not isinstance(tool, BaseTool):
                continue
                
            schema = tool.get_schema()
            tools_prompt += f"\n工具名称：{tool_name}\n"
            tools_prompt += f"描述：{schema.get('description', '')}\n"
            
            params = schema.get('parameters', {})
            if params:
                tools_prompt += f"参数：{json.dumps(params, ensure_ascii=False, indent=2)}\n"
        
        tools_prompt += "\n当需要使用工具时，请在回复中使用以下格式：\n"
        tools_prompt += "```tool_call\n{\n  \"tool\": \"工具名称\",\n  \"parameters\": {\"参数名\": \"参数值\"}\n}\n```\n"
        tools_prompt += "工具执行结果会在后续消息中提供给你。"
        
        return base_prompt + tools_prompt
    
    def _add_custom_instructions(self, base_prompt: str) -> str:
        """
        添加自定义指令（可选，子类可覆盖）
        
        Args:
            base_prompt: 基础 Prompt（可能已包含工具说明）
            
        Returns:
            添加自定义指令后的 Prompt
        """
        # 默认实现：不添加任何内容
        # 子类可以覆盖此方法添加特定指令
        return base_prompt
    
    def _build_user_input_prompt(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> str:
        """
        构建用户输入 Prompt（统一入口）
        
        子类可以覆盖此方法来自定义用户输入 Prompt 的构建逻辑。
        默认实现：从 task 中提取 content 或 query。
        
        Args:
            task: 任务内容
            context: 上下文信息
            
        Returns:
            用户输入 Prompt 字符串
        """
        # 默认实现：从 task 中提取内容
        content = task.get("content") or task.get("query") or task.get("message", "")
        if not content:
            content = str(task)
        return content
    
    def _format_prompt_template(self, template: str, **kwargs) -> str:
        """
        格式化 Prompt 模板
        
        Args:
            template: Prompt 模板字符串，支持 {variable} 格式的占位符
            **kwargs: 模板变量
            
        Returns:
            格式化后的 Prompt
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Prompt 模板格式化失败，缺少变量: {e}")
            return template
        except Exception as e:
            logger.error(f"Prompt 模板格式化失败: {e}", exc_info=True)
            return template
    
    # ==================== 消息构建（标准化）====================
    
    def _build_messages(
        self, 
        user_message: str, 
        history: Optional[List[Dict[str, str]]] = None,
        include_system_prompt: bool = True
    ) -> List[Dict[str, str]]:
        """
        构建消息列表
        
        标准格式：
        [
            {"role": "system", "content": system_prompt},  # 如果 include_system_prompt
            ...history...,  # 历史消息
            {"role": "user", "content": user_message}  # 当前消息
        ]
        
        Args:
            user_message: 用户消息
            history: 历史消息列表，格式为 [{"role": "...", "content": "..."}]
            include_system_prompt: 是否包含系统提示词
            
        Returns:
            消息列表
        """
        messages = []
        
        # 1. 添加系统提示词
        if include_system_prompt:
            system_prompt = getattr(self, 'system_prompt', None)
            if not system_prompt:
                # 如果没有 system_prompt 属性，动态构建
                system_prompt = self._build_system_prompt()
            messages.append({"role": "system", "content": system_prompt})
        
        # 2. 添加历史消息
        if history:
            # 验证历史消息格式
            validated_history = self._validate_history(history)
            messages.extend(validated_history)
        
        # 3. 添加当前用户消息
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def _validate_history(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        验证并规范化历史消息格式
        
        Args:
            history: 历史消息列表
            
        Returns:
            验证后的历史消息列表
        """
        validated = []
        for msg in history:
            if not isinstance(msg, dict):
                logger.warning(f"历史消息格式错误，跳过: {msg}")
                continue
            
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # 确保 role 是有效值
            if role not in ["system", "user", "assistant"]:
                logger.warning(f"无效的消息角色: {role}，使用默认值 'user'")
                role = "user"
            
            validated.append({
                "role": role,
                "content": str(content) if content else ""
            })
        
        return validated
    
    def _build_single_message(self, role: str, content: str) -> Dict[str, str]:
        """
        构建单个消息
        
        Args:
            role: 消息角色（system/user/assistant）
            content: 消息内容
            
        Returns:
            消息字典
        """
        if role not in ["system", "user", "assistant"]:
            logger.warning(f"无效的消息角色: {role}，使用默认值 'user'")
            role = "user"
        
        return {
            "role": role,
            "content": str(content) if content else ""
        }
    
    # ==================== LLM 管理 =====================
    
    def _get_llm_config(self) -> Dict[str, Any]:
        """
        获取 LLM 配置（三级优先级）
        
        优先级：
        1. 运行时参数 (self._instance_llm_config) - 最高优先级
        2. 子类配置 (子类的 LLM_CONFIG 类属性)
        3. 默认配置 (BaseAgent.LLM_CONFIG) - 降级配置
        
        Returns:
            LLM配置字典
        """
        # 从 BaseAgent 获取默认配置
        config = BaseAgent.LLM_CONFIG.copy()
        
        # 合并子类配置（如果子类定义了 LLM_CONFIG）
        if hasattr(self.__class__, 'LLM_CONFIG') and self.__class__ is not BaseAgent:
            class_config = self.__class__.LLM_CONFIG
            if class_config and isinstance(class_config, dict):
                config.update(class_config)
        
        # 合并运行时配置（最高优先级）
        instance_config = getattr(self, '_instance_llm_config', None)
        if instance_config and isinstance(instance_config, dict):
            config.update(instance_config)
        
        return config
    
    def _get_llm(self) -> Optional[BaseLLM]:
        """
        获取LLM实例（延迟初始化）
        
        子类可以覆盖此方法自定义LLM获取逻辑。
        默认实现使用LLMFactory创建LLM实例。
        
        Returns:
            LLM实例，如果创建失败则返回None
        """
        # 使用getattr确保属性存在，避免AttributeError
        if not getattr(self, 'llm', None):
            try:
                from core.llm.llm_factory import LLMFactory
                
                # 获取合并后的配置
                config = self._get_llm_config()
                
                # 创建LLM实例（直接传入配置参数）
                self.llm = LLMFactory.create_llm(**config)
                
                if self.llm:
                    logger.debug(
                        f"{self.__class__.__name__} 成功获取LLM实例 "
                        f"(type={config.get('llm_type')}, "
                        f"temp={config.get('temperature')}, "
                        f"max_tokens={config.get('max_tokens')})"
                    )
                else:
                    logger.warning(f"{self.__class__.__name__} 获取LLM实例失败")
            except Exception as e:
                logger.error(f"{self.__class__.__name__} 获取LLM实例时发生错误: {e}", exc_info=True)
                self.llm = None
        
        return self.llm
    
    # ==================== LLM 调用（标准化）====================
    
    async def _call_llm(self, prompt: str) -> str:
        """
        调用 LLM（文本格式）
        
        Args:
            prompt: 文本提示词
            
        Returns:
            LLM 响应文本
            
        Raises:
            ValueError: 如果 LLM 未初始化
            Exception: LLM 调用失败
        """
        # 确保LLM已初始化
        llm = self._get_llm()
        if not llm:
            error_msg = "LLM未初始化，无法调用"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            # 尝试异步调用（设置上下文使 LLM 内部 _track_usage 能获取 agent_name）
            if hasattr(llm, 'ainvoke'):
                from core.llm.base.usage_tracker import track_context
                agent_name = getattr(self, 'agent_name', None)
                task_type = getattr(self, 'agent_type', None)
                with track_context(agent_name=agent_name, task_type=task_type):
                    result = await llm.ainvoke(prompt)
                return result.content if hasattr(result, 'content') else str(result)
            
            # 尝试同步调用（在线程池中执行）
            elif hasattr(llm, '_call'):
                import asyncio
                from core.llm.base.usage_tracker import track_context
                agent_name = getattr(self, 'agent_name', None)
                task_type = getattr(self, 'agent_type', None)
                loop = asyncio.get_event_loop()
                with track_context(agent_name=agent_name, task_type=task_type):
                    result = await loop.run_in_executor(None, llm._call, prompt)
                return result.content if hasattr(result, 'content') else str(result)
            
            # 降级：直接调用
            else:
                from core.llm.base.usage_tracker import track_context
                agent_name = getattr(self, 'agent_name', None)
                task_type = getattr(self, 'agent_type', None)
                with track_context(agent_name=agent_name, task_type=task_type):
                    result = llm._call(prompt)
                return result.content if hasattr(result, 'content') else str(result)
                
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}", exc_info=True)
            error_response = self._handle_llm_error(e)
            if error_response:
                return error_response
            raise
    
    async def _call_llm_with_messages(self, messages: List[Dict[str, str]]) -> str:
        """
        调用 LLM（消息列表格式）
        
        Args:
            messages: 消息列表，格式为 [{"role": "user/assistant/system", "content": "..."}]
            
        Returns:
            LLM 响应文本
            
        Raises:
            ValueError: 如果 LLM 未初始化
            Exception: LLM 调用失败
        """
        # 确保LLM已初始化
        llm = self._get_llm()
        if not llm:
            error_msg = "LLM未初始化，无法调用"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 回测上下文启用持久化重放缓存时，统一使用稳定文本序列化。
        # 这样技术分析 Agent 与交易决策 Agent 会共享相同的 prompt 哈希语义。
        try:
            from backtest.llm_replay_cache import get_active_replay_cache, call_llm_with_replay

            if get_active_replay_cache() is not None:
                text_prompt = self._messages_to_text(messages)
                response_text, _ = await call_llm_with_replay(llm, text_prompt)
                return response_text
        except ImportError:
            pass
        
        try:
            # 尝试使用 LangChain 消息格式
            if hasattr(llm, 'ainvoke') and hasattr(llm, 'invoke'):
                try:
                    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
                    from core.llm.base.usage_tracker import track_context
                    
                    langchain_messages = []
                    for msg in messages:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        if role == "system":
                            langchain_messages.append(SystemMessage(content=content))
                        elif role == "assistant":
                            langchain_messages.append(AIMessage(content=content))
                        else:
                            langchain_messages.append(HumanMessage(content=content))
                    
                    # 设置上下文，使 LLM._call 内的 _track_usage 能获取 agent_name
                    # 注意：ainvoke 会调用 _call，LLM 内部已记录一次，无需在此重复记录
                    agent_name = getattr(self, 'agent_name', None)
                    task_type = getattr(self, 'agent_type', None)
                    with track_context(agent_name=agent_name, task_type=task_type):
                        result = await llm.ainvoke(langchain_messages)
                    
                    response_text = result.content if hasattr(result, 'content') else str(result)
                    return response_text
                except Exception as e:
                    logger.warning(f"使用消息格式调用失败，降级到文本格式: {e}")
            
            # 降级：转换为文本格式
            text_prompt = self._messages_to_text(messages)
            return await self._call_llm(text_prompt)
            
        except Exception as e:
            # 失败时 LLM._call 内部已记录（若异常在 _call 内抛出）
            # 若异常在 ainvoke 外层（如消息格式转换失败），则无记录，此处不再重复记录
            logger.error(f"LLM 消息调用失败: {e}", exc_info=True)
            error_response = self._handle_llm_error(e)
            if error_response:
                return error_response
            raise
    
    def _messages_to_text(self, messages: List[Dict[str, str]]) -> str:
        """
        将消息列表转换为文本格式
        
        Args:
            messages: 消息列表
            
        Returns:
            文本格式的提示词
        """
        text_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                text_parts.append(f"系统: {content}")
            elif role == "assistant":
                text_parts.append(f"助手: {content}")
            else:
                text_parts.append(f"用户: {content}")
        
        return "\n\n".join(text_parts)
    
    def _handle_llm_error(self, error: Exception) -> Optional[str]:
        """
        处理 LLM 调用错误
        
        Args:
            error: 异常对象
            
        Returns:
            错误响应文本，如果返回 None 则重新抛出异常
        """
        error_type = type(error).__name__
        error_msg = str(error)
        
        logger.warning(f"LLM 调用错误 [{error_type}]: {error_msg}")
        
        # 可以根据错误类型返回不同的错误消息
        if "timeout" in error_msg.lower() or "timeout" in error_type.lower():
            return "抱歉，LLM 调用超时，请稍后重试。"
        elif "rate limit" in error_msg.lower():
            return "抱歉，请求过于频繁，请稍后重试。"
        else:
            # 默认：返回 None，让调用者决定如何处理
            return None

    def __repr__(self):
        return f"<{self.__class__.__name__}(id={self.agent_id}, name={self.agent_name}, status={self.status})>"

