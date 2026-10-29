#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书多维表格工具
封装飞书 SDK 的多维表格相关功能
"""
from typing import Any, Dict, Optional, List
from loguru import logger

from core.tools.base.base_tool import BaseTool
from lib.feishu import FeishuSDK


class FeishuBitableTool(BaseTool):
    """飞书多维表格工具，用于操作多维表格数据"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        timeout: int = 30
    ):
        """
        初始化飞书多维表格工具
        
        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            timeout: 请求超时时间（秒）
        """
        super().__init__(
            tool_name="feishu_bitable",
            tool_description="操作飞书多维表格，包括创建记录、查询记录、更新记录、删除记录等",
            tool_type="feishu_bitable"
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
                    "enum": ["create_record", "batch_create_records", "search_records", "update_record", "delete_record"],
                    "description": "操作类型：create_record-创建单条记录，batch_create_records-批量创建记录，search_records-搜索记录，update_record-更新记录，delete_record-删除记录"
                },
                "app_token": {
                    "type": "string",
                    "description": "多维表格App的唯一标识（所有操作必填）"
                },
                "table_id": {
                    "type": "string",
                    "description": "多维表格数据表的唯一标识（所有操作必填）"
                },
                "fields": {
                    "type": "object",
                    "description": "字段数据，格式：{\"字段名\": \"值\"}（create_record、update_record时必填）"
                },
                "records": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fields": {"type": "object"}
                        }
                    },
                    "description": "记录列表，格式：[{\"fields\": {\"字段名\": \"值\"}}]（batch_create_records时必填）"
                },
                "record_id": {
                    "type": "string",
                    "description": "记录ID（update_record、delete_record时必填）"
                },
                "view_id": {
                    "type": "string",
                    "description": "视图ID（search_records时可选）"
                },
                "field_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "返回字段名列表（search_records时可选）"
                },
                "filter": {
                    "type": "object",
                    "description": "过滤条件对象（search_records时可选）"
                },
                "sort": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "排序条件数组（search_records时可选）"
                },
                "page_size": {
                    "type": "integer",
                    "description": "分页大小，默认100，最大500",
                    "minimum": 1,
                    "maximum": 500
                },
                "page_token": {
                    "type": "string",
                    "description": "分页标记，用于获取下一页数据"
                }
            },
            "required": ["action", "app_token", "table_id"]
        }
    
    async def execute(
        self,
        action: str,
        app_token: str,
        table_id: str,
        fields: Optional[Dict[str, Any]] = None,
        records: Optional[List[Dict[str, Any]]] = None,
        record_id: Optional[str] = None,
        page_size: int = 100,
        page_token: Optional[str] = None,
        view_id: Optional[str] = None,
        field_names: Optional[List[str]] = None,
        filter: Optional[Dict[str, Any]] = None,
        sort: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        执行工具：操作飞书多维表格
        
        Args:
            action: 操作类型
            app_token: 多维表格App的唯一标识
            table_id: 多维表格数据表的唯一标识
            fields: 字段数据
            records: 记录列表
            record_id: 记录ID
            page_size: 分页大小
            page_token: 分页标记
            
        Returns:
            执行结果
        """
        try:
            if action == "create_record":
                if not fields:
                    return {
                        "success": False,
                        "error": "fields 参数不能为空"
                    }
                result = self.sdk.bitable.create_record(
                    app_token=app_token,
                    table_id=table_id,
                    fields=fields
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "batch_create_records":
                if not records:
                    return {
                        "success": False,
                        "error": "records 参数不能为空"
                    }
                result = self.sdk.bitable.batch_create_records(
                    app_token=app_token,
                    table_id=table_id,
                    records=records
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "search_records":
                result = self.sdk.bitable.search_records(
                    app_token=app_token,
                    table_id=table_id,
                    page_size=page_size,
                    page_token=page_token,
                    view_id=view_id,
                    field_names=field_names,
                    filter=filter,
                    sort=sort
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "update_record":
                if not record_id or not fields:
                    return {
                        "success": False,
                        "error": "record_id 和 fields 参数不能为空"
                    }
                result = self.sdk.bitable.update_record(
                    app_token=app_token,
                    table_id=table_id,
                    record_id=record_id,
                    fields=fields
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "delete_record":
                if not record_id:
                    return {
                        "success": False,
                        "error": "record_id 参数不能为空"
                    }
                result = self.sdk.bitable.delete_record(
                    app_token=app_token,
                    table_id=table_id,
                    record_id=record_id
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
            logger.error(f'飞书多维表格工具执行失败: {e}')
            return {
                "success": False,
                "error": str(e),
                "action": action
            }

