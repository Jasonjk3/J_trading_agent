"""模拟盘公开契约的轻量回归测试。"""
import pytest
from pydantic import ValidationError

from app.v1.api.paper_trading_api import router
from app.v1.schemas.paper_trading_schema import CreatePaperAccountRequest, CreatePaperTradeRequest
from app.v1.services.paper_trading_scheduler import PaperTradingScheduler
from models.inner_models.paper_trading_model import (
    PaperAccountStatus,
    PaperTradeSide,
    PaperTradingAccountModel,
)


def test_paper_trading_routes_are_registered():
    paths = {route.path for route in router.routes}
    assert "/paper-trading/dashboard" in paths
    assert "/paper-trading/accounts" in paths
    assert "/paper-trading/accounts/{account_id}/trades" in paths
    assert "/paper-trading/accounts/{account_id}/decisions" in paths


def test_trade_request_rejects_non_positive_values():
    with pytest.raises(ValidationError):
        CreatePaperTradeRequest(symbol="BTC/USDT", side="buy", amount=0, price=100)
    with pytest.raises(ValidationError):
        CreatePaperTradeRequest(symbol="BTC/USDT", side="buy", amount=100, price=0)


def test_account_request_and_enums_match_public_contract():
    request = CreatePaperAccountRequest(agentId="agent-1", initialCapital=200000)
    assert request.agentId == "agent-1"
    assert PaperAccountStatus.PAUSED.value == "paused"
    assert PaperTradeSide.SELL.value == "sell"
    assert PaperTradingAccountModel.__tablename__ == "paper_trading_accounts"


def test_paper_scheduler_parses_market_time_and_strategy_interval():
    assert PaperTradingScheduler._parse_market_time("1700000000000").year == 2023
    assert PaperTradingScheduler._interval({"decisionMode": "rule", "technicalAnalysisTimeframe": "1h"}) == 3600
