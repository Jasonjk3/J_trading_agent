#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
监控服务 API Schema
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ServiceMonitorRequest(BaseModel):
    """监控服务请求"""
    action: str = Field(..., description="操作类型：start/stop/pause/resume/status/config", 
                       pattern="^(start|stop|pause|resume|status|config)$")
    config: Optional[Dict[str, Any]] = Field(None, description="配置信息（仅当 action=config 时使用）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "action": "start"
            }
        }


class ScheduledTaskInfo(BaseModel):
    """定时任务信息"""
    enabled: bool = Field(..., description="是否启用")
    interval: float = Field(..., description="执行间隔（秒）")
    last_run: Optional[str] = Field(None, description="上次执行时间")
    next_run: Optional[str] = Field(None, description="下次执行时间")


class ServiceMonitorResponse(BaseModel):
    """监控服务响应"""
    success: bool = Field(..., description="是否成功")
    action: str = Field(..., description="操作类型")
    status: Optional[str] = Field(None, description="Agent 状态")
    is_running: Optional[bool] = Field(None, description="是否运行中")
    is_paused: Optional[bool] = Field(None, description="是否暂停")
    scheduled_tasks: Optional[Dict[str, ScheduledTaskInfo]] = Field(None, description="定时任务信息")
    config: Optional[Dict[str, Any]] = Field(None, description="配置信息")
    agent_id: Optional[str] = Field(None, description="Agent ID")
    error: Optional[str] = Field(None, description="错误信息")
    message: Optional[str] = Field(None, description="消息")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "action": "status",
                "status": "running",
                "is_running": True,
                "is_paused": False,
                "agent_id": "agent_123"
            }
        }

