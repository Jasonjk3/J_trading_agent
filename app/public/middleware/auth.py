#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/7 9:55
# @Author : Jason
# @Email : Jasonforjob@qq.com
import os

# api/middleware/auth.py
from fastapi import Request, HTTPException
from typing import Optional
from typing import Set

from loguru import logger

from app.public.dependencies.response import ApiResponse, ResponseCode, CodeMessage


class AuthMiddleware:
    """API密钥鉴权中间件"""

    def __init__(self, app, valid_keys=None, excluded_paths=None):
        if valid_keys is None:
            valid_keys = {}
        if excluded_paths is None:
            excluded_paths = {}
        self.app = app
        self.valid_keys ={os.getenv('SECRET_KEY')}
        self.valid_keys.update(valid_keys)

        self.excluded_paths = {"/docs","/health","/openapi.json"}  # 配置排除路径
        self.excluded_paths.update(excluded_paths)

    async def __call__(self, scope, receive, send):
        try:
            # 创建 Request 对象
            request = Request(scope, receive)

            # 排除健康检查端点
            if request.url.path in self.excluded_paths:
                return await self.app(scope, receive, send)

            # 提取并校验 API Key
            try:
                api_key = self._extract_api_key(request)
            except Exception as e:
                logger.error(f"Error extracting API key: {e}")
                response = ApiResponse.failed_response(
                    code=ResponseCode.SYSTEM_ERROR.value,
                    msg=CodeMessage.SYSTEM_ERROR.value
                )
                return await response(scope, receive, send)

            if not api_key or api_key not in self.valid_keys:
                logger.warning(f"Invalid API key: {api_key}")
                response = ApiResponse.failed_response(
                    code=ResponseCode.AUTH_ERROR.value,
                    msg=CodeMessage.AUTH_ERROR.value
                )
                return await response(scope, receive, send)

            # 处理正常请求
            return await self.app(scope, receive, send)

        except Exception as e:
            # 捕获所有未处理的异常，防止服务崩溃
            logger.error(f"Unhandled exception: {e}")
            response = ApiResponse.failed_response(
                code=ResponseCode.SYSTEM_ERROR.value,
                msg=CodeMessage.SYSTEM_ERROR.value
            )
            return await response(scope, receive, send)

    def _extract_api_key(self, request):
        """从请求中提取 API Key"""
        # 假设 API Key 存在于请求头中
        return request.headers.get("X-API-Key")