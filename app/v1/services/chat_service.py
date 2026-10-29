#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 18:20
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
聊天服务
处理聊天相关的业务逻辑
"""
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from loguru import logger

from core.component.registry.agent_registry import AgentRegistry
from core.component.storage.session_store import SessionStore
from core.component.storage.task_queue import TaskQueue
from core.component.executor.agent_executor import AgentExecutor
from core.models.agent_models import Task, TaskStatus, TaskPriority
from core.agent_base.base_agent import BaseAgent
from core.component.intent.intent_recognizer import IntentRecognizer
from core.component.intent.intent_router import IntentRouter
from core.component.intent.intent_models import Intent
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_models import LLMModels
from app.v1.schemas.chat_schema import ChatResponse


class ChatService:
    """聊天服务"""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        session_store: SessionStore,
        task_queue: TaskQueue,
        agent_executor: Optional[AgentExecutor] = None
    ):
        """
        初始化聊天服务

        Args:
            agent_registry: 智能体注册中心
            session_store: 会话存储
            task_queue: 任务队列
            agent_executor: 智能体执行器（可选）
        """
        self.agent_registry = agent_registry
        self.session_store = session_store
        self.task_queue = task_queue
        self.agent_executor = agent_executor or AgentExecutor()
        
        # LLM实例将在需要时创建（延迟初始化）
        self.llm: Optional[BaseLLM] = None
        self.intent_recognizer = None
        self.intent_router = None

        from app.v1.services.agent_conversation_service import AgentConversationService
        self.conversation_runtime = AgentConversationService(
            session_store, task_queue, self.agent_executor
        )
        self.conversation_runs = None
    
    async def _get_or_create_llm(self, model_id: Optional[str] = None, db_session=None) -> Optional[BaseLLM]:
        """
        获取或创建LLM实例（延迟初始化）
        
        Args:
            model_id: 模型ID，如果提供则使用指定的模型，否则使用默认模型
            db_session: 数据库会话（可选）
        """
        # 如果提供了model_id，需要重新创建LLM实例
        if model_id:
            # 如果没有提供db_session，无法查询模型信息，回退到默认模型
            if not db_session:
                logger.warning(f"未提供数据库会话，无法查询模型ID: {model_id}，使用默认模型")
                return await self._get_or_create_llm(None, db_session)
            
            try:
                from core.llm.llm_factory import LLMFactory
                from app.v1.crud.model_management_crud import get_model_by_model_id, get_api_config_by_id
                
                # 使用传入的db_session查询模型信息
                model = await get_model_by_model_id(db_session, model_id)
                if not model:
                    logger.warning(f"未找到模型ID: {model_id}，使用默认模型")
                    return await self._get_or_create_llm(None, db_session)
                
                # 获取API配置
                api_config = None
                if model.api_config_id:
                    api_config = await get_api_config_by_id(db_session, model.api_config_id)
                
                if not api_config or not api_config.api_key:
                    logger.warning(f"模型 {model_id} 的API配置无效，使用默认模型")
                    return await self._get_or_create_llm(None, db_session)
                
                # 使用模型信息创建LLM
                self.llm = LLMFactory.create_llm_direct(
                    model_name=model.model_id,
                    api_key=api_config.api_key,
                    api_type=LLMFactory._infer_api_type(model.model_id),
                    api_url=api_config.api_url,
                    temperature=0.7,
                    max_tokens=getattr(model, "max_output_tokens", None) or model.max_tokens or 2048,
                    use_max_completion_tokens=bool(model.use_max_completion_tokens),
                )
                
                if self.llm:
                    # 初始化意图识别和路由组件
                    self.intent_recognizer = IntentRecognizer(self.llm)
                    self.intent_router = IntentRouter(self.agent_registry, self.llm)
                    logger.info(f"ChatService使用模型 {model_id} 创建LLM实例成功")
                else:
                    logger.error(f"ChatService使用模型 {model_id} 创建LLM实例失败")
                    return await self._get_or_create_llm(None, db_session)
            except Exception as e:
                logger.error(f"ChatService使用模型 {model_id} 创建LLM实例失败: {e}", exc_info=True)
                # 失败时回退到默认模型
                return await self._get_or_create_llm(None, db_session)
        
        # 使用默认模型
        if not self.llm:
            try:
                from core.llm.llm_factory import LLMFactory
                
                # 使用新的配置方式创建LLM（使用常量定义）
                self.llm = LLMFactory.create_llm(
                    model_name=LLMModels.GPT_4O,
                    temperature=0.7,
                    max_tokens=2048,
                    api_key_env=LLMModels.OPENAI_API_KEY_ENV
                )
                
                if self.llm:
                    # 初始化意图识别和路由组件
                    self.intent_recognizer = IntentRecognizer(self.llm)
                    self.intent_router = IntentRouter(self.agent_registry, self.llm)
                    logger.info("ChatService创建默认LLM实例成功")
                else:
                    logger.error("ChatService创建默认LLM实例失败")
            except Exception as e:
                logger.error(f"ChatService创建默认LLM实例失败: {e}", exc_info=True)
                return None
        
        return self.llm

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        agent_name: Optional[str] = None,
        thinking_mode: str = "normal",
        model_id: Optional[str] = None,
        images: Optional[List[str]] = None
    ) -> ChatResponse:
        """
        处理聊天请求

        Args:
            message: 用户消息
            session_id: 会话ID
            user_id: 用户ID
            context: 上下文信息

        Returns:
            ChatResponse对象
        """
        try:
            if self.conversation_runtime.settings.enabled and thinking_mode in {"normal", "deep"}:
                from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
                selected_agent = await self._select_agent_direct(agent_name)
                if isinstance(selected_agent, IntelligentAssistantAgent):
                    if self.conversation_runs is not None and self.conversation_runs.available:
                        from app.v1.schemas.chat_schema import ChatRequest
                        run, _ = await self.conversation_runs.submit(user_id, ChatRequest(
                            message=message, session_id=session_id, model_id=model_id,
                            thinking_mode=thinking_mode, images=images), selected_agent)
                        run = await self.conversation_runs.wait(run.id, str(user_id))
                        result = run.result or {}
                        return ChatResponse(
                            success=run.status == "succeeded", session_id=run.session_id,
                            agent_id=selected_agent.agent_id, trace_id=run.trace_id,
                            response=result.get("response"), error=run.error,
                            error_code=run.error_code,
                            runtime={k: v for k, v in (result.get("runtime") or {}).items() if k != "tool_audit"},
                            history=await self.session_store.get_history(run.session_id, user_id=user_id, limit=50),
                        )
                    return await self.conversation_runtime.chat(
                        selected_agent, message, session_id=session_id, user_id=user_id,
                        model_id=model_id, images=images,
                        db_session=(context or {}).get("db_session"),
                    )
            # 1. 获取或创建会话
            if not session_id:
                session = await self.session_store.create_session(
                    user_id=user_id,
                    context=context
                )
                session_id = session.session_id
            else:
                session = await self.session_store.get_session(session_id, user_id=user_id)
                if not session:
                    # 会话不存在，创建新会话
                    session = await self.session_store.create_session(
                        user_id=user_id,
                        context=context
                    )
                    session_id = session.session_id

            # 1.5. 检查是否需要自动生成标题
            # 如果会话没有标题，且这是第一条消息，则自动生成标题
            if not session.title:
                history = await self.session_store.get_history(session_id, user_id=user_id, limit=1)
                if not history:
                    # 这是第一条消息，自动生成标题
                    try:
                        title = await self._generate_title(message)
                        if title:
                            await self.session_store.update_session(
                                session_id=session_id,
                                title=title,
                                extend_ttl=False
                            )
                            # 更新session对象的title属性
                            session.title = title
                            logger.info(f"自动生成会话标题: {title}")
                    except Exception as e:
                        logger.warning(f"自动生成标题失败: {e}，将使用默认标题")

            # 2. 选择智能体（根据thinking_mode决定流程）
            intent = None  # 保存意图识别结果

            # 0. 如果指定了模型ID，先初始化LLM（使用指定的模型）
            # 尝试从context中获取数据库会话（如果有）
            db_session = context.get("db_session") if context else None
            if model_id:
                await self._get_or_create_llm(model_id, db_session)
            
            # 先判断 thinking_mode，只有专家模式才需要意图识别
            if thinking_mode == "expert":
                # 专家模式：需要意图识别和路由
                # 延迟初始化意图识别器
                if not self.intent_recognizer:
                    await self._get_or_create_llm(model_id, db_session)
                
                # 专家模式下，_select_agent_expert_mode 内部会进行意图识别（如果未提供）
                # 这里先进行意图识别，以便提前获取 reasoning_mode
                if hasattr(self, 'intent_recognizer') and self.intent_recognizer:
                    try:
                        intent = await self.intent_recognizer.recognize(message, context)
                        logger.info(f"意图识别完成: {intent.intent_type.value}, 推理模式: {intent.reasoning_mode.value}")
                    except Exception as e:
                        logger.warning(f"意图识别失败: {e}")
                
                # 专家模式：使用意图识别结果进行路由
                agent, intent = await self._select_agent_expert_mode(
                    message, context, agent_name, intent
                )
            else:
                # 普通模式和深度思考模式：直接选择agent，不进行意图识别
                agent = await self._select_agent_direct(agent_name)
            
            if not agent:
                return ChatResponse(
                    success=False,
                    response=None,
                    session_id=session_id,
                    error="没有可用的智能体"
                )

            # 3. 创建任务
            # 准备metadata，移除不可序列化的对象（如db_session）
            metadata_context = {}
            if context:
                metadata_context = {k: v for k, v in context.items() if k != "db_session"}
            
            task = Task(
                session_id=session_id,
                content=message,
                priority=TaskPriority.NORMAL,
                status=TaskStatus.PENDING,
                agent_id=agent.agent_id,
                metadata={
                    "user_id": user_id,
                    "agent_name": agent.agent_name,
                    "thinking_mode": thinking_mode,
                    "context": metadata_context
                }
            )

            # 4. 保存任务到数据库（通过task_queue）
            await self.task_queue.update_task(task)

            # 5. 执行任务
            # 构建执行上下文，包含 Intent 和 thinking_mode
            execution_context = session.context.copy() if session.context else {}
            execution_context["thinking_mode"] = thinking_mode
            
            # 将 Intent 传递给 Agent（核心改动：Agent 根据 Intent.reasoning_mode 选择执行方式）
            if intent:
                execution_context["intent"] = intent
                logger.info(f"传递意图给 Agent，推理模式: {intent.reasoning_mode.value}")
            
            # 如果提供了数据库会话，也添加到context中
            if context and "db_session" in context:
                execution_context["db_session"] = context.get("db_session")
            elif db_session:
                # 如果context中没有db_session，但chat_service有，也添加进去
                execution_context["db_session"] = db_session
            
            # 如果提供了图片，添加到execution_context中
            if images:
                execution_context["images"] = images
                logger.info(f"包含 {len(images)} 张图片，启用多模态分析")
            
            # 如果指定了模型ID，传递到execution_context中，让Agent使用指定的模型
            if model_id:
                execution_context["model_id"] = model_id
                # 确保db_session也在execution_context中（Agent需要它来查询模型信息）
                if "db_session" not in execution_context and db_session:
                    execution_context["db_session"] = db_session
                logger.info(f"传递模型ID到Agent: {model_id}")
            
            # 5. 执行任务
            # 注意：专家模式下，如果路由到协调Agent，协调Agent会处理Multi-Agent协作
            # 如果路由到单个Agent，该Agent会使用深度思考模式执行（通过thinking_mode="deep"传递）
            # 深度思考模式和普通模式直接执行
            task_result = await self.agent_executor.execute(
                agent=agent,
                task={
                    "message": message,
                    "session_id": session_id,
                    "task_id": task.task_id,
                    "images": images if images else None
                },
                context=execution_context
            )

            # 6. 处理任务结果
            # task_result 格式：
            # 成功: {"status": "completed", "result": {"success": True, "response": "...", ...}, ...}
            # 失败: {"status": "failed", "error": "...", ...}
            task_status = task_result.get("status", "")
            agent_result = task_result.get("result", {})
            
            # 更新任务状态
            if task_status == TaskStatus.COMPLETED.value:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                if isinstance(agent_result, dict):
                    task.result = agent_result
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error_message = task_result.get("error", "任务执行失败")
            
            # 保存任务状态到数据库
            await self.task_queue.update_task(task)
            
            # 提取响应内容
            if task_status == TaskStatus.COMPLETED.value:
                # 任务执行完成，从agent_result中提取response
                if isinstance(agent_result, dict):
                    response_text = agent_result.get("response", "")
                    agent_success = agent_result.get("success", True)
                    
                    if agent_success and response_text:
                        # 成功：更新会话历史
                        user_message = {
                            "role": "user",
                            "content": message
                        }
                        if images:
                            user_message["images"] = images
                        await self.session_store.add_history(
                            session_id=session_id,
                            user_id=user_id,
                            message=user_message
                        )
                        await self.session_store.add_history(
                            session_id=session_id,
                            user_id=user_id,
                            message={
                                "role": "assistant",
                                "content": response_text
                            }
                        )
                    else:
                        # Agent返回失败
                        error_msg = agent_result.get("error", "智能体执行失败")
                        user_message = {
                            "role": "user",
                            "content": message
                        }
                        if images:
                            user_message["images"] = images
                        await self.session_store.add_history(
                            session_id=session_id,
                            user_id=user_id,
                            message=user_message
                        )
                        await self.session_store.add_history(
                            session_id=session_id,
                            user_id=user_id,
                            message={
                                "role": "assistant",
                                "content": f"抱歉，处理失败: {error_msg}"
                            }
                        )
                else:
                    # result不是字典格式，直接使用
                    response_text = str(agent_result) if agent_result else ""
            else:
                # 任务执行失败
                error_msg = task_result.get("error", "任务执行失败")
                response_text = ""
                agent_success = False

            # 7. 获取会话历史并构建完整的对话历史
            # 先获取数据库中的历史记录
            history_data = await self.session_store.get_history(session_id, user_id=user_id, limit=50)
            
            # 构建历史记录列表（使用字典格式，避免序列化问题）
            history = [
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                    "images": msg.get("images"),  # 包含图片列表
                    "timestamp": msg.get("timestamp")
                }
                for msg in history_data
            ]
            
            # 确保历史记录包含当前对话的完整内容
            # 如果任务成功且有响应，检查并补充当前对话
            if task_status == TaskStatus.COMPLETED.value and response_text:
                # 检查历史记录的最后两条消息是否是当前对话
                # 如果最后一条是助手回复且内容匹配，说明当前对话已完整
                # 如果最后一条是用户消息且内容匹配，需要添加助手回复
                # 如果最后一条都不是，需要添加用户消息和助手回复
                last_msg = history[-1] if history else None
                second_last_msg = history[-2] if len(history) >= 2 else None
                
                # 判断当前对话是否已经在历史记录中
                current_conversation_complete = (
                    last_msg and 
                    last_msg.get("role") == "assistant" and 
                    last_msg.get("content") == response_text and
                    second_last_msg and
                    second_last_msg.get("role") == "user" and
                    second_last_msg.get("content") == message
                )
                
                if not current_conversation_complete:
                    # 当前对话不完整，需要补充
                    # 检查是否需要添加用户消息
                    if not last_msg or last_msg.get("content") != message or last_msg.get("role") != "user":
                        # 最后一条不是当前用户消息，需要添加
                        user_msg = {
                            "role": "user",
                            "content": message,
                            "timestamp": datetime.now().isoformat()
                        }
                        if images:
                            user_msg["images"] = images
                        history.append(user_msg)
                    
                    # 检查是否需要添加助手回复
                    last_msg = history[-1] if history else None
                    if not last_msg or last_msg.get("role") != "assistant" or last_msg.get("content") != response_text:
                        # 最后一条不是当前助手回复，需要添加
                        history.append({
                            "role": "assistant",
                            "content": response_text,
                            "timestamp": datetime.now().isoformat()
                        })

            # 8. 返回响应
            if task_status == TaskStatus.COMPLETED.value and response_text:
                return ChatResponse(
                    success=True,
                    response=response_text,
                    session_id=session_id,
                    agent_id=agent.agent_id,
                    history=history
                )
            else:
                # 失败情况
                error_message = task_result.get("error") or agent_result.get("error", "任务执行失败")
                return ChatResponse(
                    success=False,
                    response=None,
                    session_id=session_id,
                    agent_id=agent.agent_id,
                    error=error_message,
                    history=history
                )

        except Exception as e:
            logger.error(f"聊天处理失败: {e}")
            return ChatResponse(
                success=False,
                response=None,
                session_id=session_id or "unknown",
                error=f"服务器错误: {str(e)}"
            )

    async def create_session(
        self,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        创建新会话

        Args:
            user_id: 用户ID
            context: 上下文信息

        Returns:
            包含session_id和created_at的字典
        """
        session = await self.session_store.create_session(
            user_id=user_id,
            context=context
        )
        return {
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat()
        }

    async def get_session_history(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        获取会话历史

        Args:
            session_id: 会话ID
            user_id: 用户ID（用于验证会话所有权）
            limit: 返回数量限制

        Returns:
            包含历史记录的字典
        """
        # 验证会话是否属于当前用户
        session = await self.session_store.get_session(session_id)
        if not session:
            raise ValueError("会话不存在")
        if user_id and session.user_id != user_id:
            raise ValueError("无权访问此会话")
        
        history = await self.session_store.get_history(session_id, user_id=user_id, limit=limit)
        # 直接返回字典格式，避免序列化问题
        messages = [
            {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "images": msg.get("images"),  # 包含图片列表
                "timestamp": msg.get("timestamp")
            }
            for msg in history
        ]
        return {
            "session_id": session_id,
            "history": messages,
            "total": len(messages)
        }

    async def get_sessions(
        self,
        user_id: Optional[str] = None,
        active_only: bool = True
    ) -> Dict[str, Any]:
        """
        获取会话列表

        Args:
            user_id: 用户ID（可选）
            active_only: 是否只返回活跃会话

        Returns:
            包含会话列表的字典
        """
        if user_id:
            sessions = await self.session_store.get_user_sessions(user_id, active_only=active_only)
        else:
            # 如果没有指定用户ID，返回所有活跃会话
            sessions = await self.session_store.get_all_sessions(active_only=active_only, limit=100)
        
        # 构建会话列表
        session_list = []
        for session in sessions:
            # 使用会话的 title 字段，如果没有则从第一条消息生成
            title = session.title
            if not title:
                # 获取会话的第一条用户消息作为标题
                history = await self.session_store.get_history(session.session_id, limit=1)
                if history:
                    first_msg = history[0]
                    if first_msg.get("role") == "user":
                        content = first_msg.get("content", "")
                        # 取前30个字符作为标题
                        title = content[:30] + "..." if len(content) > 30 else content
                if not title:
                    title = "新对话"
            
            session_list.append({
                "session_id": session.session_id,
                "user_id": session.user_id,
                "title": title,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            })
        
        # 按更新时间排序（已经在数据库层面排序了，这里确保一下）
        session_list.sort(key=lambda x: x["updated_at"] or "", reverse=True)
        
        return {
            "sessions": session_list,
            "total": len(session_list)
        }

    async def update_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> bool:
        """
        更新会话信息

        Args:
            session_id: 会话ID
            user_id: 用户ID（用于验证会话所有权）
            title: 会话名称

        Returns:
            是否更新成功
        """
        # 验证会话是否属于当前用户
        if user_id:
            session = await self.session_store.get_session(session_id)
            if not session:
                return False
            if session.user_id != user_id:
                raise ValueError("无权访问此会话")
        
        return await self.session_store.update_session(
            session_id=session_id,
            title=title,
            extend_ttl=False  # 更新名称时不延长过期时间
        )

    async def delete_session(self, session_id: str, user_id: Optional[str] = None) -> bool:
        """
        删除会话（软删除）

        Args:
            session_id: 会话ID
            user_id: 用户ID（用于验证会话所有权）

        Returns:
            是否删除成功
        """
        # 验证会话是否属于当前用户
        if user_id:
            session = await self.session_store.get_session(session_id)
            if not session:
                return False
            if session.user_id != user_id:
                raise ValueError("无权访问此会话")
        
        return await self.session_store.deactivate_session(session_id)
    
    async def _select_agent_expert_mode(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
        agent_name: Optional[str],
        intent: Optional[Intent] = None
    ) -> Tuple[Optional[BaseAgent], Optional[Intent]]:
        """
        专家模式：意图识别和路由
        
        Args:
            message: 用户消息
            context: 上下文信息
            agent_name: 指定的agent名称（可选）
            intent: 已识别的意图（可选，如果未提供则进行识别）
            
        Returns:
            (选择的Agent实例, 意图识别结果) 元组
        """
        try:
            # 1. 如果没有提供 intent，进行意图识别
            if not intent:
                # 延迟初始化意图识别器
                if not self.intent_recognizer:
                    await self._get_or_create_llm()
                
                if not self.intent_recognizer:
                    logger.warning("意图识别器未初始化，降级到直接选择agent")
                    agent = await self._select_agent_direct(agent_name)
                    return agent, None
                
                intent = await self.intent_recognizer.recognize(message, context)
            
            logger.info(f"意图识别结果: {intent.intent_type.value}, 需要Multi-Agent: {intent.metadata.get('requires_multi_agent', False)}, 推理模式: {intent.reasoning_mode.value}")
            
            # 2. 判断是否需要Multi-Agent
            requires_multi_agent = intent.metadata.get("requires_multi_agent", False)
            
            if requires_multi_agent:
                # 需要Multi-Agent：路由到协调Agent
                logger.info("任务需要Multi-Agent协作，路由到协调Agent")
                coordinators = await self.agent_registry.get_available_agents(
                    agent_type="coordinator"
                )
                if coordinators:
                    return coordinators[0], intent
                else:
                    logger.warning("未找到协调Agent，降级到直接路由")
                    # 降级：使用意图路由
                    # 确保意图路由器已初始化
                    if not self.intent_router:
                        await self._get_or_create_llm()
                    
                    if self.intent_router:
                        route = await self.intent_router.route(intent)
                        if route and route.target_agent_id:
                            agent = await self.agent_registry.get_agent(route.target_agent_id)
                            return agent, intent
                    agent = await self._select_agent_direct(agent_name)
                    return agent, intent
            else:
                # 不需要Multi-Agent：直接路由到目标agent（不使用协调Agent）
                logger.info("任务不需要Multi-Agent协作，直接路由到目标agent")
                
                # 如果指定了agent_name，优先使用
                if agent_name:
                    all_agents = await self.agent_registry.get_all_agents()
                    for a in all_agents:
                        if a.agent_name == agent_name:
                            logger.info(f"使用指定的agent: {agent_name}")
                            return a, intent
                
                # 使用LLM进行智能路由（优先）
                # 确保意图路由器已初始化
                if not self.intent_router:
                    await self._get_or_create_llm()
                
                if self.intent_router and self.intent_router.llm:
                    logger.info("使用LLM进行智能路由")
                    try:
                        route = await self.intent_router._llm_route(intent)
                        if route and route.target_agent_id:
                            target_agent = await self.agent_registry.get_agent(route.target_agent_id)
                            if target_agent:
                                logger.info(f"LLM路由到: {target_agent.agent_name} ({target_agent.agent_id}), 原因: {route.routing_reason}")
                                return target_agent, intent
                        logger.warning("LLM路由失败，降级到规则路由")
                    except Exception as e:
                        logger.warning(f"LLM路由异常: {e}，降级到规则路由")
                
                # 降级：根据意图类型直接路由
                target_agent = await self._route_by_intent_type(intent)
                if target_agent:
                    logger.info(f"根据意图类型路由到: {target_agent.agent_name} ({target_agent.agent_id})")
                    return target_agent, intent
                
                # 降级：使用默认智能助手
                agent = await self._select_agent_direct(None)
                return agent, intent
                
        except Exception as e:
            logger.error(f"专家模式选择agent失败: {e}", exc_info=True)
            # 降级到直接选择
            agent = await self._select_agent_direct(agent_name)
            return agent, None
    
    async def _route_by_intent_type(self, intent) -> Optional[BaseAgent]:
        """
        根据意图类型直接路由到目标agent（不经过协调Agent）
        
        Args:
            intent: 意图对象
            
        Returns:
            Agent实例，如果未找到则返回None
        """
        from core.component.intent.intent_models import IntentType
        
        intent_type = intent.intent_type
        original_text_lower = intent.original_text.lower()
        
        # 优先检查飞书相关任务（即使意图类型不是FEISHU_OPERATION，也要检查关键词）
        feishu_keywords = ["飞书", "feishu", "任务", "审批", "联系人", "日程", "文档", "多维表格", "bitable"]
        feishu_operation_patterns = [
            "创建任务", "更新任务", "删除任务", "完成任务",
            "创建审批", "提交审批", "审批流程",
            "创建日程", "更新日程", "删除日程",
            "创建文档", "更新文档", "删除文档",
            "创建联系人", "更新联系人", "删除联系人"
        ]
        
        # 如果包含飞书关键词或操作模式，优先路由到飞书助手
        if (any(keyword in original_text_lower for keyword in feishu_keywords) or
            any(pattern in original_text_lower for pattern in feishu_operation_patterns)):
            agents = await self.agent_registry.get_available_agents(agent_type="feishu_assistant")
            if agents:
                logger.info(f"检测到飞书相关任务，路由到飞书助手")
                return agents[0]
        
        # 根据意图类型映射到agent类型
        intent_agent_mapping = {
            IntentType.FEISHU_OPERATION: "feishu_assistant",
            IntentType.SEARCH: "intelligent_assistant",
            IntentType.ANALYSIS: "intelligent_assistant",
            IntentType.CALCULATION: "intelligent_assistant",
            IntentType.CODE_GENERATION: "intelligent_assistant",
            IntentType.QUESTION: "intelligent_assistant",
            IntentType.GREETING: "intelligent_assistant",
        }
        
        agent_type = intent_agent_mapping.get(intent_type)
        if agent_type:
            agents = await self.agent_registry.get_available_agents(agent_type=agent_type)
            if agents:
                return agents[0]
        
        return None
    
    async def _select_agent_direct(
        self,
        agent_name: Optional[str]
    ):
        """
        直接选择agent（深度思考模式和普通模式）
        
        Args:
            agent_name: 指定的agent名称（可选）
            
        Returns:
            Agent实例，如果未找到则返回None
        """
        # 根据agent_name查找智能体
        if agent_name:
            all_agents = await self.agent_registry.get_all_agents()
            for a in all_agents:
                if a.agent_name == agent_name:
                    logger.info(f"根据agent_name找到智能体: {agent_name} ({a.agent_id})")
                    return a
            
            logger.warning(f"未找到指定名称的智能体: {agent_name}，将使用默认智能助手")
        
        # 如果没有找到智能体，使用默认的智能助手
        agents = await self.agent_registry.get_available_agents(
            agent_type="intelligent_assistant"
        )
        if agents:
            agent = agents[0]
            logger.info(f"使用默认智能助手: {agent.agent_id} ({agent.agent_name})")
            return agent
        
        return None

    async def _generate_title(self, user_message: str) -> Optional[str]:
        """
        根据用户输入自动生成对话标题
        
        Args:
            user_message: 用户消息内容
            
        Returns:
            生成的标题，如果生成失败则返回None
        """
        # 获取或创建LLM实例
        llm = await self._get_or_create_llm()
        if not llm:
            logger.warning("LLM未初始化，无法生成标题")
            return None
        
        try:
            # 构建生成标题的提示词
            prompt = f"""请根据以下用户消息，生成一个简洁、准确的对话标题。

要求：
1. 标题应该简洁明了，不超过20个字符
2. 标题应该准确概括用户消息的主要内容
3. 只返回标题内容，不要包含其他说明文字
4. 如果用户消息是问候语（如"你好"、"在吗"等），返回"新对话"

用户消息：
{user_message}

标题："""
            
            # 调用LLM生成标题
            try:
                # 尝试使用异步调用
                if hasattr(llm, 'ainvoke'):
                    title = await llm.ainvoke(prompt)
                else:
                    # 如果没有异步方法，使用线程池执行同步调用
                    import asyncio
                    loop = asyncio.get_event_loop()
                    title = await loop.run_in_executor(None, llm._call, prompt)
            except AttributeError:
                # 如果都没有，直接调用同步方法
                title = llm._call(prompt)
            
            # 清理标题：去除首尾空白，限制长度
            if title:
                title = title.strip()
                # 移除可能的引号
                if title.startswith('"') and title.endswith('"'):
                    title = title[1:-1]
                elif title.startswith("'") and title.endswith("'"):
                    title = title[1:-1]
                # 限制长度
                if len(title) > 30:
                    title = title[:30]
                return title if title else None
            
            return None
            
        except Exception as e:
            logger.error(f"生成标题时出错: {e}", exc_info=True)
            return None

