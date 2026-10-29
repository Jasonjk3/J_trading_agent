#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一的 HTTP 客户端封装
提供统一的请求处理、错误处理和响应验证
"""
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode, quote
from loguru import logger
import requests
from requests.exceptions import ProxyError, RequestException

from lib.feishu.base.feishu_public import ValidateResponseException


class FeishuHttpClient:
    """飞书 HTTP 客户端统一封装"""
    
    BASE_URL = 'https://open.feishu.cn/open-apis'
    
    def __init__(self, timeout: int = 30):
        """
        初始化 HTTP 客户端
        
        Args:
            timeout: 请求超时时间（秒），默认 30 秒
        """
        self.timeout = timeout
        self.session = requests.Session()
    
    def _build_headers(
        self, 
        tenant_access_token: Optional[str] = None,
        user_access_token: Optional[str] = None,
        content_type: str = 'application/json; charset=utf-8'
    ) -> Dict[str, str]:
        """
        构建请求头
        
        Args:
            tenant_access_token: 租户访问令牌
            user_access_token: 用户访问令牌
            content_type: 内容类型
            
        Returns:
            请求头字典
        """
        # 构建请求头，确保所有值都是字符串类型
        headers = {}
        
        # Content-Type 头
        if content_type:
            headers['Content-Type'] = str(content_type)
        
        # Authorization 头
        if tenant_access_token:
            headers['Authorization'] = f'Bearer {tenant_access_token}'
        elif user_access_token:
            headers['Authorization'] = f'Bearer {user_access_token}'
        
        return headers
    
    def _validate_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        验证响应并返回数据
        
        Args:
            response: requests 响应对象
            
        Returns:
            响应数据字典
            
        Raises:
            ValidateResponseException: 响应验证失败时抛出
        """
        try:
            data = response.json()
        except json.JSONDecodeError:
            error_msg = f'响应解析失败，状态码：{response.status_code}，响应内容：{response.text}'
            logger.error(error_msg)
            raise ValidateResponseException(error_msg)
        
        if 'code' not in data or data['code'] != 0:
            error_msg = f"API请求失败 -> code:[{data.get('code')}], msg:[{data.get('msg', '未知错误')}]"
            logger.error(f'{error_msg}, 完整响应: {data}')
            raise ValidateResponseException(error_msg)
        
        return data
    
    def get(
        self,
        url: str,
        tenant_access_token: Optional[str] = None,
        user_access_token: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送 GET 请求
        
        Args:
            url: 请求 URL
            tenant_access_token: 租户访问令牌
            user_access_token: 用户访问令牌
            params: 查询参数
            headers: 自定义请求头
            
        Returns:
            响应数据字典
            
        Raises:
            ValidateResponseException: 请求失败时抛出
        """
        request_headers = self._build_headers(tenant_access_token, user_access_token)
        if headers:
            request_headers.update(headers)
        
        try:
            # requests 库会自动处理 URL 参数的编码（使用 UTF-8）
            # 但为了确保中文字符正确处理，我们确保参数值是正确的类型
            response = self.session.get(
                url=url,
                headers=request_headers,
                params=params,
                timeout=self.timeout
            )
            return self._validate_response(response)
        except ProxyError as e:
            error_msg = '无法请求飞书接口，请检测是否开启了代理，请关闭代理'
            logger.error(f'{e} - {error_msg}')
            raise ValidateResponseException(error_msg)
        except RequestException as e:
            error_msg = f'HTTP请求异常: {str(e)}'
            logger.error(error_msg)
            raise ValidateResponseException(error_msg)
    
    def post(
        self,
        url: str,
        tenant_access_token: Optional[str] = None,
        user_access_token: Optional[str] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送 POST 请求
        
        Args:
            url: 请求 URL
            tenant_access_token: 租户访问令牌
            user_access_token: 用户访问令牌
            data: 请求体数据（字符串或文件）
            json_data: JSON 数据（字典）
            params: 查询参数
            headers: 自定义请求头
            
        Returns:
            响应数据字典
            
        Raises:
            ValidateResponseException: 请求失败时抛出
        """
        request_headers = self._build_headers(tenant_access_token, user_access_token)
        if headers:
            request_headers.update(headers)
        
        try:
            if json_data is not None:
                response = self.session.post(
                    url=url,
                    headers=request_headers,
                    json=json_data,
                    params=params,
                    timeout=self.timeout
                )
            else:
                response = self.session.post(
                    url=url,
                    headers=request_headers,
                    data=data,
                    params=params,
                    timeout=self.timeout
                )
            return self._validate_response(response)
        except ProxyError as e:
            error_msg = '无法请求飞书接口，请检测是否开启了代理，请关闭代理'
            logger.error(f'{e} - {error_msg}')
            raise ValidateResponseException(error_msg)
        except RequestException as e:
            error_msg = f'HTTP请求异常: {str(e)}'
            logger.error(error_msg)
            raise ValidateResponseException(error_msg)
    
    def patch(
        self,
        url: str,
        tenant_access_token: Optional[str] = None,
        user_access_token: Optional[str] = None,
        data: Optional[Any] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送 PATCH 请求
        
        Args:
            url: 请求 URL
            tenant_access_token: 租户访问令牌
            user_access_token: 用户访问令牌
            data: 请求体数据（字符串）
            json_data: JSON 数据（字典）
            params: 查询参数
            headers: 自定义请求头
            
        Returns:
            响应数据字典
            
        Raises:
            ValidateResponseException: 请求失败时抛出
        """
        request_headers = self._build_headers(tenant_access_token, user_access_token)
        if headers:
            request_headers.update(headers)
        
        try:
            if json_data is not None:
                response = self.session.patch(
                    url=url,
                    headers=request_headers,
                    json=json_data,
                    params=params,
                    timeout=self.timeout
                )
            else:
                response = self.session.patch(
                    url=url,
                    headers=request_headers,
                    data=data,
                    params=params,
                    timeout=self.timeout
                )
            return self._validate_response(response)
        except ProxyError as e:
            error_msg = '无法请求飞书接口，请检测是否开启了代理，请关闭代理'
            logger.error(f'{e} - {error_msg}')
            raise ValidateResponseException(error_msg)
        except RequestException as e:
            error_msg = f'HTTP请求异常: {str(e)}'
            logger.error(error_msg)
            raise ValidateResponseException(error_msg)
    
    def post_multipart(
        self,
        url: str,
        tenant_access_token: Optional[str] = None,
        form_data: Any = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送 multipart/form-data POST 请求（用于文件上传）
        
        Args:
            url: 请求 URL
            tenant_access_token: 租户访问令牌
            form_data: MultipartEncoder 对象
            params: 查询参数
            
        Returns:
            响应数据字典
            
        Raises:
            ValidateResponseException: 请求失败时抛出
        """
        request_headers = self._build_headers(
            tenant_access_token=tenant_access_token,
            content_type=form_data.content_type if hasattr(form_data, 'content_type') else None
        )
        
        try:
            response = self.session.post(
                url=url,
                headers=request_headers,
                data=form_data,
                params=params,
                timeout=self.timeout
            )
            return self._validate_response(response)
        except ProxyError as e:
            error_msg = '无法请求飞书接口，请检测是否开启了代理，请关闭代理'
            logger.error(f'{e} - {error_msg}')
            raise ValidateResponseException(error_msg)
        except RequestException as e:
            error_msg = f'HTTP请求异常: {str(e)}'
            logger.error(error_msg)
            raise ValidateResponseException(error_msg)
    
    def delete(
        self,
        url: str,
        tenant_access_token: Optional[str] = None,
        user_access_token: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送 DELETE 请求
        
        Args:
            url: 请求 URL
            tenant_access_token: 租户访问令牌
            user_access_token: 用户访问令牌
            params: 查询参数
            headers: 自定义请求头
            
        Returns:
            响应数据字典
            
        Raises:
            ValidateResponseException: 请求失败时抛出
        """
        request_headers = self._build_headers(tenant_access_token, user_access_token)
        if headers:
            request_headers.update(headers)
        
        try:
            response = self.session.delete(
                url=url,
                headers=request_headers,
                params=params,
                timeout=self.timeout
            )
            return self._validate_response(response)
        except ProxyError as e:
            error_msg = '无法请求飞书接口，请检测是否开启了代理，请关闭代理'
            logger.error(f'{e} - {error_msg}')
            raise ValidateResponseException(error_msg)
        except RequestException as e:
            error_msg = f'HTTP请求异常: {str(e)}'
            logger.error(error_msg)
            raise ValidateResponseException(error_msg)

