"""TraderAgent 的只读、时间安全数据工具网关。"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from trader.schemas import ToolRequest, ToolResult


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.microsecond:
            text = value.isoformat(timespec="microseconds")
        elif value.second:
            text = value.isoformat(timespec="seconds")
        else:
            text = value.isoformat(timespec="minutes")
        return text.replace("+00:00", "Z")
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _compact_decimal(value: Any) -> str:
    """为 LLM 上下文压缩十进制文本，不改变底层数值或计算精度。"""
    if value is None or value == "":
        return ""
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    if not number.is_finite():
        return str(value)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


class TraderToolGateway:
    """只暴露调查能力；不包含下单、撤单或修改账户的写操作。"""

    CATALOG = {
        "get_market_snapshot": "获取授权标的当前价格",
        "get_ohlcv": "按 symbol 获取截至 as_of 的 OHLCV，limit<=500",
        "get_indicators": "获取调用方已计算且截至 as_of 的技术事实",
        "search_news": "检索调用方提供且截至 as_of 的新闻资料",
        "get_account_state": "获取余额、权益和持仓摘要",
        "get_positions_and_orders": "获取持仓和已有订单摘要",
        "get_recent_trades": "获取调用方提供的近期成交",
    }

    def __init__(
        self,
        *,
        snapshot: Any,
        account: Any,
        context: Optional[Dict[str, Any]],
        as_of: datetime,
        authorized_symbols: Iterable[str],
    ) -> None:
        self.snapshot = snapshot
        self.account = account
        self.context = context or {}
        self.as_of = self._aware(as_of)
        self.authorized_symbols = {str(item).upper() for item in authorized_symbols}

    @classmethod
    def catalog(cls) -> List[Dict[str, str]]:
        return [{"name": name, "description": description} for name, description in cls.CATALOG.items()]

    def execute(self, request: ToolRequest) -> ToolResult:
        try:
            handler = getattr(self, f"_{request.name}")
            data = handler(dict(request.arguments or {}))
            return ToolResult(
                tool_call_id=request.tool_call_id,
                name=request.name,
                as_of=self.as_of,
                source="runtime_snapshot",
                data=data,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=request.tool_call_id,
                name=request.name,
                as_of=self.as_of,
                source="runtime_snapshot",
                error=str(exc)[:500],
            )

    def _symbol(self, args: Dict[str, Any]) -> str:
        symbol = str(args.get("symbol") or "").upper()
        if not symbol or symbol not in self.authorized_symbols:
            raise ValueError("symbol 未授权")
        return symbol

    def _get_market_snapshot(self, args: Dict[str, Any]) -> Dict[str, Any]:
        requested = str(args.get("symbol") or "").upper()
        prices = getattr(self.snapshot, "prices", {}) or {}
        symbols = [requested] if requested else sorted(self.authorized_symbols)
        return {
            "prices": {
                symbol: _compact_decimal(prices[symbol])
                for symbol in symbols if symbol in prices
            },
            "timestamp": _iso(getattr(self.snapshot, "timestamp", self.as_of)),
        }

    def _get_ohlcv(self, args: Dict[str, Any]) -> Dict[str, Any]:
        symbol = self._symbol(args)
        limit = max(1, min(500, int(args.get("limit") or 100)))
        bars = list((getattr(self.snapshot, "klines", {}) or {}).get(symbol) or [])
        safe = [bar for bar in bars if self._aware(getattr(bar, "timestamp", self.as_of)) <= self.as_of]
        return {
            "symbol": symbol,
            "bars": [[
                _iso(getattr(bar, "timestamp", "")),
                _compact_decimal(getattr(bar, "open", "")),
                _compact_decimal(getattr(bar, "high", "")),
                _compact_decimal(getattr(bar, "low", "")),
                _compact_decimal(getattr(bar, "close", "")),
                _compact_decimal(getattr(bar, "volume", "")),
            ] for bar in safe[-limit:]],
        }

    def _get_indicators(self, args: Dict[str, Any]) -> Dict[str, Any]:
        symbol = self._symbol(args)
        facts = self.context.get("technical_facts") or {}
        return {"symbol": symbol, "facts": facts.get(symbol) or {}}

    def _search_news(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or "").strip().lower()
        limit = max(1, min(50, int(args.get("limit") or 10)))
        raw = self.context.get("news_items")
        if isinstance(raw, list):
            items = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                item_time = item.get("published_at") or item.get("timestamp")
                if item_time and self._aware(item_time) > self.as_of:
                    continue
                if query and query not in str(item).lower():
                    continue
                items.append(item)
            return {"query": query, "items": items[-limit:]}
        text = str(self.context.get("news_text") or "")
        if query and query not in text.lower():
            text = ""
        return {"query": query, "text": text[:12000]}

    def _get_account_state(self, args: Dict[str, Any]) -> Dict[str, Any]:
        positions = self._positions()
        margin_used = sum(
            Decimal(str(item.get("margin_used") or 0)) for item in positions
        )
        return {
            "balance": _compact_decimal(getattr(self.account, "balance", 0)),
            "equity": _compact_decimal(getattr(self.account, "equity", 0)),
            "default_leverage": _compact_decimal(getattr(self.account, "leverage", 1)),
            "margin_used": _compact_decimal(margin_used),
            "positions": positions,
        }

    def _get_positions_and_orders(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "positions": self._positions(),
            "orders": list(self.context.get("open_orders") or []),
        }

    def _get_recent_trades(self, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = max(1, min(100, int(args.get("limit") or 20)))
        trades = self.context.get("recent_trades")
        if trades is None:
            trades = getattr(self.account, "trades", [])
        rows = []
        for trade in list(trades or [])[-limit:]:
            if isinstance(trade, dict):
                rows.append(trade)
            else:
                rows.append({
                    key: (
                        _iso(getattr(trade, key))
                        if key == "timestamp"
                        else _compact_decimal(getattr(trade, key))
                        if key in {"quantity", "price", "pnl"}
                        else str(getattr(trade, key))
                    )
                    for key in ("id", "timestamp", "symbol", "side", "quantity", "price", "pnl")
                    if hasattr(trade, key)
                })
        return {"trades": rows}

    def _positions(self) -> List[Dict[str, Any]]:
        rows = []
        for position in self.account.get_all_positions():
            rows.append({
                "symbol": str(getattr(position, "symbol", "")),
                "side": str(getattr(position, "side", "")),
                "quantity": _compact_decimal(getattr(position, "quantity", 0)),
                "entry_price": _compact_decimal(getattr(position, "entry_price", 0)),
                "leverage": _compact_decimal(getattr(position, "leverage", 1)),
                "margin_used": _compact_decimal(getattr(position, "margin_used", 0)),
                "trade_plan": getattr(position, "trade_plan", None),
            })
        return rows

    @staticmethod
    def _aware(value: Any) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime):
            raise ValueError("时间字段无效")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
