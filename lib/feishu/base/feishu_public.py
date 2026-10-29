#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2024/9/5 9:36
# @Author : Jason
# @Email : Jasonforjob@qq.com
from typing import Dict, List, Optional
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ResponseType:
    SUCCESS = 'success'
    ERROR = 'error'


class ToastType:
    INFO = 'info'
    SUCCESS = 'success'
    ERROR = 'error'
    WARNING = 'warning'


class CardType:
    RAW = 'raw'
    TEMPLATE = 'template'


class ReceiveIdType:
    """消息接收者 ID 类型"""
    OPEN_ID = 'open_id'      # 标识一个用户在某个应用中的身份
    UNION_ID = 'union_id'    # 标识一个用户在某个应用开发商下的身份
    USER_ID = 'user_id'      # 标识一个用户在某个租户内的身份
    EMAIL = 'email'          # 以用户的真实邮箱来标识用户
    CHAT_ID = 'chat_id'      # 以群 ID 来标识群聊


class MsgType:
    """消息类型"""
    TEXT = 'text'              # 文本
    POST = 'post'              # 富文本
    IMAGE = 'image'            # 图片
    FILE = 'file'              # 文件
    AUDIO = 'audio'            # 语音
    MEDIA = 'media'            # 视频
    STICKER = 'sticker'        # 表情包
    INTERACTIVE = 'interactive'  # 卡片
    SHARE_CHAT = 'share_chat'  # 分享群名片
    SHARE_USER = 'share_user'  # 分享个人名片
    SYSTEM = 'system'          # 系统消息


class ImageType:
    MESSAGE = 'message'
    AVATAR = 'avatar'


class FileType:
    OPUS = 'opus'
    MP4 = 'mp4'
    PDF = 'pdf'
    DOC = 'doc'
    XLS = 'xls'
    PPT = 'ppt'
    STREAM = 'stream'


class LocaleType:
    """审批语言类型"""
    ZH_CN = 'zh-CN'  # 中文
    EN_US = 'en-US'  # 英文
    JA_JP = 'ja-JP'  # 日文


class UserIdType:
    """用户ID类型"""
    OPEN_ID = 'open_id'    # 标识一个用户在某个应用中的身份
    UNION_ID = 'union_id'  # 标识一个用户在某个应用开发商下的身份
    USER_ID = 'user_id'    # 标识一个用户在某个租户内的身份


class ApprovalStatus:
    """审批实例状态"""
    PENDING = 'PENDING'    # 审批中
    APPROVED = 'APPROVED'  # 通过
    REJECTED = 'REJECTED'  # 拒绝
    CANCELED = 'CANCELED'  # 撤回
    DELETED = 'DELETED'    # 删除


class FeishuCallbackHeaderItem(BaseModel):
    event_id: str
    token: str
    create_time: str
    event_type: str
    tenant_key: str
    app_id: str


class FeishuCallbackEventOperatorItem(BaseModel):
    tenant_key: str
    user_id: str
    open_id: str


class FeishuCallbackEventActionItem(BaseModel):
    value: Optional[Dict[str, str]] = None
    tag: str
    timezone: Optional[str] = None
    name: Optional[str] = None
    form_value: Optional[Dict] = None
    input_value: Optional[Dict[str, str]] = None
    option: Optional[str] = None
    options: Optional[List[str]] = None
    checked: Optional[bool] = None


class FeishuCallbackEventContextItem(BaseModel):
    url: Optional[str] = None
    preview_token: Optional[str] = None
    open_message_id: str
    open_chat_id: str


class FeishuCallbackEventItem(BaseModel):
    operator: FeishuCallbackEventOperatorItem
    token: str
    action: FeishuCallbackEventActionItem
    host: str
    delivery_type: Optional[str] = None
    context: FeishuCallbackEventContextItem


class FeishuCallbackItem(BaseModel):
    challenge: Optional[str] = None
    schema_: str = Field(default=None, alias='schema')
    header: Optional[FeishuCallbackHeaderItem] = None
    event: Optional[FeishuCallbackEventItem] = None


# 定义一个自定义异常类
class ValidateResponseException(Exception):
    def __init__(self, message='API请求失败'):
        self.message = message
        super().__init__(self.message)

class ApproveCallbackItem(BaseModel):
    """
    飞书审批回调通用模型，可接收任意参数
    """
    # challenge 字段是飞书回调验证必需的
    challenge: Optional[str] = None
    
    # 使用 Dict[str, Any] 接收任意其他字段
    data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    # 允许额外字段
    class Config:
        extra = "allow"  # 允许模型接收未定义的字段
        
        # 支持别名，处理飞书API返回的下划线字段
        validate_by_name = True
