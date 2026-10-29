#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标分析生成记录（每次分析落库，供列表与详情查询）
"""
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, JSON, Float, Index

from models.inner_models.base import Base


class TechnicalAnalysisRecordModel(Base):
    """技术指标分析生成记录"""

    __tablename__ = "technical_analysis_records"

    id = Column(String(36), primary_key=True, comment="记录 ID")
    user_id = Column(String(36), nullable=False, index=True, comment="用户 ID")

    symbol = Column(String(100), nullable=False, index=True, comment="交易对")
    analysis_date = Column(String(32), nullable=True, comment="分析截止日 YYYY-MM-DD")
    timeframe = Column(String(20), nullable=False, comment="K 线周期")
    lookback_days = Column(Integer, nullable=False, default=30, comment="回溯天数")
    temperature = Column(Float, nullable=True, comment="LLM 温度")
    llm_model_id = Column(Integer, nullable=True, comment="模型管理 ID")
    llm_model_name = Column(String(200), nullable=True, comment="模型展示名")

    success = Column(Boolean, nullable=False, default=True, index=True, comment="是否成功")
    error_message = Column(Text, nullable=True, comment="失败原因")
    summary_preview = Column(String(500), nullable=True, comment="成功时摘要预览（列表用）")

    result_payload = Column(JSON, nullable=True, comment="完整响应快照（与 analyze 成功 data 结构一致）")

    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True, comment="生成时间")

    __table_args__ = (
        Index(
            "idx_ta_record_cache_lookup",
            "user_id",
            "symbol",
            "timeframe",
            "analysis_date",
            "success",
        ),
        Index(
            "idx_ta_record_context_lookup",
            "user_id",
            "symbol",
            "timeframe",
            "created_at",
            "success",
        ),
    )
