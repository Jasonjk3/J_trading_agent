#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
思考模式混入类
提供通用的思考模式执行方法（CoT、ReAct、普通模式）
"""
from typing import Any, Dict, Optional
from loguru import logger
import json

from core.component.executor.task_planner import TaskPlanner
from core.component.executor.thought_executor import ThoughtExecutor
from core.component.executor.react_executor import ReActExecutor
from core.component.intent.intent_models import Intent, ReasoningMode
from core.infrastructure.persistence.chain_of_thought_service import ChainOfThoughtService
from core.llm.base.base_llm import BaseLLM
from core.tools.base.base_tool import BaseTool
from core.agent_mixin.mixin_utils import (
    build_agent_result,
)


class ThinkingModeMixin:
    """
    思考模式混入类 - 提供通用的思考模式执行方法
    
    支持三种推理模式：
    - NONE: 普通模式，直接调用 LLM
    - REACT: ReAct 模式，交替进行推理和行动
    - COT: Chain of Thought 模式，任务规划 + 思维链执行
    """
    
    # ==================== 初始化 ====================
    
    def _init_thinking_components(
        self, 
        llm: Optional[BaseLLM], 
        tools: Dict[str, BaseTool],
        system_prompt: Optional[str] = None
    ):
        """
        初始化思维链组件
        
        Args:
            llm: LLM实例
            tools: 工具字典
            system_prompt: Agent的系统提示词（用于构建上下文背景）
        """
        self.task_planner = None
        self.thought_executor = None
        self.react_executor = None
        self._thinking_system_prompt = system_prompt
        
        if llm:
            self.task_planner = TaskPlanner(llm, tools)
            self.thought_executor = ThoughtExecutor(llm, tools, system_prompt=system_prompt)
            self.react_executor = ReActExecutor(llm, tools, system_prompt=system_prompt)
    
    def _update_thinking_tools(self, tools: Dict[str, BaseTool]):
        """更新思维链组件中的工具"""
        if self.task_planner:
            self.task_planner.tools = tools
        if self.thought_executor:
            self.thought_executor.tools = tools
        if self.react_executor:
            self.react_executor.tools = tools
    
    def _update_thinking_system_prompt(self, system_prompt: str):
        """
        更新思维链组件中的系统提示词
        
        Args:
            system_prompt: 新的系统提示词
        """
        self._thinking_system_prompt = system_prompt
        if self.thought_executor:
            self.thought_executor.system_prompt = system_prompt
        if self.react_executor:
            self.react_executor.system_prompt = system_prompt
    
    def _init_chain_service(self, context: Optional[Dict[str, Any]]):
        """初始化思维链服务"""
        if context and "db_session" in context:
            from sqlalchemy.ext.asyncio import AsyncSession
            db_session = context.get("db_session")
            if isinstance(db_session, AsyncSession):
                chain_service = ChainOfThoughtService(db_session)
                if self.task_planner:
                    self.task_planner.chain_service = chain_service
                if self.thought_executor:
                    self.thought_executor.chain_service = chain_service
                if self.react_executor:
                    self.react_executor.chain_service = chain_service
    
    # ==================== 主入口 ====================
    
    async def _execute_by_intent(
        self,
        task: Dict[str, Any],
        message: str,
        session_id: str,
        intent: Optional[Intent] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        根据 Intent 的 reasoning_mode 选择执行方式
        
        Args:
            task: 任务内容
            message: 用户消息
            session_id: 会话ID
            intent: 意图对象（包含 reasoning_mode）
            context: 上下文信息
            
        Returns:
            执行结果
        """
        # 获取推理模式
        if intent:
            reasoning_mode = intent.reasoning_mode
        else:
            mode_str = context.get("reasoning_mode", "none") if context else "none"
            reasoning_mode = ReasoningMode(mode_str) if mode_str in [m.value for m in ReasoningMode] else ReasoningMode.NONE
        
        logger.info(f"根据意图执行任务，推理模式: {reasoning_mode.value}")
        
        # 根据推理模式选择执行方式
        if reasoning_mode == ReasoningMode.NONE:
            return await self._execute_normal_mode(task, message, session_id, context)
        elif reasoning_mode == ReasoningMode.REACT:
            return await self._execute_react_mode(task, message, session_id, context)
        elif reasoning_mode == ReasoningMode.COT:
            return await self._execute_cot_mode(task, message, session_id, context)
        else:
            return await self._execute_normal_mode(task, message, session_id, context)
    
    # ==================== 三种执行模式 ====================
    
    async def _execute_normal_mode(
        self,
        task: Dict[str, Any],
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """普通模式：直接调用 LLM，不处理工具调用"""
        try:
            history = getattr(self, 'conversation_history', {}).get(session_id, [])
            messages = self._build_messages(message, history)
            response = await self._call_llm_with_messages(messages)
            
            # 普通模式：直接返回 LLM 结果，不处理工具调用
            # 如果需要工具调用，应使用深度思考模式（ReAct 或 CoT）
            
            return build_agent_result(
                self,
                success=True,
                response=response,
                session_id=session_id,
                reasoning_mode="none"
            )
        except Exception as e:
            logger.error(f"普通模式执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e), "session_id": session_id}
    
    async def _execute_react_mode(
        self,
        task: Dict[str, Any],
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """ReAct 模式：交替进行推理和行动"""
        try:
            self._init_chain_service(context)
            
            logger.info("使用 ReAct 模式执行任务")
            response = await self._execute_with_react(
                message, session_id, context, task.get("task_id")
            )
            
            return build_agent_result(
                self,
                success=True,
                response=response,
                session_id=session_id,
                reasoning_mode="react"
            )
        except Exception as e:
            logger.error(f"ReAct 模式执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e), "session_id": session_id}
    
    async def _execute_cot_mode(
        self,
        task: Dict[str, Any],
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """CoT 模式：任务规划 + 思维链执行"""
        try:
            self._init_chain_service(context)
            
            logger.info("使用 CoT 模式执行任务")
            response = await self._execute_with_chain_of_thought(
                message, session_id, context, task.get("task_id")
            )
            
            return build_agent_result(
                self,
                success=True,
                response=response,
                session_id=session_id,
                reasoning_mode="cot"
            )
        except Exception as e:
            logger.error(f"CoT 模式执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e), "session_id": session_id}
    
    # ==================== 兼容旧逻辑 ====================
    
    async def _execute_deep_thinking_mode(
        self,
        task: Dict[str, Any],
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        深度思考模式（兼容旧逻辑）
        
        根据 context 中的 reasoning_mode 选择使用 CoT 或 ReAct
        """
        # 默认值根据 Agent 类型决定
        agent_type = getattr(self, 'agent_type', '')
        default_mode = "react" if agent_type == "feishu_assistant" else "cot"
        reasoning_mode = context.get("reasoning_mode", default_mode) if context else default_mode
        
        if reasoning_mode == "react":
            return await self._execute_react_mode(task, message, session_id, context)
        else:
            return await self._execute_cot_mode(task, message, session_id, context)
    
    # ==================== 底层实现 ====================
    
    async def _execute_with_react(
        self,
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ) -> str:
        """使用 ReAct 执行任务"""
        try:
            if not self.react_executor:
                logger.warning("ReAct 执行器未初始化，降级到 CoT 模式")
                return await self._execute_with_chain_of_thought(message, session_id, context, task_id)
            
            logger.info("开始 ReAct 执行...")
            response = await self.react_executor.execute(
                task=message,
                session_id=session_id,
                context=context,
                task_id=task_id
            )
            
            logger.info("ReAct 执行完成")
            return response
                
        except Exception as e:
            logger.error(f"ReAct 执行异常: {e}", exc_info=True)
            return f"抱歉，执行过程中出现异常：{str(e)}"
    
    async def _execute_with_chain_of_thought(
        self,
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ) -> str:
        """使用思维链执行任务"""
        try:
            if not self.task_planner or not self.thought_executor:
                logger.warning("思维链组件未初始化，降级到普通模式")
                history = getattr(self, 'conversation_history', {}).get(session_id, [])
                messages = self._build_messages(message, history)
                response = await self._call_llm_with_messages(messages)
                
                # 降级到普通模式：直接返回 LLM 结果，不处理工具调用
                return response
            
            # 1. 规划任务
            logger.info("开始规划任务...")
            chain = await self.task_planner.plan(
                task=message,
                session_id=session_id,
                context=context,
                task_id=task_id
            )
            
            if chain.status == "failed":
                logger.error(f"任务规划失败: {chain.error}")
                return f"抱歉，任务规划失败：{chain.error}"
            
            # 2. 执行思维链
            logger.info(f"开始执行思维链，共 {len(chain.steps)} 个步骤...")
            chain = await self.thought_executor.execute(chain)
            
            # 3. 返回结果
            if chain.status == "completed" and chain.final_result:
                logger.info("思维链执行完成")
                return chain.final_result
            elif chain.status == "failed":
                logger.error(f"思维链执行失败: {chain.error}")
                # 从已完成的步骤中获取部分结果，而不是从中间结果
                completed_steps = chain.get_completed_steps()
                if completed_steps:
                    partial_results = {}
                    for step in completed_steps:
                        if step.result:
                            partial_results[f"步骤{step.step_number}"] = step.result
                    if partial_results:
                        return f"任务执行过程中出现错误：{chain.error}\n\n部分结果：{json.dumps(partial_results, ensure_ascii=False, indent=2)}"
                return f"抱歉，任务执行失败：{chain.error}"
            else:
                progress = chain.get_progress()
                return f"任务执行中，当前进度：{progress:.0%}\n\n已完成步骤：{len(chain.get_completed_steps())}/{len(chain.steps)}"
                
        except Exception as e:
            logger.error(f"思维链执行异常: {e}", exc_info=True)
            return f"抱歉，执行过程中出现异常：{str(e)}"
