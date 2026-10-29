#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/12/15 10:52
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
消费者基类
提供统一的消费者标准实现，方便横向扩展
"""
import os
import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TypeVar, Generic
from datetime import datetime
from dataclasses import dataclass, field
from loguru import logger

try:
    import redis.asyncio as aioredis
except ImportError:
    logger.error("请安装redis库: pip install redis")
    raise

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from dotenv import load_dotenv, find_dotenv

# 加载环境变量
load_dotenv(find_dotenv(".env", True), override=True)

# 任务数据类型变量
T = TypeVar('T')


@dataclass
class RedisConfig:
    """Redis连接配置（从.env读取）"""
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "11")))
    decode_responses: bool = True
    socket_timeout: int = 10
    socket_connect_timeout: int = 10


@dataclass
class DBConfig:
    """数据库配置基类"""
    host: str = ""
    port: int = 3306
    username: str = ""
    password: str = ""
    database: str = ""
    
    def get_async_url(self) -> str:
        """获取异步数据库连接URL"""
        return (
            f"mysql+aiomysql://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
            f"?charset=utf8mb4"
        )


@dataclass
class ConsumerConfig:
    """
    消费者配置基类
    
    每个消费者应该定义自己的配置类，继承此类或使用相同字段结构
    """
    queue_key: str = "ai:Ecomlinker:task_queue"
    result_key_prefix: str = "ai:Ecomlinker:result:"
    poll_interval: float = 1.0
    batch_size: int = 1
    max_retries: int = 3
    worker_count: int = 3
    task_timeout: int = 120  # 秒


class BaseConsumer(ABC, Generic[T]):
    """
    消费者基类
    
    提供统一的消费者实现，包括：
    - Redis连接管理
    - 数据库连接管理（支持多个数据库）
    - 工作线程管理
    - 任务消费逻辑
    - 重试机制
    - 统计信息
    - 健康检查
    - 生命周期管理
    
    子类需要实现：
    - parse_task_message: 解析任务消息为任务数据对象
    - process_task: 处理具体任务逻辑
    - save_result: 保存结果（可选，基类提供默认实现）
    """
    
    def __init__(
        self,
        redis_config: Optional[RedisConfig] = None,
        consumer_config: Optional[ConsumerConfig] = None,
        db_configs: Optional[Dict[str, DBConfig]] = None
    ):
        """
        初始化消费者
        
        Args:
            redis_config: Redis配置
            consumer_config: 消费者配置
            db_configs: 数据库配置字典，key为数据库名称，value为DBConfig
                       例如: {"crawler": CrawlerDBConfig(), "result": ResultDBConfig()}
        """
        self.redis_config = redis_config or RedisConfig()
        self.consumer_config = consumer_config or ConsumerConfig()
        self.db_configs = db_configs or {}
        
        # Redis客户端
        self.redis_client: Optional[aioredis.Redis] = None
        
        # 数据库引擎和会话工厂字典
        self.db_engines: Dict[str, Any] = {}
        self.session_factories: Dict[str, Any] = {}
        
        # 运行状态
        self._running = False
        self._workers: List[asyncio.Task] = []
        
        # 统计信息
        self.stats = {
            "total_consumed": 0,
            "total_succeeded": 0,
            "total_failed": 0,
            "total_retried": 0,
            "start_time": None
        }
    
    async def initialize(self) -> bool:
        """初始化消费者"""
        try:
            # 初始化Redis连接
            await self._connect_redis()
            
            # 初始化数据库连接
            await self._connect_databases()
            
            # 子类特定的初始化
            if hasattr(self, '_custom_initialize'):
                if not await self._custom_initialize():
                    logger.error("子类初始化失败")
                    return False
            
            logger.info(f"{self.__class__.__name__} 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"消费者初始化失败: {e}", exc_info=True)
            return False
    
    async def _connect_redis(self):
        """连接Redis"""
        try:
            self.redis_client = aioredis.Redis(
                host=self.redis_config.host,
                port=self.redis_config.port,
                password=self.redis_config.password,
                db=self.redis_config.db,
                decode_responses=self.redis_config.decode_responses,
                socket_timeout=self.redis_config.socket_timeout,
                socket_connect_timeout=self.redis_config.socket_connect_timeout
            )
            await self.redis_client.ping()
            logger.info(f"Redis连接成功: {self.redis_config.host}:{self.redis_config.port} db={self.redis_config.db}")
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise
    
    async def _connect_databases(self):
        """连接所有配置的数据库"""
        for db_name, db_config in self.db_configs.items():
            try:
                db_url = db_config.get_async_url()
                engine = create_async_engine(
                    db_url,
                    pool_size=10,
                    max_overflow=5,
                    pool_pre_ping=True,
                    echo=os.getenv("SQL_DEBUG", "").lower() == "true"
                )
                session_factory = sessionmaker(
                    bind=engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                    autoflush=False
                )
                
                # 测试连接
                async with session_factory() as session:
                    await session.execute(text("SELECT 1"))
                
                self.db_engines[db_name] = engine
                self.session_factories[db_name] = session_factory
                
                logger.info(f"数据库连接成功 [{db_name}]: {db_config.host}:{db_config.port}/{db_config.database}")
            except Exception as e:
                logger.error(f"数据库连接失败 [{db_name}]: {e}")
                raise
    
    def get_session(self, db_name: str) -> AsyncSession:
        """
        获取指定数据库的会话
        
        Args:
            db_name: 数据库名称（在db_configs中配置的key）
            
        Returns:
            AsyncSession实例
        """
        if db_name not in self.session_factories:
            raise ValueError(f"数据库 '{db_name}' 未配置")
        return self.session_factories[db_name]()
    
    async def start(self):
        """启动消费者"""
        if self._running:
            logger.warning("消费者已在运行")
            return
        
        self._running = True
        self.stats["start_time"] = datetime.now()
        
        # 启动工作线程
        for i in range(self.consumer_config.worker_count):
            worker = asyncio.create_task(
                self._worker_loop(f"worker-{i+1}")
            )
            self._workers.append(worker)
        
        logger.info(f"消费者已启动，工作线程数: {self.consumer_config.worker_count}")
    
    async def stop(self, timeout: float = 30.0):
        """停止消费者"""
        if not self._running:
            return
        
        logger.info("正在停止消费者...")
        self._running = False
        
        # 等待工作线程完成
        if self._workers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning("停止超时，强制取消工作线程")
                for worker in self._workers:
                    worker.cancel()
        
        self._workers.clear()
        
        # 关闭连接
        if self.redis_client:
            await self.redis_client.close()
        
        for engine in self.db_engines.values():
            await engine.dispose()
        
        # 子类特定的清理
        if hasattr(self, '_custom_cleanup'):
            await self._custom_cleanup()
        
        logger.info("消费者已停止")
        self._print_stats()
    
    async def _worker_loop(self, worker_name: str):
        """工作线程主循环"""
        logger.info(f"工作线程 {worker_name} 已启动")
        
        while self._running:
            try:
                # 消费消息
                task_data = await self._consume_task()
                
                if task_data:
                    await self._process_task_wrapper(task_data, worker_name)
                else:
                    # 无消息时等待
                    await asyncio.sleep(self.consumer_config.poll_interval)
                    
            except asyncio.CancelledError:
                logger.info(f"工作线程 {worker_name} 被取消")
                break
            except Exception as e:
                logger.error(f"工作线程 {worker_name} 发生错误: {e}", exc_info=True)
                await asyncio.sleep(self.consumer_config.poll_interval)
        
        logger.info(f"工作线程 {worker_name} 已停止")
    
    async def _consume_task(self) -> Optional[T]:
        """从队列消费任务"""
        try:
            # 使用BLPOP阻塞式获取消息
            result = await self.redis_client.blpop(
                self.consumer_config.queue_key,
                timeout=int(self.consumer_config.poll_interval)
            )
            
            if result:
                queue_name, message_data = result
                try:
                    data = json.loads(message_data)
                    task = self.parse_task_message(data)
                    if task:
                        self.stats["total_consumed"] += 1
                        logger.debug(f"消费任务: {task}")
                        return task
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(f"解析任务数据失败: {e}, 数据: {message_data}")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"消费任务失败: {e}")
            return None
    
    async def _process_task_wrapper(self, task: T, worker_name: str):
        """任务处理包装器（处理超时和异常）"""
        try:
            logger.info(f"[{worker_name}] 处理任务: {task}")
            
            # 执行任务（带超时）
            await asyncio.wait_for(
                self.process_task(task),
                timeout=self.consumer_config.task_timeout
            )
            
            self.stats["total_succeeded"] += 1
            logger.info(f"[{worker_name}] 任务完成: {task}")
            
        except asyncio.TimeoutError:
            logger.error(f"[{worker_name}] 任务超时: {task}")
            await self._handle_task_failure(task, "任务执行超时")
            
        except Exception as e:
            logger.error(f"[{worker_name}] 处理任务失败: {e}", exc_info=True)
            await self._handle_task_failure(task, str(e))
    
    async def _handle_task_failure(self, task: T, error_msg: str):
        """
        处理任务失败
        
        Args:
            task: 任务数据
            error_msg: 错误信息
        """
        self.stats["total_failed"] += 1
        
        # 检查是否需要重试
        retry_count = self.get_retry_count(task)
        if retry_count < self.consumer_config.max_retries:
            # 增加重试次数
            updated_task = self.increment_retry(task)
            self.stats["total_retried"] += 1
            
            # 重新放入队列
            await self.redis_client.rpush(
                self.consumer_config.queue_key,
                json.dumps(self.task_to_message(updated_task), ensure_ascii=False)
            )
            logger.warning(
                f"任务重试 ({retry_count + 1}/{self.consumer_config.max_retries}): "
                f"{task}, 错误: {error_msg}"
            )
        else:
            # 超过最大重试次数，保存失败结果
            await self.save_failure_result(task, error_msg)
            logger.error(
                f"任务最终失败，已达到最大重试次数: {task}, 错误: {error_msg}"
            )
    
    def _print_stats(self):
        """打印统计信息"""
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds() if self.stats["start_time"] else 0
        
        logger.info("=" * 60)
        logger.info(f"{self.__class__.__name__} 统计信息")
        logger.info(f"运行时间: {elapsed:.2f} 秒")
        logger.info(f"总消费数: {self.stats['total_consumed']}")
        logger.info(f"成功数: {self.stats['total_succeeded']}")
        logger.info(f"失败数: {self.stats['total_failed']}")
        logger.info(f"重试数: {self.stats['total_retried']}")
        if elapsed > 0:
            logger.info(f"处理速率: {self.stats['total_consumed'] / elapsed:.2f} 任务/秒")
        logger.info("=" * 60)
    
    async def get_queue_length(self) -> int:
        """获取队列长度"""
        if not self.redis_client:
            return 0
        try:
            return await self.redis_client.llen(self.consumer_config.queue_key)
        except Exception as e:
            logger.error(f"获取队列长度失败: {e}")
            return 0
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        redis_ok = False
        dbs_ok = {}
        
        try:
            if self.redis_client:
                await self.redis_client.ping()
                redis_ok = True
        except Exception:
            pass
        
        for db_name in self.db_configs.keys():
            try:
                if db_name in self.session_factories:
                    async with self.session_factories[db_name]() as session:
                        await session.execute(text("SELECT 1"))
                        dbs_ok[db_name] = True
                else:
                    dbs_ok[db_name] = False
            except Exception:
                dbs_ok[db_name] = False
        
        all_dbs_ok = all(dbs_ok.values()) if dbs_ok else True
        
        return {
            "healthy": redis_ok and all_dbs_ok and self._running,
            "redis_connected": redis_ok,
            "databases_connected": dbs_ok,
            "consumer_running": self._running,
            "worker_count": len(self._workers),
            "stats": self.stats.copy()
        }
    
    # ==================== 抽象方法（子类必须实现）====================
    
    @abstractmethod
    def parse_task_message(self, message: Dict[str, Any]) -> Optional[T]:
        """
        解析任务消息为任务数据对象
        
        Args:
            message: 从Redis队列获取的原始消息（JSON解析后的字典）
            
        Returns:
            任务数据对象，如果解析失败返回None
        """
        pass
    
    @abstractmethod
    async def process_task(self, task: T):
        """
        处理任务（核心业务逻辑）
        
        Args:
            task: 任务数据对象
        """
        pass
    
    @abstractmethod
    def get_retry_count(self, task: T) -> int:
        """
        获取任务的重试次数
        
        Args:
            task: 任务数据对象
            
        Returns:
            重试次数
        """
        pass
    
    @abstractmethod
    def increment_retry(self, task: T) -> T:
        """
        增加任务的重试次数并返回新任务对象
        
        Args:
            task: 任务数据对象
            
        Returns:
            更新后的任务数据对象
        """
        pass
    
    @abstractmethod
    def task_to_message(self, task: T) -> Dict[str, Any]:
        """
        将任务对象转换为消息格式（用于重试时重新入队）
        
        Args:
            task: 任务数据对象
            
        Returns:
            消息字典（包含task_id, task_type, metadata等）
        """
        pass
    
    # ==================== 可选方法（子类可以覆盖）====================
    
    async def save_result(self, task: T, result: Dict[str, Any]):
        """
        保存结果（默认实现：保存到Redis）
        
        Args:
            task: 任务数据对象
            result: 结果字典
        """
        try:
            # 默认实现：保存到Redis
            task_id = str(task)  # 子类可以覆盖此方法获取task_id
            result_key = f"{self.consumer_config.result_key_prefix}{task_id}"
            result_data = {
                **result,
                "processed_at": datetime.now().isoformat(),
                "task": str(task)
            }
            
            await self.redis_client.set(
                result_key,
                json.dumps(result_data, ensure_ascii=False),
                ex=86400 * 7  # 保留7天
            )
            
            # 同时推送到结果队列
            result_queue_key = f"{self.consumer_config.result_key_prefix}queue"
            await self.redis_client.rpush(
                result_queue_key,
                json.dumps(result_data, ensure_ascii=False)
            )
            
            logger.debug(f"Redis结果已保存: {result_key}")
            
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
    
    async def save_failure_result(self, task: T, error_msg: str):
        """
        保存失败结果
        
        Args:
            task: 任务数据对象
            error_msg: 错误信息
        """
        failure_result = {
            "success": False,
            "error": error_msg,
            "failed": True
        }
        await self.save_result(task, failure_result)

