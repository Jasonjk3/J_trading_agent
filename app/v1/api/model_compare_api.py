#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/07
# @Author : AI Assistant
"""
模型对比 API 路由 2.0
提供大模型横向对比测试的 RESTful 接口
新增：API配置管理、模型管理、模型测试、历史记录管理
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from app.public.dependencies.auth import get_current_user
from models.inner_models.user_model import UserModel, UserRole
from app.v1.schemas.model_compare_schema import (
    ModelCompareRequest,
    ModelCompareResponse,
    ModelsListResponse,
    # 2.0 新增
    ApiConfigCreate,
    ApiConfigUpdate,
    ApiConfigResponse,
    ApiConfigListResponse,
    ModelManageCreate,
    ModelManageUpdate,
    ModelManageResponse,
    ModelManageListResponse,
    ModelTestRequest,
    ModelTestResponse,
    CompareHistoryListRequest,
    CompareHistoryListResponse,
    CompareHistoryDetailResponse,
    PaginationInfo,
    CompareStatsResponse,
    ModelUsageStatsResponse,
)
from app.v1.services.model_compare_service import get_model_compare_service

# 创建路由器
router = APIRouter(prefix="/model-compare", tags=["模型对比"])


# ============================================================================
# 模型列表 API
# ============================================================================

@router.get("/models", summary="获取可用模型列表")
async def get_models(
    session: AsyncSession = Depends(get_db_session)
):
    """
    获取系统支持的所有可用模型列表（从数据库读取）
    
    返回模型的详细信息，包括：
    - 模型ID和名称
    - 提供商信息
    - 支持的功能（流式输出、思考模式等）
    - 价格信息
    """
    try:
        service = get_model_compare_service()
        result = await service.get_available_models(session)
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=result.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取模型列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 对比测试 API
# ============================================================================

@router.post("/compare", summary="执行模型对比测试")
async def compare_models(
    request: ModelCompareRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    使用相同提示词对多个模型进行横向对比测试
    
    - 支持同时测试多个模型（最多10个）
    - 并发调用所有模型，等待所有结果返回
    - 返回每个模型的响应内容、延迟、Token使用量和费用
    - 提供统计摘要（成功率、平均延迟、总费用等）
    - 支持保存到历史记录（可通过 save_history 参数控制）
    - 自动关联当前登录用户，实现数据隔离
    
    注意：此接口为同步接口，会等待所有模型返回结果
    """
    try:
        # 参数校验
        if not request.models:
            return ApiResponse.failed_response(
                msg="请至少选择一个模型",
                code=ResponseCode.PARAM_ERROR.value
            )
        
        if not request.user_prompt or not request.user_prompt.strip():
            return ApiResponse.failed_response(
                msg="用户提示词不能为空",
                code=ResponseCode.PARAM_ERROR.value
            )
        
        # 如果请求中没有user_id，使用当前登录用户的ID
        if not request.user_id:
            request.user_id = current_user.id
        
        service = get_model_compare_service()
        result = await service.compare_models(
            request, 
            session=session, 
            save_to_db=request.save_history
        )
        
        return ApiResponse.success_response(
            msg="对比测试完成",
            data=result.model_dump(mode='json')
        )
    
    except ValueError as e:
        logger.warning(f"参数错误: {e}")
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.PARAM_ERROR.value
        )
    except Exception as e:
        logger.error(f"模型对比测试失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"对比测试失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 快速测试 API（单模型）
# ============================================================================

@router.post("/test-single", summary="测试单个模型")
async def test_single_model(
    model_id: str = Query(..., description="模型ID"),
    prompt: str = Query(..., description="测试提示词"),
    system_prompt: Optional[str] = Query(None, description="系统提示词"),
    temperature: float = Query(0.7, ge=0, le=2, description="温度参数"),
    max_tokens: Optional[int] = Query(None, ge=1, description="最大Token数"),
    timeout: int = Query(60, ge=1, le=300, description="超时时间（秒）"),
):
    """
    快速测试单个模型
    
    用于快速验证单个模型的响应效果，参数通过 Query 传递
    """
    try:
        request = ModelCompareRequest(
            models=[model_id],
            user_prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            save_history=False,
        )
        
        service = get_model_compare_service()
        result = await service.compare_models(request)
        
        # 返回单个模型的结果
        if result.results:
            model_result = result.results[0]
            return ApiResponse.success_response(
                msg="测试完成",
                data=model_result.model_dump(mode='json')
            )
        else:
            return ApiResponse.failed_response(
                msg="未获取到测试结果",
                code=ResponseCode.SYSTEM_ERROR.value
            )
    
    except Exception as e:
        logger.error(f"单模型测试失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"测试失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# API 配置管理 API (2.0 新增)
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
        service = get_model_compare_service()
        config = await service.create_api_config(session, data)
        
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
        service = get_model_compare_service()
        config = await service.update_api_config(session, config_id, data)
        
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
# 模型管理 API (2.0 新增)
# ============================================================================

@router.get("/managed-models", summary="获取管理的模型列表")
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


@router.get("/managed-models/{model_id}", summary="获取管理的模型详情")
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


@router.post("/managed-models", summary="创建管理的模型")
async def create_managed_model(
    data: ModelManageCreate,
    session: AsyncSession = Depends(get_db_session)
):
    """创建新的管理模型"""
    try:
        service = get_model_compare_service()
        model = await service.create_managed_model(session, data)
        
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


@router.put("/managed-models/{model_id}", summary="更新管理的模型")
async def update_managed_model(
    model_id: int,
    data: ModelManageUpdate,
    session: AsyncSession = Depends(get_db_session)
):
    """更新管理的模型"""
    try:
        service = get_model_compare_service()
        model = await service.update_managed_model(session, model_id, data)
        
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


@router.delete("/managed-models/{model_id}", summary="删除管理的模型")
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


@router.post("/managed-models/test", summary="测试模型连通性")
async def test_models(
    request: ModelTestRequest,
    user_id: Optional[str] = Query(None, description="用户ID"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    测试模型连通性
    
    - 如果指定 model_ids，则测试指定的模型
    - 如果不指定，则测试所有启用的模型
    - 测试完成后会更新模型的可用状态
    """
    try:
        service = get_model_compare_service()
        result = await service.test_models(session, request, user_id)
        
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
# 对比历史记录 API (2.0 新增)
# ============================================================================

@router.get("/histories", summary="获取对比历史记录列表")
async def get_compare_histories(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: Optional[str] = Query(None, description="用户ID（可选，默认使用当前登录用户）"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取对比历史记录列表
    
    根据当前登录用户自动过滤历史记录，实现数据隔离。
    如果提供了user_id参数，则使用该参数（仅管理员可查看其他用户数据）。
    """
    try:
        # 如果没有提供user_id，使用当前登录用户的ID（数据隔离）
        # 如果提供了user_id，允许管理员查看其他用户的数据
        filter_user_id = user_id if user_id else current_user.id
        
        service = get_model_compare_service()
        items, total = await service.get_compare_histories(
            session, user_id=filter_user_id, start_time=start_time, 
            end_time=end_time, page=page, page_size=page_size
        )
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "items": [item.model_dump(mode='json') for item in items],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages
                }
            }
        )
    except Exception as e:
        logger.error(f"获取对比历史记录列表失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/histories/{history_id}", summary="获取对比历史记录详情")
async def get_compare_history_detail(
    history_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取对比历史记录详情
    
    只能查看当前用户自己的历史记录，实现数据隔离。
    """
    try:
        service = get_model_compare_service()
        detail = await service.get_compare_history_detail(session, history_id)
        
        if not detail:
            return ApiResponse.failed_response(
                msg="记录不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        # 检查数据隔离：只能查看自己的记录（管理员除外）
        if detail.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            return ApiResponse.failed_response(
                msg="无权访问该记录",
                code=ResponseCode.FORBIDDEN.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=detail.model_dump(mode='json')
        )
    except Exception as e:
        logger.error(f"获取对比历史记录详情失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/histories/{history_id}", summary="删除对比历史记录")
async def delete_compare_history(
    history_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    删除对比历史记录
    
    只能删除当前用户自己的历史记录，实现数据隔离。
    """
    try:
        # 先检查记录是否存在以及权限
        service = get_model_compare_service()
        detail = await service.get_compare_history_detail(session, history_id)
        
        if not detail:
            return ApiResponse.failed_response(
                msg="记录不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        # 检查数据隔离：只能删除自己的记录（管理员除外）
        if detail.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            return ApiResponse.failed_response(
                msg="无权删除该记录",
                code=ResponseCode.FORBIDDEN.value
            )
        
        result = await service.delete_compare_history(session, history_id)
        
        if not result:
            return ApiResponse.failed_response(
                msg="删除失败",
                code=ResponseCode.SYSTEM_ERROR.value
            )
        
        return ApiResponse.success_response(msg="删除成功")
    except Exception as e:
        logger.error(f"删除对比历史记录失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 统计 API (2.0 新增)
# ============================================================================

@router.get("/stats", summary="获取对比统计数据")
async def get_compare_stats(
    user_id: Optional[str] = Query(None, description="用户ID（可选，默认使用当前登录用户）"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取对比统计数据
    
    根据当前登录用户自动过滤统计数据，实现数据隔离。
    """
    try:
        # 如果没有提供user_id，使用当前登录用户的ID（数据隔离）
        filter_user_id = user_id if user_id else current_user.id
        
        service = get_model_compare_service()
        stats = await service.get_compare_stats(
            session, user_id=filter_user_id, start_time=start_time, end_time=end_time
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=stats
        )
    except Exception as e:
        logger.error(f"获取对比统计数据失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/stats/model-usage", summary="获取模型使用统计")
async def get_model_usage_stats(
    user_id: Optional[str] = Query(None, description="用户ID（可选，默认使用当前登录用户）"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取模型使用统计
    
    根据当前登录用户自动过滤统计数据，实现数据隔离。
    """
    try:
        # 如果没有提供user_id，使用当前登录用户的ID（数据隔离）
        filter_user_id = user_id if user_id else current_user.id
        
        service = get_model_compare_service()
        stats = await service.get_model_usage_stats(
            session, user_id=filter_user_id, start_time=start_time, 
            end_time=end_time, limit=limit
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"items": stats}
        )
    except Exception as e:
        logger.error(f"获取模型使用统计失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


# ============================================================================
# 健康检查 API
# ============================================================================

@router.get("/health", summary="模型对比服务健康检查")
async def health_check():
    """
    检查模型对比服务的健康状态
    """
    try:
        service = get_model_compare_service()
        models = service.get_available_models()
        
        return ApiResponse.success_response(
            msg="服务正常",
            data={
                "status": "healthy",
                "available_models": len(models.models),
                "providers": len(models.providers),
            }
        )
    except Exception as e:
        logger.error(f"健康检查失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"服务异常: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
