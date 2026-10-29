#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
监控服务 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from app.v1.schemas.service_monitor_schema import (
    ServiceMonitorRequest,
    ServiceMonitorResponse
)
from app.v1.services.service_monitor_service import ServiceMonitorService
from app.public.dependencies.response import ApiResponse, ResponseCode

# 创建路由器
router = APIRouter(prefix="/service-monitor", tags=["监控服务"])


def get_service_monitor_service(request: Request) -> ServiceMonitorService:
    """
    获取监控服务实例（依赖注入）

    Args:
        request: FastAPI请求对象

    Returns:
        ServiceMonitorService实例
    """
    if not hasattr(request.app.state, 'service_monitor_service'):
        raise HTTPException(
            status_code=500,
            detail="监控服务未初始化，请检查应用启动配置"
        )
    return request.app.state.service_monitor_service


@router.post("/control", summary="控制监控服务", response_model=ServiceMonitorResponse)
async def control_service_monitor(
    request: ServiceMonitorRequest,
    service: ServiceMonitorService = Depends(get_service_monitor_service)
):
    """
    控制监控服务（启动、停止、暂停、恢复、获取状态、更新配置）

    支持的操作：
    - start: 启动服务
    - stop: 停止服务
    - pause: 暂停服务
    - resume: 恢复服务
    - status: 获取服务状态
    - config: 更新或获取配置

    Args:
        request: 监控服务请求
        service: 监控服务

    Returns:
        监控服务响应
    """
    try:
        # 调用服务执行操作
        result = await service.control(request)
        
        if result.get("success"):
            return ApiResponse.success_response(
                msg="操作成功",
                code=ResponseCode.OK.value,
                data=result
            )
        else:
            return ApiResponse.failed_response(
                msg=result.get("error", "操作失败"),
                code=ResponseCode.FAILED.value,
                data=result
            )
            
    except Exception as e:
        logger.error(f"监控服务 API 处理失败: {e}", exc_info=True)
        return ApiResponse.failed_response(
            msg=f"处理请求失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )

