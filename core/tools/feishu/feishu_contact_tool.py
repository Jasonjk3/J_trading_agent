#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书通讯录工具
封装飞书 SDK 的通讯录相关功能
"""
from typing import Any, Dict, Optional, List
from loguru import logger

from core.tools.base.base_tool import BaseTool
from lib.feishu import FeishuSDK


class FeishuContactTool(BaseTool):
    """飞书通讯录工具，用于查询用户和部门信息"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        timeout: int = 30
    ):
        """
        初始化飞书通讯录工具
        
        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            timeout: 请求超时时间（秒）
        """
        tool_description ="""
        查询飞书用户或部门信息，支持通过手机号、邮箱、用户名查询用户，搜索用户，获取部门信息等。
        特别说明：
        1. 如果是搜索用户，需要通过OAuth流程获取user_access_token，如果没用则不要使用这个接口
        """

        super().__init__(
            tool_name="feishu_contact",
            tool_description=tool_description,
            tool_type="feishu_contact"
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
                    "enum": ["get_user_by_mobiles", "get_user_by_emails", "get_departments", "get_user_by_department", "search_user"],
                    "description": "操作类型：get_user_by_mobiles-通过手机号查询用户，get_user_by_emails-通过邮箱查询用户，get_departments-获取部门列表，get_user_by_department-根据部门获取用户列表，search_user-搜索用户"
                },
                "query": {
                    "type": "string",
                    "description": "搜索关键词（action为search_user时必填）"
                },
                "user_access_token": {
                    "type": "string",
                    "description": "用户访问令牌（action为search_user时，如果提供了code则不需要此参数，否则必填。仅支持通过用户身份调用）"
                },
                "code": {
                    "type": "string",
                    "description": "OAuth授权码（action为search_user时可选，如果提供了code，工具会自动获取user_access_token。通过飞书OAuth授权流程获得）"
                },
                "page_token": {
                    "type": "string",
                    "description": "分页标识，用于获取下一页数据（action为search_user时使用）"
                },
                "mobiles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "手机号列表（action为get_user_by_mobiles时必填）"
                },
                "emails": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "邮箱列表（action为get_user_by_emails时必填）"
                },
                "open_department_id": {
                    "type": "string",
                    "description": "部门ID（action为get_departments或get_user_by_department时使用，默认为'0'表示根部门）"
                },
                "fetch_child": {
                    "type": "boolean",
                    "description": "是否获取子部门（action为get_departments时使用，默认true）"
                },
                "page_size": {
                    "type": "integer",
                    "description": "每页数量（action为get_departments时使用，默认50）"
                },
                "include_resigned": {
                    "type": "boolean",
                    "description": "是否包含已离职用户，默认false"
                },
                "user_id_type": {
                    "type": "string",
                    "enum": ["user_id", "open_id", "union_id"],
                    "description": "用户ID类型（action为get_user_by_mobiles或get_user_by_emails时使用，默认为'user_id'）"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        action: str,
        mobiles: Optional[List[str]] = None,
        emails: Optional[List[str]] = None,
        department_id: str = '0',
        include_resigned: bool = False,
        fetch_child: bool = True,
        page_size: int = 50,
        query: Optional[str] = None,
        user_access_token: Optional[str] = None,
        code: Optional[str] = None,
        page_token: Optional[str] = None,
        user_id_type: str = 'user_id'
    ) -> Dict[str, Any]:
        """
        执行工具：查询飞书通讯录信息
        
        Args:
            action: 操作类型
            mobiles: 手机号列表
            emails: 邮箱列表
            department_id: 部门ID
            include_resigned: 是否包含已离职用户
            user_id_type: 用户ID类型，默认为'user_id'
            
        Returns:
            执行结果
        """
        try:
            if action == "get_user_by_mobiles":
                if not mobiles:
                    return {
                        "success": False,
                        "error": "mobiles 参数不能为空"
                    }
                users = self.sdk.contact.get_user_by_mobiles(
                    mobiles=mobiles,
                    include_resigned=include_resigned,
                    user_id_type=user_id_type
                )
                return {
                    "success": True,
                    "action": action,
                    "data": users,
                    "count": len(users)
                }
            
            elif action == "get_user_by_emails":
                if not emails:
                    return {
                        "success": False,
                        "error": "emails 参数不能为空"
                    }
                users = self.sdk.contact.get_user_by_mobiles(
                    emails=emails,
                    include_resigned=include_resigned,
                    user_id_type=user_id_type
                )
                return {
                    "success": True,
                    "action": action,
                    "data": users,
                    "count": len(users)
                }
            
            elif action == "get_departments":
                dept_info = self.sdk.contact.get_departments(
                    department_id=department_id,
                    fetch_child=fetch_child,
                    page_size=page_size
                )
                return {
                    "success": True,
                    "action": action,
                    "data": dept_info
                }
            
            elif action == "get_user_by_department":
                users = self.sdk.contact.get_user_by_department(department_id=department_id)
                return {
                    "success": True,
                    "action": action,
                    "data": users
                }
            
            elif action == "search_user":
                if not query:
                    return {
                        "success": False,
                        "error": "query 参数不能为空"
                    }
                
                # 如果提供了 code，自动获取 user_access_token
                if code and not user_access_token:
                    try:
                        # 获取 app_access_token（使用基类方法，返回原始字典）
                        app_token_data = self.sdk.contact.get_app_access_token()
                        app_access_token = app_token_data.get('app_access_token')
                        
                        if not app_access_token:
                            return {
                                "success": False,
                                "error": "获取应用访问令牌失败：未返回 app_access_token"
                            }
                        
                        # 使用 code 获取 user_access_token（基类方法返回原始字典）
                        user_token_data = self.sdk.contact.get_user_access_token(
                            app_access_token=app_access_token,
                            code=code
                        )
                        user_access_token = user_token_data.get('access_token')
                        
                        if not user_access_token:
                            return {
                                "success": False,
                                "error": "通过 code 获取 user_access_token 失败：未返回 access_token"
                            }
                    except Exception as e:
                        logger.error(f'通过 code 获取 user_access_token 失败: {e}')
                        return {
                            "success": False,
                            "error": f"通过 code 获取 user_access_token 失败: {str(e)}"
                        }
                
                # 如果既没有 user_access_token 也没有 code，返回错误
                if not user_access_token:
                    return {
                        "success": False,
                        "error": "user_access_token 或 code 参数必须提供一个，搜索用户接口仅支持通过用户身份调用"
                    }
                
                # 验证 page_size 范围
                search_page_size = min(max(page_size, 1), 200) if page_size else 20
                result = self.sdk.contact.search_user(
                    query=query,
                    user_access_token=user_access_token,
                    page_size=search_page_size,
                    page_token=page_token
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result,
                    "users": result.get("users", []),
                    "has_more": result.get("has_more", False),
                    "page_token": result.get("page_token"),
                    "count": len(result.get("users", []))
                }
            
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作类型: {action}"
                }
                
        except Exception as e:
            logger.error(f'飞书通讯录工具执行失败: {e}')
            return {
                "success": False,
                "error": str(e),
                "action": action
            }

