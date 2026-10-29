#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/21 10:48
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
飞书任务 API
提供任务相关的 API 接口
"""
from typing import Optional, Dict, Any, List
from loguru import logger

from lib.feishu.base.feishu_public import ValidateResponseException, UserIdType
from lib.feishu.base.http_client import FeishuHttpClient
from ..base import FeishuBaseApi


class FeishuTaskApi(FeishuBaseApi):
    """飞书任务 API 类"""

    def create_task(
        self,
        summary: str,
        description: Optional[str] = None,
        due: Optional[Dict[str, Any]] = None,
        start: Optional[Dict[str, Any]] = None,
        members: Optional[List[Dict[str, Any]]] = None,
        tasklists: Optional[List[Dict[str, Any]]] = None,
        reminders: Optional[List[Dict[str, Any]]] = None,
        client_token: Optional[str] = None,
        user_id_type: str = UserIdType.OPEN_ID,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建任务
        
        Args:
            summary: 任务标题，必填，最大3000个utf8字符
            description: 任务摘要，可选，最大3000个utf8字符
            due: 任务截止时间，格式：{"timestamp": "1675454764000", "is_all_day": true}
            start: 任务开始时间，格式：{"timestamp": "1675454764000", "is_all_day": true}
            members: 任务成员列表，格式：[{"id": "ou_xxx", "type": "user", "role": "assignee", "name": "姓名"}]
            tasklists: 任务所在清单信息，格式：[{"tasklist_guid": "xxx", "section_guid": "xxx"}]
            reminders: 任务提醒，格式：[{"relative_fire_minute": 30}]
            client_token: 幂等token，可选，长度10-100字符
            user_id_type: 用户ID类型，默认open_id
            **kwargs: 其他可选参数，如：
                - origin: 任务关联的第三方平台来源信息
                - extra: 调用者可以传入的任意附带到任务上的数据
                - completed_at: 任务的完成时刻时间戳(ms)
                - repeat_rule: 重复任务规则
                - custom_complete: 任务自定义完成配置
                - mode: 任务完成模式，1-会签任务，2-或签任务
                - is_milestone: 是否是里程碑任务
                - custom_fields: 自定义字段值
                - docx_source: 任务来源为文档
                - positive_reminders: 正数协议每日提醒
        
        Returns:
            创建的任务信息，包含task对象
        """
        url = f'{FeishuHttpClient.BASE_URL}/task/v2/tasks'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            # 构建请求体
            request_data = {
                "summary": summary
            }
            
            if description:
                request_data["description"] = description
            
            if due:
                request_data["due"] = due
            
            if start:
                request_data["start"] = start
            
            if members:
                request_data["members"] = members
            
            if tasklists:
                request_data["tasklists"] = tasklists
            
            if reminders:
                request_data["reminders"] = reminders
            
            if client_token:
                request_data["client_token"] = client_token
            
            # 添加其他可选参数
            for key, value in kwargs.items():
                if value is not None:
                    request_data[key] = value
            
            params = {}
            if user_id_type:
                params["user_id_type"] = user_id_type

            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data=request_data,
                params=params
            )

            return data.get('data', {})
        except ValidateResponseException as e:
            logger.error(f'创建任务失败: {e}')
            raise
        except Exception as e:
            logger.error(f'创建任务失败: {e}')
            raise ValidateResponseException(f'创建任务失败: {str(e)}')

    def update_task(
        self,
        task_guid: str,
        update_fields: List[str],
        task: Optional[Dict[str, Any]] = None,
        user_id_type: str = UserIdType.OPEN_ID
    ) -> Dict[str, Any]:
        """
        更新任务
        
        Args:
            task_guid: 要更新的任务全局唯一ID
            update_fields: 需要修改的字段列表，可选值：
                - summary: 任务标题
                - description: 任务描述
                - start: 任务开始时间
                - due: 任务截止时间
                - completed_at: 任务完成时间（设为"0"表示恢复为未完成）
                - extra: 任务附属自定义数据
                - custom_complete: 任务自定义完成规则
                - repeat_rule: 任务重复规则
                - mode: 任务完成模式（1-会签任务，2-或签任务）
                - is_milestone: 是否是里程碑任务
                - custom_fields: 自定义字段值（使用"custom_fields"作为字段名）
            task: 要更新的任务数据，只需要设置出现在update_fields中的字段即可
                如果update_fields设置了要变更一个字段名，但是task里没设置新的值，则表示将该字段清空
            user_id_type: 用户ID类型，默认open_id
        
        Returns:
            更新后的任务信息，包含task对象
        
        Note:
            - 任务成员/提醒/清单数据不能使用本接口进行更新，需要使用专门的接口
            - 更新时需要调用身份对任务有编辑权限
            - 不能对已经完成的任务再次完成，但可以将其恢复到未完成的状态(设置completed_at为"0")
        """
        url = f'{FeishuHttpClient.BASE_URL}/task/v2/tasks/{task_guid}'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            # 构建请求体
            request_data = {
                "update_fields": update_fields
            }
            
            if task:
                request_data["task"] = task
            
            params = {}
            if user_id_type:
                params["user_id_type"] = user_id_type

            data = self.http_client.patch(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data=request_data,
                params=params
            )

            return data.get('data', {})
        except ValidateResponseException as e:
            logger.error(f'更新任务失败: {e}')
            raise
        except Exception as e:
            logger.error(f'更新任务失败: {e}')
            raise ValidateResponseException(f'更新任务失败: {str(e)}')

    def get_task_detail(
        self,
        task_guid: str,
        user_id_type: str = UserIdType.OPEN_ID
    ) -> Dict[str, Any]:
        """
        获取任务详情
        
        Args:
            task_guid: 要获取的任务guid
            user_id_type: 用户ID类型，默认open_id
        
        Returns:
            任务详情信息，包含task对象
        
        Note:
            - 获取任务详情需要调用身份拥有对任务的可读取权限
        """
        url = f'{FeishuHttpClient.BASE_URL}/task/v2/tasks/{task_guid}'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {}
            if user_id_type:
                params["user_id_type"] = user_id_type

            data = self.http_client.get(
                url=url,
                tenant_access_token=tenant_access_token,
                params=params
            )

            return data.get('data', {})
        except ValidateResponseException as e:
            logger.error(f'获取任务详情失败: {e}')
            raise
        except Exception as e:
            logger.error(f'获取任务详情失败: {e}')
            raise ValidateResponseException(f'获取任务详情失败: {str(e)}')

    def delete_task(
        self,
        task_guid: str
    ) -> Dict[str, Any]:
        """
        删除任务
        
        Args:
            task_guid: 要删除的任务guid
        
        Returns:
            删除结果，成功时返回空字典
        
        Note:
            - 删除任务需要任务的可编辑权限
            - 删除后任务无法再被获取到
        """
        url = f'{FeishuHttpClient.BASE_URL}/task/v2/tasks/{task_guid}'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            data = self.http_client.delete(
                url=url,
                tenant_access_token=tenant_access_token
            )

            return data.get('data', {})
        except ValidateResponseException as e:
            logger.error(f'删除任务失败: {e}')
            raise
        except Exception as e:
            logger.error(f'删除任务失败: {e}')
            raise ValidateResponseException(f'删除任务失败: {str(e)}')
