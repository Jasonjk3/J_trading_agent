#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/18 15:10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
智能体管理API
用于查看智能体状态和诊断
"""
from fastapi import APIRouter, Depends, Request

from app.public.dependencies.response import ApiResponse, ResponseCode
from core.component.registry.agent_registry import AgentRegistry


# 创建路由器
router = APIRouter(prefix="/agents", tags=["智能体管理"])


def get_agent_registry(request: Request) -> AgentRegistry:
    """
    获取智能体注册中心（依赖注入）

    Args:
        request: FastAPI请求对象

    Returns:
        AgentRegistry实例
    """
    if not hasattr(request.app.state, 'agent_registry'):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail="智能体注册中心未初始化"
        )
    return request.app.state.agent_registry


@router.get("/", summary="获取所有智能体")
async def get_all_agents(
    registry: AgentRegistry = Depends(get_agent_registry)
):
    """
    获取所有智能体信息

    Returns:
        智能体列表
    """
    try:
        agents = await registry.get_all_agents()
        agents_info = [agent.to_info().dict() for agent in agents]
        
        return ApiResponse.success_response(
            msg="获取智能体列表成功",
            code=ResponseCode.OK.value,
            data={
                "total": len(agents_info),
                "agents": agents_info
            }
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取智能体列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}", summary="获取指定智能体")
async def get_agent(
    agent_id: str,
    registry: AgentRegistry = Depends(get_agent_registry)
):
    """
    获取指定智能体信息

    Args:
        agent_id: 智能体ID

    Returns:
        智能体信息
    """
    try:
        agent = await registry.get_agent(agent_id)
        if not agent:
            return ApiResponse.failed_response(
                msg=f"智能体不存在: {agent_id}",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取智能体信息成功",
            code=ResponseCode.OK.value,
            data=agent.to_info().dict()
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取智能体信息失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/stats/overview", summary="获取智能体统计信息")
async def get_agent_stats(
    registry: AgentRegistry = Depends(get_agent_registry)
):
    """
    获取智能体统计信息

    Returns:
        统计信息
    """
    try:
        stats = await registry.get_stats()
        agents = await registry.get_all_agents()
        
        # 添加详细信息
        stats["agents_detail"] = [
            {
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "agent_type": agent.agent_type,
                "status": agent.status.value,
                "current_tasks": agent.current_tasks,
                "max_concurrent_tasks": agent.max_concurrent_tasks,
                "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None
            }
            for agent in agents
        ]
        
        return ApiResponse.success_response(
            msg="获取统计信息成功",
            code=ResponseCode.OK.value,
            data=stats
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取统计信息失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )

