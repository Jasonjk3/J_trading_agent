#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
任务管道层
用于从消息中间件（如Redis）接收任务队列，执行任务并存储结果
"""
from consumers.pipeline.config import PipelineConfig

__all__ = ["PipelineManager", "PipelineConfig"]

