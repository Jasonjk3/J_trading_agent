#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书审批工具
封装飞书 SDK 的审批相关功能
"""
from typing import Any, Dict, Optional
from loguru import logger

from core.tools.base.base_tool import BaseTool
from lib.feishu import FeishuSDK


class FeishuApprovalTool(BaseTool):
    """飞书审批工具，用于查询审批实例信息"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        timeout: int = 30
    ):
        """
        初始化飞书审批工具
        
        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            timeout: 请求超时时间（秒）
        """
        super().__init__(
            tool_name="feishu_approval",
            tool_description="查询飞书审批实例信息，包括审批详情、审批列表等",
            tool_type="feishu_approval"
        )
        
        self.sdk = FeishuSDK(app_id=app_id, app_secret=app_secret, timeout=timeout)
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数模式
        
        Returns:
            参数模式字典
        """
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get_instance_detail", "get_instance_list"],
                    "description": "操作类型：get_instance_detail-获取审批实例详情，get_instance_list-获取审批实例列表"
                },
                "instance_id": {
                    "type": "string",
                    "description": "审批实例ID（action为get_instance_detail时必填）"
                },
                "approval_code": {
                    "type": "string",
                    "description": "审批定义Code（action为get_instance_list时必填）"
                },
                "start_time": {
                    "type": "string",
                    "description": "开始时间，格式：YYYY-MM-DD HH:mm:ss（action为get_instance_list时必填）"
                },
                "end_time": {
                    "type": "string",
                    "description": "结束时间，格式：YYYY-MM-DD HH:mm:ss（action为get_instance_list时必填）"
                },
                "page_size": {
                    "type": "integer",
                    "description": "分页大小，默认100，最大100",
                    "minimum": 1,
                    "maximum": 100
                },
                "page_token": {
                    "type": "string",
                    "description": "分页标记，用于获取下一页数据"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        action: str,
        instance_id: Optional[str] = None,
        approval_code: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page_size: int = 100,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行工具：查询飞书审批信息
        
        Args:
            action: 操作类型
            instance_id: 审批实例ID
            approval_code: 审批定义Code
            start_time: 开始时间
            end_time: 结束时间
            page_size: 分页大小
            page_token: 分页标记
            
        Returns:
            执行结果
        """
        try:
            if action == "get_instance_detail":
                if not instance_id:
                    return {
                        "success": False,
                        "error": "instance_id 参数不能为空"
                    }
                detail = self.sdk.approval.get_instance_detail(instance_id=instance_id)
                return {
                    "success": True,
                    "action": action,
                    "data": detail
                }
            
            elif action == "get_instance_list":
                if not approval_code or not start_time or not end_time:
                    return {
                        "success": False,
                        "error": "approval_code、start_time、end_time 参数不能为空"
                    }
                result = self.sdk.approval.get_instance_list(
                    approval_code=approval_code,
                    start_time=start_time,
                    end_time=end_time,
                    page_size=page_size,
                    page_token=page_token
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作类型: {action}"
                }
                
        except Exception as e:
            logger.error(f'飞书审批工具执行失败: {e}')
            return {
                "success": False,
                "error": str(e),
                "action": action
            }

