#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息面采集 API（与前端 /v1/news-intelligence-agents 对齐）
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.database import get_db_session
from app.public.dependencies.auth import get_current_user
from app.public.dependencies.response import ApiResponse, ResponseCode
from models.inner_models.user_model import UserModel
from models.inner_models.news_intelligence_model import NewsIntelligenceAgentStatus
from app.v1.services.news_intelligence_service import NewsIntelligenceService
from app.v1.schemas.news_intelligence_schema import (
    CreateNewsIntelligenceAgentRequest,
    UpdateNewsIntelligenceAgentRequest,
)
from app.v1.crud.news_intelligence_crud import get_agent_by_id_and_user

router = APIRouter(prefix="/news-intelligence-agents", tags=["消息面采集"])

_service = NewsIntelligenceService()


def get_service() -> NewsIntelligenceService:
    return _service


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


@router.get("", summary="消息面采集任务列表")
async def list_news_intelligence_agents(
    status: Optional[NewsIntelligenceAgentStatus] = Query(None, description="运行状态"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        agents, total = await service.get_list(session, current_user.id, status=status)
        return ApiResponse.success_response(msg="获取成功", data={"list": agents, "total": total})
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.post("", summary="创建消息面采集任务")
async def create_news_intelligence_agent(
    request: CreateNewsIntelligenceAgentRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        data = await service.create(
            session,
            user_id=current_user.id,
            name=request.name,
            sectors=request.sectors,
            llm_model_id=request.llmModelId,
            interval_minutes=request.intervalMinutes,
            max_items_per_batch=request.maxItemsPerBatch,
            temperature=request.temperature,
            remark=request.remark,
            custom_keywords=request.customKeywords,
            symbol_codes=request.symbolCodes,
            run_on_create=request.runOnCreate,
        )
        await session.commit()
        return ApiResponse.success_response(msg="创建成功", data=data)
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get("/{agent_id}", summary="任务详情")
async def get_news_intelligence_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        data = await service.get_by_id(session, agent_id, current_user.id)
        if not data:
            return ApiResponse.failed_response(msg="任务不存在", code=ResponseCode.NOT_FOUND.value)
        return ApiResponse.success_response(msg="获取成功", data=data)
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.put("/{agent_id}", summary="更新任务")
async def update_news_intelligence_agent(
    agent_id: str,
    request: UpdateNewsIntelligenceAgentRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        data = await service.update(
            session,
            agent_id,
            current_user.id,
            name=request.name,
            remark=request.remark,
            sectors=request.sectors,
            custom_keywords=request.customKeywords,
            symbol_codes=request.symbolCodes,
            llm_model_id=request.llmModelId,
            interval_minutes=request.intervalMinutes,
            max_items_per_batch=request.maxItemsPerBatch,
            temperature=request.temperature,
        )
        if not data:
            return ApiResponse.failed_response(msg="任务不存在", code=ResponseCode.NOT_FOUND.value)
        await session.commit()
        return ApiResponse.success_response(msg="更新成功", data=data)
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"更新失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.delete("/{agent_id}", summary="删除任务")
async def delete_news_intelligence_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        ok, msg = await service.delete(session, agent_id, current_user.id)
        if not ok:
            return ApiResponse.failed_response(
                msg=msg or "删除失败",
                code=ResponseCode.FAILED.value,
            )
        await session.commit()
        return ApiResponse.success_response(msg="删除成功")
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.post("/{agent_id}/start", summary="启动采集")
async def start_news_intelligence(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        ok, msg = await service.start(session, agent_id, current_user.id)
        if not ok:
            return ApiResponse.failed_response(msg=msg, code=ResponseCode.FAILED.value)
        await session.commit()
        return ApiResponse.success_response(msg=msg, data={"success": True, "message": msg})
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"操作失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.post("/{agent_id}/stop", summary="停止采集")
async def stop_news_intelligence(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        ok, msg = await service.stop(session, agent_id, current_user.id)
        if not ok:
            return ApiResponse.failed_response(msg=msg, code=ResponseCode.FAILED.value)
        await session.commit()
        return ApiResponse.success_response(msg=msg, data={"success": True, "message": msg})
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"操作失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.post("/{agent_id}/collect", summary="立即采集一轮")
async def collect_news_intelligence_now(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        ok, msg, inserted = await service.collect_now(session, agent_id, current_user.id)
        if not ok:
            return ApiResponse.failed_response(msg=msg, code=ResponseCode.FAILED.value)
        await session.commit()
        return ApiResponse.success_response(
            msg=msg,
            data={"success": True, "inserted": inserted, "message": msg},
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"采集失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get("/{agent_id}/items", summary="资讯时间轴列表")
async def list_news_timeline_items(
    agent_id: str,
    order: str = Query("desc", description="排序 asc|desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    keyword: Optional[str] = Query(None),
    time_from: Optional[str] = Query(None, alias="from"),
    time_to: Optional[str] = Query(None, alias="to"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: NewsIntelligenceService = Depends(get_service),
):
    try:
        exists = await get_agent_by_id_and_user(session, agent_id, current_user.id)
        if not exists:
            return ApiResponse.failed_response(msg="任务不存在", code=ResponseCode.NOT_FOUND.value)
        tf = _parse_dt(time_from)
        tt = _parse_dt(time_to)
        if order not in ("asc", "desc"):
            order = "desc"
        items, total = await service.list_timeline_items(
            session,
            agent_id,
            current_user.id,
            order=order,
            page=page,
            page_size=page_size,
            keyword=keyword,
            time_from=tf,
            time_to=tt,
        )
        return ApiResponse.success_response(
            msg="获取成功",
            data={"list": items, "total": total},
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )
