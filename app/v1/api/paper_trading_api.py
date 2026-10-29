#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模拟盘 API。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.auth import get_current_user
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.v1.schemas.paper_trading_schema import (
    CreatePaperAccountRequest,
    CreatePaperDecisionRequest,
    CreatePaperTradeRequest,
)
from app.v1.services.paper_trading_service import PaperTradingError, PaperTradingService
from app.v1.services.market_service import MarketService
from models.inner_models.paper_trading_model import PaperAccountStatus
from models.inner_models.user_model import UserModel


router = APIRouter(prefix="/paper-trading", tags=["模拟盘"])
_service = PaperTradingService()


def get_service() -> PaperTradingService:
    return _service


def get_market_service() -> MarketService:
    return MarketService()


def failed(exc: Exception):
    code = ResponseCode.FAILED.value if isinstance(exc, PaperTradingError) else ResponseCode.SYSTEM_ERROR.value
    return ApiResponse.failed_response(msg=str(exc), code=code)


@router.get("/dashboard", summary="获取模拟盘总览")
async def get_dashboard(
    range_name: str = Query("30D", alias="range", pattern="^(7D|30D|90D|ALL)$"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        data = await service.dashboard(session, current_user.id, range_name)
        await session.commit()
        return ApiResponse.success_response(msg="获取成功", data=data)
    except Exception as exc:
        await session.rollback()
        return failed(exc)


@router.post("/accounts/human", summary="显式初始化自主模拟账户")
async def initialize_human_account(session: AsyncSession = Depends(get_db_session),
                                   current_user: UserModel = Depends(get_current_user),
                                   service: PaperTradingService = Depends(get_service)):
    try:
        account = await service.initialize_human_account(session, current_user.id)
        await session.commit()
        return ApiResponse.success_response(data={"id": account.id})
    except Exception as exc:
        await session.rollback()
        return failed(exc)


@router.post("/accounts", summary="从已有 Agent 创建模拟账户")
async def create_account(
    request: CreatePaperAccountRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        account = await service.create_agent_account(session, current_user.id, request)
        await session.commit()
        return ApiResponse.success_response(msg="添加成功", data={"id": account.id})
    except Exception as exc:
        await session.rollback()
        return failed(exc)


@router.post("/accounts/{account_id}/pause", summary="暂停 Agent 模拟账户")
async def pause_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        await service.set_status(session, account_id, current_user.id, PaperAccountStatus.PAUSED)
        await session.commit()
        return ApiResponse.success_response(msg="已暂停", data={"success": True})
    except Exception as exc:
        await session.rollback()
        return failed(exc)


@router.post("/accounts/{account_id}/resume", summary="继续 Agent 模拟账户")
async def resume_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        await service.set_status(session, account_id, current_user.id, PaperAccountStatus.RUNNING)
        await session.commit()
        return ApiResponse.success_response(msg="已继续运行", data={"success": True})
    except Exception as exc:
        await session.rollback()
        return failed(exc)


@router.delete("/accounts/{account_id}", summary="删除模拟账户")
async def delete_account(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        await service.delete_account(session, account_id, current_user.id)
        await session.commit()
        return ApiResponse.success_response(msg="删除成功")
    except Exception as exc:
        await session.rollback()
        return failed(exc)


@router.get("/accounts/{account_id}/positions", summary="获取模拟持仓")
async def get_positions(
    account_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        rows = await service.list_positions(session, account_id, current_user.id)
        return ApiResponse.success_response(msg="获取成功", data={"list": rows, "total": len(rows)})
    except Exception as exc:
        return failed(exc)


@router.get("/accounts/{account_id}/trades", summary="获取模拟成交记录")
async def get_trades(
    account_id: str,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        rows = await service.list_trades(session, account_id, current_user.id, limit)
        return ApiResponse.success_response(msg="获取成功", data={"list": rows, "total": len(rows)})
    except Exception as exc:
        return failed(exc)


@router.post("/accounts/{account_id}/trades", summary="执行模拟买卖")
async def create_trade(
    account_id: str,
    request: CreatePaperTradeRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
    market_service: MarketService = Depends(get_market_service),
):
    try:
        market = await market_service.get_indicators(
            symbol=request.symbol,
            interval="15m",
            session=session,
        )
        market_price = float((market or {}).get("latestPrice") or 0)
        priced_request = request.model_copy(update={"price": market_price})
        trade = await service.execute_trade(session, account_id, current_user.id, priced_request)
        await session.commit()
        return ApiResponse.success_response(msg="成交成功", data=service.trade_to_response(trade))
    except Exception as exc:
        await session.rollback()
        return failed(exc)


@router.get("/accounts/{account_id}/decisions", summary="获取 Agent 决策记录")
async def get_decisions(
    account_id: str,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    try:
        rows = await service.list_decisions(session, account_id, current_user.id, limit)
        return ApiResponse.success_response(msg="获取成功", data={"list": rows, "total": len(rows)})
    except Exception as exc:
        return failed(exc)


@router.post("/accounts/{account_id}/decisions", summary="写入 Agent 模拟决策")
async def create_decision(
    account_id: str,
    request: CreatePaperDecisionRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: PaperTradingService = Depends(get_service),
):
    """供 Agent 模拟执行链写入审计记录；账户所有权仍由当前登录用户校验。"""
    try:
        row = await service.create_decision(session, account_id, current_user.id, request)
        await session.commit()
        return ApiResponse.success_response(msg="记录成功", data=service.decision_to_response(row))
    except Exception as exc:
        await session.rollback()
        return failed(exc)
