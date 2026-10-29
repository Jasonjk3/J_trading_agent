#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 16:50
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
意图路由器
根据意图选择合适的智能体
"""
from typing import List, Optional
from loguru import logger

from core.component.registry.agent_registry import AgentRegistry
from core.agent_base.base_agent import BaseAgent
from core.component.intent.intent_models import Intent, IntentRoute
from core.llm.base.base_llm import BaseLLM


class IntentRouter:
    """意图路由器"""

    def __init__(self, agent_registry: AgentRegistry, llm: Optional[BaseLLM] = None):
        """
        初始化意图路由器

        Args:
            agent_registry: 智能体注册中心
            llm: LLM实例（可选，用于智能路由）
        """
        self.agent_registry = agent_registry
        self.llm = llm
        self._intent_agent_mapping = self._build_default_mapping()

    def _build_default_mapping(self) -> dict:
        """
        构建默认的意图-智能体映射

        Returns:
            映射字典
        """
        return {
            "greeting": ["intelligent_assistant"],
            "question": ["intelligent_assistant", "search_agent"],
            "command": ["command_agent"],
            "chat": ["intelligent_assistant"],
            "search": ["search_agent"],
            "analysis": ["analysis_agent", "data_agent"],
            "calculation": ["calculator_agent"],
            "translation": ["translation_agent"],
            "code_generation": ["code_agent"],
            "data_processing": ["data_agent"],
            "feishu_operation": ["feishu_assistant"],
            "unknown": ["intelligent_assistant"]
        }

    async def route(self, intent: Intent) -> IntentRoute:
        """
        路由意图到合适的智能体
        简化逻辑：复杂任务→协调Agent，简单任务→直接路由

        Args:
            intent: 意图对象

        Returns:
            IntentRoute对象
        """
        try:
            # 判断是否需要Multi-Agent协作
            requires_multi_agent = intent.metadata.get("requires_multi_agent", False)
            complexity = intent.metadata.get("complexity", "simple")
            
            # 如果是复杂任务，路由到协调Agent
            if requires_multi_agent or complexity in ["complex", "moderate"]:
                return await self._route_to_coordinator(intent)
            
            # 简单任务：直接路由到单个Agent
            # 方法1: 使用规则映射
            route = await self._rule_based_route(intent)
            if route:
                return route

            # 方法2: 基于能力的路由
            route = await self._capability_based_route(intent)
            if route:
                return route

            # 降级到默认路由
            return await self._default_route(intent)

        except Exception as e:
            logger.error(f"意图路由失败: {e}")
            # 出错时默认路由到协调Agent（安全策略）
            return await self._route_to_coordinator(intent)
    
    async def _route_to_coordinator(self, intent: Intent) -> IntentRoute:
        """
        路由到协调Agent
        
        Args:
            intent: 意图对象
            
        Returns:
            IntentRoute对象
        """
        # 查找协调Agent
        coordinators = await self.agent_registry.get_available_agents(agent_type="coordinator")
        
        if coordinators:
            coordinator = coordinators[0]
            return IntentRoute(
                intent=intent,
                target_agent_id=coordinator.agent_id,
                target_agent_type="coordinator",
                required_capabilities=["task_decomposition", "agent_coordination"],
                routing_reason=f"复杂任务，需要Multi-Agent协作（复杂度: {intent.metadata.get('complexity', 'unknown')}）",
                alternative_agents=[a.agent_id for a in coordinators[1:]]
            )
        else:
            # 如果没有协调Agent，降级到默认路由
            logger.warning("未找到协调Agent，降级到默认路由")
            return await self._default_route(intent)

    async def _llm_route(self, intent: Intent) -> Optional[IntentRoute]:
        """
        使用LLM进行智能路由

        Args:
            intent: 意图对象

        Returns:
            IntentRoute对象，如果失败则返回None
        """
        if not self.llm:
            return None

        try:
            # 获取可用智能体信息
            agents = await self.agent_registry.get_all_agents()
            agent_capabilities = self._format_agent_capabilities(agents)

            # 构建更详细的提示词，包含用户原始输入
            prompt = f"""你是一个智能体路由助手。请根据用户输入和意图信息，选择最合适的智能体来处理任务。

用户原始输入：{intent.original_text}
意图类型：{intent.intent_type.value}
置信度：{intent.confidence}
关键词：{', '.join(intent.keywords) if intent.keywords else '无'}

可用智能体及其能力：
{agent_capabilities}

请仔细分析用户输入，选择最合适的智能体。特别注意：
1. 如果用户输入包含"飞书"、"任务"、"审批"、"联系人"、"日程"、"文档"等关键词，应该选择 feishu_assistant
2. 如果是数学计算、逻辑推理、常识问答等，应该选择 intelligent_assistant
3. 如果是代码生成、编程相关，应该选择 intelligent_assistant

请以JSON格式返回结果：
{{
    "target_agent_type": "智能体类型（如 feishu_assistant 或 intelligent_assistant）",
    "required_capabilities": ["所需能力1", "所需能力2"],
    "routing_reason": "选择理由（说明为什么选择这个智能体）",
    "alternative_agents": []
}}

只返回JSON，不要返回其他内容。"""

            # 调用LLM
            response = await self._call_llm_async(prompt)

            # 解析响应
            route_data = self._parse_route_response(response)

            # 查找目标智能体
            target_agent_type = route_data.get("target_agent_type", "")
            if not target_agent_type:
                logger.warning("LLM路由响应中缺少target_agent_type")
                return None

            target_agent = await self._find_agent_by_type(target_agent_type)
            
            if not target_agent:
                logger.warning(f"未找到类型为 {target_agent_type} 的智能体")
                return None

            return IntentRoute(
                intent=intent,
                target_agent_id=target_agent.agent_id,
                target_agent_type=target_agent_type,
                required_capabilities=route_data.get("required_capabilities", []),
                routing_reason=route_data.get("routing_reason", "LLM智能路由"),
                alternative_agents=route_data.get("alternative_agents", [])
            )

        except Exception as e:
            logger.warning(f"LLM路由失败: {e}", exc_info=True)
            return None

    async def _rule_based_route(self, intent: Intent) -> Optional[IntentRoute]:
        """
        基于规则的路由

        Args:
            intent: 意图对象

        Returns:
            IntentRoute对象
        """
        intent_type = intent.intent_type.value
        agent_types = self._intent_agent_mapping.get(intent_type, [])

        if not agent_types:
            return None

        # 尝试找到第一个可用的智能体
        for agent_type in agent_types:
            agents = await self.agent_registry.get_available_agents(
                agent_type=agent_type
            )
            if agents:
                agent = agents[0]
                return IntentRoute(
                    intent=intent,
                    target_agent_id=agent.agent_id,
                    target_agent_type=agent.agent_type,
                    required_capabilities=[],
                    routing_reason=f"规则映射: {intent_type} -> {agent_type}",
                    alternative_agents=[a.agent_id for a in agents[1:]]
                )

        return None

    async def _capability_based_route(self, intent: Intent) -> Optional[IntentRoute]:
        """
        基于能力的路由

        Args:
            intent: 意图对象

        Returns:
            IntentRoute对象
        """
        # 从意图中提取所需能力
        required_capabilities = self._extract_required_capabilities(intent)

        if not required_capabilities:
            return None

        # 查找具有所需能力的智能体
        for capability in required_capabilities:
            agents = await self.agent_registry.find_agent_by_capability(capability)
            available_agents = [
                a for a in agents
                if a.status.value != "error" 
                and a.status.value != "offline"
                and a.current_tasks < a.max_concurrent_tasks
            ]

            if available_agents:
                agent = available_agents[0]
                return IntentRoute(
                    intent=intent,
                    target_agent_id=agent.agent_id,
                    target_agent_type=agent.agent_type,
                    required_capabilities=[capability],
                    routing_reason=f"能力匹配: {capability}",
                    alternative_agents=[a.agent_id for a in available_agents[1:]]
                )

        return None

    async def _default_route(self, intent: Intent) -> IntentRoute:
        """
        默认路由

        Args:
            intent: 意图对象

        Returns:
            IntentRoute对象
        """
        # 尝试找到任何可用的智能体
        agents = await self.agent_registry.get_available_agents()
        if agents:
            agent = agents[0]
            return IntentRoute(
                intent=intent,
                target_agent_id=agent.agent_id,
                target_agent_type=agent.agent_type,
                required_capabilities=[],
                routing_reason="默认路由：选择第一个可用智能体",
                alternative_agents=[a.agent_id for a in agents[1:]]
            )

        # 没有可用智能体
        return IntentRoute(
            intent=intent,
            target_agent_id=None,
            target_agent_type=None,
            required_capabilities=[],
            routing_reason="无可用智能体",
            alternative_agents=[]
        )

    def _format_agent_capabilities(self, agents: List[BaseAgent]) -> str:
        """
        格式化智能体能力信息

        Args:
            agents: 智能体列表

        Returns:
            格式化的字符串
        """
        if not agents:
            return "暂无可用智能体"

        lines = []
        for agent in agents:
            info = agent.to_info()
            lines.append(
                f"- {info.agent_name} ({info.agent_type}): "
                f"能力={', '.join(info.capabilities)}, "
                f"状态={info.status.value}, "
                f"当前任务={info.current_tasks}/{info.max_concurrent_tasks}"
            )

        return "\n".join(lines)

    def _extract_required_capabilities(self, intent: Intent) -> List[str]:
        """
        从意图中提取所需能力

        Args:
            intent: 意图对象

        Returns:
            能力列表
        """
        capabilities = []

        # 根据意图类型推断能力
        intent_capability_map = {
            "search": ["search", "information_retrieval"],
            "analysis": ["analysis", "data_analysis"],
            "calculation": ["calculation", "math"],
            "translation": ["translation", "language"],
            "code_generation": ["code_generation", "programming"],
            "data_processing": ["data_processing", "data_analysis"],
            "feishu_operation": ["feishu_operations", "tool_calling"]
        }

        intent_type = intent.intent_type.value
        if intent_type in intent_capability_map:
            capabilities.extend(intent_capability_map[intent_type])

        # 从实体中提取能力
        if "capability" in intent.entities:
            capabilities.append(intent.entities["capability"])

        return list(set(capabilities))  # 去重

    async def _find_agent_by_type(self, agent_type: str) -> Optional[BaseAgent]:
        """
        根据类型查找智能体

        Args:
            agent_type: 智能体类型

        Returns:
            智能体实例，如果不存在则返回None
        """
        agents = await self.agent_registry.get_available_agents(agent_type=agent_type)
        return agents[0] if agents else None

    async def _call_llm_async(self, prompt: str) -> str:
        """异步调用LLM"""
        if hasattr(self.llm, 'ainvoke'):
            return await self.llm.ainvoke(prompt)
        elif hasattr(self.llm, '_call'):
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.llm._call, prompt)
        else:
            return self.llm._call(prompt)

    def _parse_route_response(self, response: str) -> dict:
        """解析路由响应"""
        import json
        import re

        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"路由响应解析失败: {response}")
            return {}

    def update_mapping(self, intent_type: str, agent_types: List[str]):
        """
        更新意图-智能体映射

        Args:
            intent_type: 意图类型
            agent_types: 智能体类型列表
        """
        self._intent_agent_mapping[intent_type] = agent_types
        logger.info(f"更新映射: {intent_type} -> {agent_types}")

