#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书 API 基类
提供统一的 API 访问基础功能
"""
import time
from typing import Optional, Dict, Any
from loguru import logger

from lib.feishu.base.feishu_base import FeishuBase
from lib.feishu.base.feishu_public import ValidateResponseException
from lib.feishu.base.http_client import FeishuHttpClient


class FeishuBaseApi(FeishuBase):
    """飞书 API 基类"""
    
    _token_cache: Optional[Dict[str, Any]] = None
    _token_expire_time: Optional[float] = None
    _tenant_access_token: Optional[str] = None

    def __init__(self, app_id: str, app_secret: str, timeout: int = 30):
        """
        初始化飞书 API 基类
        
        Args:
            app_id: 应用 ID
            app_secret: 应用密钥
            timeout: 请求超时时间（秒），默认 30 秒
        """
        if not app_id or not app_secret:
            raise ValueError('app_id 或 app_secret 未正确配置')
        
        self.app_id = app_id
        self.app_secret = app_secret
        self.http_client = FeishuHttpClient(timeout=timeout)

    def get_app_access_token(self) -> Dict[str, Any]:
        """
        自建应用获取 app_access_token，带缓存
        
        Returns:
            包含 tenant_access_token、app_access_token 和 expire 的响应数据
        """
        current_time = time.time()

        # 如果缓存存在且未过期，直接返回缓存的 token
        if (
            self._token_cache is not None 
            and self._token_expire_time is not None 
            and current_time < self._token_expire_time
        ):
            return self._token_cache

        url = f'{FeishuHttpClient.BASE_URL}/auth/v3/app_access_token/internal'

        try:
            data = self.http_client.post(
                url=url,
                json_data={
                    'app_id': self.app_id,
                    'app_secret': self.app_secret
                }
            )

            expire = data.get('expire', 0)
            result = {
                'tenant_access_token': data['tenant_access_token'],
                'app_access_token': data['app_access_token'],
                'expire': expire
            }
            
            # 使用 API 返回的 expire 时间设置缓存过期时间（提前 60 秒过期）
            if expire and isinstance(expire, int):
                self._token_cache = result
                self._token_expire_time = current_time + expire - 60
                self._tenant_access_token = data['tenant_access_token']

            return result
        except ValidateResponseException as e:
            logger.error(f'获取 app_access_token 失败: {e}')
            raise
        except Exception as e:
            logger.error(f'获取 app_access_token 失败: {e}')
            raise ValidateResponseException(f'获取访问令牌失败: {str(e)}')

    def get_tenant_access_token(self) -> str:
        """
        获取租户访问令牌（自动处理缓存）
        
        Returns:
            租户访问令牌字符串
            
        Raises:
            ValidateResponseException: 获取令牌失败时抛出
        """
        if self._tenant_access_token and self._token_expire_time and time.time() < self._token_expire_time:
            return self._tenant_access_token
        
        token_data = self.get_app_access_token()
        token = token_data.get('tenant_access_token')
        if not token:
            raise ValidateResponseException('获取访问令牌失败：未返回 tenant_access_token')
        
        return token

    def get_user_access_token(self, app_access_token: str, code: str) -> Dict[str, Any]:
        """
        获取 user_access_token
        
        接口频率限制：1000 次/分钟、50 次/秒
        
        Args:
            app_access_token: 应用访问令牌
            code: 授权码（OAuth 授权码，通过用户授权流程获得）
            
        Returns:
            包含 access_token、refresh_token、expires_in、refresh_expires_in 的字典
            
        Raises:
            ValidateResponseException: 获取令牌失败时抛出
        """
        url = f'{FeishuHttpClient.BASE_URL}/authen/v1/oidc/access_token'

        try:
            data = self.http_client.post(
                url=url,
                tenant_access_token=app_access_token,
                json_data={
                    'grant_type': 'authorization_code',
                    'code': code
                }
            )

            result = {
                'access_token': data['data']['access_token'],
                'refresh_token': data['data']['refresh_token'],
                'expires_in': data['data']['expires_in'],
                'refresh_expires_in': data['data']['refresh_expires_in'],
            }
            return result
        except ValidateResponseException as e:
            logger.error(f'获取 user_access_token 失败: {e}')
            raise
        except Exception as e:
            logger.error(f'获取 user_access_token 失败: {e}')
            raise ValidateResponseException(f'获取用户访问令牌失败: {str(e)}')