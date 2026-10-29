#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
收益分析API路由
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.services.analytics_service import AnalyticsService
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.auth import get_current_user
from app.public.dependencies.database import get_db_session
from models.inner_models.user_model import UserModel

router = APIRouter(prefix="/analytics", tags=["收益分析"])


def get_analytics_service() -> AnalyticsService:
    """获取收益分析服务实例"""
    return AnalyticsService()


@router.get("/profit-summary", summary="获取收益汇总")
async def get_profit_summary(
    from_date: Optional[str] = Query(None, alias="from", description="开始日期 YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, alias="to", description="结束日期 YYYY-MM-DD"),
    exchange: Optional[str] = Query(None, description="交易所筛选，如 okx"),
    symbol: Optional[str] = Query(None, description="交易对筛选，如 BTC-USDT-SWAP"),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取收益汇总数据
    
    - 返回总收益、总手续费、净收益、收益率
    - 支持按时间范围、交易所、交易对筛选
    """
    try:
        result = await service.get_profit_summary(
            session=session,
            user_id=current_user.id,
            from_date=from_date,
            to_date=to_date,
            exchange=exchange,
            symbol=symbol
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result
        )
    except Exception as e:
        logger.error(f"获取收益汇总失败: {e}")
        return ApiResponse.failed_response(
            msg="获取收益汇总失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/profit-trend", summary="获取收益趋势")
async def get_profit_trend(
    from_date: Optional[str] = Query(None, alias="from", description="开始日期 YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, alias="to", description="结束日期 YYYY-MM-DD"),
    period: str = Query("day", description="汇总周期：day/week"),
    exchange: Optional[str] = Query(None, description="交易所筛选"),
    symbol: Optional[str] = Query(None, description="交易对筛选"),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取收益趋势数据
    
    - 返回按日/周汇总的收益趋势
    - 包含每期收益和累计收益
    """
    try:
        if period not in ["day", "week"]:
            return ApiResponse.failed_response(
                msg=f"无效的汇总周期: {period}，可选值: day, week",
                code=ResponseCode.FAILED.value
            )
        
        result = await service.get_profit_trend(
            session=session,
            user_id=current_user.id,
            from_date=from_date,
            to_date=to_date,
            period=period,
            exchange=exchange,
            symbol=symbol
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result
        )
    except Exception as e:
        logger.error(f"获取收益趋势失败: {e}")
        return ApiResponse.failed_response(
            msg="获取收益趋势失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/profit-by-exchange", summary="按交易所获取收益")
async def get_profit_by_exchange(
    from_date: Optional[str] = Query(None, alias="from", description="开始日期 YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, alias="to", description="结束日期 YYYY-MM-DD"),
    symbol: Optional[str] = Query(None, description="交易对筛选"),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    按交易所获取收益分布
    
    - 返回各交易所的收益汇总
    - 包含总收益、手续费、净收益、成交笔数
    """
    try:
        result = await service.get_profit_by_exchange(
            session=session,
            user_id=current_user.id,
            from_date=from_date,
            to_date=to_date,
            symbol=symbol
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result
        )
    except Exception as e:
        logger.error(f"按交易所获取收益失败: {e}")
        return ApiResponse.failed_response(
            msg="按交易所获取收益失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/profit-by-symbol", summary="按币种获取收益")
async def get_profit_by_symbol(
    from_date: Optional[str] = Query(None, alias="from", description="开始日期 YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, alias="to", description="结束日期 YYYY-MM-DD"),
    exchange: Optional[str] = Query(None, description="交易所筛选"),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    按币种获取收益分布
    
    - 返回各交易对的收益汇总
    - 包含总收益、手续费、净收益、成交笔数
    - 按净收益降序排列，返回前10个
    """
    try:
        result = await service.get_profit_by_symbol(
            session=session,
            user_id=current_user.id,
            from_date=from_date,
            to_date=to_date,
            exchange=exchange
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result
        )
    except Exception as e:
        logger.error(f"按币种获取收益失败: {e}")
        return ApiResponse.failed_response(
            msg="按币种获取收益失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/wallet-balance", summary="获取钱包余额")
async def get_wallet_balance(
    exchange: Optional[str] = Query(None, description="交易所筛选，如 okx"),
    session: AsyncSession = Depends(get_db_session),
    service: AnalyticsService = Depends(get_analytics_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取个人钱包余额
    
    - 返回用户绑定的交易所账户余额
    - 包含各币种余额明细和美元等值
    - 支持按交易所筛选
    """
    try:
        result = await service.get_wallet_balance_detail(
            session=session,
            user_id=current_user.id,
            exchange=exchange
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result
        )
    except Exception as e:
        logger.error(f"获取钱包余额失败: {e}")
        return ApiResponse.failed_response(
            msg="获取钱包余额失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )
