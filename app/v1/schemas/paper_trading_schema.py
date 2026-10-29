#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模拟盘请求模型。"""
from typing import Literal

from pydantic import BaseModel, Field


class CreatePaperAccountRequest(BaseModel):
    agentId: str = Field(min_length=1, max_length=36)
    initialCapital: float = Field(default=200000, gt=0, le=1_000_000_000)


class CreatePaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    side: Literal["buy", "sell"]
    amount: float = Field(gt=0, le=1_000_000_000)
    price: float = Field(gt=0, le=1_000_000_000)


class CreatePaperDecisionRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    action: str = Field(min_length=1, max_length=20)
    title: str | None = Field(default=None, max_length=120)
    summary: str | None = None
    reasoning: str | None = None
    referencePrice: float | None = Field(default=None, gt=0)
    confidence: float | None = Field(default=None, ge=0, le=100)
    result: str | None = Field(default=None, max_length=50)
