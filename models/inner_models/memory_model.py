#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
记忆数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, JSON, Index
from sqlalchemy.dialects.mysql import JSON

from models.inner_models.base import Base


class MemoryModel(Base):
    """记忆表模型"""
    __tablename__ = "agent_memories"
    
    memory_id = Column(String(36), primary_key=True, comment="记忆ID")
    agent_id = Column(String(36), nullable=False, index=True, comment="Agent ID")
    session_id = Column(String(36), nullable=True, index=True, comment="会话ID")
    user_id = Column(String(36), nullable=True, index=True, comment="用户ID")
    
    memory_type = Column(String(50), nullable=False, index=True, comment="记忆类型")
    content = Column(Text, nullable=False, comment="记忆内容")
    meta_data = Column(JSON, default=dict, comment="元数据")
    
    related_memories = Column(JSON, default=list, comment="关联的记忆ID列表")
    embedding = Column(JSON, nullable=True, comment="向量嵌入")
    
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    accessed_at = Column(DateTime, default=datetime.now, comment="最后访问时间")
    expires_at = Column(DateTime, nullable=True, index=True, comment="过期时间")
    
    importance_score = Column(Float, default=0.5, comment="重要性评分")
    access_count = Column(Integer, default=0, comment="访问次数")
    is_deleted = Column(Integer, default=0, index=True, comment="是否删除（软删除）")
    
    # 创建复合索引
    __table_args__ = (
        Index('idx_agent_session_type', 'agent_id', 'session_id', 'memory_type'),
        Index('idx_agent_type', 'agent_id', 'memory_type'),
        Index('idx_user_type', 'user_id', 'memory_type'),
        Index('idx_expires', 'expires_at', 'is_deleted'),
    )
    
    def __repr__(self):
        return f"<MemoryModel(memory_id={self.memory_id}, agent_id={self.agent_id}, memory_type={self.memory_type})>"

