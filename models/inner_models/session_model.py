#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 17:00
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
会话数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime, JSON, Boolean, Index
from sqlalchemy.dialects.mysql import JSON

from models.inner_models.base import Base


class SessionModel(Base):
    """会话表模型"""
    __tablename__ = "agent_sessions"

    session_id = Column(String(36), primary_key=True, comment="会话ID")
    user_id = Column(String(36), nullable=True, index=True, comment="用户ID")
    title = Column(String(200), nullable=True, comment="会话名称")
    context = Column(JSON, default=dict, comment="上下文信息")
    is_active = Column(Boolean, default=True, index=True, comment="是否活跃")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    expires_at = Column(DateTime, nullable=True, index=True, comment="过期时间")

    # 创建复合索引
    __table_args__ = (
        Index('idx_user_active', 'user_id', 'is_active'),
    )

    def __repr__(self):
        return f"<SessionModel(session_id={self.session_id}, user_id={self.user_id}, is_active={self.is_active})>"

