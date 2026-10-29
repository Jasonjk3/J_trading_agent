#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
任务规划器
将复杂任务分解为多个思维步骤
"""
import json
import re
from typing import Any, Dict, Optional
from loguru import logger

from core.models.chain_of_thought import ChainOfThought, ThoughtType
from core.infrastructure.persistence.chain_of_thought_service import ChainOfThoughtService
from core.llm.base.base_llm import BaseLLM
from core.tools.base.base_tool import BaseTool


class TaskPlanner:
    """任务规划器"""

    def __init__(
        self,
        llm: BaseLLM,
        tools: Optional[Dict[str, BaseTool]] = None,
        chain_service: Optional[ChainOfThoughtService] = None
    ):
        """
        初始化任务规划器（单Agent思维链规划）
        
        Args:
            llm: LLM实例
            tools: 可用工具字典
            chain_service: 思维链数据库服务（可选）
        """
        self.llm = llm
        self.tools = tools or {}
        self.chain_service = chain_service

    async def plan(
        self,
        task: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ) -> ChainOfThought:
        """
        规划任务，生成思维链
        
        Args:
            task: 任务描述
            session_id: 会话ID
            context: 上下文信息
            task_id: 任务ID
            
        Returns:
            思维链对象
        """
        try:
            # 记录规划开始
            if self.chain_service:
                await self.chain_service.log_event(
                    thought_id="",  # 将在创建chain后更新
                    log_type="planning_start",
                    message=f"开始规划任务: {task[:100]}",
                    log_level="info",
                    details={"task": task, "session_id": session_id, "task_id": task_id}
                )
            
            # 创建思维链
            chain = ChainOfThought(
                task_id=task_id,
                session_id=session_id,
                original_task=task,
                goal=task,  # 初始目标，后续会更新
                context=context or {},
                status="planning"
            )
            
            # 单Agent任务规划：生成思维步骤
            prompt = self._build_planning_prompt(task, context, chain)
            response = await self._call_llm(prompt)
            plan_data = self._parse_planning_response(response)
            
            # 更新目标
            chain.goal = plan_data.get("goal", task)
            
            # 记录规划过程
            if self.chain_service:
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="planning_llm_response",
                    message="收到LLM规划响应",
                    log_level="debug",
                    details={"response": response[:500], "parsed_steps_count": len(plan_data.get("steps", []))}
                )
            
            # 添加思维步骤
            steps = plan_data.get("steps", [])
            start_step_number = 1
            
            for step_data in steps:
                step_number = step_data.get("step_number", start_step_number + len(chain.steps))
                
                thought_type_str = step_data.get("thought_type", "reasoning")
                thought_type = ThoughtType(thought_type_str) if thought_type_str in [t.value for t in ThoughtType] else ThoughtType.REASONING
                
                # 处理依赖关系
                dependencies = step_data.get("dependencies", [])
                # 过滤掉无效的依赖（负数或0）
                dependencies = [dep for dep in dependencies if dep >= 1]
                
                step = chain.add_step(
                    step_number=step_number,
                    thought_type=thought_type,
                    description=step_data.get("description", ""),
                    dependencies=dependencies,
                    tool_name=step_data.get("tool_name"),
                    tool_parameters=step_data.get("tool_parameters"),
                    meta_data=step_data.get("meta_data", {})
                )
                
                # 记录步骤创建
                if self.chain_service:
                    await self.chain_service.log_event(
                        thought_id=chain.thought_id,
                        log_type="step_created",
                        message=f"创建步骤 {step_number}: {step.description}",
                        log_level="info",
                        step_id=step.step_id,
                        details={
                            "step_number": step_number,
                            "thought_type": thought_type.value,
                            "dependencies": step.dependencies
                        }
                    )
            
            chain.status = "executing"
            logger.info(f"任务规划完成: {task}, 生成 {len(chain.steps)} 个步骤")
            
            # 保存思维链到数据库
            if self.chain_service:
                await self.chain_service.save_chain(chain)
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="planning_complete",
                    message=f"任务规划完成，共生成 {len(chain.steps)} 个步骤",
                    log_level="info",
                    details={"steps_count": len(chain.steps), "goal": chain.goal}
                )
            
            return chain
            
        except Exception as e:
            logger.error(f"任务规划失败: {e}", exc_info=True)
            # 返回一个简单的思维链
            chain = ChainOfThought(
                task_id=task_id,
                session_id=session_id,
                original_task=task,
                goal=task,
                context=context or {},
                status="failed",
                error=str(e)
            )
            
            # 记录规划失败
            if self.chain_service:
                await self.chain_service.save_chain(chain)
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="planning_failed",
                    message=f"任务规划失败: {str(e)}",
                    log_level="error",
                    details={"error": str(e), "task": task}
                )
            
            return chain
    
    def _build_planning_prompt(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        chain: Optional[ChainOfThought] = None
    ) -> str:
        """
        构建规划提示词
        
        Args:
            task: 任务描述
            context: 上下文信息
            
        Returns:
            提示词
        """
        # 获取可用工具信息
        tools_info = self._format_tools_info()
        
        prompt = f"""你是一个任务规划专家。请将用户的任务分解为多个清晰的执行步骤。

用户任务：{task}
"""

        if context:
            # 序列化 context，处理 Pydantic 模型（如 Intent）
            serialized_context = self._serialize_context(context)
            prompt += f"\n上下文信息：{self._safe_json_dumps(serialized_context, ensure_ascii=False, indent=2)}\n"

        if tools_info:
            prompt += f"\n可用工具：\n{tools_info}\n"

        prompt += """
请分析任务，将其分解为**最少的必要步骤**。每个步骤应该：
1. 有明确的描述（要具体，不要抽象）
2. 如果涉及工具调用，指定工具名称和参数
3. 如果步骤之间有依赖关系，说明依赖的步骤序号
4. 步骤类型可以是：
   - analysis（分析）：分析信息、理解需求
   - tool_call（工具调用）：调用工具执行操作
   - reasoning（推理）：逻辑推理、判断
   - decision（决策）：做出决策
   - synthesis（综合）：综合多个结果生成最终答案
   - validation（验证）：验证结果（仅在必要时使用）

**重要规划原则（必须严格遵守）：**
1. **最小化步骤数量**：能用3步完成就不要用5步，能用5步完成就不要用10步
2. **避免冗余步骤**：不要创建以下类型的冗余步骤：
   - "任务分解"、"理解任务"、"分析需求"（这些是规划器的工作，不是执行步骤）
   - "验证信息完整性"、"确认成功"、"检查结果"（除非确实需要验证）
   - "准备数据"、"整理信息"（可以合并到实际使用数据的步骤中）
   - "总结"、"回顾"（除非是最终的综合步骤）
3. **合并相似步骤**：如果多个步骤可以合并为一个，必须合并
4. **直接执行**：能直接执行的步骤就不要先"分析"再"执行"
5. **步骤描述要具体**：例如"从用户输入中提取任务名称、负责人、截止时间"而不是"解析任务"
6. **优先使用工具**：如果可以直接调用工具完成，就不要先分析再调用

**步骤数量建议：**
- 简单任务（1-2个操作）：2-3个步骤
- 中等任务（3-5个操作）：3-5个步骤
- 复杂任务（6+个操作）：5-8个步骤
- 超过10个步骤通常意味着过度分解，需要重新规划

请以JSON格式返回规划结果，格式如下：
{
    "goal": "任务目标描述",
    "steps": [
        {
            "step_number": 1,
            "thought_type": "analysis",
            "description": "步骤描述（要具体）",
            "dependencies": [],
            "tool_name": null,
            "tool_parameters": null
        },
        {
            "step_number": 2,
            "thought_type": "tool_call",
            "description": "调用工具获取信息",
            "dependencies": [1],
            "tool_name": "工具名称",
            "tool_parameters": {
                "param1": "value1"
            }
        }
    ]
}

只返回JSON，不要返回其他内容。

**再次强调：步骤数量要尽可能少，只保留必要的步骤！**"""
        
        return prompt

    def _format_tools_info(self) -> str:
        """格式化工具信息"""
        if not self.tools:
            return ""
        
        tools_list = []
        for tool_name, tool in self.tools.items():
            schema = tool.get_schema()
            description = schema.get("description", "")
            parameters = schema.get("parameters", {})
            
            tool_info = f"- {tool_name}: {description}"
            if parameters:
                tool_info += f"\n  参数: {self._safe_json_dumps(parameters, ensure_ascii=False, indent=2)}"
            
            tools_list.append(tool_info)
        
        return "\n".join(tools_list)

    def _parse_planning_response(self, response: str) -> Dict[str, Any]:
        """
        解析规划响应
        
        Args:
            response: LLM响应
            
        Returns:
            解析后的规划数据
        """
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group(0))
                return plan_data
            
            # 如果直接是JSON
            return json.loads(response)
            
        except json.JSONDecodeError as e:
            logger.warning(f"解析规划响应失败: {e}, 响应内容: {response[:200]}")
            # 返回默认规划
            return {
                "goal": "完成任务",
                "steps": [
                    {
                        "step_number": 1,
                        "thought_type": "reasoning",
                        "description": "分析任务需求",
                        "dependencies": []
                    },
                    {
                        "step_number": 2,
                        "thought_type": "synthesis",
                        "description": "综合结果并生成回复",
                        "dependencies": [1]
                    }
                ]
            }

    def _serialize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        序列化上下文信息，处理 Pydantic 模型、枚举、datetime等不可序列化的对象
        
        Args:
            context: 原始上下文字典
            
        Returns:
            可序列化的上下文字典
        """
        from pydantic import BaseModel
        from enum import Enum
        from datetime import datetime, date
        
        serialized = {}
        for key, value in context.items():
            if value is None:
                serialized[key] = None
            elif isinstance(value, (datetime, date)):
                # datetime/date 对象：转换为 ISO 格式字符串
                serialized[key] = value.isoformat()
            elif isinstance(value, BaseModel):
                # Pydantic 模型：转换为字典，然后递归处理（可能包含datetime）
                if hasattr(value, 'model_dump'):
                    # Pydantic v2
                    model_dict = value.model_dump()
                    # 递归处理字典，确保其中的datetime也被转换
                    serialized[key] = self._serialize_context(model_dict) if isinstance(model_dict, dict) else model_dict
                elif hasattr(value, 'dict'):
                    # Pydantic v1
                    model_dict = value.dict()
                    # 递归处理字典，确保其中的datetime也被转换
                    serialized[key] = self._serialize_context(model_dict) if isinstance(model_dict, dict) else model_dict
                else:
                    # 降级：转换为字符串
                    serialized[key] = str(value)
            elif isinstance(value, Enum):
                # 枚举类型：转换为值
                serialized[key] = value.value
            elif isinstance(value, dict):
                # 递归处理嵌套字典
                serialized[key] = self._serialize_context(value)
            elif isinstance(value, (list, tuple)):
                # 处理列表/元组
                serialized[key] = [
                    self._serialize_value(item) for item in value
                ]
            else:
                # 其他类型直接保留（包括基本类型：str, int, float, bool 等）
                serialized[key] = value
        
        return serialized
    
    def _safe_json_dumps(self, obj: Any, **kwargs) -> str:
        """
        安全的JSON序列化，自动处理datetime等不可序列化的对象
        
        Args:
            obj: 要序列化的对象
            **kwargs: 传递给json.dumps的其他参数
            
        Returns:
            JSON字符串
        """
        from datetime import datetime, date
        
        def default_serializer(o: Any) -> Any:
            """默认序列化器"""
            if isinstance(o, (datetime, date)):
                return o.isoformat()
            raise TypeError(f"Object of type {type(o)} is not JSON serializable")
        
        # 如果obj是字典或列表，先序列化其中的datetime
        if isinstance(obj, dict):
            obj = self._serialize_context(obj)
        elif isinstance(obj, (list, tuple)):
            obj = [self._serialize_value(item) for item in obj]
        
        return json.dumps(obj, default=default_serializer, **kwargs)
    
    def _serialize_value(self, value: Any) -> Any:
        """
        序列化单个值（辅助方法，用于处理列表中的元素）
        
        Args:
            value: 要序列化的值
            
        Returns:
            序列化后的值
        """
        from pydantic import BaseModel
        from enum import Enum
        from datetime import datetime, date
        
        if value is None:
            return None
        elif isinstance(value, (datetime, date)):
            # datetime/date 对象：转换为 ISO 格式字符串
            return value.isoformat()
        elif isinstance(value, BaseModel):
            # Pydantic 模型：转换为字典，然后递归处理（可能包含datetime）
            if hasattr(value, 'model_dump'):
                model_dict = value.model_dump()
                # 递归处理字典，确保其中的datetime也被转换
                return self._serialize_context(model_dict) if isinstance(model_dict, dict) else model_dict
            elif hasattr(value, 'dict'):
                model_dict = value.dict()
                # 递归处理字典，确保其中的datetime也被转换
                return self._serialize_context(model_dict) if isinstance(model_dict, dict) else model_dict
            else:
                return str(value)
        elif isinstance(value, Enum):
            # 枚举类型
            return value.value
        elif isinstance(value, dict):
            # 递归处理字典
            return self._serialize_context(value)
        else:
            # 其他类型直接返回
            return value
    
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

    async def refine_plan(
        self,
        chain: ChainOfThought,
        feedback: str
    ) -> ChainOfThought:
        """
        根据反馈优化规划
        
        Args:
            chain: 现有思维链
            feedback: 反馈信息
            
        Returns:
            优化后的思维链
        """
        try:
            # 序列化步骤，处理datetime等不可序列化的对象
            serialized_steps = []
            for step in chain.steps:
                step_dict = step.dict() if hasattr(step, 'dict') else {}
                serialized_steps.append(self._serialize_context(step_dict))
            
            prompt = f"""你是一个任务规划专家。请根据反馈优化现有的任务规划。

原始任务：{chain.original_task}
当前规划：{self._safe_json_dumps(serialized_steps, ensure_ascii=False, indent=2)}
反馈：{feedback}

请优化规划，以JSON格式返回新的步骤列表（格式与规划时相同）。
只返回JSON，不要返回其他内容。"""
            
            response = await self._call_llm(prompt)
            plan_data = self._parse_planning_response(response)
            
            # 更新思维链
            chain.steps.clear()
            steps = plan_data.get("steps", [])
            for step_data in steps:
                step_number = step_data.get("step_number", len(chain.steps) + 1)
                thought_type_str = step_data.get("thought_type", "reasoning")
                thought_type = ThoughtType(thought_type_str) if thought_type_str in [t.value for t in ThoughtType] else ThoughtType.REASONING
                
                chain.add_step(
                    step_number=step_number,
                    thought_type=thought_type,
                    description=step_data.get("description", ""),
                    dependencies=step_data.get("dependencies", []),
                    tool_name=step_data.get("tool_name"),
                    tool_parameters=step_data.get("tool_parameters")
                )
            
            chain.status = "executing"
            logger.info(f"规划已优化: {chain.thought_id}")
            
            # 记录规划优化
            if self.chain_service:
                await self.chain_service.save_chain(chain)
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="planning_refined",
                    message=f"规划已优化，当前共 {len(chain.steps)} 个步骤",
                    log_level="info",
                    details={"feedback": feedback, "steps_count": len(chain.steps)}
                )
            
            return chain
            
        except Exception as e:
            logger.error(f"规划优化失败: {e}", exc_info=True)
            chain.error = f"规划优化失败: {str(e)}"
            
            # 记录优化失败
            if self.chain_service:
                await self.chain_service.log_event(
                    thought_id=chain.thought_id,
                    log_type="planning_refine_failed",
                    message=f"规划优化失败: {str(e)}",
                    log_level="error",
                    details={"error": str(e), "feedback": feedback}
                )
            
            return chain

