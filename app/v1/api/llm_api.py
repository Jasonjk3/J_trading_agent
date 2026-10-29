#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/18 16:20
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
LLM管理API
用于查看LLM健康状态和监控信息
"""
from fastapi import APIRouter, Depends, Request
from fastapi import HTTPException

from app.public.dependencies.response import ApiResponse, ResponseCode
from core.llm.base.llm_health_monitor import LLMHealthMonitor


# 创建路由器
router = APIRouter(prefix="/llm", tags=["LLM管理"])


def get_llm_health_monitor(request: Request) -> LLMHealthMonitor:
    """
    获取LLM健康监控器（依赖注入）

    Args:
        request: FastAPI请求对象

    Returns:
        LLMHealthMonitor实例
    """
    if not hasattr(request.app.state, 'llm_health_monitor'):
        raise HTTPException(
            status_code=500,
            detail="LLM健康监控器未初始化"
        )
    return request.app.state.llm_health_monitor


@router.get("/health", summary="获取LLM健康状态")
async def get_llm_health(
    monitor: LLMHealthMonitor = Depends(get_llm_health_monitor)
):
    """
    获取LLM健康状态

    Returns:
        LLM健康信息
    """
    try:
        health_info = await monitor.get_health_info_async()
        
        return ApiResponse.success_response(
            msg="获取LLM健康状态成功",
            code=ResponseCode.OK.value,
            data=health_info
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取LLM健康状态失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/health/check", summary="手动触发LLM健康检查")
async def check_llm_health(
    monitor: LLMHealthMonitor = Depends(get_llm_health_monitor)
):
    """
    手动触发LLM健康检查

    Returns:
        健康检查结果
    """
    try:
        result = await monitor.check_health()
        
        if result["success"]:
            return ApiResponse.success_response(
                msg="LLM健康检查成功",
                code=ResponseCode.OK.value,
                data=result
            )
        else:
            return ApiResponse.failed_response(
                msg=f"LLM健康检查失败: {result.get('error')}",
                code=ResponseCode.SYSTEM_ERROR.value,
                data=result
            )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"执行LLM健康检查失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )

