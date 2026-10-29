#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/12
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
用户 CRUD 操作
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.user_model import UserModel, UserRole
from loguru import logger


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[UserModel]:
    """根据ID获取用户"""
    query = select(UserModel).where(UserModel.id == user_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_username(session: AsyncSession, username: str) -> Optional[UserModel]:
    """根据用户名获取用户"""
    query = select(UserModel).where(UserModel.username == username)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[UserModel]:
    """根据邮箱获取用户"""
    query = select(UserModel).where(UserModel.email == email)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_users(
    session: AsyncSession,
    is_active: Optional[bool] = None,
    role: Optional[UserRole] = None,
    skip: int = 0,
    limit: int = 100
) -> List[UserModel]:
    """获取用户列表"""
    conditions = []
    if is_active is not None:
        conditions.append(UserModel.is_active == is_active)
    if role:
        conditions.append(UserModel.role == role)
    
    query = select(UserModel)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(desc(UserModel.created_at)).offset(skip).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_user(
    session: AsyncSession,
    username: str,
    password_hash: str,
    email: Optional[str] = None,
    role: UserRole = UserRole.USER,
    is_active: bool = True
) -> UserModel:
    """创建用户"""
    user = UserModel(
        id=str(uuid.uuid4()),
        username=username,
        email=email,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession,
    user_id: str,
    data: Dict[str, Any]
) -> Optional[UserModel]:
    """更新用户"""
    user = await get_user_by_id(session, user_id)
    if not user:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    
    user.updated_at = datetime.now()
    await session.flush()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: str) -> bool:
    """删除用户"""
    user = await get_user_by_id(session, user_id)
    if not user:
        return False
    
    await session.delete(user)
    await session.flush()
    return True


async def verify_user_password(user: UserModel, password: str, password_hasher) -> bool:
    """验证用户密码"""
    return password_hasher.verify(password, user.password_hash)
