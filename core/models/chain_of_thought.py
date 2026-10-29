#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
思维链（Chain of Thought）模型
支持多步骤推理和复杂任务处理
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class ThoughtStatus(str, Enum):
    """思维步骤状态"""
    PENDING = "pending"  # 等待执行
    THINKING = "thinking"  # 思考中
    EXECUTING = "executing"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 已跳过


class ThoughtType(str, Enum):
    """思维步骤类型"""
    ANALYSIS = "analysis"  # 分析
    TOOL_CALL = "tool_call"  # 工具调用
    REASONING = "reasoning"  # 推理
    DECISION = "decision"  # 决策
    SYNTHESIS = "synthesis"  # 综合
    VALIDATION = "validation"  # 验证
    INTENT_RECOGNITION = "intent_recognition"  # 意图识别
    AGENT_ROUTING = "agent_routing"  # Agent路由
    TASK_DECOMPOSITION = "task_decomposition"  # 任务分解
    AGENT_EXECUTION = "agent_execution"  # Agent执行
    RESULT_INTEGRATION = "result_integration"  # 结果整合


class ThoughtStep(BaseModel):
    """思维步骤"""
    step_id: str = Field(default_factory=lambda: str(uuid4()))
    step_number: int  # 步骤序号
    thought_type: ThoughtType  # 步骤类型
    description: str  # 步骤描述
    reasoning: Optional[str] = None  # 推理过程
    status: ThoughtStatus = ThoughtStatus.PENDING  # 状态
    tool_name: Optional[str] = None  # 工具名称（如果是工具调用）
    tool_parameters: Optional[Dict[str, Any]] = None  # 工具参数
    result: Optional[Any] = None  # 执行结果
    error: Optional[str] = None  # 错误信息
    dependencies: List[int] = Field(default_factory=list)  # 依赖的步骤序号
    # Multi-Agent支持
    assigned_agent_id: Optional[str] = None  # 分配的Agent ID
    assigned_agent_type: Optional[str] = None  # 分配的Agent类型
    subtask_id: Optional[str] = None  # 关联的子任务ID（如果是子任务）
    parent_thought_id: Optional[str] = None  # 父思维链ID（如果是子任务）
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    meta_data: Dict[str, Any] = Field(default_factory=dict)  # 元数据

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChainOfThought(BaseModel):
    """思维链"""
    thought_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: Optional[str] = None  # 关联的任务ID
    session_id: str  # 会话ID
    original_task: str  # 原始任务描述
    goal: str  # 目标描述
    steps: List[ThoughtStep] = Field(default_factory=list)  # 思维步骤列表
    current_step: int = 0  # 当前执行的步骤序号
    status: str = "planning"  # 状态: planning, executing, completed, failed
    context: Dict[str, Any] = Field(default_factory=dict)  # 上下文信息
    intermediate_results: Dict[str, Any] = Field(default_factory=dict)  # 中间结果
    final_result: Optional[Any] = None  # 最终结果
    error: Optional[str] = None  # 错误信息
    # Multi-Agent支持
    is_global_chain: bool = False  # 是否为全局思维链
    parent_thought_id: Optional[str] = None  # 父思维链ID（如果是子任务）
    child_thought_ids: List[str] = Field(default_factory=list)  # 子思维链ID列表
    coordinator_agent_id: Optional[str] = None  # 协调Agent ID
    subtasks: List[Dict[str, Any]] = Field(default_factory=list)  # 子任务列表
    agent_results: Dict[str, Any] = Field(default_factory=dict)  # Agent执行结果 {agent_id: result}
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def add_step(
        self,
        step_number: int,
        thought_type: ThoughtType,
        description: str,
        dependencies: Optional[List[int]] = None,
        tool_name: Optional[str] = None,
        tool_parameters: Optional[Dict[str, Any]] = None,
        assigned_agent_id: Optional[str] = None,
        assigned_agent_type: Optional[str] = None,
        subtask_id: Optional[str] = None,
        parent_thought_id: Optional[str] = None,
        meta_data: Optional[Dict[str, Any]] = None
    ) -> ThoughtStep:
        """
        添加思维步骤
        
        Args:
            step_number: 步骤序号
            thought_type: 步骤类型
            description: 步骤描述
            dependencies: 依赖的步骤序号
            tool_name: 工具名称
            tool_parameters: 工具参数
            assigned_agent_id: 分配的Agent ID（Multi-Agent支持）
            assigned_agent_type: 分配的Agent类型（Multi-Agent支持）
            subtask_id: 子任务ID（Multi-Agent支持）
            parent_thought_id: 父思维链ID（Multi-Agent支持）
            meta_data: 元数据
            
        Returns:
            创建的思维步骤
        """
        step = ThoughtStep(
            step_number=step_number,
            thought_type=thought_type,
            description=description,
            dependencies=dependencies or [],
            tool_name=tool_name,
            tool_parameters=tool_parameters,
            assigned_agent_id=assigned_agent_id,
            assigned_agent_type=assigned_agent_type,
            subtask_id=subtask_id,
            parent_thought_id=parent_thought_id,
            meta_data=meta_data or {}
        )
        self.steps.append(step)
        return step

    def get_step(self, step_number: int) -> Optional[ThoughtStep]:
        """获取指定步骤"""
        for step in self.steps:
            if step.step_number == step_number:
                return step
        return None

    def get_current_step(self) -> Optional[ThoughtStep]:
        """获取当前步骤"""
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def get_pending_steps(self) -> List[ThoughtStep]:
        """获取待执行的步骤"""
        return [step for step in self.steps if step.status == ThoughtStatus.PENDING]

    def get_completed_steps(self) -> List[ThoughtStep]:
        """获取已完成的步骤"""
        return [step for step in self.steps if step.status == ThoughtStatus.COMPLETED]

    def can_execute_step(self, step_number: int) -> bool:
        """
        检查步骤是否可以执行（依赖是否满足）
        
        Args:
            step_number: 步骤序号
            
        Returns:
            是否可以执行
        """
        step = self.get_step(step_number)
        if not step:
            return False
        
        # 检查依赖的步骤是否都已完成或被跳过
        for dep_step_num in step.dependencies:
            dep_step = self.get_step(dep_step_num)
            if not dep_step or dep_step.status not in [ThoughtStatus.COMPLETED, ThoughtStatus.SKIPPED]:
                return False
        
        return True

    def get_next_executable_step(self) -> Optional[ThoughtStep]:
        """获取下一个可执行的步骤"""
        for step in self.steps:
            # 只返回PENDING状态的步骤，并且依赖已满足
            if step.status == ThoughtStatus.PENDING and self.can_execute_step(step.step_number):
                return step
        return None

    def update_step_status(
        self,
        step_number: int,
        status: ThoughtStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ):
        """
        更新步骤状态
        
        Args:
            step_number: 步骤序号
            status: 新状态
            result: 执行结果
            error: 错误信息
        """
        step = self.get_step(step_number)
        if not step:
            return
        
        step.status = status
        if result is not None:
            step.result = result
        if error:
            step.error = error
        
        if status == ThoughtStatus.THINKING or status == ThoughtStatus.EXECUTING:
            if not step.started_at:
                step.started_at = datetime.now()
        elif status == ThoughtStatus.COMPLETED or status == ThoughtStatus.FAILED:
            step.completed_at = datetime.now()
        
        self.updated_at = datetime.now()

    def is_completed(self) -> bool:
        """检查思维链是否完成"""
        if not self.steps:
            return False
        
        # 所有步骤都已完成或跳过
        for step in self.steps:
            if step.status not in [ThoughtStatus.COMPLETED, ThoughtStatus.SKIPPED]:
                return False
        
        return True

    def get_progress(self) -> float:
        """
        获取执行进度
        
        Returns:
            进度百分比 (0.0 - 1.0)
        """
        if not self.steps:
            return 0.0
        
        completed_count = len(self.get_completed_steps())
        return completed_count / len(self.steps)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "thought_id": self.thought_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "original_task": self.original_task,
            "goal": self.goal,
            "steps": [step.dict() for step in self.steps],
            "current_step": self.current_step,
            "status": self.status,
            "context": self.context,
            "intermediate_results": self.intermediate_results,
            "final_result": self.final_result,
            "error": self.error,
            "progress": self.get_progress(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }

