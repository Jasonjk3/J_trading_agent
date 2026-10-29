#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
LLM 使用量追踪器
核心功能：
1. 拦截 LLM 调用，记录 token 使用量
2. 异步批量写入数据库
3. 支持上下文注入（agent_name, task_type 等）
"""
import asyncio
import logging
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from core.llm.base.cost_calculator import calculate_cost, get_model_provider
from core.llm.base.token_counter import count_tokens

logger = logging.getLogger(__name__)

# ============================================================================
# 上下文变量定义
# ============================================================================

# 当前 Agent 名称
_current_agent_name: ContextVar[Optional[str]] = ContextVar("current_agent_name", default=None)

# 当前任务类型
_current_task_type: ContextVar[Optional[str]] = ContextVar("current_task_type", default=None)

# 当前用户 ID
_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)

# 当前会话 ID
_current_session_id: ContextVar[Optional[str]] = ContextVar("current_session_id", default=None)

# 额外数据
_current_extra_data: ContextVar[Optional[Dict[str, Any]]] = ContextVar("current_extra_data", default=None)


# ============================================================================
# 上下文管理函数
# ============================================================================

@contextmanager
def track_context(
    agent_name: Optional[str] = None,
    task_type: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None
):
    """
    上下文管理器：设置 LLM 调用的上下文信息
    
    使用示例：
        with track_context(agent_name="competitor_analysis_agent", task_type="analysis"):
            result = llm.invoke(prompt)
    
    Args:
        agent_name: Agent 名称
        task_type: 任务类型
        user_id: 用户 ID
        session_id: 会话 ID
        extra_data: 额外数据
    """
    # 保存旧值
    old_agent_name = _current_agent_name.get()
    old_task_type = _current_task_type.get()
    old_user_id = _current_user_id.get()
    old_session_id = _current_session_id.get()
    old_extra_data = _current_extra_data.get()
    
    # 设置新值
    if agent_name is not None:
        _current_agent_name.set(agent_name)
    if task_type is not None:
        _current_task_type.set(task_type)
    if user_id is not None:
        _current_user_id.set(user_id)
    if session_id is not None:
        _current_session_id.set(session_id)
    if extra_data is not None:
        _current_extra_data.set(extra_data)
    
    try:
        yield
    finally:
        # 恢复旧值
        _current_agent_name.set(old_agent_name)
        _current_task_type.set(old_task_type)
        _current_user_id.set(old_user_id)
        _current_session_id.set(old_session_id)
        _current_extra_data.set(old_extra_data)


def set_agent_context(agent_name: str, task_type: Optional[str] = None):
    """设置 Agent 上下文（非 context manager 方式）"""
    _current_agent_name.set(agent_name)
    if task_type:
        _current_task_type.set(task_type)


def get_current_context() -> Dict[str, Any]:
    """获取当前上下文信息"""
    return {
        "agent_name": _current_agent_name.get(),
        "task_type": _current_task_type.get(),
        "user_id": _current_user_id.get(),
        "session_id": _current_session_id.get(),
        "extra_data": _current_extra_data.get(),
    }


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class UsageRecord:
    """LLM 使用记录"""
    request_id: str
    model_name: str
    model_provider: str
    agent_name: Optional[str] = None
    task_type: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    cost_cny: Decimal = field(default_factory=lambda: Decimal("0"))
    response_time_ms: int = 0
    status: str = "success"
    error_message: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    extra_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "cost_cny": self.cost_cny,
            "response_time_ms": self.response_time_ms,
            "status": self.status,
            "error_message": self.error_message,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "extra_data": self.extra_data,
        }


# ============================================================================
# 使用量追踪器
# ============================================================================

class UsageTracker:
    """
    LLM 使用量追踪器
    
    特性：
    1. 异步队列：调用记录先写入内存队列，不阻塞主业务
    2. 批量写入：后台 Worker 定时批量入库
    3. 上下文感知：自动获取 agent_name、task_type 等上下文信息
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        flush_interval: float = 5.0,
        max_queue_size: int = 10000,
        enabled: bool = True
    ):
        """
        初始化追踪器
        
        Args:
            batch_size: 批量写入的阈值
            flush_interval: 定时刷新间隔（秒）
            max_queue_size: 队列最大容量
            enabled: 是否启用追踪
        """
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_queue_size = max_queue_size
        self.enabled = enabled
        
        # 内存队列
        self._queue: List[UsageRecord] = []
        self._queue_lock = threading.Lock()
        
        # 统计信息
        self._total_records = 0
        self._total_flushed = 0
        self._flush_errors = 0
        
        # 后台任务
        self._worker_task: Optional[asyncio.Task] = None
        self._stop_event = threading.Event()
        
        # 数据库会话工厂（延迟初始化）
        self._db_initialized = False
        self._async_db = None
        
        # 回调函数（用于测试或自定义处理）
        self._on_flush_callback: Optional[Callable[[List[UsageRecord]], None]] = None
    
    def _init_database(self):
        """延迟初始化数据库连接"""
        if self._db_initialized:
            return
        
        try:
            from configs.config import app_config
            from core.infrastructure.database.async_database import AsyncDatabase
            self._async_db = AsyncDatabase(app_config)
            self._db_initialized = True
            logger.info("UsageTracker 数据库连接初始化成功")
        except Exception as e:
            logger.error(f"UsageTracker 数据库连接初始化失败: {e}")
            self._db_initialized = False
    
    def record(
        self,
        model_name: str,
        prompt: str,
        completion: str,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        response_time_ms: int = 0,
        status: str = "success",
        error_message: Optional[str] = None,
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        记录一次 LLM 调用
        
        Args:
            model_name: 模型名称
            prompt: 输入提示
            completion: 生成的回复
            prompt_tokens: 输入 token 数（如果 API 返回了 usage）
            completion_tokens: 输出 token 数（如果 API 返回了 usage）
            response_time_ms: 响应时间（毫秒）
            status: 状态（success, failed, timeout）
            error_message: 错误信息
            agent_name: Agent 名称（如果为 None 则从上下文获取）
            task_type: 任务类型（如果为 None 则从上下文获取）
            user_id: 用户 ID（如果为 None 则从上下文获取）
            session_id: 会话 ID（如果为 None 则从上下文获取）
            extra_data: 额外数据
            
        Returns:
            request_id（如果成功记录）
        """
        if not self.enabled:
            return None
        
        # 生成请求 ID
        request_id = str(uuid.uuid4())
        
        # 从上下文获取缺失的信息
        ctx = get_current_context()
        agent_name = agent_name or ctx.get("agent_name")
        task_type = task_type or ctx.get("task_type")
        user_id = user_id or ctx.get("user_id")
        session_id = session_id or ctx.get("session_id")
        
        # 合并 extra_data
        final_extra_data = ctx.get("extra_data") or {}
        if extra_data:
            final_extra_data.update(extra_data)
        
        # 计算 token 数（如果未提供）
        if prompt_tokens is None:
            prompt_tokens = count_tokens(prompt, model_name)
        if completion_tokens is None:
            completion_tokens = count_tokens(completion, model_name)
        total_tokens = prompt_tokens + completion_tokens
        
        # 计算费用
        cost_usd, cost_cny = calculate_cost(prompt_tokens, completion_tokens, model_name)
        
        # 获取提供商
        model_provider = get_model_provider(model_name)
        
        # 创建记录
        record = UsageRecord(
            request_id=request_id,
            model_name=model_name,
            model_provider=model_provider,
            agent_name=agent_name,
            task_type=task_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            cost_cny=cost_cny,
            response_time_ms=response_time_ms,
            status=status,
            error_message=error_message,
            user_id=user_id,
            session_id=session_id,
            created_at=datetime.now(),
            extra_data=final_extra_data if final_extra_data else None,
        )
        
        # 添加到队列
        self._add_to_queue(record)
        
        return request_id
    
    def record_from_usage(
        self,
        model_name: str,
        usage: Dict[str, int],
        response_time_ms: int = 0,
        status: str = "success",
        error_message: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """
        从 API 返回的 usage 信息记录调用
        
        Args:
            model_name: 模型名称
            usage: API 返回的 usage 字典，通常包含 prompt_tokens, completion_tokens
            response_time_ms: 响应时间
            status: 状态
            error_message: 错误信息
            **kwargs: 其他参数传递给 record()
            
        Returns:
            request_id
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        
        return self.record(
            model_name=model_name,
            prompt="",  # 不再需要文本计算
            completion="",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            response_time_ms=response_time_ms,
            status=status,
            error_message=error_message,
            **kwargs
        )
    
    def _add_to_queue(self, record: UsageRecord):
        """将记录添加到队列"""
        with self._queue_lock:
            if len(self._queue) >= self.max_queue_size:
                # 队列满了，丢弃最旧的记录
                self._queue.pop(0)
                logger.warning("UsageTracker 队列已满，丢弃最旧的记录")
            
            self._queue.append(record)
            self._total_records += 1
            
            # 检查是否需要立即刷新
            if len(self._queue) >= self.batch_size:
                # 触发异步刷新
                self._trigger_flush()
    
    def _trigger_flush(self):
        """触发刷新（非阻塞）"""
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._flush_async())
        except RuntimeError:
            # 没有运行的事件循环，使用同步方式
            self._flush_sync()
    
    def _flush_sync(self):
        """同步刷新（用于非异步上下文）"""
        records = self._get_batch()
        if not records:
            return
        
        if self._on_flush_callback:
            try:
                self._on_flush_callback(records)
                self._total_flushed += len(records)
            except Exception as e:
                logger.error(f"刷新回调执行失败: {e}")
                self._flush_errors += 1
        else:
            # 创建新的事件循环来执行异步写入
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._write_to_db(records))
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"同步刷新数据库写入失败: {e}")
                self._flush_errors += 1
    
    async def _flush_async(self):
        """异步刷新"""
        records = self._get_batch()
        if not records:
            return
        
        if self._on_flush_callback:
            try:
                self._on_flush_callback(records)
                self._total_flushed += len(records)
            except Exception as e:
                logger.error(f"刷新回调执行失败: {e}")
                self._flush_errors += 1
        else:
            await self._write_to_db(records)
    
    def _get_batch(self) -> List[UsageRecord]:
        """获取一批记录用于写入"""
        with self._queue_lock:
            if not self._queue:
                return []
            
            batch = self._queue[:self.batch_size]
            self._queue = self._queue[self.batch_size:]
            return batch
    
    async def _write_to_db(self, records: List[UsageRecord]):
        """批量写入数据库"""
        if not records:
            return
        
        # 确保数据库已初始化
        self._init_database()
        
        if not self._async_db:
            logger.warning("数据库未初始化，跳过写入")
            return
        
        try:
            from models.inner_models.llm_monitor_model import LLMUsageLog
            
            async with self._async_db.get_session() as session:
                # 批量插入
                for record in records:
                    log_entry = LLMUsageLog(
                        request_id=record.request_id,
                        model_name=record.model_name,
                        model_provider=record.model_provider,
                        agent_name=record.agent_name,
                        task_type=record.task_type,
                        prompt_tokens=record.prompt_tokens,
                        completion_tokens=record.completion_tokens,
                        total_tokens=record.total_tokens,
                        cost_usd=record.cost_usd,
                        cost_cny=record.cost_cny,
                        response_time_ms=record.response_time_ms,
                        status=record.status,
                        error_message=record.error_message,
                        user_id=record.user_id,
                        session_id=record.session_id,
                        created_at=record.created_at,
                        extra_data=record.extra_data,
                    )
                    session.add(log_entry)
                
                # 提交由 context manager 自动处理
            
            self._total_flushed += len(records)
            logger.debug(f"成功写入 {len(records)} 条 LLM 使用记录")
            
        except Exception as e:
            logger.error(f"批量写入数据库失败: {e}")
            self._flush_errors += 1
            # 将失败的记录放回队列（可选）
            # with self._queue_lock:
            #     self._queue = records + self._queue
    
    async def start_worker(self):
        """启动后台刷新 Worker"""
        if self._worker_task is not None:
            logger.warning("Worker 已经在运行")
            return
        
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(f"UsageTracker Worker 已启动，刷新间隔: {self.flush_interval}s")
    
    async def stop_worker(self):
        """停止后台 Worker"""
        if self._worker_task is None:
            return
        
        self._stop_event.set()
        self._worker_task.cancel()
        
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        
        self._worker_task = None
        
        # 最后刷新一次
        await self._flush_async()
        logger.info("UsageTracker Worker 已停止")
    
    async def _worker_loop(self):
        """Worker 主循环"""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_async()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker 循环出错: {e}")
    
    def flush_now(self):
        """立即刷新（同步）"""
        while True:
            records = self._get_batch()
            if not records:
                break
            
            if self._on_flush_callback:
                self._on_flush_callback(records)
                self._total_flushed += len(records)
            else:
                # 使用同步方式
                self._flush_sync()
    
    async def flush_now_async(self):
        """立即刷新（异步）"""
        while True:
            records = self._get_batch()
            if not records:
                break
            await self._write_to_db(records)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._queue_lock:
            queue_size = len(self._queue)
        
        return {
            "enabled": self.enabled,
            "queue_size": queue_size,
            "total_records": self._total_records,
            "total_flushed": self._total_flushed,
            "flush_errors": self._flush_errors,
            "batch_size": self.batch_size,
            "flush_interval": self.flush_interval,
        }
    
    def set_flush_callback(self, callback: Callable[[List[UsageRecord]], None]):
        """设置刷新回调（用于测试）"""
        self._on_flush_callback = callback


# ============================================================================
# 全局实例
# ============================================================================

_usage_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    """获取全局使用量追踪器实例"""
    global _usage_tracker
    if _usage_tracker is None:
        _usage_tracker = UsageTracker()
    return _usage_tracker


def init_usage_tracker(
    batch_size: int = 100,
    flush_interval: float = 5.0,
    enabled: bool = True
) -> UsageTracker:
    """
    初始化全局使用量追踪器
    
    Args:
        batch_size: 批量写入阈值
        flush_interval: 刷新间隔（秒）
        enabled: 是否启用
        
    Returns:
        UsageTracker 实例
    """
    global _usage_tracker
    _usage_tracker = UsageTracker(
        batch_size=batch_size,
        flush_interval=flush_interval,
        enabled=enabled
    )
    return _usage_tracker


# ============================================================================
# 便捷函数
# ============================================================================

def record_usage(
    model_name: str,
    prompt: str,
    completion: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    response_time_ms: int = 0,
    status: str = "success",
    error_message: Optional[str] = None,
    **kwargs
) -> Optional[str]:
    """
    便捷函数：记录 LLM 使用
    
    Args:
        model_name: 模型名称
        prompt: 输入提示
        completion: 生成的回复
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        response_time_ms: 响应时间
        status: 状态
        error_message: 错误信息
        **kwargs: 其他参数
        
    Returns:
        request_id
    """
    return get_usage_tracker().record(
        model_name=model_name,
        prompt=prompt,
        completion=completion,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        response_time_ms=response_time_ms,
        status=status,
        error_message=error_message,
        **kwargs
    )


def record_usage_from_api(
    model_name: str,
    usage: Dict[str, int],
    response_time_ms: int = 0,
    status: str = "success",
    **kwargs
) -> Optional[str]:
    """
    便捷函数：从 API usage 记录
    
    Args:
        model_name: 模型名称
        usage: API 返回的 usage
        response_time_ms: 响应时间
        status: 状态
        **kwargs: 其他参数
        
    Returns:
        request_id
    """
    return get_usage_tracker().record_from_usage(
        model_name=model_name,
        usage=usage,
        response_time_ms=response_time_ms,
        status=status,
        **kwargs
    )
