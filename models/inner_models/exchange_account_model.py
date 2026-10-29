#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/09
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
交易所账户数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Enum as SQLEnum, Text
from enum import Enum as PyEnum

from models.inner_models.base import Base


class ExchangeCode(str, PyEnum):
    """交易所标识枚举"""
    OKX = "okx"


class BindStatus(str, PyEnum):
    """绑定/校验状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    NEVER = "never"


class ExchangeAccountModel(Base):
    """交易所账户表模型"""
    __tablename__ = "exchange_accounts"

    id = Column(String(36), primary_key=True, comment="账户ID")
    user_id = Column(String(36), nullable=False, index=True, comment="用户ID")
    exchange = Column(
        SQLEnum(ExchangeCode, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
        comment="交易所标识"
    )
    remark = Column(String(100), nullable=True, comment="备注名")
    api_key = Column(String(255), nullable=False, comment="API Key（加密存储）")
    api_secret = Column(Text, nullable=False, comment="API Secret（加密存储）")
    passphrase = Column(String(255), nullable=True, comment="Passphrase（加密存储，如OKX需要）")
    bind_status = Column(
        SQLEnum(BindStatus, values_callable=lambda x: [e.value for e in x]),
        default=BindStatus.NEVER,
        nullable=False,
        comment="绑定状态"
    )
    last_verified_at = Column(DateTime, nullable=True, comment="最后校验时间")
    enabled = Column(Boolean, default=True, nullable=False, index=True, comment="是否启用")
    read_only = Column(Boolean, default=False, nullable=False, comment="是否只读（仅查询，不交易）")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def __repr__(self):
        return f"<ExchangeAccountModel(id={self.id}, exchange={self.exchange}, user_id={self.user_id})>"

    def get_api_key_masked(self) -> str:
        """获取脱敏后的API Key"""
        if not self.api_key or len(self.api_key) < 8:
            return "****"
        return f"****{self.api_key[-4:]}"
    
    @property
    def has_passphrase(self) -> bool:
        """是否有Passphrase"""
        return bool(self.passphrase)
