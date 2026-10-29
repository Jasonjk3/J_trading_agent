#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
市场数据API路由
"""
from fastapi import APIRouter, Depends, Query, Body
from typing import Optional, Literal, List
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.services.market_service import MarketService
from app.v1.schemas.market_schema import AddFavoriteRequest, RemoveFavoriteRequest, UpdateFavoriteSortRequest
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.auth import get_current_user
from app.public.dependencies.database import get_db_session
from models.inner_models.user_model import UserModel

router = APIRouter(prefix="/market", tags=["市场数据"])


def get_market_service() -> MarketService:
    """获取市场服务实例"""
    return MarketService()


@router.get("/symbols", summary="搜索交易对")
async def search_symbols(
    keyword: Optional[str] = Query(None, description="搜索关键词，如 BTC"),
    service: MarketService = Depends(get_market_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    搜索交易对列表
    
    - 支持按关键词模糊搜索
    - 返回交易对ID、基础币种、计价币种
    """
    try:
        symbols = await service.search_symbols(keyword)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "list": symbols
            }
        )
    except ValueError as e:
        logger.error(f"搜索交易对失败(配置错误): {e}")
        return ApiResponse.failed_response(
            msg="OKX API配置不完整，请联系管理员",
            code=ResponseCode.FAILED.value
        )
    except Exception as e:
        logger.error(f"搜索交易对失败: {e}")
        return ApiResponse.failed_response(
            msg="搜索交易对失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/kline", summary="获取K线数据")
async def get_kline(
    symbol: str = Query(..., description="交易对，如 BTCUSDT 或 BTC-USDT"),
    interval: Literal["15m", "1h", "4h", "1d"] = Query(..., description="时间周期"),
    limit: int = Query(100, ge=1, le=300, description="获取数量，最大300"),
    service: MarketService = Depends(get_market_service),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取K线数据
    
    - 支持多种时间周期：15m, 1h, 4h, 1d
    - 优先读 MySQL 缓存，不足时从交易所增量补拉
    - 返回时间、开高低收、成交量
    """
    try:
        kline_data = await service.get_kline(
            symbol=symbol,
            interval=interval,
            limit=limit,
            session=session,
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "list": kline_data
            }
        )
    except ValueError as e:
        logger.error(f"获取K线数据失败(配置错误): {e}")
        return ApiResponse.failed_response(
            msg="OKX API配置不完整，请联系管理员",
            code=ResponseCode.FAILED.value
        )
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return ApiResponse.failed_response(
            msg="获取K线数据失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/indicators", summary="获取市场指标")
async def get_indicators(
    symbol: str = Query(..., description="交易对，如 BTCUSDT 或 BTC-USDT"),
    interval: Literal["15m", "1h", "4h", "1d"] = Query(..., description="时间周期"),
    service: MarketService = Depends(get_market_service),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取市场指标数据
    
    - 返回最新价、24小时涨跌幅、高低价、成交量
    - K 线优先读 MySQL 缓存；ticker 仍走交易所
    - 返回技术指标：MA5/10/20、RSI14、MACD
    - 返回交易建议：bullish/bearish/neutral
    """
    try:
        indicators = await service.get_indicators(
            symbol=symbol,
            interval=interval,
            session=session,
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=indicators
        )
    except ValueError as e:
        logger.error(f"获取市场指标失败(配置错误): {e}")
        return ApiResponse.failed_response(
            msg="OKX API配置不完整，请联系管理员",
            code=ResponseCode.FAILED.value
        )
    except Exception as e:
        logger.error(f"获取市场指标失败: {e}")
        return ApiResponse.failed_response(
            msg="获取市场指标失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 自选交易对相关接口
# ============================================================================

@router.get("/favorites", summary="获取自选交易对列表")
async def get_favorite_symbols(
    session: AsyncSession = Depends(get_db_session),
    service: MarketService = Depends(get_market_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取当前用户的自选交易对列表
    
    - 返回用户添加的所有自选交易对
    - 按排序顺序返回
    """
    try:
        favorites = await service.get_favorite_symbols(session, current_user.id)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "list": favorites
            }
        )
    except Exception as e:
        logger.error(f"获取自选列表失败: {e}")
        return ApiResponse.failed_response(
            msg="获取自选列表失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/favorites", summary="添加自选交易对")
async def add_favorite_symbol(
    request: AddFavoriteRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MarketService = Depends(get_market_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    添加交易对到自选列表
    
    - 最多支持20个自选
    - 重复添加会返回错误
    """
    try:
        favorite = await service.add_favorite_symbol(
            session=session,
            user_id=current_user.id,
            symbol=request.symbol,
            name=request.name
        )
        await session.commit()
        
        return ApiResponse.success_response(
            msg="添加成功",
            data=favorite
        )
    except ValueError as e:
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.FAILED.value
        )
    except Exception as e:
        logger.error(f"添加自选失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg="添加自选失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/favorites", summary="移除自选交易对")
async def remove_favorite_symbol(
    symbol: str = Query(..., description="交易对，如 BTC-USDT"),
    session: AsyncSession = Depends(get_db_session),
    service: MarketService = Depends(get_market_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    从自选列表中移除交易对
    """
    try:
        await service.remove_favorite_symbol(
            session=session,
            user_id=current_user.id,
            symbol=symbol
        )
        await session.commit()
        
        return ApiResponse.success_response(msg="移除成功")
    except ValueError as e:
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.FAILED.value
        )
    except Exception as e:
        logger.error(f"移除自选失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg="移除自选失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/favorites/check", summary="检查交易对是否已自选")
async def check_favorite_symbol(
    symbol: str = Query(..., description="交易对，如 BTC-USDT"),
    session: AsyncSession = Depends(get_db_session),
    service: MarketService = Depends(get_market_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    检查指定交易对是否已在自选列表中
    """
    try:
        is_favorite = await service.is_symbol_favorite(
            session=session,
            user_id=current_user.id,
            symbol=symbol
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"isFavorite": is_favorite}
        )
    except Exception as e:
        logger.error(f"检查自选状态失败: {e}")
        return ApiResponse.failed_response(
            msg="检查自选状态失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/favorites/sort", summary="更新自选排序")
async def update_favorite_sort(
    request: UpdateFavoriteSortRequest,
    session: AsyncSession = Depends(get_db_session),
    service: MarketService = Depends(get_market_service),
    current_user: UserModel = Depends(get_current_user)
):
    """
    批量更新自选交易对的排序顺序
    """
    try:
        await service.update_favorite_sort(
            session=session,
            user_id=current_user.id,
            items=request.items
        )
        await session.commit()
        
        return ApiResponse.success_response(msg="更新成功")
    except Exception as e:
        logger.error(f"更新自选排序失败: {e}")
        await session.rollback()
        return ApiResponse.failed_response(
            msg="更新自选排序失败，请稍后重试",
            code=ResponseCode.SYSTEM_ERROR.value
        )
