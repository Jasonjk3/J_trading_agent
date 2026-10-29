#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
收益分析服务层
"""
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.inner_models.exchange_account_model import (
    ExchangeAccountModel,
    ExchangeCode,
    BindStatus
)
from app.v1.crud.exchange_account_crud import get_exchange_accounts
from app.v1.services.exchange_account_service import ExchangeAccountService
from app.v1.schemas.analytics_schema import (
    ProfitSummaryResponse,
    ProfitTrendPoint,
    ProfitTrendResponse,
    ProfitByExchangeItem,
    ProfitByExchangeResponse,
    ProfitBySymbolItem,
    ProfitBySymbolResponse,
    WalletBalanceItem,
    WalletBalanceResponse,
)


from app.v1.services.analytics_queries import AnalyticsQueries
from app.v1.services.query_contracts import trading_sandbox_mode


class AnalyticsService(AnalyticsQueries):
    """收益分析服务类"""

    def __init__(self):
        self._exchange_account_service = ExchangeAccountService()

    async def _fetch_positions_history(
        self,
        account: ExchangeAccountModel,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """从交易所获取历史持仓数据"""
        api_key = self._exchange_account_service.decrypt(account.api_key)
        api_secret = self._exchange_account_service.decrypt(account.api_secret)
        passphrase = self._exchange_account_service.decrypt(account.passphrase) if account.passphrase else None

        if account.exchange == ExchangeCode.OKX:
            return await self._fetch_okx_positions_history(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                from_date=from_date,
                to_date=to_date,
                symbol=symbol
            )

        raise ValueError("不支持的交易所")

    async def _fetch_okx_positions_history(
        self,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str],
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """从OKX获取历史持仓数据"""
        if not passphrase:
            raise ValueError("OKX账户缺少Passphrase")

        try:
            from lib.okx.okx_api import ApiService
            client = ApiService(
                API_KEY=api_key,
                SECRET_KEY=api_secret,
                PASSPHRASE=passphrase,
                IS_SANDBOX=trading_sandbox_mode(),
            )

            params = {}
            if symbol:
                params["inst_id"] = symbol

            okx_history = await client.get_positions_history(**params)

            result = []
            for pos in okx_history:
                pos_data = pos if isinstance(pos, dict) else {}
                
                close_time = pos_data.get("uTime", "")
                close_time_str = None
                if close_time:
                    try:
                        timestamp_ms = int(close_time)
                        close_dt = datetime.fromtimestamp(timestamp_ms / 1000)
                        close_time_str = close_dt.isoformat()
                        
                        if from_date:
                            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
                            if close_dt < from_dt:
                                continue
                        if to_date:
                            to_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
                            if close_dt >= to_dt:
                                continue
                    except (ValueError, TypeError):
                        pass

                result.append({
                    "symbol": pos_data.get("instId", ""),
                    "currency": pos_data.get("ccy"),
                    "realizedPnl": pos_data.get("realizedPnl"),
                    "fundingFee": pos_data.get("fundingFee"),
                    "liqPenalty": pos_data.get("liqPenalty"),
                    "settledPnl": pos_data.get("settledPnl"),
                    "pnl": pos_data.get("pnl", "0"),
                    "fee": pos_data.get("fee", "0"),
                    "closeTime": close_time_str
                })

            return result

        except Exception as e:
            logger.error(f"获取OKX历史持仓失败: {e}")
            raise

    async def _fetch_account_balance(
        self,
        account: ExchangeAccountModel
    ) -> Dict[str, Any]:
        """从交易所获取账户余额"""
        api_key = self._exchange_account_service.decrypt(account.api_key)
        api_secret = self._exchange_account_service.decrypt(account.api_secret)
        passphrase = self._exchange_account_service.decrypt(account.passphrase) if account.passphrase else None

        if account.exchange == ExchangeCode.OKX:
            return await self._fetch_okx_balance(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                exchange_code=account.exchange.value
            )

        raise ValueError("不支持的交易所")

    async def _fetch_okx_balance(
        self,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str],
        exchange_code: str
    ) -> Dict[str, Any]:
        """从OKX获取账户余额"""
        if not passphrase:
            raise ValueError("OKX账户缺少Passphrase")

        try:
            from lib.okx.okx_api import ApiService
            client = ApiService(
                API_KEY=api_key,
                SECRET_KEY=api_secret,
                PASSPHRASE=passphrase,
                IS_SANDBOX=trading_sandbox_mode(),
            )

            balance_data = await client.get_account_balance()

            if not balance_data:
                raise ValueError("交易所未返回账户余额")

            account_data = balance_data[0] if balance_data else {}
            total_eq_usd = account_data.get("totalEq", "0")
            details = account_data.get("details", [])
            u_time = account_data.get("uTime", "")

            updated_at = None
            if u_time:
                try:
                    timestamp_ms = int(u_time)
                    updated_at = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
                except (ValueError, TypeError):
                    pass

            balances = []
            for detail in details:
                ccy = detail.get("ccy", "")
                avail_bal = detail.get("availBal", "0")
                frozen_bal = detail.get("frozenBal", "0")
                eq = detail.get("eq", "0")
                eq_usd = detail.get("eqUsd", "0")

                if float(eq) > 0 or float(avail_bal) > 0:
                    balances.append({
                        "currency": ccy,
                        "available": avail_bal,
                        "frozen": frozen_bal,
                        "total": eq,
                        "eqUsd": eq_usd
                    })

            balances.sort(key=lambda x: float(x.get("eqUsd", "0")), reverse=True)

            return {
                "totalEqUsd": str(Decimal(total_eq_usd).quantize(Decimal("0.01"))),
                "balances": balances,
                "exchange": exchange_code,
                "updatedAt": updated_at
            }

        except Exception as e:
            logger.error(f"获取OKX账户余额失败: {e}")
            raise
