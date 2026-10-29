#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
实盘交易执行器

负责将 TradingDecisionAgent 的决策结果转换为真实交易所订单，
并记录操作结果和收益变化。
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from uuid import uuid4

from loguru import logger
from trader.risk_kernel import HardRiskPolicy, RiskKernel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lib.okx.okx_trading_service import OkxTradingService
from lib.okx.okx_market_service import OkxMarketService
from models.inner_models.exchange_account_model import ExchangeAccountModel, ExchangeCode
from models.inner_models.trading_agent_model import (
    TradingAgentModel,
    OperationType,
    OperationResult,
)
from models.inner_models.trader_state_model import TraderExecutionEventModel
from app.v1.crud.trading_agent_crud import (
    create_agent_operation,
    create_agent_profit_record,
)
from app.v1.crud.exchange_account_crud import get_exchange_account_by_id


@dataclass
class LiveAccountSnapshot:
    """实盘账户快照"""
    timestamp: datetime
    prices: Dict[str, Decimal]
    equity: Decimal
    available_balance: Decimal
    positions: List[Dict[str, Any]]
    pending_orders: List[Dict[str, Any]] = field(default_factory=list)
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取指定交易对的持仓"""
        for pos in self.positions:
            if pos.get("instId") == symbol or pos.get("symbol") == symbol:
                return pos
        return None


def calc_unrealized_summary(positions: List[Dict[str, Any]]) -> Tuple[Decimal, Decimal]:
    """汇总持仓未实现盈亏及加权收益率(%)"""
    total_upl = Decimal("0")
    total_margin = Decimal("0")
    weighted_ratio_sum = Decimal("0")

    for pos in positions:
        try:
            pos_qty = float(pos.get("pos", 0) or 0)
        except (TypeError, ValueError):
            pos_qty = 0
        if pos_qty == 0:
            continue
        upl = Decimal(str(pos.get("upl", 0) or 0))
        margin = Decimal(str(pos.get("margin", 0) or 0))
        upl_ratio = Decimal(str(pos.get("uplRatio", 0) or 0))
        total_upl += upl
        total_margin += margin
        weighted_ratio_sum += margin * upl_ratio

    if total_margin > 0:
        rate = (weighted_ratio_sum / total_margin) * Decimal("100")
    else:
        rate = Decimal("0")

    return total_upl, rate.quantize(Decimal("0.01"))


@dataclass
class LiveAccount:
    """实盘账户状态（兼容 TradingDecisionAgent 接口）"""
    balance: Decimal
    equity: Decimal
    positions: List[Dict[str, Any]]
    leverage: Decimal = Decimal("1")
    trades: List[Any] = None
    
    def __post_init__(self):
        if self.trades is None:
            self.trades = []
    
    def get_all_positions(self) -> List[Any]:
        """返回所有持仓（兼容虚拟账户接口）"""
        return [LivePosition(p) for p in self.positions if float(p.get("pos", 0)) > 0]
    
    def get_position(self, symbol: str) -> Optional["LivePosition"]:
        """获取指定交易对的持仓"""
        for pos in self.positions:
            if (pos.get("instId") == symbol or pos.get("symbol") == symbol) and float(pos.get("pos", 0)) > 0:
                return LivePosition(pos)
        return None


class LivePosition:
    """实盘持仓（兼容虚拟账户接口）"""
    
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.symbol = raw.get("instId", "")
        self.side = raw.get("posSide", "long")
        self.quantity = Decimal(str(raw.get("pos", 0)))
        self.entry_price = Decimal(str(raw.get("avgPx", 0)))
        self.entry_time = None
        self.unrealized_pnl = Decimal(str(raw.get("upl", 0)))
        self.margin_used = Decimal(str(raw.get("margin", 0) or 0))
        self.leverage = Decimal(str(raw.get("lever", 1) or 1))
    
    def get_pnl_percent(self, current_price: Decimal) -> Decimal:
        """计算盈亏百分比"""
        if self.entry_price <= 0:
            return Decimal("0")
        if self.side == "long":
            return (current_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - current_price) / self.entry_price * 100


class LiveMarketSnapshot:
    """实盘行情快照（兼容 TradingDecisionAgent 接口）"""
    
    def __init__(self, timestamp: datetime, prices: Dict[str, Decimal], klines: Dict[str, List] = None):
        self.timestamp = timestamp
        self.prices = prices
        self.klines = klines or {}


class LiveTradingExecutor:
    """实盘交易执行器"""
    
    ACTION_TO_OPERATION_TYPE = {
        "open_long": OperationType.OPEN_LONG,
        "open_short": OperationType.OPEN_SHORT,
        "add_long": OperationType.ADJUST,
        "add_short": OperationType.ADJUST,
        "reduce_long": OperationType.ADJUST,
        "reduce_short": OperationType.ADJUST,
        "close_long": OperationType.CLOSE_LONG,
        "close_short": OperationType.CLOSE_SHORT,
    }
    
    def __init__(
        self,
        agent: TradingAgentModel,
        exchange_account: ExchangeAccountModel,
        is_sandbox: bool = True,
    ):
        """
        初始化实盘执行器
        
        Args:
            agent: 交易 Agent 模型
            exchange_account: 交易所账户模型
            is_sandbox: 是否使用沙盒环境
        """
        self.agent = agent
        self.exchange_account = exchange_account
        self.is_sandbox = is_sandbox
        
        self.trading_service: Optional[OkxTradingService] = None
        self.market_service: Optional[OkxMarketService] = None
        
        self._last_equity: Optional[Decimal] = None
        self._initial_equity: Optional[Decimal] = None
        self._submitted_intent_ids = set()
        
        self._init_services()
    
    def _init_services(self) -> None:
        """初始化交易所服务"""
        if self.exchange_account.exchange != ExchangeCode.OKX:
            raise ValueError(f"暂不支持交易所: {self.exchange_account.exchange}")
        
        if self.exchange_account.read_only:
            raise ValueError("该账户为只读模式，无法执行交易")
        
        api_key = self.exchange_account.api_key
        api_secret = self.exchange_account.api_secret
        passphrase = self.exchange_account.passphrase
        
        self.trading_service = OkxTradingService(
            api_key=api_key,
            secret_key=api_secret,
            passphrase=passphrase,
            is_sandbox=self.is_sandbox,
        )
        
        self.market_service = OkxMarketService(
            api_key=api_key,
            secret_key=api_secret,
            passphrase=passphrase,
            is_sandbox=self.is_sandbox,
        )
        
        logger.info(
            f"[LiveTradingExecutor] 初始化完成: agent={self.agent.id}, "
            f"exchange={self.exchange_account.exchange}, sandbox={self.is_sandbox}"
        )
    
    async def get_account_snapshot(self, symbols: List[str]) -> LiveAccountSnapshot:
        """
        获取账户快照
        
        Args:
            symbols: 需要获取价格的交易对列表
            
        Returns:
            LiveAccountSnapshot: 账户快照
        """
        account_summary = await self.trading_service.get_account_summary()
        
        prices = {}
        pending_orders: List[Dict[str, Any]] = []
        for symbol in symbols:
            try:
                price = await self.trading_service.get_market_price(symbol)
                if price > 0:
                    prices[symbol] = Decimal(str(price))
            except Exception as e:
                logger.warning(f"[LiveTradingExecutor] 获取 {symbol} 价格失败: {e}")
            try:
                raw_orders = await self.trading_service.get_pending_orders(
                    self._normalize_symbol(symbol)
                )
                for order in raw_orders or []:
                    size = Decimal(str(order.get("sz", 0) or 0))
                    filled = Decimal(str(order.get("accFillSz", 0) or 0))
                    pending_orders.append({
                        "order_id": str(order.get("ordId") or ""),
                        "client_intent_id": order.get("clOrdId") or None,
                        "symbol": symbol,
                        "exchange_symbol": order.get("instId"),
                        "side": order.get("side"),
                        "position_side": order.get("posSide"),
                        "order_type": order.get("ordType"),
                        "limit_price": order.get("px"),
                        "remaining_quantity": str(max(Decimal("0"), size - filled)),
                        "created_at": order.get("cTime"),
                        "expires_at": None,
                        "status": order.get("state") or "live",
                    })
            except Exception as e:
                logger.warning(f"[LiveTradingExecutor] 获取 {symbol} 活动挂单失败: {e}")
        
        equity = Decimal(str(account_summary.get("total_equity", 0)))
        positions = account_summary.get("positions", [])
        
        balance_list = account_summary.get("balance", [])
        available = Decimal("0")
        for b in balance_list:
            available += Decimal(str(b.get("availBal", 0)))
        
        return LiveAccountSnapshot(
            timestamp=datetime.now(),
            prices=prices,
            equity=equity,
            available_balance=available,
            positions=positions,
            pending_orders=pending_orders,
        )
    
    def build_live_account(self, snapshot: LiveAccountSnapshot) -> LiveAccount:
        """构建兼容 TradingDecisionAgent 的账户对象"""
        return LiveAccount(
            balance=snapshot.available_balance,
            equity=snapshot.equity,
            positions=snapshot.positions,
            leverage=Decimal(str((self.agent.strategy_config or {}).get("leverage", 1))),
        )
    
    def build_market_snapshot(self, account_snapshot: LiveAccountSnapshot) -> LiveMarketSnapshot:
        """构建兼容 TradingDecisionAgent 的行情快照"""
        return LiveMarketSnapshot(
            timestamp=account_snapshot.timestamp,
            prices=account_snapshot.prices,
        )
    
    async def execute_decision(
        self,
        session: AsyncSession,
        decision: Dict[str, Any],
        account_snapshot: LiveAccountSnapshot,
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        执行交易决策
        
        Args:
            session: 数据库会话
            decision: TradingDecisionAgent 的决策结果
            account_snapshot: 当前账户快照
            
        Returns:
            Tuple[bool, Optional[str], Optional[Dict]]: (是否成功, 错误信息, 订单结果)
        """
        cancellations = decision.get("cancel_order_intents") or []
        cancellation_results = []
        cancelled_order_ids = set()
        for cancel in cancellations:
            if not isinstance(cancel, dict) or not cancel.get("order_id") or not cancel.get("symbol"):
                continue
            result = await self.trading_service.api.cancel_order(
                inst_id=self._normalize_symbol(str(cancel["symbol"])),
                ord_id=str(cancel["order_id"]),
            )
            sub_code = str((result or {}).get("sCode") or "0")
            if sub_code != "0":
                raise ValueError(
                    f"旧挂单 {cancel['order_id']} 撤销失败，禁止提交替代订单: "
                    f"[{sub_code}] {(result or {}).get('sMsg') or '未知错误'}"
                )
            cancellation_results.append(result)
            cancelled_order_ids.add(str(cancel["order_id"]))
            await self._record_execution_event(
                session,
                event_type="cancelled",
                proposal_id=decision.get("proposal_id"),
                exchange_order_id=str(cancel["order_id"]),
                payload={"request": cancel, "result": result},
            )
        if cancelled_order_ids:
            account_snapshot.pending_orders = [
                item for item in (account_snapshot.pending_orders or [])
                if str(item.get("order_id") or "") not in cancelled_order_ids
            ]

        order_batch = decision.get("order_batch")
        if isinstance(order_batch, list):
            results = []
            errors = []
            for item in order_batch:
                if not isinstance(item, dict):
                    continue
                child = dict(item)
                child.pop("order_batch", None)
                child.setdefault("proposal_id", decision.get("proposal_id"))
                child.setdefault("decision_mode", decision.get("decision_mode"))
                success, error, result = await self.execute_decision(
                    session, child, account_snapshot
                )
                results.append({
                    "clientIntentId": child.get("client_intent_id"),
                    "success": success,
                    "error": error,
                    "order": result,
                })
                if error:
                    errors.append(error)
            return not errors, "; ".join(errors) or None, {
                "proposalId": decision.get("proposal_id"),
                "cancellations": cancellation_results,
                "orders": results,
            }

        action = str(decision.get("action", "hold")).lower()
        
        if action == "hold":
            logger.info(f"[LiveTradingExecutor] 决策为 hold，不执行交易")
            return True, None, {"cancellations": cancellation_results} if cancellation_results else None

        if action == "system_error":
            reason = str(decision.get("reason") or "交易决策系统错误")
            error_type = str(decision.get("error_type") or "unknown_system_error")
            signals = list(decision.get("signals") or [])
            await create_agent_operation(
                session=session,
                agent_id=self.agent.id,
                operation_type=OperationType.OTHER,
                symbol=decision.get("symbol"),
                reason=reason,
                result=OperationResult.FAILED,
                chain_of_thought=[
                    {
                        "type": "system_error",
                        "errorType": error_type,
                        "signals": signals,
                    }
                ],
                error_message=reason,
            )
            logger.error(
                f"[LiveTradingExecutor] 决策系统错误，不执行交易: "
                f"error_type={error_type}, reason={reason[:200]}"
            )
            return False, reason, None
        
        symbol = decision.get("symbol")
        if not symbol:
            return False, "决策缺少 symbol 字段", None
        
        okx_symbol = self._normalize_symbol(symbol)
        quantity = decision.get("quantity")
        reason = decision.get("reason", "")
        confidence = decision.get("confidence", 0)
        signals = decision.get("signals", [])
        client_intent_id = str(decision.get("client_intent_id") or "")
        if client_intent_id and (
            client_intent_id in self._submitted_intent_ids
            or await self._intent_already_submitted(session, client_intent_id)
        ):
            return True, None, {"duplicate": True, "clientIntentId": client_intent_id}

        order_type = str(decision.get("order_type") or "market").lower()
        effect, _, position_side = action.partition("_")
        if order_type == "limit" and effect in {"open", "add"}:
            same_direction_orders = []
            for pending in account_snapshot.pending_orders or []:
                pending_symbol = pending.get("exchange_symbol") or pending.get("symbol")
                if self._normalize_symbol(str(pending_symbol or "")) != okx_symbol:
                    continue
                pending_position_side = str(pending.get("position_side") or "").lower()
                if not pending_position_side:
                    pending_side = str(pending.get("side") or "").lower()
                    pending_position_side = "long" if pending_side == "buy" else "short"
                if pending_position_side == position_side:
                    same_direction_orders.append(str(pending.get("order_id") or ""))
            if same_direction_orders:
                return False, (
                    f"{symbol} {position_side} 已有活动挂单 "
                    f"{same_direction_orders}；必须先明确 replace/cancel，禁止重复提交"
                ), None
        
        current_price = account_snapshot.prices.get(symbol) or account_snapshot.prices.get(okx_symbol)
        if not current_price:
            return False, f"无法获取 {symbol} 的当前价格", None

        risk_kernel = RiskKernel.from_strategy_config(self.agent.strategy_config or {})
        risk_evaluation = risk_kernel.evaluate(
            decision,
            self.build_live_account(account_snapshot),
            {**account_snapshot.prices, symbol: current_price},
        )
        decision["risk_evaluation"] = risk_evaluation.to_dict()
        if not risk_evaluation.approved or not risk_evaluation.approved_decision:
            reason = (
                risk_evaluation.violations[0].message
                if risk_evaluation.violations else "硬风险内核拒绝该订单"
            )
            logger.warning(f"[LiveTradingExecutor] RiskKernel 拒绝执行: {reason}")
            return False, reason, None
        quantity = risk_evaluation.approved_decision.get("quantity", quantity)
        decision["quantity"] = quantity
        approved_leverage = float(
            risk_evaluation.approved_decision.get("leverage")
            or decision.get("requested_leverage")
            or 1
        )
        decision["leverage"] = approved_leverage
        
        chain_of_thought = [
            {"step": "decision", "action": action, "confidence": confidence},
            {"step": "signals", "data": signals},
            {"step": "reason", "text": reason},
        ]
        
        operation_type = self.ACTION_TO_OPERATION_TYPE.get(action)
        if not operation_type:
            return False, f"不支持的操作类型: {action}", None
        
        try:
            order_result = await self._place_order(
                action=action,
                symbol=okx_symbol,
                quantity=quantity,
                current_price=float(current_price),
                order_type=order_type,
                limit_price=decision.get("limit_price"),
                leverage=approved_leverage,
                strict_quantity=str(decision.get("decision_mode") or "") == "trader",
            )
            if client_intent_id:
                self._submitted_intent_ids.add(client_intent_id)
            
            order_id = order_result.get("ordId") if order_result else None
            
            await create_agent_operation(
                session=session,
                agent_id=self.agent.id,
                operation_type=operation_type,
                symbol=symbol,
                side="buy" if action in ("open_long", "add_long", "reduce_short", "close_short") else "sell",
                quantity=str(quantity) if quantity else None,
                price=str(current_price),
                reason=reason,
                result=OperationResult.SUCCESS,
                chain_of_thought=chain_of_thought,
                order_id=order_id,
            )
            await self._record_execution_event(
                session,
                event_type="submitted",
                proposal_id=decision.get("proposal_id"),
                client_intent_id=client_intent_id or None,
                exchange_order_id=order_id,
                payload={"decision": decision, "exchangeResult": order_result},
            )
            
            logger.info(
                f"[LiveTradingExecutor] 订单执行成功: "
                f"action={action}, symbol={symbol}, quantity={quantity}, order_id={order_id}"
            )
            
            return True, None, order_result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[LiveTradingExecutor] 订单执行失败: {error_msg}")
            
            await create_agent_operation(
                session=session,
                agent_id=self.agent.id,
                operation_type=operation_type,
                symbol=symbol,
                side="buy" if action in ("open_long", "add_long", "reduce_short", "close_short") else "sell",
                quantity=str(quantity) if quantity else None,
                price=str(current_price),
                reason=reason,
                result=OperationResult.FAILED,
                chain_of_thought=chain_of_thought,
                error_message=error_msg,
            )
            await self._record_execution_event(
                session,
                event_type="rejected",
                proposal_id=decision.get("proposal_id"),
                client_intent_id=client_intent_id or None,
                payload={"decision": decision, "error": error_msg},
            )
            
            return False, error_msg, None

    async def _intent_already_submitted(
        self, session: AsyncSession, client_intent_id: str
    ) -> bool:
        result = await session.execute(
            select(TraderExecutionEventModel.id).where(
                TraderExecutionEventModel.client_intent_id == client_intent_id,
                TraderExecutionEventModel.event_type == "submitted",
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def _record_execution_event(
        session: AsyncSession,
        *,
        event_type: str,
        payload: Dict[str, Any],
        proposal_id: Optional[str] = None,
        client_intent_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
    ) -> None:
        session.add(TraderExecutionEventModel(
            id=str(uuid4()),
            proposal_id=proposal_id,
            client_intent_id=client_intent_id,
            exchange_order_id=exchange_order_id,
            event_type=event_type,
            payload_json=payload,
            occurred_at=datetime.now(),
        ))
        await session.flush()
    
    async def _place_order(
        self,
        action: str,
        symbol: str,
        quantity: Optional[float],
        current_price: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        leverage: float = 1.0,
        strict_quantity: bool = False,
    ) -> Optional[Dict]:
        """
        下单执行
        
        Args:
            action: 操作类型
            symbol: 交易对（OKX 格式）
            quantity: 数量（USD 金额或张数）
            current_price: 当前价格
            
        Returns:
            订单结果
        """
        if order_type not in {"market", "limit"}:
            raise ValueError(f"不支持的订单类型: {order_type}")
        if order_type == "limit" and (limit_price is None or float(limit_price) <= 0):
            raise ValueError("限价单必须提供有效 limit_price")
        strategy_config = self.agent.strategy_config or {}
        if strict_quantity:
            policy = HardRiskPolicy.from_strategy_config(strategy_config)
            min_amount = float(policy.min_order_notional)
            max_amount = float(policy.max_order_notional)
        else:
            min_amount = float(strategy_config.get("minOrderAmount", 100))
            max_amount = float(strategy_config.get("maxOrderAmount", 1000))
        
        if quantity:
            usd_amount = float(quantity) * current_price
        else:
            usd_amount = min_amount
        
        if strict_quantity:
            if usd_amount < min_amount or usd_amount > max_amount:
                raise ValueError(
                    f"RiskKernel 批准数量与执行限额不一致: {usd_amount} not in "
                    f"[{min_amount}, {max_amount}]"
                )
        else:
            usd_amount = max(min_amount, min(max_amount, usd_amount))
        
        max_leverage = float(strategy_config.get("maxLeverage", 10) or 10)
        approved_leverage = max(1.0, min(float(leverage or 1), max_leverage))
        
        await self.trading_service.initialize_trading(
            symbol=symbol,
            leverage=str(approved_leverage),
            mgn_mode="cross",
        )
        
        if action in {"open_long", "add_long"}:
            return await self.trading_service.open_long_position(
                symbol=symbol,
                usd_amount=usd_amount,
                price=float(limit_price) if order_type == "limit" else None,
                order_type=order_type,
            )
        elif action in {"open_short", "add_short"}:
            return await self.trading_service.open_short_position(
                symbol=symbol,
                usd_amount=usd_amount,
                price=float(limit_price) if order_type == "limit" else None,
                order_type=order_type,
            )
        elif action in {"reduce_long", "close_long"}:
            return await self.trading_service.close_position(
                symbol=symbol,
                pos_side="long",
                price=float(limit_price) if order_type == "limit" else None,
                order_type=order_type,
                quantity=quantity if action == "reduce_long" else None,
            )
        elif action in {"reduce_short", "close_short"}:
            return await self.trading_service.close_position(
                symbol=symbol,
                pos_side="short",
                price=float(limit_price) if order_type == "limit" else None,
                order_type=order_type,
                quantity=quantity if action == "reduce_short" else None,
            )
        else:
            raise ValueError(f"不支持的操作: {action}")
    
    async def record_profit(
        self,
        session: AsyncSession,
        account_snapshot: LiveAccountSnapshot,
    ) -> None:
        """
        记录收益变化
        
        Args:
            session: 数据库会话
            account_snapshot: 当前账户快照
        """
        current_equity = account_snapshot.equity
        
        if self._initial_equity is None:
            self._initial_equity = current_equity
            self._last_equity = current_equity
            return
        
        period_profit = current_equity - self._last_equity
        cumulative_profit = current_equity - self._initial_equity
        total_upl, upl_rate = calc_unrealized_summary(account_snapshot.positions)
        
        await create_agent_profit_record(
            session=session,
            agent_id=self.agent.id,
            record_time=account_snapshot.timestamp,
            value=str(period_profit),
            cumulative=str(cumulative_profit),
            equity=str(current_equity),
            unrealized_pnl=str(total_upl),
            unrealized_pnl_rate=str(upl_rate),
        )
        
        self._last_equity = current_equity
        
        logger.debug(
            f"[LiveTradingExecutor] 收益记录: "
            f"unrealized={total_upl} ({upl_rate}%), equity={current_equity}"
        )
    
    async def check_risk(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        风险检查
        
        Args:
            symbols: 需要检查的交易对列表
            
        Returns:
            风险检查结果
        """
        if symbols:
            results = {}
            for symbol in symbols:
                okx_symbol = self._normalize_symbol(symbol)
                result = await self.trading_service.risk_management_check(okx_symbol)
                results[symbol] = result
            return results
        else:
            return await self.trading_service.risk_management_check()
    
    async def cancel_all_pending_orders(self, symbol: str) -> List[Dict]:
        """撤销指定交易对的所有未成交订单"""
        okx_symbol = self._normalize_symbol(symbol)
        return await self.trading_service.cancel_all_orders(okx_symbol)
    
    async def close_all_positions(self, symbol: str) -> List[Dict]:
        """平掉指定交易对的所有持仓"""
        okx_symbol = self._normalize_symbol(symbol)
        results = []
        
        positions = await self.trading_service.get_position_info(okx_symbol)
        for pos in positions:
            pos_side = pos.get("posSide")
            if pos_side and float(pos.get("pos", 0)) > 0:
                try:
                    result = await self.trading_service.close_position(
                        symbol=okx_symbol,
                        pos_side=pos_side,
                        order_type="market",
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"[LiveTradingExecutor] 平仓失败 {pos_side}: {e}")
        
        return results
    
    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        标准化交易对格式为 OKX 格式

        支持的输入格式：
        - BTCUSDT -> BTC-USDT-SWAP
        - BTC-USDT -> BTC-USDT-SWAP
        - BTC-USDT-SWAP -> BTC-USDT-SWAP
        - BTC -> BTC-USDT-SWAP
        """
        symbol = symbol.upper().strip()

        if symbol.endswith("-SWAP"):
            return symbol

        if "-" in symbol:
            return f"{symbol}-SWAP"

        common_bases = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "LINK", "UNI", "AVAX",
                        "MATIC", "LTC", "BCH", "ETC", "ATOM", "FIL", "APT", "ARB", "OP", "SUI"]

        for base in common_bases:
            if symbol.startswith(base) and symbol != base:
                quote = symbol[len(base):]
                if quote in ["USDT", "USDC", "USD", "BTC", "ETH"]:
                    return f"{base}-{quote}-SWAP"

        if symbol.endswith("USDT"):
            base = symbol[:-4]
            if base:
                return f"{base}-USDT-SWAP"
        elif symbol.endswith("USDC"):
            base = symbol[:-4]
            if base:
                return f"{base}-USDC-SWAP"
        elif symbol.endswith("USD"):
            base = symbol[:-3]
            if base:
                return f"{base}-USD-SWAP"

        return f"{symbol}-USDT-SWAP"


async def create_live_executor(
    session: AsyncSession,
    agent: TradingAgentModel,
    is_sandbox: bool = None,
) -> LiveTradingExecutor:
    """
    创建实盘执行器的工厂函数
    
    Args:
        session: 数据库会话
        agent: 交易 Agent 模型
        is_sandbox: 是否使用沙盒环境
        
    Returns:
        LiveTradingExecutor: 实盘执行器实例
    """
    if not agent.exchange_account_id:
        raise ValueError("Agent 未绑定交易所账户")
    
    exchange_account = await get_exchange_account_by_id(session, agent.exchange_account_id)
    if not exchange_account:
        raise ValueError(f"交易所账户不存在: {agent.exchange_account_id}")
    if exchange_account.user_id != agent.user_id:
        raise ValueError("交易所账户不属于当前 Agent 用户")
    if is_sandbox is None:
        from app.v1.services.query_contracts import trading_sandbox_mode
        is_sandbox = trading_sandbox_mode()
    
    return LiveTradingExecutor(
        agent=agent,
        exchange_account=exchange_account,
        is_sandbox=is_sandbox,
    )
