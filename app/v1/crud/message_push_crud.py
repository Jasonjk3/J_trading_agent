"""消息推送配置 CRUD。"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.message_push_model import (
    MessagePushConfigModel,
    PushBotType,
    PushTestStatus,
)


async def get_configs(
    session: AsyncSession,
    user_id: str,
    bot_type: Optional[PushBotType] = None,
    enabled: Optional[bool] = None,
) -> List[MessagePushConfigModel]:
    conditions = [MessagePushConfigModel.user_id == user_id]
    if bot_type is not None:
        conditions.append(MessagePushConfigModel.bot_type == bot_type)
    if enabled is not None:
        conditions.append(MessagePushConfigModel.enabled == enabled)
    result = await session.execute(
        select(MessagePushConfigModel)
        .where(and_(*conditions))
        .order_by(desc(MessagePushConfigModel.created_at))
    )
    return list(result.scalars().all())


async def count_configs(session: AsyncSession, user_id: str) -> int:
    result = await session.execute(
        select(func.count(MessagePushConfigModel.id)).where(
            MessagePushConfigModel.user_id == user_id
        )
    )
    return result.scalar() or 0


async def get_config(
    session: AsyncSession, config_id: str, user_id: str
) -> Optional[MessagePushConfigModel]:
    result = await session.execute(
        select(MessagePushConfigModel).where(
            and_(
                MessagePushConfigModel.id == config_id,
                MessagePushConfigModel.user_id == user_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def create_config(
    session: AsyncSession, user_id: str, data: Dict[str, Any]
) -> MessagePushConfigModel:
    config = MessagePushConfigModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        **data,
    )
    session.add(config)
    await session.flush()
    await session.refresh(config)
    return config


async def update_config(
    session: AsyncSession, config: MessagePushConfigModel, data: Dict[str, Any]
) -> MessagePushConfigModel:
    for key, value in data.items():
        setattr(config, key, value)
    config.updated_at = datetime.now()
    await session.flush()
    await session.refresh(config)
    return config


async def delete_config(session: AsyncSession, config: MessagePushConfigModel) -> None:
    await session.delete(config)
    await session.flush()


async def update_test_result(
    session: AsyncSession,
    config: MessagePushConfigModel,
    success: bool,
    error: Optional[str] = None,
) -> MessagePushConfigModel:
    config.last_test_status = PushTestStatus.SUCCESS if success else PushTestStatus.FAILED
    config.last_test_at = datetime.now()
    config.last_error = None if success else (error or "发送失败")[:500]
    config.updated_at = datetime.now()
    await session.flush()
    await session.refresh(config)
    return config

