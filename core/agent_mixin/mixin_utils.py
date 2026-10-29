#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Mixin 工具函数
提供 Mixin 层共用的工具函数，减少代码重复
"""
from typing import Any, Dict, Optional
from loguru import logger

from core.tools.base.base_tool import BaseTool


def get_agent_attr(agent, attr_name: str, default: Any = None):
    """
    安全获取 Agent 属性（统一封装）
    
    Args:
        agent: Agent 实例
        attr_name: 属性名
        default: 默认值
        
    Returns:
        属性值或默认值
    """
    return getattr(agent, attr_name, default)


def get_agent_id(agent) -> Optional[str]:
    """获取 Agent ID"""
    return get_agent_attr(agent, 'agent_id', None)


def get_agent_name(agent, default: str = 'Agent') -> str:
    """获取 Agent 名称"""
    return get_agent_attr(agent, 'agent_name', default)


def get_agent_type(agent, default: Optional[str] = None) -> Optional[str]:
    """获取 Agent 类型"""
    return get_agent_attr(agent, 'agent_type', default)


def get_tools(agent) -> Dict[str, BaseTool]:
    """获取工具字典"""
    return get_agent_attr(agent, 'tools', {})


def get_llm(agent):
    """获取 LLM 实例"""
    return get_agent_attr(agent, 'llm', None)


def register_tool_unified(agent, tool: BaseTool) -> None:
    """
    统一工具注册方法（避免重复代码）
    
    Args:
        agent: Agent 实例
        tool: 工具实例
    """
    tools = get_tools(agent)
    tools[tool.tool_name] = tool
    logger.debug(f'已注册工具: {tool.tool_name}')


def unregister_tool_unified(agent, tool_name: str) -> None:
    """
    统一工具注销方法（避免重复代码）
    
    Args:
        agent: Agent 实例
        tool_name: 工具名称
    """
    tools = get_tools(agent)
    if tool_name in tools:
        del tools[tool_name]
        logger.info(f'已注销工具: {tool_name}')


def build_agent_result(
    agent,
    success: bool = True,
    response: Optional[str] = None,
    error: Optional[str] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    reasoning_mode: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    统一构建 Agent 执行结果字典（避免重复代码）
    
    Args:
        agent: Agent 实例
        success: 是否成功
        response: 响应内容
        error: 错误信息
        session_id: 会话ID
        task_id: 任务ID
        reasoning_mode: 推理模式
        **kwargs: 其他字段
        
    Returns:
        格式化的结果字典
    """
    result = {
        "success": success,
        "agent_id": get_agent_id(agent),
        "agent_type": get_agent_type(agent),
    }
    
    if response is not None:
        result["response"] = response
    if error is not None:
        result["error"] = error
    if session_id is not None:
        result["session_id"] = session_id
    if task_id is not None:
        result["task_id"] = task_id
    if reasoning_mode is not None:
        result["reasoning_mode"] = reasoning_mode
    
    # 添加其他字段
    result.update(kwargs)
    
    return result


async def cleanup_tools_unified(agent) -> None:
    """
    统一清理工具方法（避免重复代码）
    
    Args:
        agent: Agent 实例
    """
    tools = get_tools(agent)
    for tool in tools.values():
        if hasattr(tool, 'cleanup'):
            try:
                await tool.cleanup()
            except Exception as e:
                logger.warning(f'清理工具 {tool.tool_name} 失败: {e}')

