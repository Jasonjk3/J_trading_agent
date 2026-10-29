#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/04
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
提示词模版数据库模型
包含：提示词分类、提示词模版、用户收藏
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Enum as SQLEnum, ForeignKey
from enum import Enum as PyEnum

from models.inner_models.base import Base


class PromptTemplateType(str, PyEnum):
    """提示词类型枚举"""
    PUBLIC = "public"      # 公共提示词
    PERSONAL = "personal"  # 个人提示词


class PromptTemplateCategory(Base):
    """提示词分类表"""
    __tablename__ = "prompt_template_categories"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="分类ID")
    name = Column(String(50), nullable=False, comment="分类名称")
    description = Column(String(255), nullable=True, comment="分类描述")
    icon = Column(String(50), nullable=True, comment="分类图标")
    sort_order = Column(Integer, default=0, nullable=False, comment="排序顺序")
    is_active = Column(Boolean, default=True, nullable=False, index=True, comment="是否启用")
    created_by = Column(String(36), nullable=False, comment="创建人ID")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def __repr__(self):
        return f"<PromptTemplateCategory(id={self.id}, name={self.name})>"


class PromptTemplate(Base):
    """提示词模版表"""
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="模版ID")
    title = Column(String(100), nullable=False, comment="模版标题")
    content = Column(Text, nullable=False, comment="模版内容")
    description = Column(String(500), nullable=True, comment="模版描述")
    category_id = Column(Integer, ForeignKey("prompt_template_categories.id"), nullable=True, index=True, comment="分类ID")
    template_type = Column(SQLEnum(PromptTemplateType, values_callable=lambda x: [e.value for e in x]), 
                          default=PromptTemplateType.PERSONAL, nullable=False, index=True, comment="模版类型")
    user_id = Column(String(36), nullable=False, index=True, comment="创建人ID（个人模版的所有者）")
    usage_count = Column(Integer, default=0, nullable=False, comment="使用次数")
    is_active = Column(Boolean, default=True, nullable=False, index=True, comment="是否启用")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment="更新时间")

    def __repr__(self):
        return f"<PromptTemplate(id={self.id}, title={self.title}, type={self.template_type})>"


class PromptTemplateFavorite(Base):
    """用户收藏的公共提示词表"""
    __tablename__ = "prompt_template_favorites"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="收藏ID")
    user_id = Column(String(36), nullable=False, index=True, comment="用户ID")
    template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=False, index=True, comment="模版ID")
    created_at = Column(DateTime, default=datetime.now, nullable=False, comment="收藏时间")

    def __repr__(self):
        return f"<PromptTemplateFavorite(id={self.id}, user_id={self.user_id}, template_id={self.template_id})>"
