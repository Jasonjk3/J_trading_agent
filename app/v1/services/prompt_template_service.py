#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/04
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
提示词模版服务
处理提示词模版的业务逻辑
"""
from typing import List, Optional, Tuple
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.crud import prompt_template_crud as crud
from app.v1.schemas.prompt_template_schema import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CategoryResponse,
    TemplateCreateRequest,
    TemplateUpdateRequest,
    TemplateResponse,
    PromptTemplateTypeEnum,
)
from models.inner_models.prompt_template_model import (
    PromptTemplateCategory,
    PromptTemplate,
    PromptTemplateType,
)
from models.inner_models.user_model import UserRole


class PromptTemplateService:
    """提示词模版服务"""

    # ========================================================================
    # 分类管理
    # ========================================================================

    async def get_categories(
        self,
        session: AsyncSession,
        is_active: Optional[bool] = True
    ) -> List[CategoryResponse]:
        """获取分类列表"""
        categories = await crud.get_categories(session, is_active)
        return [self._convert_category_to_response(cat) for cat in categories]

    async def get_category(
        self,
        session: AsyncSession,
        category_id: int
    ) -> Optional[CategoryResponse]:
        """获取单个分类"""
        category = await crud.get_category_by_id(session, category_id)
        if category:
            return self._convert_category_to_response(category)
        return None

    async def create_category(
        self,
        session: AsyncSession,
        user_id: str,
        request: CategoryCreateRequest
    ) -> CategoryResponse:
        """创建分类"""
        data = request.model_dump(exclude_unset=True)
        category = await crud.create_category(session, user_id, data)
        await session.commit()
        logger.info(f"用户 {user_id} 创建了分类: {category.name}")
        return self._convert_category_to_response(category)

    async def update_category(
        self,
        session: AsyncSession,
        category_id: int,
        request: CategoryUpdateRequest
    ) -> Optional[CategoryResponse]:
        """更新分类"""
        category = await crud.get_category_by_id(session, category_id)
        if not category:
            return None
        
        data = request.model_dump(exclude_unset=True)
        category = await crud.update_category(session, category, data)
        await session.commit()
        logger.info(f"更新了分类 {category_id}: {category.name}")
        return self._convert_category_to_response(category)

    async def delete_category(
        self,
        session: AsyncSession,
        category_id: int
    ) -> bool:
        """删除分类"""
        result = await crud.delete_category(session, category_id)
        if result:
            await session.commit()
            logger.info(f"删除了分类 {category_id}")
        return result

    # ========================================================================
    # 提示词模版管理
    # ========================================================================

    async def get_templates(
        self,
        session: AsyncSession,
        user_id: str,
        template_type: Optional[str] = None,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[TemplateResponse], int]:
        """获取提示词模版列表"""
        type_enum = None
        if template_type:
            type_enum = PromptTemplateType(template_type)
        
        templates, total = await crud.get_templates(
            session, user_id, type_enum, category_id, search, True, limit, offset
        )
        
        favorites = await crud.get_user_favorites(session, user_id)
        categories = await crud.get_categories(session)
        category_map = {cat.id: cat.name for cat in categories}
        
        responses = []
        for template in templates:
            resp = self._convert_template_to_response(
                template,
                category_name=category_map.get(template.category_id),
                is_favorited=template.id in favorites
            )
            responses.append(resp)
        
        return responses, total

    async def get_template(
        self,
        session: AsyncSession,
        template_id: int,
        user_id: str
    ) -> Optional[TemplateResponse]:
        """获取单个模版"""
        template = await crud.get_template_by_id(session, template_id)
        if not template or not template.is_active:
            return None
        
        if template.template_type == PromptTemplateType.PERSONAL and template.user_id != user_id:
            return None
        
        favorites = await crud.get_user_favorites(session, user_id)
        category = await crud.get_category_by_id(session, template.category_id) if template.category_id else None
        
        return self._convert_template_to_response(
            template,
            category_name=category.name if category else None,
            is_favorited=template.id in favorites
        )

    async def create_template(
        self,
        session: AsyncSession,
        user_id: str,
        user_role: UserRole,
        request: TemplateCreateRequest
    ) -> TemplateResponse:
        """创建提示词模版"""
        if request.template_type == PromptTemplateTypeEnum.PUBLIC and user_role != UserRole.ADMIN:
            raise PermissionError("只有管理员可以创建公共提示词")
        
        data = request.model_dump(exclude_unset=True)
        if "template_type" in data:
            data["template_type"] = PromptTemplateType(data["template_type"])
        
        template = await crud.create_template(session, user_id, data)
        await session.commit()
        
        category = await crud.get_category_by_id(session, template.category_id) if template.category_id else None
        
        logger.info(f"用户 {user_id} 创建了提示词模版: {template.title}")
        return self._convert_template_to_response(
            template,
            category_name=category.name if category else None,
            is_favorited=False
        )

    async def update_template(
        self,
        session: AsyncSession,
        template_id: int,
        user_id: str,
        user_role: UserRole,
        request: TemplateUpdateRequest
    ) -> Optional[TemplateResponse]:
        """更新提示词模版"""
        template = await crud.get_template_by_id(session, template_id)
        if not template:
            return None
        
        if template.template_type == PromptTemplateType.PUBLIC and user_role != UserRole.ADMIN:
            raise PermissionError("只有管理员可以编辑公共提示词")
        
        if template.template_type == PromptTemplateType.PERSONAL and template.user_id != user_id:
            raise PermissionError("只能编辑自己的个人提示词")
        
        data = request.model_dump(exclude_unset=True)
        template = await crud.update_template(session, template, data)
        await session.commit()
        
        favorites = await crud.get_user_favorites(session, user_id)
        category = await crud.get_category_by_id(session, template.category_id) if template.category_id else None
        
        logger.info(f"用户 {user_id} 更新了提示词模版 {template_id}")
        return self._convert_template_to_response(
            template,
            category_name=category.name if category else None,
            is_favorited=template.id in favorites
        )

    async def delete_template(
        self,
        session: AsyncSession,
        template_id: int,
        user_id: str,
        user_role: UserRole
    ) -> bool:
        """删除提示词模版"""
        template = await crud.get_template_by_id(session, template_id)
        if not template:
            return False
        
        if template.template_type == PromptTemplateType.PUBLIC and user_role != UserRole.ADMIN:
            raise PermissionError("只有管理员可以删除公共提示词")
        
        if template.template_type == PromptTemplateType.PERSONAL and template.user_id != user_id:
            raise PermissionError("只能删除自己的个人提示词")
        
        result = await crud.delete_template(session, template_id)
        if result:
            await session.commit()
            logger.info(f"用户 {user_id} 删除了提示词模版 {template_id}")
        return result

    async def use_template(
        self,
        session: AsyncSession,
        template_id: int,
        user_id: str
    ) -> bool:
        """使用模版（增加使用计数）"""
        template = await crud.get_template_by_id(session, template_id)
        if not template or not template.is_active:
            return False
        
        if template.template_type == PromptTemplateType.PERSONAL and template.user_id != user_id:
            return False
        
        result = await crud.increment_usage_count(session, template_id)
        if result:
            await session.commit()
        return result

    # ========================================================================
    # 收藏管理
    # ========================================================================

    async def get_favorites(
        self,
        session: AsyncSession,
        user_id: str,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[TemplateResponse], int]:
        """获取收藏的模版列表"""
        templates, total = await crud.get_favorited_templates(
            session, user_id, category_id, search, limit, offset
        )
        
        categories = await crud.get_categories(session)
        category_map = {cat.id: cat.name for cat in categories}
        
        responses = []
        for template in templates:
            resp = self._convert_template_to_response(
                template,
                category_name=category_map.get(template.category_id),
                is_favorited=True
            )
            responses.append(resp)
        
        return responses, total

    async def add_favorite(
        self,
        session: AsyncSession,
        user_id: str,
        template_id: int
    ) -> bool:
        """添加收藏"""
        template = await crud.get_template_by_id(session, template_id)
        if not template or not template.is_active:
            return False
        
        if template.template_type != PromptTemplateType.PUBLIC:
            return False
        
        existing = await crud.get_favorite(session, user_id, template_id)
        if existing:
            return True
        
        await crud.add_favorite(session, user_id, template_id)
        await session.commit()
        logger.info(f"用户 {user_id} 收藏了模版 {template_id}")
        return True

    async def remove_favorite(
        self,
        session: AsyncSession,
        user_id: str,
        template_id: int
    ) -> bool:
        """取消收藏"""
        result = await crud.remove_favorite(session, user_id, template_id)
        if result:
            await session.commit()
            logger.info(f"用户 {user_id} 取消收藏了模版 {template_id}")
        return result

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _convert_category_to_response(
        self,
        category: PromptTemplateCategory
    ) -> CategoryResponse:
        """转换分类模型为响应"""
        return CategoryResponse(
            id=category.id,
            name=category.name,
            description=category.description,
            icon=category.icon,
            sort_order=category.sort_order,
            is_active=category.is_active,
            created_by=category.created_by,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )

    def _convert_template_to_response(
        self,
        template: PromptTemplate,
        category_name: Optional[str] = None,
        is_favorited: bool = False
    ) -> TemplateResponse:
        """转换模版模型为响应"""
        return TemplateResponse(
            id=template.id,
            title=template.title,
            content=template.content,
            description=template.description,
            category_id=template.category_id,
            category_name=category_name,
            template_type=PromptTemplateTypeEnum(template.template_type.value),
            user_id=template.user_id,
            usage_count=template.usage_count,
            is_active=template.is_active,
            is_favorited=is_favorited,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
