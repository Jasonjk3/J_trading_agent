#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/9 15:19
# @Author : Jason
# @Email : Jasonforjob@qq.com
from enum import Enum

from starlette.responses import JSONResponse


class ResponseCode(Enum):
    OK = 200
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    FAILED = 500
    SYSTEM_ERROR = 501
    AUTH_ERROR = 5002

class CodeMessage(Enum):
    OK = "成功"
    FORBIDDEN = "禁止访问"
    NOT_FOUND = "未找到"
    METHOD_NOT_ALLOWED = "请求方法错误"
    FAILED = "失败"
    SYSTEM_ERROR = "系统内部错误"
    AUTH_ERROR = "认证失败"


class ApiResponse:
    @classmethod
    def success_response(cls, msg: str = "成功", code=ResponseCode.OK.value, data=None, **kwargs):
        return cls.response(msg=msg, code=code, data=data, **kwargs)

    @classmethod
    def failed_response(cls, msg: str = "失败", code=ResponseCode.FAILED.value, data=None, **kwargs):
        return cls.response(msg=msg, code=code, data=data, **kwargs)

    @staticmethod
    def response(msg, code, data, **kwargs):
        response_data = {"message": msg, "code": code, "data": data, **kwargs}
        return JSONResponse(content=response_data, status_code=200)
