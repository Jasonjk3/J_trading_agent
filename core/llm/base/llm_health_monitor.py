#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/18 16:00
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
LLM健康监控器
监控大模型服务的健康状态、可用性、响应时间等
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum
from loguru import logger

from core.llm.base.base_llm import BaseLLM


class LLMHealthStatus(str, Enum):
    """LLM健康状态"""
    HEALTHY = "healthy"  # 健康
    DEGRADED = "degraded"  # 降级（响应慢或偶发错误）
    UNHEALTHY = "unhealthy"  # 不健康（频繁错误或不可用）
    UNKNOWN = "unknown"  # 未知（未检测）


class LLMHealthMonitor:
    """LLM健康监控器"""

    def __init__(
        self,
        llm: BaseLLM,
        check_interval_seconds: int = 60,
        health_check_timeout: int = 10,
        degraded_threshold: float = 3.0,  # 响应时间超过3秒视为降级
        unhealthy_error_rate: float = 0.5,  # 错误率超过50%视为不健康
        error_window_seconds: int = 300  # 统计错误的时间窗口（5分钟）
    ):
        """
        初始化LLM健康监控器

        Args:
            llm: LLM实例
            check_interval_seconds: 健康检查间隔（秒）
            health_check_timeout: 健康检查超时时间（秒）
            degraded_threshold: 降级阈值（响应时间，秒）
            unhealthy_error_rate: 不健康错误率阈值（0-1）
            error_window_seconds: 错误统计时间窗口（秒）
        """
        self.llm = llm
        self.check_interval_seconds = check_interval_seconds
        self.health_check_timeout = health_check_timeout
        self.degraded_threshold = degraded_threshold
        self.unhealthy_error_rate = unhealthy_error_rate
        self.error_window_seconds = error_window_seconds

        # 状态指标
        self.status = LLMHealthStatus.UNKNOWN
        self.last_check_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        self.last_error_time: Optional[datetime] = None
        self.last_error_message: Optional[str] = None

        # 性能指标
        self.response_times: List[float] = []  # 响应时间列表（最近100次）
        self.error_history: List[Dict] = []  # 错误历史记录

        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def check_health(self) -> Dict:
        """
        执行健康检查

        Returns:
            健康检查结果
        """
        start_time = time.time()
        success = False
        error_message = None

        try:
            # 发送一个简单的测试请求
            test_prompt = "健康检查"
            result = await asyncio.wait_for(
                self._call_llm_async(test_prompt),
                timeout=self.health_check_timeout
            )

            if result:
                success = True
                response_time = time.time() - start_time
                await self._record_success(response_time)
            else:
                error_message = "LLM返回空响应"
                await self._record_error(error_message)

        except asyncio.TimeoutError:
            error_message = f"LLM健康检查超时（>{self.health_check_timeout}秒）"
            await self._record_error(error_message)
        except Exception as e:
            error_message = f"LLM健康检查失败: {str(e)}"
            await self._record_error(error_message)

        # 更新状态
        await self._update_status()

        return {
            "success": success,
            "error": error_message,
            "response_time": time.time() - start_time if success else None,
            "status": self.status.value,
            "timestamp": datetime.now().isoformat()
        }

    async def _call_llm_async(self, prompt: str) -> str:
        """异步调用LLM"""
        import asyncio
        loop = asyncio.get_event_loop()
        
        # 如果LLM有异步方法，使用异步方法
        if hasattr(self.llm, 'ainvoke'):
            result = await self.llm.ainvoke(prompt)
            return result.content if hasattr(result, 'content') else str(result)
        
        # 否则在线程池中执行同步方法
        if hasattr(self.llm, '_call'):
            return await loop.run_in_executor(None, self.llm._call, prompt)
        
        # 直接调用
        return self.llm._call(prompt)

    async def _record_success(self, response_time: float):
        """记录成功请求"""
        async with self._lock:
            self.last_success_time = datetime.now()
            self.response_times.append(response_time)
            # 只保留最近100次
            if len(self.response_times) > 100:
                self.response_times.pop(0)

    async def _record_error(self, error_message: str):
        """记录错误"""
        async with self._lock:
            self.last_error_time = datetime.now()
            self.last_error_message = error_message
            self.error_history.append({
                "timestamp": datetime.now(),
                "error": error_message
            })
            # 清理过期错误记录
            cutoff_time = datetime.now() - timedelta(seconds=self.error_window_seconds)
            self.error_history = [
                err for err in self.error_history
                if err["timestamp"] > cutoff_time
            ]

    async def _update_status(self):
        """更新健康状态"""
        async with self._lock:
            now = datetime.now()

            # 计算错误率
            total_requests = len(self.response_times) + len(self.error_history)
            if total_requests == 0:
                self.status = LLMHealthStatus.UNKNOWN
                return

            error_rate = len(self.error_history) / total_requests if total_requests > 0 else 0

            # 计算平均响应时间
            avg_response_time = (
                sum(self.response_times) / len(self.response_times)
                if self.response_times else 0
            )

            # 判断状态
            if error_rate >= self.unhealthy_error_rate:
                self.status = LLMHealthStatus.UNHEALTHY
            elif avg_response_time > self.degraded_threshold or error_rate > 0.1:
                self.status = LLMHealthStatus.DEGRADED
            elif self.last_success_time and (now - self.last_success_time).total_seconds() < 300:
                self.status = LLMHealthStatus.HEALTHY
            else:
                self.status = LLMHealthStatus.UNKNOWN

    async def start_monitor(self):
        """启动健康监控任务"""
        if self._monitor_task and not self._monitor_task.done():
            logger.warning("LLM健康监控任务已在运行")
            return

        async def monitor_loop():
            logger.info(f"LLM健康监控任务启动，检查间隔: {self.check_interval_seconds}秒")
            while True:
                try:
                    # 执行健康检查
                    result = await self.check_health()
                    self.last_check_time = datetime.now()

                    if result["success"]:
                        logger.debug(
                            f"LLM健康检查成功，响应时间: {result.get('response_time', 0):.2f}秒，"
                            f"状态: {result['status']}"
                        )
                    else:
                        logger.warning(
                            f"LLM健康检查失败: {result.get('error')}，状态: {result['status']}"
                        )

                    # 等待下一次检查
                    await asyncio.sleep(self.check_interval_seconds)

                except asyncio.CancelledError:
                    logger.info("LLM健康监控任务被取消")
                    break
                except Exception as e:
                    logger.error(f"LLM健康监控任务出错: {e}", exc_info=True)
                    await asyncio.sleep(self.check_interval_seconds)

        self._monitor_task = asyncio.create_task(monitor_loop())
        logger.info("LLM健康监控任务已启动")

    async def stop_monitor(self):
        """停止健康监控任务"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("LLM健康监控任务已停止")


    async def get_health_info_async(self) -> Dict:
        """异步获取健康信息"""
        async with self._lock:
            avg_response_time = (
                sum(self.response_times) / len(self.response_times)
                if self.response_times else 0
            )
            max_response_time = max(self.response_times) if self.response_times else 0
            min_response_time = min(self.response_times) if self.response_times else 0

            total_requests = len(self.response_times) + len(self.error_history)
            error_rate = (
                len(self.error_history) / total_requests
                if total_requests > 0 else 0
            )

            return {
                "status": self.status.value,
                "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
                "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
                "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
                "last_error_message": self.last_error_message,
                "metrics": {
                    "total_requests": total_requests,
                    "success_count": len(self.response_times),
                    "error_count": len(self.error_history),
                    "error_rate": error_rate,
                    "avg_response_time": avg_response_time,
                    "max_response_time": max_response_time,
                    "min_response_time": min_response_time,
                }
            }

