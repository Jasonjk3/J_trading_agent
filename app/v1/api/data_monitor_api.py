"""Authenticated data monitoring configuration endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.auth import get_current_admin
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse
from app.v1.schemas.data_monitor_schema import RulePayload, TaskEnabledPayload, TaskPayload, TemplatePayload
from app.v1.services.data_monitor_service import DataMonitorService
from models.inner_models.data_monitor_model import MonitorSampleModel
from models.inner_models.user_model import UserModel

router = APIRouter(prefix="/data-monitor", tags=["数据监控"])


def get_service():
    return DataMonitorService()


@router.get("/rules")
async def list_rules(session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    return ApiResponse.success_response(data={"list": await service.list_rules(session, user.id)})


@router.post("/rules")
async def create_rule(payload: RulePayload, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    result = await service.save_rule(session, user.id, payload.model_dump())
    await session.commit()
    return ApiResponse.success_response(data=result)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    try:
        await service.remove_rule(session, user.id, rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApiResponse.success_response()


@router.get("/templates")
async def list_templates(session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    return ApiResponse.success_response(data={"list": await service.list_templates(session, user.id)})


@router.post("/templates")
async def create_template(payload: TemplatePayload, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    result = await service.save_template(session, user.id, payload.model_dump())
    await session.commit()
    return ApiResponse.success_response(data=result)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    try:
        await service.remove_template(session, user.id, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApiResponse.success_response()


@router.get("/tasks")
async def list_tasks(session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    return ApiResponse.success_response(data={"list": await service.list_tasks(session, user.id)})


@router.post("/tasks")
async def create_task(payload: TaskPayload, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    try:
        task = await service.save_task(session, user.id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApiResponse.success_response(data={"id": task.id})


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, payload: TaskPayload, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    task = await service.get_task(session, user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="监控任务不存在")
    try:
        await service.save_task(session, user.id, payload.model_dump(), task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ApiResponse.success_response(data={"id": task.id})


@router.put("/tasks/{task_id}/enabled")
async def set_enabled(task_id: str, payload: TaskEnabledPayload, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    from datetime import datetime
    task = await service.get_task(session, user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="监控任务不存在")
    task.enabled = payload.enabled
    task.next_check_at = datetime.now() if payload.enabled else None
    task.updated_at = datetime.now()
    await session.commit()
    return ApiResponse.success_response(data={"enabled": task.enabled})


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    task = await service.get_task(session, user.id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="监控任务不存在")
    await session.execute(delete(MonitorSampleModel).where(MonitorSampleModel.task_id == task.id))
    await session.delete(task)
    await session.commit()
    return ApiResponse.success_response()


@router.get("/events")
async def list_events(taskId: str | None = None, session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    return ApiResponse.success_response(data={"list": await service.get_events(session, user.id, taskId)})


@router.get("/summary")
async def get_summary(session: AsyncSession = Depends(get_db_session), user: UserModel = Depends(get_current_admin), service: DataMonitorService = Depends(get_service)):
    return ApiResponse.success_response(data=await service.get_summary(session, user.id))
