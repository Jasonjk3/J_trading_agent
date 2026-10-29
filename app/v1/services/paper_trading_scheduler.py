#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent 模拟盘调度器；只操作 paper_trading_* 表，不触碰交易所下单接口。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select

from agent_applications.service_agents.trading_decision_agent import TradingDecisionAgent
from app.v1.schemas.paper_trading_schema import CreatePaperDecisionRequest, CreatePaperTradeRequest
from app.v1.services.managed_llm_service import build_decision_llm
from app.v1.services.market_service import MarketService
from app.v1.services.paper_trading_service import PaperTradingError, PaperTradingService
from app.v1.services.trading_analysis_context_service import build_trading_analysis_context
from backtest.backtest_engine import KlineData, MarketSnapshot
from backtest.virtual_account import Position, VirtualAccount
from decision.rule_context_builder import build_rule_decision_context
from decision.types import resolve_decision_mode
from models.inner_models.paper_trading_model import (
    PaperAccountStatus,
    PaperAccountType,
    PaperPositionModel,
    PaperTradingAccountModel,
)
from models.inner_models.trading_agent_model import TradingAgentModel
from trader.event_store import SqlTraderEventStore
from trader.state_store import SqlTraderStateStore


class PaperTradingScheduler:
    def __init__(self, db, poll_seconds: int = 60):
        self.db = db
        self.poll_seconds = max(15, int(poll_seconds))
        self.market = MarketService()
        self.paper = PaperTradingService()
        self._task: asyncio.Task | None = None
        self._last_run: dict[str, datetime] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_due_accounts()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[PaperTradingScheduler] 调度轮次失败")
            await asyncio.sleep(self.poll_seconds)

    @staticmethod
    def _interval(config: dict[str, Any]) -> int:
        if resolve_decision_mode(config) == "trader":
            value = (config.get("traderConfig") or {}).get("defaultReviewIntervalMinutes") or 15
            return max(60, min(86400, int(value) * 60))
        timeframe = str(config.get("technicalAnalysisTimeframe") or "15m").lower()
        return {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}.get(timeframe, 900)

    async def run_due_accounts(self) -> None:
        async with self.db.get_session() as session:
            rows = (await session.execute(select(PaperTradingAccountModel, TradingAgentModel).join(
                TradingAgentModel, TradingAgentModel.id == PaperTradingAccountModel.source_agent_id,
            ).where(
                PaperTradingAccountModel.account_type == PaperAccountType.AGENT,
                PaperTradingAccountModel.status == PaperAccountStatus.RUNNING,
            ))).all()
        now = datetime.now()
        for account, agent in rows:
            last = self._last_run.get(account.id)
            if last and now - last < timedelta(seconds=self._interval(agent.strategy_config or {})):
                continue
            self._last_run[account.id] = now
            try:
                await self.run_account_once(account.id)
            except Exception:
                logger.exception("[PaperTradingScheduler] Agent 模拟轮次失败 account={}", account.id)

    async def run_account_once(self, account_id: str) -> None:
        async with self.db.get_session() as session:
            account = (await session.execute(select(PaperTradingAccountModel).where(
                PaperTradingAccountModel.id == account_id,
                PaperTradingAccountModel.status == PaperAccountStatus.RUNNING,
            ))).scalar_one_or_none()
            if not account or not account.source_agent_id:
                return
            agent_model = (await session.execute(select(TradingAgentModel).where(
                TradingAgentModel.id == account.source_agent_id,
            ))).scalar_one_or_none()
            if not agent_model:
                return
            config = dict(agent_model.strategy_config or {})
            symbols = [str(item).upper().replace("/", "-") for item in config.get("symbols") or []]
            if not symbols:
                return
            interval = str(config.get("technicalAnalysisTimeframe") or "15m").lower()
            interval = interval if interval in {"15m", "1h", "4h", "1d"} else "15m"
            snapshot = await self._market_snapshot(session, symbols, interval)
            virtual_account = await self._virtual_account(session, account, snapshot.prices)
            decision_mode = resolve_decision_mode(config)
            llm = None
            if decision_mode == "trader":
                llm, managed_id, managed_name = await build_decision_llm(
                    session, config, agent_llm_model_id=agent_model.llm_model_id,
                )
                config["_managedDecisionLlmModelId"] = managed_id
                config["_managedDecisionLlmModelName"] = managed_name
            trader_config = dict(config.get("traderConfig") or {})
            trader_config.update({"stateScope": "paper", "sessionId": f"paper:{account.id}", "executionMode": "shadow"})
            config["traderConfig"] = trader_config
            decision_agent = TradingDecisionAgent(
                agent_id=f"paper:{account.id}", agent_name=f"Paper-{agent_model.name}",
                llm=llm, strategy_config=config,
                state_store=SqlTraderStateStore(self.db.get_session, f"paper:{account.id}"),
                event_store=SqlTraderEventStore(self.db.get_session),
            )
            if decision_mode == "rule":
                context = build_rule_decision_context(snapshot, config, symbols)
            else:
                context = await build_trading_analysis_context(
                    session=session, user_id=account.user_id, strategy_config=config,
                    symbols=symbols, as_of=datetime.now(), market_snapshot=snapshot,
                )
            decision = await decision_agent.make_decision(
                snapshot=snapshot, account=virtual_account, risk_manager=None,
                analysis_context=context, decision_mode=decision_mode,
            )
            await self._persist_decision(session, account, decision, snapshot)
            await session.commit()

    async def _market_snapshot(self, session, symbols: list[str], interval: str) -> MarketSnapshot:
        prices, histories = {}, {}
        for symbol in symbols:
            rows = await self.market.get_kline(symbol=symbol, interval=interval, limit=120, session=session)
            klines = [KlineData(
                timestamp=self._parse_market_time(row["time"]),
                open=Decimal(str(row["open"])), high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])), close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
            ) for row in rows]
            if not klines:
                raise PaperTradingError(f"{symbol} 暂无行情数据")
            histories[symbol] = klines
            prices[symbol] = klines[-1].close
        return MarketSnapshot(timestamp=datetime.now(), prices=prices, klines=histories)

    @staticmethod
    def _parse_market_time(value: Any) -> datetime:
        raw = str(value)
        if raw.isdigit():
            return datetime.fromtimestamp(int(raw) / 1000)
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)

    async def _virtual_account(self, session, account, prices) -> VirtualAccount:
        virtual = VirtualAccount(Decimal(str(account.initial_capital)))
        virtual.balance = Decimal(str(account.cash_balance))
        rows = (await session.execute(select(PaperPositionModel).where(
            PaperPositionModel.account_id == account.id, PaperPositionModel.quantity > 0,
        ))).scalars().all()
        for row in rows:
            position = Position(
                symbol=row.symbol, side="long", quantity=Decimal(str(row.quantity)),
                entry_price=Decimal(str(row.average_price)), entry_time=row.created_at,
                margin_used=Decimal(str(row.quantity)) * Decimal(str(row.average_price)),
            )
            position.update_unrealized_pnl(prices.get(row.symbol, Decimal(str(row.last_price))))
            virtual.positions[row.symbol] = position
        return virtual

    async def _persist_decision(self, session, account, decision, snapshot) -> None:
        action = str(decision.get("action") or "hold").lower()
        symbol = str(decision.get("symbol") or next(iter(snapshot.prices))).upper().replace("/", "-")
        price = snapshot.prices.get(symbol)
        confidence = float(decision.get("confidence") or 0)
        if 0 < confidence <= 1:
            confidence *= 100
        decision_row = await self.paper.create_decision(session, account.id, account.user_id, CreatePaperDecisionRequest(
            symbol=symbol, action=action, title=str(decision.get("title") or "Agent 策略决策"),
            summary=str(decision.get("reason") or ""), reasoning=str(decision.get("reason") or ""),
            referencePrice=float(price) if price else None,
            confidence=confidence, result="未下单" if action in {"hold", "error"} else "待执行",
        ))
        side = "buy" if action in {"buy", "open_long", "add_long"} else "sell" if action in {"sell", "close_long", "reduce_long"} else None
        quantity = Decimal(str(decision.get("quantity") or 0))
        if not side or not price or quantity <= 0:
            return
        try:
            await self.paper.execute_trade(
                session, account.id, account.user_id,
                CreatePaperTradeRequest(symbol=symbol, side=side, amount=float(quantity * price), price=float(price)),
                decision_id=decision_row.id,
            )
            decision_row.result = "已成交"
        except PaperTradingError as exc:
            decision_row.result = f"未成交：{exc}"


async def paper_trading_scheduler_loop(db, poll_seconds: int = 60) -> None:
    scheduler = PaperTradingScheduler(db, poll_seconds)
    await scheduler.start()
    assert scheduler._task is not None
    await scheduler._task
