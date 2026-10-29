#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
手工实盘交易服务
"""
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.crud.exchange_account_crud import get_exchange_account_by_id_and_user
from app.v1.services.exchange_account_service import ExchangeAccountService
from models.inner_models.exchange_account_model import BindStatus, ExchangeAccountModel, ExchangeCode
from lib.okx.okx_api import ApiService
from lib.okx.utils import NonRetryableRequestError
from app.v1.schemas.manual_trading_schema import PlaceManualOrderRequest
from app.v1.services.query_contracts import trading_sandbox_mode


class ManualTradingService:
    """手工实盘交易服务"""

    def __init__(self):
        self._exchange_account_service = ExchangeAccountService()

    async def search_instruments(
        self,
        session: AsyncSession,
        user_id: str,
        account_id: str,
        inst_type: str,
        keyword: Optional[str] = None,
    ) -> List[Dict]:
        account = await self._get_account(session, user_id, account_id)
        client = self._build_okx_client(account)
        instruments = await client.get_instruments(inst_type=inst_type)

        keyword_upper = (keyword or "").strip().upper()
        result = []
        for item in instruments:
            inst_id = item.get("instId", "")
            base_ccy = item.get("baseCcy", "")
            quote_ccy = item.get("quoteCcy", "")
            if keyword_upper and keyword_upper not in inst_id.upper() and keyword_upper not in base_ccy.upper() and keyword_upper not in quote_ccy.upper():
                continue

            result.append(
                {
                    "instId": inst_id,
                    "instType": item.get("instType", inst_type),
                    "baseCcy": base_ccy or None,
                    "quoteCcy": quote_ccy or None,
                    "settleCcy": item.get("settleCcy") or None,
                    "tickSz": item.get("tickSz") or None,
                    "lotSz": item.get("lotSz") or None,
                    "minSz": item.get("minSz") or None,
                    "state": item.get("state") or None,
                }
            )

        result.sort(key=lambda row: (row["state"] != "live", row["instId"]))
        return result[:80]

    async def get_snapshot(
        self,
        session: AsyncSession,
        user_id: str,
        account_id: str,
        inst_id: str,
    ) -> Dict:
        account = await self._get_account(session, user_id, account_id)
        client = self._build_okx_client(account)

        ticker = await client.get_ticker(inst_id)
        books = await client.get_order_books(inst_id, 5)

        open_24h = self._to_decimal(ticker.get("open24h"))
        last = self._to_decimal(ticker.get("last"))
        change_24h = Decimal("0")
        if open_24h > 0:
            change_24h = (last - open_24h) / open_24h * Decimal("100")

        return {
            "ticker": {
                "instId": ticker.get("instId", inst_id),
                "last": ticker.get("last", "0"),
                "askPx": ticker.get("askPx", "0"),
                "bidPx": ticker.get("bidPx", "0"),
                "high24h": ticker.get("high24h", "0"),
                "low24h": ticker.get("low24h", "0"),
                "change24h": str(change_24h.quantize(Decimal("0.01"))),
                "vol24h": ticker.get("vol24h") or None,
                "ts": ticker.get("ts") or None,
            },
            "bids": self._normalize_order_book_side(books.get("bids")),
            "asks": self._normalize_order_book_side(books.get("asks")),
        }

    async def get_account_overview(
        self,
        session: AsyncSession,
        user_id: str,
        account_id: str,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
    ) -> Dict:
        account = await self._get_account(session, user_id, account_id)
        client = self._build_okx_client(account)

        raw_balances = await client.get_account_balance()
        raw_positions = await client.get_account_positions(inst_type=inst_type, inst_id=inst_id)

        return {
            "balances": self._normalize_balances(raw_balances),
            "positions": self._normalize_positions(raw_positions),
        }

    async def get_pending_orders(
        self,
        session: AsyncSession,
        user_id: str,
        account_id: str,
        inst_type: Optional[str] = None,
        inst_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        account = await self._get_account(session, user_id, account_id)
        client = self._build_okx_client(account)
        orders = await client.get_orders_pending(inst_type=inst_type, inst_id=inst_id, limit=min(limit, 50))

        result = []
        for item in orders:
            result.append(
                {
                    "ordId": item.get("ordId", ""),
                    "instId": item.get("instId", ""),
                    "side": item.get("side", ""),
                    "ordType": item.get("ordType", ""),
                    "px": item.get("px") or None,
                    "sz": item.get("sz", "0"),
                    "accFillSz": item.get("accFillSz", "0"),
                    "state": item.get("state", "live"),
                    "posSide": item.get("posSide") or None,
                    "cTime": item.get("cTime") or None,
                }
            )

        return result

    async def place_order(
        self,
        session: AsyncSession,
        user_id: str,
        request: PlaceManualOrderRequest,
    ) -> Dict:
        account = await self._get_account(session, user_id, request.accountId, require_writable=True)
        client = self._build_okx_client(account)

        side, pos_side, reduce_only = self._resolve_trade_action(request.tradeAction, request.instType)
        td_mode = request.tdMode or ("cash" if request.instType == "SPOT" else "cross")

        if request.ordType == "limit" and not request.px:
            raise ValueError("限价单必须提供价格")

        if request.instType == "SWAP" and request.leverage:
            try:
                await client.set_leverage(
                    inst_id=request.instId,
                    lever=request.leverage,
                    mgn_mode=td_mode,
                    pos_side=pos_side,
                )
            except NonRetryableRequestError as e:
                raise ValueError(str(e))

        tgt_ccy = request.tgtCcy
        if request.instType == "SPOT" and request.ordType == "market" and not tgt_ccy:
            tgt_ccy = "base_ccy"

        try:
            result = await client.place_order(
                inst_id=request.instId,
                td_mode=td_mode,
                side=side,
                ord_type=request.ordType,
                sz=request.sz,
                px=request.px,
                pos_side=pos_side,
                reduce_only=reduce_only,
                tgt_ccy=tgt_ccy,
            )
        except NonRetryableRequestError as e:
            raise ValueError(str(e))
        return {
            "ordId": result.get("ordId"),
            "clOrdId": result.get("clOrdId"),
            "sCode": result.get("sCode"),
            "sMsg": result.get("sMsg"),
        }

    async def cancel_order(
        self,
        session: AsyncSession,
        user_id: str,
        account_id: str,
        inst_id: str,
        ord_id: str,
    ) -> Dict:
        account = await self._get_account(session, user_id, account_id, require_writable=True)
        client = self._build_okx_client(account)
        try:
            result = await client.cancel_order(inst_id=inst_id, ord_id=ord_id)
        except NonRetryableRequestError as e:
            raise ValueError(str(e))
        return {
            "ordId": result.get("ordId"),
            "clOrdId": result.get("clOrdId"),
            "sCode": result.get("sCode"),
            "sMsg": result.get("sMsg"),
        }

    async def _get_account(
        self,
        session: AsyncSession,
        user_id: str,
        account_id: str,
        require_writable: bool = False,
    ) -> ExchangeAccountModel:
        account = await get_exchange_account_by_id_and_user(session, account_id, user_id)
        if not account:
            raise ValueError("交易所账户不存在")
        if account.exchange != ExchangeCode.OKX:
            raise ValueError("当前仅支持 OKX 账户")
        if not account.enabled:
            raise ValueError("交易所账户已停用")
        if account.bind_status != BindStatus.SUCCESS:
            raise ValueError("请先校验并启用交易所账户")
        if require_writable and account.read_only:
            raise ValueError("当前账户为只读模式，无法执行交易")
        return account

    def _build_okx_client(self, account: ExchangeAccountModel) -> ApiService:
        api_key = self._exchange_account_service.decrypt(account.api_key)
        api_secret = self._exchange_account_service.decrypt(account.api_secret)
        passphrase = self._exchange_account_service.decrypt(account.passphrase) if account.passphrase else None
        if not passphrase:
            raise ValueError("OKX 账户缺少 Passphrase")
        return ApiService(
            API_KEY=api_key,
            SECRET_KEY=api_secret,
            PASSPHRASE=passphrase,
            IS_SANDBOX=trading_sandbox_mode(),
        )

    def _resolve_trade_action(self, trade_action: str, inst_type: str) -> Tuple[str, Optional[str], Optional[bool]]:
        if inst_type == "SPOT":
            if trade_action not in {"buy", "sell"}:
                raise ValueError("现货仅支持买入或卖出")
            return trade_action, None, None

        mapping = {
            "open_long": ("buy", "long", False),
            "open_short": ("sell", "short", False),
            "close_long": ("sell", "long", True),
            "close_short": ("buy", "short", True),
        }
        result = mapping.get(trade_action)
        if not result:
            raise ValueError("合约仅支持开多、开空、平多、平空")
        return result

    def _normalize_order_book_side(self, rows: Optional[List[List[str]]]) -> List[Dict]:
        result = []
        for item in rows or []:
            if not item:
                continue
            result.append(
                {
                    "price": str(item[0]),
                    "size": str(item[1]) if len(item) > 1 else "0",
                }
            )
        return result

    def _normalize_balances(self, raw_balances: List[Dict]) -> List[Dict]:
        details: List[Dict] = []
        for item in raw_balances or []:
            details.extend(item.get("details") or [])

        result = []
        for item in details:
            if self._to_decimal(item.get("eq")) <= 0 and self._to_decimal(item.get("availBal")) <= 0:
                continue
            result.append(
                {
                    "ccy": item.get("ccy", ""),
                    "availBal": item.get("availBal", "0"),
                    "frozenBal": item.get("frozenBal", "0"),
                    "eq": item.get("eq", "0"),
                    "eqUsd": item.get("eqUsd", "0"),
                }
            )

        result.sort(key=lambda row: self._to_decimal(row.get("eqUsd")), reverse=True)
        return result[:8]

    def _normalize_positions(self, raw_positions: List[Dict]) -> List[Dict]:
        result = []
        for item in raw_positions or []:
            pos = item.get("pos", "0")
            if self._to_decimal(pos) == 0:
                continue
            result.append(
                {
                    "instId": item.get("instId", ""),
                    "instType": item.get("instType") or None,
                    "posSide": item.get("posSide", "net"),
                    "pos": pos,
                    "availPos": item.get("availPos") or None,
                    "avgPx": item.get("avgPx") or None,
                    "markPx": item.get("markPx") or None,
                    "upl": item.get("upl") or None,
                    "lever": item.get("lever") or None,
                    "mgnMode": item.get("mgnMode") or None,
                }
            )
        return result[:10]

    def _to_decimal(self, value: Optional[str]) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")
