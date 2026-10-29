#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书 SDK 主类
提供飞书开放平台 API 的统一封装，作为统一入口组合各个板块的 API
"""
import time
from typing import Dict, Any
from loguru import logger

from lib.feishu.base.feishu_public import ValidateResponseException
from lib.feishu.base.http_client import FeishuHttpClient
from lib.feishu.apis.base import FeishuBaseApi
from lib.feishu.apis.approval.approval_api import FeishuApprovalApi
from lib.feishu.apis.contact.contact_api import FeishuContactApi
from lib.feishu.apis.bitable.bitable_api import FeishuBitableApi
from lib.feishu.apis.im.im_api import FeishuImApi
from lib.feishu.apis.task.task_api import FeishuTaskApi


class FeishuSDK(FeishuBaseApi):
    """飞书 SDK 主类，提供统一入口和基础功能"""
    
    def __init__(self, app_id: str, app_secret: str, timeout: int = 30):
        """
        初始化飞书 SDK
        
        Args:
            app_id: 应用 ID
            app_secret: 应用密钥
            timeout: 请求超时时间（秒），默认 30 秒
            
        Raises:
            ValueError: app_id 或 app_secret 未配置时抛出
        """
        super().__init__(app_id=app_id, app_secret=app_secret, timeout=timeout)
        
        # 初始化各个板块的 API（共享同一个实例的 token 缓存）
        # 通过共享 token 缓存对象引用，确保所有实例使用同一个 token
        self.approval = FeishuApprovalApi(app_id=app_id, app_secret=app_secret, timeout=timeout)
        self.contact = FeishuContactApi(app_id=app_id, app_secret=app_secret, timeout=timeout)
        self.bitable = FeishuBitableApi(app_id=app_id, app_secret=app_secret, timeout=timeout)
        self.im = FeishuImApi(app_id=app_id, app_secret=app_secret, timeout=timeout)
        self.task = FeishuTaskApi(app_id=app_id, app_secret=app_secret, timeout=timeout)
        
        # 共享 token 缓存（让所有 API 实例共享同一个 token 缓存对象）
        self._share_token_cache()

    def _share_token_cache(self):
        """
        共享 token 缓存到各个 API 实例
        通过共享对象引用，确保所有实例使用同一个 token 缓存
        """
        for api_instance in [self.approval, self.contact, self.bitable, self.im, self.task]:
            # 共享缓存对象引用，这样当主 SDK 更新 token 时，所有子实例都能看到
            api_instance._token_cache = self._token_cache
            api_instance._token_expire_time = self._token_expire_time
            api_instance._tenant_access_token = self._tenant_access_token

    def get_app_access_token(self) -> Dict[str, Any]:
        """
        自建应用获取 app_access_token，带缓存
        返回格式与原有 SDK 保持一致（包装为 success/error 格式）
        
        Returns:
            包含 tenant_access_token、app_access_token 和 expire 的响应数据
        """
        try:
            # 调用基类方法获取 token（返回原始字典）
            token_data = super().get_app_access_token()
            
            # 同步更新所有子 API 实例的 token 缓存
            self._sync_token_cache()
            
            # 包装为统一的返回格式，保持向后兼容
            return self.build_success_return_data(data=token_data)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'获取 app_access_token 失败: {e}')
            return self.build_error_return_data(msg=f'获取访问令牌失败: {str(e)}')
    
    def _sync_token_cache(self):
        """
        同步 token 缓存到所有子 API 实例
        当 token 更新时，确保所有子实例都能获取到最新的 token
        """
        for api_instance in [self.approval, self.contact, self.bitable, self.im, self.task]:
            api_instance._token_cache = self._token_cache
            api_instance._token_expire_time = self._token_expire_time
            api_instance._tenant_access_token = self._tenant_access_token

    def get_user_access_token(self, app_access_token: str, code: str) -> Dict[str, Any]:
        """
        获取 user_access_token
        返回格式与原有 SDK 保持一致（包装为 success/error 格式）
        
        接口频率限制：1000 次/分钟、50 次/秒
        
        Args:
            app_access_token: 应用访问令牌
            code: 授权码（OAuth 授权码，通过用户授权流程获得）
            
        Returns:
            包含 access_token、refresh_token 等信息的响应数据（包装后的格式）
        """
        try:
            # 调用基类方法获取 token（返回原始字典）
            token_data = super().get_user_access_token(app_access_token=app_access_token, code=code)
            
            # 包装为统一的返回格式，保持向后兼容
            return self.build_success_return_data(data=token_data)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'获取 user_access_token 失败: {e}')
            return self.build_error_return_data(msg=f'获取用户访问令牌失败: {str(e)}')
    
    def get_tenant_access_token(self) -> str:
        """
        获取租户访问令牌（自动处理缓存）
        继承自 FeishuBaseApi，提供便捷访问
        
        Returns:
            租户访问令牌字符串
            
        Raises:
            ValidateResponseException: 获取令牌失败时抛出
        """
        # 不能直接调用 super().get_tenant_access_token()：父类内部会通过
        # self.get_app_access_token() 动态分派回本类，而本类为兼容旧调用会将
        # token 包装成 {state, msg, data}，导致父类在顶层读取不到
        # tenant_access_token。这里显式调用父类的原始 token 获取方法。
        if (
            self._tenant_access_token
            and self._token_expire_time
            and time.time() < self._token_expire_time
        ):
            return self._tenant_access_token

        token_data = FeishuBaseApi.get_app_access_token(self)
        self._sync_token_cache()
        token = token_data.get('tenant_access_token')
        if not token:
            raise ValidateResponseException('获取访问令牌失败：未返回 tenant_access_token')
        return token
