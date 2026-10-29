#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
LLM 监控数据清理和聚合任务
功能：
1. 清理超过 90 天的详细日志数据
2. 每日聚合统计数据
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select, delete, and_, text
from sqlalchemy.dialects.mysql import insert as mysql_insert

logger = logging.getLogger(__name__)

# 数据保留天数
DATA_RETENTION_DAYS = 90


async def aggregate_daily_stats(
    target_date: Optional[date] = None,
    db_session=None
) -> Dict:
    """
    聚合指定日期的 LLM 使用统计
    
    Args:
        target_date: 目标日期，默认为昨天
        db_session: 数据库会话（如果为 None，将自动创建）
        
    Returns:
        聚合结果统计
    """
    from models.inner_models.llm_monitor_model import LLMUsageLog, LLMDailyStats
    
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    
    logger.info(f"开始聚合 {target_date} 的 LLM 使用统计")
    
    # 计算日期范围
    start_datetime = datetime.combine(target_date, datetime.min.time())
    end_datetime = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
    
    result = {
        "target_date": target_date.isoformat(),
        "aggregated_records": 0,
        "models": [],
        "errors": []
    }
    
    # 获取数据库会话
    session_context = None
    if db_session is None:
        try:
            from configs.config import app_config
            from core.infrastructure.database.async_database import AsyncDatabase
            async_db = AsyncDatabase(app_config)
            session_context = async_db.get_session()
            db_session = await session_context.__aenter__()
        except Exception as e:
            logger.error(f"获取数据库会话失败: {e}")
            result["errors"].append(f"数据库连接失败: {e}")
            return result
    
    try:
        # 按模型和 Agent 分组聚合
        query = select(
            LLMUsageLog.model_name,
            LLMUsageLog.agent_name,
            func.count(LLMUsageLog.id).label('total_requests'),
            func.sum(
                func.IF(LLMUsageLog.status == 'success', 1, 0)
            ).label('success_requests'),
            func.sum(
                func.IF(LLMUsageLog.status != 'success', 1, 0)
            ).label('failed_requests'),
            func.sum(LLMUsageLog.prompt_tokens).label('total_prompt_tokens'),
            func.sum(LLMUsageLog.completion_tokens).label('total_completion_tokens'),
            func.sum(LLMUsageLog.total_tokens).label('total_tokens'),
            func.sum(LLMUsageLog.cost_usd).label('total_cost_usd'),
            func.sum(LLMUsageLog.cost_cny).label('total_cost_cny'),
            func.avg(LLMUsageLog.response_time_ms).label('avg_response_time_ms'),
        ).where(
            and_(
                LLMUsageLog.created_at >= start_datetime,
                LLMUsageLog.created_at < end_datetime
            )
        ).group_by(
            LLMUsageLog.model_name,
            LLMUsageLog.agent_name
        )
        
        rows = await db_session.execute(query)
        aggregated_data = rows.fetchall()
        
        # 计算响应时间百分位数（P50, P99）
        # 使用子查询获取响应时间列表
        for row in aggregated_data:
            model_name = row.model_name
            agent_name = row.agent_name or ""
            
            # 获取响应时间列表用于计算百分位数
            time_query = select(LLMUsageLog.response_time_ms).where(
                and_(
                    LLMUsageLog.created_at >= start_datetime,
                    LLMUsageLog.created_at < end_datetime,
                    LLMUsageLog.model_name == model_name,
                    LLMUsageLog.agent_name == agent_name if agent_name else LLMUsageLog.agent_name.is_(None)
                )
            ).order_by(LLMUsageLog.response_time_ms)
            
            time_rows = await db_session.execute(time_query)
            response_times = [r[0] for r in time_rows.fetchall()]
            
            # 计算百分位数
            p50, p99 = _calculate_percentiles(response_times)
            
            # 插入或更新聚合数据
            stats_data = {
                "stat_date": target_date,
                "model_name": model_name,
                "agent_name": agent_name,
                "total_requests": row.total_requests or 0,
                "success_requests": row.success_requests or 0,
                "failed_requests": row.failed_requests or 0,
                "total_prompt_tokens": row.total_prompt_tokens or 0,
                "total_completion_tokens": row.total_completion_tokens or 0,
                "total_tokens": row.total_tokens or 0,
                "total_cost_usd": row.total_cost_usd or Decimal("0"),
                "total_cost_cny": row.total_cost_cny or Decimal("0"),
                "avg_response_time_ms": int(row.avg_response_time_ms or 0),
                "p50_response_time_ms": p50,
                "p99_response_time_ms": p99,
            }
            
            # 使用 INSERT ... ON DUPLICATE KEY UPDATE
            stmt = mysql_insert(LLMDailyStats).values(**stats_data)
            update_dict = {k: v for k, v in stats_data.items() if k not in ('stat_date', 'model_name', 'agent_name')}
            update_dict['updated_at'] = datetime.now()
            stmt = stmt.on_duplicate_key_update(**update_dict)
            
            await db_session.execute(stmt)
            
            result["aggregated_records"] += 1
            result["models"].append(f"{model_name}:{agent_name}")
        
        await db_session.commit()
        logger.info(f"成功聚合 {result['aggregated_records']} 条记录")
        
    except Exception as e:
        logger.error(f"聚合统计数据失败: {e}")
        result["errors"].append(str(e))
        if session_context:
            await db_session.rollback()
    finally:
        if session_context:
            await session_context.__aexit__(None, None, None)
    
    return result


def _calculate_percentiles(values: List[int]) -> Tuple[int, int]:
    """
    计算 P50 和 P99 百分位数
    
    Args:
        values: 已排序的数值列表
        
    Returns:
        (p50, p99) 元组
    """
    if not values:
        return 0, 0
    
    n = len(values)
    
    # P50
    p50_idx = int(n * 0.5)
    p50 = values[min(p50_idx, n - 1)]
    
    # P99
    p99_idx = int(n * 0.99)
    p99 = values[min(p99_idx, n - 1)]
    
    return p50, p99


async def cleanup_old_logs(
    retention_days: int = DATA_RETENTION_DAYS,
    db_session=None
) -> Dict:
    """
    清理超过保留期限的详细日志数据
    
    Args:
        retention_days: 数据保留天数
        db_session: 数据库会话
        
    Returns:
        清理结果统计
    """
    from models.inner_models.llm_monitor_model import LLMUsageLog
    
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    
    logger.info(f"开始清理 {cutoff_date.date()} 之前的 LLM 使用日志")
    
    result = {
        "cutoff_date": cutoff_date.isoformat(),
        "deleted_count": 0,
        "errors": []
    }
    
    # 获取数据库会话
    session_context = None
    if db_session is None:
        try:
            from configs.config import app_config
            from core.infrastructure.database.async_database import AsyncDatabase
            async_db = AsyncDatabase(app_config)
            session_context = async_db.get_session()
            db_session = await session_context.__aenter__()
        except Exception as e:
            logger.error(f"获取数据库会话失败: {e}")
            result["errors"].append(f"数据库连接失败: {e}")
            return result
    
    try:
        # 分批删除，避免长时间锁表
        batch_size = 10000
        total_deleted = 0
        
        while True:
            # 先查询要删除的 ID
            id_query = select(LLMUsageLog.id).where(
                LLMUsageLog.created_at < cutoff_date
            ).limit(batch_size)
            
            rows = await db_session.execute(id_query)
            ids_to_delete = [row[0] for row in rows.fetchall()]
            
            if not ids_to_delete:
                break
            
            # 删除
            delete_stmt = delete(LLMUsageLog).where(
                LLMUsageLog.id.in_(ids_to_delete)
            )
            result_proxy = await db_session.execute(delete_stmt)
            deleted_count = result_proxy.rowcount
            
            await db_session.commit()
            
            total_deleted += deleted_count
            logger.debug(f"已删除 {deleted_count} 条记录，累计: {total_deleted}")
            
            if deleted_count < batch_size:
                break
        
        result["deleted_count"] = total_deleted
        logger.info(f"成功清理 {total_deleted} 条过期日志")
        
    except Exception as e:
        logger.error(f"清理日志数据失败: {e}")
        result["errors"].append(str(e))
        if session_context:
            await db_session.rollback()
    finally:
        if session_context:
            await session_context.__aexit__(None, None, None)
    
    return result


async def run_daily_maintenance():
    """
    运行每日维护任务
    包含：数据聚合 + 旧数据清理
    """
    logger.info("开始执行 LLM 监控数据每日维护任务")
    
    results = {
        "aggregation": None,
        "cleanup": None,
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    try:
        # 1. 聚合昨天的数据
        results["aggregation"] = await aggregate_daily_stats()
        
        # 2. 清理过期数据
        results["cleanup"] = await cleanup_old_logs()
        
    except Exception as e:
        logger.error(f"每日维护任务执行失败: {e}")
        results["error"] = str(e)
    
    results["end_time"] = datetime.now().isoformat()
    logger.info(f"LLM 监控数据每日维护任务完成: {results}")
    
    return results


# 注册到调度器的处理函数
def _handle_llm_data_cleanup(scheduler, job_id: str, job_config: dict) -> str:
    """
    LLM 数据清理任务处理函数
    用于通过调度器配置添加任务
    """
    from apscheduler.triggers.cron import CronTrigger
    
    # 解析触发器配置，默认每天凌晨 3 点执行
    trigger_config = job_config.get("trigger", {"type": "cron", "hour": 3, "minute": 0})
    trigger = scheduler.parse_trigger(trigger_config)
    
    # 添加异步任务
    scheduler.scheduler.add_job(
        func=run_daily_maintenance,
        trigger=trigger,
        id=job_id,
        name=f"LLM数据维护-{job_id}",
        replace_existing=True
    )
    
    scheduler.jobs[job_id] = f"LLM数据维护-{job_id}"
    logger.info(f"已添加 LLM 数据维护定时任务: {job_id}")
    
    return job_id


# 自动注册任务类型
def register_llm_cleanup_task():
    """注册 LLM 数据清理任务类型到调度器"""
    try:
        from schedules.scheduler import register_task_type
        register_task_type("llm_data_cleanup", _handle_llm_data_cleanup)
        logger.info("已注册 LLM 数据清理任务类型")
    except ImportError:
        logger.warning("无法导入调度器，跳过任务注册")
