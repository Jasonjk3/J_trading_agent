#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/7 9:55
# @Author : Jason
# @Email : Jasonforjob@qq.com

import time
from fastapi import Request
from loguru import logger


class LoggingMiddleware:
    """自定义日志中间件"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive)
        start_time = time.time()
        status_code = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            process_time = time.time() - start_time

            log_data = {
                "path": request.url.path,
                "method": request.method,
                "status": status_code or "unknown",
                "latency": f"{process_time:.4f}s"
            }

            # 写入日志系统
            logger.info(log_data)
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "Request failed: %s %s, error: %s, latency: %.4fs",
                request.method,
                request.url.path,
                str(e),
                process_time
            )
            raise