import asyncio
from types import SimpleNamespace

from app.v1.services import backtest_service
from backtest import backtest_runner
from models.inner_models.backtest_model import BacktestStatus


def test_stop_marks_task_cancelled(monkeypatch):
    recorded = {}
    row = SimpleNamespace(status=BacktestStatus.RUNNING)

    async def fake_get(_session, _backtest_id, _user_id):
        return row

    async def fake_update(**kwargs):
        recorded.update(kwargs)
        row.status = kwargs["status"]
        return row

    monkeypatch.setattr(backtest_service, "get_backtest_by_id_and_user", fake_get)
    monkeypatch.setattr(backtest_service, "update_backtest_status", fake_update)

    success, message = asyncio.run(
        backtest_service.BacktestService().stop(object(), "bt-1", "user-1")
    )

    assert success is True
    assert message == "回测已停止"
    assert recorded["status"] == BacktestStatus.CANCELLED


def test_registered_background_task_is_really_cancelled(monkeypatch):
    async def scenario():
        started = asyncio.Event()

        async def fake_run_backtest_task(backtest_id, db):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(backtest_runner, "run_backtest_task", fake_run_backtest_task)
        monkeypatch.setattr(backtest_runner, "_runner", None)
        backtest_runner._BACKGROUND_TASKS.clear()

        task = backtest_runner.start_backtest_task("bt-2", object())
        await started.wait()
        assert backtest_runner.cancel_backtest_task("bt-2") is True

        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0)

        assert task.cancelled()
        assert "bt-2" not in backtest_runner._BACKGROUND_TASKS

    asyncio.run(scenario())
