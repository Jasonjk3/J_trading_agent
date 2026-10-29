#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""规则决策模式冒烟测试（Phase 1）。"""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from backtest.backtest_engine import MarketSnapshot, KlineData
from backtest.virtual_account import VirtualAccount
from decision.rule_context_builder import build_rule_decision_context
from decision.rule_engine import RuleDecisionEngine
from decision.types import resolve_decision_mode
from agent_applications.service_agents.trading_decision_agent import TradingDecisionAgent


def _make_uptrend_klines(n: int = 60) -> list:
    base = datetime(2026, 1, 1)
    klines = []
    price = 100.0
    for i in range(n):
        price += 0.3 + (i % 3) * 0.1
        p = Decimal(str(round(price, 2)))
        klines.append(
            KlineData(
                timestamp=base + timedelta(minutes=15 * i),
                open=p - Decimal("0.2"),
                high=p + Decimal("0.5"),
                low=p - Decimal("0.5"),
                close=p,
                volume=Decimal("1000"),
            )
        )
    return klines


async def main() -> None:
    assert resolve_decision_mode({}) == "trader"
    assert resolve_decision_mode({"decisionMode": "trader"}) == "trader"
    assert resolve_decision_mode({"decisionMode": "rule"}) == "rule"

    klines = _make_uptrend_klines()
    snapshot = MarketSnapshot(
        timestamp=klines[-1].timestamp,
        prices={"BTCUSDT": klines[-1].close},
        klines={"BTCUSDT": klines},
    )
    account = VirtualAccount(initial_capital=Decimal("10000"))
    cfg = {
        "symbols": ["BTCUSDT"],
        "decisionMode": "rule",
        "tradingStyle": "balanced",
        "minOrderAmount": 10,
        "maxOrderAmount": 1000,
        "maxPositionRatio": 30,
        "marketMode": "trend_only",
        "positionDirection": "both",
    }

    ctx = build_rule_decision_context(snapshot, cfg, ["BTCUSDT"])
    engine = RuleDecisionEngine(cfg)
    d1 = await engine.evaluate(snapshot, account, ctx)
    print("engine:", d1.get("action"), (d1.get("reason") or "")[:100])
    print("decision_mode:", d1.get("decision_mode"), "signals:", d1.get("signals"))

    agent = TradingDecisionAgent(strategy_config=cfg)
    d2 = await agent.make_decision(
        snapshot, account, None, analysis_context=ctx, decision_mode="rule"
    )
    print("agent:", d2.get("action"), (d2.get("reason") or "")[:100])

    assert d1.get("decision_mode") == "rule"
    assert d2.get("action") in {"hold", "open_long", "open_short", "close_long", "close_short"}
    print("SMOKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
