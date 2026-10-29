from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.v1.services.backtest_service import BacktestService
from models.inner_models.backtest_model import BacktestStatus, KlineInterval


def test_failed_backtest_keeps_live_preview_history():
    now = datetime(2026, 10, 8, 10, 31)
    preview = {
        "equity": 9800.0,
        "equityCurve": [{"time": now.isoformat(), "value": 9800.0}],
        "drawdownCurve": [{"time": now.isoformat(), "value": 2.0}],
        "decisionLog": [
            {
                "timestamp": now.isoformat(),
                "action": "hold",
                "symbol": "BTCUSDT",
                "reasoning": "risk limit reached",
            }
        ],
        "trades": [
            {
                "id": "trade-1",
                "timestamp": now.isoformat(),
                "symbol": "BTCUSDT",
                "side": "buy",
                "type": "open",
                "price": 60000.0,
                "quantity": 0.01,
                "amount": 600.0,
                "fee": 0.6,
                "pnl": 0.0,
                "pnlPercent": 0.0,
                "balance": 9399.4,
            }
        ],
    }
    backtest = SimpleNamespace(
        id="backtest-1",
        name="failed backtest",
        status=BacktestStatus.FAILED,
        progress=42,
        progress_snapshot={
            "progress": 42,
            "currentTime": now.isoformat(),
            "livePreview": preview,
        },
        agent_id="agent-1",
        agent_name="agent",
        strategy_config={},
        start_time=now,
        end_time=now,
        initial_capital=Decimal("10000"),
        exchange="okx",
        symbols=["BTCUSDT"],
        interval=KlineInterval.M15,
        maker_fee=Decimal("0.1"),
        taker_fee=Decimal("0.1"),
        slippage=Decimal("0.05"),
        result_statistics=None,
        error_message="user stopped",
        created_at=now,
        started_at=now,
        completed_at=now,
    )

    response = BacktestService().model_to_detail_response(backtest, [], [], [])

    assert response["status"] == "failed"
    assert response["runningProgress"] == backtest.progress_snapshot
    assert response["result"] is not None
    assert response["result"]["trades"] == preview["trades"]
    assert response["result"]["decisionLog"] == preview["decisionLog"]
    assert response["result"]["equityCurve"] == preview["equityCurve"]
    assert response["result"]["statistics"]["totalReturn"] == -2.0


def test_detail_response_can_use_compact_snapshot_without_legacy_decisions():
    now = datetime(2026, 10, 8, 10, 31)
    backtest = SimpleNamespace(
        id="backtest-1",
        name="running backtest",
        status=BacktestStatus.RUNNING,
        progress=42,
        progress_snapshot={
            "currentTime": now.isoformat(),
            "livePreview": {
                "decisionLog": [{"decisionPrompt": "very large legacy prompt"}],
            },
        },
        agent_id="agent-1",
        agent_name="agent",
        strategy_config={},
        start_time=now,
        end_time=now,
        initial_capital=Decimal("10000"),
        exchange="okx",
        symbols=["BTCUSDT"],
        interval=KlineInterval.M15,
        maker_fee=Decimal("0.1"),
        taker_fee=Decimal("0.1"),
        slippage=Decimal("0.05"),
        result_statistics=None,
        error_message=None,
        created_at=now,
        started_at=now,
        completed_at=None,
    )
    compact = {
        "currentTime": now.isoformat(),
        "currentStep": 4,
        "totalSteps": 10,
        "livePreview": {"decisionLogTotal": 4, "equityCurve": []},
    }

    response = BacktestService().model_to_detail_response(
        backtest,
        [],
        [],
        [],
        progress_snapshot_override=compact,
    )

    assert response["runningProgress"] == compact
    assert "decisionLog" not in response["runningProgress"]["livePreview"]
