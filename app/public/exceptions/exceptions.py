# -*- coding: utf-8 -*-
from com.app.core.response_code import RET, MessageType


class BaseAppException(Exception):
    """应用异常基类"""
    def __init__(self, message: str = MessageType.ERROR.value, code: int = RET.EXECERR, data: dict = None):
        self.message = message
        self.code = code
        self.data = data or {}
        super().__init__(self.message)


class PermissionDeniedException(BaseAppException):
    """
    权限不足异常
    """
    def __init__(self, message: str = MessageType.PERMISSION_DENIED.value):
        super().__init__(code=RET.FORBIDDEN, message=message)


class SystemErrorException(BaseAppException):
    """
    系统错误
    """
    def __init__(self, message: str = MessageType.ERROR.value):
        super().__init__(code=RET.EXECERR, message=message)


class DataBaseException(BaseAppException):
    """
    数据库操作异常
    """
    def __init__(self, message: str = MessageType.DBERR.value):
        super().__init__(code=RET.EXECERR, message=message)


class FeishuPushException(BaseAppException):
    """
    自定义异常类，用于处理与飞书推送相关的错误。
    """
    def __init__(self, message=''):
        self.message = 'Feishu push operation failed ->' + message
        super().__init__(message=self.message)


class ServiceException(BaseAppException):
    """
    业务逻辑异常
    """
    def __init__(self, message: str = MessageType.BUSINESS_ERROR.value):
        self.message = message
        super().__init__(message=self.message)


class BoxMessageException(BaseAppException):
    """
    前端展示消息
    """
    def __init__(self, message=MessageType.ERROR.value):
        self.message = message
        super().__init__(message=self.message)


class InvalidParameterError(BaseAppException):
    """
    用于输入参数错误的异常
    """
    def __init__(self, message=MessageType.PARAMERR.value):
        self.message = message
        super().__init__(message=self.message)


class ApiKeyAuthenticationException(BaseAppException):
    """
    API认证失败
    """
    def __init__(self, message=MessageType.API_KEY_VERIFICATION_ERROR.value):
        self.message = message
        super().__init__(message=self.message)
