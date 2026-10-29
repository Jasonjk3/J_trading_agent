#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
用户管理API路由（管理员功能）
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from loguru import logger

from app.v1.schemas.auth_schema import (
    UserCreateRequest,
    UserUpdateRequest,
    UserResponse,
    FeaturePermissionsUpdateRequest
)
from app.v1.services.auth_service import AuthService
from app.v1.crud.user_crud import (
    get_users,
    get_user_by_id,
    update_user,
    delete_user
)
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.auth import get_current_admin
from models.inner_models.user_model import UserModel, UserRole

# 创建路由器
router = APIRouter(prefix="/users", tags=["用户管理"])


def get_auth_service() -> AuthService:
    """获取认证服务实例"""
    return AuthService()


@router.get("", summary="获取用户列表")
async def get_user_list(
    is_active: Optional[bool] = Query(None, description="是否激活"),
    role: Optional[str] = Query(None, description="角色筛选"),
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    session: AsyncSession = Depends(get_db_session),
    current_admin: UserModel = Depends(get_current_admin)
):
    """
    获取用户列表（仅管理员）
    
    Args:
        is_active: 是否激活筛选
        role: 角色筛选
        skip: 跳过数量
        limit: 返回数量
        session: 数据库会话
        current_admin: 当前管理员用户
        
    Returns:
        用户列表
    """
    try:
        # 转换角色字符串为枚举
        role_enum = None
        if role:
            try:
                role_enum = UserRole(role)
            except ValueError:
                return ApiResponse.failed_response(
                    msg=f"无效的角色: {role}",
                    code=ResponseCode.FAILED.value
                )
        
        users = await get_users(
            session=session,
            is_active=is_active,
            role=role_enum,
            skip=skip,
            limit=limit
        )
        
        user_list = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "feature_permissions": user.feature_permissions if user.feature_permissions else [],
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat()
            }
            for user in users
        ]
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "users": user_list,
                "total": len(user_list)
            }
        )
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}")
        return ApiResponse.failed_response(
            msg=f"获取用户列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{user_id}", summary="获取用户详情")
async def get_user_detail(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_admin: UserModel = Depends(get_current_admin)
):
    """
    获取用户详情（仅管理员）
    
    Args:
        user_id: 用户ID
        session: 数据库会话
        current_admin: 当前管理员用户
        
    Returns:
        用户详情
    """
    try:
        user = await get_user_by_id(session, user_id)
        if not user:
            return ApiResponse.failed_response(
                msg="用户不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "feature_permissions": user.feature_permissions if user.feature_permissions else [],
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat()
            }
        )
    except Exception as e:
        logger.error(f"获取用户详情失败: {e}")
        return ApiResponse.failed_response(
            msg=f"获取用户详情失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("", summary="创建用户")
async def create_user(
    request: UserCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    auth_service: AuthService = Depends(get_auth_service),
    current_admin: UserModel = Depends(get_current_admin)
):
    """
    创建用户（仅管理员）
    
    Args:
        request: 创建用户请求
        session: 数据库会话
        auth_service: 认证服务
        current_admin: 当前管理员用户
        
    Returns:
        创建结果
    """
    try:
        user = await auth_service.create_user_account(
            session=session,
            username=request.username,
            password=request.password,
            email=request.email,
            role=request.role,
            is_active=request.is_active
        )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="用户创建成功",
            data={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "feature_permissions": user.feature_permissions if user.feature_permissions else [],
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat()
            }
        )
    except ValueError as e:
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.FAILED.value
        )
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"创建用户失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/{user_id}", summary="更新用户")
async def update_user_info(
    user_id: str,
    request: UserUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    auth_service: AuthService = Depends(get_auth_service),
    current_admin: UserModel = Depends(get_current_admin)
):
    """
    更新用户信息（仅管理员）
    
    Args:
        user_id: 用户ID
        request: 更新用户请求
        session: 数据库会话
        auth_service: 认证服务
        current_admin: 当前管理员用户
        
    Returns:
        更新结果
    """
    try:
        # 构建更新数据
        update_data = {}
        if request.email is not None:
            update_data["email"] = request.email
        if request.role is not None:
            update_data["role"] = request.role
        if request.is_active is not None:
            update_data["is_active"] = request.is_active
        if request.password:
            # 加密新密码
            update_data["password_hash"] = auth_service.get_password_hash(request.password)
        
        user = await update_user(session, user_id, update_data)
        if not user:
            return ApiResponse.failed_response(
                msg="用户不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="用户更新成功",
            data={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "feature_permissions": user.feature_permissions if user.feature_permissions else [],
                "created_at": user.created_at.isoformat(),
                "updated_at": user.updated_at.isoformat()
            }
        )
    except Exception as e:
        logger.error(f"更新用户失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"更新用户失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/{user_id}", summary="删除用户")
async def delete_user_account(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_admin: UserModel = Depends(get_current_admin)
):
    """
    删除用户（仅管理员）
    
    Args:
        user_id: 用户ID
        session: 数据库会话
        current_admin: 当前管理员用户
        
    Returns:
        删除结果
    """
    try:
        # 不允许删除自己
        if user_id == current_admin.id:
            return ApiResponse.failed_response(
                msg="不能删除自己的账号",
                code=ResponseCode.FAILED.value
            )
        
        success = await delete_user(session, user_id)
        if not success:
            return ApiResponse.failed_response(
                msg="用户不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(msg="用户删除成功")
    except Exception as e:
        logger.error(f"删除用户失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"删除用户失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/{user_id}/permissions", summary="更新用户功能权限")
async def update_user_permissions(
    user_id: str,
    request: FeaturePermissionsUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_admin: UserModel = Depends(get_current_admin)
):
    """
    更新用户功能权限（仅管理员）
    
    Args:
        user_id: 用户ID
        request: 权限更新请求
        session: 数据库会话
        current_admin: 当前管理员用户
        
    Returns:
        更新结果
    """
    try:
        user = await get_user_by_id(session, user_id)
        if not user:
            return ApiResponse.failed_response(
                msg="用户不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        # 更新权限
        update_data = {"feature_permissions": request.feature_permissions}
        user = await update_user(session, user_id, update_data)
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="权限更新成功",
            data={
                "id": user.id,
                "username": user.username,
                "feature_permissions": user.feature_permissions if user.feature_permissions else []
            }
        )
    except Exception as e:
        logger.error(f"更新用户权限失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"更新用户权限失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
