#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""模拟盘业务服务：所有资产均为虚拟资产，与实盘完全隔离。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.schemas.paper_trading_schema import (
    CreatePaperAccountRequest,
    CreatePaperDecisionRequest,
    CreatePaperTradeRequest,
)
from models.inner_models.paper_trading_model import (
    PaperAccountStatus,
    PaperAccountType,
    PaperDecisionModel,
    PaperEquityRecordModel,
    PaperPositionModel,
    PaperTradeModel,
    PaperTradeSide,
    PaperTradingAccountModel,
)
from models.inner_models.trading_agent_model import TradingAgentModel


MONEY = Decimal("0.00000001")
QUANTITY = Decimal("0.000000000001")


class PaperTradingError(ValueError):
    pass


class PaperTradingService:
    @staticmethod
    def _d(value: Any) -> Decimal:
        return Decimal(str(value or 0))

    async def _owned_account(
        self, session: AsyncSession, account_id: str, user_id: str, *, lock: bool = False
    ) -> PaperTradingAccountModel | None:
        query = select(PaperTradingAccountModel).where(
            PaperTradingAccountModel.id == account_id,
            PaperTradingAccountModel.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        return (await session.execute(query)).scalar_one_or_none()

    async def ensure_human_account(
        self, session: AsyncSession, user_id: str
    ) -> PaperTradingAccountModel:
        account = (await session.execute(
            select(PaperTradingAccountModel).where(
                PaperTradingAccountModel.user_id == user_id,
                PaperTradingAccountModel.account_type == PaperAccountType.HUMAN,
            ).limit(1).with_for_update()
        )).scalar_one_or_none()
        if account:
            return account
        capital = Decimal("250000")
        account = PaperTradingAccountModel(
            id=str(uuid.uuid4()), user_id=user_id, account_type=PaperAccountType.HUMAN,
            name="我的账户", status=PaperAccountStatus.RUNNING,
            initial_capital=capital, cash_balance=capital, realized_pnl=Decimal("0"),
        )
        session.add(account)
        await session.flush()
        session.add(PaperEquityRecordModel(
            id=str(uuid.uuid4()), account_id=account.id, equity=capital,
            return_rate=Decimal("0"), recorded_at=datetime.now(),
        ))
        await session.flush()
        return account

    async def initialize_human_account(self, session: AsyncSession, user_id: str):
        from models.inner_models.user_model import UserModel
        user = (await session.execute(select(UserModel).where(
            UserModel.id == user_id, UserModel.is_active == True).with_for_update())).scalar_one_or_none()
        if user is None:
            raise PaperTradingError("当前用户不可用")
        return await self.ensure_human_account(session, user_id)

    async def create_agent_account(
        self, session: AsyncSession, user_id: str, request: CreatePaperAccountRequest
    ) -> PaperTradingAccountModel:
        agent = (await session.execute(select(TradingAgentModel).where(
            TradingAgentModel.id == request.agentId,
            TradingAgentModel.user_id == user_id,
        ))).scalar_one_or_none()
        if not agent:
            raise PaperTradingError("Agent 不存在或不属于当前用户")
        duplicate = (await session.execute(select(PaperTradingAccountModel.id).where(
            PaperTradingAccountModel.user_id == user_id,
            PaperTradingAccountModel.source_agent_id == agent.id,
        ))).scalar_one_or_none()
        if duplicate:
            raise PaperTradingError("该 Agent 已添加到模拟盘")
        capital = self._d(request.initialCapital).quantize(MONEY)
        account = PaperTradingAccountModel(
            id=str(uuid.uuid4()), user_id=user_id, source_agent_id=agent.id,
            account_type=PaperAccountType.AGENT, name=agent.name,
            status=PaperAccountStatus.RUNNING, initial_capital=capital,
            cash_balance=capital, realized_pnl=Decimal("0"),
        )
        session.add(account)
        await session.flush()
        session.add(PaperEquityRecordModel(
            id=str(uuid.uuid4()), account_id=account.id, equity=capital,
            return_rate=Decimal("0"), recorded_at=datetime.now(),
        ))
        await session.flush()
        return account

    async def set_status(
        self, session: AsyncSession, account_id: str, user_id: str, status: PaperAccountStatus
    ) -> PaperTradingAccountModel:
        account = await self._owned_account(session, account_id, user_id, lock=True)
        if not account:
            raise PaperTradingError("模拟账户不存在")
        if account.account_type == PaperAccountType.HUMAN:
            raise PaperTradingError("自主账户无需暂停")
        account.status = status
        account.updated_at = datetime.now()
        await session.flush()
        return account

    async def delete_account(self, session: AsyncSession, account_id: str, user_id: str) -> None:
        account = await self._owned_account(session, account_id, user_id, lock=True)
        if not account:
            raise PaperTradingError("模拟账户不存在")
        if account.account_type == PaperAccountType.HUMAN:
            raise PaperTradingError("自主账户不能删除")
        for model in (PaperPositionModel, PaperDecisionModel, PaperTradeModel, PaperEquityRecordModel):
            rows = (await session.execute(select(model).where(model.account_id == account.id))).scalars().all()
            for row in rows:
                await session.delete(row)
        await session.delete(account)
        await session.flush()

    async def _positions(self, session: AsyncSession, account_id: str) -> list[PaperPositionModel]:
        return list((await session.execute(select(PaperPositionModel).where(
            PaperPositionModel.account_id == account_id,
            PaperPositionModel.quantity > 0,
        ).order_by(PaperPositionModel.symbol))).scalars().all())

    async def _equity(self, session: AsyncSession, account: PaperTradingAccountModel) -> Decimal:
        positions = await self._positions(session, account.id)
        market_value = sum((self._d(p.quantity) * self._d(p.last_price) for p in positions), Decimal("0"))
        return (self._d(account.cash_balance) + market_value).quantize(MONEY)

    async def _record_equity(self, session: AsyncSession, account: PaperTradingAccountModel) -> Decimal:
        equity = await self._equity(session, account)
        initial = self._d(account.initial_capital)
        rate = ((equity - initial) / initial * 100) if initial else Decimal("0")
        session.add(PaperEquityRecordModel(
            id=str(uuid.uuid4()), account_id=account.id, recorded_at=datetime.now(),
            equity=equity, return_rate=rate.quantize(Decimal("0.000001")),
        ))
        await session.flush()
        return equity

    async def execute_trade(
        self, session: AsyncSession, account_id: str, user_id: str,
        request: CreatePaperTradeRequest, decision_id: str | None = None,
    ) -> PaperTradeModel:
        account = await self._owned_account(session, account_id, user_id, lock=True)
        if not account:
            raise PaperTradingError("模拟账户不存在")
        if account.status != PaperAccountStatus.RUNNING:
            raise PaperTradingError("账户已暂停，请先继续运行")
        symbol = request.symbol.upper().replace("/", "-")
        price = self._d(request.price).quantize(MONEY)
        amount = self._d(request.amount).quantize(MONEY)
        if price <= 0:
            raise PaperTradingError("未获取到有效的市场价格")
        quantity = (amount / price).quantize(QUANTITY, rounding=ROUND_DOWN)
        if quantity <= 0:
            raise PaperTradingError("交易数量过小")
        position = (await session.execute(select(PaperPositionModel).where(
            PaperPositionModel.account_id == account.id,
            PaperPositionModel.symbol == symbol,
        ).with_for_update())).scalar_one_or_none()
        realized = Decimal("0")
        side = PaperTradeSide(request.side)
        if side == PaperTradeSide.BUY:
            if self._d(account.cash_balance) < amount:
                raise PaperTradingError("可用模拟资金不足")
            old_qty = self._d(position.quantity) if position else Decimal("0")
            old_cost = old_qty * (self._d(position.average_price) if position else Decimal("0"))
            if not position:
                position = PaperPositionModel(
                    id=str(uuid.uuid4()), account_id=account.id, symbol=symbol,
                    quantity=Decimal("0"), average_price=Decimal("0"), last_price=price,
                    realized_pnl=Decimal("0"),
                )
                session.add(position)
            position.quantity = old_qty + quantity
            position.average_price = ((old_cost + amount) / position.quantity).quantize(MONEY)
            account.cash_balance = self._d(account.cash_balance) - amount
        else:
            if not position or self._d(position.quantity) < quantity:
                raise PaperTradingError("可卖持仓不足")
            realized = ((price - self._d(position.average_price)) * quantity).quantize(MONEY)
            position.quantity = self._d(position.quantity) - quantity
            position.realized_pnl = self._d(position.realized_pnl) + realized
            account.cash_balance = self._d(account.cash_balance) + amount
            account.realized_pnl = self._d(account.realized_pnl) + realized
        position.last_price = price
        position.updated_at = datetime.now()
        account.updated_at = datetime.now()
        trade = PaperTradeModel(
            id=str(uuid.uuid4()), account_id=account.id, decision_id=decision_id,
            symbol=symbol, side=side, price=price, quantity=quantity,
            amount=amount, realized_pnl=realized, executed_at=datetime.now(),
        )
        session.add(trade)
        await session.flush()
        await self._record_equity(session, account)
        return trade

    async def create_decision(
        self, session: AsyncSession, account_id: str, user_id: str,
        request: CreatePaperDecisionRequest,
    ) -> PaperDecisionModel:
        account = await self._owned_account(session, account_id, user_id)
        if not account:
            raise PaperTradingError("模拟账户不存在")
        decision = PaperDecisionModel(
            id=str(uuid.uuid4()), account_id=account.id, source_agent_id=account.source_agent_id,
            symbol=request.symbol.upper().replace("/", "-"), action=request.action,
            title=request.title, summary=request.summary, reasoning=request.reasoning,
            reference_price=self._d(request.referencePrice) if request.referencePrice else None,
            confidence=self._d(request.confidence) if request.confidence is not None else None,
            result=request.result, created_at=datetime.now(),
        )
        session.add(decision)
        await session.flush()
        return decision

    async def list_positions(self, session: AsyncSession, account_id: str, user_id: str) -> list[dict]:
        account = await self._owned_account(session, account_id, user_id)
        if not account:
            raise PaperTradingError("模拟账户不存在")
        result = []
        for item in await self._positions(session, account.id):
            pnl = (self._d(item.last_price) - self._d(item.average_price)) * self._d(item.quantity)
            result.append({
                "id": item.id, "symbol": item.symbol, "quantity": float(item.quantity),
                "averagePrice": float(item.average_price), "lastPrice": float(item.last_price),
                "unrealizedPnl": float(pnl), "realizedPnl": float(item.realized_pnl),
            })
        return result

    async def list_trades(self, session: AsyncSession, account_id: str, user_id: str, limit: int = 50) -> list[dict]:
        if not await self._owned_account(session, account_id, user_id):
            raise PaperTradingError("模拟账户不存在")
        rows = (await session.execute(select(PaperTradeModel).where(
            PaperTradeModel.account_id == account_id,
        ).order_by(desc(PaperTradeModel.executed_at)).limit(limit))).scalars().all()
        return [self.trade_to_response(row) for row in rows]

    async def list_decisions(self, session: AsyncSession, account_id: str, user_id: str, limit: int = 50) -> list[dict]:
        if not await self._owned_account(session, account_id, user_id):
            raise PaperTradingError("模拟账户不存在")
        rows = (await session.execute(select(PaperDecisionModel).where(
            PaperDecisionModel.account_id == account_id,
        ).order_by(desc(PaperDecisionModel.created_at)).limit(limit))).scalars().all()
        return [self.decision_to_response(row) for row in rows]

    @staticmethod
    def trade_to_response(row: PaperTradeModel) -> dict:
        return {
            "id": row.id, "symbol": row.symbol, "side": row.side.value,
            "price": float(row.price), "quantity": float(row.quantity),
            "amount": float(row.amount), "realizedPnl": float(row.realized_pnl),
            "executedAt": row.executed_at.isoformat(),
        }

    @staticmethod
    def decision_to_response(row: PaperDecisionModel) -> dict:
        return {
            "id": row.id, "symbol": row.symbol, "action": row.action,
            "title": row.title, "summary": row.summary, "reasoning": row.reasoning,
            "referencePrice": float(row.reference_price) if row.reference_price is not None else None,
            "confidence": float(row.confidence) if row.confidence is not None else None,
            "result": row.result, "createdAt": row.created_at.isoformat(),
        }

    async def dashboard(self, session: AsyncSession, user_id: str, range_name: str = "30D", *, ensure_account: bool = False) -> dict:
        if ensure_account:
            await self.ensure_human_account(session, user_id)
        accounts = list((await session.execute(select(PaperTradingAccountModel).where(
            PaperTradingAccountModel.user_id == user_id,
        ).order_by(PaperTradingAccountModel.created_at))).scalars().all())
        days = {"7D": 7, "30D": 30, "90D": 90}.get(range_name.upper())
        since = datetime.now() - timedelta(days=days) if days else None
        account_items, curves = [], []
        total_equity = Decimal("0")
        total_initial = Decimal("0")
        total_realized = Decimal("0")
        wins = trades_total = 0
        max_drawdown = Decimal("0")
        activity_items: list[dict] = []
        for account in accounts:
            equity = await self._equity(session, account)
            positions = await self._positions(session, account.id)
            trade_stats = (await session.execute(select(
                func.count(PaperTradeModel.id),
                func.sum(case((PaperTradeModel.realized_pnl > 0, 1), else_=0)),
            ).where(
                PaperTradeModel.account_id == account.id,
                PaperTradeModel.side == PaperTradeSide.SELL,
            ))).one()
            account_trades = int(trade_stats[0] or 0)
            account_wins = int(trade_stats[1] or 0)
            recent_trades = (await session.execute(select(PaperTradeModel).where(
                PaperTradeModel.account_id == account.id,
            ).order_by(desc(PaperTradeModel.executed_at)).limit(3))).scalars().all()
            for trade in recent_trades:
                asset = trade.symbol.split("-")[0]
                side_label = "买入" if trade.side == PaperTradeSide.BUY else "卖出"
                activity_items.append({
                    "id": trade.id, "type": "trade", "accountId": account.id,
                    "accountName": account.name, "title": f"{account.name} {side_label} {asset}",
                    "detail": f"{float(trade.quantity):g} {asset} · ¥{float(trade.amount):,.2f}",
                    "occurredAt": trade.executed_at.isoformat(),
                })
            recent_decisions = (await session.execute(select(PaperDecisionModel).where(
                PaperDecisionModel.account_id == account.id,
            ).order_by(desc(PaperDecisionModel.created_at)).limit(3))).scalars().all()
            for decision in recent_decisions:
                if decision.result == "已成交":
                    continue
                activity_items.append({
                    "id": decision.id, "type": "decision", "accountId": account.id,
                    "accountName": account.name, "title": f"{account.name} · {decision.action}",
                    "detail": decision.summary or decision.symbol,
                    "occurredAt": decision.created_at.isoformat(),
                })
            rate = ((equity - self._d(account.initial_capital)) / self._d(account.initial_capital) * 100) if account.initial_capital else Decimal("0")
            strategy = "自主交易"
            if account.source_agent_id:
                agent = (await session.execute(select(TradingAgentModel).where(TradingAgentModel.id == account.source_agent_id))).scalar_one_or_none()
                mode = ((agent.strategy_config or {}).get("marketMode") if agent else None)
                strategy = {"trend_only": "趋势跟随", "range_only": "均值回归"}.get(mode, "自适应策略")
            account_items.append({
                "id": account.id, "sourceAgentId": account.source_agent_id,
                "name": account.name, "kind": account.account_type.value,
                "status": account.status.value, "strategy": strategy,
                "currency": account.currency, "initialCapital": float(account.initial_capital),
                "cashBalance": float(account.cash_balance), "equity": float(equity),
                "returnRate": float(rate), "positionCount": len(positions),
                "winRate": (account_wins / account_trades * 100) if account_trades else None,
            })
            query = select(PaperEquityRecordModel).where(PaperEquityRecordModel.account_id == account.id)
            if since:
                query = query.where(PaperEquityRecordModel.recorded_at >= since)
            records = list((await session.execute(query.order_by(PaperEquityRecordModel.recorded_at))).scalars().all())
            if not records:
                records = [PaperEquityRecordModel(recorded_at=datetime.now(), equity=equity, return_rate=rate)]
            range_start_equity = self._d(records[0].equity) or Decimal("1")
            peak = Decimal("0")
            normalized_points = []
            for row in records:
                point_equity = self._d(row.equity)
                peak = max(peak, point_equity)
                if peak > 0:
                    max_drawdown = max(max_drawdown, (peak - point_equity) / peak * 100)
                normalized_points.append({
                    "time": row.recorded_at.isoformat(),
                    "value": float((point_equity - range_start_equity) / range_start_equity * 100),
                })
            curves.append({
                "accountId": account.id, "name": account.name,
                "points": normalized_points,
            })
            total_equity += equity
            total_initial += self._d(account.initial_capital)
            today_realized = (await session.execute(select(func.sum(PaperTradeModel.realized_pnl)).where(
                PaperTradeModel.account_id == account.id,
                PaperTradeModel.executed_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            ))).scalar_one()
            total_realized += self._d(today_realized)
            trades_total += account_trades
            wins += account_wins
        total_rate = ((total_equity - total_initial) / total_initial * 100) if total_initial else Decimal("0")
        return {
            "summary": {
                "totalEquity": float(total_equity), "totalReturnRate": float(total_rate),
                "totalPnl": float(total_equity - total_initial), "todayPnl": float(total_realized),
                "maxDrawdown": float(max_drawdown),
                "runningAccounts": sum(1 for a in accounts if a.status == PaperAccountStatus.RUNNING),
                "totalAccounts": len(accounts), "winRate": (wins / trades_total * 100) if trades_total else None,
            },
            "accounts": account_items,
            "curves": curves,
            "activities": sorted(
                activity_items, key=lambda item: item["occurredAt"], reverse=True
            )[:8],
        }
