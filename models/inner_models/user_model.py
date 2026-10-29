#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
用户数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Enum as SQLEnum, JSON
from enum import Enum as PyEnum

from models.inner_models.base import Base


class UserRole(str, PyEnum):
    """用户角色枚举"""
    ADMIN = "admin"
    USER = "user"


class UserModel(Base):
    """用户表模型"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, comment="用户ID")
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    email = Column(String(100), unique=True, nullable=True, index=True, comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    role = Column(SQLEnum(UserRole, values_callable=lambda x: [e.value for e in x]), default=UserRole.USER, nullable=False, comment="角色")
    is_active = Column(Boolean, default=True, nullable=False, index=True, comment="是否激活")
    feature_permissions = Column(JSON, default=list, nullable=True, comment="功能权限列表，存储允许访问的功能ID列表")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def __repr__(self):
        return f"<UserModel(id={self.id}, username={self.username}, role={self.role})>"
