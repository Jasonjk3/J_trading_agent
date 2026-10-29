"""确定性的交易硬风险内核。

本模块只判断权限、资金安全和订单合法性，不读取技术指标，不评价交易机会。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence


def _decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


@dataclass(frozen=True)
class HardRiskPolicy:
    """用户授权的、不可由模型绕过的风险边界。"""

    allowed_symbols: Sequence[str] = field(default_factory=tuple)
    allowed_directions: Sequence[str] = ("long", "short")
    min_order_notional: Decimal = Decimal("10")
    max_order_notional: Decimal = Decimal("1000")
    max_order_margin: Decimal = Decimal("1000")
    max_margin_usage_pct: Decimal = Decimal("30")
    max_symbol_exposure_pct: Decimal = Decimal("30")
    max_gross_exposure_pct: Decimal = Decimal("30")
    max_risk_per_trade_pct: Decimal = Decimal("0.5")
    max_portfolio_risk_pct: Decimal = Decimal("1.5")
    max_drawdown_pct: Decimal = Decimal("8")
    min_leverage: Decimal = Decimal("1")
    max_leverage: Decimal = Decimal("5")
    require_protective_stop: bool = True
    kill_switch: bool = False
    version: str = "hard-risk-v1"

    @classmethod
    def from_strategy_config(cls, config: Optional[Dict[str, Any]]) -> "HardRiskPolicy":
        config = config or {}
        raw = config.get("hardRiskPolicy") or {}
        if not isinstance(raw, dict):
            raw = {}

        direction = str(config.get("positionDirection") or "both").lower()
        directions = {
            "long_only": ("long",),
            "short_only": ("short",),
            "both": ("long", "short"),
        }.get(direction, ("long", "short"))
        configured_directions = raw.get("allowedDirections")
        if isinstance(configured_directions, list):
            requested = tuple(
                str(item).lower() for item in configured_directions
                if str(item).lower() in {"long", "short"}
            )
            directions = tuple(item for item in directions if item in requested)

        default_margin_usage = _decimal(config.get("maxPositionRatio"), "30")
        trading_style = str(config.get("tradingStyle") or "balanced").lower()
        configured_max_leverage = max(
            Decimal("1"),
            _decimal(raw.get("maxLeverage", config.get("maxLeverage")), "5"),
        )
        min_leverage = Decimal("2") if trading_style == "aggressive" else Decimal("1")
        max_leverage = (
            Decimal("1")
            if trading_style == "conservative"
            else configured_max_leverage
        )
        max_order_margin = _decimal(
            raw.get("maxOrderMarginUSDT", config.get("maxOrderAmount")), "1000"
        )
        default_gross_exposure = default_margin_usage * max_leverage
        return cls(
            allowed_symbols=tuple(raw.get("allowedSymbols") or config.get("symbols") or ()),
            allowed_directions=directions,
            min_order_notional=_decimal(
                raw.get("minOrderNotionalUSDT", config.get("minOrderAmount")), "10"
            ),
            max_order_notional=_decimal(
                raw.get("maxOrderNotionalUSDT"), str(max_order_margin * max_leverage)
            ),
            max_order_margin=max_order_margin,
            max_margin_usage_pct=_decimal(
                raw.get("maxMarginUsagePct"), str(default_margin_usage)
            ),
            max_symbol_exposure_pct=_decimal(
                raw.get("maxSymbolExposurePct"), str(default_gross_exposure)
            ),
            max_gross_exposure_pct=_decimal(
                raw.get("maxGrossExposurePct"), str(default_gross_exposure)
            ),
            max_risk_per_trade_pct=_decimal(raw.get("maxRiskPerTradePct"), "0.5"),
            max_portfolio_risk_pct=_decimal(raw.get("maxPortfolioRiskPct"), "1.5"),
            max_drawdown_pct=_decimal(raw.get("maxDrawdownPct"), "8"),
            min_leverage=min_leverage,
            max_leverage=max_leverage,
            require_protective_stop=bool(raw.get("requireProtectiveStop", True)),
            kill_switch=bool(raw.get("killSwitch", False)),
            version=str(raw.get("version") or "hard-risk-v1"),
        )

    def public_summary(self) -> Dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Decimal):
                data[key] = float(value)
            elif isinstance(value, tuple):
                data[key] = list(value)
        return data


@dataclass
class RiskViolation:
    code: str
    message: str
    field: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskEvaluation:
    status: str
    approved_decision: Optional[Dict[str, Any]] = None
    violations: List[RiskViolation] = field(default_factory=list)
    computed_risk: Dict[str, float] = field(default_factory=dict)
    policy_version: str = "hard-risk-v1"

    @property
    def approved(self) -> bool:
        return self.status in {"approved", "resized"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "approvedDecision": self.approved_decision,
            "violations": [item.to_dict() for item in self.violations],
            "computedRisk": self.computed_risk,
            "policyVersion": self.policy_version,
        }


class RiskKernel:
    """对单个兼容动作执行最终硬风险检查，并在可能时向下缩量。"""

    ENTRY_ACTIONS = {"open_long", "open_short", "add_long", "add_short"}
    EXIT_ACTIONS = {"reduce_long", "reduce_short", "close_long", "close_short"}
    SUPPORTED_ACTIONS = ENTRY_ACTIONS | EXIT_ACTIONS | {"hold", "system_error"}

    def __init__(self, policy: HardRiskPolicy):
        self.policy = policy

    @classmethod
    def from_strategy_config(cls, config: Optional[Dict[str, Any]]) -> "RiskKernel":
        return cls(HardRiskPolicy.from_strategy_config(config))

    @staticmethod
    def _positions(account: Any) -> List[Any]:
        getter = getattr(account, "get_all_positions", None)
        return list(getter() or []) if callable(getter) else []

    @staticmethod
    def _position(account: Any, symbol: str) -> Any:
        getter = getattr(account, "get_position", None)
        return getter(symbol) if callable(getter) else None

    @staticmethod
    def _position_value(position: Any, prices: Dict[str, Any]) -> Decimal:
        symbol = str(getattr(position, "symbol", ""))
        price = _decimal(prices.get(symbol), str(getattr(position, "entry_price", 0)))
        return abs(_decimal(getattr(position, "quantity", 0)) * price)

    @classmethod
    def _position_margin(cls, position: Any, prices: Dict[str, Any]) -> Decimal:
        explicit = _decimal(getattr(position, "margin_used", 0))
        if explicit > 0:
            return explicit
        leverage = max(Decimal("1"), _decimal(getattr(position, "leverage", 1), "1"))
        return cls._position_value(position, prices) / leverage

    @staticmethod
    def _position_stop(position: Any) -> Optional[Decimal]:
        plan = getattr(position, "trade_plan", None)
        if not isinstance(plan, dict):
            raw = getattr(position, "raw", None)
            plan = raw.get("trade_plan") if isinstance(raw, dict) else None
        if not isinstance(plan, dict) or plan.get("stop_loss_price") is None:
            return None
        stop = _decimal(plan.get("stop_loss_price"))
        return stop if stop > 0 else None

    def _portfolio_risk(self, account: Any, prices: Dict[str, Any]) -> Decimal:
        risk = Decimal("0")
        for position in self._positions(account):
            symbol = str(getattr(position, "symbol", ""))
            current = _decimal(prices.get(symbol), str(getattr(position, "entry_price", 0)))
            stop = self._position_stop(position)
            if current <= 0 or stop is None:
                continue
            risk += abs(current - stop) * abs(_decimal(getattr(position, "quantity", 0)))
        return risk

    def evaluate(
        self,
        decision: Dict[str, Any],
        account: Any,
        prices: Dict[str, Any],
    ) -> RiskEvaluation:
        action = str(decision.get("action") or "hold").lower()
        if action in {"hold", "system_error"}:
            return RiskEvaluation(
                status="approved",
                approved_decision=dict(decision),
                policy_version=self.policy.version,
            )
        if action not in self.SUPPORTED_ACTIONS:
            return self._reject("unsupported_action", f"不支持的动作: {action}", "action")
        if self.policy.kill_switch:
            return self._reject("kill_switch", "全局交易开关已关闭")

        symbol = str(decision.get("symbol") or "")
        if not symbol or (
            self.policy.allowed_symbols and symbol not in self.policy.allowed_symbols
        ):
            return self._reject("symbol_not_allowed", f"未授权交易对: {symbol}", "symbol")
        market_price = _decimal(prices.get(symbol))
        if market_price <= 0:
            return self._reject("market_price_missing", f"缺少 {symbol} 的有效行情")
        order_type = str(decision.get("order_type") or "market").lower()
        price = (
            _decimal(decision.get("limit_price"))
            if order_type == "limit"
            else market_price
        )
        if price <= 0:
            return self._reject("limit_price_missing", "限价订单缺少有效 limit_price", "limit_price")

        side = "long" if action.endswith("_long") else "short"
        if str(decision.get("execution_role") or "") == "pullback_add":
            is_pullback = (
                side == "long" and price < market_price
            ) or (
                side == "short" and price > market_price
            )
            if not is_pullback:
                return self._reject(
                    "invalid_pullback_price",
                    "回撤加仓价格必须位于趋势主动首仓现价的回撤方向",
                    "limit_price",
                )
        position = self._position(account, symbol)
        if action in self.EXIT_ACTIONS:
            if position is None or str(getattr(position, "side", "")).lower() != side:
                return self._reject("position_not_found", "没有与动作方向匹配的可管理持仓")
            return RiskEvaluation(
                status="approved",
                approved_decision=dict(decision),
                policy_version=self.policy.version,
            )

        if side not in self.policy.allowed_directions:
            return self._reject("direction_not_allowed", f"未授权 {side} 方向", "action")

        equity = _decimal(getattr(account, "equity", 0))
        if equity <= 0:
            return self._reject("invalid_equity", "账户权益无效")
        requested_leverage = max(
            Decimal("1"),
            _decimal(
                decision.get("requested_leverage", decision.get("leverage")),
                str(getattr(account, "leverage", 1)),
            ),
        )
        if self.policy.min_leverage > self.policy.max_leverage:
            return self._reject(
                "invalid_leverage_policy",
                "交易风格要求使用杠杆，但最大杠杆配置不足；请将最大杠杆设为至少 2x",
                "requested_leverage",
            )
        if requested_leverage < self.policy.min_leverage:
            return self._reject(
                "leverage_required_by_style",
                f"当前交易风格要求杠杆不低于 {self.policy.min_leverage}x",
                "requested_leverage",
            )
        approved_leverage = min(requested_leverage, self.policy.max_leverage)
        peak_equity = _decimal(getattr(account, "peak_equity", equity), str(equity))
        drawdown_pct = (
            max(Decimal("0"), (peak_equity - equity) / peak_equity * Decimal("100"))
            if peak_equity > 0 else Decimal("0")
        )
        if drawdown_pct >= self.policy.max_drawdown_pct:
            return self._reject(
                "max_drawdown_reached",
                f"账户回撤 {drawdown_pct:.2f}% 已达到硬上限 {self.policy.max_drawdown_pct}%",
            )

        quantity = abs(_decimal(decision.get("quantity")))
        if quantity <= 0:
            return self._reject("invalid_quantity", "新增风险动作必须包含正数 quantity", "quantity")
        requested_notional = quantity * price
        existing_positions = self._positions(account)
        gross_before = sum(
            (self._position_value(item, prices) for item in existing_positions), Decimal("0")
        )
        margin_before = sum(
            (self._position_margin(item, prices) for item in existing_positions), Decimal("0")
        )
        symbol_before = sum(
            (
                self._position_value(item, prices)
                for item in existing_positions
                if str(getattr(item, "symbol", "")) == symbol
            ),
            Decimal("0"),
        )

        caps = [
            self.policy.max_order_notional,
            self.policy.max_order_margin * approved_leverage,
        ]
        caps.append(max(Decimal("0"), equity * self.policy.max_gross_exposure_pct / 100 - gross_before))
        caps.append(max(Decimal("0"), equity * self.policy.max_symbol_exposure_pct / 100 - symbol_before))
        remaining_margin = max(
            Decimal("0"),
            equity * self.policy.max_margin_usage_pct / Decimal("100") - margin_before,
        )
        caps.append(remaining_margin * approved_leverage)

        plan = decision.get("trade_plan") if isinstance(decision.get("trade_plan"), dict) else decision
        stop = _decimal(plan.get("stop_loss_price"))
        if self.policy.require_protective_stop and stop <= 0:
            return self._reject("protective_stop_required", "新增风险动作必须声明保护性止损", "stop_loss_price")
        if stop > 0:
            valid_stop = (side == "long" and stop < price) or (side == "short" and stop > price)
            if not valid_stop:
                return self._reject("invalid_stop_side", "止损价格位于错误方向", "stop_loss_price")
            risk_per_unit = abs(price - stop)
            risk_cap = equity * self.policy.max_risk_per_trade_pct / Decimal("100")
            if risk_per_unit > 0:
                caps.append(risk_cap / risk_per_unit * price)

        current_portfolio_risk = self._portfolio_risk(account, prices)
        if stop > 0:
            remaining_portfolio_risk = max(
                Decimal("0"),
                equity * self.policy.max_portfolio_risk_pct / Decimal("100")
                - current_portfolio_risk,
            )
            risk_per_unit = abs(price - stop)
            if risk_per_unit > 0:
                caps.append(remaining_portfolio_risk / risk_per_unit * price)

        approved_notional = min([requested_notional, *caps])
        if approved_notional < self.policy.min_order_notional:
            return self._reject(
                "risk_budget_exhausted",
                "硬风险额度不足，缩量后低于最小订单金额",
            )

        approved = dict(decision)
        approved_quantity = approved_notional / price
        approved["quantity"] = float(approved_quantity)
        approved["requested_leverage"] = float(requested_leverage)
        approved["leverage"] = float(approved_leverage)
        incremental_risk = (
            approved_quantity * abs(price - stop) if stop > 0 else Decimal("0")
        )
        computed = {
            "requestedNotional": float(requested_notional),
            "approvedNotional": float(approved_notional),
            "requestedLeverage": float(requested_leverage),
            "approvedLeverage": float(approved_leverage),
            "marginRequired": float(approved_notional / approved_leverage),
            "marginUsagePctAfter": float(
                (margin_before + approved_notional / approved_leverage) / equity * 100
            ),
            "incrementalRiskUSDT": float(incremental_risk),
            "incrementalRiskPct": float(incremental_risk / equity * 100),
            "grossExposurePctAfter": float((gross_before + approved_notional) / equity * 100),
            "drawdownPct": float(drawdown_pct),
        }
        resized = (
            approved_notional < requested_notional
            or approved_leverage < requested_leverage
        )
        return RiskEvaluation(
            status="resized" if resized else "approved",
            approved_decision=approved,
            computed_risk=computed,
            policy_version=self.policy.version,
        )

    def _reject(
        self, code: str, message: str, field_name: Optional[str] = None
    ) -> RiskEvaluation:
        return RiskEvaluation(
            status="rejected",
            violations=[RiskViolation(code, message, field_name)],
            policy_version=self.policy.version,
        )
