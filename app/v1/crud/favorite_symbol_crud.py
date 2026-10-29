#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
自选交易对 CRUD 操作
"""
from typing import List, Optional
from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.favorite_symbol_model import FavoriteSymbolModel


async def get_user_favorites(
    session: AsyncSession,
    user_id: str
) -> List[FavoriteSymbolModel]:
    """获取用户的自选交易对列表"""
    query = select(FavoriteSymbolModel).where(
        FavoriteSymbolModel.user_id == user_id
    ).order_by(FavoriteSymbolModel.sort_order, FavoriteSymbolModel.id)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_favorite_by_symbol(
    session: AsyncSession,
    user_id: str,
    symbol: str
) -> Optional[FavoriteSymbolModel]:
    """根据交易对获取自选记录"""
    query = select(FavoriteSymbolModel).where(
        and_(
            FavoriteSymbolModel.user_id == user_id,
            FavoriteSymbolModel.symbol == symbol
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_favorite_by_id(
    session: AsyncSession,
    favorite_id: int,
    user_id: str
) -> Optional[FavoriteSymbolModel]:
    """根据ID获取自选记录"""
    query = select(FavoriteSymbolModel).where(
        and_(
            FavoriteSymbolModel.id == favorite_id,
            FavoriteSymbolModel.user_id == user_id
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def add_favorite(
    session: AsyncSession,
    user_id: str,
    symbol: str,
    name: Optional[str] = None
) -> FavoriteSymbolModel:
    """添加自选交易对"""
    # 获取当前最大排序号
    max_order_query = select(func.max(FavoriteSymbolModel.sort_order)).where(
        FavoriteSymbolModel.user_id == user_id
    )
    result = await session.execute(max_order_query)
    max_order = result.scalar() or 0
    
    # 如果没有提供名称，从symbol中提取
    if not name:
        name = symbol.split('-')[0] if '-' in symbol else symbol.replace('USDT', '')
    
    favorite = FavoriteSymbolModel(
        user_id=user_id,
        symbol=symbol,
        name=name,
        sort_order=max_order + 1
    )
    session.add(favorite)
    await session.flush()
    await session.refresh(favorite)
    return favorite


async def remove_favorite(
    session: AsyncSession,
    user_id: str,
    symbol: str
) -> bool:
    """移除自选交易对"""
    favorite = await get_favorite_by_symbol(session, user_id, symbol)
    if favorite:
        await session.delete(favorite)
        await session.flush()
        return True
    return False


async def remove_favorite_by_id(
    session: AsyncSession,
    favorite_id: int,
    user_id: str
) -> bool:
    """根据ID移除自选交易对"""
    favorite = await get_favorite_by_id(session, favorite_id, user_id)
    if favorite:
        await session.delete(favorite)
        await session.flush()
        return True
    return False


async def update_sort_order(
    session: AsyncSession,
    user_id: str,
    symbol_orders: List[dict]
) -> bool:
    """批量更新排序顺序
    
    Args:
        symbol_orders: [{"symbol": "BTC-USDT", "sortOrder": 1}, ...]
    """
    for item in symbol_orders:
        favorite = await get_favorite_by_symbol(session, user_id, item["symbol"])
        if favorite:
            favorite.sort_order = item["sortOrder"]
    
    await session.flush()
    return True


async def is_favorite(
    session: AsyncSession,
    user_id: str,
    symbol: str
) -> bool:
    """判断是否已自选"""
    favorite = await get_favorite_by_symbol(session, user_id, symbol)
    return favorite is not None


async def get_favorites_count(
    session: AsyncSession,
    user_id: str
) -> int:
    """获取用户自选数量"""
    query = select(func.count(FavoriteSymbolModel.id)).where(
        FavoriteSymbolModel.user_id == user_id
    )
    result = await session.execute(query)
    return result.scalar() or 0
