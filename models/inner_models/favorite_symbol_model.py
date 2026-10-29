#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
自选交易对数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Index

from models.inner_models.base import Base


class FavoriteSymbolModel(Base):
    """自选交易对表模型"""
    __tablename__ = "favorite_symbols"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增ID")
    user_id = Column(String(36), nullable=False, index=True, comment="用户ID")
    symbol = Column(String(50), nullable=False, comment="交易对，如 BTC-USDT")
    name = Column(String(20), nullable=True, comment="显示名称，如 BTC")
    sort_order = Column(Integer, default=0, nullable=False, comment="排序顺序")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")

    __table_args__ = (
        Index('ix_favorite_symbols_user_symbol', 'user_id', 'symbol', unique=True),
    )

    def __repr__(self):
        return f"<FavoriteSymbolModel(id={self.id}, user_id={self.user_id}, symbol={self.symbol})>"

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "sortOrder": self.sort_order,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
