"""Account analytics with explicit currency, fee, coverage and unknown-return semantics."""
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from app.v1.crud.exchange_account_crud import get_exchange_accounts
from app.v1.services.query_contracts import query_coverage
from models.inner_models.exchange_account_model import BindStatus, ExchangeCode


def money(value):
    value = Decimal(str(value or 0))
    if not value.is_finite():
        raise ValueError("金额无效")
    return value


def net_pnl(item):
    if item.get("realizedPnl") not in (None, ""):
        return money(item["realizedPnl"])
    # OKX reports signed fees (negative payment, positive rebate).
    return sum((money(item.get(key)) for key in ("pnl", "fee", "fundingFee", "liqPenalty", "settledPnl")), Decimal(0))


class AnalyticsQueries:
    async def _history_rows(self, session, user_id, from_date=None, to_date=None, exchange=None, symbol=None):
        start = datetime.strptime(from_date, "%Y-%m-%d") if from_date else None
        end = datetime.strptime(to_date, "%Y-%m-%d") if to_date else None
        if start and end and (end < start or (end - start).days > 366):
            raise ValueError("日期范围无效或超过366天")
        accounts = await get_exchange_accounts(session=session, user_id=user_id,
            exchange=ExchangeCode(exchange) if exchange else None, enabled=True, bind_status=BindStatus.SUCCESS)
        rows, failed = [], []
        for account in accounts:
            try:
                fetched = await self._fetch_positions_history(account, from_date, to_date, symbol)
                rows.extend([{**item, "exchange": account.exchange.value, "accountId": str(account.id)} for item in fetched])
            except Exception:
                failed.append(str(account.id))
        meta = query_coverage(len(accounts), failed)
        # Existing exchange fetch reads the recent page, not an exhaustive ledger.
        meta.update(historyScope="exchange_recent_position_records", complete=False if accounts else meta["complete"])
        if accounts:
            meta["warnings"].append("仅统计交易所近期返回的持仓历史，不能视为完整区间账单")
        return rows, meta

    @staticmethod
    def _totals(rows):
        currencies = defaultdict(list)
        for item in rows:
            currencies[item.get("currency") or item.get("ccy") or "unknown"].append(item)
        groups = []
        for currency, items in currencies.items():
            groups.append({"currency": currency, "totalProfit": str(sum((money(i.get("pnl")) for i in items), Decimal(0))),
                "totalFee": str(sum((-money(i.get("fee")) for i in items), Decimal(0))),
                "netProfit": str(sum((net_pnl(i) for i in items), Decimal(0))), "tradeCount": len(items)})
        flat = groups[0] if len(groups) == 1 and groups[0]["currency"] != "unknown" else None
        return {"totalProfit": flat["totalProfit"] if flat else ("0" if not rows else None),
                "totalFee": flat["totalFee"] if flat else ("0" if not rows else None),
                "netProfit": flat["netProfit"] if flat else ("0" if not rows else None),
                "currency": flat["currency"] if flat else None, "byCurrency": groups,
                "tradeCount": len(rows), "netProfitBasis": "exchange_realizedPnl_or_signed_adjustments"}

    async def get_profit_summary(self, session, user_id, from_date=None, to_date=None, exchange=None, symbol=None):
        rows, meta = await self._history_rows(session, user_id, from_date, to_date, exchange, symbol)
        return {**self._totals(rows), **meta, "returnRate": None,
                "returnRateReason": "缺少真实期初权益及出入金数据，不计算账户收益率",
                "from": from_date, "to": to_date, "exchange": exchange}

    async def get_profit_trend(self, session, user_id, from_date=None, to_date=None, period="day", exchange=None, symbol=None):
        if period not in {"day", "week"}:
            raise ValueError("不支持的统计周期")
        rows, meta = await self._history_rows(session, user_id, from_date, to_date, exchange, symbol)
        buckets = defaultdict(list)
        for row in rows:
            if not row.get("closeTime"):
                continue
            date = datetime.fromisoformat(row["closeTime"]).date()
            if period == "week":
                date -= timedelta(days=date.weekday())
            buckets[str(date)].append(row)
        points, cumulative = [], defaultdict(Decimal)
        for day, items in sorted(buckets.items()):
            totals = self._totals(items)
            currency = totals["currency"]
            if currency:
                cumulative[currency] += money(totals["netProfit"])
            points.append({"date": day, "profit": totals["netProfit"], "currency": currency,
                           "cumulative": str(cumulative[currency]) if currency else None, "byCurrency": totals["byCurrency"]})
        return {"points": points, "period": period, **meta}

    async def _breakdown(self, session, user_id, dimension, from_date=None, to_date=None, exchange=None, symbol=None):
        rows, meta = await self._history_rows(session, user_id, from_date, to_date, exchange, symbol)
        buckets = defaultdict(list)
        for row in rows:
            buckets[row.get(dimension) or "unknown"].append(row)
        return {"list": [{dimension: key, **self._totals(items)} for key, items in sorted(buckets.items())], **meta}

    async def get_profit_by_exchange(self, session, user_id, from_date=None, to_date=None, symbol=None):
        return await self._breakdown(session, user_id, "exchange", from_date, to_date, symbol=symbol)

    async def get_profit_by_symbol(self, session, user_id, from_date=None, to_date=None, exchange=None):
        return await self._breakdown(session, user_id, "symbol", from_date, to_date, exchange=exchange)

    async def get_wallet_balance_detail(self, session, user_id, exchange=None):
        accounts = await get_exchange_accounts(session=session, user_id=user_id,
            exchange=ExchangeCode(exchange) if exchange else None, enabled=True, bind_status=BindStatus.SUCCESS)
        result, failed = [], []
        for account in accounts:
            try:
                result.append({**await self._fetch_account_balance(account), "accountId": str(account.id)})
            except Exception:
                failed.append(str(account.id))
        return {"list": result, **query_coverage(len(accounts), failed)}

    async def get_wallet_balance(self, session, user_id, exchange=None):
        result = await self.get_wallet_balance_detail(session, user_id, exchange)
        if not result["complete"]:
            from app.v1.services.query_contracts import QueryUnavailable
            raise QueryUnavailable("部分账户余额查询失败")
        return result["list"]
