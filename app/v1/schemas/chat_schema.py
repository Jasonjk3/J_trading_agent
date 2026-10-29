#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 18:20
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
聊天API Schema
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """聊天请求"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=5000)
    session_id: Optional[str] = Field(None, description="会话ID，如果不提供则创建新会话")
    user_id: Optional[str] = Field(None, description="用户ID")
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")
    thinking_mode: str = Field("normal", description="思考模式：normal（普通模式，直接返回结果）/ deep（深度思考模式，单agent思维链）/ expert（专家模式，multi-agent思维链），默认normal")
    model_id: Optional[str] = Field(None, description="指定模型ID，如果不提供则使用默认模型")
    images: Optional[List[str]] = Field(None, description="图片列表（base64编码），支持多模态分析")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "你好，请介绍一下你自己",
                "session_id": "session_123",
                "user_id": "user_456",
                "thinking_mode": "normal"
            }
        }


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色：user/assistant/system")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[str] = Field(None, description="时间戳")


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool = Field(..., description="是否成功")
    response: Optional[str] = Field(None, description="助手回复")
    session_id: str = Field(..., description="会话ID")
    agent_id: Optional[str] = Field(None, description="处理的智能体ID")
    error: Optional[str] = Field(None, description="错误信息")
    history: Optional[List[Dict[str, Any]]] = Field(None, description="会话历史")
    trace_id: Optional[str] = Field(None, description="Agent 对话执行追踪ID")
    error_code: Optional[str] = Field(None, description="稳定的执行错误码")
    runtime: Optional[Dict[str, Any]] = Field(None, description="对话运行状态和预算计数，不包含工具审计载荷")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "response": "你好！我是智能助手，很高兴为你服务。",
                "session_id": "session_123",
                "agent_id": "agent_789"
            }
        }


class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    user_id: Optional[str] = Field(None, description="用户ID")
    context: Optional[Dict[str, Any]] = Field(None, description="初始上下文")


class SessionCreateResponse(BaseModel):
    """创建会话响应"""
    session_id: str = Field(..., description="会话ID")
    created_at: str = Field(..., description="创建时间")


class SessionHistoryResponse(BaseModel):
    """会话历史响应"""
    session_id: str = Field(..., description="会话ID")
    history: List[ChatMessage] = Field(..., description="历史记录")
    total: int = Field(..., description="总记录数")


class SessionUpdateRequest(BaseModel):
    """更新会话请求"""
    title: Optional[str] = Field(None, description="会话名称", max_length=200)

