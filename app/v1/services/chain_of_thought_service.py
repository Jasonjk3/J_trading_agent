#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
思维链数据库服务（向后兼容层）
此文件已迁移到 core.infrastructure.persistence.chain_of_thought_service
保留此文件仅用于向后兼容，请使用新的导入路径
"""
# 从核心层重新导出，保持向后兼容
from core.infrastructure.persistence.chain_of_thought_service import ChainOfThoughtService

__all__ = ["ChainOfThoughtService"]
