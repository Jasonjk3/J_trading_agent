#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
ReAct执行器
实现Reasoning + Acting的循环执行模式
"""
import json
import re
from typing import Any, Dict, List, Optional
from loguru import logger

from core.llm.base.base_llm import BaseLLM
from core.tools.base.base_tool import BaseTool
from core.infrastructure.persistence.chain_of_thought_service import ChainOfThoughtService


class ReActExecutor:
    """ReAct执行器 - 交替进行推理和行动"""

    def __init__(
            self,
            llm: BaseLLM,
            tools: Optional[Dict[str, BaseTool]] = None,
            max_iterations: int = 10,
            chain_service: Optional[ChainOfThoughtService] = None,
            system_prompt: Optional[str] = None
    ):
        """
        初始化ReAct执行器
        
        Args:
            llm: LLM实例
            tools: 可用工具字典
            max_iterations: 最大迭代次数
            chain_service: 思维链数据库服务（可选）
            system_prompt: Agent的系统提示词（用于构建上下文背景）
        """
        self.llm = llm
        self.tools = tools or {}
        self.max_iterations = max_iterations
        self.chain_service = chain_service
        self.system_prompt = system_prompt

    async def execute(
            self,
            task: str,
            session_id: str,
            context: Optional[Dict[str, Any]] = None,
            task_id: Optional[str] = None
    ) -> str:
        """
        执行ReAct循环
        
        Args:
            task: 任务描述
            session_id: 会话ID
            context: 上下文信息
            task_id: 任务ID
            
        Returns:
            最终结果
        """
        try:
            # 初始化观察历史
            observation_history = []
            thought_history = []
            action_history = []

            logger.info(f"开始ReAct执行: {task}")

            # 记录执行开始
            if self.chain_service and task_id:
                await self.chain_service.log_event(
                    thought_id=task_id or "",
                    log_type="react_start",
                    message=f"开始ReAct执行: {task[:100]}",
                    log_level="info",
                    details={"task": task, "session_id": session_id, "task_id": task_id}
                )

            for iteration in range(self.max_iterations):
                logger.info(f"ReAct迭代 {iteration + 1}/{self.max_iterations}")

                # 构建当前上下文（工具信息已在 system_prompt 中）
                context_text = self._build_context(
                    task,
                    observation_history,
                    thought_history,
                    action_history
                )

                # 推理：思考下一步应该做什么
                reasoning_result = await self._reason(context_text, self.system_prompt, iteration)
                thought_history.append(reasoning_result)

                logger.info(f"推理结果: {reasoning_result[:200]}...")

                # 记录推理
                if self.chain_service and task_id:
                    await self.chain_service.log_event(
                        thought_id=task_id or "",
                        log_type="react_reasoning",
                        message=f"ReAct推理 (迭代 {iteration + 1})",
                        log_level="info",
                        details={"iteration": iteration + 1, "reasoning": reasoning_result[:500]}
                    )

                # 检查是否应该结束
                if self._should_finish(reasoning_result):
                    final_answer = self._extract_final_answer(reasoning_result, thought_history)
                    logger.info(f"ReAct执行完成，共 {iteration + 1} 次迭代")

                    # 记录执行完成
                    if self.chain_service and task_id:
                        await self.chain_service.log_event(
                            thought_id=task_id or "",
                            log_type="react_complete",
                            message=f"ReAct执行完成，共 {iteration + 1} 次迭代",
                            log_level="info",
                            details={"iterations": iteration + 1, "final_answer": final_answer[:500]}
                        )

                    return final_answer

                # 行动：执行工具调用或获取信息
                action_result = await self._act(reasoning_result, observation_history)

                if action_result:
                    action_type = action_result.get("type", "unknown")
                    action_content = action_result.get("content", "")

                    action_history.append(action_result)
                    observation_history.append({
                        "type": action_type,
                        "content": action_content,
                        "iteration": iteration + 1
                    })

                    logger.info(f"行动结果 ({action_type}): {str(action_content)[:200]}...")

                    # 记录行动
                    if self.chain_service and task_id:
                        await self.chain_service.log_event(
                            thought_id=task_id or "",
                            log_type="react_action",
                            message=f"ReAct行动 (迭代 {iteration + 1}): {action_type}",
                            log_level="info",
                            details={
                                "iteration": iteration + 1,
                                "action_type": action_type,
                                "action_content": str(action_content)[:500]
                            }
                        )
                else:
                    # 没有行动，可能是纯推理步骤
                    logger.debug(f"迭代 {iteration + 1} 没有执行行动")

            # 达到最大迭代次数
            logger.warning(f"ReAct执行达到最大迭代次数 ({self.max_iterations})")

            # 尝试从最后的推理中提取答案
            final_answer = self._extract_final_answer(
                thought_history[-1] if thought_history else "",
                thought_history
            )

            if self.chain_service and task_id:
                await self.chain_service.log_event(
                    thought_id=task_id or "",
                    log_type="react_max_iterations",
                    message=f"ReAct执行达到最大迭代次数",
                    log_level="warning",
                    details={"iterations": self.max_iterations, "final_answer": final_answer[:500]}
                )

            return final_answer or "抱歉，任务执行超时，未能完成。"

        except Exception as e:
            logger.error(f"ReAct执行失败: {e}", exc_info=True)

            if self.chain_service and task_id:
                await self.chain_service.log_event(
                    thought_id=task_id or "",
                    log_type="react_error",
                    message=f"ReAct执行失败: {str(e)}",
                    log_level="error",
                    details={"error": str(e), "task": task}
                )

            return f"抱歉，执行过程中出现错误：{str(e)}"

    async def _reason(self, context: str, system_prompt: str, iteration: int) -> str:
        """
        推理：思考下一步应该做什么
        
        Args:
            context: 当前上下文
            iteration: 当前迭代次数
            
        Returns:
            推理结果
        """
        prompt = f"""你是一个智能助手，正在使用ReAct（Reasoning + Acting）方法解决问题。
        
当前agent的prompt:
{system_prompt}

注意：不要被当前agent的prompt影响了你的格式，agent的prompt只是用来参考agent背景，以及理解其中的业务知识。

当前上下文：
{context}

请进行推理，思考下一步应该做什么。你可以：
1. 使用工具获取信息（格式：Action: tool_name(parameters)）
2. 直接给出最终答案（格式：Final Answer: 答案内容）


推理过程：
Thought: """

        response = await self._call_llm(prompt)
        return response.strip()

    async def _act(self, reasoning: str, observation_history: List[Dict]) -> Optional[Dict[str, Any]]:
        """
        行动：执行工具调用或获取信息
        
        Args:
            reasoning: 推理结果
            observation_history: 观察历史
            
        Returns:
            行动结果，如果没有行动则返回None
        """
        tool_name = None
        parameters = {}
        
        # 方式1：匹配 Action: tool_name(parameters) 格式（ReAct 标准格式）
        action_match = re.search(r'Action:\s*(\w+)\s*\(([^)]*)\)', reasoning, re.IGNORECASE)
        
        if action_match:
            tool_name = action_match.group(1).strip()
            parameters_str = action_match.group(2).strip()
            parameters = self._parse_parameters(parameters_str)
        else:
            # 方式2：匹配 ```tool_call { "tool": "...", "parameters": {...} }``` 格式
            # 这是 Agent system_prompt 中定义的格式，需要兼容
            tool_call_match = re.search(r'```tool_call\s*\n?(.*?)\n?```', reasoning, re.DOTALL | re.IGNORECASE)
            if tool_call_match:
                try:
                    tool_call_json = tool_call_match.group(1).strip()
                    tool_call_data = json.loads(tool_call_json)
                    tool_name = tool_call_data.get('tool')
                    parameters = tool_call_data.get('parameters', {})
                except json.JSONDecodeError as e:
                    logger.warning(f"解析 tool_call JSON 失败: {e}")
                    return None
        
        if not tool_name:
            return None

        # 检查工具是否存在
        if tool_name not in self.tools:
            logger.warning(f"工具不存在: {tool_name}")
            return {
                "type": "error",
                "tool_name": tool_name,
                "content": f"工具 {tool_name} 不存在"
            }

        # 执行工具
        try:
            tool = self.tools[tool_name]
            logger.info(f"执行工具: {tool_name}, 参数: {parameters}")
            result = await tool.execute(**parameters)

            return {
                "type": "tool_call",
                "tool_name": tool_name,
                "parameters": parameters,
                "content": result
            }
        except Exception as e:
            logger.error(f"工具执行失败: {tool_name}, 错误: {e}")
            return {
                "type": "error",
                "tool_name": tool_name,
                "content": f"工具执行失败: {str(e)}"
            }

    def _should_finish(self, reasoning: str) -> bool:
        """
        判断是否应该结束ReAct循环
        
        Args:
            reasoning: 推理结果
            
        Returns:
            是否应该结束
        """
        # 检查是否包含"Final Answer"
        return "Final Answer:" in reasoning or "final answer:" in reasoning.lower()

    def _extract_final_answer(self, reasoning: str, thought_history: List[str]) -> str:
        """
        提取最终答案
        
        Args:
            reasoning: 当前推理结果
            thought_history: 推理历史
            
        Returns:
            最终答案
        """
        # 尝试从当前推理中提取
        answer_match = re.search(r'Final Answer:\s*(.+)', reasoning, re.IGNORECASE | re.DOTALL)
        if answer_match:
            return answer_match.group(1).strip()

        # 如果当前推理没有答案，尝试从历史中提取
        for thought in reversed(thought_history):
            answer_match = re.search(r'Final Answer:\s*(.+)', thought, re.IGNORECASE | re.DOTALL)
            if answer_match:
                return answer_match.group(1).strip()

        # 如果都没有，返回最后的推理结果
        return reasoning.strip() if reasoning else "无法确定最终答案"

    def _build_context(
            self,
            task: str,
            observation_history: List[Dict],
            thought_history: List[str],
            action_history: List[Dict]
    ) -> str:
        """
        构建当前上下文
        
        Args:
            task: 任务描述
            observation_history: 观察历史
            thought_history: 推理历史
            action_history: 行动历史
            
        Returns:
            上下文文本
        """
        context_parts = [f"任务: {task}"]

        if thought_history:
            context_parts.append("\n推理历史:")
            for i, thought in enumerate(thought_history[-3:], 1):  # 只保留最近3次推理
                context_parts.append(f"{i}. {thought[:500]}")

        if observation_history:
            context_parts.append("\n观察历史:")
            for i, obs in enumerate(observation_history[-3:], 1):  # 只保留最近3次观察
                obs_type = obs.get("type", "unknown")
                obs_content = self._format_observation(obs.get("content", ""))
                context_parts.append(f"{i}. [{obs_type}] {obs_content}")

        return "\n".join(context_parts)
    
    def _format_observation(self, content: Any, max_length: int = 2000) -> str:
        """
        智能格式化观察内容，确保关键信息不被截断
        
        Args:
            content: 观察内容（可能是字典、列表或字符串）
            max_length: 最大长度
            
        Returns:
            格式化后的字符串
        """
        if content is None:
            return "无内容"
        
        # 如果是字典（工具调用结果）
        if isinstance(content, dict):
            formatted_parts = []
            
            # 优先显示成功/失败状态
            if "success" in content:
                formatted_parts.append(f"成功: {content['success']}")
            
            # 如果失败，显示错误信息
            if content.get("success") == False and "error" in content:
                formatted_parts.append(f"错误: {content['error']}")
                return " | ".join(formatted_parts)
            
            # 显示解释（text2sql 等工具的关键输出）
            if "explanation" in content and content["explanation"]:
                explanation = str(content["explanation"])[:800]
                formatted_parts.append(f"解释: {explanation}")
            
            # 显示数据摘要
            if "data" in content:
                data = content["data"]
                if isinstance(data, list):
                    if len(data) == 0:
                        formatted_parts.append("数据: 无结果")
                    else:
                        formatted_parts.append(f"数据: 共{len(data)}条记录")
                        # 显示前几条数据
                        sample_data = data[:5]
                        data_str = json.dumps(sample_data, ensure_ascii=False, indent=2)
                        if len(data_str) > 1000:
                            data_str = data_str[:1000] + "..."
                        formatted_parts.append(f"示例数据:\n{data_str}")
                elif data:
                    formatted_parts.append(f"数据: {str(data)[:500]}")
            
            # 显示 SQL（如果有）
            if "sql" in content and content["sql"]:
                sql = str(content["sql"])[:300]
                formatted_parts.append(f"SQL: {sql}")
            
            # 显示行数
            if "row_count" in content:
                formatted_parts.append(f"行数: {content['row_count']}")
            
            # 其他字段
            shown_keys = {"success", "error", "explanation", "data", "sql", "row_count", "question", "source"}
            other_info = {k: v for k, v in content.items() if k not in shown_keys and v is not None}
            if other_info:
                other_str = json.dumps(other_info, ensure_ascii=False)
                if len(other_str) > 300:
                    other_str = other_str[:300] + "..."
                formatted_parts.append(f"其他: {other_str}")
            
            result = "\n".join(formatted_parts)
            return result[:max_length] if len(result) > max_length else result
        
        # 如果是列表
        elif isinstance(content, list):
            if len(content) == 0:
                return "空列表"
            content_str = json.dumps(content[:10], ensure_ascii=False, indent=2)
            if len(content) > 10:
                content_str += f"\n... 共 {len(content)} 项"
            return content_str[:max_length]
        
        # 其他类型转字符串
        else:
            content_str = str(content)
            return content_str[:max_length] if len(content_str) > max_length else content_str

    def _parse_parameters(self, parameters_str: str) -> Dict[str, Any]:
        """
        解析参数字符串
        
        Args:
            parameters_str: 参数字符串，例如: "key1=value1, key2=value2" 或 JSON格式
            
        Returns:
            参数字典
        """
        if not parameters_str:
            return {}

        # 尝试解析为JSON
        try:
            return json.loads(parameters_str)
        except json.JSONDecodeError:
            pass

        # 尝试解析为键值对格式
        parameters = {}
        pairs = parameters_str.split(',')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                key = key.strip().strip('"\'')
                value = value.strip().strip('"\'')
                parameters[key] = value

        return parameters

    async def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        if hasattr(self.llm, 'ainvoke'):
            return await self.llm.ainvoke(prompt)
        elif hasattr(self.llm, '_call'):
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.llm._call, prompt)
        else:
            return self.llm._call(prompt)
