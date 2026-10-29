#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/07
# @Author : AI Assistant
"""
模型对比 CRUD 操作
封装数据库操作：API配置、模型管理、对比历史记录
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.inner_models.model_compare_model import (
    ModelCompareApiConfig,
    ModelCompareModel,
    ModelCompareHistory,
    ModelCompareResult
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
# 对比历史记录 CRUD
# ============================================================================

async def get_compare_histories(
    session: AsyncSession,
    user_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[ModelCompareHistory], int]:
    """
    获取对比历史记录列表（分页）
    
    Args:
        session: 数据库会话
        user_id: 用户ID筛选
        start_time: 开始时间
        end_time: 结束时间
        page: 页码
        page_size: 每页数量
        
    Returns:
        (历史记录列表, 总数)
    """
    conditions = []
    if user_id:
        conditions.append(ModelCompareHistory.user_id == user_id)
    if start_time:
        conditions.append(ModelCompareHistory.created_at >= start_time)
    if end_time:
        conditions.append(ModelCompareHistory.created_at <= end_time)
    
    # 查询总数
    count_query = select(func.count(ModelCompareHistory.id))
    if conditions:
        count_query = count_query.where(and_(*conditions))
    result = await session.execute(count_query)
    total = result.scalar() or 0
    
    # 查询数据
    query = select(ModelCompareHistory)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(desc(ModelCompareHistory.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await session.execute(query)
    items = result.scalars().all()
    
    return list(items), total


async def get_compare_history_by_id(
    session: AsyncSession,
    history_id: int,
    include_results: bool = True
) -> Optional[ModelCompareHistory]:
    """
    根据ID获取对比历史记录
    
    注意：results 是动态关系（lazy="dynamic"），不支持 eager loading。
    如果需要结果，请使用 get_compare_results() 单独查询。
    """
    query = select(ModelCompareHistory).where(ModelCompareHistory.id == history_id)
    # 注意：results 是动态关系，不支持 selectinload
    # 如果需要结果，请使用 get_compare_results() 单独查询
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_compare_history_by_task_id(
    session: AsyncSession,
    task_id: str,
    include_results: bool = True
) -> Optional[ModelCompareHistory]:
    """
    根据任务ID获取对比历史记录
    
    注意：results 是动态关系（lazy="dynamic"），不支持 eager loading。
    如果需要结果，请使用 get_compare_results() 单独查询。
    """
    query = select(ModelCompareHistory).where(ModelCompareHistory.task_id == task_id)
    # 注意：results 是动态关系，不支持 selectinload
    # 如果需要结果，请使用 get_compare_results() 单独查询
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_compare_history(
    session: AsyncSession,
    data: Dict[str, Any]
) -> ModelCompareHistory:
    """创建对比历史记录"""
    history = ModelCompareHistory(**data)
    session.add(history)
    await session.flush()
    await session.refresh(history)
    return history


async def update_compare_history(
    session: AsyncSession,
    history_id: int,
    data: Dict[str, Any]
) -> Optional[ModelCompareHistory]:
    """更新对比历史记录"""
    history = await get_compare_history_by_id(session, history_id, include_results=False)
    if not history:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(history, key, value)
    
    await session.flush()
    await session.refresh(history)
    return history


async def delete_compare_history(
    session: AsyncSession,
    history_id: int
) -> bool:
    """删除对比历史记录（级联删除结果）"""
    stmt = delete(ModelCompareHistory).where(ModelCompareHistory.id == history_id)
    result = await session.execute(stmt)
    return result.rowcount > 0


# ============================================================================
# 对比结果 CRUD
# ============================================================================

async def get_compare_results(
    session: AsyncSession,
    history_id: int
) -> List[ModelCompareResult]:
    """获取指定历史记录的所有结果"""
    query = select(ModelCompareResult).where(
        ModelCompareResult.history_id == history_id
    ).order_by(ModelCompareResult.id)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_compare_result(
    session: AsyncSession,
    data: Dict[str, Any]
) -> ModelCompareResult:
    """创建对比结果"""
    result_obj = ModelCompareResult(**data)
    session.add(result_obj)
    await session.flush()
    await session.refresh(result_obj)
    return result_obj


async def batch_create_compare_results(
    session: AsyncSession,
    results: List[Dict[str, Any]]
) -> List[ModelCompareResult]:
    """批量创建对比结果"""
    result_objs = [ModelCompareResult(**data) for data in results]
    session.add_all(result_objs)
    await session.flush()
    for obj in result_objs:
        await session.refresh(obj)
    return result_objs


# ============================================================================
# 统计查询
# ============================================================================

async def get_compare_stats(
    session: AsyncSession,
    user_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    获取对比统计数据
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        start_time: 开始时间
        end_time: 结束时间
        
    Returns:
        统计数据字典
    """
    conditions = []
    if user_id:
        conditions.append(ModelCompareHistory.user_id == user_id)
    if start_time:
        conditions.append(ModelCompareHistory.created_at >= start_time)
    if end_time:
        conditions.append(ModelCompareHistory.created_at <= end_time)
    
    query = select(
        func.count(ModelCompareHistory.id).label('total_compares'),
        func.sum(ModelCompareHistory.total_models).label('total_models_tested'),
        func.sum(ModelCompareHistory.success_count).label('total_success'),
        func.sum(ModelCompareHistory.failed_count).label('total_failed'),
        func.sum(ModelCompareHistory.total_tokens).label('total_tokens'),
        func.sum(ModelCompareHistory.total_cost_usd).label('total_cost_usd'),
        func.sum(ModelCompareHistory.total_cost_cny).label('total_cost_cny'),
        func.avg(ModelCompareHistory.avg_latency_ms).label('avg_latency_ms')
    )
    if conditions:
        query = query.where(and_(*conditions))
    
    result = await session.execute(query)
    row = result.fetchone()
    
    total_models_tested = row.total_models_tested or 0
    total_success = row.total_success or 0
    success_rate = total_success / total_models_tested if total_models_tested > 0 else 0
    
    return {
        "total_compares": row.total_compares or 0,
        "total_models_tested": total_models_tested,
        "total_success": total_success,
        "total_failed": row.total_failed or 0,
        "success_rate": round(success_rate, 4),
        "total_tokens": row.total_tokens or 0,
        "total_cost_usd": float(row.total_cost_usd or 0),
        "total_cost_cny": float(row.total_cost_cny or 0),
        "avg_latency_ms": int(row.avg_latency_ms or 0)
    }


async def get_model_usage_stats(
    session: AsyncSession,
    user_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    获取模型使用统计（按模型分组）
    
    Args:
        session: 数据库会话
        user_id: 用户ID
        start_time: 开始时间
        end_time: 结束时间
        limit: 返回数量
        
    Returns:
        模型使用统计列表
    """
    conditions = []
    if start_time:
        conditions.append(ModelCompareResult.created_at >= start_time)
    if end_time:
        conditions.append(ModelCompareResult.created_at <= end_time)
    
    # 如果有 user_id 筛选，需要 join history 表
    if user_id:
        query = select(
            ModelCompareResult.model_id,
            ModelCompareResult.model_name,
            ModelCompareResult.provider,
            func.count(ModelCompareResult.id).label('usage_count'),
            func.sum(func.IF(ModelCompareResult.status == 'success', 1, 0)).label('success_count'),
            func.sum(ModelCompareResult.total_tokens).label('total_tokens'),
            func.sum(ModelCompareResult.cost_cny).label('total_cost_cny'),
            func.avg(ModelCompareResult.latency_ms).label('avg_latency_ms')
        ).join(
            ModelCompareHistory, ModelCompareResult.history_id == ModelCompareHistory.id
        ).where(
            and_(ModelCompareHistory.user_id == user_id, *conditions)
        ).group_by(
            ModelCompareResult.model_id,
            ModelCompareResult.model_name,
            ModelCompareResult.provider
        ).order_by(desc('usage_count')).limit(limit)
    else:
        query = select(
            ModelCompareResult.model_id,
            ModelCompareResult.model_name,
            ModelCompareResult.provider,
            func.count(ModelCompareResult.id).label('usage_count'),
            func.sum(func.IF(ModelCompareResult.status == 'success', 1, 0)).label('success_count'),
            func.sum(ModelCompareResult.total_tokens).label('total_tokens'),
            func.sum(ModelCompareResult.cost_cny).label('total_cost_cny'),
            func.avg(ModelCompareResult.latency_ms).label('avg_latency_ms')
        )
        if conditions:
            query = query.where(and_(*conditions))
        query = query.group_by(
            ModelCompareResult.model_id,
            ModelCompareResult.model_name,
            ModelCompareResult.provider
        ).order_by(desc('usage_count')).limit(limit)
    
    result = await session.execute(query)
    rows = result.fetchall()
    
    return [{
        "model_id": row.model_id,
        "model_name": row.model_name,
        "provider": row.provider,
        "usage_count": row.usage_count or 0,
        "success_count": row.success_count or 0,
        "success_rate": round((row.success_count or 0) / row.usage_count, 4) if row.usage_count else 0,
        "total_tokens": row.total_tokens or 0,
        "total_cost_cny": float(row.total_cost_cny or 0),
        "avg_latency_ms": int(row.avg_latency_ms or 0)
    } for row in rows]
