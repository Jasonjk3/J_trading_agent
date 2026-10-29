#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:39
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
异步数据库管理器（向后兼容层）
此文件已迁移到 core.infrastructure.database.async_database
保留此文件仅用于向后兼容，请使用新的导入路径
"""
# 从核心层重新导出，保持向后兼容
from core.infrastructure.database.async_database import AsyncDatabase, create_async_mysql_engine

__all__ = ["AsyncDatabase", "create_async_mysql_engine"]
