#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书任务工具
封装飞书 SDK 的任务相关功能
"""
from typing import Any, Dict, Optional, List
from loguru import logger
from datetime import datetime

from core.tools.base.base_tool import BaseTool
from lib.feishu import FeishuSDK


class FeishuTaskTool(BaseTool):
    """飞书任务工具，用于创建和管理任务"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        timeout: int = 30
    ):
        """
        初始化飞书任务工具
        
        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            timeout: 请求超时时间（秒）
        """
        super().__init__(
            tool_name="feishu_task",
            tool_description="创建和管理飞书任务，包括创建任务、更新任务、获取任务详情、删除任务、设置任务负责人、截止时间、提醒等。支持更新任务标题、描述、开始时间、截止时间、完成状态等",
            tool_type="feishu_task"
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
                    "enum": ["create_task", "update_task", "get_task_detail", "delete_task"],
                    "description": "操作类型：create_task-创建任务，update_task-更新任务，get_task_detail-获取任务详情，delete_task-删除任务"
                },
                "task_guid": {
                    "type": "string",
                    "description": "任务GUID，更新任务时必填"
                },
                "update_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要修改的字段列表，可选值：summary(标题), description(描述), start(开始时间), due(截止时间), completed_at(完成时间), extra(自定义数据), repeat_rule(重复规则), mode(完成模式), is_milestone(里程碑)"
                },
                "completed_at": {
                    "type": "string",
                    "description": "任务完成时间戳（毫秒），设为\"0\"表示恢复为未完成状态"
                },
                "summary": {
                    "type": "string",
                    "description": "任务标题，必填，最大3000个utf8字符"
                },
                "description": {
                    "type": "string",
                    "description": "任务摘要，可选，最大3000个utf8字符"
                },
                "due_timestamp": {
                    "type": "string",
                    "description": "任务截止时间戳（毫秒），可选"
                },
                "due_is_all_day": {
                    "type": "boolean",
                    "description": "截止时间是否为全天，默认false"
                },
                "start_timestamp": {
                    "type": "string",
                    "description": "任务开始时间戳（毫秒），可选"
                },
                "start_is_all_day": {
                    "type": "boolean",
                    "description": "开始时间是否为全天，默认false"
                },
                "assignee_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "任务负责人ID列表（必须是open_id格式，以'ou_'开头），可选。如果提供的是user_id或其他格式，需要先通过搜索用户名或者根据手机号/邮箱接口获取open_id"
                },
                "follower_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "任务关注人ID列表（必须是open_id格式，以'ou_'开头），可选。如果提供的是user_id或其他格式，需要先通过搜索用户接口获取open_id"
                },
                "tasklist_guid": {
                    "type": "string",
                    "description": "任务所在清单的GUID，可选"
                },
                "section_guid": {
                    "type": "string",
                    "description": "清单中自定义分组的GUID，可选"
                },
                "reminder_minutes": {
                    "type": "integer",
                    "description": "提醒时间（相对于截止时间的分钟数），可选，例如30表示截止时间前30分钟提醒"
                },
                "client_token": {
                    "type": "string",
                    "description": "幂等token，可选，长度10-100字符"
                }
            },
            "required": ["action"]
        }
    
    def _format_timestamp(self, timestamp_str: str) -> Optional[str]:
        """
        格式化时间戳字符串
        
        Args:
            timestamp_str: 时间戳字符串（可以是毫秒时间戳或日期时间字符串）
        
        Returns:
            毫秒时间戳字符串
        """
        if not timestamp_str:
            return None
        
        try:
            # 如果已经是纯数字字符串，直接返回
            if timestamp_str.isdigit():
                return timestamp_str
            
            # 尝试解析日期时间字符串
            # 支持格式：YYYY-MM-DD, YYYY-MM-DD HH:mm:ss
            formats = [
                "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d",
                "%Y/%m/%d %H:%M:%S"
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    # 转换为毫秒时间戳
                    return str(int(dt.timestamp() * 1000))
                except ValueError:
                    continue
            
            logger.warning(f"无法解析时间戳格式: {timestamp_str}")
            return None
        except Exception as e:
            logger.error(f"格式化时间戳失败: {e}")
            return None
    
    async def execute(
        self,
        action: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        due_timestamp: Optional[str] = None,
        due_is_all_day: bool = False,
        start_timestamp: Optional[str] = None,
        start_is_all_day: bool = False,
        assignee_ids: Optional[List[str]] = None,
        follower_ids: Optional[List[str]] = None,
        tasklist_guid: Optional[str] = None,
        section_guid: Optional[str] = None,
        reminder_minutes: Optional[int] = None,
        client_token: Optional[str] = None,
        task_guid: Optional[str] = None,
        update_fields: Optional[List[str]] = None,
        completed_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行工具：创建或更新飞书任务
        
        Args:
            action: 操作类型（create_task 或 update_task）
            summary: 任务标题（创建时必填）
            description: 任务摘要
            due_timestamp: 截止时间戳（毫秒）或日期时间字符串
            due_is_all_day: 截止时间是否为全天
            start_timestamp: 开始时间戳（毫秒）或日期时间字符串
            start_is_all_day: 开始时间是否为全天
            assignee_ids: 负责人ID列表（仅创建时使用）
            follower_ids: 关注人ID列表（仅创建时使用）
            tasklist_guid: 任务所在清单的GUID（仅创建时使用）
            section_guid: 清单中自定义分组的GUID（仅创建时使用）
            reminder_minutes: 提醒时间（相对于截止时间的分钟数，仅创建时使用）
            client_token: 幂等token（仅创建时使用）
            task_guid: 任务GUID（更新时必填）
            update_fields: 需要修改的字段列表（更新时必填）
            completed_at: 任务完成时间戳（毫秒），设为"0"表示恢复为未完成状态
            
        Returns:
            执行结果
        """
        try:
            if action == "create_task":
                return await self._create_task(
                    summary=summary,
                    description=description,
                    due_timestamp=due_timestamp,
                    due_is_all_day=due_is_all_day,
                    start_timestamp=start_timestamp,
                    start_is_all_day=start_is_all_day,
                    assignee_ids=assignee_ids,
                    follower_ids=follower_ids,
                    tasklist_guid=tasklist_guid,
                    section_guid=section_guid,
                    reminder_minutes=reminder_minutes,
                    client_token=client_token
                )
            elif action == "update_task":
                return await self._update_task(
                    task_guid=task_guid,
                    update_fields=update_fields,
                    summary=summary,
                    description=description,
                    due_timestamp=due_timestamp,
                    due_is_all_day=due_is_all_day,
                    start_timestamp=start_timestamp,
                    start_is_all_day=start_is_all_day,
                    completed_at=completed_at
                )
            elif action == "get_task_detail":
                return await self._get_task_detail(
                    task_guid=task_guid
                )
            elif action == "delete_task":
                return await self._delete_task(
                    task_guid=task_guid
                )
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作类型: {action}"
                }
                
        except Exception as e:
            logger.error(f'飞书任务工具执行失败: {e}', exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": action
            }
    
    async def _create_task(
        self,
        summary: str,
        description: Optional[str] = None,
        due_timestamp: Optional[str] = None,
        due_is_all_day: bool = False,
        start_timestamp: Optional[str] = None,
        start_is_all_day: bool = False,
        assignee_ids: Optional[List[str]] = None,
        follower_ids: Optional[List[str]] = None,
        tasklist_guid: Optional[str] = None,
        section_guid: Optional[str] = None,
        reminder_minutes: Optional[int] = None,
        client_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建任务
        
        Args:
            summary: 任务标题
            description: 任务摘要
            due_timestamp: 截止时间戳
            due_is_all_day: 截止时间是否为全天
            start_timestamp: 开始时间戳
            start_is_all_day: 开始时间是否为全天
            assignee_ids: 负责人ID列表
            follower_ids: 关注人ID列表
            tasklist_guid: 任务所在清单的GUID
            section_guid: 清单中自定义分组的GUID
            reminder_minutes: 提醒时间
            client_token: 幂等token
            
        Returns:
            执行结果
        """
        if not summary:
            return {
                "success": False,
                "error": "任务标题不能为空"
            }
        
        # 构建请求参数
        request_params = {
            "summary": summary
        }
        
        if description:
            request_params["description"] = description
        
        # 处理截止时间
        if due_timestamp:
            formatted_due = self._format_timestamp(due_timestamp)
            if formatted_due:
                request_params["due"] = {
                    "timestamp": formatted_due,
                    "is_all_day": due_is_all_day
                }
        
        # 处理开始时间
        if start_timestamp:
            formatted_start = self._format_timestamp(start_timestamp)
            if formatted_start:
                request_params["start"] = {
                    "timestamp": formatted_start,
                    "is_all_day": start_is_all_day
                }
        
        # 处理成员（负责人和关注人）
        members = []
        if assignee_ids:
            for assignee_id in assignee_ids:
                # 验证 open_id 格式（通常以 'ou_' 开头）
                if not assignee_id.startswith('ou_'):
                    logger.warning(f'负责人ID "{assignee_id}" 不是标准的open_id格式（应以"ou_"开头），可能会失败')
                members.append({
                    "id": assignee_id,
                    "type": "user",
                    "role": "assignee"
                })
        
        if follower_ids:
            for follower_id in follower_ids:
                # 验证 open_id 格式（通常以 'ou_' 开头）
                if not follower_id.startswith('ou_'):
                    logger.warning(f'关注人ID "{follower_id}" 不是标准的open_id格式（应以"ou_"开头），可能会失败')
                members.append({
                    "id": follower_id,
                    "type": "user",
                    "role": "follower"
                })
        
        if members:
            request_params["members"] = members
        
        # 处理任务清单
        if tasklist_guid:
            tasklist_info = {"tasklist_guid": tasklist_guid}
            if section_guid:
                tasklist_info["section_guid"] = section_guid
            request_params["tasklists"] = [tasklist_info]
        
        # 处理提醒
        if reminder_minutes is not None:
            if not due_timestamp:
                return {
                    "success": False,
                    "error": "设置提醒时必须提供截止时间"
                }
            request_params["reminders"] = [
                {"relative_fire_minute": reminder_minutes}
            ]
        
        if client_token:
            request_params["client_token"] = client_token
        
        # 调用API创建任务
        result = self.sdk.task.create_task(**request_params)
        
        return {
            "success": True,
            "action": "create_task",
            "data": result
        }
    
    async def _update_task(
        self,
        task_guid: str,
        update_fields: List[str],
        summary: Optional[str] = None,
        description: Optional[str] = None,
        due_timestamp: Optional[str] = None,
        due_is_all_day: bool = False,
        start_timestamp: Optional[str] = None,
        start_is_all_day: bool = False,
        completed_at: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        更新任务
        
        Args:
            task_guid: 任务GUID
            update_fields: 需要修改的字段列表
            summary: 任务标题
            description: 任务描述
            due_timestamp: 截止时间戳
            due_is_all_day: 截止时间是否为全天
            start_timestamp: 开始时间戳
            start_is_all_day: 开始时间是否为全天
            completed_at: 任务完成时间戳（设为"0"表示恢复为未完成）
            
        Returns:
            执行结果
        """
        if not task_guid:
            return {
                "success": False,
                "error": "任务GUID不能为空"
            }
        
        if not update_fields:
            return {
                "success": False,
                "error": "update_fields 不能为空，请指定要更新的字段"
            }
        
        # 构建任务更新数据
        task_data = {}
        
        if "summary" in update_fields:
            if summary is not None:
                task_data["summary"] = summary
            # 如果summary在update_fields中但值为None，表示清空（但API不允许清空标题）
        
        if "description" in update_fields:
            task_data["description"] = description if description is not None else ""
        
        if "due" in update_fields:
            if due_timestamp:
                formatted_due = self._format_timestamp(due_timestamp)
                if formatted_due:
                    task_data["due"] = {
                        "timestamp": formatted_due,
                        "is_all_day": due_is_all_day
                    }
            else:
                # 清空截止时间（设为空对象）
                task_data["due"] = {}
        
        if "start" in update_fields:
            if start_timestamp:
                formatted_start = self._format_timestamp(start_timestamp)
                if formatted_start:
                    task_data["start"] = {
                        "timestamp": formatted_start,
                        "is_all_day": start_is_all_day
                    }
            else:
                # 清空开始时间（设为空对象）
                task_data["start"] = {}
        
        if "completed_at" in update_fields:
            if completed_at is not None:
                # 如果设为"0"，表示恢复为未完成
                if completed_at == "0":
                    task_data["completed_at"] = "0"
                else:
                    formatted_completed = self._format_timestamp(completed_at)
                    if formatted_completed:
                        task_data["completed_at"] = formatted_completed
            else:
                # 如果completed_at在update_fields中但值为None，设为"0"表示恢复未完成
                task_data["completed_at"] = "0"
        
        # 调用API更新任务
        result = self.sdk.task.update_task(
            task_guid=task_guid,
            update_fields=update_fields,
            task=task_data if task_data else None
        )
        
        return {
            "success": True,
            "action": "update_task",
            "data": result
        }
    
    async def _get_task_detail(
        self,
        task_guid: str
    ) -> Dict[str, Any]:
        """
        获取任务详情
        
        Args:
            task_guid: 任务GUID
            
        Returns:
            执行结果
        """
        if not task_guid:
            return {
                "success": False,
                "error": "任务GUID不能为空"
            }
        
        # 调用API获取任务详情
        result = self.sdk.task.get_task_detail(task_guid=task_guid)
        
        return {
            "success": True,
            "action": "get_task_detail",
            "data": result
        }
    
    async def _delete_task(
        self,
        task_guid: str
    ) -> Dict[str, Any]:
        """
        删除任务
        
        Args:
            task_guid: 任务GUID
            
        Returns:
            执行结果
        """
        if not task_guid:
            return {
                "success": False,
                "error": "任务GUID不能为空"
            }
        
        # 调用API删除任务
        result = self.sdk.task.delete_task(task_guid=task_guid)
        
        return {
            "success": True,
            "action": "delete_task",
            "data": result,
            "message": "任务已成功删除"
        }

