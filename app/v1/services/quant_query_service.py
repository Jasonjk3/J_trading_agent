"""Owner-scoped research queries. No orders, task control, report generation or credential output."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func

from app.v1.services.quant_tool_common import decimal, drawdown_analysis, fields, instant, result, safe_value
from app.v1.services.query_contracts import trading_sandbox_mode


class QuantQueryService:
    def __init__(self, user_id, session):
        self.user_id, self.session = str(user_id), session

    def market(self):
        from app.v1.services.market_service import MarketService
        return MarketService()._get_market_service()

    async def market_symbols(self, keyword="", inst_type="SPOT", limit=20):
        rows = await self.market().api.get_instruments(inst_type=inst_type)
        matches = [r for r in rows if keyword.upper() in r.get("instId", "").upper()]
        return result("OKX instruments", {"items": [fields(r, ["instId", "instType", "baseCcy", "quoteCcy", "settleCcy", "tickSz", "lotSz", "minSz", "state"]) for r in matches[:limit]], "total": len(matches)}, complete=len(matches) <= limit)

    async def market_quote(self, symbol):
        from lib.okx.symbol_utils import normalize_okx_symbol
        row = await self.market().get_ticker(normalize_okx_symbol(symbol))
        if not row or decimal(row.get("last") or 0) <= 0:
            raise ValueError("交易所未返回有效报价")
        payload = fields(row, ["instId", "last", "askPx", "bidPx", "open24h", "high24h", "low24h", "vol24h", "volCcy24h"])
        market_time = instant(row.get("ts"))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(market_time)).total_seconds() if market_time else None
        fresh = age is not None and -5 <= age <= 60
        return result("OKX ticker", {**payload, "market_time": market_time, "quoteAgeSeconds": round(age, 2) if age is not None else None}, complete=fresh, warnings=[] if fresh else ["报价时间缺失或超过60秒，请勿视为当前实时报价"])

    async def market_orderbook(self, symbol, depth=5):
        from lib.okx.symbol_utils import normalize_okx_symbol
        row = await self.market().get_order_books(normalize_okx_symbol(symbol), depth)
        if not row or not row.get("bids") or not row.get("asks"):
            raise ValueError("盘口数据不可用")
        return result("OKX orderbook", {"symbol": symbol, "bids": row["bids"][:depth], "asks": row["asks"][:depth], "market_time": instant(row.get("ts"))}, complete=bool(row.get("ts")))

    async def market_recent_trades(self, symbol, limit=20):
        from lib.okx.symbol_utils import normalize_okx_symbol
        rows = await self.market().get_trades(normalize_okx_symbol(symbol), limit)
        return result("OKX public trades", {"symbol": symbol, "items": [fields(row, ["tradeId", "px", "sz", "side", "ts"]) for row in rows[:limit]]}, warnings=["公开市场成交，不是账户成交"])

    async def market_movers(self, metric="gainers", limit=10):
        service = self.market()
        tickers = await service.get_tickers(inst_type="SPOT")
        if not tickers:
            raise ValueError("行情不可用")
        rows = service.rank_tickers(tickers, metric, limit)
        return result("OKX SPOT USDT", {"metric": metric, "items": [fields(r, ["instId", "last", "change_pct", "quoteVolume24h", "quoteCurrency", "ts"]) for r in rows]})

    async def market_overview(self):
        return result("OKX SPOT USDT", await self.market().get_market_summary())

    async def exchange_system_status(self):
        rows = await self.market().get_system_status()
        return result("OKX system status", {"items": rows[:20]}, complete=len(rows) <= 20)

    async def list_favorite_symbols(self, limit=30):
        from app.v1.services.market_service import MarketService
        rows = await MarketService().get_favorite_symbols(self.session, self.user_id)
        return result("user favorites", {"items": rows[:limit], "total": len(rows)}, complete=len(rows) <= limit)

    async def technical_indicators(self, symbol, interval="1h"):
        from app.v1.services.market_service import MarketService
        row = await MarketService().get_indicators(symbol, interval, session=self.session)
        row.pop("recommendation", None)
        return result("OKX ticker and computed indicators", row, warnings=["指标基于有限K线；报价时间与指标最后一根K线时间可能不同"])

    async def multi_timeframe_snapshot(self, symbol, intervals=None):
        values = []
        for interval in intervals or ["1h", "4h", "1d"]:
            values.append(await self.technical_indicators(symbol, interval))
        return result("multi-timeframe indicators", {"symbol": symbol, "snapshots": values}, warnings=["各周期按实际采集时间记录，不保证同一时刻的原子快照"])

    async def list_technical_reports(self, page=1, limit=10):
        from app.v1.services.technical_analysis_service import TechnicalAnalysisService
        return result("stored technical reports", await TechnicalAnalysisService().list_generation_records(self.session, self.user_id, page, limit))

    async def technical_report_detail(self, record_id):
        from app.v1.services.technical_analysis_service import TechnicalAnalysisService
        row = await TechnicalAnalysisService().get_generation_record(self.session, self.user_id, record_id)
        if row is None:
            raise ValueError("报告不存在或不可访问")
        return result("stored technical report", row, warnings=["读取历史报告，不重新生成"])

    async def list_exchange_accounts(self, limit=20):
        from app.v1.crud.exchange_account_crud import get_exchange_accounts
        rows = await get_exchange_accounts(self.session, self.user_id, limit=limit + 1)
        return result("owned exchange accounts", {"items": [fields(r, ["id", "remark", "exchange", "enabled", "bind_status", "read_only"]) for r in rows[:limit]]}, environment=self.environment(), complete=len(rows) <= limit)

    @staticmethod
    def environment():
        return "sandbox" if trading_sandbox_mode() else "live"

    async def client(self, account_id):
        from app.v1.services.manual_trading_service import ManualTradingService
        service = ManualTradingService()
        account = await service._get_account(self.session, self.user_id, account_id)
        return service._build_okx_client(account)

    async def _account_data(self, account_id):
        client = await self.client(account_id)
        balances = await client.get_account_balance()
        if not balances:
            raise ValueError("账户余额数据不可用")
        positions = await client.get_account_positions()
        return client, balances, positions

    async def account_overview(self, account_id, limit=20):
        _, balances, positions = await self._account_data(account_id)
        balance = balances[0]
        details = [fields(row, ["ccy", "eq", "eqUsd", "availBal", "frozenBal"]) for row in balance.get("details", [])]
        return result("OKX authenticated balance", {"account_id": account_id, "equityUsd": balance.get("totalEq"), "availableEquityUsd": balance.get("availEq"), "market_time": instant(balance.get("uTime")), "balances": details[:limit], "positionCount": len(positions)}, environment=self.environment(), complete=len(details) <= limit and balance.get("totalEq") not in (None, "") and bool(balance.get("uTime")))

    async def list_positions(self, account_id, symbol=None, limit=20):
        client = await self.client(account_id)
        rows = await client.get_account_positions(inst_id=symbol) if symbol else await client.get_account_positions()
        rows = [r for r in rows if decimal(r.get("pos") or 0) != 0]
        return result("OKX authenticated positions", {"account_id": account_id, "items": [fields(r, ["instId", "instType", "posSide", "pos", "notionalUsd", "avgPx", "markPx", "upl", "ccy", "lever", "liqPx", "uTime"]) for r in rows[:limit]], "total": len(rows)}, environment=self.environment(), complete=len(rows) <= limit)

    async def position_history(self, account_id, symbol=None, limit=20):
        client = await self.client(account_id)
        rows = await client.get_positions_history(inst_id=symbol, limit=limit)
        return result("OKX recent position history", {"items": [fields(r, ["instId", "posSide", "openAvgPx", "closeAvgPx", "pnl", "fee", "realizedPnl", "ccy", "cTime", "uTime"]) for r in rows[:limit]]}, environment=self.environment(), complete=False, warnings=["近期返回的持仓记录，不是完整区间账单"])

    async def list_pending_orders(self, account_id, symbol=None, limit=20):
        client = await self.client(account_id)
        rows = await client.get_orders_pending(inst_id=symbol, limit=limit)
        return result("OKX pending orders", {"items": [fields(r, ["ordId", "instId", "side", "posSide", "ordType", "sz", "px", "state", "accFillSz", "uTime"]) for r in rows[:limit]]}, environment=self.environment(), complete=len(rows) < limit, warnings=["普通未成交订单，不包含全部条件委托"])

    async def list_protection_orders(self, account_id, symbol=None, limit=20):
        client = await self.client(account_id)
        rows = []
        complete = True
        for kind in ("conditional", "oco"):
            batch = await client.get_algo_orders_pending(inst_id=symbol, ord_type=kind, limit=limit)
            complete &= len(batch) < limit
            rows.extend(batch)
        return result("OKX conditional and OCO orders", {"items": [fields(r, ["algoId", "instId", "posSide", "side", "sz", "tpTriggerPx", "slTriggerPx", "reduceOnly", "state"]) for r in rows[:limit]]}, environment=self.environment(), complete=complete and len(rows) <= limit, warnings=["不包含追踪止损等其他委托；不能仅凭缺少记录断言仓位未受保护"])

    async def account_profit_summary(self, from_date=None, to_date=None, exchange=None):
        from app.v1.services.analytics_service import AnalyticsService
        return result("OKX recent position records", await AnalyticsService().get_profit_summary(self.session, self.user_id, from_date, to_date, exchange), environment=self.environment())

    async def account_profit_breakdown(self, group_by="symbol", from_date=None, to_date=None):
        from app.v1.services.analytics_service import AnalyticsService
        service = AnalyticsService()
        method = {"symbol": service.get_profit_by_symbol, "exchange": service.get_profit_by_exchange, "day": service.get_profit_trend}[group_by]
        return result("OKX recent position records", await method(self.session, self.user_id, from_date=from_date, to_date=to_date), environment=self.environment())

    async def portfolio_risk_summary(self, account_id):
        _, balances, positions = await self._account_data(account_id)
        notionals, net = {}, Decimal(0)
        unknown = []
        for row in positions:
            if decimal(row.get("pos") or 0) == 0:
                continue
            if row.get("instType") not in {"SWAP", "FUTURES"} or row.get("posSide") not in {"long", "short", "net"} or row.get("notionalUsd") in (None, ""):
                unknown.append(row.get("instId")); continue
            value = abs(decimal(row["notionalUsd"]))
            symbol = row["instId"]
            notionals[symbol] = notionals.get(symbol, Decimal(0)) + value
            side = row.get("posSide")
            net += -value if side == "short" or (side == "net" and decimal(row["pos"]) < 0) else value
        gross = sum(notionals.values(), Decimal(0))
        equity = decimal(balances[0]["totalEq"]) if balances[0].get("totalEq") not in (None, "") else None
        return result("OKX positions and USD equity", {"account_id": account_id, "equityUsd": equity,
            "grossNotionalUsd": gross if not unknown else None, "netNotionalUsd": net if not unknown else None,
            "grossExposureToEquity": gross / equity if equity and equity > 0 and not unknown else None,
            "concentrationPercent": {key: str(value / gross * 100) for key, value in notionals.items()} if gross and not unknown else {},
            "missingNotionalSymbols": unknown, "stopLossCoverage": None}, environment=self.environment(), complete=not unknown and equity is not None,
            warnings=["按衍生品名义价值计算；现货余额、期权Delta及完整止损覆盖未纳入，不等同于组合保证金风险"])

    async def backtest(self, backtest_id):
        from app.v1.services.backtest_service import BacktestService
        service = BacktestService()
        row = await service.get_by_id(self.session, backtest_id, self.user_id)
        if row is None:
            raise ValueError("回测不存在或不可访问")
        return service, row

    async def backtest_detail(self, backtest_id):
        service, row = await self.backtest(backtest_id)
        return result("stored backtest", {**service.model_to_list_item(row), **fields(row, ["strategy_config", "interval", "maker_fee", "taker_fee", "slippage", "result_statistics"])})

    async def backtest_progress(self, backtest_id):
        service, _ = await self.backtest(backtest_id)
        return result("backtest progress", await service.get_progress(self.session, backtest_id, self.user_id))

    async def backtest_trades(self, backtest_id, page=1, limit=20, order="recent"):
        _, row = await self.backtest(backtest_id)
        from models.inner_models.backtest_model import BacktestTradeModel as Trade
        ordering = {"recent": Trade.timestamp.desc(), "oldest": Trade.timestamp.asc(), "largest_loss": Trade.pnl.asc(), "largest_profit": Trade.pnl.desc()}[order]
        query = select(Trade).where(Trade.backtest_id == row.id).order_by(ordering, Trade.id).offset((page - 1) * limit).limit(limit + 1)
        rows = (await self.session.execute(query)).scalars().all()
        return result("stored backtest trades", {"page": page, "has_more": len(rows) > limit, "order": order,
            "items": [fields(r, ["id", "timestamp", "symbol", "side", "trade_type", "action", "price", "quantity", "fee", "pnl", "leverage", "reasoning"]) for r in rows[:limit]]}, complete=len(rows) <= limit)

    async def backtest_decisions(self, backtest_id, page=1, limit=10, decision_id=None):
        service, _ = await self.backtest(backtest_id)
        if decision_id:
            row = await service.get_decision(self.session, backtest_id, decision_id, self.user_id)
            if row is None:
                raise ValueError("决策记录不存在")
            rows, total = [row], 1
        else:
            rows, total = await service.get_decisions(self.session, backtest_id, self.user_id, skip=(page - 1) * limit, limit=limit)
        return result("stored backtest decisions", {"items": [fields(r, ["id", "timestamp", "action", "symbol", "quantity", "reasoning", "reference_price", "execution_result"]) for r in rows], "total": total, "page": page}, complete=total <= limit)

    async def _equity(self, backtest_id):
        from models.inner_models.backtest_model import BacktestEquityModel as Equity
        _, row = await self.backtest(backtest_id)
        records = (await self.session.execute(select(Equity.timestamp, Equity.equity).where(Equity.backtest_id == row.id).order_by(Equity.timestamp, Equity.id))).all()
        return row, [{"timestamp": row.start_time, "equity": row.initial_capital}, *[{"timestamp": time, "equity": value} for time, value in records]]

    async def backtest_drawdown_analysis(self, backtest_id):
        _, points = await self._equity(backtest_id)
        if len(points) <= 1:
            return result("stored equity curve", {"analysis": None}, complete=False, warnings=["没有权益记录"])
        return result("full stored equity curve", drawdown_analysis(points))

    async def backtest_equity(self, backtest_id, limit=50):
        _, points = await self._equity(backtest_id)
        stride = max(1, (len(points) + limit - 2) // max(1, limit - 1))
        sampled = points[::stride]
        if sampled[-1] != points[-1]: sampled.append(points[-1])
        return result("stored equity curve", {"points": sampled, "sampled": len(sampled) < len(points), "fullCurveAnalysis": drawdown_analysis(points)}, complete=len(points) > 1)

    async def compare_backtests(self, backtest_ids):
        items, signatures = [], []
        for backtest_id in backtest_ids:
            service, row = await self.backtest(backtest_id)
            items.append(service.model_to_list_item(row))
            signatures.append(fields(row, ["start_time", "end_time", "initial_capital", "symbols", "interval", "maker_fee", "taker_fee", "slippage"]))
        differences = [key for key in signatures[0] if any(s[key] != signatures[0][key] for s in signatures[1:])]
        return result("owned backtest comparison", {"items": items, "comparable": not differences, "differentFields": differences}, warnings=["结果为历史回测，不能推断未来收益"])

    async def backtest_market_context(self, backtest_id, symbol=None, limit=50):
        service, row = await self.backtest(backtest_id)
        if symbol and symbol not in (row.symbols or []):
            raise ValueError("标的不属于此回测")
        # Avoid the large unbounded kline API: query only stored execution-period bars.
        from models.inner_models.backtest_model import HistoricalKlineModel as Kline
        from lib.okx.symbol_utils import normalize_okx_symbol
        chosen = symbol or (row.symbols or [None])[0]
        if not chosen: raise ValueError("回测未配置标的")
        rows = (await self.session.execute(select(Kline).where(Kline.exchange == row.exchange,
            Kline.symbol == normalize_okx_symbol(chosen), Kline.interval == getattr(row.interval, "value", row.interval),
            Kline.timestamp >= row.start_time, Kline.timestamp <= row.end_time).order_by(Kline.timestamp.desc()).limit(limit + 1))).scalars().all()
        return result("stored backtest market bars", {"symbol": chosen, "items": [fields(r, ["timestamp", "open_price", "high_price", "low_price", "close_price", "volume"]) for r in reversed(rows[:limit])]}, complete=len(rows) <= limit, warnings=["回测执行区间内已存储行情，不含区间之后的数据；不等于某一决策点可见的数据"])

    async def export_backtest_report(self, backtest_id):
        await self.backtest(backtest_id)
        from urllib.parse import quote
        return result("authenticated report route", {"download_path": f"/v1/backtest/{quote(backtest_id, safe='')}/export", "authentication": "current-user bearer token required"})

    async def paper_accounts_summary(self, range_name="30D", limit=20):
        from app.v1.services.paper_trading_service import PaperTradingService
        data = await PaperTradingService().dashboard(self.session, self.user_id, range_name, ensure_account=False)
        data["summary"]["maxDrawdownBasis"] = "worst_single_account_within_requested_range"
        accounts = data["accounts"]
        return result("stored paper trading", {"summary": data["summary"], "accounts": accounts[:limit]}, environment="paper", complete=len(accounts) <= limit)

    async def paper_positions(self, account_id):
        from app.v1.services.paper_trading_service import PaperTradingService
        rows = await PaperTradingService().list_positions(self.session, account_id, self.user_id)
        return result("stored paper positions", {"items": rows[:30], "total": len(rows)}, environment="paper", complete=len(rows) <= 30)

    async def paper_trades(self, account_id, limit=20):
        from app.v1.services.paper_trading_service import PaperTradingService
        rows = await PaperTradingService().list_trades(self.session, account_id, self.user_id, limit)
        return result("stored paper trades", {"items": rows}, environment="paper", complete=len(rows) < limit)

    async def paper_decisions(self, account_id, limit=10):
        from app.v1.services.paper_trading_service import PaperTradingService
        rows = await PaperTradingService().list_decisions(self.session, account_id, self.user_id, limit)
        return result("stored paper decisions", {"items": rows}, environment="paper", complete=len(rows) < limit)

    async def agent(self, agent_id):
        from app.v1.services.trading_agent_service import TradingAgentService
        service = TradingAgentService()
        agent = await service.get_by_id(self.session, agent_id, self.user_id)
        if agent is None: raise ValueError("交易Agent不存在或不可访问")
        return service, agent

    async def list_trading_agents(self, limit=20):
        from app.v1.services.trading_agent_service import TradingAgentService
        rows, total = await TradingAgentService().get_list(self.session, self.user_id)
        return result("owned trading agents", {"items": [fields(r, ["id", "name", "status", "strategy_type", "last_run_at"]) for r in rows[:limit]], "total": total}, complete=total <= limit)

    async def trading_agent_status(self, agent_id, limit=10):
        service, agent = await self.agent(agent_id)
        runtime = await service.get_trader_runtime(self.session, agent_id, self.user_id, limit)
        return result("trading scheduler and stored audit", {"agent": fields(agent, ["id", "name", "status", "last_run_at"]), "scheduler": service.get_live_status(agent_id), "audit": runtime}, environment=self.environment(), warnings=["调度器状态仅反映当前进程，未加载不等于Agent已停止"])

    async def trading_agent_strategy(self, agent_id):
        _, agent = await self.agent(agent_id)
        return result("stored strategy config", {"agent_id": agent_id, "strategy": agent.strategy_config or {}})

    async def trading_agent_performance(self, agent_id, period="30d", limit=30):
        service, _ = await self.agent(agent_id)
        rows = await service.get_profit_curve(self.session, agent_id, self.user_id, period)
        operations, total = await service.get_operations(self.session, agent_id, self.user_id, min(limit, 10))
        return result("stored agent profit and operations", {"points": [fields(r, ["record_time", "value", "cumulative", "equity", "unrealized_pnl"]) for r in rows[-limit:]],
            "operations": [fields(r, ["id", "type", "symbol", "reason", "result", "created_at"]) for r in operations], "operationCount": total}, complete=len(rows) <= limit and total <= 10)

    async def trading_agent_research_context(self, agent_id):
        service, _ = await self.agent(agent_id)
        return result("stored technical and news context", await service.build_trading_analysis_context_for_agent(self.session, agent_id, self.user_id, readonly=True))

    async def trading_agent_diagnosis(self, agent_id):
        service, agent = await self.agent(agent_id)
        status = service.get_live_status(agent_id)
        runtime = await service.get_trader_runtime(self.session, agent_id, self.user_id, 5)
        findings = []
        if status is None: findings.append("当前进程没有该Agent的调度器状态，不能据此判断远程进程")
        if status and status.get("last_error"): findings.append("调度器记录错误，请核对错误摘要及事件")
        if status and status.get("state") == "cooldown": findings.append("调度器处于冷却状态")
        if not agent.exchange_account_id: findings.append("未绑定交易所账户")
        if not findings: findings.append("未发现可直接确认的异常，需结合最近事件判断是否无信号或风控拒绝")
        return result("scheduler and recent audit evidence", {"findings": findings, "scheduler": status, "evidence": runtime}, warnings=["只读诊断，不触发决策、不重启Agent"])

    async def list_news_sources(self, limit=20):
        from app.v1.services.news_intelligence_service import NewsIntelligenceService
        rows, total = await NewsIntelligenceService().get_list(self.session, self.user_id)
        return result("owned news collection tasks", {"items": rows[:limit], "total": total}, complete=total <= limit)

    async def query_news_timeline(self, agent_id, keyword=None, page=1, limit=10, from_date=None, to_date=None):
        from app.v1.services.news_intelligence_service import NewsIntelligenceService
        service = NewsIntelligenceService()
        if await service.get_by_id(self.session, agent_id, self.user_id) is None: raise ValueError("采集任务不存在或不可访问")
        start = datetime.strptime(from_date, "%Y-%m-%d") if from_date else None
        end = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1) if to_date else None
        if start and end and end < start: raise ValueError("日期范围无效")
        rows, total = await service.list_timeline_items(self.session, agent_id, self.user_id, keyword=keyword, page=page, page_size=limit, time_from=start, time_to=end)
        return result("stored collected news", {"items": [{**row, "source_verified": False} for row in rows], "total": total}, complete=total <= limit, warnings=["已采集的模型整理资讯，原文及真实性未由本工具独立核实"])

    async def _admin(self):
        from models.inner_models.user_model import UserModel, UserRole
        user = (await self.session.execute(select(UserModel).where(UserModel.id == self.user_id, UserModel.is_active == True))).scalar_one_or_none()
        if user is None or user.role != UserRole.ADMIN: raise PermissionError("需要管理员权限")

    async def monitor_tasks(self, limit=20):
        await self._admin()
        from app.v1.services.data_monitor_service import DataMonitorService
        service = DataMonitorService()
        rows = await service.list_tasks(self.session, self.user_id)
        return result("owned monitor tasks", {"items": rows[:limit]}, complete=len(rows) <= limit)

    async def monitor_events(self, task_id=None, limit=20):
        await self._admin()
        from app.v1.services.data_monitor_service import DataMonitorService
        service = DataMonitorService()
        rows = await service.get_events(self.session, self.user_id, task_id)
        return result("owned monitor events", {"items": rows[:limit], "summary": await service.get_summary(self.session, self.user_id)}, complete=len(rows) <= limit)

    async def llm_usage_summary(self, days=7):
        from models.inner_models.llm_monitor_model import LLMUsageLog as Log
        start = datetime.now() - timedelta(days=days)
        row = (await self.session.execute(select(func.count(Log.id), func.sum(Log.total_tokens), func.sum(Log.cost_usd)).where(Log.user_id == self.user_id, Log.created_at >= start))).one()
        return result("owned llm usage logs", {"days": days, "from": start.isoformat(), "to": datetime.now().isoformat(), "requests": row[0], "total_tokens": row[1] or 0, "cost_usd": str(row[2] or 0)}, complete=False, warnings=["仅统计明确记录当前user_id的日志；未归属日志不计入，不能据此断言全部调用费用为零"])

    async def research_brief(self, symbol, interval="4h", news_agent_id=None):
        quote = await self.market_quote(symbol)
        indicators = await self.technical_indicators(symbol, interval)
        news = await self.query_news_timeline(news_agent_id, limit=5) if news_agent_id else None
        return result("research evidence bundle", {"quote": quote, "indicators": indicators, "news": news}, warnings=["返回数据依据，由当前对话模型整理简报；不额外调用模型或下单"])
