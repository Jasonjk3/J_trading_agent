#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 17:00
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
意图识别数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, JSON, Index

from core.component.intent.intent_models import IntentConfidence
from models.inner_models.base import Base


class IntentModel(Base):
    """意图表模型"""
    __tablename__ = "agent_intents"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    intent_type = Column(String(50), nullable=False, index=True, comment="意图类型")
    confidence = Column(Float, default=0.0, comment="置信度")
    confidence_level = Column(String(10), default=IntentConfidence.LOW, comment="置信度等级")
    entities = Column(JSON, default=dict, comment="实体信息")
    keywords = Column(JSON, default=list, comment="关键词列表")
    original_text = Column(Text, nullable=False, comment="原始文本")
    processed_text = Column(Text, nullable=False, comment="处理后的文本")
    meta_data = Column(JSON, default=dict, comment="元数据")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    # 创建索引
    __table_args__ = (
        Index('idx_type_confidence', 'intent_type', 'confidence'),
    )

    def __repr__(self):
        return f"<IntentModel(intent_type={self.intent_type}, confidence={self.confidence})>"


class IntentRouteModel(Base):
    """意图路由表模型"""
    __tablename__ = "agent_intent_routes"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    intent_id = Column(Integer, nullable=False, index=True, comment="意图ID")
    target_agent_id = Column(String(36), nullable=True, index=True, comment="目标智能体ID")
    target_agent_type = Column(String(50), nullable=True, comment="目标智能体类型")
    required_capabilities = Column(JSON, default=list, comment="所需能力")
    routing_reason = Column(String(500), nullable=True, comment="路由原因")
    alternative_agents = Column(JSON, default=list, comment="备选智能体")
    created_at = Column(DateTime, default=datetime.now, index=True, comment="创建时间")

    def __repr__(self):
        return f"<IntentRouteModel(intent_id={self.intent_id}, target_agent_id={self.target_agent_id})>"

