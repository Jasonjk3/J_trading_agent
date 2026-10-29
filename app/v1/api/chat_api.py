#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 18:20
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
聊天API路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional
from loguru import logger

from app.v1.schemas.chat_schema import (
    ChatRequest,
    SessionCreateRequest,
    SessionUpdateRequest
)
from app.v1.services.chat_service import ChatService
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.database import get_db_session
from app.public.dependencies.auth import get_current_user
from models.inner_models.user_model import UserModel

# 创建路由器
router = APIRouter(prefix="/chat", tags=["聊天"])


def get_chat_service(request: Request) -> ChatService:
    """
    获取聊天服务实例（依赖注入）

    Args:
        request: FastAPI请求对象

    Returns:
        ChatService实例
    """
    if not hasattr(request.app.state, 'chat_service'):
        raise HTTPException(
            status_code=500,
            detail="聊天服务未初始化，请检查应用启动配置"
        )
    return request.app.state.chat_service


@router.get("/models", summary="当前用户可用的助手模型")
async def assistant_models(current_user=Depends(get_current_user), service=Depends(get_chat_service),
                           db_session=Depends(get_db_session)):
    return ApiResponse.success_response(data={"items": await service.conversation_runtime.available_models(
        db_session, current_user.id)})


@router.get("/tools", summary="当前用户已启用的只读工具")
async def assistant_tools(current_user=Depends(get_current_user), db_session=Depends(get_db_session)):
    from app.v1.services.agent_conversation_service import tools_for_user
    tools = await tools_for_user(current_user.id, db_session)
    return ApiResponse.success_response(data={"version": "quant-read-v1", "items": [
        {"name": tool.name, "description": tool.description, "side_effect": tool.side_effect} for tool in tools]})


@router.post("/", summary="发送消息")
async def chat(
    request: ChatRequest,
    current_user: UserModel = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
    db_session = Depends(get_db_session)
):
    """
    发送聊天消息

    Args:
        request: 聊天请求
        current_user: 当前登录用户（通过认证依赖获取）
        service: 聊天服务
        db_session: 数据库会话

    Returns:
        聊天响应
    """
    try:
        # 将db_session添加到context中，以便service可以使用它查询模型信息
        context = request.context or {}
        context["db_session"] = db_session
        
        # 使用当前登录用户的ID，忽略请求中的user_id（确保数据隔离）
        user_id = current_user.id
        
        response = await service.chat(
            message=request.message,
            session_id=request.session_id,
            user_id=user_id,
            context=context,
            thinking_mode=request.thinking_mode,
            model_id=request.model_id,
            images=request.images
        )
        
        if response.success:
            return ApiResponse.success_response(
                msg="消息处理成功",
                code=ResponseCode.OK.value,
                data=response.dict()
            )
        else:
            return ApiResponse.failed_response(
                msg=response.error or "消息处理失败",
                code=ResponseCode.FAILED.value,
                data=response.dict()
            )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"处理请求失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/sessions", summary="创建会话")
async def create_session(
    request: SessionCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service)
):
    """
    创建新会话

    Args:
        request: 创建会话请求
        current_user: 当前登录用户（通过认证依赖获取）
        service: 聊天服务

    Returns:
        会话信息
    """
    try:
        # 使用当前登录用户的ID，忽略请求中的user_id（确保数据隔离）
        result = await service.create_session(
            user_id=current_user.id,
            context=request.context
        )
        return ApiResponse.success_response(
            msg="会话创建成功",
            code=ResponseCode.OK.value,
            data=result
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"创建会话失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/sessions/{session_id}/history", summary="获取会话历史")
async def get_history(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    limit: Optional[int] = 50,
    service: ChatService = Depends(get_chat_service)
):
    """
    获取会话历史

    Args:
        session_id: 会话ID
        current_user: 当前登录用户（通过认证依赖获取）
        limit: 返回数量限制
        service: 聊天服务

    Returns:
        会话历史
    """
    try:
        # 验证会话是否属于当前用户（在service层进行验证）
        result = await service.get_session_history(
            session_id=session_id,
            user_id=current_user.id,
            limit=limit
        )
        return ApiResponse.success_response(
            msg="获取会话历史成功",
            code=ResponseCode.OK.value,
            data=result
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取历史失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/sessions", summary="获取会话列表")
async def get_sessions(
    current_user: UserModel = Depends(get_current_user),
    active_only: bool = True,
    service: ChatService = Depends(get_chat_service)
):
    """
    获取会话列表

    Args:
        current_user: 当前登录用户（通过认证依赖获取）
        active_only: 是否只返回活跃会话
        service: 聊天服务

    Returns:
        会话列表（只返回当前用户的会话）
    """
    try:
        # 只返回当前用户的会话，忽略请求参数中的user_id（确保数据隔离）
        result = await service.get_sessions(user_id=current_user.id, active_only=active_only)
        return ApiResponse.success_response(
            msg="获取会话列表成功",
            code=ResponseCode.OK.value,
            data=result
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取会话列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/sessions/{session_id}", summary="更新会话")
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service)
):
    """
    更新会话信息

    Args:
        session_id: 会话ID
        request: 更新请求
        current_user: 当前登录用户（通过认证依赖获取）
        service: 聊天服务

    Returns:
        更新结果
    """
    try:
        # 验证会话是否属于当前用户（在service层进行验证）
        result = await service.update_session(
            session_id=session_id,
            user_id=current_user.id,
            title=request.title
        )
        if result:
            return ApiResponse.success_response(
                msg="更新会话成功",
                code=ResponseCode.OK.value,
                data={"session_id": session_id}
            )
        else:
            return ApiResponse.failed_response(
                msg="会话不存在或更新失败",
                code=ResponseCode.NOT_FOUND.value
            )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"更新会话失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service)
):
    """
    删除会话（软删除，设置 is_active=False）

    Args:
        session_id: 会话ID
        current_user: 当前登录用户（通过认证依赖获取）
        service: 聊天服务

    Returns:
        删除结果
    """
    try:
        # 验证会话是否属于当前用户（在service层进行验证）
        result = await service.delete_session(
            session_id=session_id,
            user_id=current_user.id
        )
        if result:
            return ApiResponse.success_response(
                msg="删除会话成功",
                code=ResponseCode.OK.value,
                data={"session_id": session_id}
            )
        else:
            return ApiResponse.failed_response(
                msg="会话不存在或删除失败",
                code=ResponseCode.NOT_FOUND.value
            )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"删除会话失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/agents", summary="获取可用智能体列表")
async def get_agents(
    service: ChatService = Depends(get_chat_service)
):
    """
    获取可用的智能体列表

    Args:
        service: 聊天服务

    Returns:
        智能体列表
    """
    try:
        agents = await service.get_available_agents()
        return ApiResponse.success_response(
            msg="获取智能体列表成功",
            code=ResponseCode.OK.value,
            data={"agents": agents}
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取智能体列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
