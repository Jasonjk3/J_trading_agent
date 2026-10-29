#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
定时任务调度器
使用APScheduler管理定时任务
"""
import os
from typing import Optional, Dict, Any, Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from schedules.batch_competitor_analysis import run_batch_competitor_analysis


# 任务类型注册表：存储任务类型和对应的处理函数
_task_registry: Dict[str, Callable] = {}


def register_task_type(task_type: str, handler: Callable):
    """
    注册任务类型
    
    Args:
        task_type: 任务类型名称
        handler: 处理函数，接收 (scheduler, job_id, job_config) 参数
    """
    _task_registry[task_type] = handler
    logger.info(f"已注册任务类型: {task_type}")


class TaskScheduler:
    """定时任务调度器"""
    
    def __init__(self):
        """初始化调度器"""
        self.scheduler = AsyncIOScheduler()
        self.jobs: Dict[str, str] = {}  # job_id -> job_name 映射
    
    @staticmethod
    def parse_trigger(trigger_config: Optional[Dict[str, Any]], default_trigger: Optional[Any] = None) -> Any:
        """
        解析触发器配置（统一方法，解决重复代码问题）
        
        Args:
            trigger_config: 触发器配置字典，格式：
                {
                    "type": "cron" | "interval",
                    ...其他参数
                }
                如果为None，返回默认触发器
            default_trigger: 默认触发器，如果trigger_config为None时使用
                            如果也为None，则使用每天凌晨2点执行
        
        Returns:
            触发器对象
        """
        if trigger_config is None:
            return default_trigger or CronTrigger(hour=2, minute=0)
        
        trigger_type = trigger_config.get("type", "cron")
        trigger_params = {k: v for k, v in trigger_config.items() if k != "type"}
        
        if trigger_type == "cron":
            return CronTrigger(**trigger_params)
        elif trigger_type == "interval":
            return IntervalTrigger(**trigger_params)
        else:
            raise ValueError(f"不支持的触发器类型: {trigger_type}")
    
    def add_batch_competitor_analysis_job(
        self,
        job_id: str,
        input_excel_path: str,
        output_excel_path: Optional[str] = None,
        trigger: Optional[Any] = None,
        llm_api_key: Optional[str] = None,
        batch_size: int = 10,
        thinking_mode: str = "normal",
        **kwargs
    ) -> str:
        """
        添加批量产品相关性识别定时任务（便捷方法）
        
        Args:
            job_id: 任务ID（唯一标识）
            input_excel_path: 输入Excel文件路径
            output_excel_path: 输出Excel文件路径（可选）
            trigger: 触发器（CronTrigger或IntervalTrigger），如果为None则使用默认的每天执行一次
            llm_api_key: LLM API密钥（可选）
            batch_size: 批处理大小
            thinking_mode: 思维模式
            **kwargs: 其他参数
            
        Returns:
            任务ID
        """
        # 使用统一的触发器解析方法
        trigger = self.parse_trigger(None, trigger)
        
        # 添加任务
        self.scheduler.add_job(
            func=run_batch_competitor_analysis,
            trigger=trigger,
            id=job_id,
            name=f"批量产品相关性识别-{job_id}",
            args=[input_excel_path],
            kwargs={
                "output_excel_path": output_excel_path,
                "llm_api_key": llm_api_key,
                "batch_size": batch_size,
                "thinking_mode": thinking_mode,
                **kwargs
            },
            replace_existing=True
        )
        
        self.jobs[job_id] = f"批量产品相关性识别-{job_id}"
        logger.info(f"已添加定时任务: {job_id} - {self.jobs[job_id]}")
        
        return job_id
    
    def add_job_from_config(self, job_id: str, job_config: Dict[str, Any]) -> str:
        """
        从配置添加任务（通用方法，支持通过注册表扩展新任务类型）
        
        Args:
            job_id: 任务ID
            job_config: 任务配置字典，必须包含 "type" 字段指定任务类型
            
        Returns:
            任务ID
            
        示例配置：
        {
            "type": "batch_competitor_analysis",
            "input_excel_path": "/path/to/input.xlsx",
            "trigger": {"type": "cron", "hour": 2, "minute": 0},
            ...
        }
        """
        task_type = job_config.get("type")
        if not task_type:
            raise ValueError(f"任务配置缺少 'type' 字段: {job_config}")
        
        if task_type not in _task_registry:
            raise ValueError(f"未注册的任务类型: {task_type}，可用类型: {list(_task_registry.keys())}")
        
        # 调用注册的处理函数
        handler = _task_registry[task_type]
        return handler(self, job_id, job_config)
    
    def remove_job(self, job_id: str) -> bool:
        """
        移除定时任务
        
        Args:
            job_id: 任务ID
            
        Returns:
            是否成功移除
        """
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self.jobs:
                del self.jobs[job_id]
            logger.info(f"已移除定时任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"移除定时任务失败: {job_id}, 错误: {e}")
            return False
    
    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("定时任务调度器已启动")
        else:
            logger.warning("定时任务调度器已在运行")
    
    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("定时任务调度器已停止")
        else:
            logger.warning("定时任务调度器未运行")
    
    def get_jobs(self) -> list:
        """获取所有任务列表"""
        return [job.id for job in self.scheduler.get_jobs()]
    
    def pause_job(self, job_id: str) -> bool:
        """暂停任务"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"已暂停任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"暂停任务失败: {job_id}, 错误: {e}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """恢复任务"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"已恢复任务: {job_id}")
            return True
        except Exception as e:
            logger.error(f"恢复任务失败: {job_id}, 错误: {e}")
            return False


# 全局调度器实例
_global_scheduler: Optional[TaskScheduler] = None


def get_scheduler() -> TaskScheduler:
    """获取全局调度器实例"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = TaskScheduler()
    return _global_scheduler


def init_scheduler_from_config(config: Dict[str, Any]) -> TaskScheduler:
    """
    从配置初始化调度器
    
    Args:
        config: 配置字典，格式如下：
        {
            "jobs": [
                {
                    "job_id": "batch_competitor_analysis_1",
                    "type": "batch_competitor_analysis",  # 任务类型
                    "input_excel_path": "/path/to/input.xlsx",
                    "output_excel_path": "/path/to/output.xlsx",  # 可选
                    "trigger": {
                        "type": "cron",  # 或 "interval"
                        "hour": 2,
                        "minute": 0
                    },
                    "batch_size": 10,
                    "thinking_mode": "normal"
                }
            ]
        }
    """
    scheduler = get_scheduler()
    
    jobs = config.get("jobs", [])
    for job_config in jobs:
        job_id = job_config.get("job_id")
        if not job_id:
            logger.warning(f"任务配置缺少job_id: {job_config}")
            continue
        
        try:
            # 使用通用的配置添加方法
            scheduler.add_job_from_config(job_id, job_config)
        except Exception as e:
            logger.error(f"添加任务失败: {job_id}, 错误: {e}", exc_info=True)
    
    return scheduler


# 注册批量竞品分析任务类型
def _handle_batch_competitor_analysis(scheduler: TaskScheduler, job_id: str, job_config: Dict[str, Any]) -> str:
    """批量竞品分析任务处理函数"""
    input_excel_path = job_config.get("input_excel_path")
    if not input_excel_path:
        raise ValueError(f"任务 {job_id} 缺少 input_excel_path")
    
    # 使用统一的触发器解析方法
    trigger = scheduler.parse_trigger(job_config.get("trigger"))
    
    return scheduler.add_batch_competitor_analysis_job(
        job_id=job_id,
        input_excel_path=input_excel_path,
        output_excel_path=job_config.get("output_excel_path"),
        trigger=trigger,
        batch_size=job_config.get("batch_size", 10),
        thinking_mode=job_config.get("thinking_mode", "normal")
    )


# 自动注册内置任务类型
register_task_type("batch_competitor_analysis", _handle_batch_competitor_analysis)

# 注册 LLM 数据清理任务类型
try:
    from schedules.llm_data_cleanup import register_llm_cleanup_task
    register_llm_cleanup_task()
except ImportError:
    logger.warning("无法导入 LLM 数据清理模块")

