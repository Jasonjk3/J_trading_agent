#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/12/15 10:52
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
消费者模块
提供统一的消费者基类和标准实现
"""
from consumers.base_consumer import (
    BaseConsumer,
    RedisConfig,
    DBConfig,
    ConsumerConfig
)
from consumers.asin_correlation_analysis import (
    ASINCorrelationAnalysisConsumer,
    ASINCorrelationConsumerConfig,
    TaskData,
    CrawlerDBConfig,
    ResultDBConfig,
    run_asin_correlation_consumer
)

__all__ = [
    # 基类和配置
    "BaseConsumer",
    "RedisConfig",
    "DBConfig",
    "ConsumerConfig",
    # ASIN相关性分析消费者
    "ASINCorrelationAnalysisConsumer",
    "ASINCorrelationConsumerConfig",
    "TaskData",
    "CrawlerDBConfig",
    "ResultDBConfig",
    "run_asin_correlation_consumer",
]
