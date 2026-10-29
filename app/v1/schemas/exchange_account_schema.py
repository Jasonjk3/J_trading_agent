#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
交易所账户相关 Schema
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from models.inner_models.exchange_account_model import ExchangeCode, BindStatus


class ExchangeAccountListParams(BaseModel):
    """列表查询参数"""
    exchange: Optional[ExchangeCode] = Field(None, description="交易所标识")
    enabled: Optional[bool] = Field(None, description="是否启用")
    bind_status: Optional[BindStatus] = Field(None, description="绑定状态")


class ExchangeAccountListItem(BaseModel):
    """交易所配置列表项"""
    id: str = Field(..., description="账户ID")
    exchange: ExchangeCode = Field(..., description="交易所标识")
    remark: Optional[str] = Field(None, description="备注名")
    bindStatus: BindStatus = Field(..., description="绑定状态")
    lastVerifiedAt: Optional[str] = Field(None, description="最后校验时间")
    enabled: bool = Field(..., description="是否启用")
    readOnly: Optional[bool] = Field(None, description="是否只读")
    apiKeyMasked: Optional[str] = Field(None, description="脱敏后的API Key")
    hasPassphrase: Optional[bool] = Field(None, description="是否需要Passphrase")
    createdAt: str = Field(..., description="创建时间")
    updatedAt: Optional[str] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class ExchangeAccountListResponse(BaseModel):
    """列表响应"""
    list: List[ExchangeAccountListItem] = Field(..., description="配置列表")
    total: int = Field(..., description="总数")


class CreateExchangeAccountRequest(BaseModel):
    """创建交易所配置请求"""
    exchange: ExchangeCode = Field(..., description="交易所标识")
    apiKey: str = Field(..., description="API Key", min_length=1, max_length=255)
    apiSecret: str = Field(..., description="API Secret", min_length=1)
    passphrase: Optional[str] = Field(None, description="Passphrase（OKX等需要）", max_length=255)
    remark: Optional[str] = Field(None, description="备注名", max_length=100)
    readOnly: Optional[bool] = Field(False, description="是否只读")
    enabled: Optional[bool] = Field(True, description="是否启用")

    class Config:
        json_schema_extra = {
            "example": {
                "exchange": "okx",
                "apiKey": "your-api-key",
                "apiSecret": "your-api-secret",
                "passphrase": "your-passphrase",
                "remark": "主账户",
                "readOnly": False,
                "enabled": True
            }
        }


class UpdateExchangeAccountRequest(BaseModel):
    """更新交易所配置请求"""
    apiKey: Optional[str] = Field(None, description="API Key", max_length=255)
    apiSecret: Optional[str] = Field(None, description="API Secret")
    passphrase: Optional[str] = Field(None, description="Passphrase", max_length=255)
    remark: Optional[str] = Field(None, description="备注名", max_length=100)
    readOnly: Optional[bool] = Field(None, description="是否只读")
    enabled: Optional[bool] = Field(None, description="是否启用")

    class Config:
        json_schema_extra = {
            "example": {
                "remark": "更新后的备注",
                "enabled": True
            }
        }


class VerifyResult(BaseModel):
    """校验连接响应"""
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="消息")
