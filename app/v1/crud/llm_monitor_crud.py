#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
LLM 监控 CRUD 操作
封装数据库操作
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.inner_models.llm_monitor_model import (
    LLMUsageLog,
    LLMDailyStats,
    LLMCostConfig
)

logger = logging.getLogger(__name__)


# ============================================================================
# 使用日志 CRUD
# ============================================================================

async def get_usage_logs(
    session: AsyncSession,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    model_name: Optional[str] = None,
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[LLMUsageLog], int]:
    """
    获取使用日志列表（分页）
    
    Args:
        session: 数据库会话
        start_time: 开始时间
        end_time: 结束时间
        model_name: 模型名称
        agent_name: Agent名称
        status: 状态
        user_id: 用户ID
        page: 页码
        page_size: 每页条数
        
    Returns:
        (日志列表, 总数)
    """
    # 构建查询条件
    conditions = []
    if start_time:
        conditions.append(LLMUsageLog.created_at >= start_time)
    if end_time:
        conditions.append(LLMUsageLog.created_at <= end_time)
    if model_name:
        conditions.append(LLMUsageLog.model_name == model_name)
    if agent_name:
        conditions.append(LLMUsageLog.agent_name == agent_name)
    if status:
        conditions.append(LLMUsageLog.status == status)
    if user_id:
        conditions.append(LLMUsageLog.user_id == user_id)
    
    # 查询总数
    count_query = select(func.count(LLMUsageLog.id))
    if conditions:
        count_query = count_query.where(and_(*conditions))
    result = await session.execute(count_query)
    total = result.scalar() or 0
    
    # 查询数据
    query = select(LLMUsageLog)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(desc(LLMUsageLog.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await session.execute(query)
    items = result.scalars().all()
    
    return list(items), total


async def get_realtime_usage_stats(
    session: AsyncSession,
    start_time: datetime,
    end_time: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    获取实时使用统计
    
    Args:
        session: 数据库会话
        start_time: 开始时间
        end_time: 结束时间（默认当前）
        
    Returns:
        统计数据字典
    """
    end_time = end_time or datetime.now()
    
    query = select(
        func.count(LLMUsageLog.id).label('total_requests'),
        func.sum(LLMUsageLog.total_tokens).label('total_tokens'),
        func.sum(LLMUsageLog.cost_cny).label('total_cost_cny'),
        func.sum(func.IF(LLMUsageLog.status == 'success', 1, 0)).label('success_count'),
        func.avg(LLMUsageLog.response_time_ms).label('avg_response_time_ms')
    ).where(
        and_(
            LLMUsageLog.created_at >= start_time,
            LLMUsageLog.created_at <= end_time
        )
    )
    
    result = await session.execute(query)
    row = result.fetchone()
    
    total_requests = row.total_requests or 0
    success_count = row.success_count or 0
    success_rate = success_count / total_requests if total_requests > 0 else 1.0
    
    return {
        "total_requests": total_requests,
        "total_tokens": row.total_tokens or 0,
        "total_cost_cny": float(row.total_cost_cny or 0),
        "success_rate": round(success_rate, 4),
        "avg_response_time_ms": int(row.avg_response_time_ms or 0)
    }


async def get_active_models(
    session: AsyncSession,
    start_time: datetime
) -> List[str]:
    """获取活跃模型列表"""
    query = select(LLMUsageLog.model_name).where(
        LLMUsageLog.created_at >= start_time
    ).distinct()
    
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def get_top_agents(
    session: AsyncSession,
    start_time: datetime,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """获取 Top Agent 列表"""
    query = select(
        LLMUsageLog.agent_name,
        func.count(LLMUsageLog.id).label('requests')
    ).where(
        and_(
            LLMUsageLog.created_at >= start_time,
            LLMUsageLog.agent_name.isnot(None)
        )
    ).group_by(LLMUsageLog.agent_name).order_by(
        desc('requests')
    ).limit(limit)
    
    result = await session.execute(query)
    return [{"name": row[0], "requests": row[1]} for row in result.fetchall()]


# ============================================================================
# 每日统计 CRUD
# ============================================================================

async def get_daily_stats(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    model_name: Optional[str] = None,
    agent_name: Optional[str] = None,
    group_by: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    获取每日统计数据
    
    策略：直接从 llm_usage_log 表实时聚合数据（不再依赖预聚合表）
    
    Args:
        session: 数据库会话
        start_date: 开始日期
        end_date: 结束日期
        model_name: 模型名称筛选
        agent_name: Agent名称筛选
        group_by: 分组方式 (model/agent/none)
        
    Returns:
        统计数据列表
    """
    from datetime import datetime
    from models.inner_models.llm_monitor_model import LLMUsageLog
    
    # 计算日期时间范围
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    
    log_conditions = [
        LLMUsageLog.created_at >= start_datetime,
        LLMUsageLog.created_at < end_datetime
    ]
    
    if model_name:
        log_conditions.append(LLMUsageLog.model_name == model_name)
    if agent_name:
        log_conditions.append(LLMUsageLog.agent_name == agent_name)
    
    # 根据分组方式构建实时聚合查询
    if group_by == "model":
        log_query = select(
            func.date(LLMUsageLog.created_at).label('stat_date'),
            LLMUsageLog.model_name,
            func.count(LLMUsageLog.id).label('total_requests'),
            func.sum(func.IF(LLMUsageLog.status == 'success', 1, 0)).label('success_requests'),
            func.sum(func.IF(LLMUsageLog.status != 'success', 1, 0)).label('failed_requests'),
            func.sum(LLMUsageLog.prompt_tokens).label('total_prompt_tokens'),
            func.sum(LLMUsageLog.completion_tokens).label('total_completion_tokens'),
            func.sum(LLMUsageLog.total_tokens).label('total_tokens'),
            func.sum(LLMUsageLog.cost_usd).label('total_cost_usd'),
            func.sum(LLMUsageLog.cost_cny).label('total_cost_cny'),
            func.avg(LLMUsageLog.response_time_ms).label('avg_response_time_ms'),
        ).where(and_(*log_conditions)).group_by(
            func.date(LLMUsageLog.created_at), LLMUsageLog.model_name
        ).order_by(func.date(LLMUsageLog.created_at))
    elif group_by == "agent":
        log_query = select(
            func.date(LLMUsageLog.created_at).label('stat_date'),
            LLMUsageLog.agent_name,
            func.count(LLMUsageLog.id).label('total_requests'),
            func.sum(func.IF(LLMUsageLog.status == 'success', 1, 0)).label('success_requests'),
            func.sum(func.IF(LLMUsageLog.status != 'success', 1, 0)).label('failed_requests'),
            func.sum(LLMUsageLog.prompt_tokens).label('total_prompt_tokens'),
            func.sum(LLMUsageLog.completion_tokens).label('total_completion_tokens'),
            func.sum(LLMUsageLog.total_tokens).label('total_tokens'),
            func.sum(LLMUsageLog.cost_usd).label('total_cost_usd'),
            func.sum(LLMUsageLog.cost_cny).label('total_cost_cny'),
            func.avg(LLMUsageLog.response_time_ms).label('avg_response_time_ms'),
        ).where(and_(*log_conditions)).group_by(
            func.date(LLMUsageLog.created_at), LLMUsageLog.agent_name
        ).order_by(func.date(LLMUsageLog.created_at))
    else:
        # 默认按日期汇总
        log_query = select(
            func.date(LLMUsageLog.created_at).label('stat_date'),
            func.count(LLMUsageLog.id).label('total_requests'),
            func.sum(func.IF(LLMUsageLog.status == 'success', 1, 0)).label('success_requests'),
            func.sum(func.IF(LLMUsageLog.status != 'success', 1, 0)).label('failed_requests'),
            func.sum(LLMUsageLog.prompt_tokens).label('total_prompt_tokens'),
            func.sum(LLMUsageLog.completion_tokens).label('total_completion_tokens'),
            func.sum(LLMUsageLog.total_tokens).label('total_tokens'),
            func.sum(LLMUsageLog.cost_usd).label('total_cost_usd'),
            func.sum(LLMUsageLog.cost_cny).label('total_cost_cny'),
            func.avg(LLMUsageLog.response_time_ms).label('avg_response_time_ms'),
        ).where(and_(*log_conditions)).group_by(
            func.date(LLMUsageLog.created_at)
        ).order_by(func.date(LLMUsageLog.created_at))
    
    log_result = await session.execute(log_query)
    log_rows = log_result.fetchall()
    
    items = []
    for row in log_rows:
        item = {
            "date": row.stat_date,
            "total_requests": row.total_requests or 0,
            "success_requests": row.success_requests or 0,
            "failed_requests": row.failed_requests or 0,
            "prompt_tokens": row.total_prompt_tokens or 0,
            "completion_tokens": row.total_completion_tokens or 0,
            "total_tokens": row.total_tokens or 0,
            "cost_usd": float(row.total_cost_usd or 0),
            "cost_cny": float(row.total_cost_cny or 0),
            "avg_response_time_ms": int(row.avg_response_time_ms or 0),
        }
        if hasattr(row, 'model_name') and row.model_name:
            item["model_name"] = row.model_name
        if hasattr(row, 'agent_name') and row.agent_name:
            item["agent_name"] = row.agent_name
        items.append(item)
    
    return items


async def get_stats_by_model(
    session: AsyncSession,
    start_date: date,
    end_date: date
) -> List[Dict[str, Any]]:
    """
    按模型获取统计数据
    
    策略：直接从 llm_usage_log 表实时聚合数据
    """
    from datetime import datetime
    from models.inner_models.llm_monitor_model import LLMUsageLog
    
    # 计算日期时间范围
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    
    log_query = select(
        LLMUsageLog.model_name,
        func.count(LLMUsageLog.id).label('total_requests'),
        func.sum(func.IF(LLMUsageLog.status == 'success', 1, 0)).label('success_requests'),
        func.sum(LLMUsageLog.total_tokens).label('total_tokens'),
        func.sum(LLMUsageLog.cost_cny).label('total_cost_cny'),
        func.avg(LLMUsageLog.response_time_ms).label('avg_response_time_ms'),
    ).where(
        and_(
            LLMUsageLog.created_at >= start_datetime,
            LLMUsageLog.created_at < end_datetime
        )
    ).group_by(LLMUsageLog.model_name)
    
    log_result = await session.execute(log_query)
    log_rows = log_result.fetchall()
    
    items = []
    for row in log_rows:
        total_requests = row.total_requests or 0
        success_requests = row.success_requests or 0
        success_rate = success_requests / total_requests if total_requests > 0 else 1.0
        
        items.append({
            "model_name": row.model_name,
            "total_requests": total_requests,
            "success_requests": success_requests,
            "total_tokens": row.total_tokens or 0,
            "cost_cny": float(row.total_cost_cny or 0),
            "avg_response_time_ms": int(row.avg_response_time_ms or 0),
            "success_rate": round(success_rate, 4)
        })
    
    # 按请求数降序排序
    items.sort(key=lambda x: x["total_requests"], reverse=True)
    
    return items


async def get_stats_by_agent(
    session: AsyncSession,
    start_date: date,
    end_date: date
) -> List[Dict[str, Any]]:
    """
    按Agent获取统计数据
    
    策略：直接从 llm_usage_log 表实时聚合数据
    """
    from datetime import datetime
    from models.inner_models.llm_monitor_model import LLMUsageLog
    
    # 计算日期时间范围
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    
    agent_stats = {}  # agent_name -> stats dict
    agent_models = {}  # agent_name -> {model_name: count}
    
    log_query = select(
        LLMUsageLog.agent_name,
        LLMUsageLog.model_name,
        func.count(LLMUsageLog.id).label('total_requests'),
        func.sum(func.IF(LLMUsageLog.status == 'success', 1, 0)).label('success_requests'),
        func.sum(LLMUsageLog.total_tokens).label('total_tokens'),
        func.sum(LLMUsageLog.cost_cny).label('total_cost_cny'),
        func.avg(LLMUsageLog.response_time_ms).label('avg_response_time_ms'),
    ).where(
        and_(
            LLMUsageLog.created_at >= start_datetime,
            LLMUsageLog.created_at < end_datetime,
            LLMUsageLog.agent_name.isnot(None),
            LLMUsageLog.agent_name != ""
        )
    ).group_by(LLMUsageLog.agent_name, LLMUsageLog.model_name)
    
    log_result = await session.execute(log_query)
    log_rows = log_result.fetchall()
    
    for row in log_rows:
        agent_name = row.agent_name or "unknown"
        if agent_name not in agent_stats:
            agent_stats[agent_name] = {
                "agent_name": agent_name,
                "total_requests": 0,
                "success_requests": 0,
                "total_tokens": 0,
                "cost_cny": 0.0,
                "avg_response_time_ms": 0,
            }
            agent_models[agent_name] = {}
        
        # 合并数据
        agent_stats[agent_name]["total_requests"] += row.total_requests or 0
        agent_stats[agent_name]["success_requests"] += row.success_requests or 0
        agent_stats[agent_name]["total_tokens"] += row.total_tokens or 0
        agent_stats[agent_name]["cost_cny"] += float(row.total_cost_cny or 0)
        
        # 记录模型使用情况
        model_name = row.model_name
        if model_name not in agent_models[agent_name]:
            agent_models[agent_name][model_name] = 0
        agent_models[agent_name][model_name] += row.total_requests or 0
    
    # 计算成功率、主要模型并排序
    items = []
    for agent_name, stats in agent_stats.items():
        total_requests = stats["total_requests"]
        success_requests = stats["success_requests"]
        success_rate = success_requests / total_requests if total_requests > 0 else 1.0
        
        # 获取主要使用的模型
        primary_model = "unknown"
        if agent_name in agent_models and agent_models[agent_name]:
            primary_model = max(agent_models[agent_name].items(), key=lambda x: x[1])[0]
        
        items.append({
            **stats,
            "success_rate": round(success_rate, 4),
            "primary_model": primary_model
        })
    
    # 按请求数降序排序
    items.sort(key=lambda x: x["total_requests"], reverse=True)
    
    return items


# ============================================================================
# 费用配置 CRUD
# ============================================================================

async def get_cost_configs(
    session: AsyncSession,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    is_active: Optional[bool] = None
) -> List[LLMCostConfig]:
    """获取费用配置列表，支持按模型名称、提供商、状态筛选"""
    query = select(LLMCostConfig)
    conditions = []
    if model_name:
        conditions.append(LLMCostConfig.model_name.like(f"%{model_name}%"))
    if provider:
        conditions.append(LLMCostConfig.provider.like(f"%{provider}%"))
    if is_active is not None:
        conditions.append(LLMCostConfig.is_active == is_active)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(LLMCostConfig.model_name)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_cost_config_by_id(
    session: AsyncSession,
    config_id: int
) -> Optional[LLMCostConfig]:
    """根据ID获取费用配置"""
    query = select(LLMCostConfig).where(LLMCostConfig.id == config_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_cost_config(
    session: AsyncSession,
    data: Dict[str, Any]
) -> LLMCostConfig:
    """创建费用配置"""
    config = LLMCostConfig(**data)
    session.add(config)
    await session.flush()
    await session.refresh(config)
    return config


async def update_cost_config(
    session: AsyncSession,
    config_id: int,
    data: Dict[str, Any]
) -> Optional[LLMCostConfig]:
    """更新费用配置"""
    config = await get_cost_config_by_id(session, config_id)
    if not config:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(config, key, value)
    
    await session.flush()
    await session.refresh(config)
    return config


async def delete_cost_config(
    session: AsyncSession,
    config_id: int
) -> bool:
    """删除费用配置"""
    stmt = delete(LLMCostConfig).where(LLMCostConfig.id == config_id)
    result = await session.execute(stmt)
    return result.rowcount > 0


# ============================================================================
# 费用统计 CRUD
# ============================================================================

async def get_cost_summary(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    group_by: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取费用汇总
    
    策略：合并预聚合表和实时聚合的数据
    """
    from datetime import datetime
    from models.inner_models.llm_monitor_model import LLMUsageLog
    
    today = date.today()
    total_cost_usd = 0.0
    total_cost_cny = 0.0
    breakdown_dict = {}  # name -> {cost_usd, cost_cny}
    
    # 1. 查询历史数据（从预聚合表，排除今天）
    if start_date < today:
        history_end_date = min(end_date, today - timedelta(days=1))
        if start_date <= history_end_date:
            conditions = [
                LLMDailyStats.stat_date >= start_date,
                LLMDailyStats.stat_date <= history_end_date
            ]
            
            # 总费用
            total_query = select(
                func.sum(LLMDailyStats.total_cost_usd).label('total_cost_usd'),
                func.sum(LLMDailyStats.total_cost_cny).label('total_cost_cny')
            ).where(and_(*conditions))
            
            result = await session.execute(total_query)
            total_row = result.fetchone()
            
            total_cost_usd += float(total_row.total_cost_usd or 0)
            total_cost_cny += float(total_row.total_cost_cny or 0)
            
            # 分组统计
            if group_by == "model":
                breakdown_query = select(
                    LLMDailyStats.model_name.label('name'),
                    func.sum(LLMDailyStats.total_cost_usd).label('cost_usd'),
                    func.sum(LLMDailyStats.total_cost_cny).label('cost_cny')
                ).where(and_(*conditions)).group_by(
                    LLMDailyStats.model_name
                )
            elif group_by == "agent":
                breakdown_query = select(
                    LLMDailyStats.agent_name.label('name'),
                    func.sum(LLMDailyStats.total_cost_usd).label('cost_usd'),
                    func.sum(LLMDailyStats.total_cost_cny).label('cost_cny')
                ).where(
                    and_(*conditions, LLMDailyStats.agent_name != "")
                ).group_by(
                    LLMDailyStats.agent_name
                )
            else:
                breakdown_query = None
            
            if breakdown_query is not None:
                result = await session.execute(breakdown_query)
                rows = result.fetchall()
                
                for row in rows:
                    name = row.name or "unknown"
                    if name not in breakdown_dict:
                        breakdown_dict[name] = {"cost_usd": 0.0, "cost_cny": 0.0}
                    breakdown_dict[name]["cost_usd"] += float(row.cost_usd or 0)
                    breakdown_dict[name]["cost_cny"] += float(row.cost_cny or 0)
    
    # 2. 实时聚合今天的数据（从原始日志表）
    if end_date >= today:
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.now()
        
        log_conditions = [
            LLMUsageLog.created_at >= today_start,
            LLMUsageLog.created_at <= today_end
        ]
        
        # 总费用
        log_total_query = select(
            func.sum(LLMUsageLog.cost_usd).label('total_cost_usd'),
            func.sum(LLMUsageLog.cost_cny).label('total_cost_cny')
        ).where(and_(*log_conditions))
        
        log_result = await session.execute(log_total_query)
        log_total_row = log_result.fetchone()
        
        total_cost_usd += float(log_total_row.total_cost_usd or 0)
        total_cost_cny += float(log_total_row.total_cost_cny or 0)
        
        # 分组统计
        if group_by == "model":
            log_breakdown_query = select(
                LLMUsageLog.model_name.label('name'),
                func.sum(LLMUsageLog.cost_usd).label('cost_usd'),
                func.sum(LLMUsageLog.cost_cny).label('cost_cny')
            ).where(and_(*log_conditions)).group_by(
                LLMUsageLog.model_name
            )
        elif group_by == "agent":
            log_breakdown_query = select(
                LLMUsageLog.agent_name.label('name'),
                func.sum(LLMUsageLog.cost_usd).label('cost_usd'),
                func.sum(LLMUsageLog.cost_cny).label('cost_cny')
            ).where(
                and_(*log_conditions, LLMUsageLog.agent_name.isnot(None), LLMUsageLog.agent_name != "")
            ).group_by(
                LLMUsageLog.agent_name
            )
        else:
            log_breakdown_query = None
        
        if log_breakdown_query is not None:
            log_result = await session.execute(log_breakdown_query)
            log_rows = log_result.fetchall()
            
            for row in log_rows:
                name = row.name or "unknown"
                if name not in breakdown_dict:
                    breakdown_dict[name] = {"cost_usd": 0.0, "cost_cny": 0.0}
                breakdown_dict[name]["cost_usd"] += float(row.cost_usd or 0)
                breakdown_dict[name]["cost_cny"] += float(row.cost_cny or 0)
    
    # 3. 构建返回结果
    breakdown = []
    for name, costs in breakdown_dict.items():
        cost_cny = costs["cost_cny"]
        percentage = (cost_cny / total_cost_cny * 100) if total_cost_cny > 0 else 0
        breakdown.append({
            "name": name,
            "cost_usd": costs["cost_usd"],
            "cost_cny": cost_cny,
            "percentage": round(percentage, 2)
        })
    
    # 按费用降序排序
    breakdown.sort(key=lambda x: x["cost_cny"], reverse=True)
    
    return {
        "total_cost_usd": total_cost_usd,
        "total_cost_cny": total_cost_cny,
        "breakdown": breakdown
    }


async def get_cost_trend(
    session: AsyncSession,
    start_date: date,
    end_date: date,
    granularity: str = "day"
) -> List[Dict[str, Any]]:
    """
    获取费用趋势
    
    策略：合并预聚合表和实时聚合的数据
    """
    from datetime import datetime
    from models.inner_models.llm_monitor_model import LLMUsageLog
    
    today = date.today()
    trend_dict = {}  # period -> {cost_usd, cost_cny, tokens, requests}
    
    # 1. 查询历史数据（从预聚合表，排除今天）
    if start_date < today:
        history_end_date = min(end_date, today - timedelta(days=1))
        if start_date <= history_end_date:
            if granularity == "day":
                query = select(
                    LLMDailyStats.stat_date,
                    func.sum(LLMDailyStats.total_cost_usd).label('cost_usd'),
                    func.sum(LLMDailyStats.total_cost_cny).label('cost_cny'),
                    func.sum(LLMDailyStats.total_tokens).label('tokens'),
                    func.sum(LLMDailyStats.total_requests).label('requests')
                ).where(
                    and_(
                        LLMDailyStats.stat_date >= start_date,
                        LLMDailyStats.stat_date <= history_end_date
                    )
                ).group_by(LLMDailyStats.stat_date)
                
                result = await session.execute(query)
                rows = result.fetchall()
                
                for row in rows:
                    period = row.stat_date.isoformat()
                    trend_dict[period] = {
                        "period": period,
                        "cost_usd": float(row.cost_usd or 0),
                        "cost_cny": float(row.cost_cny or 0),
                        "tokens": row.tokens or 0,
                        "requests": row.requests or 0
                    }
    
    # 2. 实时聚合今天的数据（从原始日志表）
    if end_date >= today and granularity == "day":
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.now()
        
        log_query = select(
            func.date(LLMUsageLog.created_at).label('stat_date'),
            func.sum(LLMUsageLog.cost_usd).label('cost_usd'),
            func.sum(LLMUsageLog.cost_cny).label('cost_cny'),
            func.sum(LLMUsageLog.total_tokens).label('tokens'),
            func.count(LLMUsageLog.id).label('requests')
        ).where(
            and_(
                LLMUsageLog.created_at >= today_start,
                LLMUsageLog.created_at <= today_end
            )
        ).group_by(func.date(LLMUsageLog.created_at))
        
        log_result = await session.execute(log_query)
        log_rows = log_result.fetchall()
        
        for row in log_rows:
            period = row.stat_date.isoformat()
            if period in trend_dict:
                # 合并数据
                trend_dict[period]["cost_usd"] += float(row.cost_usd or 0)
                trend_dict[period]["cost_cny"] += float(row.cost_cny or 0)
                trend_dict[period]["tokens"] += row.tokens or 0
                trend_dict[period]["requests"] += row.requests or 0
            else:
                # 新增
                trend_dict[period] = {
                    "period": period,
                    "cost_usd": float(row.cost_usd or 0),
                    "cost_cny": float(row.cost_cny or 0),
                    "tokens": row.tokens or 0,
                    "requests": row.requests or 0
                }
    
    # 处理其他粒度（week, month）- 只从预聚合表查询
    if granularity == "week":
        # 按周聚合
        conditions = [
            LLMDailyStats.stat_date >= start_date,
            LLMDailyStats.stat_date <= end_date
        ]
        query = select(
            func.yearweek(LLMDailyStats.stat_date).label('week'),
            func.min(LLMDailyStats.stat_date).label('week_start'),
            func.sum(LLMDailyStats.total_cost_usd).label('cost_usd'),
            func.sum(LLMDailyStats.total_cost_cny).label('cost_cny'),
            func.sum(LLMDailyStats.total_tokens).label('tokens'),
            func.sum(LLMDailyStats.total_requests).label('requests')
        ).where(and_(*conditions)).group_by('week').order_by('week')
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        return [{
            "period": f"Week {row.week}",
            "cost_usd": float(row.cost_usd or 0),
            "cost_cny": float(row.cost_cny or 0),
            "tokens": row.tokens or 0,
            "requests": row.requests or 0
        } for row in rows]
    elif granularity == "month":
        # 按月聚合
        conditions = [
            LLMDailyStats.stat_date >= start_date,
            LLMDailyStats.stat_date <= end_date
        ]
        query = select(
            func.date_format(LLMDailyStats.stat_date, '%Y-%m').label('month'),
            func.sum(LLMDailyStats.total_cost_usd).label('cost_usd'),
            func.sum(LLMDailyStats.total_cost_cny).label('cost_cny'),
            func.sum(LLMDailyStats.total_tokens).label('tokens'),
            func.sum(LLMDailyStats.total_requests).label('requests')
        ).where(and_(*conditions)).group_by('month').order_by('month')
        
        result = await session.execute(query)
        rows = result.fetchall()
        
        return [{
            "period": row.month,
            "cost_usd": float(row.cost_usd or 0),
            "cost_cny": float(row.cost_cny or 0),
            "tokens": row.tokens or 0,
            "requests": row.requests or 0
        } for row in rows]
    
    # 3. 转换为列表并排序（day 粒度）
    items = list(trend_dict.values())
    items.sort(key=lambda x: x["period"])
    
    return items


async def get_tokens_for_period(
    session: AsyncSession,
    start_date: date,
    end_date: date
) -> int:
    """
    获取指定时间段的总Token数
    
    策略：合并预聚合表和实时聚合的数据
    
    Args:
        session: 数据库会话
        start_date: 开始日期
        end_date: 结束日期
        
    Returns:
        总Token数
    """
    from datetime import datetime
    from models.inner_models.llm_monitor_model import LLMUsageLog
    
    today = date.today()
    total_tokens = 0
    
    # 1. 查询历史数据（从预聚合表，排除今天）
    if start_date < today:
        history_end_date = min(end_date, today - timedelta(days=1))
        if start_date <= history_end_date:
            query = select(
                func.sum(LLMDailyStats.total_tokens).label('total_tokens')
            ).where(
                and_(
                    LLMDailyStats.stat_date >= start_date,
                    LLMDailyStats.stat_date <= history_end_date
                )
            )
            
            result = await session.execute(query)
            row = result.fetchone()
            total_tokens += int(row.total_tokens or 0)
    
    # 2. 实时聚合今天的数据（从原始日志表）
    if end_date >= today:
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.now()
        
        log_query = select(
            func.sum(LLMUsageLog.total_tokens).label('total_tokens')
        ).where(
            and_(
                LLMUsageLog.created_at >= today_start,
                LLMUsageLog.created_at <= today_end
            )
        )
        
        log_result = await session.execute(log_query)
        log_row = log_result.fetchone()
        total_tokens += int(log_row.total_tokens or 0)
    
    return total_tokens
