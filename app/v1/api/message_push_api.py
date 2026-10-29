"""消息推送管理 API。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.auth import get_current_admin
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.v1.schemas.message_push_schema import (
    CreateMessagePushConfigRequest,
    TestMessagePushRequest,
    UpdateMessagePushConfigRequest,
    ValidateMessagePushConfigRequest,
)
from app.v1.services.message_push_service import MessagePushService
from models.inner_models.message_push_model import PushBotType
from models.inner_models.user_model import UserModel


router = APIRouter(prefix="/message-push-configs", tags=["消息推送管理"])


def get_message_push_service() -> MessagePushService:
    return MessagePushService()


@router.get("", summary="获取消息推送配置")
async def list_configs(
    botType: Optional[PushBotType] = Query(None),
    enabled: Optional[bool] = Query(None),
    session: AsyncSession = Depends(get_db_session),
    service: MessagePushService = Depends(get_message_push_service),
    current_admin: UserModel = Depends(get_current_admin),
):
    items, total = await service.get_list(session, current_admin.id, botType, enabled)
    return ApiResponse.success_response(
        data={"list": [service.model_to_response(item) for item in items], "total": total}
    )


@router.post("", summary="创建消息推送配置")
async def create_push_config(
    request: CreateMessagePushConfigRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MessagePushService = Depends(get_message_push_service),
    current_admin: UserModel = Depends(get_current_admin),
):
    try:
        item = await service.create(
            session, current_admin.id, request.model_dump(exclude_none=True)
        )
        await session.commit()
        return ApiResponse.success_response(msg="创建成功", data=service.model_to_response(item))
    except ValueError as exc:
        await session.rollback()
        return ApiResponse.failed_response(msg=str(exc), code=ResponseCode.FAILED.value)
    except Exception as exc:
        logger.exception("创建消息推送配置失败: {}", exc)
        await session.rollback()
        return ApiResponse.failed_response(msg="创建失败", code=ResponseCode.SYSTEM_ERROR.value)


@router.put("/{config_id}", summary="更新消息推送配置")
async def update_push_config(
    config_id: str,
    request: UpdateMessagePushConfigRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MessagePushService = Depends(get_message_push_service),
    current_admin: UserModel = Depends(get_current_admin),
):
    try:
        item = await service.update(
            session,
            config_id,
            current_admin.id,
            request.model_dump(exclude_unset=True),
        )
        if not item:
            return ApiResponse.failed_response(msg="配置不存在", code=ResponseCode.NOT_FOUND.value)
        await session.commit()
        return ApiResponse.success_response(msg="更新成功", data=service.model_to_response(item))
    except ValueError as exc:
        await session.rollback()
        return ApiResponse.failed_response(msg=str(exc), code=ResponseCode.FAILED.value)
    except Exception as exc:
        logger.exception("更新消息推送配置失败: {}", exc)
        await session.rollback()
        return ApiResponse.failed_response(msg="更新失败", code=ResponseCode.SYSTEM_ERROR.value)


@router.delete("/{config_id}", summary="删除消息推送配置")
async def remove_push_config(
    config_id: str,
    session: AsyncSession = Depends(get_db_session),
    service: MessagePushService = Depends(get_message_push_service),
    current_admin: UserModel = Depends(get_current_admin),
):
    from sqlalchemy import func, select
    from models.inner_models.data_monitor_model import MonitorTaskModel

    in_use = (await session.execute(
        select(func.count()).select_from(MonitorTaskModel).where(
            MonitorTaskModel.user_id == current_admin.id,
            MonitorTaskModel.push_config_id == config_id,
        )
    )).scalar() or 0
    if in_use:
        return ApiResponse.failed_response(
            msg="该机器人已被监控任务使用，请先更换任务的推送渠道",
            code=ResponseCode.FAILED.value,
        )
    success = await service.delete(session, config_id, current_admin.id)
    if not success:
        return ApiResponse.failed_response(msg="配置不存在", code=ResponseCode.NOT_FOUND.value)
    await session.commit()
    return ApiResponse.success_response(msg="删除成功")


@router.post("/validate", summary="验证飞书机器人凭据")
async def validate_push_config(
    request: ValidateMessagePushConfigRequest,
    service: MessagePushService = Depends(get_message_push_service),
    _current_admin: UserModel = Depends(get_current_admin),
):
    success, message = await service.validate_credentials(request.model_dump(exclude_none=True))
    return ApiResponse.success_response(data={"success": success, "message": message})


@router.post("/{config_id}/test", summary="发送测试消息")
async def test_push_config(
    config_id: str,
    request: TestMessagePushRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MessagePushService = Depends(get_message_push_service),
    current_admin: UserModel = Depends(get_current_admin),
):
    success, message = await service.send_test(
        session,
        config_id,
        current_admin.id,
        request.model_dump(exclude_none=True),
    )
    await session.commit()
    return ApiResponse.success_response(data={"success": success, "message": message})


@router.post("/{config_id}/validate", summary="验证已保存的飞书机器人凭据")
async def validate_saved_push_config(
    config_id: str,
    session: AsyncSession = Depends(get_db_session),
    service: MessagePushService = Depends(get_message_push_service),
    current_admin: UserModel = Depends(get_current_admin),
):
    success, message = await service.validate_saved(session, config_id, current_admin.id)
    await session.commit()
    return ApiResponse.success_response(data={"success": success, "message": message})
