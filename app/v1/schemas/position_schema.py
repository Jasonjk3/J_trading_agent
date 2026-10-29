#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
持仓管理相关 Schema
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum as PyEnum


class PositionSide(str, PyEnum):
    """持仓方向枚举"""
    LONG = "long"
    SHORT = "short"
    NET = "net"


class ExchangeCode(str, PyEnum):
    """交易所标识枚举"""
    OKX = "okx"
    BINANCE = "binance"
    BYBIT = "bybit"


class CloseType(str, PyEnum):
    """平仓类型枚举"""
    LIQUIDATION = "liquidation"
    PARTIAL_LIQUIDATION = "partial_liquidation"
    ADL = "adl"
    DELIVERY = "delivery"
    MANUAL = "manual"


class PositionListParams(BaseModel):
    """持仓列表查询参数"""
    exchange: Optional[ExchangeCode] = Field(None, description="交易所标识")
    symbol: Optional[str] = Field(None, description="交易对，如 BTC-USDT-SWAP")
    side: Optional[PositionSide] = Field(None, description="持仓方向")
    page: Optional[int] = Field(1, ge=1, description="页码")
    pageSize: Optional[int] = Field(20, ge=1, le=100, description="每页数量")


class PositionListItem(BaseModel):
    """持仓列表项"""
    id: str = Field(..., description="持仓ID（交易所账户ID_持仓ID）")
    exchange: str = Field(..., description="交易所标识")
    symbol: str = Field(..., description="交易对，如 BTC-USDT-SWAP")
    side: str = Field(..., description="持仓方向：long/short/net")
    quantity: str = Field(..., description="持仓数量")
    costPrice: str = Field(..., description="开仓均价")
    markPrice: str = Field(..., description="标记价格")
    notional: str = Field(..., description="持仓价值（美元）")
    unrealizedPnl: str = Field(..., description="未实现盈亏")
    unrealizedPnlRate: str = Field(..., description="未实现盈亏率")
    updatedAt: Optional[str] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class PositionHistoryItem(BaseModel):
    """历史持仓列表项"""
    id: str = Field(..., description="持仓ID（交易所账户ID_持仓ID）")
    exchange: str = Field(..., description="交易所标识")
    symbol: str = Field(..., description="交易对，如 BTC-USDT-SWAP")
    side: str = Field(..., description="持仓方向：long/short")
    quantity: str = Field(..., description="最大持仓数量")
    openAvgPrice: str = Field(..., description="开仓均价")
    closeAvgPrice: str = Field(..., description="平仓均价")
    pnl: str = Field(..., description="已实现盈亏")
    pnlRate: str = Field(..., description="已实现盈亏率（百分比）")
    lever: str = Field(..., description="杠杆倍数")
    closeType: Optional[str] = Field(None, description="平仓类型")
    openTime: Optional[str] = Field(None, description="开仓时间")
    closeTime: Optional[str] = Field(None, description="平仓时间")

    class Config:
        from_attributes = True


class PositionSummary(BaseModel):
    """持仓汇总信息"""
    totalNotional: str = Field(..., description="总持仓价值（美元）")
    totalUnrealizedPnl: str = Field(..., description="总未实现盈亏")


class PositionHistorySummary(BaseModel):
    """历史持仓汇总信息"""
    totalPnl: str = Field(..., description="总已实现盈亏")


class PositionListResponse(BaseModel):
    """持仓列表响应"""
    list: List[PositionListItem] = Field(..., description="持仓列表")
    total: int = Field(..., description="总数")
    summary: Optional[PositionSummary] = Field(None, description="汇总信息")


class PositionHistoryResponse(BaseModel):
    """历史持仓列表响应"""
    list: List[PositionHistoryItem] = Field(..., description="历史持仓列表")
    total: int = Field(..., description="总数")
    summary: Optional[PositionHistorySummary] = Field(None, description="汇总信息")
