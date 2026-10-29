#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/11
# @Author : AI Assistant
"""
模型管理 API 路由
提供 AI 模型和 API 配置的统一管理接口
从 model_compare_api.py 中抽离，作为独立的公共模块
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.v1.schemas.model_management_schema import (
    ApiConfigCreate,
    ApiConfigUpdate,
    ApiConfigResponse,
    ModelCreate,
    ModelUpdate,
    ModelResponse,
    ModelTestRequest,
    ModelTestResponse,
    TagCreate,
    TagUpdate,
    TagResponse,
    TagListResponse,
)
from app.v1.services.model_compare_service import get_model_compare_service

# 创建路由器
router = APIRouter(prefix="/model-management", tags=["模型管理"])


# ============================================================================
# API 配置管理 API
# ============================================================================

@router.get("/api-configs", summary="获取API配置列表")
async def get_api_configs(
    provider: Optional[str] = Query(None, description="供应商筛选"),
    is_active: Optional[bool] = Query(None, description="状态筛选"),
    user_id: Optional[str] = Query(None, description="用户ID"),
    session: AsyncSession = Depends(get_db_session)
):
    """获取API配置列表"""
    try:
        service = get_model_compare_service()
        configs = await service.get_api_configs(
            session, provider=provider, is_active=is_active, user_id=user_id
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "items": [c.model_dump(mode='json') for c in configs],
                "total": len(configs)
            }
        )
    except Exception as e:
        logger.error(f"获取API配置列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/api-configs/{config_id}", summary="获取API配置详情")
async def get_api_config(
    config_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """获取单个API配置详情"""
    try:
        service = get_model_compare_service()
        config = await service.get_api_config(session, config_id)
        
        if not config:
            return ApiResponse.failed_response(
                msg="配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=config.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"获取API配置详情失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/api-configs", summary="创建API配置")
async def create_api_config(
    data: ApiConfigCreate,
    session: AsyncSession = Depends(get_db_session)
):
    """创建新的API配置"""
    try:
        # 转换为 model_compare 的 schema（字段兼容）
        from app.v1.schemas.model_compare_schema import ApiConfigCreate as MCApiConfigCreate
        mc_data = MCApiConfigCreate(**data.model_dump())
        
        service = get_model_compare_service()
        config = await service.create_api_config(session, mc_data)
        
        return ApiResponse.success_response(
            msg="创建成功",
            data=config.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"创建API配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/api-configs/{config_id}", summary="更新API配置")
async def update_api_config(
    config_id: int,
    data: ApiConfigUpdate,
    session: AsyncSession = Depends(get_db_session)
):
    """更新API配置"""
    try:
        from app.v1.schemas.model_compare_schema import ApiConfigUpdate as MCApiConfigUpdate
        mc_data = MCApiConfigUpdate(**data.model_dump())
        
        service = get_model_compare_service()
        config = await service.update_api_config(session, config_id, mc_data)
        
        if not config:
            return ApiResponse.failed_response(
                msg="配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="更新成功",
            data=config.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"更新API配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"更新失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/api-configs/{config_id}", summary="删除API配置")
async def delete_api_config(
    config_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """删除API配置"""
    try:
        service = get_model_compare_service()
        result = await service.delete_api_config(session, config_id)
        
        if not result:
            return ApiResponse.failed_response(
                msg="配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(msg="删除成功")
    except Exception as e:
        logger.error(f"删除API配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/api-configs/{config_id}/set-default", summary="设置默认API配置")
async def set_default_api_config(
    config_id: int,
    user_id: Optional[str] = Query(None, description="用户ID"),
    session: AsyncSession = Depends(get_db_session)
):
    """设置默认API配置"""
    try:
        service = get_model_compare_service()
        result = await service.set_default_api_config(session, config_id, user_id)
        
        if not result:
            return ApiResponse.failed_response(
                msg="配置不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(msg="设置成功")
    except Exception as e:
        logger.error(f"设置默认API配置失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"设置失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 模型管理 API
# ============================================================================

@router.get("/models", summary="获取管理的模型列表")
async def get_managed_models(
    provider: Optional[str] = Query(None, description="供应商筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    user_id: Optional[str] = Query(None, description="用户ID"),
    session: AsyncSession = Depends(get_db_session)
):
    """获取管理的模型列表"""
    try:
        service = get_model_compare_service()
        models = await service.get_managed_models(
            session, provider=provider, status=status, 
            is_active=is_active, user_id=user_id
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "items": [m.model_dump(mode='json') for m in models],
                "total": len(models)
            }
        )
    except Exception as e:
        logger.error(f"获取管理的模型列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/models/{model_id}", summary="获取管理的模型详情")
async def get_managed_model(
    model_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """获取单个管理的模型详情"""
    try:
        service = get_model_compare_service()
        model = await service.get_managed_model(session, model_id)
        
        if not model:
            return ApiResponse.failed_response(
                msg="模型不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=model.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"获取管理的模型详情失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/models", summary="创建管理的模型")
async def create_managed_model(
    data: ModelCreate,
    session: AsyncSession = Depends(get_db_session)
):
    """创建新的管理模型"""
    try:
        from app.v1.schemas.model_compare_schema import ModelManageCreate
        mc_data = ModelManageCreate(**data.model_dump())
        
        service = get_model_compare_service()
        model = await service.create_managed_model(session, mc_data)
        
        return ApiResponse.success_response(
            msg="创建成功",
            data=model.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"创建管理的模型失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/models/{model_id}", summary="更新管理的模型")
async def update_managed_model(
    model_id: int,
    data: ModelUpdate,
    session: AsyncSession = Depends(get_db_session)
):
    """更新管理的模型"""
    try:
        from app.v1.schemas.model_compare_schema import ModelManageUpdate
        mc_data = ModelManageUpdate(**data.model_dump())
        
        service = get_model_compare_service()
        model = await service.update_managed_model(session, model_id, mc_data)
        
        if not model:
            return ApiResponse.failed_response(
                msg="模型不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="更新成功",
            data=model.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"更新管理的模型失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"更新失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/models/{model_id}", summary="删除管理的模型")
async def delete_managed_model(
    model_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """删除管理的模型"""
    try:
        service = get_model_compare_service()
        result = await service.delete_managed_model(session, model_id)
        
        if not result:
            return ApiResponse.failed_response(
                msg="模型不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(msg="删除成功")
    except Exception as e:
        logger.error(f"删除管理的模型失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/models/test", summary="测试模型连通性")
async def test_models(
    data: ModelTestRequest,
    user_id: Optional[str] = Query(None, description="用户ID"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    测试模型连通性
    
    - 如果 model_ids 为空，则测试所有启用的模型
    - 返回每个模型的测试结果（状态、延迟、错误信息）
    """
    try:
        from app.v1.schemas.model_compare_schema import ModelTestRequest as MCModelTestRequest
        mc_data = MCModelTestRequest(**data.model_dump())
        
        service = get_model_compare_service()
        result = await service.test_models(session, mc_data, user_id)
        
        return ApiResponse.success_response(
            msg="测试完成",
            data=result.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"测试模型失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"测试失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 健康检查
# ============================================================================

# ============================================================================
# 标签管理 API
# ============================================================================

@router.get("/tags", summary="获取标签列表")
async def get_tags(
    is_active: Optional[bool] = Query(None, description="状态筛选"),
    session: AsyncSession = Depends(get_db_session)
):
    """获取标签列表"""
    try:
        service = get_model_compare_service()
        tags = await service.get_tags(session, is_active=is_active)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "items": tags,
                "total": len(tags)
            }
        )
    except Exception as e:
        logger.error(f"获取标签列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/tags/{tag_id}", summary="获取标签详情")
async def get_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """获取单个标签详情"""
    try:
        service = get_model_compare_service()
        tag = await service.get_tag(session, tag_id)
        
        if not tag:
            return ApiResponse.failed_response(
                msg="标签不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=tag
        )
    except Exception as e:
        logger.error(f"获取标签详情失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/tags", summary="创建标签")
async def create_tag(
    data: TagCreate,
    session: AsyncSession = Depends(get_db_session)
):
    """创建新标签"""
    try:
        service = get_model_compare_service()
        tag = await service.create_tag(session, data.model_dump())
        
        return ApiResponse.success_response(
            msg="创建成功",
            data=tag
        )
    except Exception as e:
        logger.error(f"创建标签失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/tags/{tag_id}", summary="更新标签")
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    session: AsyncSession = Depends(get_db_session)
):
    """更新标签"""
    try:
        service = get_model_compare_service()
        tag = await service.update_tag(session, tag_id, data.model_dump(exclude_unset=True))
        
        if not tag:
            return ApiResponse.failed_response(
                msg="标签不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="更新成功",
            data=tag
        )
    except Exception as e:
        logger.error(f"更新标签失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"更新失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/tags/{tag_id}", summary="删除标签")
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """删除标签"""
    try:
        service = get_model_compare_service()
        result = await service.delete_tag(session, tag_id)
        
        if not result:
            return ApiResponse.failed_response(
                msg="标签不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(msg="删除成功")
    except Exception as e:
        logger.error(f"删除标签失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/health", summary="健康检查")
async def health_check(
    session: AsyncSession = Depends(get_db_session)
):
    """模型管理服务健康检查"""
    try:
        service = get_model_compare_service()
        models = await service.get_managed_models(session, is_active=True)
        configs = await service.get_api_configs(session, is_active=True)
        
        available_models = len([m for m in models if m.status == "available"])
        
        return ApiResponse.success_response(
            msg="服务正常",
            data={
                "status": "healthy",
                "total_models": len(models),
                "available_models": available_models,
                "total_api_configs": len(configs)
            }
        )
    except Exception as e:
        logger.error(f"健康检查失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"健康检查失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
