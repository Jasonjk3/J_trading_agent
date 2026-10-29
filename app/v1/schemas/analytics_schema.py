#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
收益分析相关Schema
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum


class ExchangeCode(str, Enum):
    """交易所代码"""
    BINANCE = "binance"
    OKX = "okx"
    BYBIT = "bybit"


class PeriodType(str, Enum):
    """汇总周期类型"""
    DAY = "day"
    WEEK = "week"


# ==================== 收益汇总 ====================

class ProfitSummaryParams(BaseModel):
    """收益汇总查询参数"""
    from_date: Optional[str] = Field(None, alias="from", description="开始日期 YYYY-MM-DD")
    to_date: Optional[str] = Field(None, alias="to", description="结束日期 YYYY-MM-DD")
    exchange: Optional[str] = Field(None, description="交易所筛选")
    symbol: Optional[str] = Field(None, description="交易对筛选")
    
    class Config:
        populate_by_name = True


class ProfitSummaryResponse(BaseModel):
    """收益汇总响应"""
    totalProfit: str = Field(description="总收益（已实现盈亏）")
    totalFee: str = Field(description="总手续费")
    netProfit: str = Field(description="净收益（总收益-总手续费）")
    returnRate: Optional[str] = Field(None, description="收益率；期初权益或出入金未知时为空")
    from_date: Optional[str] = Field(None, alias="from", description="开始日期")
    to_date: Optional[str] = Field(None, alias="to", description="结束日期")
    exchange: Optional[str] = Field(None, description="交易所")
    
    class Config:
        populate_by_name = True


# ==================== 收益趋势 ====================

class ProfitTrendParams(BaseModel):
    """收益趋势查询参数"""
    from_date: Optional[str] = Field(None, alias="from", description="开始日期 YYYY-MM-DD")
    to_date: Optional[str] = Field(None, alias="to", description="结束日期 YYYY-MM-DD")
    period: PeriodType = Field(default=PeriodType.DAY, description="汇总周期：day/week")
    exchange: Optional[str] = Field(None, description="交易所筛选")
    symbol: Optional[str] = Field(None, description="交易对筛选")
    
    class Config:
        populate_by_name = True


class ProfitTrendPoint(BaseModel):
    """收益趋势数据点"""
    date: str = Field(description="日期")
    profit: str = Field(description="当期收益")
    cumulative: Optional[str] = Field(None, description="累计收益")


class ProfitTrendResponse(BaseModel):
    """收益趋势响应"""
    points: List[ProfitTrendPoint] = Field(default_factory=list, description="趋势数据点")
    period: str = Field(default="day", description="汇总周期")


# ==================== 按交易所收益 ====================

class ProfitByExchangeItem(BaseModel):
    """按交易所收益项"""
    exchange: str = Field(description="交易所代码")
    totalProfit: str = Field(description="总收益")
    totalFee: str = Field(description="总手续费")
    netProfit: str = Field(description="净收益")
    tradeCount: int = Field(description="成交笔数")


class ProfitByExchangeResponse(BaseModel):
    """按交易所收益响应"""
    list: List[ProfitByExchangeItem] = Field(default_factory=list)


# ==================== 按币种收益 ====================

class ProfitBySymbolItem(BaseModel):
    """按币种收益项"""
    symbol: str = Field(description="交易对")
    totalProfit: str = Field(description="总收益")
    totalFee: str = Field(description="总手续费")
    netProfit: str = Field(description="净收益")
    tradeCount: int = Field(description="成交笔数")


class ProfitBySymbolResponse(BaseModel):
    """按币种收益响应"""
    list: List[ProfitBySymbolItem] = Field(default_factory=list)


# ==================== 钱包余额 ====================

class WalletBalanceItem(BaseModel):
    """钱包余额项"""
    currency: str = Field(description="币种")
    available: str = Field(description="可用余额")
    frozen: str = Field(description="冻结余额")
    total: str = Field(description="总余额")
    eqUsd: str = Field(description="美元等值")


class WalletBalanceResponse(BaseModel):
    """钱包余额响应"""
    totalEqUsd: str = Field(description="账户总权益（美元）")
    balances: List[WalletBalanceItem] = Field(default_factory=list, description="各币种余额")
    exchange: str = Field(description="交易所")
    updatedAt: Optional[str] = Field(None, description="更新时间")
