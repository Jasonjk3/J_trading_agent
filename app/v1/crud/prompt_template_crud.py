#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/04
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
提示词模版 CRUD 操作
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.prompt_template_model import (
    PromptTemplateCategory,
    PromptTemplate,
    PromptTemplateFavorite,
    PromptTemplateType,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 分类 CRUD
# ============================================================================

async def get_categories(
    session: AsyncSession,
    is_active: Optional[bool] = True
) -> List[PromptTemplateCategory]:
    """获取分类列表"""
    conditions = []
    if is_active is not None:
        conditions.append(PromptTemplateCategory.is_active == is_active)
    
    query = select(PromptTemplateCategory)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(PromptTemplateCategory.sort_order, PromptTemplateCategory.id)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_category_by_id(
    session: AsyncSession,
    category_id: int
) -> Optional[PromptTemplateCategory]:
    """根据ID获取分类"""
    query = select(PromptTemplateCategory).where(PromptTemplateCategory.id == category_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_category(
    session: AsyncSession,
    user_id: str,
    data: Dict[str, Any]
) -> PromptTemplateCategory:
    """创建分类"""
    category = PromptTemplateCategory(
        name=data["name"],
        description=data.get("description"),
        icon=data.get("icon"),
        sort_order=data.get("sort_order", 0),
        created_by=user_id,
    )
    session.add(category)
    await session.flush()
    await session.refresh(category)
    return category


async def update_category(
    session: AsyncSession,
    category: PromptTemplateCategory,
    data: Dict[str, Any]
) -> PromptTemplateCategory:
    """更新分类"""
    for key, value in data.items():
        if value is not None and hasattr(category, key):
            setattr(category, key, value)
    category.updated_at = datetime.now()
    await session.flush()
    await session.refresh(category)
    return category


async def delete_category(
    session: AsyncSession,
    category_id: int
) -> bool:
    """删除分类（软删除）"""
    category = await get_category_by_id(session, category_id)
    if category:
        category.is_active = False
        category.updated_at = datetime.now()
        await session.flush()
        return True
    return False


# ============================================================================
# 提示词模版 CRUD
# ============================================================================

async def get_templates(
    session: AsyncSession,
    user_id: str,
    template_type: Optional[PromptTemplateType] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    is_active: bool = True,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[PromptTemplate], int]:
    """获取提示词模版列表"""
    conditions = [PromptTemplate.is_active == is_active]
    
    if template_type == PromptTemplateType.PUBLIC:
        conditions.append(PromptTemplate.template_type == PromptTemplateType.PUBLIC)
    elif template_type == PromptTemplateType.PERSONAL:
        conditions.append(PromptTemplate.template_type == PromptTemplateType.PERSONAL)
        conditions.append(PromptTemplate.user_id == user_id)
    else:
        conditions.append(
            or_(
                PromptTemplate.template_type == PromptTemplateType.PUBLIC,
                and_(
                    PromptTemplate.template_type == PromptTemplateType.PERSONAL,
                    PromptTemplate.user_id == user_id
                )
            )
        )
    
    if category_id is not None:
        conditions.append(PromptTemplate.category_id == category_id)
    
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                PromptTemplate.title.ilike(search_pattern),
                PromptTemplate.content.ilike(search_pattern),
                PromptTemplate.description.ilike(search_pattern)
            )
        )
    
    count_query = select(func.count(PromptTemplate.id)).where(and_(*conditions))
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    
    query = select(PromptTemplate).where(and_(*conditions))
    query = query.order_by(desc(PromptTemplate.usage_count), desc(PromptTemplate.created_at))
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all()), total


async def get_template_by_id(
    session: AsyncSession,
    template_id: int
) -> Optional[PromptTemplate]:
    """根据ID获取模版"""
    query = select(PromptTemplate).where(PromptTemplate.id == template_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_template(
    session: AsyncSession,
    user_id: str,
    data: Dict[str, Any]
) -> PromptTemplate:
    """创建提示词模版"""
    template = PromptTemplate(
        title=data["title"],
        content=data["content"],
        description=data.get("description"),
        category_id=data.get("category_id"),
        template_type=data.get("template_type", PromptTemplateType.PERSONAL),
        user_id=user_id,
    )
    session.add(template)
    await session.flush()
    await session.refresh(template)
    return template


async def update_template(
    session: AsyncSession,
    template: PromptTemplate,
    data: Dict[str, Any]
) -> PromptTemplate:
    """更新提示词模版"""
    for key, value in data.items():
        if value is not None and hasattr(template, key):
            setattr(template, key, value)
    template.updated_at = datetime.now()
    await session.flush()
    await session.refresh(template)
    return template


async def delete_template(
    session: AsyncSession,
    template_id: int
) -> bool:
    """删除模版（软删除）"""
    template = await get_template_by_id(session, template_id)
    if template:
        template.is_active = False
        template.updated_at = datetime.now()
        await session.flush()
        return True
    return False


async def increment_usage_count(
    session: AsyncSession,
    template_id: int
) -> bool:
    """增加使用次数"""
    template = await get_template_by_id(session, template_id)
    if template:
        template.usage_count += 1
        await session.flush()
        return True
    return False


# ============================================================================
# 收藏 CRUD
# ============================================================================

async def get_user_favorites(
    session: AsyncSession,
    user_id: str
) -> List[int]:
    """获取用户收藏的模版ID列表"""
    query = select(PromptTemplateFavorite.template_id).where(
        PromptTemplateFavorite.user_id == user_id
    )
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def get_favorite(
    session: AsyncSession,
    user_id: str,
    template_id: int
) -> Optional[PromptTemplateFavorite]:
    """获取收藏记录"""
    query = select(PromptTemplateFavorite).where(
        and_(
            PromptTemplateFavorite.user_id == user_id,
            PromptTemplateFavorite.template_id == template_id
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def add_favorite(
    session: AsyncSession,
    user_id: str,
    template_id: int
) -> PromptTemplateFavorite:
    """添加收藏"""
    favorite = PromptTemplateFavorite(
        user_id=user_id,
        template_id=template_id,
    )
    session.add(favorite)
    await session.flush()
    await session.refresh(favorite)
    return favorite


async def remove_favorite(
    session: AsyncSession,
    user_id: str,
    template_id: int
) -> bool:
    """取消收藏"""
    favorite = await get_favorite(session, user_id, template_id)
    if favorite:
        await session.delete(favorite)
        await session.flush()
        return True
    return False


async def get_favorited_templates(
    session: AsyncSession,
    user_id: str,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> Tuple[List[PromptTemplate], int]:
    """获取用户收藏的模版列表"""
    subquery = select(PromptTemplateFavorite.template_id).where(
        PromptTemplateFavorite.user_id == user_id
    ).subquery()
    
    conditions = [
        PromptTemplate.id.in_(select(subquery)),
        PromptTemplate.is_active == True
    ]
    
    if category_id is not None:
        conditions.append(PromptTemplate.category_id == category_id)
    
    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                PromptTemplate.title.ilike(search_pattern),
                PromptTemplate.content.ilike(search_pattern),
                PromptTemplate.description.ilike(search_pattern)
            )
        )
    
    count_query = select(func.count(PromptTemplate.id)).where(and_(*conditions))
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    
    query = select(PromptTemplate).where(and_(*conditions))
    query = query.order_by(desc(PromptTemplate.created_at))
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    return list(result.scalars().all()), total
