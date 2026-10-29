#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""传统规则决策引擎：按 priority_stack 评估启用的规则集。"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from decision.rule_params import allows_direction, position_size, resolve_rule_params
from decision.symbol_context import build_symbol_context, detect_market_regime, indicators_snapshot
from decision.types import RuleHit, resolve_enabled_rules


class RuleDecisionEngine:
    """回测与实盘共用的规则决策引擎。"""

    def __init__(self, strategy_config: Optional[Dict[str, Any]] = None):
        self.strategy_config = strategy_config or {}
        self.symbols: List[str] = list(self.strategy_config.get("symbols") or [])
        self.enabled_rules: Set[str] = set(resolve_enabled_rules(self.strategy_config))

    def _enabled(self, rule_id: str) -> bool:
        return rule_id in self.enabled_rules

    async def evaluate(
        self,
        snapshot: Any,
        account: Any,
        analysis_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params = resolve_rule_params(self.strategy_config)
        rule_hits: List[Dict[str, Any]] = []
        last_regime: Optional[str] = None

        for symbol in self.symbols:
            ctx = self._resolve_symbol_context(snapshot, symbol, analysis_context)
            if not ctx:
                continue

            regime: Optional[str] = None
            regime_meta: Dict[str, float] = {}
            if self._enabled("regime_detector"):
                regime, regime_meta = detect_market_regime(ctx, params)
                last_regime = regime
                rule_hits.append(
                    RuleHit(
                        rule_id="regime_detector",
                        action="hold",
                        reason=f"市场状态: {regime}",
                        metadata={"regime": regime, **regime_meta},
                    ).to_dict()
                )
            else:
                regime = "trending" if params["market_mode"] == "trend_only" else "ranging"

            decision = self._evaluate_symbol(ctx, account, params, regime or "ranging", rule_hits)
            if decision and decision.get("action") != "hold":
                decision["decision_mode"] = "rule"
                decision["regime"] = regime
                decision["rule_hits"] = list(rule_hits)
                decision["indicators_snapshot"] = indicators_snapshot(ctx)
                return decision

        mode_desc = {
            "auto": "自动识别",
            "trend_only": "仅趋势",
            "range_only": "仅震荡",
        }.get(params["market_mode"], params["market_mode"])
        return {
            "action": "hold",
            "reason": f"{mode_desc}模式下暂无明确交易信号",
            "decision_mode": "rule",
            "regime": last_regime,
            "rule_hits": rule_hits,
            "confidence": 0.5,
            "signals": ["no_rule_signal"],
        }

    def _resolve_symbol_context(
        self,
        snapshot: Any,
        symbol: str,
        analysis_context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        ctx_map = (analysis_context or {}).get("symbol_contexts") or {}
        if isinstance(ctx_map, dict) and symbol in ctx_map:
            return ctx_map[symbol]
        return build_symbol_context(snapshot, symbol)

    def _evaluate_symbol(
        self,
        ctx: Dict[str, Any],
        account: Any,
        params: Dict[str, Any],
        regime: str,
        rule_hits: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        symbol = ctx["symbol"]
        current_price = ctx["price"]
        current_f = ctx["current_f"]
        ind = ctx["indicators"]
        ma5 = ctx["ma5"]
        ma20 = ctx["ma20"]
        position = account.get_position(symbol)
        quantity = position_size(Decimal(str(current_price)), account, params, self.strategy_config)
        rsi_val = ind.get("rsi")
        boll = ind.get("boll")
        macd_val = ind.get("macd")
        tolerance = params["range_band_tolerance"]
        near_upper = boll is not None and current_f >= boll["upper"] * (1 - tolerance)
        near_lower = boll is not None and current_f <= boll["lower"] * (1 + tolerance)
        near_middle = (
            boll is not None
            and abs(current_f - boll["middle"]) / boll["middle"] <= max(tolerance, 0.003)
        )
        breakout_up = (
            ctx["recent_high_lookback"] > 0
            and current_f >= ctx["recent_high_lookback"] * (1 + params["breakout_buffer"])
        )
        breakout_down = (
            ctx["recent_low_lookback"] > 0
            and current_f <= ctx["recent_low_lookback"] * (1 - params["breakout_buffer"])
        )
        macd_bull = bool(macd_val and macd_val["histogram"] > 0)
        macd_bear = bool(macd_val and macd_val["histogram"] < 0)

        if position:
            exit_decision = self._evaluate_exit(
                ctx,
                position,
                current_price,
                params,
                regime,
                boll,
                rsi_val,
                ma5,
                ma20,
                macd_bull,
                macd_bear,
                rule_hits,
            )
            if exit_decision:
                return exit_decision
            return None

        return self._evaluate_entry(
            ctx,
            params,
            regime,
            quantity,
            boll,
            rsi_val,
            ma5,
            ma20,
            macd_bull,
            macd_bear,
            near_upper,
            near_lower,
            near_middle,
            breakout_up,
            breakout_down,
            rule_hits,
        )

    def _evaluate_exit(
        self,
        ctx: Dict[str, Any],
        position: Any,
        current_price: Any,
        params: Dict[str, Any],
        regime: str,
        boll: Optional[Dict[str, float]],
        rsi_val: Optional[float],
        ma5: float,
        ma20: float,
        macd_bull: bool,
        macd_bear: bool,
        rule_hits: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        symbol = ctx["symbol"]
        current_f = ctx["current_f"]
        tolerance = params["range_band_tolerance"]
        pnl_percent = position.get_pnl_percent(current_price)

        if self._enabled("trailing_stop"):
            trailing = self._check_trailing_stop(position, float(pnl_percent), ctx, params)
            if trailing:
                rule_hits.append(RuleHit("trailing_stop", trailing["action"], trailing["reason"], trailing.get("confidence", 0.88), trailing.get("signals", [])).to_dict())
                return trailing

        if regime == "ranging" and boll and self._enabled("bollinger_range"):
            long_mid_take = params["range_take_profit_mode"] == "mid_band" and current_f >= boll["middle"]
            long_opp_take = (
                params["range_take_profit_mode"] == "opposite_band"
                and current_f >= boll["upper"] * (1 - tolerance / 2)
            )
            short_mid_take = params["range_take_profit_mode"] == "mid_band" and current_f <= boll["middle"]
            short_opp_take = (
                params["range_take_profit_mode"] == "opposite_band"
                and current_f <= boll["lower"] * (1 + tolerance / 2)
            )
            if position.side == "long":
                if self._enabled("fixed_pct_stop") and (
                    pnl_percent <= -params["range_stop_loss"] or current_f < boll["lower"] * (1 - tolerance)
                ):
                    hit = self._close_decision(
                        "close_long",
                        symbol,
                        f"震荡策略止损 {pnl_percent:.2f}%，跌破下沿",
                        0.9,
                        ["range_stop_loss", "range_breakdown"],
                    )
                    rule_hits.append(RuleHit("fixed_pct_stop", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                    return hit
                if long_mid_take or long_opp_take or pnl_percent >= params["range_take_profit"] or (
                    self._enabled("rsi_threshold") and rsi_val is not None and rsi_val >= 58
                ):
                    target_desc = "布林中轨" if params["range_take_profit_mode"] == "mid_band" else "对侧轨道"
                    hit = self._close_decision(
                        "close_long",
                        symbol,
                        f"震荡策略止盈，价格回到{target_desc}",
                        0.75,
                        ["range_take_profit", "mean_reversion_complete"],
                    )
                    rule_hits.append(RuleHit("bollinger_range", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                    return hit
            if position.side == "short":
                if self._enabled("fixed_pct_stop") and (
                    pnl_percent <= -params["range_stop_loss"] or current_f > boll["upper"] * (1 + tolerance)
                ):
                    hit = self._close_decision(
                        "close_short",
                        symbol,
                        f"震荡策略止损 {pnl_percent:.2f}%，突破上沿",
                        0.9,
                        ["range_stop_loss", "range_breakout"],
                    )
                    rule_hits.append(RuleHit("fixed_pct_stop", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                    return hit
                if short_mid_take or short_opp_take or pnl_percent >= params["range_take_profit"] or (
                    self._enabled("rsi_threshold") and rsi_val is not None and rsi_val <= 42
                ):
                    target_desc = "布林中轨" if params["range_take_profit_mode"] == "mid_band" else "对侧轨道"
                    hit = self._close_decision(
                        "close_short",
                        symbol,
                        f"震荡策略止盈，价格回到{target_desc}",
                        0.75,
                        ["range_take_profit", "mean_reversion_complete"],
                    )
                    rule_hits.append(RuleHit("bollinger_range", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                    return hit

        if self._enabled("fixed_pct_stop"):
            if pnl_percent >= params["trend_take_profit"]:
                hit = self._close_decision(
                    f"close_{position.side}",
                    symbol,
                    f"达到趋势止盈目标 {pnl_percent:.2f}%",
                    0.9,
                    ["trend_take_profit"],
                )
                rule_hits.append(RuleHit("fixed_pct_stop", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit
            if pnl_percent <= -params["trend_stop_loss"]:
                hit = self._close_decision(
                    f"close_{position.side}",
                    symbol,
                    f"触发趋势止损 {pnl_percent:.2f}%",
                    0.9,
                    ["trend_stop_loss"],
                )
                rule_hits.append(RuleHit("fixed_pct_stop", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit

        if self._enabled("ma_cross") or self._enabled("trend_follow"):
            if position.side == "long" and (ma5 < ma20 or (regime == "trending" and macd_bear)):
                hit = self._close_decision(
                    "close_long",
                    symbol,
                    "趋势转弱，平掉多单",
                    0.72,
                    ["trend_reversal", "ma_cross_down"],
                )
                rule_id = "ma_cross" if ma5 < ma20 else "trend_follow"
                rule_hits.append(RuleHit(rule_id, hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit
            if position.side == "short" and (ma5 > ma20 or (regime == "trending" and macd_bull)):
                hit = self._close_decision(
                    "close_short",
                    symbol,
                    "趋势转强，平掉空单",
                    0.72,
                    ["trend_reversal", "ma_cross_up"],
                )
                rule_id = "ma_cross" if ma5 > ma20 else "trend_follow"
                rule_hits.append(RuleHit(rule_id, hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit

        return None

    def _evaluate_entry(
        self,
        ctx: Dict[str, Any],
        params: Dict[str, Any],
        regime: str,
        quantity: float,
        boll: Optional[Dict[str, float]],
        rsi_val: Optional[float],
        ma5: float,
        ma20: float,
        macd_bull: bool,
        macd_bear: bool,
        near_upper: bool,
        near_lower: bool,
        near_middle: bool,
        breakout_up: bool,
        breakout_down: bool,
        rule_hits: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        symbol = ctx["symbol"]

        if params["market_mode"] != "range_only" and self._enabled("breakout"):
            if (
                allows_direction(self.strategy_config, "long")
                and breakout_up
                and ma5 >= ma20
                and macd_bull
                and ctx["recent_change"] >= params["breakout_min_change"]
            ):
                vol_ok = True
                vol_adj = 0.0
                if self._enabled("volume_confirm"):
                    vol_ok, vol_adj = self._check_volume_confirmation(ctx, "long", True, params)
                if vol_ok:
                    signals = ["breakout_long", "trend_regime", "macd_bull"]
                    if vol_adj > 0:
                        signals.append("volume_surge")
                    hit = self._open_decision(
                        "open_long",
                        symbol,
                        quantity,
                        "短线突破追多，价格上破近端高点且动能延续",
                        min(0.95, 0.74 + vol_adj),
                        signals,
                    )
                    rule_hits.append(RuleHit("breakout", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                    return hit
            if (
                allows_direction(self.strategy_config, "short")
                and breakout_down
                and ma5 <= ma20
                and macd_bear
                and ctx["recent_change"] <= -params["breakout_min_change"]
            ):
                vol_ok = True
                vol_adj = 0.0
                if self._enabled("volume_confirm"):
                    vol_ok, vol_adj = self._check_volume_confirmation(ctx, "short", True, params)
                if vol_ok:
                    signals = ["breakout_short", "trend_regime", "macd_bear"]
                    if vol_adj > 0:
                        signals.append("volume_surge")
                    hit = self._open_decision(
                        "open_short",
                        symbol,
                        quantity,
                        "短线突破追空，价格跌破近端低点且动能延续",
                        min(0.95, 0.74 + vol_adj),
                        signals,
                    )
                    rule_hits.append(RuleHit("breakout", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                    return hit

        if regime == "ranging" and boll and self._enabled("bollinger_range"):
            rsi_ok_long = not self._enabled("rsi_threshold") or (
                rsi_val is not None and rsi_val <= params["range_rsi_long"]
            )
            rsi_ok_short = not self._enabled("rsi_threshold") or (
                rsi_val is not None and rsi_val >= params["range_rsi_short"]
            )
            if (
                allows_direction(self.strategy_config, "long")
                and near_lower
                and rsi_ok_long
                and (ctx["recent_rebound"] or not ctx["recent_fade"])
            ):
                reason = (
                    f"震荡下沿做多 RSI={rsi_val:.1f}，等待价格回归均值"
                    if rsi_val is not None
                    else "震荡下沿做多，等待价格回归均值"
                )
                hit = self._open_decision(
                    "open_long",
                    symbol,
                    quantity,
                    reason,
                    0.68,
                    ["range_regime", "boll_lower_touch", "rsi_pullback_long"],
                )
                rule_hits.append(RuleHit("bollinger_range", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit
            if (
                allows_direction(self.strategy_config, "short")
                and near_upper
                and rsi_ok_short
                and (ctx["recent_fade"] or not ctx["recent_rebound"])
            ):
                reason = (
                    f"震荡上沿做空 RSI={rsi_val:.1f}，等待价格回归均值"
                    if rsi_val is not None
                    else "震荡上沿做空，等待价格回归均值"
                )
                hit = self._open_decision(
                    "open_short",
                    symbol,
                    quantity,
                    reason,
                    0.68,
                    ["range_regime", "boll_upper_touch", "rsi_pullback_short"],
                )
                rule_hits.append(RuleHit("bollinger_range", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit

        if regime == "trending" and self._enabled("trend_follow"):
            if (
                allows_direction(self.strategy_config, "long")
                and ma5 > ma20
                and macd_bull
                and (
                    ctx["bullish_momentum"]
                    or near_middle
                    or ctx["recent_change"] >= params["breakout_min_change"]
                )
            ):
                hit = self._open_decision(
                    "open_long",
                    symbol,
                    quantity,
                    "趋势做多 MA5>MA20 且 MACD 偏强，当前为顺势参与点",
                    0.7,
                    ["trend_regime", "ma_cross_up", "macd_bull"],
                )
                rule_hits.append(RuleHit("trend_follow", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit
            if (
                allows_direction(self.strategy_config, "short")
                and ma5 < ma20
                and macd_bear
                and (
                    ctx["bearish_momentum"]
                    or near_middle
                    or ctx["recent_change"] <= -params["breakout_min_change"]
                )
            ):
                hit = self._open_decision(
                    "open_short",
                    symbol,
                    quantity,
                    "趋势做空 MA5<MA20 且 MACD 偏弱，当前为顺势参与点",
                    0.7,
                    ["trend_regime", "ma_cross_down", "macd_bear"],
                )
                rule_hits.append(RuleHit("trend_follow", hit["action"], hit["reason"], hit["confidence"], hit["signals"]).to_dict())
                return hit

        return None

    @staticmethod
    def _open_decision(
        action: str,
        symbol: str,
        quantity: float,
        reason: str,
        confidence: float,
        signals: List[str],
    ) -> Dict[str, Any]:
        return {
            "action": action,
            "symbol": symbol,
            "quantity": quantity,
            "reason": reason,
            "confidence": confidence,
            "signals": signals,
        }

    @staticmethod
    def _close_decision(
        action: str,
        symbol: str,
        reason: str,
        confidence: float,
        signals: List[str],
    ) -> Dict[str, Any]:
        return {
            "action": action,
            "symbol": symbol,
            "reason": reason,
            "confidence": confidence,
            "signals": signals,
        }

    def _check_trailing_stop(
        self,
        position: Any,
        pnl_pct: float,
        ctx: Dict[str, Any],
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not position:
            return None

        enable_pct = params["trailing_stop_enable_pct"]
        callback_pct = params["trailing_stop_callback_pct"]
        if pnl_pct < enable_pct:
            return None

        highest_pnl = getattr(position, "highest_pnl_pct", pnl_pct)
        if pnl_pct > highest_pnl:
            position.highest_pnl_pct = pnl_pct
            highest_pnl = pnl_pct

        drawdown_from_high = highest_pnl - pnl_pct
        if drawdown_from_high >= callback_pct:
            symbol = ctx["symbol"]
            return {
                "action": f"close_{position.side}",
                "symbol": symbol,
                "reason": (
                    f"跟踪止盈触发：最高盈利 {highest_pnl:.2f}%，"
                    f"当前 {pnl_pct:.2f}%，回撤 {drawdown_from_high:.2f}% 超过阈值 {callback_pct:.1f}%"
                ),
                "confidence": 0.88,
                "signals": ["trailing_stop_triggered", f"peak_pnl_{highest_pnl:.1f}pct"],
            }
        return None

    @staticmethod
    def _check_volume_confirmation(
        ctx: Dict[str, Any],
        direction: str,
        is_breakout: bool,
        params: Dict[str, Any],
    ) -> Tuple[bool, float]:
        volume_ratio = ctx.get("volume_ratio")
        if volume_ratio is None:
            return True, 0.0

        confirm_ratio = params["volume_confirm_ratio"]
        if is_breakout:
            if volume_ratio >= confirm_ratio:
                return True, 0.1
            if volume_ratio >= 1.2:
                return True, 0.0
            return False, -0.15

        if volume_ratio >= 1.3:
            return True, 0.05
        return True, 0.0
