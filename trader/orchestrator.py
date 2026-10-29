"""交易员回合、风险提案与显式提交编排。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Dict, Optional

from trader.event_store import InMemoryTraderEventStore, TraderEventStore
from trader.risk_kernel import HardRiskPolicy, RiskKernel
from trader.schemas import (
    CancelOrderIntent,
    OrderIntent,
    OrderProposal,
    RiskCheckedIntent,
    TraderState,
    TraderTurn,
)
from trader.state_store import InMemoryTraderStateStore, TraderStateStore


TurnGenerator = Callable[[TraderState], Awaitable[TraderTurn]]
StatePreparer = Callable[[TraderState], TraderState]


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


class TraderOrchestrator:
    """加载状态、执行一个模型回合、提交新状态并记录审计事件。"""

    def __init__(
        self,
        session_id: str,
        *,
        state_store: Optional[TraderStateStore] = None,
        event_store: Optional[TraderEventStore] = None,
        execution_mode: str = "shadow",
    ) -> None:
        if execution_mode not in {"shadow", "live"}:
            raise ValueError("traderConfig.executionMode 只允许 shadow 或 live")
        self.session_id = session_id
        self.state_store = state_store or InMemoryTraderStateStore()
        self.event_store = event_store or InMemoryTraderEventStore()
        self.execution_mode = execution_mode

    async def run_turn(
        self,
        *,
        as_of: Any,
        wake_reason: str,
        generate: TurnGenerator,
        prepare_state: Optional[StatePreparer] = None,
    ) -> tuple[TraderTurn, TraderState]:
        state = await self.state_store.load(self.session_id)
        if state is None:
            state = TraderState(session_id=self.session_id)

        if prepare_state is not None:
            previous_plans = set(state.plans)
            prepared = prepare_state(state)
            if prepared != state:
                state = prepared
                await self.state_store.save(state)
                await self.event_store.append(
                    self.session_id,
                    "state_reconciled",
                    {
                        "state_revision": state.revision,
                        "removed_plans": sorted(previous_plans - set(state.plans)),
                        "reason": "current_account_and_active_orders_are_source_of_truth",
                    },
                    occurred_at=as_of,
                )

        await self.event_store.append(
            self.session_id,
            "turn_woke",
            {"wake_reason": wake_reason, "state_revision": state.revision},
            occurred_at=as_of,
        )
        turn = await generate(state)
        if turn.session_id != self.session_id:
            raise ValueError("TraderTurn session_id 与当前会话不一致")

        await self.event_store.save_turn(turn)
        next_state = state.apply_turn(turn) if turn.status == "completed" else state
        if turn.status == "completed":
            await self.state_store.save(next_state)
            if turn.order_intents or turn.cancel_order_intents:
                await self.event_store.append(
                    self.session_id,
                    "shadow_intents_recorded" if self.execution_mode == "shadow" else "order_intents_proposed",
                    {
                        "execution_mode": self.execution_mode,
                        "intents": [item.model_dump(mode="json") for item in turn.order_intents],
                        "cancellations": [
                            item.model_dump(mode="json")
                            for item in turn.cancel_order_intents
                        ],
                    },
                    decision_id=turn.decision_id,
                    occurred_at=turn.as_of,
                )
            else:
                await self.event_store.append(
                    self.session_id,
                    "no_trade",
                    {"reason": turn.no_trade_reason},
                    decision_id=turn.decision_id,
                    occurred_at=turn.as_of,
                )
            if turn.next_review.at or turn.next_review.events or turn.next_review.conditions:
                await self.event_store.append(
                    self.session_id,
                    "review_registered",
                    turn.next_review.model_dump(mode="json"),
                    decision_id=turn.decision_id,
                    occurred_at=turn.as_of,
                )
        await self.event_store.append(
            self.session_id,
            "turn_completed" if turn.status == "completed" else "turn_failed",
            {
                "status": turn.status,
                "state_revision": next_state.revision,
                "order_intent_count": len(turn.order_intents),
                "next_review": turn.next_review.model_dump(mode="json"),
                "error_type": turn.error_type,
            },
            decision_id=turn.decision_id,
            occurred_at=turn.as_of,
        )
        return turn, next_state

    def to_execution_decision(
        self,
        turn: TraderTurn,
        snapshot: Any,
        account: Any,
        policy: HardRiskPolicy,
        proposal: Optional[OrderProposal] = None,
    ) -> Dict[str, Any]:
        """兼容入口：提案经风控后一次性提交全部获批订单。"""
        base: Dict[str, Any] = {
            "decision_mode": "trader",
            "decision_id": turn.decision_id,
            "trader_turn": turn.model_dump(mode="json"),
            "market_view": turn.market_view.model_dump(mode="json"),
            "plan_updates": [item.model_dump(mode="json") for item in turn.plan_updates],
            "next_review": turn.next_review.model_dump(mode="json"),
            "pending_order_actions": [
                item.model_dump(mode="json") for item in turn.pending_order_actions
            ],
            "signals": ["trader_turn_v1"],
        }
        if turn.status == "system_error":
            return {
                **base,
                "action": "system_error",
                "outcome_type": "SYSTEM_ERROR",
                "error_type": turn.error_type or "trader_turn_failed",
                "reason": turn.no_trade_reason or "交易员回合失败",
            }
        resolved_cancellations = list(turn.cancel_order_intents)
        cancelled_ids = {item.order_id for item in resolved_cancellations}
        for item in turn.pending_order_actions:
            if item.action in {"cancel", "replace"} and item.order_id not in cancelled_ids:
                resolved_cancellations.append(CancelOrderIntent(
                    order_id=item.order_id,
                    symbol=item.symbol,
                    reason=item.reason,
                ))
                cancelled_ids.add(item.order_id)
        base["cancel_order_intents"] = [
            item.model_dump(mode="json") for item in resolved_cancellations
        ]
        if not turn.order_intents and not resolved_cancellations:
            return {
                **base,
                "action": "hold",
                "outcome_type": "NO_TRADE",
                "reason": turn.no_trade_reason or "本轮无订单意图",
            }
        if self.execution_mode == "shadow":
            return {
                **base,
                "action": "hold",
                "outcome_type": "SHADOW_PROPOSAL",
                "reason": "shadow 模式：订单意图已记录但不会提交执行",
                "shadow_order_intents": [item.model_dump(mode="json") for item in turn.order_intents],
                "shadow_cancel_order_intents": [
                    item.model_dump(mode="json") for item in resolved_cancellations
                ],
                "order_proposal": (
                    proposal.model_dump(mode="json") if proposal is not None else None
                ),
            }

        proposal = proposal or self.propose_orders(turn, snapshot, account, policy)
        approved = [
            dict(item.approved_decision)
            for item in proposal.intents
            if item.approved_decision is not None
        ]
        cancellations = [item.model_dump(mode="json") for item in resolved_cancellations]
        if not approved and not cancellations:
            return {
                **base,
                "action": "hold",
                "outcome_type": "RISK_REJECTED",
                "reason": "RiskKernel 拒绝了本轮全部订单意图",
                "order_proposal": proposal.model_dump(mode="json"),
            }

        if proposal.commit_status != "committed":
            return {
                **base,
                "action": "hold",
                "outcome_type": "ABANDONED",
                "reason": "订单提案未获交易员提交",
                "order_proposal": proposal.model_dump(mode="json"),
            }
        first = dict(approved[0]) if approved else {
            "action": "hold",
            "reason": "提交撤单请求",
        }
        first.update(base)
        first["order_batch"] = approved
        first["cancel_order_intents"] = cancellations
        first["order_proposal"] = proposal.model_dump(mode="json")
        first["proposal_id"] = proposal.proposal_id
        first["outcome_type"] = "COMMITTED"
        first["policy_boundary"] = {
            "enforced": ["hard_risk", "authorization", "protocol", "execution_legality"],
            "strategy_vetoes": [],
        }
        first["signals"] = list(dict.fromkeys([*first.get("signals", []), "risk_checked_batch"]))
        return first

    def propose_orders(
        self,
        turn: TraderTurn,
        snapshot: Any,
        account: Any,
        policy: HardRiskPolicy,
    ) -> OrderProposal:
        """propose_orders -> RiskKernel；不产生任何外部副作用。"""
        kernel = RiskKernel(policy)
        checked = []
        prices = getattr(snapshot, "prices", {}) or {}
        equity = _decimal(getattr(account, "equity", 0))
        positions = list(account.get_all_positions() or [])
        gross_before = sum(
            abs(_decimal(getattr(item, "quantity", 0)))
            * _decimal(prices.get(str(getattr(item, "symbol", ""))))
            for item in positions
        )
        margin_before = sum(
            kernel._position_margin(item, prices) for item in positions
        )
        symbol_before: Dict[str, Decimal] = {}
        for item in positions:
            symbol = str(getattr(item, "symbol", ""))
            symbol_before[symbol] = symbol_before.get(symbol, Decimal("0")) + (
                abs(_decimal(getattr(item, "quantity", 0))) * _decimal(prices.get(symbol))
            )
        batch_gross = Decimal("0")
        batch_symbol: Dict[str, Decimal] = {}
        batch_direction_risk: Dict[tuple[str, str], Decimal] = {}
        batch_risk = Decimal("0")
        batch_margin = Decimal("0")
        portfolio_risk_before = kernel._portfolio_risk(account, prices)
        for intent in turn.order_intents:
            try:
                proposed = self._intent_to_decision(intent, snapshot, account, policy)
                evaluation = kernel.evaluate(proposed, account, prices)
                approved = evaluation.approved_decision
                status = evaluation.status
                violations = [item.to_dict() for item in evaluation.violations]
                if approved is not None and intent.effect in {"open", "add"}:
                    market_price = _decimal(prices.get(intent.symbol))
                    price = (
                        _decimal(approved.get("limit_price"))
                        if str(approved.get("order_type") or "market") == "limit"
                        else market_price
                    )
                    requested_notional = abs(_decimal(approved.get("quantity"))) * price
                    approved_leverage = max(
                        Decimal("1"), _decimal(approved.get("leverage"), "1")
                    )
                    incremental_risk = _decimal(
                        evaluation.computed_risk.get("incrementalRiskUSDT")
                    )
                    gross_remaining = max(
                        Decimal("0"),
                        equity * policy.max_gross_exposure_pct / Decimal("100")
                        - gross_before - batch_gross,
                    )
                    symbol_remaining = max(
                        Decimal("0"),
                        equity * policy.max_symbol_exposure_pct / Decimal("100")
                        - symbol_before.get(intent.symbol, Decimal("0"))
                        - batch_symbol.get(intent.symbol, Decimal("0")),
                    )
                    risk_remaining = max(
                        Decimal("0"),
                        equity * policy.max_portfolio_risk_pct / Decimal("100")
                        - portfolio_risk_before - batch_risk,
                    )
                    direction_key = (intent.symbol, intent.position_side)
                    same_plan_risk_remaining = max(
                        Decimal("0"),
                        equity * policy.max_risk_per_trade_pct / Decimal("100")
                        - batch_direction_risk.get(direction_key, Decimal("0")),
                    )
                    margin_remaining = max(
                        Decimal("0"),
                        equity * policy.max_margin_usage_pct / Decimal("100")
                        - margin_before - batch_margin,
                    )
                    allowed_notional = min(
                        requested_notional,
                        gross_remaining,
                        symbol_remaining,
                        margin_remaining * approved_leverage,
                    )
                    if incremental_risk > 0:
                        allowed_notional = min(
                            allowed_notional,
                            requested_notional * risk_remaining / incremental_risk,
                            requested_notional
                            * same_plan_risk_remaining
                            / incremental_risk,
                        )
                    if allowed_notional < policy.min_order_notional or price <= 0:
                        approved = None
                        status = "rejected"
                        violations = [{
                            "code": "batch_risk_budget_exhausted",
                            "message": "本批前序订单已占用剩余组合风险额度",
                        }]
                    else:
                        if allowed_notional < requested_notional:
                            approved = dict(approved)
                            approved["quantity"] = float(allowed_notional / price)
                            status = "resized"
                        ratio = allowed_notional / requested_notional if requested_notional > 0 else Decimal("0")
                        accepted_risk = incremental_risk * ratio
                        batch_gross += allowed_notional
                        batch_symbol[intent.symbol] = (
                            batch_symbol.get(intent.symbol, Decimal("0")) + allowed_notional
                        )
                        batch_risk += accepted_risk
                        batch_direction_risk[direction_key] = (
                            batch_direction_risk.get(direction_key, Decimal("0"))
                            + accepted_risk
                        )
                        batch_margin += allowed_notional / approved_leverage
                checked.append(RiskCheckedIntent(
                    client_intent_id=intent.client_intent_id,
                    status=status,
                    proposed_decision=proposed,
                    approved_decision=approved,
                    violations=violations,
                ))
            except Exception as exc:
                checked.append(RiskCheckedIntent(
                    client_intent_id=intent.client_intent_id,
                    status="rejected",
                    proposed_decision={
                        "symbol": intent.symbol,
                        "action": intent.legacy_action,
                        "order_type": intent.order_type,
                    },
                    violations=[{"code": "invalid_intent", "message": str(exc)}],
                ))
        statuses = {item.status for item in checked}
        if statuses == {"approved"}:
            status = "approved"
        elif statuses == {"resized"}:
            status = "resized"
        elif statuses == {"rejected"} or not statuses:
            status = "rejected"
        else:
            status = "mixed"
        return OrderProposal(
            decision_id=turn.decision_id,
            session_id=turn.session_id,
            as_of=turn.as_of,
            status=status,
            intents=checked,
        )

    async def record_proposal(self, proposal: OrderProposal) -> None:
        await self.event_store.save_proposal(proposal)
        await self.event_store.append(
            self.session_id,
            "orders_risk_checked",
            proposal.model_dump(mode="json"),
            decision_id=proposal.decision_id,
            occurred_at=proposal.as_of,
        )

    async def record_commit(self, proposal: OrderProposal) -> None:
        await self.event_store.save_proposal(proposal)
        await self.event_store.append(
            self.session_id,
            "orders_committed" if proposal.commit_status == "committed" else "orders_abandoned",
            proposal.model_dump(mode="json"),
            decision_id=proposal.decision_id,
            occurred_at=proposal.committed_at or proposal.as_of,
        )

    @staticmethod
    def _intent_to_decision(
        intent: OrderIntent,
        snapshot: Any,
        account: Any,
        policy: HardRiskPolicy,
    ) -> Dict[str, Any]:
        action = intent.legacy_action
        decision: Dict[str, Any] = {
            "action": action,
            "symbol": intent.symbol,
            "reason": intent.rationale,
            "thesis": intent.thesis,
            "invalidation": intent.invalidation,
            "client_intent_id": intent.client_intent_id,
            "order_type": intent.order_type,
            "execution_role": intent.execution_role,
            "parent_intent_id": intent.parent_intent_id,
            "requested_leverage": intent.requested_leverage,
            "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
        }
        if intent.limit_price:
            decision["limit_price"] = intent.limit_price

        position = account.get_position(intent.symbol)
        if intent.effect in {"reduce", "close"}:
            if position is None or str(position.side).lower() != intent.position_side:
                raise ValueError("订单意图与当前持仓不匹配")
            if intent.effect == "close":
                quantity = _decimal(position.quantity)
            elif intent.size.quantity:
                quantity = min(_decimal(position.quantity), _decimal(intent.size.quantity))
            else:
                quantity = _decimal(position.quantity) * Decimal("0.5")
            decision["quantity"] = float(quantity)
            return decision

        market_price = _decimal((getattr(snapshot, "prices", {}) or {}).get(intent.symbol))
        price = (
            _decimal(intent.limit_price)
            if intent.order_type == "limit"
            else market_price
        )
        stop = _decimal(intent.protection.stop_loss_price)
        if market_price <= 0 or price <= 0 or stop <= 0:
            raise ValueError("新增风险意图缺少有效现价或保护性止损")

        if intent.size.mode == "quantity":
            quantity = _decimal(intent.size.quantity)
        elif intent.size.mode == "notional":
            quantity = _decimal(intent.size.notional_usdt) / price
        else:
            risk_pct = min(
                policy.max_risk_per_trade_pct,
                max(Decimal("0"), _decimal(intent.size.risk_pct_equity, policy.max_risk_per_trade_pct)),
            )
            risk_budget = _decimal(getattr(account, "equity", 0)) * risk_pct / Decimal("100")
            quantity = risk_budget / abs(price - stop) if price != stop else Decimal("0")

        max_quantity = policy.max_order_notional / price
        quantity = min(quantity, max_quantity)
        if quantity <= 0:
            raise ValueError("订单意图无法计算出有效数量")
        decision["quantity"] = float(quantity)
        decision["stop_loss_price"] = float(stop)
        if intent.protection.take_profit_price:
            decision["take_profit_price"] = float(intent.protection.take_profit_price)
        decision["trade_plan"] = {
            "thesis": intent.thesis,
            "invalidation": intent.invalidation,
            "execution_role": intent.execution_role,
            "parent_intent_id": intent.parent_intent_id,
            "stop_loss_price": float(stop),
            "take_profit_price": intent.protection.take_profit_price,
        }
        return decision
