import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from sqlalchemy import select, func

from app.v1.services.agent_conversation_service import conversation_tools, tools_for_user
from app.v1.services.analytics_service import AnalyticsService
from app.v1.services.position_service import PositionService
from app.v1.services.quant_query_service import QuantQueryService
from app.v1.services.quant_tool_common import drawdown_analysis, safe_value
from app.v1.services.query_contracts import QueryUnavailable, trading_sandbox_mode
from lib.okx.okx_api import ApiService
from lib.okx.okx_market_service import OkxMarketService
from models.inner_models.exchange_account_model import ExchangeCode, BindStatus
from test_conversation_runs import setup


def test_registry_has_only_reviewed_queries_and_role_scoped_monitor_tools():
    tools = {tool.name: tool for tool in conversation_tools("owner", object())}
    admin = {tool.name for tool in conversation_tools("owner", object(), is_admin=True)}
    assert len(tools) == 48 and len(admin) == 50
    assert admin - set(tools) == {"monitor_tasks", "monitor_events"}
    assert all(tool.side_effect == "none" and tool.parameters["additionalProperties"] is False for tool in tools.values())
    assert all(not {"user_id", "tenant_id", "is_admin", "api_key", "url", "sql"} & set(tool.parameters["properties"]) for tool in tools.values())
    assert not {"place_order", "cancel_order", "execute_trade", "trigger_manual_decision", "create_backtest"} & set(tools)
    assert len(conversation_tools("owner", object(), include_quant=False)) == 4


def test_rankings_compare_quote_not_base_volume_and_use_real_datetime():
    rows = [
        {"instId": "BTC-USDT", "last": "100", "open24h": "80", "vol24h": "1", "volCcy24h": "100"},
        {"instId": "DOGE-USDT", "last": "1", "open24h": "2", "vol24h": "20", "volCcy24h": "20"},
        {"instId": "BTC-USDC", "last": "100", "open24h": "1", "volCcy24h": "9999"},
    ]
    assert OkxMarketService.rank_tickers(rows, "volume")[0]["instId"] == "BTC-USDT"
    assert OkxMarketService.rank_tickers(rows, "losers")[0]["instId"] == "DOGE-USDT"
    assert "change_pct" not in rows[0]
    async def scenario():
        service = OkxMarketService()
        service.get_tickers = AsyncMock(return_value=rows)
        answer = await service.get_market_summary()
        assert datetime.fromisoformat(answer["timestamp"]).tzinfo is not None
        service.get_tickers.assert_awaited_once_with(inst_type="SPOT")
    asyncio.run(scenario())


def test_stored_reports_news_and_agent_queries_are_owner_scoped_and_readonly(tmp_path, monkeypatch):
    from sqlalchemy import MetaData, update
    from models.inner_models.technical_analysis_record_model import TechnicalAnalysisRecordModel as Report
    from models.inner_models.news_intelligence_model import NewsIntelligenceAgentModel as News, NewsIntelligenceItemModel as Item
    from models.inner_models.trading_agent_model import TradingAgentModel as Agent, AgentProfitRecordModel, AgentOperationModel
    from models.inner_models.trader_state_model import TraderStateModel, TraderTurnModel, TraderEventModel
    from models.inner_models.user_model import UserModel, UserRole
    from models.inner_models.data_monitor_model import MonitorEventModel, MonitorTaskModel, MonitorRuleModel, MonitorTemplateModel
    from models.inner_models.message_push_model import MessagePushConfigModel
    from app.v1.services.technical_analysis_service import TechnicalAnalysisService
    from app.v1.services.news_intelligence_service import NewsIntelligenceService
    from app.v1.services.trading_agent_service import TradingAgentService
    import app.v1.services.trading_analysis_context_service as context_service
    monkeypatch.setattr(TechnicalAnalysisService, "analyze", AsyncMock(side_effect=AssertionError("query must not regenerate")))
    monkeypatch.setattr(NewsIntelligenceService, "collect_now", AsyncMock(side_effect=AssertionError("query must not collect")))
    monkeypatch.setattr(NewsIntelligenceService, "_llm_name", AsyncMock(return_value="test model"))
    monkeypatch.setattr(TradingAgentService, "get_live_status", lambda *_: None)
    monkeypatch.setattr(context_service, "TECHNICAL_ANALYSIS_LLM_ENABLED", True)
    generator = AsyncMock(side_effect=AssertionError("readonly context must not call model"))
    monkeypatch.setattr(context_service, "_generate_missing_technical_analyses", generator)
    async def scenario():
        db, _ = await setup(tmp_path / "domains.sqlite3")
        try:
            metadata = MetaData()
            for model in [Report, News, Item, Agent, AgentProfitRecordModel, AgentOperationModel, TraderStateModel, TraderTurnModel, TraderEventModel, MonitorEventModel, MonitorTaskModel, MonitorRuleModel, MonitorTemplateModel, MessagePushConfigModel]:
                table = model.__table__.to_metadata(metadata)
                for index in table.indexes: index.name = table.name + "_" + index.name
            async with db.engine.begin() as conn: await conn.run_sync(metadata.create_all)
            now = datetime.now()
            async with db.get_session() as session:
                for suffix, owner in [("mine", "owner"), ("victim", "other")]:
                    session.add(Report(id=suffix, user_id=owner, symbol="BTC-USDT", timeframe="1h", result_payload={"summary": suffix, "api_key": "must-not-leak"}))
                    session.add(News(id=suffix, user_id=owner, name=suffix, llm_model_id=1))
                    session.add(Item(id=suffix, agent_id=suffix, title=suffix, summary="stored article", ingested_at=now, sort_time=now))
                    session.add(Agent(id=suffix, user_id=owner, name=suffix, strategy_config={"symbols": ["BTCUSDT"], "useNewsAnalysis": False}))
                    session.add(MonitorEventModel(id=suffix, task_id=suffix, user_id=owner, event_type="trigger", value=1, success=True))
            async with db.get_session() as session:
                query = QuantQueryService("owner", session)
                assert len((await query.list_technical_reports())["items"]) == 1
                assert "must-not-leak" not in json.dumps(await query.technical_report_detail("mine"))
                assert len((await query.list_news_sources())["items"]) == 1
                article = (await query.query_news_timeline("mine"))["items"][0]
                assert article["title"] == "mine" and article["source_verified"] is False
                assert len((await query.list_trading_agents())["items"]) == 1
                assert (await query.trading_agent_status("mine"))["scheduler"] is None
                assert (await query.trading_agent_strategy("mine"))["strategy"]["symbols"] == ["BTCUSDT"]
                assert (await query.trading_agent_performance("mine"))["points"] == []
                assert (await query.trading_agent_diagnosis("mine"))["findings"]
                assert await query.trading_agent_research_context("mine")
                generator.assert_not_awaited()
                for method in [query.technical_report_detail, query.query_news_timeline, query.trading_agent_status, query.trading_agent_strategy, query.trading_agent_diagnosis]:
                    with pytest.raises(ValueError): await method("victim")
                await session.execute(update(UserModel).where(UserModel.id == "owner").values(role=UserRole.ADMIN))
                names = {tool.name for tool in await tools_for_user("owner", session)}
                assert {"monitor_events", "monitor_tasks"} <= names
                assert len((await query.monitor_events())["items"]) == 1
                assert (await query.monitor_tasks())["items"] == []
                assert (await session.execute(select(func.count()).select_from(Report))).scalar_one() == 2
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


@pytest.mark.parametrize("legacy", [True, False])
def test_run_toolset_version_keeps_old_jobs_replayable(tmp_path, monkeypatch, legacy):
    from sqlalchemy import update
    from models.inner_models.conversation_run_model import ConversationRunModel
    from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
    from app.v1.schemas.chat_schema import ChatRequest
    from core.agent_runtime.provider import ExistingLLMProvider
    from core.agent_runtime.llm_contracts import LLMResponse, LLMUsage
    seen = []
    async def complete(self, messages, **kwargs):
        seen.append({tool.name for tool in kwargs["tools"]})
        return LLMResponse("完成", "test", usage=LLMUsage(10, 10, 20))
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        db, service = await setup(tmp_path / "version.sqlite3")
        try:
            row, _ = await service.submit("owner", ChatRequest(message="hello"), IntelligentAssistantAgent())
            if legacy:
                async with db.get_session() as session:
                    payload = {k: v for k, v in row.payload.items() if k != "toolset_version"}
                    await session.execute(update(ConversationRunModel).where(ConversationRunModel.id == row.id).values(payload=payload))
            assert await service.run_once()
            assert (await service.repository.get(row.id, "owner")).status == "succeeded"
            assert ("market_quote" in seen[0]) is not legacy
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


@pytest.mark.parametrize("mode,expected", [("False", False), ("true", True), ("0", False), ("1", True)])
def test_exchange_environment_uses_server_setting(monkeypatch, mode, expected):
    from app.v1.services.manual_trading_service import ManualTradingService
    monkeypatch.setenv("TRADING_SANDBOX_MODE", mode)
    assert trading_sandbox_mode() is expected
    service = ManualTradingService()
    service._exchange_account_service.decrypt = lambda value: value
    client = service._build_okx_client(SimpleNamespace(api_key="test", api_secret="test", passphrase="test"))
    assert client.is_sandbox is expected
    monkeypatch.setenv("TRADING_SANDBOX_MODE", "invalid")
    with pytest.raises(ValueError): trading_sandbox_mode()


def test_account_analytics_never_fabricates_roi_or_combines_different_currencies(monkeypatch):
    from app.v1.services import analytics_queries
    accounts = [SimpleNamespace(id="account-1", exchange=ExchangeCode.OKX)]
    monkeypatch.setattr(analytics_queries, "get_exchange_accounts", AsyncMock(return_value=accounts))
    async def scenario():
        service = AnalyticsService()
        service._fetch_positions_history = AsyncMock(return_value=[
            {"symbol": "BTC-USDT-SWAP", "currency": "USDT", "pnl": "100", "fee": "-2", "fundingFee": "-1", "realizedPnl": "97"},
            {"symbol": "ETH-USDT-SWAP", "currency": "USDT", "pnl": "10", "fee": "1", "fundingFee": "0"},
        ])
        result = await service.get_profit_summary(object(), "owner")
        assert result["returnRate"] is None and result["netProfit"] == "108" and result["totalFee"] == "1"
        assert not result["complete"] and result["currency"] == "USDT"
        service._fetch_positions_history.return_value.append({"currency": "BTC", "pnl": "1", "fee": "0"})
        result = await service.get_profit_summary(object(), "owner")
        assert result["netProfit"] is None and len(result["byCurrency"]) == 2
        service._fetch_positions_history.side_effect = RuntimeError("sensitive exchange body")
        with pytest.raises(QueryUnavailable): await service.get_profit_summary(object(), "owner")
    asyncio.run(scenario())


def test_positions_distinguish_partial_failure_all_failure_and_true_empty(monkeypatch):
    from app.v1.services import position_service
    accounts = [SimpleNamespace(id="a", exchange=ExchangeCode.OKX), SimpleNamespace(id="b", exchange=ExchangeCode.OKX)]
    monkeypatch.setattr(position_service, "get_exchange_accounts", AsyncMock(return_value=accounts))
    async def scenario():
        service = PositionService()
        service._fetch_positions_from_exchange = AsyncMock(side_effect=[[], RuntimeError("private")])
        positions, count, summary = await service.get_positions(object(), "owner")
        assert positions == [] and count == 0 and summary["complete"] is False
        assert summary["accountsSucceeded"] == 1 and summary["failedAccountIds"] == ["b"]
        service._fetch_positions_from_exchange.side_effect = RuntimeError("private")
        with pytest.raises(QueryUnavailable): await service.get_positions(object(), "owner")
        service._fetch_positions_from_exchange.side_effect = None
        service._fetch_positions_from_exchange.return_value = []
        assert (await service.get_positions(object(), "owner"))[2]["complete"] is True
    asyncio.run(scenario())


def test_public_market_and_account_queries_use_real_sdk_signatures(monkeypatch):
    sdk = create_autospec(ApiService, instance=True)
    sdk.get_ticker.return_value = {"instId": "ETH-USDT", "last": "100", "ts": "1700000000000"}
    sdk.get_order_books.return_value = {"bids": [["99", "1"]], "asks": [["101", "1"]], "ts": "1700000000000"}
    sdk.get_trades.return_value = [{"px": "100", "ts": "1700000000000"}]
    sdk.get_account_balance.return_value = [{"totalEq": "1000", "uTime": "1700000000000", "details": []}]
    sdk.get_account_positions.return_value = [{"instId": "ETH-USDT-SWAP", "instType": "SWAP", "posSide": "short", "pos": "2", "notionalUsd": "200"}]
    sdk.get_orders_pending.return_value = []
    sdk.get_algo_orders_pending.return_value = []
    sdk.get_positions_history.return_value = []
    market = OkxMarketService()
    market.api = sdk
    query = QuantQueryService("owner", object())
    monkeypatch.setattr(query, "market", lambda: market)
    monkeypatch.setattr(query, "client", AsyncMock(return_value=sdk))
    async def scenario():
        assert (await query.market_quote("ETH-USDT"))["market_time"]
        assert (await query.market_orderbook("ETH-USDT"))["bids"]
        assert (await query.market_recent_trades("ETH-USDT"))["items"]
        assert (await query.account_overview("mine"))["equityUsd"] == "1000"
        assert (await query.list_positions("mine"))["total"] == 1
        assert (await query.list_pending_orders("mine"))["items"] == []
        assert (await query.list_protection_orders("mine"))["items"] == []
        assert (await query.position_history("mine"))["complete"] is False
        risk = await query.portfolio_risk_summary("mine")
        assert risk["grossNotionalUsd"] == "200" and risk["netNotionalUsd"] == "-200"
        assert risk["grossExposureToEquity"] == "0.2" and risk["stopLossCoverage"] is None
        sdk.get_account_positions.return_value[0].pop("notionalUsd")
        risk = await query.portfolio_risk_summary("mine")
        assert risk["complete"] is False and risk["grossNotionalUsd"] is None
    asyncio.run(scenario())


def test_private_tool_cannot_select_another_users_exchange_account(monkeypatch):
    from app.v1.crud import exchange_account_crud
    from app.v1.services.manual_trading_service import ManualTradingService
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr("app.v1.services.manual_trading_service.get_exchange_account_by_id_and_user", lookup)
    build = lambda *args: pytest.fail("must not construct exchange client for inaccessible account")
    monkeypatch.setattr(ManualTradingService, "_build_okx_client", build)
    async def scenario():
        with pytest.raises(ValueError): await QuantQueryService("owner", object()).list_positions("victim")
        assert lookup.call_args.args[1:] == ("victim", "owner")
    asyncio.run(scenario())


def test_drawdown_is_from_entire_curve_and_preserves_recovery():
    points = [{"timestamp": str(i), "equity": value} for i, value in enumerate([100, 120, 60, 100, 120, 150, 140])]
    analysis = drawdown_analysis(points)
    assert Decimal(analysis["maxDrawdownPercent"]) == 50
    assert (analysis["peakAt"], analysis["troughAt"], analysis["recoveredAt"]) == ("1", "2", "4")
    assert "api_key" not in safe_value({"api_key": "secret", "nested": {"chainOfThought": ["private"], "equity": Decimal("10")}})
    assert "private" not in json.dumps(safe_value({"nested": {"chainOfThought": ["private"]}}))


def test_existing_global_llm_monitor_requires_admin(tmp_path, monkeypatch):
    from fastapi import FastAPI
    import httpx
    from app.v1.api.llm_monitor_api import router
    from app.public.dependencies.auth import get_current_user
    from app.v1.services.llm_monitor_service import LLMMonitorService
    from models.inner_models.user_model import UserRole
    monkeypatch.setattr(LLMMonitorService, "get_realtime_usage", AsyncMock(return_value=SimpleNamespace(model_dump=lambda **kwargs: {"safe": True})))
    async def scenario():
        db, _ = await setup(tmp_path / "monitor.sqlite3")
        try:
            app = FastAPI(); app.state.db = db; app.include_router(router, prefix="/v1")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                assert (await client.get("/v1/monitor/usage/realtime")).status_code == 401
                async def user(): return SimpleNamespace(id="owner", role=UserRole.USER)
                app.dependency_overrides[get_current_user] = user
                assert (await client.get("/v1/monitor/usage/realtime")).status_code == 403
                async def admin(): return SimpleNamespace(id="owner", role=UserRole.ADMIN)
                app.dependency_overrides[get_current_user] = admin
                assert (await client.get("/v1/monitor/usage/realtime")).json()["data"] == {"safe": True}
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_durable_run_executes_new_account_tool_with_fresh_owner_scoped_session(tmp_path, monkeypatch):
    from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
    from app.v1.services.manual_trading_service import ManualTradingService
    from app.v1.schemas.chat_schema import ChatRequest
    from core.agent_runtime.llm_contracts import LLMResponse, LLMUsage, ToolCall
    from core.agent_runtime.provider import ExistingLLMProvider
    from models.inner_models.exchange_account_model import ExchangeAccountModel
    client = create_autospec(ApiService, instance=True)
    client.get_account_positions.return_value = [{"instId": "BTC-USDT-SWAP", "instType": "SWAP", "pos": "1", "posSide": "long", "notionalUsd": "100"}]
    build = lambda *_: client
    monkeypatch.setattr(ManualTradingService, "_build_okx_client", build)
    responses = [LLMResponse("", "test", usage=LLMUsage(10, 10, 20), tool_calls=(ToolCall("positions", "list_positions", {"account_id": "mine"}),)), LLMResponse("查询成功", "test", usage=LLMUsage(10, 10, 20))]
    async def complete(*args, **kwargs): return responses.pop(0)
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        db, service = await setup(tmp_path / "native-account.sqlite3")
        try:
            async with db.engine.begin() as conn: await conn.run_sync(lambda c: ExchangeAccountModel.__table__.create(c))
            async with db.get_session() as session:
                session.add(ExchangeAccountModel(id="mine", user_id="owner", exchange=ExchangeCode.OKX, api_key="unused", api_secret="unused", passphrase="unused", bind_status=BindStatus.SUCCESS, enabled=True))
            row, _ = await service.submit("owner", ChatRequest(message="查询我的持仓"), IntelligentAssistantAgent())
            assert await service.run_once()
            final = await service.repository.get(row.id, "owner")
            assert final.status == "succeeded"
            audit = final.result["runtime"]["tool_audit"]
            assert audit[0]["tool"] == "list_positions" and audit[0]["status"] == "succeeded"
            assert audit[0]["output"]["items"][0]["instId"] == "BTC-USDT-SWAP"
            assert "unused" not in json.dumps(audit)
            client.get_account_positions.assert_awaited_once()
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_database_queries_owner_isolation_no_implicit_paper_creation_and_cost_scope(tmp_path):
    from models.inner_models.backtest_model import BacktestTaskModel as Backtest, BacktestTradeModel as Trade, BacktestEquityModel as Equity, BacktestStatus, KlineInterval
    from models.inner_models.paper_trading_model import PaperTradingAccountModel, PaperPositionModel, PaperTradeModel, PaperDecisionModel, PaperEquityRecordModel
    from models.inner_models.llm_monitor_model import LLMUsageLog
    from app.v1.services.paper_trading_service import PaperTradingService
    async def scenario():
        db, _ = await setup(tmp_path / "quant.sqlite3")
        try:
            async with db.engine.begin() as conn:
                from sqlalchemy import MetaData
                metadata = MetaData()
                for model in [Backtest, Trade, Equity, PaperTradingAccountModel, PaperPositionModel, PaperTradeModel, PaperDecisionModel, PaperEquityRecordModel, LLMUsageLog]:
                    table = model.__table__.to_metadata(metadata)
                    for index in table.indexes:
                        index.name = table.name + "_" + index.name  # SQLite indexes use a database-wide namespace.
                await conn.run_sync(metadata.create_all)
            start = datetime.now() - timedelta(days=2)
            async with db.get_session() as session:
                for ident, owner in [("mine", "owner"), ("victim", "other")]:
                    session.add(Backtest(id=ident, user_id=owner, name=ident, status=BacktestStatus.COMPLETED, agent_id="agent", strategy_type="rule", exchange="okx", symbols=["BTCUSDT"], interval=KlineInterval("1h"), start_time=start, end_time=start+timedelta(days=1), initial_capital=100, strategy_config={}, result_statistics={"totalReturn": 20}))
                for i, pnl in enumerate([2, -5, 10]):
                    session.add(Trade(id=str(i), backtest_id="mine", timestamp=start+timedelta(minutes=i), symbol="BTCUSDT", side="sell", trade_type="close", price=10, quantity=1, amount=10, balance=100, pnl=pnl))
                for i, equity in enumerate([100, 120, 60, 120]):
                    session.add(Equity(id=str(i), backtest_id="mine", timestamp=start+timedelta(minutes=i), equity=equity))
                for i, owner in enumerate(["owner", "other", None], 1):
                    session.add(LLMUsageLog(id=i, request_id=str(i), model_name="test", model_provider="test", total_tokens=i*10, user_id=owner, cost_usd=Decimal("0.1")))
            async with db.get_session() as session:
                query = QuantQueryService("owner", session)
                assert (await query.backtest_trades("mine", limit=1, order="largest_loss"))["items"][0]["pnl"] == "-5.00000000"
                assert Decimal((await query.backtest_drawdown_analysis("mine"))["maxDrawdownPercent"]) == 50
                with pytest.raises(ValueError): await query.backtest_detail("victim")
                assert (await query.llm_usage_summary())["total_tokens"] == 10
                assert (await query.paper_accounts_summary())["accounts"] == []
                assert (await session.execute(select(func.count()).select_from(PaperTradingAccountModel))).scalar_one() == 0
                names = {tool.name for tool in await tools_for_user("owner", session)}
                assert "monitor_tasks" not in names
                with pytest.raises(PermissionError): await query.monitor_tasks()
                paper = PaperTradingService()
                created = await paper.initialize_human_account(session, "owner")
                again = await paper.initialize_human_account(session, "owner")
                assert again.id == created.id
                assert (await session.execute(select(func.count()).select_from(PaperTradingAccountModel))).scalar_one() == 1
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())
