#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
交易所账户 CRUD 操作
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.exchange_account_model import (
    ExchangeAccountModel,
    ExchangeCode,
    BindStatus
)
from loguru import logger


async def get_exchange_account_by_id(
    session: AsyncSession,
    account_id: str
) -> Optional[ExchangeAccountModel]:
    """根据ID获取交易所账户"""
    query = select(ExchangeAccountModel).where(ExchangeAccountModel.id == account_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_exchange_account_by_id_and_user(
    session: AsyncSession,
    account_id: str,
    user_id: str
) -> Optional[ExchangeAccountModel]:
    """根据ID和用户ID获取交易所账户"""
    query = select(ExchangeAccountModel).where(
        and_(
            ExchangeAccountModel.id == account_id,
            ExchangeAccountModel.user_id == user_id
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_exchange_accounts(
    session: AsyncSession,
    user_id: str,
    exchange: Optional[ExchangeCode] = None,
    enabled: Optional[bool] = None,
    bind_status: Optional[BindStatus] = None,
    skip: int = 0,
    limit: int = 100
) -> List[ExchangeAccountModel]:
    """获取交易所账户列表"""
    conditions = [ExchangeAccountModel.user_id == user_id]
    
    if exchange is not None:
        conditions.append(ExchangeAccountModel.exchange == exchange)
    if enabled is not None:
        conditions.append(ExchangeAccountModel.enabled == enabled)
    if bind_status is not None:
        conditions.append(ExchangeAccountModel.bind_status == bind_status)
    
    query = select(ExchangeAccountModel).where(and_(*conditions))
    query = query.order_by(desc(ExchangeAccountModel.created_at)).offset(skip).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_exchange_accounts(
    session: AsyncSession,
    user_id: str,
    exchange: Optional[ExchangeCode] = None,
    enabled: Optional[bool] = None,
    bind_status: Optional[BindStatus] = None
) -> int:
    """统计交易所账户数量"""
    from sqlalchemy import func
    
    conditions = [ExchangeAccountModel.user_id == user_id]
    
    if exchange is not None:
        conditions.append(ExchangeAccountModel.exchange == exchange)
    if enabled is not None:
        conditions.append(ExchangeAccountModel.enabled == enabled)
    if bind_status is not None:
        conditions.append(ExchangeAccountModel.bind_status == bind_status)
    
    query = select(func.count(ExchangeAccountModel.id)).where(and_(*conditions))
    result = await session.execute(query)
    return result.scalar() or 0


async def create_exchange_account(
    session: AsyncSession,
    user_id: str,
    exchange: ExchangeCode,
    api_key: str,
    api_secret: str,
    passphrase: Optional[str] = None,
    remark: Optional[str] = None,
    read_only: bool = False,
    enabled: bool = True
) -> ExchangeAccountModel:
    """创建交易所账户"""
    account = ExchangeAccountModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        exchange=exchange,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        remark=remark,
        read_only=read_only,
        enabled=enabled,
        bind_status=BindStatus.NEVER,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return account


async def update_exchange_account(
    session: AsyncSession,
    account_id: str,
    data: Dict[str, Any]
) -> Optional[ExchangeAccountModel]:
    """更新交易所账户"""
    account = await get_exchange_account_by_id(session, account_id)
    if not account:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(account, key, value)
    
    account.updated_at = datetime.now()
    await session.flush()
    await session.refresh(account)
    return account


async def delete_exchange_account(
    session: AsyncSession,
    account_id: str
) -> bool:
    """删除交易所账户"""
    account = await get_exchange_account_by_id(session, account_id)
    if not account:
        return False
    
    await session.delete(account)
    await session.flush()
    return True


async def update_bind_status(
    session: AsyncSession,
    account_id: str,
    bind_status: BindStatus,
    verified_at: Optional[datetime] = None
) -> Optional[ExchangeAccountModel]:
    """更新绑定状态"""
    account = await get_exchange_account_by_id(session, account_id)
    if not account:
        return None
    
    account.bind_status = bind_status
    if verified_at:
        account.last_verified_at = verified_at
    account.updated_at = datetime.now()
    
    await session.flush()
    await session.refresh(account)
    return account
