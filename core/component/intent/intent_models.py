#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 16:50
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
意图识别数据模型
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """意图类型枚举"""
    # 通用意图
    GREETING = "greeting"  # 问候
    QUESTION = "question"  # 提问
    COMMAND = "command"  # 命令
    CHAT = "chat"  # 闲聊
    
    # 业务意图（可根据实际业务扩展）
    SEARCH = "search"  # 搜索
    ANALYSIS = "analysis"  # 分析
    CALCULATION = "calculation"  # 计算
    TRANSLATION = "translation"  # 翻译
    CODE_GENERATION = "code_generation"  # 代码生成
    DATA_PROCESSING = "data_processing"  # 数据处理
    FEISHU_OPERATION = "feishu_operation"  # 飞书操作
    UNKNOWN = "unknown"  # 未知意图


class IntentConfidence(str, Enum):
    """意图置信度"""
    HIGH = "high"  # 高置信度 (>0.8)
    MEDIUM = "medium"  # 中等置信度 (0.5-0.8)
    LOW = "low"  # 低置信度 (<0.5)


class ReasoningMode(str, Enum):
    """推理模式"""
    REACT = "react"  # ReAct模式：工具使用、事实核查、复杂规划
    COT = "cot"  # Chain of Thought模式：数学推理、逻辑分析、常识问答
    NONE = "none"  # 不需要推理：简单问答、问候等


class Intent(BaseModel):
    """意图模型"""
    intent_type: IntentType  # 意图类型
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)  # 置信度 (0-1)
    confidence_level: IntentConfidence = IntentConfidence.LOW  # 置信度等级
    reasoning_mode: ReasoningMode = ReasoningMode.NONE  # 推理模式
    entities: Dict[str, Any] = Field(default_factory=dict)  # 提取的实体信息
    keywords: List[str] = Field(default_factory=list)  # 关键词
    original_text: str  # 原始文本
    processed_text: str  # 处理后的文本
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 元数据
    created_at: datetime = Field(default_factory=datetime.now)

    def __init__(self, **data):
        """初始化，自动计算置信度等级"""
        super().__init__(**data)
        # 如果confidence_level未设置，根据confidence自动计算
        if "confidence_level" not in data:
            if self.confidence >= 0.8:
                self.confidence_level = IntentConfidence.HIGH
            elif self.confidence >= 0.5:
                self.confidence_level = IntentConfidence.MEDIUM
            else:
                self.confidence_level = IntentConfidence.LOW

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IntentRoute(BaseModel):
    """意图路由结果"""
    intent: Intent  # 识别的意图
    target_agent_id: Optional[str] = None  # 目标智能体ID
    target_agent_type: Optional[str] = None  # 目标智能体类型
    required_capabilities: List[str] = Field(default_factory=list)  # 所需能力
    routing_reason: str = ""  # 路由原因
    alternative_agents: List[str] = Field(default_factory=list)  # 备选智能体

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

