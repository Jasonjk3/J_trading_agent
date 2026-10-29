#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/04
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
提示词模版 Schema 定义
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class PromptTemplateTypeEnum(str, Enum):
    """提示词类型"""
    PUBLIC = "public"
    PERSONAL = "personal"


# ============================================================================
# 分类相关 Schema
# ============================================================================

class CategoryCreateRequest(BaseModel):
    """创建分类请求"""
    name: str = Field(..., description="分类名称", min_length=1, max_length=50)
    description: Optional[str] = Field(None, description="分类描述", max_length=255)
    icon: Optional[str] = Field(None, description="分类图标", max_length=50)
    sort_order: int = Field(0, description="排序顺序")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "数据生成",
                "description": "用于生成测试数据的提示词",
                "icon": "database",
                "sort_order": 1
            }
        }


class CategoryUpdateRequest(BaseModel):
    """更新分类请求"""
    name: Optional[str] = Field(None, description="分类名称", min_length=1, max_length=50)
    description: Optional[str] = Field(None, description="分类描述", max_length=255)
    icon: Optional[str] = Field(None, description="分类图标", max_length=50)
    sort_order: Optional[int] = Field(None, description="排序顺序")
    is_active: Optional[bool] = Field(None, description="是否启用")


class CategoryResponse(BaseModel):
    """分类响应"""
    id: int = Field(..., description="分类ID")
    name: str = Field(..., description="分类名称")
    description: Optional[str] = Field(None, description="分类描述")
    icon: Optional[str] = Field(None, description="分类图标")
    sort_order: int = Field(0, description="排序顺序")
    is_active: bool = Field(True, description="是否启用")
    created_by: str = Field(..., description="创建人ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


# ============================================================================
# 提示词模版相关 Schema
# ============================================================================

class TemplateCreateRequest(BaseModel):
    """创建提示词模版请求"""
    title: str = Field(..., description="模版标题", min_length=1, max_length=100)
    content: str = Field(..., description="模版内容", min_length=1)
    description: Optional[str] = Field(None, description="模版描述", max_length=500)
    category_id: Optional[int] = Field(None, description="分类ID")
    template_type: PromptTemplateTypeEnum = Field(PromptTemplateTypeEnum.PERSONAL, description="模版类型")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "生成用户测试数据",
                "content": "请为用户表生成10条测试数据，包含用户名、邮箱、手机号等字段，数据要符合中国用户的特点。",
                "description": "用于快速生成用户相关的测试数据",
                "category_id": 1,
                "template_type": "public"
            }
        }


class TemplateUpdateRequest(BaseModel):
    """更新提示词模版请求"""
    title: Optional[str] = Field(None, description="模版标题", min_length=1, max_length=100)
    content: Optional[str] = Field(None, description="模版内容", min_length=1)
    description: Optional[str] = Field(None, description="模版描述", max_length=500)
    category_id: Optional[int] = Field(None, description="分类ID")
    is_active: Optional[bool] = Field(None, description="是否启用")


class TemplateResponse(BaseModel):
    """提示词模版响应"""
    id: int = Field(..., description="模版ID")
    title: str = Field(..., description="模版标题")
    content: str = Field(..., description="模版内容")
    description: Optional[str] = Field(None, description="模版描述")
    category_id: Optional[int] = Field(None, description="分类ID")
    category_name: Optional[str] = Field(None, description="分类名称")
    template_type: PromptTemplateTypeEnum = Field(..., description="模版类型")
    user_id: str = Field(..., description="创建人ID")
    usage_count: int = Field(0, description="使用次数")
    is_active: bool = Field(True, description="是否启用")
    is_favorited: bool = Field(False, description="是否已收藏（仅公共模版）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class TemplateListResponse(BaseModel):
    """提示词模版列表响应"""
    templates: List[TemplateResponse] = Field(default_factory=list, description="模版列表")
    total: int = Field(0, description="总数")


class CategoryListResponse(BaseModel):
    """分类列表响应"""
    categories: List[CategoryResponse] = Field(default_factory=list, description="分类列表")


class FavoriteRequest(BaseModel):
    """收藏/取消收藏请求"""
    template_id: int = Field(..., description="模版ID")


class UseTemplateRequest(BaseModel):
    """使用模版请求（用于统计使用次数）"""
    template_id: int = Field(..., description="模版ID")
