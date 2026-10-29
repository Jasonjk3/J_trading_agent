import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backtest.backtest_engine import BacktestConfig, BacktestEngine, KlineData, MarketSnapshot
from backtest.virtual_account import VirtualAccount
from trader.agent import TraderAgent
from trader.orchestrator import TraderOrchestrator
from trader.risk_kernel import HardRiskPolicy
from trader.schemas import ToolRequest, TraderState, TraderTurn
from trader.tool_gateway import TraderToolGateway


def _bar(ts, low="95", high="105", volume="100"):
    return KlineData(
        timestamp=ts,
        open=Decimal("100"), high=Decimal(high), low=Decimal(low),
        close=Decimal("100"), volume=Decimal(volume),
    )


def test_tool_gateway_filters_future_bars_and_rejects_unauthorized_symbol():
    now = datetime(2026, 1, 1, 12)
    snapshot = SimpleNamespace(
        timestamp=now,
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": [_bar(now - timedelta(hours=1)), _bar(now + timedelta(hours=1))]},
    )
    gateway = TraderToolGateway(
        snapshot=snapshot, account=VirtualAccount(Decimal("1000")), context={},
        as_of=now, authorized_symbols=["BTCUSDT"],
    )
    result = gateway.execute(ToolRequest(name="get_ohlcv", arguments={"symbol": "BTCUSDT"}))
    assert result.error is None
    assert len(result.data["bars"]) == 1
    denied = gateway.execute(ToolRequest(name="get_ohlcv", arguments={"symbol": "ETHUSDT"}))
    assert denied.error == "symbol 未授权"


def test_tool_gateway_compacts_ohlcv_decimals_and_hour_timestamp():
    now = datetime(2026, 10, 3, 12)
    bar = KlineData(
        timestamp=now,
        open=Decimal("2683.27000000"),
        high=Decimal("2687.09000000"),
        low=Decimal("2680.52000000"),
        close=Decimal("2680.77000000"),
        volume=Decimal("1452.75966100"),
    )
    snapshot = SimpleNamespace(
        timestamp=now,
        prices={"ETHUSDT": Decimal("2680.77000000")},
        klines={"ETHUSDT": [bar]},
    )
    gateway = TraderToolGateway(
        snapshot=snapshot,
        account=VirtualAccount(Decimal("1000.00000000")),
        context={},
        as_of=now,
        authorized_symbols=["ETHUSDT"],
    )

    result = gateway.execute(
        ToolRequest(name="get_ohlcv", arguments={"symbol": "ETHUSDT", "limit": 1})
    )
    market = gateway.execute(ToolRequest(name="get_market_snapshot", arguments={}))

    assert result.data["bars"] == [[
        "2026-10-03T12:00", "2683.27", "2687.09", "2680.52", "2680.77",
        "1452.759661",
    ]]
    assert market.data["prices"]["ETHUSDT"] == "2680.77"
    assert bar.open == Decimal("2683.27000000")


def test_agent_can_investigate_then_finish_without_preloaded_ohlcv():
    class FakeLLM:
        model_name = "tool-user"

        def __init__(self):
            self.calls = 0
            self.prompts = []

        def _call(self, prompt):
            self.calls += 1
            self.prompts.append(prompt)
            if self.calls == 1:
                return json.dumps({
                    "response_type": "investigate",
                    "tool_requests": [{"name": "get_ohlcv", "arguments": {"symbol": "BTCUSDT", "limit": 2}}],
                })
            return json.dumps({
                "schema_version": "trader-turn-v1",
                "response_type": "final",
                    "market_view": {
                        "summary": "insufficient edge", "regime": None,
                        "trend_state": "unclear",
                        "key_drivers": [], "counter_evidence": [], "uncertainties": [],
                },
                "plan_updates": [],
                "order_intents": [],
                "cancel_order_intents": [],
                "pending_order_actions": [],
                "no_trade_reason": "等待更多证据",
                "next_review": {
                    "at": None, "events": ["bar_closed"], "conditions": [],
                },
            })

    now = datetime(2026, 1, 1, 12)
    llm = FakeLLM()
    agent = TraderAgent(
        agent_id="tool-loop", llm=llm,
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
            "tradingStyle": "aggressive",
            "maxLeverage": 20,
        },
    )
    snapshot = SimpleNamespace(
        timestamp=now, prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": [_bar(now - timedelta(hours=1)), _bar(now)]},
    )
    decision = asyncio.run(agent.make_decision(snapshot, VirtualAccount(Decimal("1000"))))
    assert decision["action"] == "hold"
    assert llm.calls == 2
    assert "tool_results" in llm.prompts[1]
    assert '"hard_risk_policy"' in llm.prompts[1]
    assert '"min_leverage": 2.0' in llm.prompts[1]
    assert '"max_leverage": 20.0' in llm.prompts[1]
    assert '"account"' in llm.prompts[1]
    assert '"equity": 1000.0' in llm.prompts[1]
    assert '"balance": 1000.0' in llm.prompts[1]
    assert '"as_of": "2026-01-01 12:00:00"' in llm.prompts[1]
    assert decision["llm_metadata"]["tool_call_count"] == 1


def test_proposal_risk_checks_every_intent_and_commits_as_batch():
    now = datetime(2026, 1, 1)
    account = VirtualAccount(Decimal("1000"))
    snapshot = SimpleNamespace(timestamp=now, prices={"BTCUSDT": Decimal("100")})
    turn = TraderTurn.model_validate({
        "session_id": "s1", "as_of": now,
        "market_view": {"summary": "two entries"},
        "order_intents": [
            {"symbol": "BTCUSDT", "side": "buy", "effect": "open", "position_side": "long",
             "requested_leverage": 2,
             "size": {"mode": "quantity", "quantity": 0.5}, "protection": {"stop_loss_price": 95}},
            {"symbol": "BTCUSDT", "side": "sell", "effect": "open", "position_side": "short",
             "requested_leverage": 2,
             "size": {"mode": "quantity", "quantity": 0.4}, "protection": {"stop_loss_price": 105}},
        ],
        "next_review": {"events": ["bar_closed"]},
    })
    orchestrator = TraderOrchestrator("s1", execution_mode="live")
    policy = HardRiskPolicy(allowed_symbols=("BTCUSDT",), max_gross_exposure_pct=Decimal("100"), max_symbol_exposure_pct=Decimal("100"))
    proposal = orchestrator.propose_orders(turn, snapshot, account, policy)
    assert len(proposal.intents) == 2
    committed = proposal.model_copy(update={"commit_status": "committed", "committed_at": now})
    decision = orchestrator.to_execution_decision(turn, snapshot, account, policy, proposal=committed)
    assert len(decision["order_batch"]) == 2
    assert decision["proposal_id"] == proposal.proposal_id


def test_batch_proposal_cannot_bypass_aggregate_exposure_limit():
    now = datetime(2026, 1, 1)
    account = VirtualAccount(Decimal("1000"))
    snapshot = SimpleNamespace(timestamp=now, prices={"BTCUSDT": Decimal("100")})
    intents = [
        {"symbol": "BTCUSDT", "side": "buy", "effect": "open", "position_side": "long",
         "requested_leverage": 1,
         "size": {"mode": "quantity", "quantity": 2}, "protection": {"stop_loss_price": 99}}
        for _ in range(2)
    ]
    turn = TraderTurn.model_validate({
        "session_id": "batch-cap", "as_of": now, "market_view": {"summary": "scale in"},
        "order_intents": intents, "next_review": {"events": ["bar_closed"]},
    })
    policy = HardRiskPolicy(
        allowed_symbols=("BTCUSDT",), max_gross_exposure_pct=Decimal("30"),
        max_symbol_exposure_pct=Decimal("30"), max_risk_per_trade_pct=Decimal("100"),
        max_portfolio_risk_pct=Decimal("100"),
    )
    proposal = TraderOrchestrator("batch-cap", execution_mode="live").propose_orders(
        turn, snapshot, account, policy
    )
    approved_notional = sum(
        Decimal(str(item.approved_decision["quantity"])) * Decimal("100")
        for item in proposal.intents if item.approved_decision
    )
    assert approved_notional <= Decimal("300")
    assert proposal.intents[-1].status in {"resized", "rejected"}


def test_aggressive_strong_trend_requires_starter_and_pullback_pair():
    now = datetime(2026, 1, 1, 12)
    agent = TraderAgent(
        agent_id="aggressive-staged-entry",
        llm=object(),
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
            "tradingStyle": "aggressive",
            "maxLeverage": 5,
            "interval": "1h",
            "hardRiskPolicy": {"maxRiskPerTradePct": 1},
        },
    )
    payload = agent._final_output_template()
    payload.update({
        "market_view": {
            "summary": "BTC 放量突破并确认上行趋势",
            "regime": "trend",
            "trend_state": "strong_bullish",
            "key_drivers": ["一小时收盘突破"],
            "counter_evidence": ["短线已有涨幅"],
            "uncertainties": [],
        },
        "plan_updates": [],
        "cancel_order_intents": [],
        "pending_order_actions": [],
        "no_trade_reason": None,
        "next_review": {"at": None, "events": ["bar_closed"], "conditions": []},
    })
    base = {
        "symbol": "BTCUSDT", "side": "buy", "position_side": "long",
        "requested_leverage": 3,
        "protection": {"stop_loss_price": 95, "take_profit_price": 110},
        "rationale": "趋势确认后先建立轻仓，保留回撤加仓预算",
        "thesis": "突破后的短线趋势延续", "invalidation": "跌破九十五",
    }
    payload["order_intents"] = [{
        **base,
        "client_intent_id": "starter", "effect": "open", "order_type": "market",
        "execution_role": "standalone", "parent_intent_id": None,
        "limit_price": None,
        "size": {"mode": "risk_budget", "risk_pct_equity": 0.3,
                 "notional_usdt": None, "quantity": None},
        "expires_at": None,
    }]
    with pytest.raises(ValueError, match="trend_starter.*pullback_add"):
        agent._validate_final_response_contract(payload, now, [])

    payload["order_intents"] = [
        {
            **base,
            "client_intent_id": "starter", "effect": "open", "order_type": "market",
            "execution_role": "trend_starter", "parent_intent_id": None,
            "limit_price": None,
            "size": {"mode": "risk_budget", "risk_pct_equity": 0.3,
                     "notional_usdt": None, "quantity": None},
            "expires_at": None,
        },
        {
            **base,
            "client_intent_id": "pullback", "effect": "add", "order_type": "limit",
            "execution_role": "pullback_add", "parent_intent_id": "starter",
            "limit_price": 98,
            "size": {"mode": "risk_budget", "risk_pct_equity": 0.7,
                     "notional_usdt": None, "quantity": None},
            "rationale": "价格回踩突破位后补足计划仓位",
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        },
    ]
    agent._validate_final_response_contract(payload, now, [])
    runtime = agent._runtime_context_payload(
        TraderState(session_id="aggressive-staged-entry"),
        SimpleNamespace(timestamp=now, prices={"BTCUSDT": Decimal("100")}),
        VirtualAccount(Decimal("1000")),
    )
    assert runtime["execution_profile"]["aggressive_trend_entry"]["enabled"] is True
    assert runtime["execution_profile"]["aggressive_trend_entry"]["starter_risk_fraction"] == 0.35


def test_staged_same_direction_orders_share_one_trade_risk_budget():
    now = datetime(2026, 1, 1)
    account = VirtualAccount(Decimal("1000"))
    snapshot = SimpleNamespace(timestamp=now, prices={"BTCUSDT": Decimal("100")})
    turn = TraderTurn.model_validate({
        "session_id": "staged-risk", "as_of": now,
        "market_view": {"summary": "confirmed trend", "trend_state": "strong_bullish"},
        "order_intents": [
            {
                "client_intent_id": "starter", "symbol": "BTCUSDT", "side": "buy",
                "effect": "open", "position_side": "long", "order_type": "market",
                "execution_role": "trend_starter", "requested_leverage": 2,
                "size": {"mode": "risk_budget", "risk_pct_equity": 0.4},
                "protection": {"stop_loss_price": 99},
            },
            {
                "client_intent_id": "pullback", "symbol": "BTCUSDT", "side": "buy",
                "effect": "add", "position_side": "long", "order_type": "limit",
                "execution_role": "pullback_add", "parent_intent_id": "starter",
                "limit_price": 99.5, "requested_leverage": 2,
                "size": {"mode": "risk_budget", "risk_pct_equity": 0.4},
                "protection": {"stop_loss_price": 99},
            },
        ],
        "next_review": {"events": ["bar_closed"]},
    })
    policy = HardRiskPolicy(
        allowed_symbols=("BTCUSDT",), max_risk_per_trade_pct=Decimal("0.5"),
        max_portfolio_risk_pct=Decimal("10"), max_gross_exposure_pct=Decimal("100"),
        max_symbol_exposure_pct=Decimal("100"), max_order_notional=Decimal("10000"),
        max_order_margin=Decimal("10000"), max_margin_usage_pct=Decimal("100"),
    )
    proposal = TraderOrchestrator("staged-risk", execution_mode="live").propose_orders(
        turn, snapshot, account, policy
    )
    entry_prices = {"starter": Decimal("100"), "pullback": Decimal("99.5")}
    accepted_risk = sum(
        Decimal(str(item.approved_decision["quantity"]))
        * abs(entry_prices[item.client_intent_id] - Decimal("99"))
        for item in proposal.intents if item.approved_decision
    )
    assert accepted_risk <= Decimal("5")
    assert proposal.intents[-1].status == "resized"


def test_backtest_limit_order_is_replayable_and_partially_filled():
    now = datetime(2026, 1, 1)
    config = BacktestConfig(
        start_time=now, end_time=now + timedelta(hours=1), initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"], interval="1h", maker_fee=Decimal("0"), taker_fee=Decimal("0"),
        slippage=Decimal("0"), market_impact_bps=Decimal("0"), impact_volatility_weight=Decimal("0"),
        max_participation_rate=Decimal("1"),
        strategy_config={"maxDailyTrades": 50, "maxOrderAmount": 10000, "maxPositionRatio": 100,
                         "hardRiskPolicy": {"maxRiskPerTradePct": 100, "maxPortfolioRiskPct": 100,
                                            "maxGrossExposurePct": 100, "maxSymbolExposurePct": 100}},
    )
    engine = BacktestEngine(config)
    submit_snapshot = MarketSnapshot(
        timestamp=now, prices={"BTCUSDT": Decimal("100")}, klines={"BTCUSDT": []},
        execution_prices={"BTCUSDT": Decimal("100")}, current_bars={"BTCUSDT": _bar(now)},
    )
    decision = {"action": "open_long", "symbol": "BTCUSDT", "quantity": 2,
                "order_type": "limit", "limit_price": 100, "stop_loss_price": 90,
                "trade_plan": {"stop_loss_price": 90}, "client_intent_id": "i1",
                "decision_id": "submit-decision"}
    engine._record_decision(decision, submit_snapshot)
    asyncio.run(engine._submit_or_execute_order(decision, submit_snapshot))
    assert engine.order_events[-1]["eventType"] == "submitted"
    asyncio.run(engine._process_pending_orders(submit_snapshot))
    assert engine.order_events[-1]["eventType"] == "partially_filled"
    assert engine.pending_orders
    assert engine.order_events[-1]["remainingQuantity"] < 2
    assert len(engine.decision_log) == 2
    assert engine.decision_log[0]["id"] == "submit-decision"
    assert engine.decision_log[1]["id"] != "submit-decision"
    assert engine.decision_log[1]["execution_result"]["sourceDecisionId"] == "submit-decision"
    assert engine.decision_log[1]["execution_result"]["executionOrigin"] == "pending_order_fill"
    assert engine.decision_log[1]["execution_result"]["status"] == "filled"


def test_same_plan_limit_order_is_kept_and_new_plan_replaces_it():
    now = datetime(2026, 1, 1)
    config = BacktestConfig(
        start_time=now,
        end_time=now + timedelta(hours=1),
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
    )
    engine = BacktestEngine(config)
    snapshot = MarketSnapshot(
        timestamp=now,
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
        current_bars={"BTCUSDT": _bar(now)},
    )
    first = {
        "action": "open_long", "symbol": "BTCUSDT", "quantity": 1,
        "order_type": "limit", "limit_price": 96,
        "client_intent_id": "first", "thesis": "support rebound",
        "invalidation": "close below 94",
    }
    duplicate = {**first, "client_intent_id": "duplicate", "limit_price": 95}
    replacement = {
        **first,
        "client_intent_id": "replacement",
        "limit_price": 94,
        "thesis": "deeper support rebound",
        "invalidation": "close below 92",
    }

    asyncio.run(engine._submit_or_execute_order(first, snapshot))
    original_id = next(iter(engine.pending_orders))
    asyncio.run(engine._submit_or_execute_order(duplicate, snapshot))
    assert list(engine.pending_orders) == [original_id]
    assert duplicate["execution_result"]["status"] == "kept"

    asyncio.run(engine._submit_or_execute_order(replacement, snapshot))
    assert len(engine.pending_orders) == 1
    assert original_id not in engine.pending_orders
    assert any(
        item["orderId"] == original_id and item["eventType"] == "replaced"
        for item in engine.order_events
    )


def test_active_order_must_be_explicitly_managed_without_keep_and_resubmit():
    now = datetime(2026, 1, 1)
    agent = TraderAgent(
        agent_id="pending-order-contract",
        llm=object(),
        strategy_config={"symbols": ["BTCUSDT"], "decisionMode": "trader"},
    )
    active_orders = [{
        "order_id": "ord-1",
        "symbol": "BTCUSDT",
        "position_side": "long",
        "side": "buy",
        "order_type": "limit",
        "limit_price": 95,
        "remaining_quantity": "1",
        "status": "live",
    }]
    payload = agent._final_output_template()
    payload.update({
        "plan_updates": [],
        "order_intents": [],
        "cancel_order_intents": [],
        "pending_order_actions": [{
            "order_id": "ord-1",
            "symbol": "BTCUSDT",
            "action": "keep",
            "reason": "计划未发生变化",
            "replacement_client_intent_id": None,
        }],
        "no_trade_reason": "现有挂单仍然有效",
        "next_review": {"at": None, "events": ["order_updated"], "conditions": []},
    })
    agent._validate_final_response_contract(payload, now, active_orders)

    payload["order_intents"] = [{
        "client_intent_id": "duplicate-long",
        "symbol": "BTCUSDT",
        "side": "buy",
        "effect": "open",
        "position_side": "long",
        "requested_leverage": 2,
        "order_type": "limit",
        "execution_role": "standalone",
        "parent_intent_id": None,
        "limit_price": 94,
        "size": {
            "mode": "quantity", "risk_pct_equity": None,
            "notional_usdt": None, "quantity": 1,
        },
        "protection": {"stop_loss_price": 92, "take_profit_price": None},
        "rationale": "测试重复订单",
        "thesis": "same direction",
        "invalidation": "below 92",
        "expires_at": (now + timedelta(hours=1)).isoformat(),
    }]
    payload["no_trade_reason"] = None
    with pytest.raises(ValueError, match="不能再提交同标的同方向"):
        agent._validate_final_response_contract(payload, now, active_orders)

    payload["pending_order_actions"][0].update({
        "action": "replace",
        "reason": "价格位置已经变化",
        "replacement_client_intent_id": "duplicate-long",
    })
    agent._validate_final_response_contract(payload, now, active_orders)


def test_short_term_limit_order_gets_hard_expiry_and_expires_after_max_bars():
    now = datetime(2026, 1, 1)
    engine = BacktestEngine(BacktestConfig(
        start_time=now,
        end_time=now + timedelta(hours=3),
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
        strategy_config={"pendingOrderMaxBars": 2},
    ))
    submit_snapshot = MarketSnapshot(
        timestamp=now,
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
        current_bars={"BTCUSDT": _bar(now)},
    )
    decision = {
        "action": "open_long", "symbol": "BTCUSDT", "quantity": 1,
        "order_type": "limit", "limit_price": 90,
        "client_intent_id": "short-lived-limit",
    }

    asyncio.run(engine._submit_or_execute_order(decision, submit_snapshot))
    order = next(iter(engine.pending_orders.values()))
    assert order.expires_at == now + timedelta(hours=2)
    assert decision["execution_result"]["expiresAt"] == (now + timedelta(hours=2)).isoformat()

    review = engine.active_orders_snapshot(
        as_of=now + timedelta(hours=1),
        prices={"BTCUSDT": Decimal("100")},
    )[0]
    assert review["age_bars"] == 1
    assert review["distance_pct"] == pytest.approx(-10.0)

    expiry_snapshot = MarketSnapshot(
        timestamp=now + timedelta(hours=2),
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
        current_bars={"BTCUSDT": _bar(now + timedelta(hours=2))},
    )
    asyncio.run(engine._process_pending_orders(expiry_snapshot))
    assert not engine.pending_orders
    assert engine.order_events[-1]["eventType"] == "expired"


def test_pending_order_keep_is_rejected_when_stale_or_too_far_from_market():
    now = datetime(2026, 1, 1)
    agent = TraderAgent(
        agent_id="stale-pending-order",
        llm=object(),
        strategy_config={
            "symbols": ["BTCUSDT"],
            "decisionMode": "trader",
            "pendingOrderMaxBars": 6,
            "pendingOrderMaxDistancePct": 2,
        },
    )
    payload = agent._final_output_template()
    payload.update({
        "plan_updates": [],
        "order_intents": [],
        "cancel_order_intents": [],
        "pending_order_actions": [{
            "order_id": "ord-stale", "symbol": "BTCUSDT", "action": "keep",
            "reason": "继续等待计划价格", "replacement_client_intent_id": None,
        }],
        "no_trade_reason": "保留现有挂单",
        "next_review": {"at": None, "events": ["order_updated"], "conditions": []},
    })
    active = [{
        "order_id": "ord-stale", "symbol": "BTCUSDT", "position_side": "long",
        "age_bars": 3, "distance_pct": -4.5,
    }]
    with pytest.raises(ValueError, match="必须 replace 或 cancel"):
        agent._validate_final_response_contract(payload, now, active)

    active[0].update({"age_bars": 6, "distance_pct": -1})
    with pytest.raises(ValueError, match="达到短线挂单上限"):
        agent._validate_final_response_contract(payload, now, active)


def test_decision_reason_must_be_written_in_chinese_by_llm():
    with pytest.raises(ValueError, match="必须使用中文说明"):
        TraderAgent._require_chinese_reason("No valid entry", "no_trade_reason")
    TraderAgent._require_chinese_reason("暂时没有有效入场机会", "no_trade_reason")


def _parent_child_test_engine(now):
    return BacktestEngine(BacktestConfig(
        start_time=now,
        end_time=now + timedelta(hours=2),
        initial_capital=Decimal("1000"),
        symbols=["BTCUSDT"],
        interval="1h",
        maker_fee=Decimal("0"),
        taker_fee=Decimal("0"),
        slippage=Decimal("0"),
        strategy_config={
            "maxDailyTrades": 50,
            "maxOrderAmount": 10000,
            "maxPositionRatio": 100,
            "hardRiskPolicy": {
                "maxRiskPerTradePct": 100,
                "maxPortfolioRiskPct": 100,
                "maxGrossExposurePct": 100,
                "maxSymbolExposurePct": 100,
                "maxMarginUsagePct": 100,
            },
        },
    ))


def _parent_child_snapshot(now, *, low="95", high="105"):
    return MarketSnapshot(
        timestamp=now,
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
        execution_prices={"BTCUSDT": Decimal("100")},
        current_bars={"BTCUSDT": _bar(now, low=low, high=high)},
    )


def _starter_decision():
    return {
        "decision_id": "starter-decision",
        "client_intent_id": "starter-intent",
        "action": "open_long",
        "symbol": "BTCUSDT",
        "quantity": 1,
        "requested_leverage": 2,
        "order_type": "market",
        "execution_role": "trend_starter",
        "stop_loss_price": 90,
        "trade_plan": {"stop_loss_price": 90, "take_profit_price": 120},
    }


def _pullback_child_decision():
    return {
        "decision_id": "child-decision",
        "client_intent_id": "child-intent",
        "parent_intent_id": "starter-intent",
        "action": "add_long",
        "symbol": "BTCUSDT",
        "quantity": 1,
        "requested_leverage": 2,
        "order_type": "limit",
        "limit_price": 96,
        "execution_role": "pullback_add",
        "stop_loss_price": 90,
        "trade_plan": {
            "parent_intent_id": "starter-intent",
            "stop_loss_price": 90,
            "take_profit_price": 120,
        },
    }


def test_pullback_child_order_is_bound_and_cancelled_when_parent_is_closed():
    now = datetime(2026, 1, 1)
    engine = _parent_child_test_engine(now)
    snapshot = _parent_child_snapshot(now)

    starter = _starter_decision()
    asyncio.run(engine._execute_decision(starter, snapshot))
    position = engine.account.get_position("BTCUSDT")
    assert position.lifecycle_id
    assert position.entry_intent_id == "starter-intent"

    child = _pullback_child_decision()
    asyncio.run(engine._submit_or_execute_order(child, snapshot))
    order = next(iter(engine.pending_orders.values()))
    execution = child["execution_result"]
    assert execution["orderType"] == "limit"
    assert execution["limitPrice"] == 96
    assert execution["stopLossPrice"] == 90
    assert execution["takeProfitPrice"] == 120
    assert order.decision["parent_position_id"] == position.lifecycle_id
    active = engine.active_orders_snapshot(
        as_of=now, prices={"BTCUSDT": Decimal("100")}
    )[0]
    assert active["parent_intent_id"] == "starter-intent"
    assert active["parent_position_id"] == position.lifecycle_id
    live_order = engine._serialize_live_active_orders(now)[0]
    assert live_order["orderId"] == order.order_id
    assert live_order["limitPrice"] == 96
    assert live_order["quantity"] == 1
    assert live_order["remainingQuantity"] == 1
    assert live_order["stopLossPrice"] == 90
    assert live_order["takeProfitPrice"] == 120
    assert live_order["executionRole"] == "pullback_add"
    assert live_order["parentPositionId"] == position.lifecycle_id

    close = {
        "action": "close_long", "symbol": "BTCUSDT", "quantity": 1,
        "order_type": "market", "reason": "父仓手动平仓",
    }
    asyncio.run(engine._execute_decision(close, snapshot))

    assert engine.account.get_position("BTCUSDT") is None
    assert not engine.pending_orders
    assert engine.order_events[-1]["eventType"] == "cancelled"
    assert engine.order_events[-1]["reason"] == "parent_position_closed_by_order"
    assert engine.order_events[-1]["parentPositionId"] == position.lifecycle_id


def test_risk_close_cascades_to_child_order_without_waiting_for_next_llm_turn():
    now = datetime(2026, 1, 1)
    engine = _parent_child_test_engine(now)
    snapshot = _parent_child_snapshot(now)
    asyncio.run(engine._execute_decision(_starter_decision(), snapshot))
    asyncio.run(engine._submit_or_execute_order(_pullback_child_decision(), snapshot))
    assert engine.pending_orders

    stop_snapshot = _parent_child_snapshot(
        now + timedelta(hours=1), low="89", high="101"
    )
    asyncio.run(engine._run_risk_checks(stop_snapshot))

    assert engine.account.get_position("BTCUSDT") is None
    assert not engine.pending_orders
    assert engine.order_events[-1]["reason"] == (
        "parent_position_closed_by_risk_control"
    )


def test_pullback_child_without_live_parent_is_rejected():
    now = datetime(2026, 1, 1)
    engine = _parent_child_test_engine(now)
    snapshot = _parent_child_snapshot(now)
    child = _pullback_child_decision()

    asyncio.run(engine._submit_or_execute_order(child, snapshot))

    assert not engine.pending_orders
    assert child["execution_result"]["status"] == "rejected"
    assert "活动父仓" in child["execution_result"]["message"]


def test_plain_add_limit_order_cannot_bypass_parent_position_binding():
    now = datetime(2026, 1, 1)
    engine = _parent_child_test_engine(now)
    snapshot = _parent_child_snapshot(now)
    asyncio.run(engine._execute_decision(_starter_decision(), snapshot))
    position = engine.account.get_position("BTCUSDT")
    add = {
        "action": "add_long",
        "symbol": "BTCUSDT",
        "quantity": 1,
        "requested_leverage": 2,
        "order_type": "limit",
        "limit_price": 96,
        "execution_role": "standalone",
        "stop_loss_price": 90,
        "trade_plan": {"stop_loss_price": 90, "take_profit_price": 120},
    }

    asyncio.run(engine._submit_or_execute_order(add, snapshot))

    order = next(iter(engine.pending_orders.values()))
    assert order.decision["parent_position_id"] == position.lifecycle_id


def test_live_state_reconciliation_removes_active_plan_without_position_or_order():
    agent = TraderAgent(
        agent_id="state-reconcile",
        llm=object(),
        strategy_config={
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "decisionMode": "trader",
            "traderConfig": {"executionMode": "live"},
        },
    )
    previous = TraderState.model_validate({
        "session_id": agent.orchestrator.session_id,
        "revision": 4,
        "plans": {
            "BTCUSDT": {
                "symbol": "BTCUSDT", "status": "active", "thesis": "long",
            },
            "ETHUSDT": {
                "symbol": "ETHUSDT", "status": "watching", "thesis": "observe",
            },
        },
    })

    reconciled = agent._reconcile_previous_state(
        previous, VirtualAccount(Decimal("1000")), {"open_orders": []}
    )

    assert "BTCUSDT" not in reconciled.plans
    assert "ETHUSDT" in reconciled.plans
    assert reconciled.revision == 5
