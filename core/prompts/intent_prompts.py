#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 16:50
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
意图识别提示词模板
"""
from typing import List, Optional, Tuple


class IntentPrompts:
    """意图识别提示词"""

    INTENT_RECOGNITION_SYSTEM = """你是一个专业的意图识别助手。你的任务是分析用户输入，识别用户的真实意图。

可用的意图类型包括：
- greeting: 问候、打招呼
- question: 提问、询问信息
- command: 命令、指令执行
- chat: 闲聊、对话
- search: 搜索信息
- analysis: 数据分析、分析任务
- calculation: 计算任务
- translation: 翻译任务
- code_generation: 代码生成
- data_processing: 数据处理
- feishu_operation: 飞书相关操作（如查询用户、审批、多维表格、上传文件,发送消息等）
- unknown: 无法识别的意图

请仔细分析用户输入，识别意图类型，并提取关键信息。"""

    INTENT_RECOGNITION_USER = """请分析以下用户输入，识别意图并提取关键信息。

用户输入：{user_input}

请以JSON格式返回结果，格式如下：
{{
    "intent_type": "意图类型",
    "confidence": 0.0-1.0之间的置信度分数,
    "entities": {{
        "key": "value"
    }},
    "keywords": ["关键词1", "关键词2"],
    "reasoning": "识别理由"
}}

只返回JSON，不要返回其他内容。"""

    INTENT_ROUTING_SYSTEM = """你是一个智能体路由助手。你的任务是根据用户意图，选择合适的智能体来处理任务。

可用的智能体类型和能力：
{agent_capabilities}

请根据意图和智能体的能力，选择最合适的智能体。"""

    INTENT_ROUTING_USER = """用户意图：{intent_type}
置信度：{confidence}
关键词：{keywords}
实体信息：{entities}

请选择最合适的智能体来处理这个意图，以JSON格式返回：
{{
    "target_agent_type": "智能体类型",
    "required_capabilities": ["所需能力1", "所需能力2"],
    "routing_reason": "选择理由",
    "alternative_agents": ["备选智能体1", "备选智能体2"]
}}

只返回JSON，不要返回其他内容。"""

    RESULT_INTEGRATION_TEMPLATE = """用户请求：{user_request}

{agent_name}已处理该请求，结果如下：
{agent_result}

请根据{agent_name}的结果，生成一个友好、清晰的回复给用户。回复应该：
1. 说明已经完成了用户的请求
2. 清晰地展示结果
3. 如果结果中有错误，要说明原因
4. 保持自然、友好的语气

请直接回复，不要包含任何格式标记。"""

    @staticmethod
    def get_result_integration_prompt(
        user_request: str,
        agent_result: str,
        agent_name: str = "助手"
    ) -> str:
        """
        获取结果整合提示词
        
        Args:
            user_request: 用户原始请求
            agent_result: 其他Agent的执行结果
            agent_name: Agent名称，默认为"助手"
        
        Returns:
            格式化的提示词
        """
        return IntentPrompts.RESULT_INTEGRATION_TEMPLATE.format(
            user_request=user_request,
            agent_result=agent_result,
            agent_name=agent_name
        )

    @staticmethod
    def get_intent_recognition_prompt(user_input: str) -> str:
        """
        获取意图识别提示词

        Args:
            user_input: 用户输入

        Returns:
            格式化的提示词
        """
        return IntentPrompts.INTENT_RECOGNITION_USER.format(
            user_input=user_input
        )

    @staticmethod
    def get_intent_routing_prompt(
        intent_type: str,
        confidence: float,
        keywords: List[str],
        entities: dict,
        agent_capabilities: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        获取意图路由提示词

        Args:
            intent_type: 意图类型
            confidence: 置信度
            keywords: 关键词列表
            entities: 实体信息
            agent_capabilities: 智能体能力描述

        Returns:
            (system_prompt, user_prompt) 元组
        """
        system_prompt = IntentPrompts.INTENT_ROUTING_SYSTEM.format(
            agent_capabilities=agent_capabilities or "暂无可用智能体信息"
        )
        
        user_prompt = IntentPrompts.INTENT_ROUTING_USER.format(
            intent_type=intent_type,
            confidence=confidence,
            keywords=", ".join(keywords),
            entities=str(entities)
        )
        
        return system_prompt, user_prompt

