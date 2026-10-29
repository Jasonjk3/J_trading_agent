#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书 SDK
提供飞书开放平台 API 的统一封装
"""
from .feishu_sdk import FeishuSDK
from .base import (
    FeishuBase,
    FeishuHttpClient,
    ResponseType,
    ToastType,
    CardType,
    ReceiveIdType,
    MsgType,
    ImageType,
    FileType,
    LocaleType,
    UserIdType,
    ApprovalStatus,
    ValidateResponseException,
)
from .apis import (
    FeishuBaseApi,
    FeishuApprovalApi,
    FeishuContactApi,
    FeishuBitableApi,
    FeishuImApi,
)
from .bot import FeishuAppBot, FeishuGroupBot

__all__ = [
    # 主 SDK
    'FeishuSDK',
    # 基础功能
    'FeishuBase',
    'FeishuHttpClient',
    # 公共类型
    'ResponseType',
    'ToastType',
    'CardType',
    'ReceiveIdType',
    'MsgType',
    'ImageType',
    'FileType',
    'LocaleType',
    'UserIdType',
    'ApprovalStatus',
    'ValidateResponseException',
    # API 板块
    'FeishuBaseApi',
    'FeishuApprovalApi',
    'FeishuContactApi',
    'FeishuBitableApi',
    'FeishuImApi',
    # 机器人
    'FeishuAppBot',
    'FeishuGroupBot',
]
