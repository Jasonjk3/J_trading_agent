#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息面采集 API Schema
"""
from typing import Optional, List
from pydantic import BaseModel, Field

from models.inner_models.news_intelligence_model import NewsIntelligenceAgentStatus


class CreateNewsIntelligenceAgentRequest(BaseModel):
    """创建消息面采集任务"""
    name: str = Field(..., min_length=1, max_length=100, description="任务名称")
    remark: Optional[str] = Field(None, max_length=255, description="备注")
    sectors: List[str] = Field(..., min_length=1, description="金融方向 code 列表")
    customKeywords: Optional[str] = Field(None, max_length=500, description="自定义关键词")
    symbolCodes: Optional[str] = Field(None, max_length=500, description="标的代码")
    llmModelId: int = Field(..., description="LLM 模型 ID")
    intervalMinutes: int = Field(60, ge=1, le=720, description="采集间隔（分钟）")
    maxItemsPerBatch: int = Field(10, ge=1, le=50, description="单次条数上限")
    temperature: float = Field(0.3, ge=0.0, le=1.0, description="温度")
    runOnCreate: bool = Field(False, description="创建后是否启动")


class UpdateNewsIntelligenceAgentRequest(BaseModel):
    """更新消息面采集任务"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    remark: Optional[str] = Field(None, max_length=255)
    sectors: Optional[List[str]] = Field(None, min_length=1)
    customKeywords: Optional[str] = Field(None, max_length=500)
    symbolCodes: Optional[str] = Field(None, max_length=500)
    llmModelId: Optional[int] = None
    intervalMinutes: Optional[int] = Field(None, ge=1, le=720)
    maxItemsPerBatch: Optional[int] = Field(None, ge=1, le=50)
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)


class NewsIntelligenceAgentResponse(BaseModel):
    """任务响应（与前端字段对齐）"""
    id: str
    name: str
    remark: Optional[str] = None
    sectors: List[str]
    customKeywords: Optional[str] = None
    symbolCodes: Optional[str] = None
    llmModelId: int
    llmModelName: Optional[str] = None
    intervalMinutes: int
    maxItemsPerBatch: int
    temperature: float
    status: NewsIntelligenceAgentStatus
    lastRunAt: Optional[str] = None
    createdAt: str
    updatedAt: str

    class Config:
        from_attributes = True


class NewsTimelineItemResponse(BaseModel):
    """时间轴单条"""
    id: str
    agentId: str
    title: str
    summary: Optional[str] = None
    sourceUrl: Optional[str] = None
    sourceName: Optional[str] = None
    eventTime: Optional[str] = None
    ingestedAt: str
    sortTime: str

    class Config:
        from_attributes = True
