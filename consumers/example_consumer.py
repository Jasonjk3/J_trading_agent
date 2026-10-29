#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/12/15 10:52
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
示例消费者
展示如何使用 BaseConsumer 创建新的消费者
"""
import os
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

from consumers.base_consumer import (
    BaseConsumer,
    RedisConfig,
    DBConfig,
    ConsumerConfig
)


@dataclass
class ExampleConsumerConfig(ConsumerConfig):
    """示例消费者配置"""
    queue_key: str = field(default_factory=lambda: os.getenv("EXAMPLE_QUEUE_KEY", "example:task_queue"))
    result_key_prefix: str = field(default_factory=lambda: os.getenv("EXAMPLE_RESULT_PREFIX", "example:result:"))
    poll_interval: float = field(default_factory=lambda: float(os.getenv("EXAMPLE_POLL_INTERVAL", "1.0")))
    batch_size: int = field(default_factory=lambda: int(os.getenv("EXAMPLE_BATCH_SIZE", "1")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("EXAMPLE_MAX_RETRIES", "3")))
    worker_count: int = field(default_factory=lambda: int(os.getenv("EXAMPLE_WORKER_COUNT", "2")))
    task_timeout: int = field(default_factory=lambda: int(os.getenv("EXAMPLE_TASK_TIMEOUT", "120")))


@dataclass
class ExampleTaskData:
    """示例任务数据模型"""
    task_id: str
    task_type: str
    data: str
    retry: int = 0
    
    @classmethod
    def from_message(cls, message: Dict[str, Any]) -> "ExampleTaskData":
        """从消息创建任务数据"""
        return cls(
            task_id=message.get("task_id", ""),
            task_type=message.get("task_type", ""),
            data=message.get("metadata", {}).get("data", ""),
            retry=message.get("metadata", {}).get("retry", 0)
        )
    
    def to_message(self) -> Dict[str, Any]:
        """转换为消息格式"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "metadata": {
                "data": self.data,
                "retry": self.retry
            }
        }
    
    def __str__(self) -> str:
        return f"task_id={self.task_id}, data={self.data}"


@dataclass
class ExampleDBConfig(DBConfig):
    """示例数据库配置"""
    host: str = "127.0.0.1"
    port: int = 3306
    username: str = "root"
    password: str = ""
    database: str = "example_db"


class ExampleConsumer(BaseConsumer[ExampleTaskData]):
    """
    示例消费者
    
    展示如何继承 BaseConsumer 创建新的消费者
    """
    
    def __init__(
        self,
        redis_config: Optional[RedisConfig] = None,
        db_config: Optional[ExampleDBConfig] = None,
        consumer_config: Optional[ExampleConsumerConfig] = None
    ):
        # 准备数据库配置字典
        db_configs = {}
        if db_config:
            db_configs["example_db"] = db_config
        
        # 使用默认配置或传入的配置
        if consumer_config is None:
            consumer_config = ExampleConsumerConfig()
        
        # 调用基类初始化
        super().__init__(
            redis_config=redis_config,
            consumer_config=consumer_config,
            db_configs=db_configs
        )
    
    # ==================== 实现抽象方法 ====================
    
    def parse_task_message(self, message: Dict[str, Any]) -> Optional[ExampleTaskData]:
        """解析任务消息为任务数据对象"""
        try:
            return ExampleTaskData.from_message(message)
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"解析任务消息失败: {e}, 消息: {message}")
            return None
    
    async def process_task(self, task: ExampleTaskData):
        """处理任务（核心业务逻辑）"""
        logger.info(f"处理任务: {task.data}")
        
        # 在这里实现具体的业务逻辑
        # 例如：调用API、处理数据、保存结果等
        
        result = {
            "success": True,
            "task_id": task.task_id,
            "processed_data": task.data.upper()  # 示例：转换为大写
        }
        
        # 保存结果
        await self.save_result(task, result)
    
    def get_retry_count(self, task: ExampleTaskData) -> int:
        """获取任务的重试次数"""
        return task.retry
    
    def increment_retry(self, task: ExampleTaskData) -> ExampleTaskData:
        """增加任务的重试次数并返回新任务对象"""
        return ExampleTaskData(
            task_id=task.task_id,
            task_type=task.task_type,
            data=task.data,
            retry=task.retry + 1
        )
    
    def task_to_message(self, task: ExampleTaskData) -> Dict[str, Any]:
        """将任务对象转换为消息格式（用于重试时重新入队）"""
        return task.to_message()
    
    # ==================== 可选：覆盖基类方法 ====================
    
    async def save_result(self, task: ExampleTaskData, result: Dict[str, Any]):
        """
        保存结果（可选：如果需要自定义保存逻辑）
        
        默认实现会保存到Redis，如果需要保存到数据库，可以覆盖此方法
        """
        # 先调用基类方法保存到Redis
        await super().save_result(task, result)
        
        # 如果需要，可以在这里添加数据库保存逻辑
        # async with self.get_session("example_db") as session:
        #     # 保存到数据库
        #     pass


# 使用示例
async def run_example_consumer():
    """运行示例消费者"""
    # 创建配置
    redis_config = RedisConfig()
    db_config = ExampleDBConfig()
    consumer_config = ExampleConsumerConfig(
        worker_count=2
    )
    
    # 创建消费者
    consumer = ExampleConsumer(
        redis_config=redis_config,
        db_config=db_config,
        consumer_config=consumer_config
    )
    
    # 初始化
    if not await consumer.initialize():
        logger.error("消费者初始化失败")
        return
    
    # 启动
    await consumer.start()
    
    try:
        # 保持运行
        while True:
            await asyncio.sleep(60)
            health = await consumer.health_check()
            logger.info(f"健康状态: {health['healthy']}")
    except KeyboardInterrupt:
        pass
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(run_example_consumer())

