#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书 API 模块
提供不同板块的 API 接口
"""
from .base import FeishuBaseApi
from .approval.approval_api import FeishuApprovalApi
from .contact.contact_api import FeishuContactApi
from .bitable.bitable_api import FeishuBitableApi
from .im.im_api import FeishuImApi

__all__ = [
    'FeishuBaseApi',
    'FeishuApprovalApi',
    'FeishuContactApi',
    'FeishuBitableApi',
    'FeishuImApi',
]
