"""交易员回合、工作状态与订单意图协议。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewTrigger(BaseModel):
    """交易员希望再次被唤醒的时间或事件条件。"""

    model_config = ConfigDict(extra="ignore")

    at: Optional[datetime] = None
    events: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)

    @field_validator("events", "conditions", mode="before")
    @classmethod
    def _normalize_strings(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:300] for item in value if str(item).strip()][:20]


class MarketView(BaseModel):
    """跨回合延续的市场观点，不要求使用固定的行情分类。"""

    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    regime: Optional[str] = None
    trend_state: Literal[
        "strong_bullish",
        "strong_bearish",
        "weak_bullish",
        "weak_bearish",
        "range",
        "unclear",
    ] = "unclear"
    key_drivers: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value: Any) -> str:
        return str(value or "").strip()[:2000]

    @field_validator("regime", mode="before")
    @classmethod
    def _regime(cls, value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text[:200] or None

    @field_validator("key_drivers", "counter_evidence", "uncertainties", mode="before")
    @classmethod
    def _items(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:500] for item in value if str(item).strip()][:20]


class TraderPlan(BaseModel):
    """某个标的当前有效的 thesis 与复核条件。"""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    status: Literal["watching", "active", "invalidated", "closed"] = "watching"
    thesis: str = ""
    invalidation: str = ""
    evidence: List[str] = Field(default_factory=list)
    counter_evidence: List[str] = Field(default_factory=list)
    review_triggers: List[str] = Field(default_factory=list)

    @field_validator("symbol", mode="before")
    @classmethod
    def _symbol(cls, value: Any) -> str:
        return str(value or "").strip().upper()[:40]

    @field_validator("thesis", "invalidation", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return str(value or "").strip()[:2000]

    @field_validator("evidence", "counter_evidence", "review_triggers", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:500] for item in value if str(item).strip()][:20]


class IntentSize(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: Literal["risk_budget", "notional", "quantity"] = "risk_budget"
    risk_pct_equity: Optional[float] = None
    notional_usdt: Optional[float] = None
    quantity: Optional[float] = None


class IntentProtection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None


class OrderIntent(BaseModel):
    """模型提出的订单意图；它不是已批准订单，也不代表已经成交。"""

    model_config = ConfigDict(extra="ignore")

    client_intent_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    side: Literal["buy", "sell"]
    effect: Literal["open", "add", "reduce", "close"]
    position_side: Literal["long", "short"]
    order_type: Literal["market", "limit"] = "market"
    execution_role: Literal[
        "standalone", "trend_starter", "pullback_add"
    ] = "standalone"
    parent_intent_id: Optional[str] = None
    limit_price: Optional[float] = None
    requested_leverage: Optional[float] = Field(default=None, ge=1.0)
    size: IntentSize = Field(default_factory=IntentSize)
    protection: IntentProtection = Field(default_factory=IntentProtection)
    rationale: str = ""
    thesis: str = ""
    invalidation: str = ""
    expires_at: Optional[datetime] = None

    @field_validator("symbol", mode="before")
    @classmethod
    def _intent_symbol(cls, value: Any) -> str:
        return str(value or "").strip().upper()[:40]

    @field_validator("rationale", "thesis", "invalidation", mode="before")
    @classmethod
    def _intent_text(cls, value: Any) -> str:
        return str(value or "").strip()[:2000]

    @model_validator(mode="after")
    def _validate_semantics(self) -> "OrderIntent":
        expected_side = {
            ("open", "long"): "buy",
            ("add", "long"): "buy",
            ("reduce", "long"): "sell",
            ("close", "long"): "sell",
            ("open", "short"): "sell",
            ("add", "short"): "sell",
            ("reduce", "short"): "buy",
            ("close", "short"): "buy",
        }[(self.effect, self.position_side)]
        if self.side != expected_side:
            raise ValueError("side 与 effect/position_side 语义不一致")
        if self.order_type == "limit" and not self.limit_price:
            raise ValueError("limit 订单必须提供 limit_price")
        if self.effect in {"open", "add"} and not self.protection.stop_loss_price:
            raise ValueError("新增风险意图必须提供保护性止损")
        if self.effect in {"open", "add"} and self.requested_leverage is None:
            raise ValueError("新增风险意图必须明确 requested_leverage")
        if self.effect in {"reduce", "close"} and self.requested_leverage is not None:
            raise ValueError("减仓/平仓不得修改杠杆")
        if self.execution_role == "trend_starter":
            if self.effect != "open" or self.order_type != "market":
                raise ValueError("trend_starter 必须是 market open 订单")
            if self.parent_intent_id:
                raise ValueError("trend_starter 不得填写 parent_intent_id")
        elif self.execution_role == "pullback_add":
            if self.effect != "add" or self.order_type != "limit":
                raise ValueError("pullback_add 必须是 limit add 订单")
            if not self.parent_intent_id:
                raise ValueError("pullback_add 必须填写 parent_intent_id")
        elif self.parent_intent_id:
            raise ValueError("仅 pullback_add 可填写 parent_intent_id")
        return self

    @property
    def legacy_action(self) -> str:
        return f"{self.effect}_{self.position_side}"


class CancelOrderIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str
    symbol: str
    reason: str = ""

    @field_validator("symbol", mode="before")
    @classmethod
    def _cancel_symbol(cls, value: Any) -> str:
        return str(value or "").strip().upper()[:40]


class PendingOrderAction(BaseModel):
    """交易员对每个活动挂单的显式处置。"""

    model_config = ConfigDict(extra="ignore")

    order_id: str
    symbol: str
    action: Literal["keep", "replace", "cancel"]
    reason: str
    replacement_client_intent_id: Optional[str] = None

    @field_validator("order_id", "reason", mode="before")
    @classmethod
    def _required_text(cls, value: Any) -> str:
        return str(value or "").strip()[:2000]

    @field_validator("symbol", mode="before")
    @classmethod
    def _symbol(cls, value: Any) -> str:
        return str(value or "").strip().upper()[:40]

    @model_validator(mode="after")
    def _validate_action(self) -> "PendingOrderAction":
        if not self.order_id:
            raise ValueError("pending_order_actions.order_id 不能为空")
        if not self.reason:
            raise ValueError("pending_order_actions.reason 不能为空")
        if self.action == "replace" and not self.replacement_client_intent_id:
            raise ValueError("replace 必须提供 replacement_client_intent_id")
        if self.action != "replace" and self.replacement_client_intent_id:
            raise ValueError("仅 replace 可提供 replacement_client_intent_id")
        return self


class ToolRequest(BaseModel):
    """模型只能通过该协议请求白名单内的只读数据。"""

    model_config = ConfigDict(extra="ignore")

    tool_call_id: str = Field(default_factory=lambda: str(uuid4()))
    name: Literal[
        "get_market_snapshot",
        "get_ohlcv",
        "get_indicators",
        "search_news",
        "get_account_state",
        "get_positions_and_orders",
        "get_recent_trades",
    ]
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """带时间边界与来源标记的工具结果，便于完整回放。"""

    model_config = ConfigDict(extra="ignore")

    tool_call_id: str
    name: str
    as_of: datetime
    source: str
    data: Any = None
    error: Optional[str] = None


class TraderModelResponse(BaseModel):
    """调查循环中的中间响应；final 响应仍使用 TraderTurn 业务字段。"""

    model_config = ConfigDict(extra="allow")

    response_type: Literal["investigate", "final"] = "final"
    tool_requests: List[ToolRequest] = Field(default_factory=list)


class RiskCheckedIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    client_intent_id: str
    status: Literal["approved", "resized", "rejected"]
    proposed_decision: Dict[str, Any]
    approved_decision: Optional[Dict[str, Any]] = None
    violations: List[Dict[str, Any]] = Field(default_factory=list)


class OrderProposal(BaseModel):
    """RiskKernel 裁决后的不可变订单提案；只有 committed 才可交给执行器。"""

    model_config = ConfigDict(extra="ignore")

    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    decision_id: str
    session_id: str
    as_of: datetime
    status: Literal["approved", "resized", "rejected", "mixed"]
    intents: List[RiskCheckedIntent] = Field(default_factory=list)
    commit_status: Literal["pending", "committed", "abandoned"] = "pending"
    committed_at: Optional[datetime] = None


class TraderTurn(BaseModel):
    """一次完整、可审计的交易员输出。"""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["trader-turn-v1"] = "trader-turn-v1"
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    as_of: datetime = Field(default_factory=utc_now)
    market_view: MarketView = Field(default_factory=MarketView)
    plan_updates: List[TraderPlan] = Field(default_factory=list)
    order_intents: List[OrderIntent] = Field(default_factory=list)
    cancel_order_intents: List[CancelOrderIntent] = Field(default_factory=list)
    pending_order_actions: List[PendingOrderAction] = Field(default_factory=list)
    no_trade_reason: Optional[str] = None
    next_review: ReviewTrigger = Field(default_factory=ReviewTrigger)
    status: Literal["completed", "system_error"] = "completed"
    error_type: Optional[str] = None

    @model_validator(mode="after")
    def _require_outcome(self) -> "TraderTurn":
        manages_order = any(
            item.action in {"replace", "cancel"}
            for item in self.pending_order_actions
        )
        if (
            self.status == "completed"
            and not self.order_intents
            and not self.cancel_order_intents
            and not manages_order
            and not self.no_trade_reason
        ):
            raise ValueError("无订单意图时必须说明 no_trade_reason")
        return self


class TraderState(BaseModel):
    """可覆盖的工作记忆；只保存当前有效状态，不无限追加历史。"""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["trader-state-v1"] = "trader-state-v1"
    session_id: str
    revision: int = 0
    market_view: MarketView = Field(default_factory=MarketView)
    plans: Dict[str, TraderPlan] = Field(default_factory=dict)
    watchlist: List[str] = Field(default_factory=list)
    pending_hypotheses: List[str] = Field(default_factory=list)
    next_review: ReviewTrigger = Field(default_factory=ReviewTrigger)
    last_decision_id: Optional[str] = None
    updated_at: datetime = Field(default_factory=utc_now)

    def apply_turn(self, turn: TraderTurn) -> "TraderState":
        plans = dict(self.plans)
        for plan in turn.plan_updates:
            if plan.status in {"invalidated", "closed"}:
                plans.pop(plan.symbol, None)
            else:
                plans[plan.symbol] = plan
        watchlist = sorted({
            plan.symbol for plan in plans.values() if plan.status == "watching"
        })
        return self.model_copy(update={
            "revision": self.revision + 1,
            "market_view": turn.market_view,
            "plans": plans,
            "watchlist": watchlist,
            "next_review": turn.next_review,
            "last_decision_id": turn.decision_id,
            "updated_at": utc_now(),
        })
