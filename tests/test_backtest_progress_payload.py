import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.v1.services.backtest_service import BacktestService
from backtest.backtest_engine import BacktestConfig, BacktestEngine, MarketSnapshot
from models.inner_models.backtest_model import BacktestStatus


def _engine() -> BacktestEngine:
    start = datetime(2026, 1, 1)
    return BacktestEngine(
        BacktestConfig(
            start_time=start,
            end_time=start + timedelta(hours=1),
            initial_capital=Decimal("1000"),
            symbols=["BTCUSDT"],
            interval="1h",
        )
    )


def test_live_progress_contains_decision_summary_only():
    engine = _engine()
    engine.decision_log = [{
        "id": "decision-1",
        "timestamp": "2026-01-01T00:00:00",
        "action": "hold",
        "symbol": "BTCUSDT",
        "reasoning": "等待确认",
        "decision_analysis": "等待确认",
        "decision_prompt": "very large prompt",
        "llm_raw_response": "very large response",
        "parsed_decision": "{}",
        "llm_metadata": {"tokens": 1000},
        "technical_analysis": "large technical analysis",
        "chain_of_thought": [{"type": "llm_audit"}],
        "rule_hits": [{"rule_id": "r1"}],
        "indicators_snapshot": {"rsi": 50},
        "execution_result": {"status": "no_action"},
    }]

    row = engine._serialize_live_decision_log()["decisionLog"][0]

    assert row["id"] == "decision-1"
    assert row["reasoning"] == "等待确认"
    assert "decisionPrompt" not in row
    assert "llmRawResponse" not in row
    assert "parsedDecision" not in row
    assert "llmMetadata" not in row
    assert "technicalAnalysis" not in row
    assert "chainOfThought" not in row
    assert "ruleHits" not in row
    assert "indicatorsSnapshot" not in row


def test_recorded_decision_gets_stable_id():
    engine = _engine()
    snapshot = MarketSnapshot(
        timestamp=datetime(2026, 1, 1),
        prices={"BTCUSDT": Decimal("100")},
        klines={"BTCUSDT": []},
    )

    engine._record_decision({"action": "hold", "reason": "wait"}, snapshot)

    assert engine.decision_log[0]["id"]


def test_automatic_risk_trade_gets_its_own_execution_decision():
    engine = _engine()
    snapshot = MarketSnapshot(
        timestamp=datetime(2026, 1, 1, 1),
        prices={"BTCUSDT": Decimal("99")},
        klines={"BTCUSDT": []},
    )
    trade = SimpleNamespace(
        id="trade-1",
        symbol="BTCUSDT",
        side="sell",
        trade_type="close",
        quantity=Decimal("1"),
        price=Decimal("99"),
        amount=Decimal("99"),
        fee=Decimal("0.1"),
        pnl=Decimal("-1.1"),
        pnl_percent=Decimal("-1.1"),
        balance=Decimal("998.9"),
        signals=["risk_control"],
        action=None,
    )

    engine._record_automatic_trade_decision(
        trade=trade,
        action="close_long",
        snapshot=snapshot,
        reason="止损触发",
        execution_origin="risk_control",
    )

    row = engine.decision_log[-1]
    assert trade.action == "close_long"
    assert row["action"] == "close_long"
    assert row["execution_result"]["tradeId"] == "trade-1"
    assert row["execution_result"]["executionOrigin"] == "risk_control"


def test_progress_service_strips_legacy_full_decision_payload(monkeypatch):
    async def fake_progress_row(*_args, **_kwargs):
        return {
            "status": BacktestStatus.RUNNING,
            "progress": 12,
            "error_message": None,
            "progress_snapshot": {
                "currentTime": "2026-01-01T00:00:00",
                "livePreview": {
                    "decisionLog": [{
                        "id": "decision-1",
                        "timestamp": "2026-01-01T00:00:00",
                        "action": "hold",
                        "reasoning": "wait",
                        "decisionPrompt": "legacy large prompt",
                        "llmRawResponse": "legacy large response",
                    }],
                },
            },
        }

    monkeypatch.setattr(
        "app.v1.services.backtest_service.get_backtest_progress_by_id_and_user",
        fake_progress_row,
    )
    result = asyncio.run(
        BacktestService().get_progress(
            session=SimpleNamespace(),
            backtest_id="backtest-1",
            user_id="user-1",
        )
    )

    decision = result["livePreview"]["decisionLog"][0]
    assert decision["id"] == "decision-1"
    assert "decisionPrompt" not in decision
    assert "llmRawResponse" not in decision


def test_decision_summary_excludes_full_audit_payload():
    row = SimpleNamespace(
        id="decision-1",
        timestamp=datetime(2026, 1, 1),
        action="hold",
        symbol="BTCUSDT",
        quantity=None,
        reasoning="等待确认",
        decision_analysis="趋势尚未确认",
        reference_price=Decimal("100"),
        execution_result={"status": "no_action"},
        chain_of_thought=[{"decisionPrompt": "large prompt"}],
        technical_analysis="large analysis",
    )

    payload = BacktestService.decision_summary_to_response(row)

    assert payload["id"] == "decision-1"
    assert payload["decisionAnalysis"] == "趋势尚未确认"
    assert "chainOfThought" not in payload
    assert "decisionPrompt" not in payload
    assert "llmRawResponse" not in payload
    assert "technicalAnalysis" not in payload
