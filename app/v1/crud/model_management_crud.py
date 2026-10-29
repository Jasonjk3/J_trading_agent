#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/11
# @Author : AI Assistant
"""
模型管理 CRUD 操作
封装数据库操作：API配置、模型管理
从 model_compare_crud.py 中抽离，作为独立的公共模块
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.model_compare_model import (
    ModelCompareApiConfig,
    ModelCompareModel,
    ModelTag,
)

logger = logging.getLogger(__name__)


# ============================================================================
# API 配置 CRUD
# ============================================================================

async def get_api_configs(
    session: AsyncSession,
    provider: Optional[str] = None,
    is_active: Optional[bool] = None,
    user_id: Optional[str] = None
) -> List[ModelCompareApiConfig]:
    """
    获取 API 配置列表
    
    Args:
        session: 数据库会话
        provider: 供应商筛选
        is_active: 状态筛选
        user_id: 用户ID筛选
        
    Returns:
        配置列表
    """
    conditions = []
    if provider:
        conditions.append(ModelCompareApiConfig.provider == provider)
    if is_active is not None:
        conditions.append(ModelCompareApiConfig.is_active == is_active)
    if user_id:
        conditions.append(ModelCompareApiConfig.user_id == user_id)
    
    query = select(ModelCompareApiConfig)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(desc(ModelCompareApiConfig.is_default), ModelCompareApiConfig.name)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_api_config_by_id(
    session: AsyncSession,
    config_id: int
) -> Optional[ModelCompareApiConfig]:
    """根据ID获取API配置"""
    query = select(ModelCompareApiConfig).where(ModelCompareApiConfig.id == config_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_default_api_config(
    session: AsyncSession,
    provider: Optional[str] = None,
    user_id: Optional[str] = None
) -> Optional[ModelCompareApiConfig]:
    """获取默认的API配置"""
    conditions = [
        ModelCompareApiConfig.is_default == 1,
        ModelCompareApiConfig.is_active == 1
    ]
    if provider:
        conditions.append(ModelCompareApiConfig.provider == provider)
    if user_id:
        conditions.append(ModelCompareApiConfig.user_id == user_id)
    
    query = select(ModelCompareApiConfig).where(and_(*conditions)).limit(1)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_api_config(
    session: AsyncSession,
    data: Dict[str, Any]
) -> ModelCompareApiConfig:
    """创建API配置"""
    config = ModelCompareApiConfig(**data)
    session.add(config)
    await session.flush()
    await session.refresh(config)
    return config


async def update_api_config(
    session: AsyncSession,
    config_id: int,
    data: Dict[str, Any]
) -> Optional[ModelCompareApiConfig]:
    """更新API配置"""
    config = await get_api_config_by_id(session, config_id)
    if not config:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(config, key, value)
    
    await session.flush()
    await session.refresh(config)
    return config


async def delete_api_config(
    session: AsyncSession,
    config_id: int
) -> bool:
    """删除API配置"""
    stmt = delete(ModelCompareApiConfig).where(ModelCompareApiConfig.id == config_id)
    result = await session.execute(stmt)
    return result.rowcount > 0


async def set_default_api_config(
    session: AsyncSession,
    config_id: int,
    user_id: Optional[str] = None
) -> bool:
    """设置默认API配置"""
    # 先清除其他默认配置
    conditions = [ModelCompareApiConfig.is_default == 1]
    if user_id:
        conditions.append(ModelCompareApiConfig.user_id == user_id)
    
    await session.execute(
        update(ModelCompareApiConfig).where(and_(*conditions)).values(is_default=0)
    )
    
    # 设置新的默认配置
    config = await get_api_config_by_id(session, config_id)
    if config:
        config.is_default = 1
        await session.flush()
        return True
    return False


# ============================================================================
# 模型管理 CRUD
# ============================================================================

async def get_models(
    session: AsyncSession,
    provider: Optional[str] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    user_id: Optional[str] = None,
    api_config_id: Optional[int] = None
) -> List[ModelCompareModel]:
    """
    获取模型列表
    
    Args:
        session: 数据库会话
        provider: 供应商筛选
        status: 状态筛选
        is_active: 是否启用
        user_id: 用户ID
        api_config_id: API配置ID
        
    Returns:
        模型列表
    """
    conditions = []
    if provider:
        conditions.append(ModelCompareModel.provider == provider)
    if status:
        conditions.append(ModelCompareModel.status == status)
    if is_active is not None:
        conditions.append(ModelCompareModel.is_active == is_active)
    if user_id:
        conditions.append(ModelCompareModel.user_id == user_id)
    if api_config_id:
        conditions.append(ModelCompareModel.api_config_id == api_config_id)
    
    query = select(ModelCompareModel)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(ModelCompareModel.sort_order, ModelCompareModel.provider, ModelCompareModel.name)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_model_by_id(
    session: AsyncSession,
    model_id: int
) -> Optional[ModelCompareModel]:
    """根据ID获取模型"""
    query = select(ModelCompareModel).where(ModelCompareModel.id == model_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_model_by_model_id(
    session: AsyncSession,
    model_id: str,
    user_id: Optional[str] = None
) -> Optional[ModelCompareModel]:
    """根据模型ID字符串获取模型"""
    conditions = [ModelCompareModel.model_id == model_id]
    if user_id:
        conditions.append(ModelCompareModel.user_id == user_id)
    
    query = select(ModelCompareModel).where(and_(*conditions))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_model(
    session: AsyncSession,
    data: Dict[str, Any]
) -> ModelCompareModel:
    """创建模型"""
    model = ModelCompareModel(**data)
    session.add(model)
    await session.flush()
    await session.refresh(model)
    return model


async def update_model(
    session: AsyncSession,
    id: int,
    data: Dict[str, Any]
) -> Optional[ModelCompareModel]:
    """更新模型"""
    model = await get_model_by_id(session, id)
    if not model:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(model, key, value)
    
    await session.flush()
    await session.refresh(model)
    return model


async def delete_model(
    session: AsyncSession,
    id: int
) -> bool:
    """删除模型"""
    stmt = delete(ModelCompareModel).where(ModelCompareModel.id == id)
    result = await session.execute(stmt)
    return result.rowcount > 0


async def update_model_test_status(
    session: AsyncSession,
    id: int,
    status: str,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None
) -> Optional[ModelCompareModel]:
    """更新模型测试状态"""
    model = await get_model_by_id(session, id)
    if not model:
        return None
    
    model.status = status
    model.last_test_at = datetime.now()
    model.last_test_latency_ms = latency_ms
    model.last_test_error = error
    
    await session.flush()
    await session.refresh(model)
    return model


async def batch_update_model_status(
    session: AsyncSession,
    model_ids: List[int],
    status: str
) -> int:
    """批量更新模型状态"""
    stmt = update(ModelCompareModel).where(
        ModelCompareModel.id.in_(model_ids)
    ).values(status=status, last_test_at=datetime.now())
    
    result = await session.execute(stmt)
    return result.rowcount


# ============================================================================
# 标签管理 CRUD
# ============================================================================

async def get_tags(
    session: AsyncSession,
    is_active: Optional[bool] = None
) -> List[ModelTag]:
    """
    获取标签列表
    
    Args:
        session: 数据库会话
        is_active: 状态筛选
        
    Returns:
        标签列表
    """
    conditions = []
    if is_active is not None:
        conditions.append(ModelTag.is_active == is_active)
    
    query = select(ModelTag)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(ModelTag.sort_order, ModelTag.name)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_tag_by_id(
    session: AsyncSession,
    tag_id: int
) -> Optional[ModelTag]:
    """根据ID获取标签"""
    query = select(ModelTag).where(ModelTag.id == tag_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_tag_by_name(
    session: AsyncSession,
    name: str
) -> Optional[ModelTag]:
    """根据名称获取标签"""
    query = select(ModelTag).where(ModelTag.name == name)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_tag(
    session: AsyncSession,
    data: Dict[str, Any]
) -> ModelTag:
    """创建标签"""
    tag = ModelTag(**data)
    session.add(tag)
    await session.flush()
    await session.refresh(tag)
    return tag


async def update_tag(
    session: AsyncSession,
    id: int,
    data: Dict[str, Any]
) -> Optional[ModelTag]:
    """更新标签"""
    tag = await get_tag_by_id(session, id)
    if not tag:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(tag, key, value)
    
    await session.flush()
    await session.refresh(tag)
    return tag


async def delete_tag(
    session: AsyncSession,
    id: int
) -> bool:
    """删除标签"""
    stmt = delete(ModelTag).where(ModelTag.id == id)
    result = await session.execute(stmt)
    return result.rowcount > 0
