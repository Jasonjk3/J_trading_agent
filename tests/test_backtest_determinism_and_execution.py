from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from backtest.backtest_engine import BacktestConfig, BacktestEngine, KlineData, MarketSnapshot
from backtest.backtest_runner import (
    MissingHistoricalKlineError,
    _get_runtime_tuning,
    _validate_real_kline_coverage,
)
from backtest.llm_replay_cache import (
    activate_replay_cache,
    call_llm_with_replay,
    record_successful_llm_response,
)
from backtest.virtual_account import VirtualAccount
from backtest.risk_manager import RiskManager
from agent_applications.service_agents.trading_decision_agent import TradingDecisionAgent
from trader.risk_kernel import HardRiskPolicy, RiskKernel
from trader.schemas import TraderState, TraderTurn
from trader.state_store import InMemoryTraderStateStore
from trader.event_store import InMemoryTraderEventStore
from trader.orchestrator import TraderOrchestrator
from decision.symbol_context import structured_technical_facts_from_context
from core.llm.base.base_llm import chat_completion_diagnostics
from app.v1.schemas.trading_agent_schema import (
    StrategyConfigSchema,
    expand_strategy_config_for_backtest,
)


def _bar(ts: datetime, o: str, h: str, low: str, c: str) -> KlineData:
    return KlineData(
        timestamp=ts,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1000"),
        quote_volume=Decimal("100000"),
    )


def test_formal_backtest_rejects_missing_or_incomplete_real_klines():
    start = datetime(2026, 1, 8)
    end = start + timedelta(hours=2)
    with __import__('pytest').raises(MissingHistoricalKlineError, match="没有真实 K 线"):
        _validate_real_kline_coverage(
            [], symbol="BTCUSDT", interval="1h", start_time=start, end_time=end
        )

    bars = [
        SimpleNamespace(timestamp=start - timedelta(hours=168) + timedelta(hours=index))
        for index in range(171)
        if index != 169
    ]
    with __import__('pytest').raises(MissingHistoricalKlineError, match="K 线不连续"):
        _validate_real_kline_coverage(
            bars, symbol="BTCUSDT", interval="1h", start_time=start, end_time=end
        )


def _engine_once():
    t0 = datetime(2026, 1, 1, 0, 0)
    observed = {}

    async def decide(snapshot, account, risk_manager):
        observed.setdefault("history_last", snapshot.klines["BTCUSDT"][-1].timestamp)
        observed.setdefault("signal_price", snapshot.prices["BTCUSDT"])
        observed.setdefault("execution_price", snapshot.execution_prices["BTCUSDT"])
        if account.get_position("BTCUSDT"):
            return {"action": "hold", "reason": "already open"}
        return {
            "action": "open_long",
            "symbol": "BTCUSDT",
            "quantity": 1,
            "reason": "deterministic test",
            "trade_plan": {"stop_loss_price": 95, "take_profit_price": 110},
        }

    config = BacktestConfig(
        start_time=t0 + timedelta(hours=1),
        end_time=t0 + timedelta(hours=2),
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        slippage=Decimal("0"),
        market_impact_bps=Decimal("0"),
        impact_volatility_weight=Decimal("0"),
        strategy_config={
            "maxDailyTrades": 50,
            "maxOrderAmount": 10000,
            "maxPositionRatio": 100,
            "hardRiskPolicy": {
                "maxRiskPerTradePct": 100,
                "maxPortfolioRiskPct": 100,
            },
        },
    )
    engine = BacktestEngine(config, decision_callback=decide)
    engine.load_klines(
        "BTCUSDT",
        [
            _bar(t0, "99", "101", "98", "100"),
            # stop 与 take profit 同 bar 命中，必须保守地按 stop 退出。
            _bar(t0 + timedelta(hours=1), "101", "112", "94", "105"),
            _bar(t0 + timedelta(hours=2), "105", "106", "103", "104"),
        ],
    )
    result = asyncio.run(engine.run())
    sequence = [
        (trade.timestamp.isoformat(), trade.side, trade.trade_type, str(trade.price), str(trade.pnl))
        for trade in result.trades
    ]
    return observed, sequence


def test_previous_closed_bar_next_open_and_conservative_intrabar_exit():
    observed, sequence = _engine_once()
    assert observed["history_last"] == datetime(2026, 1, 1, 0, 0)
    assert observed["signal_price"] == Decimal("100")
    assert observed["execution_price"] == Decimal("101")
    assert sequence[0][3] == "101.00000000"
    assert sequence[1][3] == "95.00000000"


def test_same_input_has_identical_trade_sequence_twenty_times():
    sequences = [_engine_once()[1] for _ in range(20)]
    assert len({tuple(sequence) for sequence in sequences}) == 1


def test_round_trip_pnl_includes_entry_and_exit_fees():
    account = VirtualAccount(
        Decimal("1000"), maker_fee=Decimal("0.05"), taker_fee=Decimal("0.1"), slippage=Decimal("0")
    )
    ts = datetime(2026, 1, 1)
    account.open_long("BTCUSDT", Decimal("1"), Decimal("100"), ts, liquidity="maker")
    trade = account.close_long(
        "BTCUSDT", None, Decimal("110"), ts + timedelta(hours=1), liquidity="taker"
    )
    assert trade is not None
    assert trade.pnl == Decimal("9.840")
    assert trade.round_trip_cost == Decimal("0.160")
    assert account.balance == Decimal("1009.840")
    stats = account.get_statistics()
    assert stats["total_trades"] == 1
    assert stats["total_fees"] == 0.16


def test_funding_is_allocated_to_completed_round_trip():
    account = VirtualAccount(Decimal("1000"), maker_fee=Decimal("0"), taker_fee=Decimal("0"))
    ts = datetime(2026, 1, 1)
    account.open_long("BTCUSDT", Decimal("1"), Decimal("100"), ts, slippage_rate=Decimal("0"))
    account.apply_funding({"BTCUSDT": Decimal("100")}, Decimal("0.001"))
    trade = account.close_long(
        "BTCUSDT", None, Decimal("100"), ts + timedelta(hours=8), slippage_rate=Decimal("0")
    )
    assert trade is not None
    assert trade.pnl == Decimal("-0.100")
    assert trade.round_trip_cost == Decimal("0.100")
    assert account.balance == Decimal("999.900")


def test_llm_replay_cache_avoids_second_model_call(tmp_path):
    class FakeLLM:
        model_name = "fake-v1"
        api_url = "local"
        temperature = 0.0

        def __init__(self):
            self.calls = 0

        def _call(self, prompt):
            self.calls += 1
            return '{"action":"hold"}'

    llm = FakeLLM()

    async def exercise():
        with activate_replay_cache(str(tmp_path / "replay.sqlite3"), mode="replay"):
            first, first_meta = await call_llm_with_replay(llm, "same prompt")
            second, second_meta = await call_llm_with_replay(llm, "same prompt")
        return first, second, first_meta, second_meta

    first, second, first_meta, second_meta = asyncio.run(exercise())
    assert first == second
    assert llm.calls == 1
    assert first_meta.cache_hit is False
    assert second_meta.cache_hit is True


def test_llm_record_mode_never_reads_and_only_records_confirmed_success(tmp_path):
    class FakeLLM:
        model_name = "fake-v1"
        api_url = "local"

        def __init__(self):
            self.calls = 0

        def _call(self, prompt):
            self.calls += 1
            return '{"action":"hold"}'

    llm = FakeLLM()
    cache_path = str(tmp_path / "record.sqlite3")

    async def exercise():
        with activate_replay_cache(cache_path, mode="record"):
            first, first_meta = await call_llm_with_replay(llm, "same prompt")
            saved = await record_successful_llm_response(llm, "same prompt", first)
            second, second_meta = await call_llm_with_replay(llm, "same prompt")
        return first, second, first_meta, second_meta, saved

    first, second, first_meta, second_meta, saved = asyncio.run(exercise())
    assert first == second
    assert saved is True
    assert llm.calls == 2
    assert first_meta.cache_hit is False
    assert second_meta.cache_hit is False


def test_backtest_llm_cache_mode_defaults_to_fresh():
    assert StrategyConfigSchema().llmCacheMode == "fresh"


def test_trader_prompt_exposes_facts_and_hard_policy_without_signal_score_template():
    t0 = datetime(2026, 1, 1)
    bars = [
        _bar(t0 + timedelta(hours=i), str(100 + i), str(102 + i), str(99 + i), str(101 + i))
        for i in range(50)
    ]
    snapshot = SimpleNamespace(
        timestamp=t0 + timedelta(hours=50),
        prices={"BTCUSDT": bars[-1].close},
        klines={"BTCUSDT": bars},
    )
    agent = TradingDecisionAgent(
        llm=object(),
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
            "technicalAnalysisTimeframe": "1h",
        },
    )
    prompt = agent._build_prompt(
        TraderState(session_id=agent.orchestrator.session_id),
        snapshot,
        VirtualAccount(Decimal("1000")),
        {"technical_facts": {}},
    )
    assert "hard_risk_policy" in prompt
    assert "previous_state" in prompt
    assert "order_intents" in prompt
    assert "recent_ohlcv" in prompt
    assert "保护性止损" in prompt
    assert "open_score" not in prompt
    assert "signal_conflict" not in prompt


def test_open_is_rejected_when_next_open_invalidates_trade_plan():
    t0 = datetime(2026, 1, 1)

    async def decide(snapshot, account, risk_manager):
        return {
            "action": "open_long",
            "symbol": "BTCUSDT",
            "quantity": 1,
            "reason": "gap test",
            "trade_plan": {"stop_loss_price": 95, "take_profit_price": 110},
        }

    config = BacktestConfig(
        start_time=t0 + timedelta(hours=1),
        end_time=t0 + timedelta(hours=1),
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        slippage=Decimal("0"),
        market_impact_bps=Decimal("0"),
        impact_volatility_weight=Decimal("0"),
        strategy_config={"maxDailyTrades": 50, "maxOrderAmount": 10000, "maxPositionRatio": 100},
    )
    engine = BacktestEngine(config, decision_callback=decide)
    engine.load_klines(
        "BTCUSDT",
        [_bar(t0, "99", "101", "98", "100"), _bar(t0 + timedelta(hours=1), "111", "113", "109", "112")],
    )
    result = asyncio.run(engine.run())
    assert result.trades == []
    assert result.decision_log[-1]["action"] == "hold"
    assert "execution_revalidation_rejected" in result.decision_log[-1]["signals"]
    assert result.decision_log[-1]["execution_result"]["status"] == "rejected"
    assert result.decision_log[-1]["execution_result"]["requestedAction"] == "open_long"
    assert result.decision_log[-1]["execution_result"]["finalAction"] == "hold"


def test_close_without_quantity_closes_position():
    t0 = datetime(2026, 1, 1)

    async def decide(snapshot, account, risk_manager):
        if account.get_position("BTCUSDT"):
            return {"action": "close_long", "symbol": "BTCUSDT", "reason": "exit"}
        return {
            "action": "open_long",
            "symbol": "BTCUSDT",
            "quantity": 1,
            "reason": "entry",
            "trade_plan": {"stop_loss_price": 90, "take_profit_price": 120},
        }

    config = BacktestConfig(
        start_time=t0 + timedelta(hours=1),
        end_time=t0 + timedelta(hours=2),
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        slippage=Decimal("0"),
        market_impact_bps=Decimal("0"),
        impact_volatility_weight=Decimal("0"),
        strategy_config={"maxDailyTrades": 50, "maxOrderAmount": 10000, "maxPositionRatio": 100},
    )
    engine = BacktestEngine(config, decision_callback=decide)
    engine.load_klines(
        "BTCUSDT",
        [
            _bar(t0, "99", "101", "98", "100"),
            _bar(t0 + timedelta(hours=1), "101", "103", "100", "102"),
            _bar(t0 + timedelta(hours=2), "103", "105", "102", "104"),
        ],
    )
    result = asyncio.run(engine.run())
    assert [trade.trade_type for trade in result.trades] == ["open", "close"]
    assert result.trades[-1].price == Decimal("103.00000000")


def test_weak_single_timeframe_trend_is_not_reported_as_consensus():
    facts = structured_technical_facts_from_context(
        {
            "symbol": "BTCUSDT",
            "current_f": 100,
            "ma5": 101,
            "ma20": 100,
            "trend_strength": "weak",
            "adx": 14,
            "indicators": {"rsi": 55, "macd": {"histogram": 0.1}},
        },
        execution_tf="1h",
        as_of=datetime(2026, 1, 1),
    )
    assert facts["timeframes"]["1h"]["trend"] == "bullish"
    assert facts["consensus"] == "mixed"


def test_risk_kernel_resizes_by_declared_stop_risk():
    account = VirtualAccount(Decimal("1000"))
    kernel = RiskKernel(
        HardRiskPolicy(
            allowed_symbols=("BTCUSDT",),
            max_order_notional=Decimal("1000"),
            max_symbol_exposure_pct=Decimal("100"),
            max_gross_exposure_pct=Decimal("100"),
            max_risk_per_trade_pct=Decimal("0.5"),
            max_portfolio_risk_pct=Decimal("1.5"),
        )
    )
    result = kernel.evaluate(
        {
            "action": "open_long",
            "symbol": "BTCUSDT",
            "quantity": 10,
            "stop_loss_price": 95,
        },
        account,
        {"BTCUSDT": Decimal("100")},
    )
    assert result.status == "resized"
    assert result.approved_decision["quantity"] == 1.0
    assert result.computed_risk["incrementalRiskUSDT"] == 5.0


def test_chat_completion_diagnostics_report_shape_without_response_text():
    response = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": "secret-final",
                    "reasoning_content": "secret-reasoning",
                    "provider_extension": {"value": 1},
                },
            }
        ],
        "usage": {
            "prompt_tokens": 4200,
            "completion_tokens": 1024,
            "total_tokens": 5224,
        },
    }
    diagnostics = chat_completion_diagnostics(
        response,
        {"max_tokens": 1024, "messages": [{"content": "secret-prompt"}]},
    )
    assert diagnostics["finish_reason"] == "length"
    assert diagnostics["message_fields"] == [
        "content",
        "provider_extension",
        "reasoning_content",
        "role",
    ]
    assert diagnostics["content_type"] == "str"
    assert diagnostics["content_length"] == len("secret-final")
    assert diagnostics["reasoning_content_length"] == len("secret-reasoning")
    assert diagnostics["usage"]["total_tokens"] == 5224
    assert diagnostics["request_max_tokens"] == 1024
    assert "secret" not in repr(diagnostics)


def test_explicit_max_position_ratio_overrides_style_default():
    legacy = StrategyConfigSchema(tradingStyle="aggressive")
    assert legacy.get_derived_params()["maxPositionRatio"] == 50.0

    explicit = StrategyConfigSchema(
        tradingStyle="aggressive",
        maxPositionRatio=37.5,
    )
    assert explicit.get_derived_params()["maxPositionRatio"] == 37.5

    expanded = expand_strategy_config_for_backtest(
        {"tradingStyle": "conservative", "maxPositionRatio": 42.0},
        interval="1h",
    )
    assert expanded["maxPositionRatio"] == 42.0
    assert RiskManager.from_strategy_config(
        {"tradingStyle": "aggressive", "maxPositionRatio": None}
    ).config.max_position_ratio == Decimal("50")

    default_policy = HardRiskPolicy.from_strategy_config({"tradingStyle": "conservative"})
    assert default_policy.max_gross_exposure_pct == Decimal("30")
    assert default_policy.min_leverage == Decimal("1")
    assert default_policy.max_leverage == Decimal("1")

    explicit_policy = HardRiskPolicy.from_strategy_config({"maxPositionRatio": 42})
    assert explicit_policy.max_gross_exposure_pct == Decimal("210")


def test_trading_style_enforces_leverage_permission_in_schema_and_risk_kernel():
    with __import__('pytest').raises(Exception, match="至少 2x"):
        StrategyConfigSchema(tradingStyle="aggressive", maxLeverage=1)

    conservative = StrategyConfigSchema(
        tradingStyle="conservative", maxLeverage=20
    )
    assert conservative.maxLeverage == 1
    assert conservative.get_derived_params()["maxLeverage"] == 1

    account = VirtualAccount(
        Decimal("1000"), maker_fee=Decimal("0"), taker_fee=Decimal("0")
    )
    base_decision = {
        "action": "open_long",
        "symbol": "BTCUSDT",
        "quantity": 1,
        "stop_loss_price": 95,
    }
    aggressive_policy = HardRiskPolicy.from_strategy_config({
        "tradingStyle": "aggressive",
        "symbols": ["BTCUSDT"],
        "maxLeverage": 20,
        "maxOrderAmount": 1000,
    })
    assert aggressive_policy.min_leverage == Decimal("2")
    rejected = RiskKernel(aggressive_policy).evaluate(
        {**base_decision, "requested_leverage": 1},
        account,
        {"BTCUSDT": Decimal("100")},
    )
    assert rejected.status == "rejected"
    assert rejected.violations[0].code == "leverage_required_by_style"

    balanced = RiskKernel.from_strategy_config({
        "tradingStyle": "balanced",
        "symbols": ["BTCUSDT"],
        "maxLeverage": 20,
        "maxOrderAmount": 1000,
    }).evaluate(
        {**base_decision, "requested_leverage": 1},
        account,
        {"BTCUSDT": Decimal("100")},
    )
    assert balanced.approved_decision["leverage"] == 1.0

    stable = RiskKernel.from_strategy_config({
        "tradingStyle": "conservative",
        "symbols": ["BTCUSDT"],
        "maxLeverage": 20,
        "maxOrderAmount": 1000,
    }).evaluate(
        {**base_decision, "requested_leverage": 10},
        account,
        {"BTCUSDT": Decimal("100")},
    )
    assert stable.status == "resized"
    assert stable.approved_decision["leverage"] == 1.0


def test_llm_entry_must_request_leverage_and_risk_kernel_clamps_it():
    payload = {
        "session_id": "leverage-contract",
        "as_of": datetime(2026, 1, 1),
        "market_view": {"summary": "entry"},
        "order_intents": [{
            "symbol": "BTCUSDT",
            "side": "buy",
            "effect": "open",
            "position_side": "long",
            "size": {"mode": "quantity", "quantity": 1},
            "protection": {"stop_loss_price": 95},
        }],
        "next_review": {"events": ["bar_closed"]},
    }
    with __import__('pytest').raises(Exception, match="requested_leverage"):
        TraderTurn.model_validate(payload)

    payload["order_intents"][0]["requested_leverage"] = 20
    turn = TraderTurn.model_validate(payload)
    decision = TraderOrchestrator("leverage-contract")._intent_to_decision(
        turn.order_intents[0],
        SimpleNamespace(
            timestamp=datetime(2026, 1, 1),
            prices={"BTCUSDT": Decimal("100")},
        ),
        VirtualAccount(Decimal("1000"), maker_fee=Decimal("0"), taker_fee=Decimal("0")),
        HardRiskPolicy(
            allowed_symbols=("BTCUSDT",),
            max_leverage=Decimal("5"),
            max_order_notional=Decimal("1000"),
            max_order_margin=Decimal("1000"),
            max_margin_usage_pct=Decimal("100"),
            max_symbol_exposure_pct=Decimal("100"),
            max_gross_exposure_pct=Decimal("100"),
            max_risk_per_trade_pct=Decimal("100"),
            max_portfolio_risk_pct=Decimal("100"),
        ),
    )
    evaluation = RiskKernel(HardRiskPolicy(
        allowed_symbols=("BTCUSDT",),
        max_leverage=Decimal("5"),
        max_order_notional=Decimal("1000"),
        max_order_margin=Decimal("1000"),
        max_margin_usage_pct=Decimal("100"),
        max_symbol_exposure_pct=Decimal("100"),
        max_gross_exposure_pct=Decimal("100"),
        max_risk_per_trade_pct=Decimal("100"),
        max_portfolio_risk_pct=Decimal("100"),
    )).evaluate(
        decision,
        VirtualAccount(Decimal("1000"), maker_fee=Decimal("0"), taker_fee=Decimal("0")),
        {"BTCUSDT": Decimal("100")},
    )
    assert evaluation.status == "resized"
    assert evaluation.approved_decision["requested_leverage"] == 20.0
    assert evaluation.approved_decision["leverage"] == 5.0


def test_margin_budget_allows_leveraged_notional_above_account_equity():
    account = VirtualAccount(Decimal("100000"), maker_fee=Decimal("0"), taker_fee=Decimal("0"))
    policy = HardRiskPolicy.from_strategy_config({
        "symbols": ["BTCUSDT"],
        "maxOrderAmount": 10000,
        "maxPositionRatio": 80,
        "maxLeverage": 20,
    })
    evaluation = RiskKernel(policy).evaluate({
        "action": "open_long",
        "symbol": "BTCUSDT",
        "quantity": 1000,
        "requested_leverage": 10,
        "stop_loss_price": 99.95,
    }, account, {"BTCUSDT": Decimal("100")})
    assert evaluation.status == "approved"
    assert evaluation.computed_risk["approvedNotional"] == 100000.0
    assert evaluation.computed_risk["marginRequired"] == 10000.0
    assert evaluation.computed_risk["marginUsagePctAfter"] == 10.0


def test_virtual_account_uses_approved_leverage_for_margin_and_trade_audit():
    account = VirtualAccount(Decimal("1000"), maker_fee=Decimal("0"), taker_fee=Decimal("0"))
    trade = account.open_long(
        "BTCUSDT",
        Decimal("10"),
        Decimal("100"),
        datetime(2026, 1, 1),
        slippage_rate=Decimal("0"),
        leverage=Decimal("5"),
    )
    assert trade is not None
    assert trade.leverage == Decimal("5")
    assert account.balance == Decimal("800.00000000")
    assert account.equity == Decimal("1000.00000000")
    assert account.get_position("BTCUSDT").margin_used == Decimal("200.00000000")
    assert account.get_position("BTCUSDT").leverage == Decimal("5")


def test_trader_parse_failure_is_system_error_and_never_a_hold():
    agent = TradingDecisionAgent(
        llm=object(),
        strategy_config={"symbols": ["ETHUSDT"], "decisionMode": "trader"},
    )
    account = VirtualAccount(Decimal("1000"))
    malformed = '{"action":"hold","symbol":"ETHUSDT","thesis":"truncated'

    try:
        agent._parse_turn(malformed, datetime(2026, 1, 1))
    except ValueError as exc:
        assert "合法 JSON" in str(exc)
    else:
        raise AssertionError("malformed trader response must fail")


def test_trader_missing_no_trade_reason_is_rejected_instead_of_inferred():
    agent = TradingDecisionAgent(
        llm=object(),
        strategy_config={"symbols": ["BTCUSDT"], "decisionMode": "trader"},
    )

    try:
        agent._parse_turn(
            __import__('json').dumps({
                "schema_version": "trader-turn-v1",
                "response_type": "final",
                "market_view": {
                    "summary": "量价证据不足，等待下一根 K 线确认",
                    "regime": None,
                    "key_drivers": [],
                    "counter_evidence": [],
                    "uncertainties": [],
                },
                "plan_updates": [],
                "order_intents": [],
                "cancel_order_intents": [],
                "pending_order_actions": [],
                "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
            }),
            datetime(2026, 1, 1),
        )
    except ValueError as exc:
        assert "no_trade_reason" in str(exc)
    else:
        raise AssertionError("missing no_trade_reason must be rejected")


def test_trader_final_contract_rejects_state_storage_fields_and_past_review():
    agent = TradingDecisionAgent(
        llm=object(),
        strategy_config={"symbols": ["BTCUSDT"], "decisionMode": "trader"},
    )
    payload = agent._final_output_template()
    payload.update({
        "plan_updates": [],
        "order_intents": [],
        "cancel_order_intents": [],
        "pending_order_actions": [],
        "no_trade_reason": "等待确认",
        "next_review": {
            "at": "2026-01-01T02:00:00Z",
            "events": ["bar_closed"],
            "conditions": [],
        },
        "plans": {"BTCUSDT": {"status": "flat_no_trade"}},
    })

    try:
        agent._parse_turn(
            __import__('json').dumps(payload), datetime(2026, 1, 1, 1)
        )
    except ValueError as exc:
        assert "未定义顶层字段" in str(exc)
        assert "plans" in str(exc)
    else:
        raise AssertionError("state storage fields must not be accepted in a turn")

    payload.pop("plans")
    payload["next_review"] = {
        "at": "2025-12-31T23:00:00Z",
        "events": ["BTC/ETH 1h K 线收盘"],
        "conditions": [],
    }
    try:
        agent._parse_turn(
            __import__('json').dumps(payload), datetime(2026, 1, 1, 1)
        )
    except ValueError as exc:
        assert "未定义事件" in str(exc)
    else:
        raise AssertionError("free-form review events must not be accepted")

    payload["next_review"]["events"] = ["bar_closed"]
    try:
        agent._parse_turn(
            __import__('json').dumps(payload), datetime(2026, 1, 1, 1)
        )
    except ValueError as exc:
        assert "晚于当前 as_of" in str(exc)
    else:
        raise AssertionError("past review time must not be accepted")


def test_trader_validation_failure_preserves_raw_audit_artifacts():
    class InvalidTurnLLM:
        model_name = "invalid-turn-model"

        def _call(self, prompt):
            return __import__('json').dumps({
                "schema_version": "trader-turn-v1",
                "response_type": "final",
                "market_view": {"summary": "尝试返回非法订单集合"},
                "order_intents": "not-a-list",
            })

    agent = TradingDecisionAgent(
        llm=InvalidTurnLLM(),
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
            "llmParseRetries": 0,
        },
    )
    snapshot = SimpleNamespace(
        timestamp=datetime(2026, 1, 1),
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
    )

    decision = asyncio.run(
        agent.make_decision(snapshot, VirtualAccount(Decimal("1000")))
    )

    assert decision["action"] == "system_error"
    assert "not-a-list" in decision["llm_raw_response"]
    assert "当前最小上下文" in decision["decision_prompt"]
    assert decision["llm_metadata"]["model"] == "invalid-turn-model"


def test_trader_classifies_llm_client_error_text_as_transport_failure():
    class ConnectionFailureLLM:
        model_name = "unavailable-model"

        def __init__(self):
            self.calls = 0

        def _call(self, prompt):
            self.calls += 1
            return "AI服务请求连接错误，已重试3次，请稍后再试。"

    llm = ConnectionFailureLLM()
    agent = TradingDecisionAgent(
        llm=llm,
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
            "llmParseRetries": 2,
        },
    )
    snapshot = SimpleNamespace(
        timestamp=datetime(2026, 1, 1),
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
    )

    decision = asyncio.run(
        agent.make_decision(snapshot, VirtualAccount(Decimal("1000")))
    )

    assert llm.calls == 1
    assert decision["action"] == "system_error"
    assert decision["error_type"] == "llm_transport_error"
    assert decision["llm_raw_response"].startswith("AI服务请求连接错误")
    assert "当前最小上下文" in decision["decision_prompt"]
    assert decision["llm_metadata"]["failure_kind"] == "transport"
    assert decision["llm_metadata"]["parse_retry_count"] == 0


def test_trader_retries_legacy_order_shape_instead_of_guessing_direction():
    class RepairingLLM:
        model_name = "repairing-model"

        def __init__(self):
            self.calls = 0
            self.prompts = []

        def _call(self, prompt):
            self.calls += 1
            self.prompts.append(prompt)
            if self.calls == 1:
                return __import__('json').dumps({
                    "schema_version": "trader-turn-v1",
                    "response_type": "final",
                    "market_view": {"summary": "BTC 突破后回踩"},
                    "order_intents": [{
                        "symbol": "BTCUSDT",
                        "side": "buy",
                        "qty": 0.2,
                        "order_type": "limit",
                        "limit_price": 100,
                        "stop_loss": 95,
                        "reason": "回踩确认",
                    }],
                })
            return __import__('json').dumps({
                "schema_version": "trader-turn-v1",
                "response_type": "final",
                "market_view": {
                    "summary": "BTC 突破后回踩", "regime": "trend",
                    "trend_state": "weak_bullish",
                    "key_drivers": [], "counter_evidence": [], "uncertainties": [],
                },
                "plan_updates": [],
                "order_intents": [{
                    "client_intent_id": "btc-long-retest",
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "effect": "open",
                    "position_side": "long",
                    "requested_leverage": 2,
                    "order_type": "limit",
                    "execution_role": "standalone",
                    "parent_intent_id": None,
                    "limit_price": 100,
                    "size": {
                        "mode": "quantity", "risk_pct_equity": None,
                        "notional_usdt": None, "quantity": 0.2,
                    },
                    "protection": {"stop_loss_price": 95, "take_profit_price": None},
                    "rationale": "回踩确认",
                    "thesis": "突破延续",
                    "invalidation": "跌破 95",
                    "expires_at": "2026-01-01T01:00:00",
                }],
                "cancel_order_intents": [],
                "pending_order_actions": [],
                "no_trade_reason": None,
                "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
            })

    llm = RepairingLLM()
    agent = TradingDecisionAgent(
        llm=llm,
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
            "llmParseRetries": 1,
        },
    )
    snapshot = SimpleNamespace(
        timestamp=datetime(2026, 1, 1),
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
    )

    decision = asyncio.run(
        agent.make_decision(snapshot, VirtualAccount(Decimal("1000")))
    )

    assert decision["action"] == "hold"
    assert decision["outcome_type"] == "SHADOW_PROPOSAL"
    assert llm.calls == 2
    assert "effect=open|add|reduce|close" in llm.prompts[1]
    assert decision["llm_metadata"]["parse_retry_count"] == 1
    assert len(decision["llm_metadata"]["validation_failures"]) == 1


def test_trader_rejects_still_invalid_order_after_parse_retries():
    class PersistentlyInvalidOrderLLM:
        model_name = "persistently-invalid-order-model"

        def __init__(self):
            self.calls = 0

        def _call(self, prompt):
            self.calls += 1
            return __import__('json').dumps({
                "schema_version": "trader-turn-v1",
                "response_type": "final",
                "market_view": {
                    "summary": "ETH 突破，但订单协议字段不完整", "regime": "trend",
                    "trend_state": "weak_bullish",
                    "key_drivers": [], "counter_evidence": [], "uncertainties": [],
                },
                "plan_updates": [],
                "order_intents": [{
                    "intent_id": "eth-long-retest",
                    "symbol": "ETHUSDT",
                    "side": "buy",
                    "order_type": "limit",
                    "limit_price": 100,
                    "size": {
                        "mode": "quantity", "risk_pct_equity": None,
                        "notional_usdt": None, "quantity": 0.2,
                    },
                    "protection": {"stop_loss_price": 95, "take_profit_price": None},
                    "rationale": "突破回踩",
                    "thesis": "突破延续",
                    "invalidation": "跌破 95",
                    "expires_at": None,
                }],
                "cancel_order_intents": [],
                "pending_order_actions": [],
                "no_trade_reason": None,
                "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
            })

    llm = PersistentlyInvalidOrderLLM()
    agent = TradingDecisionAgent(
        llm=llm,
        strategy_config={
            "symbols": ["ETHUSDT"],
            "decisionMode": "trader",
            "llmParseRetries": 2,
        },
    )
    snapshot = SimpleNamespace(
        timestamp=datetime(2026, 1, 1),
        prices={"ETHUSDT": Decimal("100")},
        klines={"ETHUSDT": []},
    )

    decision = asyncio.run(
        agent.make_decision(snapshot, VirtualAccount(Decimal("1000")))
    )

    assert llm.calls == 3
    assert decision["action"] == "hold"
    assert decision["outcome_type"] == "NO_TRADE"
    assert "安全策略拒绝" in decision["reason"]
    assert decision["llm_metadata"]["parse_retry_count"] == 2
    assert len(decision["llm_metadata"]["validation_failures"]) == 3
    rejected = decision["llm_metadata"]["rejected_order_intents"]
    assert len(rejected) == 1
    assert rejected[0]["client_intent_id"] == "eth-long-retest"
    assert "effect" in rejected[0]["error"]
    assert "position_side" in rejected[0]["error"]


def test_backtest_records_system_error_without_executing_a_trade():
    t0 = datetime(2026, 1, 1)

    async def decide(snapshot, account, risk_manager):
        return {
            "action": "system_error",
            "error_type": "llm_parse_error",
            "reason": "LLM 响应解析失败",
            "signals": ["schema_parse_failed"],
        }

    config = BacktestConfig(
        start_time=t0,
        end_time=t0 + timedelta(hours=1),
        initial_capital=Decimal("1000"),
        symbols=["ETHUSDT"],
        interval="1h",
    )
    engine = BacktestEngine(config, decision_callback=decide)
    snapshot = MarketSnapshot(
        timestamp=t0,
        prices={"ETHUSDT": Decimal("100")},
        klines={"ETHUSDT": []},
    )

    status = asyncio.run(engine._run_decision(snapshot))

    assert status is None
    assert engine.decision_log[-1]["action"] == "system_error"
    assert engine.decision_log[-1]["error_type"] == "llm_parse_error"
    assert engine.account.trades == []


def test_position_order_intents_are_direction_specific_and_quantity_is_capped():
    agent = TradingDecisionAgent(
        llm=object(),
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
        },
    )
    account = VirtualAccount(Decimal("1000"), maker_fee=Decimal("0"), taker_fee=Decimal("0"))
    now = datetime(2026, 1, 1)
    account.open_long("BTCUSDT", Decimal("2"), Decimal("100"), now, slippage_rate=Decimal("0"))
    position = account.get_position("BTCUSDT")
    position.trade_plan = {"stop_loss_price": 90, "take_profit_price": 130}
    snapshot = SimpleNamespace(timestamp=now + timedelta(hours=1), prices={"BTCUSDT": Decimal("105")})

    turn = agent._parse_turn(
        __import__('json').dumps(
        {
            "schema_version": "trader-turn-v1",
            "response_type": "final",
            "market_view": {
                "summary": "edge weakened", "regime": None,
                "trend_state": "unclear",
                "key_drivers": [], "counter_evidence": [], "uncertainties": [],
            },
            "plan_updates": [],
            "order_intents": [{
                "client_intent_id": "btc-long-reduce",
                "symbol": "BTCUSDT",
                "side": "sell",
                "effect": "reduce",
                "position_side": "long",
                "requested_leverage": None,
                "order_type": "market",
                "execution_role": "standalone",
                "parent_intent_id": None,
                "limit_price": None,
                "size": {
                    "mode": "quantity", "risk_pct_equity": None,
                    "notional_usdt": None, "quantity": 0.8,
                },
                "protection": {"stop_loss_price": None, "take_profit_price": None},
                "rationale": "交易优势减弱",
                "thesis": "long edge weakened",
                "invalidation": "risk reduction",
                "expires_at": None,
            }],
            "cancel_order_intents": [],
            "pending_order_actions": [],
            "no_trade_reason": None,
            "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
        }),
        snapshot.timestamp,
    )
    reduced = agent.orchestrator._intent_to_decision(
        turn.order_intents[0], snapshot, account, agent.policy
    )
    assert reduced["action"] == "reduce_long"
    assert reduced["quantity"] == 0.8

    try:
        wrong_turn = agent._parse_turn(
            __import__('json').dumps({
                "schema_version": "trader-turn-v1",
                "response_type": "final",
                "market_view": {
                    "summary": "wrong side", "regime": None,
                    "trend_state": "unclear",
                    "key_drivers": [], "counter_evidence": [], "uncertainties": [],
                },
                "plan_updates": [],
                "order_intents": [{
                    "client_intent_id": "btc-short-reduce",
                    "symbol": "BTCUSDT",
                    "side": "buy",
                    "effect": "reduce",
                    "position_side": "short",
                    "requested_leverage": None,
                    "order_type": "market",
                    "execution_role": "standalone",
                    "parent_intent_id": None,
                    "limit_price": None,
                    "size": {
                        "mode": "quantity", "risk_pct_equity": None,
                        "notional_usdt": None, "quantity": 0.5,
                    },
                    "protection": {"stop_loss_price": None, "take_profit_price": None},
                    "rationale": "持仓方向不匹配",
                    "thesis": "wrong side",
                    "invalidation": "position mismatch",
                    "expires_at": None,
                }],
                "cancel_order_intents": [],
                "pending_order_actions": [],
                "no_trade_reason": None,
                "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
            }),
            snapshot.timestamp,
        )
        agent.orchestrator._intent_to_decision(
            wrong_turn.order_intents[0], snapshot, account, agent.policy
        )
    except ValueError as exc:
        assert "持仓不匹配" in str(exc)
    else:
        raise AssertionError("wrong-side position action must fail")


def test_trader_orchestrator_persists_thesis_and_audit_events_across_turns():
    state_store = InMemoryTraderStateStore()
    event_store = InMemoryTraderEventStore()
    orchestrator = TraderOrchestrator(
        "backtest:test-agent",
        state_store=state_store,
        event_store=event_store,
    )
    seen_revisions = []

    async def exercise():
        async def first(previous):
            seen_revisions.append(previous.revision)
            return TraderTurn.model_validate({
                "session_id": previous.session_id,
                "as_of": datetime(2026, 1, 1),
                "market_view": {"summary": "BTC structure remains constructive"},
                "plan_updates": [{
                    "symbol": "BTCUSDT",
                    "status": "watching",
                    "thesis": "wait for breakout confirmation",
                    "invalidation": "daily structure fails",
                }],
                "order_intents": [],
                "no_trade_reason": "confirmation missing",
                "next_review": {"events": ["bar_closed"]},
            })

        async def second(previous):
            seen_revisions.append(previous.revision)
            assert previous.market_view.summary == "BTC structure remains constructive"
            assert previous.plans["BTCUSDT"].thesis == "wait for breakout confirmation"
            return TraderTurn.model_validate({
                "session_id": previous.session_id,
                "as_of": datetime(2026, 1, 1, 1),
                "market_view": {"summary": "view unchanged"},
                "plan_updates": [],
                "order_intents": [],
                "no_trade_reason": "no new evidence",
                "next_review": {"events": ["news_arrived"]},
            })

        await orchestrator.run_turn(
            as_of=datetime(2026, 1, 1), wake_reason="bar_closed", generate=first
        )
        return await orchestrator.run_turn(
            as_of=datetime(2026, 1, 1, 1), wake_reason="bar_closed", generate=second
        )

    _, final_state = asyncio.run(exercise())
    assert seen_revisions == [0, 1]
    assert final_state.revision == 2
    assert len(event_store.turns) == 2
    assert [item["event_type"] for item in event_store.events] == [
        "turn_woke", "no_trade", "review_registered", "turn_completed",
        "turn_woke", "no_trade", "review_registered", "turn_completed",
    ]


def test_trader_agent_reuses_previous_state_and_shadows_intents_by_default():
    class FakeLLM:
        model_name = "fake-trader-v1"

        def __init__(self):
            self.prompts = []

        def _call(self, prompt):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                return __import__('json').dumps({
                    "schema_version": "trader-turn-v1",
                    "response_type": "final",
                    "market_view": {
                        "summary": "breakout thesis forming", "regime": "trend",
                        "trend_state": "weak_bullish",
                        "key_drivers": [], "counter_evidence": [], "uncertainties": [],
                    },
                    "plan_updates": [{
                        "symbol": "BTCUSDT",
                        "status": "active",
                        "thesis": "breakout can extend",
                        "invalidation": "price below 95",
                        "evidence": [],
                        "counter_evidence": [],
                        "review_triggers": [],
                    }],
                    "order_intents": [{
                        "client_intent_id": "btc-breakout-open",
                        "symbol": "BTCUSDT",
                        "side": "buy",
                        "effect": "open",
                        "position_side": "long",
                        "requested_leverage": 2,
                        "order_type": "market",
                        "execution_role": "standalone",
                        "parent_intent_id": None,
                        "limit_price": None,
                        "size": {
                            "mode": "risk_budget", "risk_pct_equity": 0.25,
                            "notional_usdt": None, "quantity": None,
                        },
                        "protection": {"stop_loss_price": 95, "take_profit_price": None},
                        "rationale": "结构已经确认",
                        "thesis": "breakout can extend",
                        "invalidation": "price below 95",
                        "expires_at": None,
                    }],
                    "cancel_order_intents": [],
                    "pending_order_actions": [],
                    "no_trade_reason": None,
                    "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
                })
            return __import__('json').dumps({
                "schema_version": "trader-turn-v1",
                "response_type": "final",
                "market_view": {
                    "summary": "breakout thesis still valid", "regime": "trend",
                    "trend_state": "weak_bullish",
                    "key_drivers": [], "counter_evidence": [], "uncertainties": [],
                },
                "plan_updates": [],
                "order_intents": [],
                "cancel_order_intents": [],
                "pending_order_actions": [],
                "no_trade_reason": "没有新的有效证据",
                "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
            })

    llm = FakeLLM()
    agent = TradingDecisionAgent(
        agent_id="stateful-agent",
        llm=llm,
        strategy_config={"symbols": ["BTCUSDT"], "decisionMode": "trader"},
    )
    account = VirtualAccount(Decimal("1000"))
    snapshot = SimpleNamespace(
        timestamp=datetime(2026, 1, 1),
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
    )

    async def exercise():
        first = await agent.make_decision(snapshot, account, analysis_context={})
        snapshot.timestamp += timedelta(hours=1)
        second = await agent.make_decision(snapshot, account, analysis_context={})
        return first, second

    first, second = asyncio.run(exercise())
    assert first["action"] == "hold"
    assert first["shadow_order_intents"][0]["effect"] == "open"
    assert first["trader_state_revision"] == 1
    assert second["trader_state_revision"] == 2
    assert "breakout thesis forming" in llm.prompts[1]


def test_backtest_executes_add_and_partial_reduce_actions():
    now = datetime(2026, 1, 1)
    config = BacktestConfig(
        start_time=now,
        end_time=now + timedelta(hours=1),
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        slippage=Decimal("0"),
        market_impact_bps=Decimal("0"),
        impact_volatility_weight=Decimal("0"),
        strategy_config={
            "maxDailyTrades": 50,
            "maxOrderAmount": 10000,
            "maxPositionRatio": 100,
            "hardRiskPolicy": {
                "maxRiskPerTradePct": 100,
                "maxPortfolioRiskPct": 100,
            },
        },
    )
    engine = BacktestEngine(config)
    engine.account.open_long(
        "BTCUSDT", Decimal("1"), Decimal("100"), now, slippage_rate=Decimal("0")
    )
    snapshot = MarketSnapshot(
        timestamp=now + timedelta(hours=1),
        prices={"BTCUSDT": Decimal("110")},
        execution_prices={"BTCUSDT": Decimal("110")},
        klines={"BTCUSDT": []},
    )

    add_decision = {
        "action": "add_long",
        "symbol": "BTCUSDT",
        "quantity": 0.5,
        "reason": "edge strengthened",
        "trade_plan": {"stop_loss_price": 90, "take_profit_price": 150},
    }
    engine._record_decision(add_decision, snapshot)
    asyncio.run(engine._execute_decision(add_decision, snapshot))
    assert engine.account.get_position("BTCUSDT").quantity == Decimal("1.5")
    assert engine.account.trades[-1].action == "add_long"
    assert engine.decision_log[-1]["execution_result"]["status"] == "filled"
    assert engine.decision_log[-1]["execution_result"]["quantity"] == 0.5
    assert engine.decision_log[-1]["execution_result"]["positionQuantityAfter"] == 1.5

    reduce_decision = {
        "action": "reduce_long",
        "symbol": "BTCUSDT",
        "quantity": 0.6,
        "reason": "edge weakened",
    }
    engine._record_decision(reduce_decision, snapshot)
    asyncio.run(engine._execute_decision(reduce_decision, snapshot))
    assert engine.account.get_position("BTCUSDT").quantity == Decimal("0.9")
    assert [trade.trade_type for trade in engine.account.trades] == ["open", "open", "close"]
    assert [trade.action for trade in engine.account.trades] == ["open_long", "add_long", "reduce_long"]
    assert engine.decision_log[-1]["execution_result"]["status"] == "filled"
    assert engine.decision_log[-1]["execution_result"]["quantity"] == 0.6
    assert engine.decision_log[-1]["execution_result"]["positionQuantityAfter"] == 0.9
    assert engine.account.total_trades == 0

    asyncio.run(
        engine._execute_decision(
            {
                "action": "close_long",
                "symbol": "BTCUSDT",
                "reason": "thesis invalidated",
            },
            snapshot,
        )
    )
    assert engine.account.get_position("BTCUSDT") is None
    assert engine.account.total_trades == 1
    assert engine.account.trades[-1].round_trip_complete is True
    assert engine.account.trades[-1].round_trip_pnl == sum(
        trade.pnl for trade in engine.account.trades if trade.trade_type == "close"
    )


def test_execution_price_gap_caps_quantity_instead_of_rejecting_max_order():
    now = datetime(2026, 1, 1)
    config = BacktestConfig(
        start_time=now,
        end_time=now + timedelta(hours=1),
        initial_capital=Decimal("10000"),
        symbols=["ETHUSDT"],
        interval="1h",
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        slippage=Decimal("0"),
        market_impact_bps=Decimal("0"),
        impact_volatility_weight=Decimal("0"),
        strategy_config={
            "minOrderAmount": 10,
            "maxOrderAmount": 5000,
            "maxPositionRatio": 100,
            "maxDailyTrades": 50,
        },
    )
    engine = BacktestEngine(config)
    decision = {
        "action": "open_long",
        "symbol": "ETHUSDT",
        # 信号价 100 时恰好 5000；下一根开盘涨到 101 后原数量会变成 5050。
        "quantity": 50,
        "reason": "gap sizing test",
        "trade_plan": {"stop_loss_price": 90, "take_profit_price": 130},
    }
    snapshot = MarketSnapshot(
        timestamp=now + timedelta(hours=1),
        prices={"ETHUSDT": Decimal("100")},
        execution_prices={"ETHUSDT": Decimal("101")},
        klines={"ETHUSDT": []},
    )
    engine._record_decision(decision, snapshot)

    asyncio.run(engine._execute_decision(decision, snapshot))

    assert len(engine.account.trades) == 1
    assert engine.account.trades[0].amount <= Decimal("5000")
    assert engine.decision_log[-1]["action"] == "open_long"
    assert engine.decision_log[-1]["quantity"] < 50
    assert "risk_kernel_resized" in engine.decision_log[-1]["signals"]
    assert engine.decision_log[-1]["execution_result"]["status"] == "filled"
    assert engine.decision_log[-1]["execution_result"]["amount"] <= 5000


def test_progress_callback_timeout_defaults_to_three_minutes():
    t0 = datetime(2026, 1, 1)
    config = BacktestConfig(
        start_time=t0,
        end_time=t0 + timedelta(hours=1),
        initial_capital=Decimal("1000"),
        symbols=["ETHUSDT"],
        interval="1h",
    )

    assert config.progress_timeout_seconds == 180.0
    assert _get_runtime_tuning({})["progress_timeout_seconds"] == 180.0
