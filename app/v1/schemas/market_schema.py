#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
市场数据相关Schema
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class MarketSymbolItem(BaseModel):
    """交易对信息"""
    symbol: str = Field(..., description="交易对ID，如 BTC-USDT")
    baseAsset: str = Field(..., description="基础币种，如 BTC")
    quoteAsset: str = Field(..., description="计价币种，如 USDT")


class MarketSymbolListResponse(BaseModel):
    """交易对列表响应"""
    list: List[MarketSymbolItem]


class KlineItem(BaseModel):
    """K线数据项"""
    time: str = Field(..., description="时间戳")
    open: str = Field(..., description="开盘价")
    high: str = Field(..., description="最高价")
    low: str = Field(..., description="最低价")
    close: str = Field(..., description="收盘价")
    volume: str = Field(..., description="成交量")


class KlineListResponse(BaseModel):
    """K线数据响应"""
    list: List[KlineItem]


MarketInterval = Literal["15m", "1h", "4h", "1d"]
RecommendationType = Literal["bullish", "bearish", "neutral"]


class MarketIndicators(BaseModel):
    """市场指标数据"""
    symbol: str = Field(..., description="交易对")
    interval: MarketInterval = Field(..., description="时间周期")
    latestPrice: str = Field(..., description="最新价格")
    change24h: str = Field(..., description="24小时涨跌幅")
    high24h: str = Field(..., description="24小时最高价")
    low24h: str = Field(..., description="24小时最低价")
    volume24h: str = Field(..., description="24小时成交量")
    ma5: str = Field(default="0", description="5日均线")
    ma10: str = Field(default="0", description="10日均线")
    ma20: str = Field(default="0", description="20日均线")
    rsi14: str = Field(default="0", description="14日RSI")
    macd: str = Field(default="0", description="MACD")
    signal: str = Field(default="0", description="Signal线")
    histogram: str = Field(default="0", description="MACD柱状图")
    volatility: str = Field(default="0", description="波动率")
    recommendation: RecommendationType = Field(default="neutral", description="建议: bullish/bearish/neutral")


class KlineQueryParams(BaseModel):
    """K线查询参数"""
    symbol: str = Field(..., description="交易对，如 BTC-USDT")
    interval: MarketInterval = Field(..., description="时间周期")
    limit: Optional[int] = Field(default=100, ge=1, le=300, description="获取数量")


class IndicatorsQueryParams(BaseModel):
    """指标查询参数"""
    symbol: str = Field(..., description="交易对，如 BTC-USDT")
    interval: MarketInterval = Field(..., description="时间周期")


# ============================================================================
# 自选交易对相关 Schema
# ============================================================================

class FavoriteSymbolItem(BaseModel):
    """自选交易对项"""
    id: int = Field(..., description="自选ID")
    symbol: str = Field(..., description="交易对，如 BTC-USDT")
    name: str = Field(..., description="显示名称，如 BTC")
    sortOrder: int = Field(default=0, description="排序顺序")
    createdAt: Optional[str] = Field(None, description="创建时间")
    # 实时数据（前端获取）
    price: Optional[str] = Field(None, description="最新价格")
    change: Optional[str] = Field(None, description="24小时涨跌幅")


class FavoriteSymbolListResponse(BaseModel):
    """自选交易对列表响应"""
    list: List[FavoriteSymbolItem]


class AddFavoriteRequest(BaseModel):
    """添加自选请求"""
    symbol: str = Field(..., description="交易对，如 BTC-USDT")
    name: Optional[str] = Field(None, description="显示名称，如 BTC")


class RemoveFavoriteRequest(BaseModel):
    """移除自选请求"""
    symbol: str = Field(..., description="交易对，如 BTC-USDT")


class UpdateFavoriteSortRequest(BaseModel):
    """更新自选排序请求"""
    items: List[dict] = Field(..., description="排序列表，如 [{symbol: 'BTC-USDT', sortOrder: 1}]")
