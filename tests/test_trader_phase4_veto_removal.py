import asyncio
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backtest.backtest_engine import BacktestConfig, BacktestEngine, MarketSnapshot
from backtest.risk_manager import RiskManager
from backtest.virtual_account import VirtualAccount
from app.v1.services.live_trading_executor import LiveTradingExecutor
from decision.rule_params import resolve_rule_params
from trader.orchestrator import TraderOrchestrator
from trader.risk_kernel import HardRiskPolicy
from trader.schemas import TraderTurn


LEGACY_VETO_CONFIG = {
    "minExpectedRR": 999,
    "minOpenScore": 999,
    "maxSignalConflictScore": 0,
    "minEdgeAfterCostPct": 999,
    "decisionSafetyBufferPct": 99,
    "minHoldBars": 999,
    "reentryCooldownBars": 999,
    "blockCountertrendShort": True,
    "trailingStopEnabled": True,
    "trailingStopRatio": 0.01,
}


def _hard_policy_config(mode="trader"):
    return {
        "decisionMode": mode,
        "symbols": ["BTCUSDT"],
        "hardRiskPolicy": {
            "allowedSymbols": ["BTCUSDT"],
            "allowedDirections": ["long", "short"],
            "minOrderNotionalUSDT": 10,
            "maxOrderNotionalUSDT": 1000,
            "maxSymbolExposurePct": 100,
            "maxGrossExposurePct": 100,
            "maxRiskPerTradePct": 100,
            "maxPortfolioRiskPct": 100,
        },
    }


def _turn(now):
    return TraderTurn.model_validate({
        "session_id": "veto-audit",
        "as_of": now,
        "market_view": {"summary": "model-owned thesis"},
        "order_intents": [{
            "client_intent_id": "same-intent",
            "symbol": "BTCUSDT",
            "side": "sell",
            "effect": "open",
            "position_side": "short",
            "requested_leverage": 2,
            "size": {"mode": "quantity", "quantity": 1},
            "protection": {"stop_loss_price": 110},
            "rationale": "LLM deliberately chooses a short",
        }],
        "next_review": {"events": ["bar_closed"]},
    })


def test_legacy_strategy_veto_fields_cannot_change_trader_proposal():
    now = datetime(2026, 1, 1)
    account = VirtualAccount(Decimal("1000"))
    snapshot = SimpleNamespace(timestamp=now, prices={"BTCUSDT": Decimal("100")})
    base_config = _hard_policy_config()
    hostile_config = {**base_config, **LEGACY_VETO_CONFIG}
    orchestrator = TraderOrchestrator("veto-audit", execution_mode="live")

    base = orchestrator.propose_orders(
        _turn(now), snapshot, account, HardRiskPolicy.from_strategy_config(base_config)
    )
    hostile = orchestrator.propose_orders(
        _turn(now), snapshot, account, HardRiskPolicy.from_strategy_config(hostile_config)
    )
    assert base.status == hostile.status == "approved"
    assert base.intents[0].approved_decision == hostile.intents[0].approved_decision


def test_trader_disables_fixed_trailing_stop_while_rule_mode_keeps_it():
    trader = RiskManager.from_strategy_config({
        **_hard_policy_config("trader"),
        "trailingStopEnabled": True,
        "trailingStopRatio": 0.01,
    })
    rule = RiskManager.from_strategy_config({
        "decisionMode": "rule",
        "trailingStopEnabled": True,
        "trailingStopRatio": 0.01,
    })
    assert trader.config.trailing_stop_enabled is False
    assert rule.config.trailing_stop_enabled is True


def test_trader_execution_is_not_rejected_by_legacy_amount_or_style_caps():
    now = datetime(2026, 1, 1)
    strategy = {
        **_hard_policy_config("trader"),
        **LEGACY_VETO_CONFIG,
        "maxPositionRatio": 1,
        "maxOrderAmount": 20,
        "maxDailyTrades": 50,
    }
    engine = BacktestEngine(BacktestConfig(
        start_time=now,
        end_time=now,
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        slippage=Decimal("0"),
        market_impact_bps=Decimal("0"),
        impact_volatility_weight=Decimal("0"),
        strategy_config=strategy,
    ))
    snapshot = MarketSnapshot(
        timestamp=now,
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
        execution_prices={"BTCUSDT": Decimal("100")},
        current_bars={},
    )
    decision = {
        "decision_mode": "trader",
        "action": "open_short",
        "symbol": "BTCUSDT",
        "quantity": 1,
        "stop_loss_price": 110,
        "trade_plan": {"stop_loss_price": 110},
        "reason": "countertrend is the trader's judgment",
    }
    engine._record_decision(decision, snapshot)
    asyncio.run(engine._execute_decision(decision, snapshot))
    assert engine.account.get_position("BTCUSDT") is not None
    assert decision["execution_result"]["status"] == "filled"


def test_removed_legacy_llm_thresholds_are_not_rule_runtime_parameters():
    params = resolve_rule_params({"decisionMode": "rule", **LEGACY_VETO_CONFIG})
    removed = {
        "min_expected_rr",
        "min_edge_after_cost_pct",
        "decision_safety_buffer_pct",
        "min_open_score",
        "max_signal_conflict",
        "min_hold_bars",
        "reentry_cooldown_bars",
        "min_early_exit_pnl_pct",
    }
    assert removed.isdisjoint(params)


def test_live_trader_executor_rejects_inconsistent_quantity_instead_of_clamping():
    executor = LiveTradingExecutor.__new__(LiveTradingExecutor)
    executor.agent = SimpleNamespace(strategy_config={
        **_hard_policy_config("trader"),
        "minOrderAmount": 1,
        "maxOrderAmount": 999999,
        "hardRiskPolicy": {
            **_hard_policy_config("trader")["hardRiskPolicy"],
            "maxOrderNotionalUSDT": 100,
        },
    })
    with pytest.raises(ValueError, match="RiskKernel 批准数量与执行限额不一致"):
        asyncio.run(executor._place_order(
            action="open_long",
            symbol="BTC-USDT-SWAP",
            quantity=2,
            current_price=100,
            strict_quantity=True,
        ))
