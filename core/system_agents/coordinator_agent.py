#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
协调Agent
负责任务分解、分配和Multi-Agent协作协调
"""
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4
from loguru import logger

from core.agent_base.base_agent import BaseAgent
from core.models.agent_models import AgentStatus
from core.component.registry.agent_registry import AgentRegistry
from core.models.agent_message import MessageBus, AgentMessage, MessageType
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_models import LLMModels


class CoordinatorAgent(BaseAgent):
    """协调Agent - 负责任务分解和Multi-Agent协调"""
    
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
        agent_name: str = "协调Agent",
        agent_registry: Optional[AgentRegistry] = None,
        message_bus: Optional[MessageBus] = None,
        **kwargs
    ):
        """
        初始化协调Agent

        Args:
            agent_id: Agent ID
            agent_name: Agent名称
            agent_registry: Agent注册中心
            message_bus: 消息总线
            **kwargs: 其他参数
        """
        agent_id = agent_id or str(uuid4())
        capabilities = ["task_decomposition", "agent_coordination", "multi_agent_planning"]
        
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type="coordinator",
            capabilities=capabilities,
            max_concurrent_tasks=kwargs.get("max_concurrent_tasks", 5),
            metadata=kwargs.get("metadata", {})
        )
        
        # LLM 实例将在 initialize() 中创建
        self.llm: Optional[BaseLLM] = None
        self.agent_registry = agent_registry
        self.message_bus = message_bus
        self.active_tasks: Dict[str, Dict[str, Any]] = {}  # 活跃任务 {task_id: task_info}
        self.subtask_results: Dict[str, Dict[str, Any]] = {}  # 子任务结果 {task_id: {subtask_id: result}}
        
        # 注意：协调Agent不再使用TaskPlanner和ThoughtExecutor
        # 任务分解直接使用_decompose_task方法，子任务由各Agent使用自己的思维链执行

    async def initialize(self) -> bool:
        """初始化Agent"""
        try:
            # 确保LLM已初始化（使用BaseAgent的_get_llm方法）
            if not self._get_llm():
                logger.error("协调Agent创建LLM实例失败")
                await self.update_status(AgentStatus.ERROR)
                return False
            
            if not self.agent_registry:
                logger.error("协调Agent需要Agent注册中心")
                await self.update_status(AgentStatus.ERROR)
                return False
            
            if not self.message_bus:
                logger.warning("协调Agent未配置消息总线，将使用内部消息机制")
                self.message_bus = MessageBus()
            
            await self.update_status(AgentStatus.IDLE)
            logger.info(f"协调Agent初始化成功: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"协调Agent初始化失败: {e}", exc_info=True)
            await self.update_status(AgentStatus.ERROR)
            return False

    async def cleanup(self) -> bool:
        """清理资源"""
        try:
            self.active_tasks.clear()
            self.subtask_results.clear()
            await self.update_status(AgentStatus.IDLE)
            return True
        except Exception as e:
            logger.error(f"协调Agent清理失败: {e}")
            return False

    async def execute(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        执行任务 - 任务分解和协调（只负责核心业务逻辑）

        注意：
        - 任务计数和状态管理已由 AgentExecutor 统一管理
        - 钩子函数（_pre_execute, _post_execute, _handle_error）的调用已由 AgentExecutor 统一管理
        - 此方法只负责核心业务逻辑

        Args:
            task: 任务内容
            context: 上下文信息

        Returns:
            执行结果
        """
        # 使用 AgentExecutor 传递的 task_id（通过 context），如果没有则从 task 中获取
        task_id = context.get("task_id") if context else None
        if not task_id:
            task_id = task.get("task_id") or str(uuid4())
        original_task = task.get("task", task.get("message", ""))
        session_id = task.get("session_id", "")
        
        logger.info(f"协调Agent开始处理任务: {task_id}")
        logger.info(f"原始任务内容: {original_task}")
        logger.info(f"会话ID: {session_id}")
        
        
        # 1. 任务分解（不使用思维链）
        logger.info("开始分解任务...")
        subtasks = await self._decompose_task(original_task, context)
        
        if not subtasks:
            logger.error("无法分解任务")
            return {
                "success": False,
                "error": "无法分解任务",
                "task_id": task_id
            }
        
        logger.info(f"任务分解完成，生成 {len(subtasks)} 个子任务:")
        for idx, subtask in enumerate(subtasks, 1):
            logger.info(f"  子任务 {idx}:")
            logger.info(f"    - ID: {subtask.get('subtask_id', 'N/A')}")
            logger.info(f"    - 描述: {subtask.get('description', 'N/A')}")
            logger.info(f"    - 所需能力: {subtask.get('required_capabilities', [])}")
            logger.info(f"    - 偏好Agent类型: {subtask.get('preferred_agent_type', 'N/A')}")
            logger.info(f"    - 依赖: {subtask.get('dependencies', [])}")
            logger.info(f"    - 优先级: {subtask.get('priority', 'N/A')}")
        
        # 2. 分配子任务给专业Agent
        logger.info("开始分配子任务给专业Agent...")
        task_assignments = await self._assign_subtasks(subtasks, context)
        
        # 3. 记录任务信息
        self.active_tasks[task_id] = {
            "original_task": original_task,
            "subtasks": subtasks,
            "assignments": task_assignments,
            "status": "executing",
            "session_id": session_id
        }
        self.subtask_results[task_id] = {}
        
        # 4. 发送子任务给专业Agent（使用深度思考模式）
        logger.info(f"开始发送 {len(task_assignments)} 个子任务给专业Agent（使用深度思考模式）...")
        await self._dispatch_subtasks(task_id, task_assignments, context)
        
        # 5. 等待并收集结果
        logger.info("等待子任务执行结果...")
        results = await self._collect_results(task_id, timeout=300)  # 5分钟超时
        
        logger.info(f"收集到 {len(results)} 个子任务结果:")
        for subtask_id, result in results.items():
            logger.info(f"  子任务 {subtask_id} 结果: {str(result)[:200]}...")
        
        # 6. 整合结果
        logger.info("开始整合子任务结果...")
        final_result = await self._integrate_results(task_id, results, original_task)
        logger.info(f"结果整合完成，最终结果长度: {len(str(final_result))} 字符")
        
        # 清理
        if task_id in self.active_tasks:
            del self.active_tasks[task_id]
        if task_id in self.subtask_results:
            del self.subtask_results[task_id]
        
        result = {
            "success": True,
            "task_id": task_id,
            "response": final_result,  # 使用 response 保持与其他 Agent 接口一致
            "subtask_results": results
        }
        
        return result

    async def _decompose_task(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        分解任务为子任务

        Args:
            task: 原始任务
            context: 上下文信息

        Returns:
            子任务列表
        """
        try:
            # 获取可用Agent信息
            agents = await self.agent_registry.get_all_agents()
            agent_info = self._format_agent_info(agents)
            
            prompt = f"""你是一个任务分解专家。请将以下复杂任务分解为最少数量的子任务。

原始任务：{task}

可用Agent信息：
{agent_info}

【核心原则 - 极简分解】：
1. 子任务数量必须最少化，通常只需要1-2个子任务
2. 如果任务可以由单个Agent一次性完成，就只创建1个子任务
3. 只有当任务确实需要不同类型Agent协作时，才创建多个子任务

【严格禁止】：
- ❌ 禁止创建"验证"、"确认"、"检查结果"类的独立子任务（执行步骤应自带结果确认）
- ❌ 禁止将子任务分配给 coordinator 类型的Agent
- ❌ 禁止过度分解（如把"提取信息"和"创建任务"拆成3个以上步骤）
- ❌ 禁止创建会重复调用相同工具的子任务

【正确示例】：
- 任务"从会议纪要提取信息并创建飞书任务" → 只需1个子任务给feishu_assistant
- 任务"分析数据并生成报告然后发送" → 最多2个子任务

【preferred_agent_type选择】：
- feishu_assistant: 飞书相关操作（任务、审批、联系人、日程等）
- intelligent_assistant: 信息分析、问答、通用对话

请以JSON格式返回，格式如下：
{{
    "subtasks": [
        {{
            "subtask_id": "subtask_1",
            "description": "完整的任务描述，包含所有必要的上下文和执行要求",
            "required_capabilities": ["capability1"],
            "preferred_agent_type": "feishu_assistant",
            "dependencies": [],
            "priority": 1
        }}
    ]
}}

只返回JSON，不要返回其他内容。"""
            
            response = await self._call_llm(prompt)
            decomposition = self._parse_json_response(response)
            
            subtasks = decomposition.get("subtasks", [])
            logger.info(f"任务分解完成，生成 {len(subtasks)} 个子任务")
            
            return subtasks
            
        except Exception as e:
            logger.error(f"任务分解失败: {e}", exc_info=True)
            return []

    async def _assign_subtasks(
        self,
        subtasks: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        分配子任务给专业Agent

        Args:
            subtasks: 子任务列表
            context: 上下文信息

        Returns:
            分配结果列表
        """
        assignments = []
        
        # 【修复问题1】定义不允许分配的Agent类型（防止递归分解）
        forbidden_agent_types = ["coordinator"]
        
        for subtask in subtasks:
            subtask_id = subtask.get("subtask_id", "")
            required_capabilities = subtask.get("required_capabilities", [])
            preferred_agent_type = subtask.get("preferred_agent_type")
            
            # 查找合适的Agent
            assigned_agent = None
            
            # 【修复问题1】如果偏好类型是coordinator，降级到其他类型
            if preferred_agent_type in forbidden_agent_types:
                logger.warning(f"子任务 {subtask_id} 偏好coordinator类型，将降级分配给其他Agent")
                preferred_agent_type = None  # 清除偏好，使用能力匹配
            
            if preferred_agent_type:
                agents = await self.agent_registry.get_available_agents(
                    agent_type=preferred_agent_type
                )
                # 【修复问题1】过滤掉coordinator类型
                agents = [a for a in agents if a.agent_type not in forbidden_agent_types]
                if agents:
                    assigned_agent = agents[0]
            
            if not assigned_agent and required_capabilities:
                # 【修复问题1】过滤掉coordinator专属能力
                filtered_capabilities = [
                    cap for cap in required_capabilities 
                    if cap not in ["task_decomposition", "agent_coordination", "multi_agent_planning"]
                ]
                for capability in (filtered_capabilities or required_capabilities):
                    agents = await self.agent_registry.find_agent_by_capability(capability)
                    available = [
                        a for a in agents
                        if a.status.value not in ["error", "offline"]
                        and a.current_tasks < a.max_concurrent_tasks
                        and a.agent_type not in forbidden_agent_types  # 【修复问题1】排除coordinator
                    ]
                    if available:
                        assigned_agent = available[0]
                        break
            
            if not assigned_agent:
                # 降级：选择任何可用的非coordinator Agent
                agents = await self.agent_registry.get_available_agents()
                # 【修复问题1】排除coordinator类型
                agents = [a for a in agents if a.agent_type not in forbidden_agent_types]
                if agents:
                    assigned_agent = agents[0]
            
            if assigned_agent:
                assignments.append({
                    "subtask_id": subtask_id,
                    "subtask": subtask,
                    "assigned_agent_id": assigned_agent.agent_id,
                    "assigned_agent_type": assigned_agent.agent_type,
                    "status": "pending"
                })
                logger.info(f"子任务 {subtask_id} 分配给 {assigned_agent.agent_name} ({assigned_agent.agent_id})")
            else:
                logger.warning(f"无法为子任务 {subtask_id} 找到合适的Agent")
                assignments.append({
                    "subtask_id": subtask_id,
                    "subtask": subtask,
                    "assigned_agent_id": None,
                    "status": "failed",
                    "error": "无可用Agent"
                })
        
        return assignments

    async def _dispatch_subtasks(
        self,
        task_id: str,
        assignments: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ):
        """
        发送子任务给专业Agent（按依赖顺序执行，使用深度思考模式）
        
        【修复问题3&4】按依赖关系顺序执行子任务，而不是全部并行
        
        Args:
            task_id: 任务ID
            assignments: 任务分配列表
            context: 上下文信息
        """
        import asyncio
        
        # 获取原始任务内容用于上下文传递
        original_task = self.active_tasks.get(task_id, {}).get("original_task", "")
        
        # 构建子任务依赖图
        subtask_map = {a.get("subtask_id"): a for a in assignments}
        completed_subtasks = set()
        pending_subtasks = {a.get("subtask_id") for a in assignments if a.get("assigned_agent_id")}
        
        logger.info(f"开始按依赖顺序执行 {len(pending_subtasks)} 个子任务...")
        
        while pending_subtasks:
            ready_subtasks = []
            for subtask_id in list(pending_subtasks):
                assignment = subtask_map.get(subtask_id)
                if not assignment:
                    continue
                    
                subtask = assignment.get("subtask", {})
                dependencies = subtask.get("dependencies", [])
                
                # 检查所有依赖是否已完成
                if all(dep in completed_subtasks for dep in dependencies):
                    ready_subtasks.append(subtask_id)
            
            if not ready_subtasks:
                # 没有可执行的任务，可能存在循环依赖或所有任务已完成
                if pending_subtasks:
                    logger.warning(f"存在无法解决的依赖关系，强制执行剩余任务: {pending_subtasks}")
                    ready_subtasks = list(pending_subtasks)
                else:
                    break
            
            logger.info(f"本批次执行 {len(ready_subtasks)} 个子任务: {ready_subtasks}")
            
            # 并行执行本批次的子任务
            batch_tasks = []
            for subtask_id in ready_subtasks:
                assignment = subtask_map.get(subtask_id)
                if not assignment:
                    continue
                    
                assigned_agent_id = assignment.get("assigned_agent_id")
                if not assigned_agent_id:
                    continue
                    
                assigned_agent = await self.agent_registry.get_agent(assigned_agent_id)
                
                if assigned_agent:
                    # 构建子任务内容
                    subtask = assignment.get("subtask", {})
                    subtask_description = subtask.get("description", "")
                    
                   # 收集已完成子任务的结果作为上下文
                    dependency_results = {}
                    for dep_id in subtask.get("dependencies", []):
                        if dep_id in self.subtask_results.get(task_id, {}):
                            dependency_results[dep_id] = self.subtask_results[task_id][dep_id]
                    
                    # 【修复问题5】为任务型 Agent 构建结构化参数
                    structured_params = await self._build_task_agent_params(
                        assigned_agent,
                        subtask_description,
                        original_task,
                        dependency_results
                    )
                    
                    # 构建包含完整上下文的任务
                    agent_task = {
                        "message": subtask_description,
                        "task": subtask_description,
                        "session_id": context.get("session_id", "") if context else "",
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                        # 【修复问题2】添加原始任务上下文
                        "original_task": original_task,
                        "parent_context": context.get("original_message", original_task) if context else original_task,
                        # 【修复问题2】添加依赖任务的结果
                        "dependency_results": dependency_results,
                        # 【修复问题5】添加结构化参数（如果存在）
                        **structured_params
                    }
                    
                    # 使用深度思考模式，并传递完整上下文
                    agent_context = {
                        **(context or {}), 
                        "thinking_mode": "deep",
                        # 【修复问题2】确保上下文包含原始任务信息
                        "original_task": original_task,
                        "dependency_results": dependency_results
                    }
                    
                    # 创建异步任务
                    task = asyncio.create_task(
                        self._execute_subtask_and_send_result(
                            assigned_agent,
                            agent_task,
                            agent_context,
                            task_id,
                            subtask_id
                        )
                    )
                    batch_tasks.append((subtask_id, task))
                    
                    logger.info(f"已发送子任务 {subtask_id} 给Agent {assigned_agent_id}（深度思考模式，依赖: {subtask.get('dependencies', [])}）")
                else:
                    logger.warning(f"无法找到Agent {assigned_agent_id}，跳过子任务 {subtask_id}")
                    # 标记为完成（失败），以免阻塞依赖它的任务
                    completed_subtasks.add(subtask_id)
                    pending_subtasks.discard(subtask_id)
            
            # 等待本批次所有任务完成
            if batch_tasks:
                logger.info(f"等待本批次 {len(batch_tasks)} 个子任务完成...")
                
                # 等待所有任务完成或获取结果
                for subtask_id, task in batch_tasks:
                    try:
                        await task
                        logger.info(f"子任务 {subtask_id} 已完成")
                    except Exception as e:
                        logger.error(f"子任务 {subtask_id} 执行异常: {e}")
                    finally:
                        completed_subtasks.add(subtask_id)
                        pending_subtasks.discard(subtask_id)
                
                logger.info(f"本批次执行完成，已完成: {len(completed_subtasks)}, 待执行: {len(pending_subtasks)}")
        
        logger.info(f"所有子任务调度完成，共 {len(completed_subtasks)} 个")
    
    async def _execute_subtask_and_send_result(
        self,
        agent: BaseAgent,
        task: Dict[str, Any],
        context: Dict[str, Any],
        task_id: str,
        subtask_id: str
    ):
        """
        执行子任务并发送结果
        
        Args:
            agent: 执行的Agent
            task: 任务内容
            context: 上下文信息
            task_id: 任务ID
            subtask_id: 子任务ID
        """
        try:
            # 执行子任务
            result = await agent.execute(task, context)
            
            # 发送结果消息（包含完整的结构化数据，供后续依赖任务使用）
            result_content = result.get("response", "") if isinstance(result, dict) else str(result)
            
            # 同时保存完整的结构化结果，供依赖任务使用
            full_result = {
                "subtask_id": subtask_id,
                "result": result_content,
                "success": result.get("success", False) if isinstance(result, dict) else True,
                # 保存完整的原始结果（包含工具调用返回的数据如 task_guid 等）
                "full_result": result if isinstance(result, dict) else {"response": str(result)}
            }
            
            # 更新子任务结果缓存（用于传递给依赖任务）
            if task_id in self.subtask_results:
                self.subtask_results[task_id][subtask_id] = full_result
            
            response_message = AgentMessage(
                message_type=MessageType.TASK_RESPONSE,
                from_agent_id=agent.agent_id,
                to_agent_id=self.agent_id,
                task_id=task_id,
                content=full_result
            )
            await self.message_bus.send_message(response_message)
            logger.info(f"子任务 {subtask_id} 执行完成，结果已发送")
            
        except Exception as e:
            logger.error(f"子任务 {subtask_id} 执行失败: {e}", exc_info=True)
            # 发送错误消息
            error_message = AgentMessage(
                message_type=MessageType.TASK_RESPONSE,
                from_agent_id=agent.agent_id,
                to_agent_id=self.agent_id,
                task_id=task_id,
                content={
                    "subtask_id": subtask_id,
                    "result": None,
                    "success": False,
                    "error": str(e)
                }
            )
            await self.message_bus.send_message(error_message)

    async def _collect_results(
        self,
        task_id: str,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        收集子任务结果

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）

        Returns:
            结果字典 {subtask_id: result}
        """
        import asyncio
        
        results = {}
        start_time = asyncio.get_event_loop().time()
        assignments = self.active_tasks.get(task_id, {}).get("assignments", [])
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            # 检查消息
            messages = await self.message_bus.receive_messages(
                self.agent_id,
                MessageType.TASK_RESPONSE
            )
            
            for message in messages:
                if message.task_id == task_id:
                    subtask_id = message.content.get("subtask_id")
                    result = message.content.get("result")
                    success = message.content.get("success", True)
                    
                    if subtask_id:
                        if success:
                            results[subtask_id] = result
                            self.subtask_results[task_id][subtask_id] = result
                            logger.info(f"收到子任务 {subtask_id} 的执行结果")
                        else:
                            error = message.content.get("error", "执行失败")
                            results[subtask_id] = {"error": error}
                            self.subtask_results[task_id][subtask_id] = {"error": error}
                            logger.error(f"子任务 {subtask_id} 执行失败: {error}")
                        
                        await self.message_bus.mark_message_processed(message.message_id)
            
            # 检查是否所有子任务都完成
            completed_count = len(results)
            total_count = len([a for a in assignments if a.get("assigned_agent_id")])
            
            if completed_count >= total_count:
                logger.info(f"所有子任务已完成: {completed_count}/{total_count}")
                break
            
            await asyncio.sleep(1)  # 等待1秒后再次检查
        
        return results

    async def _integrate_results(
        self,
        task_id: str,
        results: Dict[str, Any],
        original_task: str
    ) -> str:
        """
        整合子任务结果

        Args:
            task_id: 任务ID
            results: 子任务结果
            original_task: 原始任务

        Returns:
            整合后的最终结果
        """
        try:
            # 构建整合提示词
            results_summary = []
            for subtask_id, result in results.items():
                results_summary.append(f"子任务 {subtask_id}:\n{json.dumps(result, ensure_ascii=False, indent=2)}")
            
            prompt = f"""请根据以下子任务的执行结果，整合生成最终回复：

原始任务：{original_task}

子任务结果：
{chr(10).join(results_summary)}

请综合所有子任务的结果，生成一个清晰、完整的最终回复，回答用户的问题或完成任务。"""
            
            final_result = await self._call_llm(prompt)
            return final_result
            
        except Exception as e:
            logger.error(f"结果整合失败: {e}", exc_info=True)
            return json.dumps(results, ensure_ascii=False, indent=2)

    async def _identify_target_agent(self, task: str) -> Optional[BaseAgent]:
        """
        识别任务是否需要特定Agent处理
        
        Args:
            task: 任务描述
            
        Returns:
            目标Agent，如果不需要特定Agent则返回None
        """
        try:
            task_lower = task.lower()
            
            # 判断是否是飞书相关任务
            feishu_keywords = ["飞书", "feishu", "任务", "审批", "联系人", "日程", "文档"]
            if any(keyword in task_lower for keyword in feishu_keywords):
                agents = await self.agent_registry.get_available_agents(agent_type="feishu_assistant")
                if agents:
                    logger.info(f"识别为飞书相关任务，目标Agent: {agents[0].agent_name}")
                    return agents[0]
            
            # 可以添加其他类型的判断逻辑
            # 例如：代码生成、数据分析等
            
            return None
        except Exception as e:
            logger.warning(f"识别目标Agent失败: {e}")
            return None
    
    def _format_agent_info(self, agents: List[BaseAgent]) -> str:
        """格式化Agent信息"""
        if not agents:
            return "暂无可用Agent"
        
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

    # 注意：_get_llm和_call_llm方法已在BaseAgent中实现，这里不再需要重复实现

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
            return {"subtasks": []}
    
    async def _build_task_agent_params(
        self,
        agent: BaseAgent,
        subtask_description: str,
        original_task: str,
        dependency_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        为任务型 Agent 构建结构化参数（兼容 multi-agent 模式）
        
        根据 Agent 类型，从文本描述中提取结构化参数，确保任务型 Agent 能够正确接收参数。
        
        Args:
            agent: 目标 Agent
            subtask_description: 子任务描述（文本）
            original_task: 原始任务内容
            dependency_results: 依赖任务的结果
            
        Returns:
            结构化参数字典（如果 Agent 不是任务型，返回空字典）
        """

        # 检查是否是任务型 Agent（通过 agent_type 判断）
        agent_type = agent.agent_type
        
        # 可以在这里添加其他任务型 Agent 的参数构建逻辑
        # 例如：competitor_analysis, 其他任务型 Agent 等
        
        # 默认返回空字典（对话型 Agent 不需要结构化参数）
        return {}

