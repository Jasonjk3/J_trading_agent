#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
管道配置类
"""
import os
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv, find_dotenv
from loguru import logger

# 加载.env文件
load_dotenv(find_dotenv(".env", True), override=True)


class RedisConfig(BaseModel):
    """Redis连接配置"""
    host: str = Field(default="127.0.0.1", env="REDIS_HOST")
    port: int = Field(default=6379, env="REDIS_PORT")
    password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    db: int = Field(default=0, env="REDIS_DB")
    decode_responses: bool = True
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    retry_on_timeout: bool = True
    health_check_interval: int = 30


class QueueConfig(BaseModel):
    """队列配置"""
    queue_name: str = Field(default="task_queue", description="队列名称")
    priority: int = Field(default=2, description="优先级（数字越大优先级越高）")
    batch_size: int = Field(default=1, description="批量消费大小")
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: int = Field(default=5, description="重试延迟（秒）")


class PipelineConfig(BaseModel):
    """管道配置"""
    redis: RedisConfig = Field(default_factory=RedisConfig)
    queues: List[QueueConfig] = Field(
        default_factory=lambda: [QueueConfig()],
        description="队列配置列表"
    )
    worker_count: int = Field(default=5, ge=1, le=50, description="工作线程数量")
    poll_interval: float = Field(default=1.0, ge=0.1, description="轮询间隔（秒）")
    task_timeout: int = Field(default=300, ge=1, description="任务超时时间（秒）")
    enable_dead_letter_queue: bool = Field(default=True, description="是否启用死信队列")
    dead_letter_queue_name: str = Field(default="task_dead_letter_queue", description="死信队列名称")
    enable_metrics: bool = Field(default=True, description="是否启用指标统计")
    max_batch_size: int = Field(default=10, ge=1, description="最大批量大小")
    
    # 任务类型到Agent ID的映射（可选，如果不提供则根据task_type自动路由）
    task_type_agent_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="任务类型到Agent ID的映射"
    )
    
    @classmethod
    def from_env(cls) -> "PipelineConfig":
        """从环境变量创建配置"""
        # 从环境变量读取Redis配置
        redis_config = RedisConfig(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0"))
        )
        
        return cls(
            redis=redis_config,
            queues=[
                QueueConfig(
                    queue_name=os.getenv("REDIS_QUEUE_NAME", "task_queue"),
                    priority=int(os.getenv("REDIS_QUEUE_PRIORITY", "2")),
                    batch_size=int(os.getenv("REDIS_BATCH_SIZE", "1")),
                    max_retries=int(os.getenv("REDIS_MAX_RETRIES", "3")),
                    retry_delay=int(os.getenv("REDIS_RETRY_DELAY", "5"))
                )
            ],
            worker_count=int(os.getenv("PIPELINE_WORKER_COUNT", "5")),
            poll_interval=float(os.getenv("PIPELINE_POLL_INTERVAL", "1.0")),
            task_timeout=int(os.getenv("PIPELINE_TASK_TIMEOUT", "300")),
            enable_dead_letter_queue=os.getenv("PIPELINE_ENABLE_DLQ", "true").lower() == "true",
            dead_letter_queue_name=os.getenv("PIPELINE_DLQ_NAME", "task_dead_letter_queue"),
            enable_metrics=os.getenv("PIPELINE_ENABLE_METRICS", "true").lower() == "true",
            max_batch_size=int(os.getenv("PIPELINE_MAX_BATCH_SIZE", "10"))
        )
    
    def get_redis_url(self) -> str:
        """获取Redis连接URL"""
        password_part = f":{self.redis.password}@" if self.redis.password else ""
        return f"redis://{password_part}{self.redis.host}:{self.redis.port}/{self.redis.db}"

