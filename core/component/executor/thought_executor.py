#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
思维链执行器
执行思维链中的各个步骤
"""
import asyncio
import json
from typing import Any, Dict, Optional
from datetime import datetime, date
from loguru import logger

from core.models.chain_of_thought import (
    ChainOfThought,
    ThoughtStep,
    ThoughtStatus,
    ThoughtType
)
from core.component.registry.agent_registry import AgentRegistry
from core.models.agent_message import MessageBus, AgentMessage, MessageType
from core.infrastructure.persistence.chain_of_thought_service import ChainOfThoughtService
from core.llm.base.base_llm import BaseLLM
from core.tools.base.base_tool import BaseTool


class ThoughtExecutor:
    """思维链执行器"""

    def __init__(
        self,
        llm: BaseLLM,
        tools: Optional[Dict[str, BaseTool]] = None,
        max_iterations: int = 10,
        chain_service: Optional[ChainOfThoughtService] = None,
        agent_registry: Optional[AgentRegistry] = None,
        message_bus: Optional[MessageBus] = None,
        current_agent_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        step_timeout_seconds: int = 120,
        llm_timeout_seconds: int = 60
    ):
        """
        初始化思维链执行器
        
        Args:
            llm: LLM实例
            tools: 可用工具字典
            max_iterations: 最大迭代次数
            chain_service: 思维链数据库服务（可选）
            agent_registry: Agent注册中心（Multi-Agent支持）
            message_bus: 消息总线（Multi-Agent支持）
            current_agent_id: 当前Agent ID（Multi-Agent支持）
            system_prompt: Agent的系统提示词（用于构建上下文背景）
            step_timeout_seconds: 单个步骤执行超时时间（秒），默认120秒
            llm_timeout_seconds: LLM调用超时时间（秒），默认60秒
        """
        self.llm = llm
        self.tools = tools or {}
        self.max_iterations = max_iterations
        self.chain_service = chain_service
        self.agent_registry = agent_registry
        self.message_bus = message_bus
        self.current_agent_id = current_agent_id
        self.system_prompt = system_prompt
        self.step_timeout_seconds = step_timeout_seconds
        self.llm_timeout_seconds = llm_timeout_seconds

    async def execute(self, chain: ChainOfThought) -> ChainOfThought:
        """
        执行思维链
        
        Args:
            chain: 思维链对象
            
        Returns:
            执行完成后的思维链
        """
        try:
            chain.status = "executing"
            
            # 记录执行开始
            if self.chain_service:
                await self.chain_service.save_chain(chain)
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="execution_start",
                    message=f"开始执行思维链，共 {len(chain.steps)} 个步骤",
                    log_level="info",
                    details={"steps_count": len(chain.steps), "max_iterations": self.max_iterations}
                )
            
            iteration = 0
            
            while iteration < self.max_iterations:
                # 获取下一个可执行的步骤
                next_step = chain.get_next_executable_step()
                
                # 添加调试日志
                if next_step:
                    logger.debug(f"找到可执行步骤: {next_step.step_number} ({next_step.description}), 状态: {next_step.status.value}")
                else:
                    # 记录所有步骤的状态，用于调试
                    step_statuses = {step.step_number: step.status.value for step in chain.steps}
                    logger.debug(f"未找到可执行步骤，当前步骤状态: {step_statuses}")
                
                if not next_step:
                    # 检查是否所有步骤都已完成
                    if chain.is_completed():
                        chain.status = "completed"
                        chain.completed_at = chain.updated_at
                        logger.info(f"思维链执行完成: {chain.thought_id}")
                        
                        # 记录执行完成
                        if self.chain_service:
                            await self.chain_service.save_chain(chain)
                            await self.chain_service.log_event(
                                thought_id=chain.thought_id,
                                log_type="execution_complete",
                                message=f"思维链执行完成，共执行 {iteration} 次迭代",
                                log_level="info",
                                details={"iterations": iteration, "progress": chain.get_progress()}
                            )
                        break
                    else:
                        # 有步骤失败或无法执行
                        chain.status = "failed"
                        chain.error = "存在无法执行的步骤"
                        logger.warning(f"思维链执行失败: {chain.thought_id}, {chain.error}")
                        
                        # 记录执行失败
                        if self.chain_service:
                            await self.chain_service.save_chain(chain)
                            await self.chain_service.log_event(
                                thought_id=chain.thought_id,
                                log_type="execution_failed",
                                message=f"思维链执行失败: {chain.error}",
                                log_level="error",
                                details={"error": chain.error, "iterations": iteration}
                            )
                        break
                
                # 执行步骤前，再次检查步骤状态（防止重复执行）
                current_step = chain.get_step(next_step.step_number)
                if not current_step:
                    logger.error(f"步骤 {next_step.step_number} 不存在，跳过执行")
                    iteration += 1
                    continue
                
                if current_step.status != ThoughtStatus.PENDING:
                    logger.warning(f"步骤 {next_step.step_number} 状态不是 PENDING (当前: {current_step.status.value})，跳过执行")
                    iteration += 1
                    continue
                
                # 执行步骤（带超时控制）
                try:
                    await asyncio.wait_for(
                        self._execute_step(chain, current_step),
                        timeout=self.step_timeout_seconds
                    )
                except asyncio.TimeoutError:
                    logger.error(f"步骤 {current_step.step_number} 执行超时（{self.step_timeout_seconds}秒）")
                    chain.update_step_status(
                        current_step.step_number, 
                        ThoughtStatus.FAILED, 
                        error=f"步骤执行超时（{self.step_timeout_seconds}秒）"
                    )
                    # 记录超时事件
                    if self.chain_service:
                        await self.chain_service.log_event(
                            thought_id=chain.thought_id,
                            log_type="step_timeout",
                            message=f"步骤 {current_step.step_number} 执行超时",
                            log_level="error",
                            step_id=current_step.step_id,
                            details={
                                "step_number": current_step.step_number,
                                "timeout_seconds": self.step_timeout_seconds
                            }
                        )
                
                # 保存进度
                if self.chain_service:
                    await self.chain_service.save_chain(chain)
                
                iteration += 1
            
            if iteration >= self.max_iterations:
                chain.status = "failed"
                chain.error = f"达到最大迭代次数: {self.max_iterations}"
                logger.warning(f"思维链执行超时: {chain.thought_id}")
                
                # 记录超时
                if self.chain_service:
                    await self.chain_service.save_chain(chain)
                    await self.chain_service.log_event(
                        thought_id=chain.thought_id,
                        log_type="execution_timeout",
                        message=f"思维链执行超时，达到最大迭代次数: {self.max_iterations}",
                        log_level="warning",
                        details={"max_iterations": self.max_iterations, "progress": chain.get_progress()}
                    )
            
            # 生成最终结果
            if chain.status == "completed":
                if self.chain_service:
                    await self.chain_service.log_event(
                        thought_id=chain.thought_id,
                        log_type="result_synthesis_start",
                        message="开始综合最终结果",
                        log_level="info"
                    )
                
                chain.final_result = await self._synthesize_result(chain)
                
                if self.chain_service:
                    await self.chain_service.save_chain(chain)
                    await self.chain_service.log_event(
                        thought_id=chain.thought_id,
                        log_type="result_synthesis_complete",
                        message="最终结果综合完成",
                        log_level="info",
                        details={"result_length": len(str(chain.final_result)) if chain.final_result else 0}
                    )
            
            return chain
            
        except Exception as e:
            logger.error(f"思维链执行异常: {e}", exc_info=True)
            chain.status = "failed"
            chain.error = str(e)
            return chain

    async def _execute_step(self, chain: ChainOfThought, step: ThoughtStep):
        """
        执行单个思维步骤
        
        Args:
            chain: 思维链对象
            step: 思维步骤
        """
        try:
            logger.info(f"执行步骤 {step.step_number}: {step.description}")
            
            # 记录步骤开始
            if self.chain_service:
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="step_start",
                    message=f"开始执行步骤 {step.step_number}: {step.description}",
                    log_level="info",
                    step_id=step.step_id,
                    details={
                        "step_number": step.step_number,
                        "thought_type": step.thought_type.value,
                        "dependencies": step.dependencies
                    }
                )
            
            chain.update_step_status(step.step_number, ThoughtStatus.EXECUTING)
            chain.current_step = step.step_number
            
            # 根据步骤类型执行
            if step.thought_type == ThoughtType.AGENT_EXECUTION:
                # Multi-Agent执行：将任务发送给其他Agent
                logger.info(f"步骤 {step.step_number} 是Agent执行步骤:")
                logger.info(f"  - 分配的Agent ID: {step.assigned_agent_id}")
                logger.info(f"  - Agent类型: {step.assigned_agent_type}")
                logger.info(f"  - 关联子任务ID: {step.subtask_id}")
                logger.info(f"  - 任务描述: {step.description}")
                result = await self._execute_agent_task(chain, step)
            elif step.thought_type == ThoughtType.TASK_DECOMPOSITION:
                # 任务分解步骤（通常由协调Agent处理）
                result = await self._execute_task_decomposition(chain, step)
            elif step.thought_type == ThoughtType.RESULT_INTEGRATION:
                # 结果整合步骤
                result = await self._execute_result_integration(chain, step)
            elif step.thought_type == ThoughtType.TOOL_CALL:
                result = await self._execute_tool_call(chain, step)
            elif step.thought_type == ThoughtType.ANALYSIS:
                result = await self._execute_analysis(chain, step)
            elif step.thought_type == ThoughtType.REASONING:
                result = await self._execute_reasoning(chain, step)
            elif step.thought_type == ThoughtType.DECISION:
                result = await self._execute_decision(chain, step)
            elif step.thought_type == ThoughtType.SYNTHESIS:
                result = await self._execute_synthesis(chain, step)
            elif step.thought_type == ThoughtType.VALIDATION:
                result = await self._execute_validation(chain, step)
            else:
                result = await self._execute_reasoning(chain, step)
            
            # 保存结果
            # 如果步骤被跳过（如Agent路由步骤不需要路由），标记为SKIPPED
            if isinstance(result, dict) and result.get("skipped"):
                chain.update_step_status(step.step_number, ThoughtStatus.SKIPPED, result=result)
                logger.info(f"步骤 {step.step_number} 被跳过")
            else:
                chain.update_step_status(step.step_number, ThoughtStatus.COMPLETED, result=result)
                result_preview = str(result)[:200] if result else "无结果"
                logger.info(f"步骤 {step.step_number} 执行完成，结果预览: {result_preview}...")
            # 注意：不再存储中间结果，因为步骤结果已经存储在 step.result 中
            # 这样可以避免上下文过长和重复数据的问题
            
            # 记录步骤完成
            if self.chain_service:
                result_preview = str(result)[:200] if result else None
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="step_complete",
                    message=f"步骤 {step.step_number} 执行完成",
                    log_level="info",
                    step_id=step.step_id,
                    details={
                        "step_number": step.step_number,
                        "result_preview": result_preview,
                        "has_result": result is not None
                    }
                )
            
        except Exception as e:
            logger.error(f"步骤 {step.step_number} 执行失败: {e}", exc_info=True)
            chain.update_step_status(step.step_number, ThoughtStatus.FAILED, error=str(e))
            
            # 记录步骤失败
            if self.chain_service:
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="step_error",
                    message=f"步骤 {step.step_number} 执行失败: {str(e)}",
                    log_level="error",
                    step_id=step.step_id,
                    details={
                        "step_number": step.step_number,
                        "error": str(e),
                        "thought_type": step.thought_type.value
                    }
                )
            
            # 根据错误决定是否继续
            # 如果步骤是关键的，可能需要停止整个思维链
            if step.thought_type in [ThoughtType.DECISION, ThoughtType.VALIDATION]:
                chain.status = "failed"
                chain.error = f"关键步骤失败: {step.description}"
    
    async def _execute_tool_call(self, chain: ChainOfThought, step: ThoughtStep) -> Any:
        """
        执行工具调用
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            工具执行结果
        """
        if not step.tool_name:
            raise ValueError("工具调用步骤缺少工具名称")
        
        if step.tool_name not in self.tools:
            raise ValueError(f"工具不存在: {step.tool_name}")
        
        tool = self.tools[step.tool_name]
        parameters = step.tool_parameters or {}
        
        # 如果参数中包含对之前步骤结果的引用，进行替换
        parameters = self._resolve_parameters(chain, parameters)
        
        logger.info(f"调用工具: {step.tool_name}, 参数: {parameters}")
        
        # 记录工具调用
        if self.chain_service:
            await self.chain_service.log_event(
                thought_id=chain.thought_id,
                log_type="tool_call",
                message=f"调用工具: {step.tool_name}",
                log_level="info",
                step_id=step.step_id,
                details={
                    "tool_name": step.tool_name,
                    "parameters": parameters
                }
            )
        
        result = await tool.execute(**parameters)
        
        # 记录工具调用结果
        if self.chain_service:
            result_preview = str(result)[:500] if result else None
            await self.chain_service.log_event(
                thought_id=chain.thought_id,
                log_type="tool_call_result",
                message=f"工具 {step.tool_name} 执行完成",
                log_level="info",
                step_id=step.step_id,
                details={
                    "tool_name": step.tool_name,
                    "result_preview": result_preview,
                    "has_result": result is not None
                }
            )
        
        return result

    async def _execute_analysis(self, chain: ChainOfThought, step: ThoughtStep) -> str:
        """
        执行分析步骤
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            分析结果
        """
        # 获取相关步骤的结果
        context = self._build_step_context(chain, step)
        
        prompt = f"""请分析以下信息：

任务目标：{chain.goal}
当前步骤：{step.description}

相关上下文：
{context}

**重要要求：**
1. 输出要简洁，只包含核心结论，不要废话
2. 控制在200字以内
3. 直接给出分析结果，不要重复问题或上下文
4. 使用要点形式，避免冗长描述

请进行深入分析，并给出简洁的分析结果。"""
        
        result = await self._call_llm(prompt)
        step.reasoning = result
        return result

    async def _execute_reasoning(self, chain: ChainOfThought, step: ThoughtStep) -> str:
        """
        执行推理步骤
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            推理结果
        """
        context = self._build_step_context(chain, step)
        
        prompt = f"""请进行推理：

任务目标：{chain.goal}
当前步骤：{step.description}

相关上下文：
{context}

**重要要求：**
1. 输出要简洁，只包含核心推理结论，不要冗长的推理过程
2. 控制在200字以内
3. 直接给出结论，简要说明关键推理点即可
4. 避免重复上下文或问题描述

请进行逻辑推理，并给出简洁的推理结论。"""
        
        result = await self._call_llm(prompt)
        result = self._truncate_result(result, max_length=200)
        step.reasoning = result
        return result

    async def _execute_decision(self, chain: ChainOfThought, step: ThoughtStep) -> Dict[str, Any]:
        """
        执行决策步骤
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            决策结果
        """
        context = self._build_step_context(chain, step)
        
        prompt = f"""请做出决策：

任务目标：{chain.goal}
当前步骤：{step.description}

相关上下文：
{context}

**重要要求：**
1. 决策内容要简洁明确，控制在50字以内
2. 决策理由要精炼，控制在100字以内
3. 后续步骤要具体，每个步骤描述控制在20字以内
4. 不要废话，只包含核心信息

请分析各种选项，做出决策，并以JSON格式返回：
{{
    "decision": "决策内容（50字以内）",
    "reasoning": "决策理由（100字以内）",
    "next_steps": ["后续步骤1（20字以内）", "后续步骤2（20字以内）"]
}}

只返回JSON，不要返回其他内容。"""
        
        response = await self._call_llm(prompt)
        decision = self._parse_json_response(response)
        step.reasoning = decision.get("reasoning", "")
        return decision

    async def _execute_synthesis(self, chain: ChainOfThought, step: ThoughtStep) -> str:
        """
        执行综合步骤
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            综合结果
        """
        context = self._build_step_context(chain, step)
        
        prompt = f"""请综合以下信息：

任务目标：{chain.goal}
当前步骤：{step.description}

相关上下文：
{context}

**重要要求：**
1. 输出要简洁，只包含核心结论，不要重复上下文
2. 控制在300字以内
3. 使用要点形式，避免冗长描述
4. 直接给出综合结果，不要废话

请综合所有信息，生成简洁的最终结果。"""
        
        result = await self._call_llm(prompt)
        result = self._truncate_result(result, max_length=300)
        return result

    async def _execute_validation(self, chain: ChainOfThought, step: ThoughtStep) -> Dict[str, Any]:
        """
        执行验证步骤
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            验证结果
        """
        context = self._build_step_context(chain, step)
        
        prompt = f"""请验证以下内容：

任务目标：{chain.goal}
当前步骤：{step.description}

相关上下文：
{context}

**重要要求：**
1. 问题描述要简洁，每个问题控制在30字以内
2. 建议要具体，每个建议控制在30字以内
3. 如果没有问题或建议，使用空数组[]
4. 不要废话，只包含核心信息

请验证结果的正确性和完整性，并以JSON格式返回：
{{
    "valid": true/false,
    "issues": ["问题1（30字以内）", "问题2（30字以内）"],
    "suggestions": ["建议1（30字以内）", "建议2（30字以内）"]
}}

只返回JSON，不要返回其他内容。"""
        
        response = await self._call_llm(prompt)
        validation = self._parse_json_response(response)
        # 截断各个字段
        if "issues" in validation and isinstance(validation["issues"], list):
            validation["issues"] = [self._truncate_result(issue, max_length=30) for issue in validation["issues"]]
        if "suggestions" in validation and isinstance(validation["suggestions"], list):
            validation["suggestions"] = [self._truncate_result(suggestion, max_length=30) for suggestion in validation["suggestions"]]
        return validation

    def _build_step_context(self, chain: ChainOfThought, step: ThoughtStep, max_length: int = 8000) -> str:
        """
        构建步骤上下文（限制长度以避免过长导致LLM处理慢）
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            max_length: 上下文最大长度（字符数），默认8000
            
        Returns:
            上下文字符串
        """
        context_parts = []
        current_length = 0
        
        # 添加依赖步骤的结果
        for dep_step_num in step.dependencies:
            dep_step = chain.get_step(dep_step_num)
            if dep_step and dep_step.result:
                result_str = json.dumps(dep_step.result, ensure_ascii=False, indent=2, default=self._json_serializer)
                step_context = f"步骤 {dep_step_num} 的结果：\n{result_str}"
                
                # 检查长度限制
                if current_length + len(step_context) > max_length:
                    # 如果超过限制，截断并添加提示
                    remaining = max_length - current_length - 100
                    if remaining > 0:
                        context_parts.append(step_context[:remaining] + "\n...（内容已截断）")
                    break
                
                context_parts.append(step_context)
                current_length += len(step_context)
        
        # 注意：不再添加中间结果，因为：
        # 1. 依赖步骤的结果已经通过 dependencies 获取
        # 2. 中间结果和步骤结果重复，会导致上下文过长
        # 3. 只使用依赖步骤的结果可以避免冗余，提高效率
        
        result = "\n\n".join(context_parts) if context_parts else "无相关上下文"
        
        # 如果结果仍然过长，进行最终截断
        if len(result) > max_length:
            result = result[:max_length] + "\n...（上下文已截断，内容过长）"
        
        return result

    def _resolve_parameters(
        self,
        chain: ChainOfThought,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        解析参数中的引用（如引用之前步骤的结果）
        
        Args:
            chain: 思维链对象
            parameters: 原始参数
            
        Returns:
            解析后的参数
        """
        resolved = {}
        for key, value in parameters.items():
            if isinstance(value, str) and value.startswith("$step_"):
                # 引用步骤结果，如 "$step_1.result"
                step_num_str = value.replace("$step_", "").split(".")[0]
                try:
                    step_num = int(step_num_str)
                    step = chain.get_step(step_num)
                    if step and step.result:
                        resolved[key] = step.result
                    else:
                        resolved[key] = value
                except ValueError:
                    resolved[key] = value
            else:
                resolved[key] = value
        
        return resolved

    async def _synthesize_result(self, chain: ChainOfThought) -> str:
        """
        综合最终结果
        
        Args:
            chain: 思维链对象
            
        Returns:
            最终结果
        """
        # 收集所有步骤的结果（包括已完成的和被跳过的）
        results_summary = []
        for step in chain.steps:
            if step.status in [ThoughtStatus.COMPLETED, ThoughtStatus.SKIPPED] and step.result:
                results_summary.append(f"步骤 {step.step_number} ({step.description}):\n{json.dumps(step.result, ensure_ascii=False, indent=2, default=self._json_serializer)}")
        
        # 构建综合提示词
        prompt = f"""请根据以下步骤的执行结果，生成最终回复：

原始任务：{chain.original_task}
任务目标：{chain.goal}

执行结果：
{chr(10).join(results_summary)}

**重要要求：**
1. 输出要简洁，只包含核心结论，不要重复步骤内容
2. 控制在500字以内
3. 直接回答用户问题，不要废话
4. 使用要点形式，避免冗长描述
5. 不要重复问题或上下文

请生成一个清晰、简洁的最终回复，回答用户的问题或完成任务。"""
        
        result = await self._call_llm(prompt)
        result = self._truncate_result(result, max_length=500)
        return result

    async def _call_llm(self, prompt: str) -> str:
        """
        调用LLM（带超时控制）
        
        Args:
            prompt: 提示词
            
        Returns:
            LLM响应
            
        Raises:
            asyncio.TimeoutError: LLM调用超时
        """
        try:
            if hasattr(self.llm, 'ainvoke'):
                return await asyncio.wait_for(
                    self.llm.ainvoke(prompt),
                    timeout=self.llm_timeout_seconds
                )
            elif hasattr(self.llm, '_call'):
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, self.llm._call, prompt),
                    timeout=self.llm_timeout_seconds
                )
            else:
                # 同步调用，也需要超时控制
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, self.llm._call, prompt),
                    timeout=self.llm_timeout_seconds
                )
        except asyncio.TimeoutError:
            logger.error(f"LLM调用超时（{self.llm_timeout_seconds}秒），提示词长度: {len(prompt)}")
            raise

    def _truncate_result(self, result: str, max_length: int = 200) -> str:
        """
        截断结果，确保不超过指定长度
        
        Args:
            result: 原始结果
            max_length: 最大长度（字符数）
            
        Returns:
            截断后的结果
        """
        if not isinstance(result, str):
            result = str(result)
        
        if len(result) <= max_length:
            return result
        
        # 截断并添加提示
        truncated = result[:max_length - 10]
        # 尝试在句号、逗号或空格处截断，避免截断单词
        last_punctuation = max(
            truncated.rfind('。'),
            truncated.rfind('，'),
            truncated.rfind('.'),
            truncated.rfind(','),
            truncated.rfind(' ')
        )
        
        if last_punctuation > max_length * 0.7:  # 如果找到的标点位置不太靠前
            truncated = truncated[:last_punctuation + 1]
        
        return truncated + "...（已截断）"
    
    def _json_serializer(self, obj: Any) -> Any:
        """
        JSON序列化辅助函数，处理datetime等不可序列化的对象
        
        Args:
            obj: 要序列化的对象
            
        Returns:
            可序列化的值
        """
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析JSON响应"""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"JSON解析失败: {response[:200]}")
            return {}
    
    async def _execute_agent_task(
        self,
        chain: ChainOfThought,
        step: ThoughtStep
    ) -> Any:
        """
        执行Agent任务（Multi-Agent支持）
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            执行结果
        """
        if not step.assigned_agent_id:
            raise ValueError("Agent执行步骤缺少分配的Agent ID")
        
        if not self.message_bus:
            raise ValueError("消息总线未配置，无法执行Agent任务")
        
        try:
            # 构建任务内容
            task_content = {
                "task": step.description,
                "task_id": chain.task_id,
                "thought_id": chain.thought_id,
                "step_id": step.step_id,
                "subtask_id": step.subtask_id,
                "context": self._build_step_context(chain, step),
                "dependencies": step.dependencies
            }
            
            # 发送任务请求消息
            message = AgentMessage(
                message_type=MessageType.TASK_REQUEST,
                from_agent_id=self.current_agent_id or "unknown",
                to_agent_id=step.assigned_agent_id,
                task_id=chain.task_id,
                step_id=step.step_id,
                content=task_content
            )
            
            await self.message_bus.send_message(message)
            logger.info(f"已发送任务给Agent {step.assigned_agent_id}: {step.description}")
            
            # 等待响应
            timeout = 300  # 5分钟超时
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                # 检查响应消息
                messages = await self.message_bus.receive_messages(
                    self.current_agent_id or "unknown",
                    MessageType.TASK_RESPONSE
                )
                
                for msg in messages:
                    if msg.task_id == chain.task_id and msg.step_id == step.step_id:
                        result = msg.content.get("result")
                        await self.message_bus.mark_message_processed(msg.message_id)
                        logger.info(f"收到Agent {step.assigned_agent_id} 的执行结果")
                        return result
                
                await asyncio.sleep(1)  # 等待1秒后再次检查
            
            # 超时
            raise TimeoutError(f"等待Agent {step.assigned_agent_id} 响应超时")
            
        except Exception as e:
            logger.error(f"Agent任务执行失败: {e}", exc_info=True)
            raise
    
    async def _execute_task_decomposition(
        self,
        chain: ChainOfThought,
        step: ThoughtStep
    ) -> Dict[str, Any]:
        """
        执行任务分解（Multi-Agent支持）
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            分解结果
        """
        # 如果思维链已经有子任务信息，直接返回
        if chain.subtasks:
            return {
                "subtasks": chain.subtasks,
                "subtask_count": len(chain.subtasks)
            }
        
        # 否则，返回步骤描述中的信息
        return {
            "subtasks": [],
            "subtask_count": 0,
            "description": step.description
        }
    
    async def _execute_result_integration(
        self,
        chain: ChainOfThought,
        step: ThoughtStep
    ) -> str:
        """
        执行结果整合（Multi-Agent支持）
        
        Args:
            chain: 思维链对象
            step: 思维步骤
            
        Returns:
            整合后的结果
        """
        # 收集所有Agent的执行结果
        results = []
        
        # 从思维链的agent_results中获取结果
        if chain.agent_results:
            for agent_id, result in chain.agent_results.items():
                results.append(f"Agent {agent_id} 的结果：\n{json.dumps(result, ensure_ascii=False, indent=2, default=self._json_serializer)}")
        
        # 从步骤结果中获取
        for step_item in chain.steps:
            if (step_item.assigned_agent_id and 
                step_item.status == ThoughtStatus.COMPLETED and 
                step_item.result):
                results.append(
                    f"步骤 {step_item.step_number} (Agent {step_item.assigned_agent_id}) 的结果：\n"
                    f"{json.dumps(step_item.result, ensure_ascii=False, indent=2, default=self._json_serializer)}"
                )
        
        if not results:
            # 如果没有Agent结果，使用常规的综合方法
            return await self._execute_synthesis(chain, step)
        
        # 构建整合提示词
        prompt = f"""请整合以下多个Agent的执行结果，生成最终回复：

原始任务：{chain.original_task}
任务目标：{chain.goal}

执行结果：
{chr(10).join(results)}

**重要要求：**
1. 输出要简洁，只包含核心结论，不要重复结果内容
2. 控制在500字以内
3. 直接回答用户问题，不要废话
4. 使用要点形式，避免冗长描述
5. 不要重复问题或上下文

请综合所有结果，生成一个清晰、简洁的最终回复。"""
        
        result = await self._call_llm(prompt)
        result = self._truncate_result(result, max_length=500)
        return result

