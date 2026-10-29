#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
认证API路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.v1.schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    PasswordResetRequest,
    UserResponse
)
from app.v1.services.auth_service import AuthService
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.auth import get_current_user
from models.inner_models.user_model import UserModel

# 创建路由器
router = APIRouter(prefix="/auth", tags=["认证"])


def get_auth_service() -> AuthService:
    """获取认证服务实例"""
    return AuthService()


@router.post("/login", summary="用户登录", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    用户登录
    
    Args:
        request: 登录请求
        session: 数据库会话
        auth_service: 认证服务
        
    Returns:
        登录响应（包含Token和用户信息）
    """
    try:
        result = await auth_service.login(
            session=session,
            username=request.username,
            password=request.password
        )
        
        if not result:
            return ApiResponse.failed_response(
                msg="用户名或密码错误",
                code=ResponseCode.AUTH_ERROR.value
            )
        
        await session.commit()
        return ApiResponse.success_response(
            msg="登录成功",
            data=result
        )
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return ApiResponse.failed_response(
            msg=f"登录失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/logout", summary="用户登出")
async def logout(current_user: UserModel = Depends(get_current_user)):
    """
    用户登出
    
    Args:
        current_user: 当前用户（通过依赖注入获取）
        
    Returns:
        登出响应
    """
    # 前端删除Token即可，这里可以记录日志或处理Token黑名单
    logger.info(f"用户 {current_user.username} 登出")
    return ApiResponse.success_response(msg="登出成功")


@router.get("/me", summary="获取当前用户信息", response_model=UserResponse)
async def get_current_user_info(current_user: UserModel = Depends(get_current_user)):
    """
    获取当前登录用户信息
    
    Args:
        current_user: 当前用户（通过依赖注入获取）
        
    Returns:
        用户信息
    """
    return ApiResponse.success_response(
        msg="获取成功",
        data={
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role.value,
            "is_active": current_user.is_active,
            "feature_permissions": current_user.feature_permissions if current_user.feature_permissions else [],
            "created_at": current_user.created_at.isoformat(),
            "updated_at": current_user.updated_at.isoformat()
        }
    )


@router.post("/reset-password", summary="重置密码")
async def reset_password(
    request: PasswordResetRequest,
    session: AsyncSession = Depends(get_db_session),
    auth_service: AuthService = Depends(get_auth_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    重置密码
    
    Args:
        request: 密码重置请求
        session: 数据库会话
        auth_service: 认证服务
        current_user: 当前用户
        
    Returns:
        重置结果
    """
    try:
        # 验证用户名是否匹配当前用户
        if current_user.username != request.username:
            return ApiResponse.failed_response(
                msg="只能重置自己的密码",
                code=ResponseCode.AUTH_ERROR.value
            )
        
        success = await auth_service.reset_password(
            session=session,
            username=request.username,
            old_password=request.old_password,
            new_password=request.new_password
        )
        
        if not success:
            return ApiResponse.failed_response(
                msg="旧密码错误或用户不存在",
                code=ResponseCode.AUTH_ERROR.value
            )
        
        await session.commit()
        return ApiResponse.success_response(msg="密码重置成功")
    except Exception as e:
        logger.error(f"密码重置失败: {e}")
        return ApiResponse.failed_response(
            msg=f"密码重置失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
