#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
持仓管理API路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from loguru import logger

from app.v1.services.position_service import PositionService
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.auth import get_current_user
from models.inner_models.user_model import UserModel

router = APIRouter(prefix="/positions", tags=["持仓管理"])


def get_position_service() -> PositionService:
    """获取持仓服务实例"""
    return PositionService()


@router.get("", summary="获取持仓列表")
async def get_position_list(
    exchange: Optional[str] = Query(None, description="交易所标识，如 okx"),
    symbol: Optional[str] = Query(None, description="交易对，如 BTC-USDT-SWAP"),
    side: Optional[str] = Query(None, description="持仓方向：long/short"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    session: AsyncSession = Depends(get_db_session),
    service: PositionService = Depends(get_position_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取当前用户的持仓列表
    
    - 自动从用户绑定的已验证且启用的交易所账户获取持仓
    - 支持按交易所、交易对、持仓方向筛选
    - 返回汇总信息（总持仓价值、总未实现盈亏）
    """
    try:
        if side and side not in ["long", "short"]:
            return ApiResponse.failed_response(
                msg=f"无效的持仓方向: {side}，可选值: long, short",
                code=ResponseCode.FAILED.value
            )
        
        positions, total, summary = await service.get_positions(
            session=session,
            user_id=current_user.id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            page=page,
            page_size=pageSize
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "list": positions,
                "total": total,
                "summary": summary
            }
        )
    except Exception as e:
        logger.error(f"获取持仓列表失败: {e}")
        return ApiResponse.failed_response(
            msg="获取持仓列表失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/history", summary="获取历史持仓列表")
async def get_position_history(
    exchange: Optional[str] = Query(None, description="交易所标识，如 okx"),
    symbol: Optional[str] = Query(None, description="交易对，如 BTC-USDT-SWAP"),
    side: Optional[str] = Query(None, description="持仓方向：long/short"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    session: AsyncSession = Depends(get_db_session),
    service: PositionService = Depends(get_position_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取当前用户的历史持仓列表（已平仓）
    
    - 自动从用户绑定的已验证且启用的交易所账户获取历史持仓
    - 支持按交易所、交易对、持仓方向筛选
    - 返回汇总信息（总已实现盈亏）
    """
    try:
        if side and side not in ["long", "short"]:
            return ApiResponse.failed_response(
                msg=f"无效的持仓方向: {side}，可选值: long, short",
                code=ResponseCode.FAILED.value
            )
        
        history, total, summary = await service.get_positions_history(
            session=session,
            user_id=current_user.id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            page=page,
            page_size=pageSize
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "list": history,
                "total": total,
                "summary": summary
            }
        )
    except Exception as e:
        logger.error(f"获取历史持仓列表失败: {e}")
        return ApiResponse.failed_response(
            msg="获取历史持仓列表失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )
