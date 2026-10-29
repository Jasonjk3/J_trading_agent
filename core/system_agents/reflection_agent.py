#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
反思Agent
监控任务执行过程，分析问题并提出改进建议
"""
from typing import Any, Dict, List, Optional
from uuid import uuid4
from loguru import logger

from core.agent_base.base_agent import BaseAgent
from core.models.agent_models import AgentStatus
from core.models.chain_of_thought import ChainOfThought, ThoughtStep, ThoughtStatus
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_models import LLMModels


class ReflectionAgent(BaseAgent):
    """反思Agent - 监控和优化任务执行"""
    
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
        agent_name: str = "反思Agent",
        **kwargs
    ):
        """
        初始化反思Agent

        Args:
            agent_id: Agent ID
            agent_name: Agent名称
            **kwargs: 其他参数
        """
        agent_id = agent_id or str(uuid4())
        capabilities = ["reflection", "monitoring", "optimization", "error_analysis"]
        
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type="reflection",
            capabilities=capabilities,
            max_concurrent_tasks=kwargs.get("max_concurrent_tasks", 10),
            metadata=kwargs.get("metadata", {})
        )
        
        # LLM 实例将在 initialize() 中创建
        self.llm: Optional[BaseLLM] = None
        self.monitored_chains: Dict[str, ChainOfThought] = {}  # 监控的思维链

    async def initialize(self) -> bool:
        """初始化Agent"""
        try:
            # 确保LLM已初始化（使用BaseAgent的_get_llm方法）
            if not self._get_llm():
                logger.error("反思Agent创建LLM实例失败")
                await self.update_status(AgentStatus.ERROR)
                return False
            
            await self.update_status(AgentStatus.IDLE)
            logger.info(f"反思Agent初始化成功: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"反思Agent初始化失败: {e}", exc_info=True)
            await self.update_status(AgentStatus.ERROR)
            return False

    async def cleanup(self) -> bool:
        """清理资源"""
        try:
            self.monitored_chains.clear()
            await self.update_status(AgentStatus.IDLE)
            return True
        except Exception as e:
            logger.error(f"反思Agent清理失败: {e}")
            return False

    async def execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行反思任务（只负责核心业务逻辑）

        注意：
        - 任务计数和状态管理已由 AgentExecutor 统一管理
        - 钩子函数（_pre_execute, _post_execute, _handle_error）的调用已由 AgentExecutor 统一管理
        - 此方法只负责核心业务逻辑

        Args:
            task: 任务内容，应包含思维链信息
            context: 上下文信息

        Returns:
            反思结果和建议
        """
        thought_id = task.get("thought_id")
        chain = task.get("chain")
        reflection_type = task.get("reflection_type", "general")  # general, error_analysis, optimization
        
        if not chain:
            return {
                "success": False,
                "error": "缺少思维链信息"
            }
        
        # 根据反思类型执行不同的反思
        if reflection_type == "error_analysis":
            result = await self._analyze_error(chain)
        elif reflection_type == "optimization":
            result = await self._optimize_execution(chain)
        else:
            result = await self._general_reflection(chain)
        
        execution_result = {
            "success": True,
            "reflection_type": reflection_type,
            "suggestions": result.get("suggestions", []),
            "analysis": result.get("analysis", ""),
            "recommendations": result.get("recommendations", [])
        }
        
        return execution_result

    async def monitor_chain(self, chain: ChainOfThought) -> Dict[str, Any]:
        """
        监控思维链执行过程

        Args:
            chain: 思维链对象

        Returns:
            监控结果和建议
        """
        try:
            self.monitored_chains[chain.thought_id] = chain
            
            # 检查是否有失败的步骤
            failed_steps = [step for step in chain.steps if step.status == ThoughtStatus.FAILED]
            
            if failed_steps:
                # 分析失败原因
                return await self._analyze_failures(chain, failed_steps)
            
            # 检查执行效率
            if chain.status == "executing":
                return await self._check_efficiency(chain)
            
            return {
                "success": True,
                "status": "normal",
                "suggestions": []
            }
            
        except Exception as e:
            logger.error(f"监控思维链失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _general_reflection(self, chain: ChainOfThought) -> Dict[str, Any]:
        """通用反思"""
        try:
            prompt = f"""请对以下任务执行过程进行反思和分析：

任务：{chain.original_task}
目标：{chain.goal}
状态：{chain.status}
进度：{chain.get_progress():.2%}

已完成的步骤：
{self._format_steps(chain.get_completed_steps())}

请分析：
1. 执行过程是否合理
2. 是否有可以优化的地方
3. 是否有潜在问题
4. 提出改进建议

请以JSON格式返回：
{{
    "analysis": "分析内容",
    "suggestions": ["建议1", "建议2"],
    "recommendations": ["推荐1", "推荐2"]
}}"""
            
            response = await self._call_llm(prompt)
            result = self._parse_json_response(response)
            
            return {
                "analysis": result.get("analysis", ""),
                "suggestions": result.get("suggestions", []),
                "recommendations": result.get("recommendations", [])
            }
            
        except Exception as e:
            logger.error(f"通用反思失败: {e}", exc_info=True)
            return {
                "analysis": "",
                "suggestions": [],
                "recommendations": []
            }

    async def _analyze_error(self, chain: ChainOfThought) -> Dict[str, Any]:
        """分析错误"""
        try:
            failed_steps = [step for step in chain.steps if step.status == ThoughtStatus.FAILED]
            
            if not failed_steps:
                return {
                    "analysis": "未发现错误",
                    "suggestions": [],
                    "recommendations": []
                }
            
            failed_info = []
            for step in failed_steps:
                failed_info.append(f"步骤 {step.step_number}: {step.description}\n错误: {step.error}")
            
            prompt = f"""请分析以下任务执行中的错误：

任务：{chain.original_task}
错误步骤：
{chr(10).join(failed_info)}

请分析：
1. 错误原因
2. 可能的解决方案
3. 如何避免类似错误
4. 是否需要重试或更换方法

请以JSON格式返回：
{{
    "analysis": "错误分析",
    "suggestions": ["建议1", "建议2"],
    "recommendations": ["推荐1", "推荐2"],
    "retry_suggested": true/false
}}"""
            
            response = await self._call_llm(prompt)
            result = self._parse_json_response(response)
            
            return {
                "analysis": result.get("analysis", ""),
                "suggestions": result.get("suggestions", []),
                "recommendations": result.get("recommendations", []),
                "retry_suggested": result.get("retry_suggested", False)
            }
            
        except Exception as e:
            logger.error(f"错误分析失败: {e}", exc_info=True)
            return {
                "analysis": "",
                "suggestions": [],
                "recommendations": []
            }

    async def _optimize_execution(self, chain: ChainOfThought) -> Dict[str, Any]:
        """优化执行"""
        try:
            prompt = f"""请分析以下任务执行过程，提出优化建议：

任务：{chain.original_task}
当前步骤：{len(chain.get_completed_steps())}/{len(chain.steps)}
执行时间：{(chain.updated_at - chain.created_at).total_seconds():.2f}秒

步骤详情：
{self._format_steps(chain.steps)}

请分析：
1. 执行效率如何
2. 步骤顺序是否合理
3. 是否可以并行执行某些步骤
4. 是否有冗余步骤

请以JSON格式返回优化建议：
{{
    "analysis": "优化分析",
    "suggestions": ["优化建议1", "优化建议2"],
    "recommendations": ["推荐1", "推荐2"]
}}"""
            
            response = await self._call_llm(prompt)
            result = self._parse_json_response(response)
            
            return {
                "analysis": result.get("analysis", ""),
                "suggestions": result.get("suggestions", []),
                "recommendations": result.get("recommendations", [])
            }
            
        except Exception as e:
            logger.error(f"执行优化失败: {e}", exc_info=True)
            return {
                "analysis": "",
                "suggestions": [],
                "recommendations": []
            }

    async def _analyze_failures(
        self,
        chain: ChainOfThought,
        failed_steps: List[ThoughtStep]
    ) -> Dict[str, Any]:
        """分析失败步骤"""
        return await self._analyze_error(chain)

    async def _check_efficiency(self, chain: ChainOfThought) -> Dict[str, Any]:
        """检查执行效率"""
        return await self._optimize_execution(chain)

    def _format_steps(self, steps: List[ThoughtStep]) -> str:
        """格式化步骤信息"""
        if not steps:
            return "无步骤"
        
        lines = []
        for step in steps:
            lines.append(
                f"步骤 {step.step_number} ({step.thought_type.value}): {step.description}\n"
                f"  状态: {step.status.value}\n"
                f"  依赖: {step.dependencies}"
            )
        
        return "\n".join(lines)

    # 注意：_get_llm和_call_llm方法已在BaseAgent中实现，这里不再需要重复实现

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析JSON响应"""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(response)
        except Exception as e:
            logger.warning(f"JSON解析失败: {e}, 响应: {response[:200]}")
            return {}

