#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书审批 API
提供审批相关的 API 接口
"""
from typing import Optional, Dict, Any
from loguru import logger

from lib.feishu.base.feishu_public import ValidateResponseException, UserIdType
from lib.feishu.base.http_client import FeishuHttpClient
from ..base import FeishuBaseApi


class FeishuApprovalApi(FeishuBaseApi):
    """飞书审批 API 类"""

    def get_instance_detail(
        self,
        instance_id: str,
        locale: Optional[str] = None,
        user_id: Optional[str] = None,
        user_id_type: str = UserIdType.OPEN_ID
    ) -> Dict[str, Any]:
        """
        获取单个审批实例详情
        通过审批实例 Code 获取指定审批实例的详细信息，包括审批实例的名称、创建时间、
        发起审批的用户、状态以及任务列表等信息。
        
        Args:
            instance_id: 审批实例 Code
            locale: 语言，可选值：LocaleType.ZH_CN（中文）、LocaleType.EN_US（英文）、LocaleType.JA_JP（日文）
            user_id: 发起审批的用户 ID，ID 类型由 user_id_type 参数指定
            user_id_type: 用户 ID 类型，可选值：UserIdType.OPEN_ID、UserIdType.UNION_ID、UserIdType.USER_ID，默认 OPEN_ID
            
        Returns:
            审批实例详情信息，包含 approval_name、start_time、end_time、user_id、status 等字段
        """
        url = f'{FeishuHttpClient.BASE_URL}/approval/v4/instances/{instance_id}'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {}
            if locale:
                params['locale'] = locale
            if user_id:
                params['user_id'] = user_id
            if user_id_type:
                params['user_id_type'] = user_id_type

            data = self.http_client.get(
                url=url,
                tenant_access_token=tenant_access_token,
                params=params
            )

            return data['data']
        except ValidateResponseException as e:
            logger.error(f'获取审批实例详情失败: {e}')
            raise
        except Exception as e:
            logger.error(f'获取审批实例详情失败: {e}')
            raise ValidateResponseException(f'获取审批实例详情失败: {str(e)}')

    def get_instance_list(
        self,
        approval_code: str,
        start_time: str,
        end_time: str,
        page_size: int = 100,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量获取审批实例ID
        根据审批定义的 approval_code 批量获取审批实例的 instance_code，用于拉取企业下某个审批定义的全部审批实例。
        默认以审批创建时间先后顺序排列。
        
        Args:
            approval_code: 审批定义 Code
            start_time: 审批实例创建时间的开始区间，毫秒时间戳
            end_time: 审批实例创建时间的结束区间，毫秒时间戳
            page_size: 分页大小，用于指定一次请求所返回的数据量上限，取值范围 1 ～ 100，默认值：100
            page_token: 分页标记，第一次请求不填，表示从头开始遍历；分页查询结果还有更多项时会同时返回新的 page_token
            
        Returns:
            审批实例ID列表信息，包含 instance_code_list、page_token、has_more 字段
        """
        url = f'{FeishuHttpClient.BASE_URL}/approval/v4/instances'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {
                'approval_code': approval_code,
                'start_time': start_time,
                'end_time': end_time,
                'page_size': page_size
            }
            
            if page_token:
                params['page_token'] = page_token

            data = self.http_client.get(
                url=url,
                tenant_access_token=tenant_access_token,
                params=params
            )

            return data['data']
        except ValidateResponseException as e:
            logger.error(f'批量获取审批实例ID失败: {e}')
            raise
        except Exception as e:
            logger.error(f'批量获取审批实例ID失败: {e}')
            raise ValidateResponseException(f'批量获取审批实例ID失败: {str(e)}')

    def get_all_instances(
        self,
        approval_code: str,
        start_time: str,
        end_time: str,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """
        获取所有审批实例ID（自动处理分页）
        根据审批定义的 approval_code 获取所有审批实例的 instance_code，自动处理分页逻辑。
        
        Args:
            approval_code: 审批定义 Code
            start_time: 审批实例创建时间的开始区间，毫秒时间戳
            end_time: 审批实例创建时间的结束区间，毫秒时间戳
            page_size: 分页大小，取值范围 1 ～ 100，默认值：100
            
        Returns:
            所有审批实例ID列表，包含 instance_code_list 和 total_count 字段
        """
        all_instance_codes = []
        page_token = None
        total_count = 0

        try:
            while True:
                result = self.get_instance_list(
                    approval_code=approval_code,
                    start_time=start_time,
                    end_time=end_time,
                    page_size=page_size,
                    page_token=page_token
                )

                instance_codes = result.get('instance_code_list', [])
                all_instance_codes.extend(instance_codes)
                total_count += len(instance_codes)

                # 检查是否还有更多数据
                has_more = result.get('has_more', False)
                if not has_more:
                    break

                # 获取下一页的 token
                page_token = result.get('page_token')
                if not page_token:
                    break

            return {
                'instance_code_list': all_instance_codes,
                'total_count': total_count
            }
        except Exception as e:
            logger.error(f'获取所有审批实例ID失败: {e}')
            raise ValidateResponseException(f'获取所有审批实例ID失败: {str(e)}')

    def get_instance_comments(
        self,
        instance_id: str,
        user_id: Optional[str] = None,
        user_id_type: str = 'user_id',
        page_size: int = 1000
    ) -> Dict[str, Any]:
        """
        获取审批实例的评论列表
        
        Args:
            instance_id: 审批实例 ID
            user_id: 用户 ID，可选
            user_id_type: 用户 ID 类型，默认 'user_id'
            page_size: 分页大小，默认 1000
            
        Returns:
            评论列表信息
        """
        url = f'{FeishuHttpClient.BASE_URL}/approval/v4/instances/{instance_id}/comments'
        
        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {
                'user_id_type': user_id_type,
                'page_size': page_size
            }
            if user_id:
                params['user_id'] = user_id
            
            data = self.http_client.get(
                url=url,
                tenant_access_token=tenant_access_token,
                params=params
            )
            
            return data
        except ValidateResponseException as e:
            logger.error(f'获取审批实例评论失败: {e}')
            raise
        except Exception as e:
            logger.error(f'获取审批实例评论失败: {e}')
            raise ValidateResponseException(f'获取审批实例评论失败: {str(e)}')

