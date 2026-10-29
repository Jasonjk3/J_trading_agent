#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
LLM 监控 API 路由
提供完整的 RESTful 接口
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.v1.schemas.llm_monitor_schema import (
    # 使用量相关
    UsageHistoryRequest,
    UsageHistoryResponse,
    RealtimeUsageResponse,
    # 统计相关
    DailyStatsRequest,
    DailyStatsResponse,
    OverviewStatsResponse,
    ModelStatsResponse,
    AgentStatsResponse,
    # 费用相关
    CostSummaryRequest,
    CostSummaryResponse,
    CostTrendRequest,
    CostTrendResponse,
    # 配置管理
    ModelCostConfigListResponse,
    ModelCostConfigCreateRequest,
    ModelCostConfigUpdateRequest,
    ModelCostConfigItem,
    # 预警相关
    AlertRuleListResponse,
    AlertRuleCreateRequest,
    AlertRuleUpdateRequest,
    AlertRuleItem,
    AlertHistoryRequest,
    AlertHistoryResponse,
)
from app.v1.services.llm_monitor_service import LLMMonitorService
from app.v1.services.budget_alert_service import BudgetAlertService

# 创建路由器
from app.public.dependencies.auth import get_current_admin

router = APIRouter(prefix="/monitor", tags=["LLM监控"], dependencies=[Depends(get_current_admin)])


# ============================================================================
# 使用量 API (/usage)
# ============================================================================

@router.get("/usage/realtime", summary="实时使用情况")
async def get_realtime_usage(
    session: AsyncSession = Depends(get_db_session)
):
    """
    获取实时使用情况
    
    返回今日和当前小时的统计数据，以及活跃模型和 Top Agent 列表
    """
    try:
        service = LLMMonitorService(session)
        result = await service.get_realtime_usage()
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取实时使用情况失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/usage/history", summary="历史调用记录")
async def get_usage_history(
    session: AsyncSession = Depends(get_db_session),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    model_name: Optional[str] = Query(None, description="模型名称"),
    agent_name: Optional[str] = Query(None, description="Agent名称"),
    status: Optional[str] = Query(None, description="状态(success/failed/timeout)"),
    user_id: Optional[str] = Query(None, description="用户ID"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数")
):
    """
    获取历史调用记录（分页）
    
    支持按时间范围、模型、Agent、状态等条件筛选
    """
    try:
        service = LLMMonitorService(session)
        request = UsageHistoryRequest(
            start_time=start_time,
            end_time=end_time,
            model_name=model_name,
            agent_name=agent_name,
            status=status,
            user_id=user_id,
            page=page,
            page_size=page_size
        )
        result = await service.get_usage_history(request)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取历史调用记录失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 统计 API (/stats)
# ============================================================================

@router.get("/stats/overview", summary="总览统计")
async def get_stats_overview(
    session: AsyncSession = Depends(get_db_session)
):
    """
    获取总览统计
    
    返回今日、本周、本月的汇总数据，以及成功率和平均响应时间
    """
    try:
        service = LLMMonitorService(session)
        result = await service.get_overview_stats()
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取总览统计失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/stats/daily", summary="每日统计")
async def get_daily_stats(
    session: AsyncSession = Depends(get_db_session),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    model_name: Optional[str] = Query(None, description="模型名称"),
    agent_name: Optional[str] = Query(None, description="Agent名称"),
    group_by: Optional[str] = Query(None, description="分组方式: model/agent/none")
):
    """
    获取每日统计数据
    
    支持按模型或 Agent 分组，返回指定时间范围内的统计数据
    """
    try:
        service = LLMMonitorService(session)
        request = DailyStatsRequest(
            start_date=start_date,
            end_date=end_date,
            model_name=model_name,
            agent_name=agent_name,
            group_by=group_by
        )
        result = await service.get_daily_stats(request)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取每日统计失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/stats/by-model", summary="按模型统计")
async def get_stats_by_model(
    session: AsyncSession = Depends(get_db_session),
    start_date: Optional[date] = Query(None, description="开始日期（默认本月初）"),
    end_date: Optional[date] = Query(None, description="结束日期（默认今天）")
):
    """
    按模型获取统计数据
    
    返回每个模型的请求数、Token数、费用、响应时间和成功率
    """
    try:
        service = LLMMonitorService(session)
        
        # 默认查询本月
        if not start_date:
            start_date = date.today().replace(day=1)
        if not end_date:
            end_date = date.today()
        
        result = await service.get_stats_by_model(start_date, end_date)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取模型统计失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/stats/by-agent", summary="按Agent统计")
async def get_stats_by_agent(
    session: AsyncSession = Depends(get_db_session),
    start_date: Optional[date] = Query(None, description="开始日期（默认本月初）"),
    end_date: Optional[date] = Query(None, description="结束日期（默认今天）")
):
    """
    按Agent获取统计数据
    
    返回每个Agent的请求数、Token数、费用、响应时间、成功率和主要使用的模型
    """
    try:
        service = LLMMonitorService(session)
        
        # 默认查询本月
        if not start_date:
            start_date = date.today().replace(day=1)
        if not end_date:
            end_date = date.today()
        
        result = await service.get_stats_by_agent(start_date, end_date)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取Agent统计失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 费用 API (/cost)
# ============================================================================

@router.get("/cost/summary", summary="费用汇总")
async def get_cost_summary(
    session: AsyncSession = Depends(get_db_session),
    start_date: Optional[date] = Query(None, description="开始日期（默认本月初）"),
    end_date: Optional[date] = Query(None, description="结束日期（默认今天）"),
    group_by: Optional[str] = Query(None, description="分组方式: model/agent")
):
    """
    获取费用汇总
    
    返回总费用和按模型/Agent的费用分解
    """
    try:
        service = LLMMonitorService(session)
        request = CostSummaryRequest(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
        result = await service.get_cost_summary(request)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取费用汇总失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/cost/trend", summary="费用趋势")
async def get_cost_trend(
    session: AsyncSession = Depends(get_db_session),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    granularity: str = Query("day", description="粒度: day/week/month")
):
    """
    获取费用趋势
    
    按指定粒度返回费用变化趋势
    """
    try:
        service = LLMMonitorService(session)
        request = CostTrendRequest(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity
        )
        result = await service.get_cost_trend(request)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取费用趋势失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 配置管理 API (/config)
# ============================================================================

@router.get("/config/models", summary="获取模型费用配置")
async def get_model_configs(
    session: AsyncSession = Depends(get_db_session),
    model_name: Optional[str] = Query(None, description="模型名称（模糊筛选）"),
    provider: Optional[str] = Query(None, description="提供商（模糊筛选）"),
    is_active: Optional[bool] = Query(None, description="是否生效")
):
    """
    获取模型费用配置，支持按模型名称、提供商、状态筛选
    """
    try:
        service = LLMMonitorService(session)
        result = await service.get_model_configs(
            model_name=model_name,
            provider=provider,
            is_active=is_active
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取模型配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/config/models", summary="新增模型费用配置")
async def create_model_config(
    request: ModelCostConfigCreateRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    新增模型费用配置
    """
    try:
        service = LLMMonitorService(session)
        result = await service.create_model_config(request)
        
        return ApiResponse.success_response(
            msg="创建成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"创建模型配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/config/models/{config_id}", summary="更新模型费用配置")
async def update_model_config(
    config_id: int,
    request: ModelCostConfigUpdateRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    更新模型费用配置
    """
    try:
        service = LLMMonitorService(session)
        result = await service.update_model_config(config_id, request)
        
        if not result:
            return ApiResponse.failed_response(
                msg="配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="更新成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"更新模型配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"更新失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/config/models/{config_id}", summary="删除模型费用配置")
async def delete_model_config(
    config_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """
    删除模型费用配置
    """
    try:
        service = LLMMonitorService(session)
        success = await service.delete_model_config(config_id)
        
        if not success:
            return ApiResponse.failed_response(
                msg="配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="删除成功"
        )
    except Exception as e:
        logger.error(f"删除模型配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 预警 API (/alert)
# ============================================================================

@router.get("/alert/rules", summary="获取预警规则")
async def get_alert_rules(
    session: AsyncSession = Depends(get_db_session),
    is_active: Optional[bool] = Query(None, description="是否只返回启用的规则")
):
    """
    获取预警规则列表
    """
    try:
        service = BudgetAlertService(session)
        result = await service.get_alert_rules(is_active)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取预警规则失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/alert/rules", summary="创建预警规则")
async def create_alert_rule(
    request: AlertRuleCreateRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    创建预警规则
    
    支持的预警类型:
    - daily_cost: 日费用预警
    - monthly_cost: 月费用预警
    - single_request: 单次请求费用预警
    """
    try:
        service = BudgetAlertService(session)
        result = await service.create_alert_rule(request)
        
        return ApiResponse.success_response(
            msg="创建成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"创建预警规则失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/alert/rules/{rule_id}", summary="更新预警规则")
async def update_alert_rule(
    rule_id: int,
    request: AlertRuleUpdateRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    更新预警规则
    """
    try:
        service = BudgetAlertService(session)
        result = await service.update_alert_rule(rule_id, request)
        
        if not result:
            return ApiResponse.failed_response(
                msg="规则不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="更新成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"更新预警规则失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"更新失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/alert/rules/{rule_id}", summary="删除预警规则")
async def delete_alert_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """
    删除预警规则
    """
    try:
        service = BudgetAlertService(session)
        success = await service.delete_alert_rule(rule_id)
        
        if not success:
            return ApiResponse.failed_response(
                msg="规则不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="删除成功"
        )
    except Exception as e:
        logger.error(f"删除预警规则失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/alert/history", summary="预警历史记录")
async def get_alert_history(
    session: AsyncSession = Depends(get_db_session),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    rule_id: Optional[int] = Query(None, description="规则ID"),
    alert_type: Optional[str] = Query(None, description="预警类型"),
    notify_status: Optional[str] = Query(None, description="通知状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数")
):
    """
    获取预警历史记录（分页）
    """
    try:
        service = BudgetAlertService(session)
        request = AlertHistoryRequest(
            start_time=start_time,
            end_time=end_time,
            rule_id=rule_id,
            alert_type=alert_type,
            notify_status=notify_status,
            page=page,
            page_size=page_size
        )
        result = await service.get_alert_history(request)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json', by_alias=True)
        )
    except Exception as e:
        logger.error(f"获取预警历史失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/alert/check", summary="手动触发预警检测")
async def trigger_alert_check(
    session: AsyncSession = Depends(get_db_session),
    rule_id: Optional[int] = Query(None, description="规则ID（不传则检测所有规则）")
):
    """
    手动触发预警检测
    
    可以指定规则ID只检测某一条规则，或不传参数检测所有启用的规则
    """
    try:
        service = BudgetAlertService(session)
        
        if rule_id:
            result = await service.trigger_manual_check(rule_id)
            if result is None:
                return ApiResponse.failed_response(
                    msg="规则不存在",
                    code=ResponseCode.NOT_FOUND.value
                )
        else:
            result = await service.check_alerts()
        
        return ApiResponse.success_response(
            msg="检测完成",
            data=result
        )
    except Exception as e:
        logger.error(f"触发预警检测失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"检测失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
