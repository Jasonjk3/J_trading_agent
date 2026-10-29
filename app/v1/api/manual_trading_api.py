#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
手工实盘交易 API 路由
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.auth import get_current_user
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.v1.schemas.manual_trading_schema import (
    CancelManualOrderRequest,
    PlaceManualOrderRequest,
)
from app.v1.services.manual_trading_service import ManualTradingService
from models.inner_models.user_model import UserModel


router = APIRouter(prefix="/manual-trading", tags=["手工实盘交易"])


def get_manual_trading_service() -> ManualTradingService:
    """获取手工实盘交易服务实例"""
    return ManualTradingService()


@router.get("/instruments", summary="搜索可交易产品")
async def search_instruments(
    accountId: str = Query(..., description="交易所账户ID"),
    instType: str = Query(..., description="产品类型：SPOT/SWAP"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    session: AsyncSession = Depends(get_db_session),
    service: ManualTradingService = Depends(get_manual_trading_service),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        instruments = await service.search_instruments(
            session=session,
            user_id=current_user.id,
            account_id=accountId,
            inst_type=instType.upper(),
            keyword=keyword,
        )
        return ApiResponse.success_response(msg="获取成功", data={"list": instruments})
    except ValueError as e:
        return ApiResponse.failed_response(msg=str(e), code=ResponseCode.FAILED.value)
    except Exception as e:
        logger.error(f"搜索可交易产品失败: {e}")
        return ApiResponse.failed_response(msg="获取可交易产品失败，请稍后重试", code=ResponseCode.SYSTEM_ERROR.value)


@router.get("/snapshot", summary="获取交易快照")
async def get_snapshot(
    accountId: str = Query(..., description="交易所账户ID"),
    instId: str = Query(..., description="产品ID"),
    session: AsyncSession = Depends(get_db_session),
    service: ManualTradingService = Depends(get_manual_trading_service),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        snapshot = await service.get_snapshot(
            session=session,
            user_id=current_user.id,
            account_id=accountId,
            inst_id=instId,
        )
        return ApiResponse.success_response(msg="获取成功", data=snapshot)
    except ValueError as e:
        return ApiResponse.failed_response(msg=str(e), code=ResponseCode.FAILED.value)
    except Exception as e:
        logger.error(f"获取交易快照失败: {e}")
        return ApiResponse.failed_response(msg="获取交易快照失败，请稍后重试", code=ResponseCode.SYSTEM_ERROR.value)


@router.get("/overview", summary="获取账户总览")
async def get_account_overview(
    accountId: str = Query(..., description="交易所账户ID"),
    instType: Optional[str] = Query(None, description="产品类型：SPOT/SWAP"),
    instId: Optional[str] = Query(None, description="产品ID"),
    session: AsyncSession = Depends(get_db_session),
    service: ManualTradingService = Depends(get_manual_trading_service),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        overview = await service.get_account_overview(
            session=session,
            user_id=current_user.id,
            account_id=accountId,
            inst_type=instType.upper() if instType else None,
            inst_id=instId,
        )
        return ApiResponse.success_response(msg="获取成功", data=overview)
    except ValueError as e:
        return ApiResponse.failed_response(msg=str(e), code=ResponseCode.FAILED.value)
    except Exception as e:
        logger.error(f"获取账户总览失败: {e}")
        return ApiResponse.failed_response(msg="获取账户总览失败，请稍后重试", code=ResponseCode.SYSTEM_ERROR.value)


@router.get("/pending-orders", summary="获取未成交委托")
async def get_pending_orders(
    accountId: str = Query(..., description="交易所账户ID"),
    instType: Optional[str] = Query(None, description="产品类型：SPOT/SWAP"),
    instId: Optional[str] = Query(None, description="产品ID"),
    limit: int = Query(20, ge=1, le=50, description="返回数量"),
    session: AsyncSession = Depends(get_db_session),
    service: ManualTradingService = Depends(get_manual_trading_service),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        orders = await service.get_pending_orders(
            session=session,
            user_id=current_user.id,
            account_id=accountId,
            inst_type=instType.upper() if instType else None,
            inst_id=instId,
            limit=limit,
        )
        return ApiResponse.success_response(msg="获取成功", data={"list": orders})
    except ValueError as e:
        return ApiResponse.failed_response(msg=str(e), code=ResponseCode.FAILED.value)
    except Exception as e:
        logger.error(f"获取未成交委托失败: {e}")
        return ApiResponse.failed_response(msg="获取未成交委托失败，请稍后重试", code=ResponseCode.SYSTEM_ERROR.value)


@router.post("/orders", summary="提交手工委托")
async def place_manual_order(
    request: PlaceManualOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    service: ManualTradingService = Depends(get_manual_trading_service),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        result = await service.place_order(session=session, user_id=current_user.id, request=request)
        return ApiResponse.success_response(msg="委托提交成功", data=result)
    except ValueError as e:
        return ApiResponse.failed_response(msg=str(e), code=ResponseCode.FAILED.value)
    except Exception as e:
        logger.error(f"提交手工委托失败: {e}")
        return ApiResponse.failed_response(msg="委托提交失败，请稍后重试", code=ResponseCode.SYSTEM_ERROR.value)


@router.post("/orders/cancel", summary="撤销手工委托")
async def cancel_manual_order(
    request: CancelManualOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    service: ManualTradingService = Depends(get_manual_trading_service),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        result = await service.cancel_order(
            session=session,
            user_id=current_user.id,
            account_id=request.accountId,
            inst_id=request.instId,
            ord_id=request.ordId,
        )
        return ApiResponse.success_response(msg="撤单成功", data=result)
    except ValueError as e:
        return ApiResponse.failed_response(msg=str(e), code=ResponseCode.FAILED.value)
    except Exception as e:
        logger.error(f"撤销手工委托失败: {e}")
        return ApiResponse.failed_response(msg="撤销手工委托失败，请稍后重试", code=ResponseCode.SYSTEM_ERROR.value)
