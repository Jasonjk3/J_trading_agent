"""Reviewed query allowlist. Model arguments never contain user/tenant identities."""
from core.agent_runtime.tools import ConversationTool
from app.v1.services.quant_query_service import QuantQueryService

ID = {"type": "string", "minLength": 1, "maxLength": 64}
SYMBOL = {"type": "string", "pattern": "^[A-Z0-9]{2,15}(-?[A-Z0-9]{2,15}){0,2}$", "maxLength": 40}
INTERVAL = {"type": "string", "enum": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 30}
PAGE = {"type": "integer", "minimum": 1, "maximum": 100}
TEXT = {"type": "string", "maxLength": 80}
DATE = {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}


def quant_tools(user_id, session, *, is_admin=False):
    service = QuantQueryService(user_id, session)
    tools = []

    def add(name, description, properties=None, required=()):
        tools.append(ConversationTool(name, description, {"type": "object", "properties": properties or {},
            "required": list(required), "additionalProperties": False}, getattr(service, name), version="quant-read-v1"))

    add("market_symbols", "搜索OKX交易对及交易规格。", {"keyword": TEXT, "inst_type": {"enum": ["SPOT", "SWAP", "FUTURES"]}, "limit": LIMIT})
    add("market_quote", "查询最新成交报价与24小时行情；回答现在价格优先用此工具。", {"symbol": SYMBOL}, ["symbol"])
    add("market_orderbook", "查询买卖盘口深度与时间。", {"symbol": SYMBOL, "depth": {"type": "integer", "enum": [5, 10, 20]}}, ["symbol"])
    add("market_recent_trades", "查询公开市场近期成交，不是个人成交。", {"symbol": SYMBOL, "limit": LIMIT}, ["symbol"])
    add("market_movers", "OKX现货USDT涨幅、跌幅或成交额榜。", {"metric": {"enum": ["gainers", "losers", "volume"]}, "limit": LIMIT})
    add("market_overview", "查询BTC/ETH及现货市场榜单摘要。")
    add("exchange_system_status", "查询OKX维护状态。")
    add("technical_indicators", "计算均线、RSI、MACD等指标；不生成新LLM报告。", {"symbol": SYMBOL, "interval": INTERVAL}, ["symbol"])
    add("multi_timeframe_snapshot", "查询同一标的最多三个周期的技术指标。", {"symbol": SYMBOL, "intervals": {"type": "array", "items": INTERVAL, "minItems": 1, "maxItems": 3, "uniqueItems": True}}, ["symbol"])
    add("research_brief", "组合报价、技术指标及可选已采集资讯，供当前模型整理简报。", {"symbol": SYMBOL, "interval": INTERVAL, "news_agent_id": ID}, ["symbol"])
    if session is None:
        # Keep the public evidence bundle independent of private collection tasks.
        return [t for t in tools if t.name != "research_brief"]

    add("list_favorite_symbols", "读取我的自选交易对。", {"limit": LIMIT})
    add("list_technical_reports", "查询我已有的技术报告列表。", {"page": PAGE, "limit": LIMIT})
    add("technical_report_detail", "读取我的已有报告，不重新生成。", {"record_id": ID}, ["record_id"])
    add("list_exchange_accounts", "查询我绑定账户的显示信息，不含密钥。", {"limit": LIMIT})
    add("account_overview", "读取我选定账户的美元权益和余额；注意环境与完整性。", {"account_id": ID, "limit": LIMIT}, ["account_id"])
    add("list_positions", "读取我选定账户的真实持仓。", {"account_id": ID, "symbol": SYMBOL, "limit": LIMIT}, ["account_id"])
    add("position_history", "读取我选定账户近期持仓历史。", {"account_id": ID, "symbol": SYMBOL, "limit": LIMIT}, ["account_id"])
    add("list_pending_orders", "查询我的普通挂单，不能撤单。", {"account_id": ID, "symbol": SYMBOL, "limit": LIMIT}, ["account_id"])
    add("list_protection_orders", "查询我的止盈止损条件委托，覆盖范围见返回说明。", {"account_id": ID, "symbol": SYMBOL, "limit": LIMIT}, ["account_id"])
    add("account_profit_summary", "我的近期已实现盈亏与手续费；无期初权益时不计算收益率。", {"from_date": DATE, "to_date": DATE, "exchange": {"enum": ["okx"]}})
    add("account_profit_breakdown", "按标的、交易所或日期汇总我近期返回的盈亏。", {"group_by": {"enum": ["symbol", "exchange", "day"]}, "from_date": DATE, "to_date": DATE})
    add("portfolio_risk_summary", "计算选定账户的名义敞口与集中度，不把未知值当零。", {"account_id": ID}, ["account_id"])
    add("backtest_detail", "读取我的回测配置、费用和统计详情。", {"backtest_id": ID}, ["backtest_id"])
    add("backtest_progress", "查询我的回测进度及失败状态，不重跑。", {"backtest_id": ID}, ["backtest_id"])
    add("backtest_trades", "分页查询我的回测成交，可按全局盈亏排序。", {"backtest_id": ID, "page": PAGE, "limit": LIMIT, "order": {"enum": ["recent", "oldest", "largest_loss", "largest_profit"]}}, ["backtest_id"])
    add("backtest_decisions", "读取我的回测决策及执行结果，不返回隐藏思维链。", {"backtest_id": ID, "decision_id": ID, "page": PAGE, "limit": LIMIT}, ["backtest_id"])
    add("backtest_equity", "读取抽样权益曲线及全量曲线回撤计算。", {"backtest_id": ID, "limit": {"type": "integer", "minimum": 5, "maximum": 100}}, ["backtest_id"])
    add("backtest_drawdown_analysis", "从完整已存权益曲线计算最大回撤起止与恢复时间。", {"backtest_id": ID}, ["backtest_id"])
    add("compare_backtests", "比较我的2至5个回测，并指出区间、资金、费用等不可比项。", {"backtest_ids": {"type": "array", "items": ID, "minItems": 2, "maxItems": 5, "uniqueItems": True}}, ["backtest_ids"])
    add("backtest_market_context", "读取我的回测执行区间已存K线，不读取区间之后行情。", {"backtest_id": ID, "symbol": SYMBOL, "limit": LIMIT}, ["backtest_id"])
    add("export_backtest_report", "取得我回测报告的受鉴权下载路径。", {"backtest_id": ID}, ["backtest_id"])
    add("paper_accounts_summary", "仅读我的模拟盘总览，不自动创建账户。", {"range_name": {"enum": ["7D", "30D", "90D", "ALL"]}, "limit": LIMIT})
    add("paper_positions", "查询我的模拟账户持仓，与真实资金分开。", {"account_id": ID}, ["account_id"])
    add("paper_trades", "查询我的模拟成交。", {"account_id": ID, "limit": LIMIT}, ["account_id"])
    add("paper_decisions", "查询我的已存模拟决策，不触发新决策。", {"account_id": ID, "limit": LIMIT}, ["account_id"])
    add("list_trading_agents", "查询我的交易Agent列表与状态。", {"limit": LIMIT})
    add("trading_agent_status", "查询我的交易Agent调度状态及近期审计事实。", {"agent_id": ID, "limit": LIMIT}, ["agent_id"])
    add("trading_agent_strategy", "只读查询我的Agent策略配置。", {"agent_id": ID}, ["agent_id"])
    add("trading_agent_performance", "查询我的Agent收益记录和操作摘要。", {"agent_id": ID, "period": {"enum": ["1d", "7d", "30d", "90d"]}, "limit": LIMIT}, ["agent_id"])
    add("trading_agent_research_context", "只读组装我的Agent消息面及已有技术面依据，不调用额外模型。", {"agent_id": ID}, ["agent_id"])
    add("trading_agent_diagnosis", "诊断我的Agent冷却、错误及配置缺口，不启动决策或重启。", {"agent_id": ID}, ["agent_id"])
    add("list_news_sources", "查询我的消息面采集任务。", {"limit": LIMIT})
    add("query_news_timeline", "查询我的已采集资讯，来源未独立核实。", {"agent_id": ID, "keyword": TEXT, "page": PAGE, "limit": LIMIT, "from_date": DATE, "to_date": DATE}, ["agent_id"])
    add("llm_usage_summary", "汇总明确归属于我的模型Token与费用，不包含未归属日志。", {"days": {"type": "integer", "minimum": 1, "maximum": 90}})
    if is_admin:
        add("monitor_tasks", "管理员读取自己配置的行情监控任务。", {"limit": LIMIT})
        add("monitor_events", "管理员读取自己的提醒触发与推送结果。", {"task_id": ID, "limit": LIMIT})
    return tools
