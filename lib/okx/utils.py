# -*- ecoding: utf-8 -*-
# @ModuleName: utils.py
# @Author: jason
# @Email: jasonforjob@qq.com
# @Time: 2025/3/7
# @Desc:
import asyncio
import time
import functools
from typing import Type, Tuple

import httpx


class NonRetryableRequestError(Exception):
    """业务类错误，不应自动重试。"""


def retry_async(
        max_retries: int = 3,
        retry_exceptions: Tuple[Type[Exception], ...] = (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ),
        backoff_factor: float = 2.0
):
    """
    异步函数重试装饰器

    Args:
        max_retries: 最大重试次数
        retry_exceptions: 需要重试的异常类型
        backoff_factor: 退避因子，用于计算重试间隔时间
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None

            for retry in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions as e:
                    last_error = e

                    # 根据异常类型生成错误消息
                    if isinstance(e, httpx.ConnectError):
                        error_type = "连接错误"
                    elif isinstance(e, httpx.TimeoutException):
                        error_type = "请求超时"
                    else:
                        error_type = "请求出错"

                    # 判断是否是最后一次重试
                    if retry == max_retries - 1:
                        raise Exception(f"请求失败: {error_type}: {str(e)}")

                    # 打印重试信息
                    print(f"{error_type}，正在重试 ({retry + 1}/{max_retries}): {str(e)}")

                    # 指数退避
                    await asyncio.sleep(backoff_factor ** retry)

            # 如果所有重试都失败，抛出最后一个错误
            raise last_error

        return wrapper

    return decorator
