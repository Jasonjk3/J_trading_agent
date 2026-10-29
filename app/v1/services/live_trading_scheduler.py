#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
实盘交易调度器

负责管理多个 Agent 的实盘交易循环，包括：
- 定时触发决策
- 管理 Agent 生命周期
- 处理异常和重试
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from models.inner_models.trading_agent_model import TradingAgentModel, TradingAgentStatus
from app.v1.crud.trading_agent_crud import (
    get_trading_agents,
    get_trading_agent_by_id,
    update_trading_agent_status,
)
from app.v1.services.live_trading_executor import (
    LiveTradingExecutor,
    create_live_executor,
    LiveAccountSnapshot,
)
from app.v1.services.trading_analysis_context_service import build_trading_analysis_context
from app.v1.services.managed_llm_service import build_decision_llm
from agent_applications.service_agents.trading_decision_agent import TradingDecisionAgent
from decision.rule_context_builder import build_rule_decision_context
from decision.types import resolve_decision_mode
from trader.event_store import SqlTraderEventStore
from trader.state_store import SqlTraderStateStore


class AgentState(str, Enum):
    """Agent 运行状态"""
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    COOLDOWN = "cooldown"


class LiveAgentRunner:
    """单个 Agent 的实盘运行器"""
    
    DEFAULT_DECISION_INTERVAL = 900  # 默认决策间隔 15 分钟
    MAX_CONSECUTIVE_ERRORS = 5
    ERROR_COOLDOWN_SECONDS = 300  # 错误后冷却 5 分钟
    
    def __init__(
        self,
        agent: TradingAgentModel,
        executor: LiveTradingExecutor,
        decision_agent: TradingDecisionAgent,
        decision_interval: int = None,
    ):
        self.agent = agent
        self.executor = executor
        self.decision_agent = decision_agent
        self.decision_interval = decision_interval or self.DEFAULT_DECISION_INTERVAL
        
        self.state = AgentState.IDLE
        self.last_decision_time: Optional[datetime] = None
        self.next_decision_time: Optional[datetime] = None
        self.consecutive_errors = 0
        self.last_error: Optional[str] = None
        self.cooldown_until: Optional[datetime] = None
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    @property
    def agent_id(self) -> str:
        return self.agent.id
    
    @property
    def symbols(self) -> List[str]:
        cfg = self.agent.strategy_config or {}
        return cfg.get("symbols", [])
    
    def is_ready_for_decision(self) -> bool:
        """判断是否可以进行决策"""
        if self.state == AgentState.COOLDOWN:
            if self.cooldown_until and datetime.now() >= self.cooldown_until:
                self.state = AgentState.IDLE
                self.cooldown_until = None
            else:
                return False
        
        if self.next_decision_time is None:
            return True
        
        return datetime.now() >= self.next_decision_time
    
    def record_decision(
        self,
        success: bool,
        error: Optional[str] = None,
        requested_next_review: Optional[datetime] = None,
    ) -> None:
        """记录决策结果"""
        self.last_decision_time = datetime.now()
        self.next_decision_time = (
            requested_next_review
            if requested_next_review and requested_next_review > self.last_decision_time
            else self.last_decision_time + timedelta(seconds=self.decision_interval)
        )
        
        if success:
            self.consecutive_errors = 0
            self.last_error = None
            self.state = AgentState.IDLE
        else:
            self.consecutive_errors += 1
            self.last_error = error
            
            if self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                self.state = AgentState.COOLDOWN
                self.cooldown_until = datetime.now() + timedelta(seconds=self.ERROR_COOLDOWN_SECONDS)
                logger.warning(
                    f"[LiveAgentRunner] Agent {self.agent_id} 连续错误 {self.consecutive_errors} 次，"
                    f"进入冷却期至 {self.cooldown_until}"
                )
            else:
                self.state = AgentState.ERROR
    
    def get_status(self) -> Dict[str, Any]:
        """获取运行状态"""
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "last_decision_time": self.last_decision_time.isoformat() if self.last_decision_time else None,
            "next_decision_time": self.next_decision_time.isoformat() if self.next_decision_time else None,
            "consecutive_errors": self.consecutive_errors,
            "last_error": self.last_error,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
        }


class LiveTradingScheduler:
    """实盘交易调度器"""
    
    SCAN_INTERVAL = 10  # 扫描间隔（秒）
    PROFIT_RECORD_INTERVAL = 3600  # 收益记录间隔（秒）
    
    def __init__(
        self,
        db_session_factory,
        is_sandbox: bool = True,
    ):
        """
        初始化调度器
        
        Args:
            db_session_factory: 数据库会话工厂
            is_sandbox: 是否使用沙盒环境
        """
        self.db_session_factory = db_session_factory
        self.is_sandbox = is_sandbox
        
        self._runners: Dict[str, LiveAgentRunner] = {}
        self._running = False
        self._main_task: Optional[asyncio.Task] = None
        self._profit_task: Optional[asyncio.Task] = None
        self._last_profit_record_time: Optional[datetime] = None
        
        logger.info(f"[LiveTradingScheduler] 初始化: sandbox={is_sandbox}")
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def active_agents(self) -> Set[str]:
        return set(self._runners.keys())
    
    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            logger.warning("[LiveTradingScheduler] 调度器已在运行中")
            return
        
        self._running = True
        self._main_task = asyncio.create_task(self._main_loop())
        self._profit_task = asyncio.create_task(self._profit_record_loop())
        
        logger.info("[LiveTradingScheduler] 调度器已启动")
    
    async def stop(self) -> None:
        """停止调度器"""
        if not self._running:
            return
        
        self._running = False
        
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        
        if self._profit_task:
            self._profit_task.cancel()
            try:
                await self._profit_task
            except asyncio.CancelledError:
                pass
        
        self._runners.clear()
        logger.info("[LiveTradingScheduler] 调度器已停止")
    
    async def add_agent(self, agent_id: str) -> bool:
        """
        添加 Agent 到调度器
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否添加成功
        """
        if agent_id in self._runners:
            logger.info(f"[LiveTradingScheduler] Agent {agent_id} 已在调度器中")
            return True
        
        async with self.db_session_factory() as session:
            agent = await get_trading_agent_by_id(session, agent_id)
            if not agent:
                logger.error(f"[LiveTradingScheduler] Agent {agent_id} 不存在")
                return False
            
            if agent.status != TradingAgentStatus.RUNNING:
                logger.warning(f"[LiveTradingScheduler] Agent {agent_id} 状态不是 RUNNING")
                return False
            
            try:
                executor = await create_live_executor(session, agent, self.is_sandbox)
                decision_agent = await self._create_decision_agent(session, agent)
                
                cfg = agent.strategy_config or {}
                interval = self._get_decision_interval(cfg)
                
                runner = LiveAgentRunner(
                    agent=agent,
                    executor=executor,
                    decision_agent=decision_agent,
                    decision_interval=interval,
                )
                
                self._runners[agent_id] = runner
                logger.info(f"[LiveTradingScheduler] Agent {agent_id} 已添加到调度器")
                return True
                
            except Exception as e:
                logger.error(f"[LiveTradingScheduler] 添加 Agent {agent_id} 失败: {e}")
                return False
    
    async def remove_agent(self, agent_id: str) -> bool:
        """
        从调度器移除 Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            是否移除成功
        """
        if agent_id not in self._runners:
            return True
        
        runner = self._runners.pop(agent_id)
        
        logger.info(f"[LiveTradingScheduler] Agent {agent_id} 已从调度器移除")
        return True
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取 Agent 运行状态"""
        runner = self._runners.get(agent_id)
        if runner:
            return runner.get_status()
        return None
    
    def get_all_status(self) -> Dict[str, Any]:
        """获取所有 Agent 状态"""
        return {
            "is_running": self._running,
            "active_agents": list(self._runners.keys()),
            "agents": {
                agent_id: runner.get_status()
                for agent_id, runner in self._runners.items()
            },
        }
    
    async def _main_loop(self) -> None:
        """主调度循环"""
        logger.info("[LiveTradingScheduler] 主循环启动")
        
        while self._running:
            try:
                await self._sync_running_agents()
                
                await self._process_decisions()
                
                await asyncio.sleep(self.SCAN_INTERVAL)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[LiveTradingScheduler] 主循环异常: {e}")
                await asyncio.sleep(self.SCAN_INTERVAL)
        
        logger.info("[LiveTradingScheduler] 主循环结束")
    
    async def _profit_record_loop(self) -> None:
        """收益记录循环"""
        logger.info("[LiveTradingScheduler] 收益记录循环启动")
        
        while self._running:
            try:
                await asyncio.sleep(self.PROFIT_RECORD_INTERVAL)
                
                await self._record_all_profits()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[LiveTradingScheduler] 收益记录循环异常: {e}")
    
    async def _sync_running_agents(self) -> None:
        """同步数据库中 RUNNING 状态的 Agent"""
        async with self.db_session_factory() as session:
            agents = await get_trading_agents(
                session=session,
                user_id="",  # 获取所有用户的
                status=TradingAgentStatus.RUNNING,
            )
            
            db_agent_ids = {a.id for a in agents}
            current_ids = set(self._runners.keys())
            
            for agent_id in db_agent_ids - current_ids:
                await self.add_agent(agent_id)
            
            for agent_id in current_ids - db_agent_ids:
                await self.remove_agent(agent_id)
    
    async def _process_decisions(self) -> None:
        """处理所有 Agent 的决策"""
        for agent_id, runner in list(self._runners.items()):
            if not runner.is_ready_for_decision():
                continue
            
            try:
                runner.state = AgentState.RUNNING
                success, error, next_review_at = await self._execute_single_decision(runner)
                runner.record_decision(success, error, next_review_at)
                
            except Exception as e:
                logger.error(f"[LiveTradingScheduler] Agent {agent_id} 决策异常: {e}")
                runner.record_decision(False, str(e))
    
    async def _execute_single_decision(
        self, runner: LiveAgentRunner
    ) -> tuple[bool, Optional[str], Optional[datetime]]:
        """
        执行单个 Agent 的决策
        
        Returns:
            (是否成功, 错误信息)
        """
        agent_id = runner.agent_id
        symbols = runner.symbols
        
        if not symbols:
            return True, None, None
        
        async with self.db_session_factory() as session:
            try:
                account_snapshot = await runner.executor.get_account_snapshot(symbols)
                
                live_account = runner.executor.build_live_account(account_snapshot)
                market_snapshot = runner.executor.build_market_snapshot(account_snapshot)
                
                agent_model = await get_trading_agent_by_id(session, agent_id)
                if not agent_model:
                    return False, "Agent 不存在", None
                
                cfg = agent_model.strategy_config or {}
                decision_mode = resolve_decision_mode(cfg)
                if decision_mode == "rule":
                    analysis_context = build_rule_decision_context(
                        market_snapshot,
                        cfg,
                        symbols,
                    )
                else:
                    analysis_context = await build_trading_analysis_context(
                        session=session,
                        user_id=agent_model.user_id,
                        strategy_config=cfg,
                        symbols=symbols,
                        as_of=datetime.now(),
                        market_snapshot=market_snapshot,
                    )
                    analysis_context["open_orders"] = list(
                        account_snapshot.pending_orders or []
                    )
                
                decision_call = runner.decision_agent.make_decision(
                    snapshot=market_snapshot,
                    account=live_account,
                    risk_manager=None,
                    analysis_context=analysis_context,
                    decision_mode=decision_mode,
                )
                if decision_mode == "trader":
                    trader_config = cfg.get("traderConfig") or {}
                    try:
                        timeout_seconds = min(
                            300, max(5, int(trader_config.get("turnTimeoutSeconds") or 60))
                        )
                    except (TypeError, ValueError):
                        timeout_seconds = 60
                    decision = await asyncio.wait_for(decision_call, timeout=timeout_seconds)
                else:
                    decision = await decision_call
                next_review_at = self._parse_next_review_at(decision.get("next_review"))
                
                logger.info(
                    f"[LiveTradingScheduler] Agent {agent_id} 决策: "
                    f"action={decision.get('action')}, reason={decision.get('reason', '')[:50]}"
                )
                
                success, error, order_result = await runner.executor.execute_decision(
                    session=session,
                    decision=decision,
                    account_snapshot=account_snapshot,
                )
                
                await session.commit()
                
                return success, error, next_review_at
                
            except Exception as e:
                await session.rollback()
                logger.error(f"[LiveTradingScheduler] Agent {agent_id} 执行失败: {e}")
                return False, str(e), None
    
    async def _record_all_profits(self) -> None:
        """记录所有 Agent 的收益"""
        for agent_id, runner in list(self._runners.items()):
            try:
                async with self.db_session_factory() as session:
                    account_snapshot = await runner.executor.get_account_snapshot(runner.symbols)
                    await runner.executor.record_profit(session, account_snapshot)
                    await session.commit()
                    
            except Exception as e:
                logger.error(f"[LiveTradingScheduler] Agent {agent_id} 收益记录失败: {e}")
    
    async def _create_decision_agent(
        self,
        session: AsyncSession,
        agent: TradingAgentModel,
    ) -> TradingDecisionAgent:
        """创建决策 Agent"""
        cfg = agent.strategy_config or {}
        decision_mode = resolve_decision_mode(cfg)
        use_trader = decision_mode == "trader"

        llm = None
        managed_model_id = None
        managed_model_name = None
        if use_trader:
            try:
                llm, managed_model_id, managed_model_name = await build_decision_llm(
                    session,
                    cfg,
                    agent_llm_model_id=agent.llm_model_id,
                )
            except Exception as e:
                logger.warning(f"[LiveTradingScheduler] 创建 LLM 失败: {e}")

        if managed_model_id is not None:
            cfg = dict(cfg)
            cfg["_managedDecisionLlmModelId"] = managed_model_id
            cfg["_managedDecisionLlmModelName"] = managed_model_name

        cfg = dict(cfg)
        trader_config = dict(cfg.get("traderConfig") or {})
        trader_config["stateScope"] = "live"
        trader_config["sessionId"] = f"live:{agent.id}"
        cfg["traderConfig"] = trader_config

        return TradingDecisionAgent(
            agent_id=agent.id,
            agent_name=f"Live-{agent.name}",
            llm=llm,
            strategy_config=cfg,
            state_store=SqlTraderStateStore(self.db_session_factory, agent.id),
            event_store=SqlTraderEventStore(self.db_session_factory),
        )

    @staticmethod
    def _parse_next_review_at(value: Any) -> Optional[datetime]:
        if not isinstance(value, dict) or not value.get("at"):
            return None
        try:
            parsed = datetime.fromisoformat(str(value["at"]).replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except (TypeError, ValueError):
            return None
    
    @staticmethod
    def _get_decision_interval(strategy_config: Dict[str, Any]) -> int:
        """
        根据策略配置获取决策间隔
        
        默认基于技术分析周期：
        - 15m -> 900秒 (15分钟)
        - 1H -> 3600秒 (1小时)
        - 4H -> 14400秒 (4小时)
        """
        if resolve_decision_mode(strategy_config) == "trader":
            trader_config = strategy_config.get("traderConfig") or {}
            try:
                review_minutes = int(trader_config.get("defaultReviewIntervalMinutes") or 15)
                return min(1440, max(1, review_minutes)) * 60
            except (TypeError, ValueError):
                return 900

        timeframe = str(strategy_config.get("technicalAnalysisTimeframe") or "15m").lower()
        
        timeframe_map = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        
        return timeframe_map.get(timeframe, 900)


_scheduler_instance: Optional[LiveTradingScheduler] = None


def get_live_trading_scheduler() -> Optional[LiveTradingScheduler]:
    """获取全局调度器实例"""
    return _scheduler_instance


async def init_live_trading_scheduler(db_session_factory, is_sandbox: bool = True) -> LiveTradingScheduler:
    """
    初始化全局调度器
    
    Args:
        db_session_factory: 数据库会话工厂
        is_sandbox: 是否使用沙盒环境
        
    Returns:
        LiveTradingScheduler: 调度器实例
    """
    global _scheduler_instance
    
    if _scheduler_instance is not None:
        logger.warning("[LiveTradingScheduler] 调度器已存在，先停止旧实例")
        await _scheduler_instance.stop()
    
    _scheduler_instance = LiveTradingScheduler(
        db_session_factory=db_session_factory,
        is_sandbox=is_sandbox,
    )
    
    return _scheduler_instance


async def cleanup_live_trading_scheduler() -> None:
    """清理全局调度器"""
    global _scheduler_instance
    
    if _scheduler_instance is not None:
        await _scheduler_instance.stop()
        _scheduler_instance = None
