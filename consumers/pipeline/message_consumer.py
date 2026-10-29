#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
Redis消息消费者
"""
import asyncio
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

try:
    import redis.asyncio as aioredis
except ImportError:
    logger.error("请安装redis库: pip install redis")
    raise


class MessageConsumer:
    """Redis消息消费者"""
    
    def __init__(
        self,
        redis_config: "RedisConfig",
        queue_configs: List["QueueConfig"],
        poll_interval: float = 1.0
    ):
        """
        初始化消息消费者
        
        Args:
            redis_config: Redis配置
            queue_configs: 队列配置列表
            poll_interval: 轮询间隔（秒）
        """
        self.redis_config = redis_config
        self.queue_configs = sorted(
            queue_configs,
            key=lambda q: q.priority,
            reverse=True
        )  # 按优先级排序
        self.poll_interval = poll_interval
        self.redis_client: Optional[aioredis.Redis] = None
        self._running = False
        self._reconnect_delay = 5  # 重连延迟（秒）
        self._max_reconnect_delay = 60  # 最大重连延迟（秒）
    
    async def connect(self):
        """连接Redis"""
        try:
            self.redis_client = aioredis.Redis(
                host=self.redis_config.host,
                port=self.redis_config.port,
                password=self.redis_config.password,
                db=self.redis_config.db,
                decode_responses=self.redis_config.decode_responses,
                socket_timeout=self.redis_config.socket_timeout,
                socket_connect_timeout=self.redis_config.socket_connect_timeout,
                retry_on_timeout=self.redis_config.retry_on_timeout,
                health_check_interval=self.redis_config.health_check_interval
            )
            # 测试连接
            await self.redis_client.ping()
            logger.info(f"Redis连接成功: {self.redis_config.host}:{self.redis_config.port}")
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise
    
    async def disconnect(self):
        """断开Redis连接"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("Redis连接已断开")
    
    async def consume(self) -> Optional[Dict[str, Any]]:
        """
        消费消息（单个）
        
        Returns:
            消费的消息，如果没有消息则返回None
        """
        if not self._running:
            return None
        
        if not self.redis_client:
            await self._reconnect()
            if not self.redis_client:
                return None
        
        try:
            # 按优先级顺序尝试从各个队列消费
            for queue_config in self.queue_configs:
                try:
                    # 使用BLPOP阻塞式获取消息（支持超时）
                    result = await self.redis_client.blpop(
                        queue_config.queue_name,
                        timeout=int(self.poll_interval)
                    )
                    
                    if result:
                        queue_name, message_data = result
                        try:
                            message = json.loads(message_data)
                            # 验证消息格式
                            if self._validate_message(message):
                                return message
                            else:
                                logger.warning(f"消息格式验证失败: {message}")
                                # 将无效消息发送到死信队列
                                await self._send_to_dead_letter_queue(message, "Invalid message format")
                        except json.JSONDecodeError as e:
                            logger.error(f"消息JSON解析失败: {e}, 数据: {message_data}")
                            await self._send_to_dead_letter_queue(
                                {"raw_data": message_data},
                                f"JSON decode error: {str(e)}"
                            )
                except asyncio.TimeoutError:
                    # 超时是正常的，继续下一个队列
                    continue
                except Exception as e:
                    logger.error(f"从队列 {queue_config.queue_name} 消费消息失败: {e}")
                    # 如果连接错误，尝试重连
                    if "Connection" in str(type(e).__name__):
                        await self._reconnect()
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"消费消息时发生错误: {e}")
            await self._reconnect()
            return None
    
    async def consume_batch(self, max_batch_size: int = 10) -> List[Dict[str, Any]]:
        """
        批量消费消息
        
        Args:
            max_batch_size: 最大批量大小
            
        Returns:
            消费的消息列表
        """
        if not self._running:
            return []
        
        if not self.redis_client:
            await self._reconnect()
            if not self.redis_client:
                return []
        
        messages = []
        
        try:
            # 按优先级顺序尝试从各个队列批量消费
            for queue_config in self.queue_configs:
                try:
                    # 批量获取消息（非阻塞）
                    for _ in range(min(max_batch_size, queue_config.batch_size)):
                        message_data = await self.redis_client.lpop(queue_config.queue_name)
                        if message_data:
                            try:
                                message = json.loads(message_data)
                                if self._validate_message(message):
                                    messages.append(message)
                                else:
                                    logger.warning(f"消息格式验证失败: {message}")
                                    await self._send_to_dead_letter_queue(message, "Invalid message format")
                            except json.JSONDecodeError as e:
                                logger.error(f"消息JSON解析失败: {e}")
                                await self._send_to_dead_letter_queue(
                                    {"raw_data": message_data},
                                    f"JSON decode error: {str(e)}"
                                )
                        else:
                            break
                    
                    if messages:
                        break  # 如果获取到消息，优先处理
                        
                except Exception as e:
                    logger.error(f"从队列 {queue_config.queue_name} 批量消费消息失败: {e}")
                    if "Connection" in str(type(e).__name__):
                        await self._reconnect()
                    continue
            
            return messages
            
        except Exception as e:
            logger.error(f"批量消费消息时发生错误: {e}")
            await self._reconnect()
            return []
    
    def _validate_message(self, message: Dict[str, Any]) -> bool:
        """
        验证消息格式
        
        Args:
            message: 消息字典
            
        Returns:
            是否有效
        """
        # 必填字段：task_id, task_type, metadata（metadata可以为空但必须存在）
        required_fields = ["task_id", "task_type"]
        if not all(field in message for field in required_fields):
            return False
        # metadata必须存在（可以为空对象）
        if "metadata" not in message:
            return False
        return True
    
    async def _send_to_dead_letter_queue(
        self,
        message: Dict[str, Any],
        error_reason: str
    ):
        """发送消息到死信队列"""
        if not self.redis_client:
            return
        
        try:
            dead_letter_message = {
                "original_message": message,
                "error_reason": error_reason,
                "failed_at": datetime.now().isoformat()
            }
            await self.redis_client.lpush(
                "task_dead_letter_queue",
                json.dumps(dead_letter_message, ensure_ascii=False)
            )
            logger.warning(f"消息已发送到死信队列: {error_reason}")
        except Exception as e:
            logger.error(f"发送消息到死信队列失败: {e}")
    
    async def _reconnect(self):
        """重连Redis"""
        if self._running:
            logger.info("尝试重连Redis...")
            try:
                await self.disconnect()
                await asyncio.sleep(self._reconnect_delay)
                await self.connect()
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay
                )
            except Exception as e:
                logger.error(f"Redis重连失败: {e}")
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self._max_reconnect_delay
                )
    
    def start(self):
        """启动消费者"""
        self._running = True
    
    def stop(self):
        """停止消费者"""
        self._running = False
    
    async def get_queue_length(self, queue_name: str) -> int:
        """获取队列长度"""
        if not self.redis_client:
            return 0
        try:
            return await self.redis_client.llen(queue_name)
        except Exception as e:
            logger.error(f"获取队列长度失败: {e}")
            return 0
    
    async def health_check(self) -> bool:
        """健康检查"""
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis健康检查失败: {e}")
            return False

