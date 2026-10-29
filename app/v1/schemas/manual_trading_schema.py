#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
手工实盘交易相关 Schema
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


InstrumentType = Literal["SPOT", "SWAP"]
OrderType = Literal["market", "limit"]
TradeAction = Literal["buy", "sell", "open_long", "open_short", "close_long", "close_short"]
TradeMode = Literal["cash", "cross", "isolated"]


class TradingInstrumentItem(BaseModel):
    """可交易产品"""

    instId: str = Field(..., description="产品ID，如 BTC-USDT 或 BTC-USDT-SWAP")
    instType: str = Field(..., description="产品类型")
    baseCcy: Optional[str] = Field(None, description="基础币种")
    quoteCcy: Optional[str] = Field(None, description="计价币种")
    settleCcy: Optional[str] = Field(None, description="结算币种")
    tickSz: Optional[str] = Field(None, description="价格精度")
    lotSz: Optional[str] = Field(None, description="下单数量精度")
    minSz: Optional[str] = Field(None, description="最小下单数量")
    state: Optional[str] = Field(None, description="交易状态")


class TradingInstrumentListResponse(BaseModel):
    """产品列表响应"""

    list: List[TradingInstrumentItem]


class TradingTicker(BaseModel):
    """交易面板行情摘要"""

    instId: str = Field(..., description="产品ID")
    last: str = Field(default="0", description="最新价")
    askPx: str = Field(default="0", description="卖一价")
    bidPx: str = Field(default="0", description="买一价")
    high24h: str = Field(default="0", description="24小时最高价")
    low24h: str = Field(default="0", description="24小时最低价")
    change24h: str = Field(default="0", description="24小时涨跌幅（百分比）")
    vol24h: Optional[str] = Field(None, description="24小时成交量")
    ts: Optional[str] = Field(None, description="时间戳")


class OrderBookLevel(BaseModel):
    """盘口档位"""

    price: str = Field(..., description="价格")
    size: str = Field(..., description="数量")


class TradingSnapshotResponse(BaseModel):
    """交易快照响应"""

    ticker: TradingTicker
    bids: List[OrderBookLevel] = Field(default_factory=list)
    asks: List[OrderBookLevel] = Field(default_factory=list)


class TradingBalanceItem(BaseModel):
    """账户余额项"""

    ccy: str = Field(..., description="币种")
    availBal: str = Field(default="0", description="可用余额")
    frozenBal: str = Field(default="0", description="冻结余额")
    eq: str = Field(default="0", description="总权益")
    eqUsd: str = Field(default="0", description="美元估值")


class TradingPositionItem(BaseModel):
    """账户持仓项"""

    instId: str = Field(..., description="产品ID")
    instType: Optional[str] = Field(None, description="产品类型")
    posSide: str = Field(default="net", description="持仓方向")
    pos: str = Field(default="0", description="持仓数量")
    availPos: Optional[str] = Field(None, description="可平仓数量")
    avgPx: Optional[str] = Field(None, description="开仓均价")
    markPx: Optional[str] = Field(None, description="标记价格")
    upl: Optional[str] = Field(None, description="未实现盈亏")
    lever: Optional[str] = Field(None, description="杠杆倍数")
    mgnMode: Optional[str] = Field(None, description="保证金模式")


class TradingAccountOverviewResponse(BaseModel):
    """账户总览响应"""

    balances: List[TradingBalanceItem] = Field(default_factory=list)
    positions: List[TradingPositionItem] = Field(default_factory=list)


class PendingOrderItem(BaseModel):
    """未成交委托"""

    ordId: str = Field(..., description="订单ID")
    instId: str = Field(..., description="产品ID")
    side: str = Field(..., description="买卖方向")
    ordType: str = Field(..., description="订单类型")
    px: Optional[str] = Field(None, description="委托价")
    sz: str = Field(default="0", description="委托数量")
    accFillSz: str = Field(default="0", description="已成交数量")
    state: str = Field(default="live", description="订单状态")
    posSide: Optional[str] = Field(None, description="持仓方向")
    cTime: Optional[str] = Field(None, description="创建时间")


class PendingOrderListResponse(BaseModel):
    """未成交订单列表响应"""

    list: List[PendingOrderItem] = Field(default_factory=list)


class PlaceManualOrderRequest(BaseModel):
    """手工下单请求"""

    accountId: str = Field(..., description="交易所账户ID")
    instId: str = Field(..., description="产品ID")
    instType: InstrumentType = Field(..., description="产品类型")
    tradeAction: TradeAction = Field(..., description="交易动作")
    ordType: OrderType = Field(..., description="订单类型")
    sz: str = Field(..., description="委托数量")
    px: Optional[str] = Field(None, description="限价单价格")
    tdMode: Optional[TradeMode] = Field(None, description="交易模式：cash/cross/isolated")
    leverage: Optional[str] = Field(None, description="杠杆倍数，仅合约场景使用")
    tgtCcy: Optional[Literal["base_ccy", "quote_ccy"]] = Field(None, description="市价单数量单位")


class PlaceManualOrderResponse(BaseModel):
    """手工下单响应"""

    ordId: Optional[str] = Field(None, description="订单ID")
    clOrdId: Optional[str] = Field(None, description="自定义订单ID")
    sCode: Optional[str] = Field(None, description="结果码")
    sMsg: Optional[str] = Field(None, description="结果信息")


class CancelManualOrderRequest(BaseModel):
    """手工撤单请求"""

    accountId: str = Field(..., description="交易所账户ID")
    instId: str = Field(..., description="产品ID")
    ordId: str = Field(..., description="订单ID")


class CancelManualOrderResponse(BaseModel):
    """手工撤单响应"""

    ordId: Optional[str] = Field(None, description="订单ID")
    clOrdId: Optional[str] = Field(None, description="自定义订单ID")
    sCode: Optional[str] = Field(None, description="结果码")
    sMsg: Optional[str] = Field(None, description="结果信息")
