#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
认证依赖注入
提供获取当前用户和管理员权限检查的依赖
"""
from fastapi import Depends, HTTPException, Request, Header
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.v1.services.auth_service import AuthService
from app.v1.crud.user_crud import get_user_by_id
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from models.inner_models.user_model import UserModel, UserRole


async def get_token_from_header(
    authorization: Optional[str] = Header(None)
) -> Optional[str]:
    """从请求头中提取Token"""
    if not authorization:
        return None
    
    # Bearer token格式
    if authorization.startswith("Bearer "):
        return authorization[7:]
    
    return authorization


async def get_current_user(
    token: Optional[str] = Depends(get_token_from_header),
    session: AsyncSession = Depends(get_db_session),
    auth_service: AuthService = Depends(lambda: AuthService())
) -> UserModel:
    """
    获取当前登录用户（依赖注入）
    
    Args:
        token: JWT Token
        session: 数据库会话
        auth_service: 认证服务
        
    Returns:
        当前用户模型
        
    Raises:
        HTTPException: Token无效或用户不存在
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="未提供认证令牌"
        )
    
    # 验证Token
    payload = auth_service.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="无效的认证令牌"
        )
    
    # 从Token中获取用户ID
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="令牌中缺少用户信息"
        )
    
    # 从数据库获取用户
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户不存在"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="用户已被禁用"
        )
    
    return user


async def get_current_admin(
    current_user: UserModel = Depends(get_current_user)
) -> UserModel:
    """
    获取当前管理员用户（依赖注入）
    只有管理员角色才能访问
    
    Args:
        current_user: 当前用户
        
    Returns:
        当前管理员用户
        
    Raises:
        HTTPException: 非管理员用户
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="需要管理员权限"
        )
    
    return current_user
