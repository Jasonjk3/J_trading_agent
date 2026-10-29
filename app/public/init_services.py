#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 18:30
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
服务初始化
在应用启动时初始化各种服务
"""
import asyncio
import os
from loguru import logger

from core.component.registry.agent_registry import AgentRegistry
from core.component.storage.session_store import SessionStore
from core.component.storage.task_queue import TaskQueue
from core.component.executor.agent_executor import AgentExecutor
from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
from agent_applications.conversation_agents.feishu_assistant_agent import FeishuAssistantAgent
# 注意：不再需要导入DeepSeekLLM，LLM实例由各个Agent自行创建
from app.v1.services.chat_service import ChatService


async def init_services(app):
    """
    初始化所有服务并挂载到应用状态

    Args:
        app: FastAPI应用实例
    """
    try:
        # 注意：LLM实例现在由各个Agent在initialize()时自行创建，不再共享
        # 如果需要共享LLM实例用于其他用途（如ChatService），可以在这里创建
        # 但目前ChatService也不再需要共享LLM实例

        # # 1.1 初始化LLM健康监控器
        # llm_health_monitor = LLMHealthMonitor(
        #     llm=llm,
        #     check_interval_seconds=60,  # 每60秒检查一次
        #     health_check_timeout=10,  # 健康检查超时10秒
        #     degraded_threshold=3.0,  # 响应时间超过3秒视为降级
        #     unhealthy_error_rate=0.5  # 错误率超过50%视为不健康
        # )
        # await llm_health_monitor.start_monitor()
        # logger.info("LLM健康监控器已启动")

        # 2. 初始化核心组件
        # 获取数据库连接
        db = app.state.db
        
        agent_registry = AgentRegistry()
        session_store = SessionStore(db=db)  # 传入数据库连接
        task_queue = TaskQueue(db=db)  # 传入数据库连接
        agent_executor = AgentExecutor()
        
        logger.info("核心组件初始化完成")

        # 3. 创建并注册协调Agent（用于专家模式）
        try:
            from core.models.agent_message import MessageBus
            from core.system_agents.coordinator_agent import CoordinatorAgent
            
            message_bus = MessageBus()
            coordinator_agent = CoordinatorAgent(
                agent_name="协调Agent",
                agent_registry=agent_registry,
                message_bus=message_bus
            )
            logger.info(f"创建协调Agent: {coordinator_agent.agent_id}")
            
            registered = await agent_registry.register(coordinator_agent)
            if registered:
                logger.info(f"协调Agent注册成功: {coordinator_agent.agent_id}, 状态: {coordinator_agent.status}")
            else:
                logger.error(f"协调Agent注册失败: {coordinator_agent.agent_id}")
        except Exception as e:
            logger.warning(f"创建或注册协调Agent失败: {e}")

        # 4. 创建并注册飞书助手Agent
        try:
            feishu_app_id = os.getenv("FEISHU_APP_ID")
            feishu_app_secret = os.getenv("FEISHU_APP_SECRET")
            DB_URL_XITING_USER_DATA = os.getenv("DB_URL_XITING_USER_DATA", "")

            
            feishu_agent = FeishuAssistantAgent(
                agent_name="飞书助手",
                feishu_app_id=feishu_app_id,
                feishu_app_secret=feishu_app_secret,
                feishu_timeout=30,
                db_url=DB_URL_XITING_USER_DATA
            )
            logger.info(f"创建飞书助手Agent: {feishu_agent.agent_id}")
            
            registered = await agent_registry.register(feishu_agent)
            if registered:
                logger.info(f"飞书助手Agent注册成功: {feishu_agent.agent_id}, 状态: {feishu_agent.status}")
            else:
                logger.error(f"飞书助手Agent注册失败: {feishu_agent.agent_id}")
                raise Exception("飞书助手Agent注册失败")
        except Exception as e:
            logger.error(f"创建或注册飞书助手Agent失败: {e}", exc_info=True)
            raise

        # 5. 创建并注册智能助手Agent
        try:
            assistant_agent = IntelligentAssistantAgent(
                agent_name="智能助手",
                agent_registry=agent_registry  # 传入agent_registry以支持专家模式
            )
            logger.info(f"创建智能助手Agent: {assistant_agent.agent_id}")
            
            registered = await agent_registry.register(assistant_agent)
            if registered:
                logger.info(f"智能助手Agent注册成功: {assistant_agent.agent_id}, 状态: {assistant_agent.status}")
            else:
                logger.error(f"智能助手Agent注册失败: {assistant_agent.agent_id}")
                raise Exception("智能助手Agent注册失败")
        except Exception as e:
            logger.error(f"创建或注册智能助手Agent失败: {e}", exc_info=True)
            raise

        # 6. 启动其他监控任务
        # 注意：智能体心跳监控已移除，因为智能体是内存对象，不需要心跳
        # 如果需要监控分布式智能体，可以重新启用
        # await agent_registry.start_monitor()
        await session_store.start_cleanup_task()

        # 回测任务租约守护：进程异常退出后自动回收长期 running 任务。
        try:
            from backtest.task_watchdog import backtest_watchdog_loop

            watchdog_interval = float(os.getenv("BACKTEST_WATCHDOG_INTERVAL", "60"))
            app.state._backtest_watchdog_task = asyncio.create_task(
                backtest_watchdog_loop(db, interval_seconds=watchdog_interval)
            )
            logger.info("回测任务租约守护已启动")
        except Exception as e:
            logger.warning(f"启动回测任务租约守护失败: {e}", exc_info=True)
        
        # 6.1 启动 LLM 使用量追踪器 Worker
        try:
            from core.llm.base.usage_tracker import get_usage_tracker
            usage_tracker = get_usage_tracker()
            await usage_tracker.start_worker()
            logger.info("LLM 使用量追踪器 Worker 已启动")
        except Exception as e:
            logger.warning(f"启动 LLM 使用量追踪器 Worker 失败: {e}", exc_info=True)
        
        # 6.2 从数据库加载模型费用配置到 CostCalculator（确保 gpt-5.2 等 DB 中的配置可用）
        try:
            from core.llm.base.cost_calculator import load_pricing_from_database
            await load_pricing_from_database()
        except Exception as e:
            logger.warning(f"加载模型费用配置失败: {e}", exc_info=True)
        
        logger.info("监控任务启动完成")

        # 7. 初始化聊天服务
        chat_service = ChatService(
            agent_registry=agent_registry,
            session_store=session_store,
            task_queue=task_queue,
            agent_executor=agent_executor
        )
        logger.info("聊天服务初始化完成")

        from app.v1.services.conversation_run_service import ConversationRunService
        conversation_runs = ConversationRunService(db, chat_service.conversation_runtime, agent_executor)
        await conversation_runs.start()
        chat_service.conversation_runs = conversation_runs
        app.state.conversation_runs = conversation_runs

        # 7.1 创建并注册监控服务 Agent
        monitor_service_agent = None
        try:
            from agent_applications.service_agents.monitor_service_agent import MonitorServiceAgent
            
            monitor_service_agent = MonitorServiceAgent(
                agent_name="监控服务Agent",
                monitor_interval=10.0  # 每10秒监控一次
            )
            logger.info(f"创建监控服务Agent: {monitor_service_agent.agent_id}")
            
            registered = await agent_registry.register(monitor_service_agent)
            if registered:
                logger.info(f"监控服务Agent注册成功: {monitor_service_agent.agent_id}, 状态: {monitor_service_agent.status}")
            else:
                logger.warning(f"监控服务Agent注册失败: {monitor_service_agent.agent_id}")
        except Exception as e:
            logger.warning(f"创建或注册监控服务Agent失败: {e}", exc_info=True)
            # 不抛出异常，因为这是可选功能

        # 7.6 初始化监控服务
        try:
            from app.v1.services.service_monitor_service import ServiceMonitorService
            
            service_monitor_service = ServiceMonitorService(
                agent_registry=agent_registry
            )
            logger.info("监控服务初始化完成")
        except Exception as e:
            logger.warning(f"初始化监控服务失败: {e}", exc_info=True)
            service_monitor_service = None

        # 8. 初始化管道管理器（可选，通过环境变量控制）
        pipeline_manager = None
        enable_pipeline = os.getenv("ENABLE_PIPELINE", "false").lower() == "true"
        if enable_pipeline:
            try:
                from consumers.pipeline.pipeline_manager import PipelineManager
                from consumers.pipeline import PipelineConfig
                
                # 创建管道配置（可以从环境变量读取）
                pipeline_config = PipelineConfig.from_env()
                
                # 创建任务类型到Agent ID的映射
                task_type_agent_mapping = {}
                if assistant_agent:
                    task_type_agent_mapping["chat"] = assistant_agent.agent_id
                if feishu_agent:
                    task_type_agent_mapping["feishu"] = feishu_agent.agent_id
                
                pipeline_config.task_type_agent_mapping = task_type_agent_mapping
                
                # 创建管道管理器
                pipeline_manager = PipelineManager(
                    config=pipeline_config,
                    agent_registry=agent_registry,
                    agent_executor=agent_executor,
                    task_queue=task_queue
                )
                
                # 启动管道
                await pipeline_manager.start()
                logger.info("管道管理器已启动")
            except Exception as e:
                logger.error(f"初始化管道管理器失败: {e}", exc_info=True)
                # 不抛出异常，因为管道是可选的
                pipeline_manager = None

        # 9. 挂载到应用状态
        app.state.agent_registry = agent_registry
        app.state.session_store = session_store
        app.state.task_queue = task_queue
        app.state.chat_service = chat_service
        if service_monitor_service:
            app.state.service_monitor_service = service_monitor_service
        if pipeline_manager:
            app.state.pipeline_manager = pipeline_manager
        # app.state.llm_health_monitor = llm_health_monitor

        # 10. 消息面采集：后台轮询运行中任务并调用 LLM 写入资讯（仅 status=running 时执行）
        enable_news_worker = os.getenv("ENABLE_NEWS_INTELLIGENCE_WORKER", "true").lower() == "true"
        if enable_news_worker:
            try:
                from app.v1.services.news_intelligence_collector import news_intelligence_worker_loop

                db = app.state.db
                interval = float(os.getenv("NEWS_INTELLIGENCE_WORKER_INTERVAL", "60"))
                app.state._news_intel_worker_task = asyncio.create_task(
                    news_intelligence_worker_loop(db, interval_sec=interval)
                )
                logger.info(f"消息面采集后台任务已启动（间隔 {interval}s）")
            except Exception as e:
                logger.warning(f"启动消息面采集后台任务失败: {e}", exc_info=True)

        if os.getenv("ENABLE_DATA_MONITOR_WORKER", "true").lower() == "true":
            try:
                from app.v1.services.data_monitor_service import data_monitor_worker_loop

                interval = max(1.0, float(os.getenv("DATA_MONITOR_POLL_SECONDS", "5")))
                app.state._data_monitor_worker_task = asyncio.create_task(
                    data_monitor_worker_loop(app.state.db, interval)
                )
                logger.info("数据监控后台任务已启动（轮询 {} 秒）", interval)
            except Exception as e:
                logger.warning("启动数据监控后台任务失败: {}", e, exc_info=True)

        # 11. 实盘交易调度器：管理运行中的交易 Agent 定时决策
        enable_live_trading = os.getenv("ENABLE_LIVE_TRADING_SCHEDULER", "false").lower() == "true"
        is_sandbox = os.getenv("TRADING_SANDBOX_MODE", "true").lower() == "true"
        if enable_live_trading:
            try:
                from app.v1.services.live_trading_scheduler import (
                    init_live_trading_scheduler,
                )
                
                db = app.state.db
                scheduler = await init_live_trading_scheduler(
                    db_session_factory=db.get_session,
                    is_sandbox=is_sandbox,
                )
                await scheduler.start()
                app.state.live_trading_scheduler = scheduler
                logger.info(f"实盘交易调度器已启动（sandbox={is_sandbox}）")
            except Exception as e:
                logger.warning(f"启动实盘交易调度器失败: {e}", exc_info=True)
        else:
            logger.info("实盘交易调度器未启用（设置 ENABLE_LIVE_TRADING_SCHEDULER=true 启用）")

        # 12. 模拟盘 Agent 调度器：独立虚拟资金，不调用交易所下单。
        enable_paper_trading = os.getenv("ENABLE_PAPER_TRADING_SCHEDULER", "false").lower() == "true"
        if enable_paper_trading:
            try:
                from app.v1.services.paper_trading_scheduler import paper_trading_scheduler_loop

                interval = int(os.getenv("PAPER_TRADING_POLL_SECONDS", "60"))
                app.state._paper_trading_scheduler_task = asyncio.create_task(
                    paper_trading_scheduler_loop(app.state.db, interval)
                )
                logger.info("模拟盘 Agent 调度器已启动（轮询 {} 秒）", interval)
            except Exception as e:
                logger.warning(f"启动模拟盘 Agent 调度器失败: {e}", exc_info=True)

        logger.info("所有服务初始化完成并挂载到应用状态")

    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        raise


async def cleanup_services(app):
    """
    清理服务资源

    Args:
        app: FastAPI应用实例
    """
    try:
        if hasattr(app.state, "conversation_runs"):
            await app.state.conversation_runs.stop()
        monitor_task = getattr(app.state, "_data_monitor_worker_task", None)
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            logger.info("数据监控后台任务已停止")

        watchdog = getattr(app.state, "_backtest_watchdog_task", None)
        if watchdog:
            watchdog.cancel()
            try:
                await watchdog
            except asyncio.CancelledError:
                pass
            logger.info("回测任务租约守护已停止")

        task = getattr(app.state, "_news_intel_worker_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("消息面采集后台任务已停止")

        paper_task = getattr(app.state, "_paper_trading_scheduler_task", None)
        if paper_task:
            paper_task.cancel()
            try:
                await paper_task
            except asyncio.CancelledError:
                pass
            logger.info("模拟盘 Agent 调度器已停止")

        # 停止实盘交易调度器
        if hasattr(app.state, 'live_trading_scheduler') and app.state.live_trading_scheduler:
            try:
                from app.v1.services.live_trading_scheduler import cleanup_live_trading_scheduler
                await cleanup_live_trading_scheduler()
                logger.info("实盘交易调度器已停止")
            except Exception as e:
                logger.error(f"停止实盘交易调度器失败: {e}")

        # 停止管道管理器
        if hasattr(app.state, 'pipeline_manager') and app.state.pipeline_manager:
            try:
                await app.state.pipeline_manager.stop()
                logger.info("管道管理器已停止")
            except Exception as e:
                logger.error(f"停止管道管理器失败: {e}")
        
        # 停止LLM健康监控
        if hasattr(app.state, 'llm_health_monitor'):
            await app.state.llm_health_monitor.stop_monitor()
        
        # 停止智能体监控（如果启用）
        if hasattr(app.state, 'agent_registry'):
            # await app.state.agent_registry.stop_monitor()  # 已禁用
            pass
        
        if hasattr(app.state, 'session_store'):
            await app.state.session_store.stop_cleanup_task()
        
        # 停止 LLM 使用量追踪器 Worker
        try:
            from core.llm.base.usage_tracker import get_usage_tracker
            usage_tracker = get_usage_tracker()
            await usage_tracker.stop_worker()
            logger.info("LLM 使用量追踪器 Worker 已停止")
        except Exception as e:
            logger.warning(f"停止 LLM 使用量追踪器 Worker 失败: {e}", exc_info=True)
        
        logger.info("服务清理完成")
    except Exception as e:
        logger.error(f"服务清理失败: {e}")
