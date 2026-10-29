#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/04
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
提示词模版 API 路由
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from loguru import logger

from app.v1.schemas.prompt_template_schema import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CategoryResponse,
    CategoryListResponse,
    TemplateCreateRequest,
    TemplateUpdateRequest,
    TemplateResponse,
    TemplateListResponse,
    FavoriteRequest,
    UseTemplateRequest,
)
from app.v1.services.prompt_template_service import PromptTemplateService
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.database import get_db_session
from app.public.dependencies.auth import get_current_user
from models.inner_models.user_model import UserModel, UserRole

router = APIRouter(prefix="/prompt-templates", tags=["提示词模版"])

_service: Optional[PromptTemplateService] = None


def get_service() -> PromptTemplateService:
    """获取服务实例（单例）"""
    global _service
    if _service is None:
        _service = PromptTemplateService()
    return _service


# ============================================================================
# 分类管理
# ============================================================================

@router.get("/categories", summary="获取分类列表")
async def get_categories(
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """获取提示词分类列表"""
    try:
        categories = await service.get_categories(db_session)
        return ApiResponse.success_response(
            msg="获取分类列表成功",
            code=ResponseCode.OK.value,
            data={"categories": [cat.model_dump(mode='json') for cat in categories]}
        )
    except Exception as e:
        logger.error(f"获取分类列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取分类列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/categories", summary="创建分类")
async def create_category(
    request: CategoryCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """创建提示词分类（仅管理员）"""
    try:
        if current_user.role != UserRole.ADMIN:
            return ApiResponse.failed_response(
                msg="只有管理员可以创建分类",
                code=ResponseCode.AUTH_ERROR.value
            )
        
        category = await service.create_category(db_session, current_user.id, request)
        return ApiResponse.success_response(
            msg="创建分类成功",
            code=ResponseCode.OK.value,
            data=category.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"创建分类失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"创建分类失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/categories/{category_id}", summary="更新分类")
async def update_category(
    category_id: int,
    request: CategoryUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """更新提示词分类（仅管理员）"""
    try:
        if current_user.role != UserRole.ADMIN:
            return ApiResponse.failed_response(
                msg="只有管理员可以更新分类",
                code=ResponseCode.AUTH_ERROR.value
            )
        
        category = await service.update_category(db_session, category_id, request)
        if not category:
            return ApiResponse.failed_response(
                msg="分类不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        return ApiResponse.success_response(
            msg="更新分类成功",
            code=ResponseCode.OK.value,
            data=category.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"更新分类失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"更新分类失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/categories/{category_id}", summary="删除分类")
async def delete_category(
    category_id: int,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """删除提示词分类（仅管理员）"""
    try:
        if current_user.role != UserRole.ADMIN:
            return ApiResponse.failed_response(
                msg="只有管理员可以删除分类",
                code=ResponseCode.AUTH_ERROR.value
            )
        
        result = await service.delete_category(db_session, category_id)
        if not result:
            return ApiResponse.failed_response(
                msg="分类不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        return ApiResponse.success_response(
            msg="删除分类成功",
            code=ResponseCode.OK.value
        )
    except Exception as e:
        logger.error(f"删除分类失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除分类失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 提示词模版管理
# ============================================================================

@router.get("/templates", summary="获取提示词模版列表")
async def get_templates(
    template_type: Optional[str] = Query(None, description="模版类型: public/personal"),
    category_id: Optional[int] = Query(None, description="分类ID"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """获取提示词模版列表"""
    try:
        templates, total = await service.get_templates(
            db_session, current_user.id, template_type, category_id, search, limit, offset
        )
        return ApiResponse.success_response(
            msg="获取模版列表成功",
            code=ResponseCode.OK.value,
            data={
                "templates": [t.model_dump(mode='json') for t in templates],
                "total": total
            }
        )
    except Exception as e:
        logger.error(f"获取模版列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取模版列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/templates/{template_id}", summary="获取单个提示词模版")
async def get_template(
    template_id: int,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """获取单个提示词模版详情"""
    try:
        template = await service.get_template(db_session, template_id, current_user.id)
        if not template:
            return ApiResponse.failed_response(
                msg="模版不存在或无权访问",
                code=ResponseCode.NOT_FOUND.value
            )
        return ApiResponse.success_response(
            msg="获取模版成功",
            code=ResponseCode.OK.value,
            data=template.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"获取模版失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取模版失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/templates", summary="创建提示词模版")
async def create_template(
    request: TemplateCreateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """创建提示词模版"""
    try:
        template = await service.create_template(
            db_session, current_user.id, current_user.role, request
        )
        return ApiResponse.success_response(
            msg="创建模版成功",
            code=ResponseCode.OK.value,
            data=template.model_dump(mode='json')
        )
    except PermissionError as e:
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.AUTH_ERROR.value
        )
    except Exception as e:
        logger.error(f"创建模版失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"创建模版失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/templates/{template_id}", summary="更新提示词模版")
async def update_template(
    template_id: int,
    request: TemplateUpdateRequest,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """更新提示词模版"""
    try:
        template = await service.update_template(
            db_session, template_id, current_user.id, current_user.role, request
        )
        if not template:
            return ApiResponse.failed_response(
                msg="模版不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        return ApiResponse.success_response(
            msg="更新模版成功",
            code=ResponseCode.OK.value,
            data=template.model_dump(mode='json')
        )
    except PermissionError as e:
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.AUTH_ERROR.value
        )
    except Exception as e:
        logger.error(f"更新模版失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"更新模版失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/templates/{template_id}", summary="删除提示词模版")
async def delete_template(
    template_id: int,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """删除提示词模版"""
    try:
        result = await service.delete_template(
            db_session, template_id, current_user.id, current_user.role
        )
        if not result:
            return ApiResponse.failed_response(
                msg="模版不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        return ApiResponse.success_response(
            msg="删除模版成功",
            code=ResponseCode.OK.value
        )
    except PermissionError as e:
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.AUTH_ERROR.value
        )
    except Exception as e:
        logger.error(f"删除模版失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除模版失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/templates/{template_id}/use", summary="使用模版")
async def use_template(
    template_id: int,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """使用模版（增加使用计数）"""
    try:
        result = await service.use_template(db_session, template_id, current_user.id)
        if not result:
            return ApiResponse.failed_response(
                msg="模版不存在或无权访问",
                code=ResponseCode.NOT_FOUND.value
            )
        return ApiResponse.success_response(
            msg="使用模版成功",
            code=ResponseCode.OK.value
        )
    except Exception as e:
        logger.error(f"使用模版失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"使用模版失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 收藏管理
# ============================================================================

@router.get("/favorites", summary="获取收藏的模版列表")
async def get_favorites(
    category_id: Optional[int] = Query(None, description="分类ID"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, ge=1, le=500, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """获取用户收藏的模版列表"""
    try:
        templates, total = await service.get_favorites(
            db_session, current_user.id, category_id, search, limit, offset
        )
        return ApiResponse.success_response(
            msg="获取收藏列表成功",
            code=ResponseCode.OK.value,
            data={
                "templates": [t.model_dump(mode='json') for t in templates],
                "total": total
            }
        )
    except Exception as e:
        logger.error(f"获取收藏列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取收藏列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/favorites", summary="添加收藏")
async def add_favorite(
    request: FavoriteRequest,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """添加模版到收藏"""
    try:
        result = await service.add_favorite(db_session, current_user.id, request.template_id)
        if not result:
            return ApiResponse.failed_response(
                msg="模版不存在或只能收藏公共模版",
                code=ResponseCode.PARAM_ERROR.value
            )
        return ApiResponse.success_response(
            msg="收藏成功",
            code=ResponseCode.OK.value
        )
    except Exception as e:
        logger.error(f"添加收藏失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"添加收藏失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/favorites/{template_id}", summary="取消收藏")
async def remove_favorite(
    template_id: int,
    current_user: UserModel = Depends(get_current_user),
    service: PromptTemplateService = Depends(get_service),
    db_session = Depends(get_db_session)
):
    """取消收藏模版"""
    try:
        result = await service.remove_favorite(db_session, current_user.id, template_id)
        return ApiResponse.success_response(
            msg="取消收藏成功" if result else "未收藏该模版",
            code=ResponseCode.OK.value
        )
    except Exception as e:
        logger.error(f"取消收藏失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"取消收藏失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
