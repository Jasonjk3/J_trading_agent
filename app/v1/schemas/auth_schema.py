#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
认证相关 Schema
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr
from models.inner_models.user_model import UserRole


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名", min_length=1, max_length=50)
    password: str = Field(..., description="密码", min_length=6, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "password123"
            }
        }


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    user: dict = Field(..., description="用户信息")


class UserCreateRequest(BaseModel):
    """创建用户请求（管理员）"""
    username: str = Field(..., description="用户名", min_length=1, max_length=50)
    email: Optional[EmailStr] = Field(None, description="邮箱")
    password: str = Field(..., description="密码", min_length=6, max_length=100)
    role: UserRole = Field(default=UserRole.USER, description="角色")
    is_active: bool = Field(default=True, description="是否激活")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "newuser",
                "email": "user@example.com",
                "password": "password123",
                "role": "user",
                "is_active": True
            }
        }


class UserUpdateRequest(BaseModel):
    """更新用户请求"""
    email: Optional[EmailStr] = Field(None, description="邮箱")
    password: Optional[str] = Field(None, description="新密码", min_length=6, max_length=100)
    role: Optional[UserRole] = Field(None, description="角色")
    is_active: Optional[bool] = Field(None, description="是否激活")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "newemail@example.com",
                "role": "admin",
                "is_active": True
            }
        }


class PasswordResetRequest(BaseModel):
    """密码重置请求"""
    username: str = Field(..., description="用户名")
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., description="新密码", min_length=6, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "user",
                "old_password": "oldpass123",
                "new_password": "newpass123"
            }
        }


class UserResponse(BaseModel):
    """用户信息响应"""
    id: str
    username: str
    email: Optional[str]
    role: str
    is_active: bool
    feature_permissions: Optional[list] = Field(default=None, description="功能权限列表")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FeaturePermissionsUpdateRequest(BaseModel):
    """功能权限更新请求"""
    feature_permissions: list = Field(..., description="功能权限列表，存储允许访问的功能ID列表")

    class Config:
        json_schema_extra = {
            "example": {
                "feature_permissions": ["chat", "competitor", "order-extraction"]
            }
        }
