#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息面采集 Agent 与资讯条目 数据库模型
"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, String, Integer, DateTime, JSON, Float, Enum as SQLEnum, Index, Text

from models.inner_models.base import Base


class NewsIntelligenceAgentStatus(str, PyEnum):
    """消息面采集任务状态"""
    RUNNING = "running"
    STOPPED = "stopped"


class NewsIntelligenceAgentModel(Base):
    """消息面采集 Agent 配置表"""
    __tablename__ = "news_intelligence_agents"

    id = Column(String(36), primary_key=True, comment="任务 ID")
    user_id = Column(String(36), nullable=False, index=True, comment="所属用户 ID")
    name = Column(String(100), nullable=False, comment="任务名称")
    remark = Column(String(255), nullable=True, comment="备注")
    sectors = Column(JSON, nullable=False, default=list, comment="金融方向 code 列表")
    custom_keywords = Column(String(500), nullable=True, comment="自定义关键词")
    symbol_codes = Column(String(500), nullable=True, comment="相关标的代码")
    llm_model_id = Column(Integer, nullable=False, comment="LLM 模型 ID")
    interval_minutes = Column(Integer, nullable=False, default=60, comment="采集间隔（分钟）")
    max_items_per_batch = Column(Integer, nullable=False, default=10, comment="单次条数上限")
    temperature = Column(Float, nullable=False, default=0.3, comment="采样温度")
    status = Column(
        SQLEnum(NewsIntelligenceAgentStatus, values_callable=lambda x: [e.value for e in x]),
        default=NewsIntelligenceAgentStatus.STOPPED,
        index=True,
        comment="运行状态",
    )
    last_run_at = Column(DateTime, nullable=True, comment="最近采集时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    __table_args__ = (
        Index("idx_news_intel_user_status", "user_id", "status"),
    )

    def __repr__(self):
        return f"<NewsIntelligenceAgentModel(id={self.id}, name={self.name}, status={self.status})>"


class NewsIntelligenceItemModel(Base):
    """采集到的资讯条目（时间轴）"""
    __tablename__ = "news_intelligence_items"

    id = Column(String(36), primary_key=True, comment="条目 ID")
    agent_id = Column(String(36), nullable=False, index=True, comment="所属任务 ID")
    title = Column(String(500), nullable=False, comment="标题")
    summary = Column(Text, nullable=True, comment="摘要")
    source_url = Column(String(2000), nullable=True, comment="来源链接")
    source_name = Column(String(200), nullable=True, comment="来源名称")
    event_time = Column(DateTime, nullable=True, index=True, comment="资讯发布时间")
    ingested_at = Column(DateTime, nullable=False, comment="入库时间")
    sort_time = Column(DateTime, nullable=False, index=True, comment="展示排序时间")
    dedup_hash = Column(String(64), nullable=True, comment="去重哈希")

    __table_args__ = (
        Index("idx_news_item_agent_sort", "agent_id", "sort_time"),
    )

    def __repr__(self):
        return f"<NewsIntelligenceItemModel(id={self.id}, agent_id={self.agent_id}, title={self.title[:20]}...)>"

