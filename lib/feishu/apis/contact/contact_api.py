#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书通讯录 API
提供用户和部门相关的 API 接口
"""
from typing import Optional, Dict, Any, List
from loguru import logger

from lib.feishu.base.feishu_public import ValidateResponseException, ReceiveIdType
from lib.feishu.base.http_client import FeishuHttpClient
from ..base import FeishuBaseApi


class FeishuContactApi(FeishuBaseApi):
    """飞书通讯录 API 类"""

    def get_user_info(
        self,
        user_id: str,
        user_id_type: str = 'open_id'
    ) -> Dict[str, Any]:
        """
        获取单个用户信息
        
        Args:
            user_id: 用户 ID
            user_id_type: 用户 ID 类型，默认 'open_id'
            
        Returns:
            用户信息响应数据
            
        Note:
            此方法尚未实现
        """
        # TODO: 实现获取单个用户信息的方法
        raise NotImplementedError('此方法尚未实现')

    def get_user_by_mobiles(
        self,
        mobiles: Optional[List[str]] = None,
        emails: Optional[List[str]] = None,
        include_resigned: bool = False,
        user_id_type: str = ReceiveIdType.USER_ID
    ) -> List[Dict[str, Any]]:
        """
        通过手机号或邮箱获取用户 ID
        
        Args:
            mobiles: 手机号列表
            emails: 邮箱列表
            include_resigned: 是否包含已离职用户，默认 False
            user_id_type: 用户 ID 类型，默认 ReceiveIdType.USER_ID
            
        Returns:
            用户信息列表
        """
        url = f'{FeishuHttpClient.BASE_URL}/contact/v3/users/batch_get_id'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data={
                    'emails': emails or [],
                    'mobiles': mobiles or [],
                    'include_resigned': include_resigned
                },
                params={'user_id_type': user_id_type}
            )

            return data['data']['user_list']
        except ValidateResponseException as e:
            logger.error(f'通过手机号或邮箱获取用户 ID 失败: {e}')
            raise
        except Exception as e:
            logger.error(f'通过手机号或邮箱获取用户 ID 失败: {e}')
            raise ValidateResponseException(f'获取用户信息失败: {str(e)}')

    def search_user(
        self,
        query: str,
        user_access_token: str,
        page_size: int = 20,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        搜索用户
        通过用户名关键词搜索其他用户的信息，包括用户头像、用户名、用户所在部门、用户 user_id 以及 open_id。
        
        Args:
            query: 搜索关键词，必填
            user_access_token: 用户访问令牌，必填（仅支持通过用户身份调用）
            page_size: 分页大小，用于限制当前请求所返回的数据条目数，最小值1，最大值200，默认20
            page_token: 分页标识，首次调用该接口时无需填写。如果返回值中包含了 page_token 值，则可以使用该值继续调用本接口
            
        Returns:
            搜索用户响应数据，包含：
                - has_more: 是否还有更多数据
                - page_token: 分页标识
                - users: 搜索到的用户列表，每个用户包含：
                    - avatar: 用户头像信息
                    - department_ids: 用户所在的部门 ID 列表
                    - name: 用户名
                    - open_id: 用户的 open_id
                    - user_id: 用户的 user_id（需要相应权限）
        
        Note:
            - 仅支持通过用户身份（user_access_token）调用该接口
            - 无法搜索到外部企业或已离职的用户
        """
        url = f'{FeishuHttpClient.BASE_URL}/search/v1/user'

        try:
            # 确保查询参数正确编码（特别是包含中文字符时）
            from urllib.parse import quote
            params = {
                'query': query,  # requests 会自动进行 URL 编码，但确保是 Unicode 字符串
                'page_size': page_size
            }
            
            if page_token:
                params['page_token'] = page_token

            data = self.http_client.get(
                url=url,
                user_access_token=user_access_token,
                params=params
            )

            return data.get('data', {})
        except ValidateResponseException as e:
            logger.error(f'搜索用户失败: {e}')
            raise
        except Exception as e:
            logger.error(f'搜索用户失败: {e}')
            raise ValidateResponseException(f'搜索用户失败: {str(e)}')

    def get_user_by_department(
        self,
        department_id: str = '0'
    ) -> Dict[str, Any]:
        """
        根据部门获取用户列表
        
        Args:
            department_id: 部门ID，默认为根部门'0'
            
        Returns:
            用户列表信息
        """
        url = f'{FeishuHttpClient.BASE_URL}/contact/v3/users/find_by_department'
        
        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {
                'department_id': department_id,
            }
            
            data = self.http_client.get(
                url=url,
                tenant_access_token=tenant_access_token,
                params=params
            )
            
            return data
        except ValidateResponseException as e:
            logger.error(f'根据部门获取用户列表失败: {e}')
            raise
        except Exception as e:
            logger.error(f'根据部门获取用户列表失败: {e}')
            raise ValidateResponseException(f'根据部门获取用户列表失败: {str(e)}')

    def get_departments(
        self,
        department_id: str = '0',
        department_id_type: str = 'open_department_id',
        fetch_child: bool = True,
        page_size: int = 50,
        user_id_type: str = 'open_id'
    ) -> Dict[str, Any]:
        """
        获取部门列表
        
        Args:
            department_id: 部门ID，默认为根部门'0'
            department_id_type: 部门ID类型，默认为open_department_id
            fetch_child: 是否获取子部门，默认为True
            page_size: 每页获取的部门数量，默认为50
            user_id_type: 用户ID类型，默认为open_id
            
        Returns:
            部门信息
        """
        url = f'{FeishuHttpClient.BASE_URL}/contact/v3/departments/{department_id}/children'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            params = {
                'department_id_type': department_id_type,
                'fetch_child': str(fetch_child).lower(),
                'page_size': page_size,
                'user_id_type': user_id_type
            }

            data = self.http_client.get(
                url=url,
                tenant_access_token=tenant_access_token,
                params=params
            )
            
            return data
        except ValidateResponseException as e:
            logger.error(f'获取部门列表失败: {e}')
            raise
        except Exception as e:
            logger.error(f'获取部门列表失败: {e}')
            raise ValidateResponseException(f'获取部门列表失败: {str(e)}')

