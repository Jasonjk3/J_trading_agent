#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/19 12:00
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
消息数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, Index, JSON

from models.inner_models.base import Base


class MessageModel(Base):
    """消息表模型"""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    session_id = Column(String(36), nullable=False, index=True, comment="会话ID")
    user_id = Column(String(36), nullable=True, index=True, comment="用户ID，用于数据隔离")
    role = Column(String(20), nullable=False, comment="角色：user/assistant/system")
    content = Column(Text, nullable=False, comment="消息内容")
    images = Column(JSON, nullable=True, comment="图片列表（base64编码数组）")
    timestamp = Column(DateTime, default=datetime.now, index=True, comment="时间戳")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    # 创建复合索引
    __table_args__ = (
        Index('idx_session_timestamp', 'session_id', 'timestamp'),
        Index('idx_user_session', 'user_id', 'session_id'),
    )

    def __repr__(self):
        return f"<MessageModel(id={self.id}, session_id={self.session_id}, role={self.role})>"

