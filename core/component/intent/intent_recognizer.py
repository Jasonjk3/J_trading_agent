#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 16:50
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
意图识别器
使用LLM识别用户意图
"""
import json
import re
from typing import Optional, List
from loguru import logger

from core.component.intent.intent_models import Intent, IntentType, IntentConfidence, ReasoningMode
from core.llm.base.base_llm import BaseLLM


class IntentRecognizer:
    """意图识别器"""

    def __init__(self, llm: BaseLLM):
        """
        初始化意图识别器

        Args:
            llm: LLM实例，用于意图识别
        """
        self.llm = llm

    async def recognize(self, user_input: str, context: Optional[dict] = None) -> Intent:
        """
        识别用户意图 - 专注于判断任务复杂度和是否需要Multi-Agent协作

        Args:
            user_input: 用户输入文本
            context: 上下文信息（可选）

        Returns:
            Intent对象
        """
        try:
            # 简化版意图识别：主要判断任务复杂度
            complexity = self._assess_complexity(user_input)
            requires_multi_agent = complexity in ["complex", "moderate"]
            
            # 提取基本信息（用于后续路由参考）
            intent_type = self._quick_classify_intent(user_input)
            
            # 判断应该使用CoT还是ReAct
            reasoning_mode = self._determine_reasoning_mode(user_input, intent_type)
            
            # 构建Intent对象
            intent = Intent(
                intent_type=intent_type,
                confidence=0.8 if complexity != "unknown" else 0.5,
                confidence_level=IntentConfidence.HIGH if complexity != "unknown" else IntentConfidence.MEDIUM,
                reasoning_mode=reasoning_mode,  # 推理模式作为一等公民字段
                entities={},
                keywords=self._extract_keywords(user_input),
                original_text=user_input,
                processed_text=user_input.strip(),
                metadata={
                    "complexity": complexity,
                    "requires_multi_agent": requires_multi_agent,
                    "task_length": len(user_input),
                    "has_multiple_actions": self._has_multiple_actions(user_input),
                    "context": context or {}
                }
            )
            
            logger.info(f"任务复杂度评估: {complexity}, 需要Multi-Agent: {requires_multi_agent}")
            return intent
            
        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            # 返回未知意图，默认需要Multi-Agent（安全策略）
            return Intent(
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                confidence_level=IntentConfidence.LOW,
                reasoning_mode=ReasoningMode.COT,  # 默认使用CoT
                original_text=user_input,
                processed_text=user_input.strip(),
                metadata={
                    "error": str(e),
                    "complexity": "complex",
                    "requires_multi_agent": True
                }
            )
    
    def _assess_complexity(self, user_input: str) -> str:
        """
        评估任务复杂度
        
        Args:
            user_input: 用户输入
            
        Returns:
            复杂度: simple, moderate, complex
        """
        user_input_lower = user_input.lower()
        length = len(user_input)
        
        # 复杂任务关键词
        complex_keywords = [
            "然后", "接着", "最后", "同时", "并且", "以及", "还要",
            "分析并", "搜索并", "计算并", "生成并", "研究并",
            "研究", "报告", "总结", "综合", "整合", "撰写",
            "对比", "比较", "评估", "分析", "预测"
        ]
        
        # 多步骤指示词
        multi_step_indicators = [
            "首先", "其次", "然后", "接着", "最后", "第一步", "第二步"
        ]
        
        keyword_count = sum(1 for keyword in complex_keywords if keyword in user_input_lower)
        step_count = sum(1 for indicator in multi_step_indicators if indicator in user_input_lower)
        
        # 判断复杂度
        if keyword_count >= 3 or step_count >= 2 or length > 200:
            return "complex"
        elif keyword_count >= 1 or step_count >= 1 or length > 100:
            return "moderate"
        else:
            return "simple"
    
    def _quick_classify_intent(self, user_input: str) -> IntentType:
        """
        快速分类意图类型（简化版）
        
        Args:
            user_input: 用户输入
            
        Returns:
            意图类型
        """
        user_input_lower = user_input.lower()
        
        # 优先检查飞书相关（必须在其他关键词之前）
        feishu_keywords = ["飞书", "feishu", "任务", "审批", "联系人", "日程", "文档", "多维表格", "bitable"]
        # 检查是否包含飞书关键词，或者包含"创建任务"、"更新任务"等飞书操作
        feishu_operation_patterns = [
            "创建任务", "更新任务", "删除任务", "完成任务",
            "创建审批", "提交审批", "审批流程",
            "创建日程", "更新日程", "删除日程",
            "创建文档", "更新文档", "删除文档",
            "创建联系人", "更新联系人", "删除联系人"
        ]
        
        if any(keyword in user_input_lower for keyword in feishu_keywords):
            return IntentType.FEISHU_OPERATION
        if any(pattern in user_input_lower for pattern in feishu_operation_patterns):
            return IntentType.FEISHU_OPERATION
        
        # 其他意图类型
        if any(word in user_input_lower for word in ["搜索", "查找", "找", "search"]):
            return IntentType.SEARCH
        elif any(word in user_input_lower for word in ["分析", "analyze"]):
            return IntentType.ANALYSIS
        elif any(word in user_input_lower for word in ["计算", "算", "calculate"]):
            return IntentType.CALCULATION
        elif any(word in user_input_lower for word in ["生成", "写", "创建", "generate", "write"]):
            return IntentType.CODE_GENERATION
        elif any(word in user_input_lower for word in ["你好", "hello", "hi"]):
            return IntentType.GREETING
        else:
            return IntentType.QUESTION
    
    def _extract_keywords(self, user_input: str) -> List[str]:
        """
        提取关键词
        
        Args:
            user_input: 用户输入
            
        Returns:
            关键词列表
        """
        # 简单的关键词提取（可以后续优化）
        import re
        # 提取中文词汇和英文单词
        words = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', user_input)
        # 过滤掉太短的词
        keywords = [w for w in words if len(w) >= 2]
        return keywords[:10]  # 最多返回10个关键词
    
    def _has_multiple_actions(self, user_input: str) -> bool:
        """
        判断是否包含多个动作
        
        Args:
            user_input: 用户输入
            
        Returns:
            是否包含多个动作
        """
        action_indicators = [
            "然后", "接着", "最后", "同时", "并且", "以及",
            "首先", "其次", "第一步", "第二步"
        ]
        
        user_input_lower = user_input.lower()
        count = sum(1 for indicator in action_indicators if indicator in user_input_lower)
        return count >= 2
    
    def _determine_reasoning_mode(self, user_input: str, intent_type) -> ReasoningMode:
        """
        判断应该使用CoT还是ReAct
        
        CoT应用场景：数学应用题、逻辑推理、常识问答、符号推理
        ReAct应用场景：需要事实核查的问答、复杂规划任务（如制定旅行计划）、工具使用（如调用API完成任务）
        NONE：简单问答、问候等不需要深度推理的场景
        
        Args:
            user_input: 用户输入
            intent_type: 意图类型
            
        Returns:
            ReasoningMode 枚举值
        """
        user_input_lower = user_input.lower()
        
        # 简单场景：问候、闲聊等不需要推理
        if intent_type in [IntentType.GREETING, IntentType.CHAT]:
            return ReasoningMode.NONE
        
        # 简单问答：长度较短且没有复杂关键词
        if len(user_input) < 20 and intent_type == IntentType.QUESTION:
            return ReasoningMode.NONE
        
        # ReAct场景关键词
        react_keywords = [
            # 工具使用相关
            "调用", "使用工具", "执行", "操作", "创建", "更新", "删除", "查询",
            "api", "接口", "工具",
            # 事实核查相关
            "查一下", "核实", "验证", "确认", "查找", "搜索", "获取",
            # 复杂规划相关
            "计划", "安排", "制定", "规划", "旅行", "行程",
            # 飞书相关
            "飞书", "feishu", "任务", "审批", "联系人", "日程", "文档"
        ]
        
        # CoT场景关键词
        cot_keywords = [
            # 数学相关
            "计算", "算", "数学", "方程", "公式", "求解",
            # 逻辑推理相关
            "推理", "逻辑", "分析", "为什么", "原因", "结论",
            # 常识问答相关
            "是什么", "什么是", "解释", "说明", "介绍",
            # 符号推理相关
            "符号", "表达式", "推导"
        ]
        
        # 检查ReAct关键词
        react_score = sum(1 for keyword in react_keywords if keyword in user_input_lower)
        
        # 检查CoT关键词
        cot_score = sum(1 for keyword in cot_keywords if keyword in user_input_lower)
        
        # 飞书操作、工具使用等倾向于ReAct
        if intent_type in [IntentType.FEISHU_OPERATION]:
            return ReasoningMode.REACT
        
        # 计算、分析等倾向于CoT
        if intent_type in [IntentType.CALCULATION, IntentType.ANALYSIS]:
            return ReasoningMode.COT
        
        # 根据关键词得分判断
        if react_score > cot_score:
            return ReasoningMode.REACT
        elif cot_score > react_score:
            return ReasoningMode.COT
        else:
            # 默认：如果有工具需求，使用ReAct；否则使用CoT
            if react_score > 0:
                return ReasoningMode.REACT
            else:
                return ReasoningMode.COT

    async def _call_llm_async(self, prompt: str) -> str:
        """
        异步调用LLM

        Args:
            prompt: 提示词

        Returns:
            LLM响应文本
        """
        # 如果LLM支持异步，使用异步方法
        if hasattr(self.llm, 'ainvoke'):
            return await self.llm.ainvoke(prompt)
        elif hasattr(self.llm, '_call'):
            # 同步调用（在异步环境中）
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.llm._call, prompt)
        else:
            # 直接调用
            return self.llm._call(prompt)

    def _parse_response(self, response: str) -> dict:
        """
        解析LLM响应

        Args:
            response: LLM响应文本

        Returns:
            解析后的字典
        """
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            else:
                # 如果没有找到JSON，尝试直接解析
                return json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}, 响应: {response}")
            # 尝试从响应中提取关键信息
            return self._extract_fallback_info(response)

    def _extract_fallback_info(self, response: str) -> dict:
        """
        从非JSON响应中提取信息（降级处理）

        Args:
            response: LLM响应文本

        Returns:
            提取的信息字典
        """
        result = {
            "intent_type": "unknown",
            "confidence": 0.5,
            "entities": {},
            "keywords": [],
            "reasoning": response
        }
        
        # 尝试从文本中提取意图类型
        response_lower = response.lower()
        for intent in IntentType:
            if intent.value in response_lower:
                result["intent_type"] = intent.value
                break
        
        return result

    def _validate_intent_type(self, intent_type: str) -> IntentType:
        """
        验证并修正意图类型

        Args:
            intent_type: 意图类型字符串

        Returns:
            IntentType枚举值
        """
        try:
            return IntentType(intent_type.lower())
        except ValueError:
            # 尝试模糊匹配
            intent_lower = intent_type.lower()
            for intent in IntentType:
                if intent.value in intent_lower or intent_lower in intent.value:
                    return intent
            return IntentType.UNKNOWN

    def _calculate_confidence_level(self, confidence: float) -> IntentConfidence:
        """
        计算置信度等级

        Args:
            confidence: 置信度分数

        Returns:
            IntentConfidence枚举值
        """
        if confidence >= 0.8:
            return IntentConfidence.HIGH
        elif confidence >= 0.5:
            return IntentConfidence.MEDIUM
        else:
            return IntentConfidence.LOW

    def recognize_batch(self, user_inputs: list[str]) -> list[Intent]:
        """
        批量识别意图（同步方法）

        Args:
            user_inputs: 用户输入列表

        Returns:
            Intent列表
        """
        import asyncio
        
        # 如果已经在事件循环中，使用gather
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已经在运行的事件循环，需要创建任务
                tasks = [self.recognize(input_text) for input_text in user_inputs]
                return asyncio.gather(*tasks)
            else:
                # 没有运行的事件循环，可以直接运行
                return loop.run_until_complete(
                    asyncio.gather(*[self.recognize(input_text) for input_text in user_inputs])
                )
        except RuntimeError:
            # 没有事件循环，创建新的
            return asyncio.run(
                asyncio.gather(*[self.recognize(input_text) for input_text in user_inputs])
            )

