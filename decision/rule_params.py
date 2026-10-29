#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""规则引擎参数解析（由交易风格与策略配置推导）。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional


def _float_config(strategy_config: Dict[str, Any], key: str, default: float) -> float:
    raw = strategy_config.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def resolve_rule_params(strategy_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = strategy_config or {}
    trading_style = str(cfg.get("tradingStyle", "balanced"))

    style_defaults = {
        "conservative": {
            "position_ratio": Decimal("0.05"),
            "range_rsi_long": 36.0,
            "range_rsi_short": 64.0,
            "range_band_tolerance": 0.006,
            "trend_take_profit": 2.2,
            "trend_stop_loss": 1.4,
            "range_take_profit": 0.9,
            "range_stop_loss": 0.6,
            "breakout_buffer": 0.0015,
            "breakout_min_change": 0.45,
            "trailing_stop_enable_pct": 1.0,
            "trailing_stop_callback_pct": 0.5,
            "volume_confirm_ratio": 1.8,
        },
        "balanced": {
            "position_ratio": Decimal("0.10"),
            "range_rsi_long": 40.0,
            "range_rsi_short": 60.0,
            "range_band_tolerance": 0.010,
            "trend_take_profit": 3.0,
            "trend_stop_loss": 1.8,
            "range_take_profit": 1.2,
            "range_stop_loss": 0.8,
            "breakout_buffer": 0.0010,
            "breakout_min_change": 0.35,
            "trailing_stop_enable_pct": 0.8,
            "trailing_stop_callback_pct": 0.6,
            "volume_confirm_ratio": 1.5,
        },
        "aggressive": {
            "position_ratio": Decimal("0.15"),
            "range_rsi_long": 43.0,
            "range_rsi_short": 57.0,
            "range_band_tolerance": 0.015,
            "trend_take_profit": 4.0,
            "trend_stop_loss": 2.2,
            "range_take_profit": 1.6,
            "range_stop_loss": 1.0,
            "breakout_buffer": 0.0005,
            "breakout_min_change": 0.25,
            "trailing_stop_enable_pct": 0.6,
            "trailing_stop_callback_pct": 0.8,
            "volume_confirm_ratio": 1.3,
        },
    }
    defaults = style_defaults.get(trading_style, style_defaults["balanced"])

    range_long = _float_config(cfg, "rangeRsiLongThreshold", defaults["range_rsi_long"])
    range_short = _float_config(cfg, "rangeRsiShortThreshold", defaults["range_rsi_short"])
    if range_short <= range_long:
        range_short = max(range_long + 10.0, defaults["range_rsi_short"])

    market_mode = str(cfg.get("marketMode", "auto")).strip().lower()
    if market_mode not in {"auto", "trend_only", "range_only"}:
        market_mode = "auto"

    take_profit_mode = str(cfg.get("rangeTakeProfitMode", "mid_band")).strip().lower()
    if take_profit_mode not in {"mid_band", "opposite_band"}:
        take_profit_mode = "mid_band"

    rule_cfg = cfg.get("ruleConfig") or {}
    overrides = rule_cfg.get("overrides") if isinstance(rule_cfg, dict) else {}
    if not isinstance(overrides, dict):
        overrides = {}

    def _param(key: str, default: float) -> float:
        for rule_overrides in overrides.values():
            if isinstance(rule_overrides, dict) and key in rule_overrides:
                try:
                    return float(rule_overrides[key])
                except (TypeError, ValueError):
                    pass
        return _float_config(cfg, key, default)

    return {
        "market_mode": market_mode,
        "position_ratio": defaults["position_ratio"],
        "range_rsi_long": range_long,
        "range_rsi_short": range_short,
        "range_band_tolerance": _float_config(cfg, "rangeEntryBandTolerance", defaults["range_band_tolerance"]),
        "range_take_profit_mode": take_profit_mode,
        "trend_take_profit": defaults["trend_take_profit"],
        "trend_stop_loss": defaults["trend_stop_loss"],
        "range_take_profit": defaults["range_take_profit"],
        "range_stop_loss": defaults["range_stop_loss"],
        "breakout_buffer": defaults["breakout_buffer"],
        "breakout_min_change": defaults["breakout_min_change"],
        "trailing_stop_enable_pct": _param("trailingStopEnablePct", defaults["trailing_stop_enable_pct"]),
        "trailing_stop_callback_pct": _param("trailingStopCallbackPct", defaults["trailing_stop_callback_pct"]),
        "volume_confirm_ratio": _param("volumeConfirmRatio", defaults["volume_confirm_ratio"]),
    }


def allows_direction(strategy_config: Dict[str, Any], direction: str) -> bool:
    mode = str(strategy_config.get("positionDirection", "both")).strip().lower()
    if mode == "both":
        return True
    if direction == "long":
        return mode == "long_only"
    if direction == "short":
        return mode == "short_only"
    return False


def position_size(current_price: Decimal, account: Any, params: Dict[str, Any], strategy_config: Dict[str, Any]) -> float:
    min_amount = Decimal(str(strategy_config.get("minOrderAmount", 100)))
    max_amount = Decimal(str(strategy_config.get("maxOrderAmount", 1000)))
    style_defaults = {
        "conservative": Decimal("0.20"),
        "balanced": Decimal("0.30"),
        "aggressive": Decimal("0.50"),
    }
    trading_style = str(strategy_config.get("tradingStyle") or "balanced").strip().lower()
    fallback_ratio = style_defaults.get(trading_style, Decimal("0.30"))
    max_position_ratio_raw = strategy_config.get("maxPositionRatio")
    try:
        max_position_ratio = Decimal(str(max_position_ratio_raw)) / Decimal("100")
    except (InvalidOperation, TypeError, ValueError):
        max_position_ratio = fallback_ratio

    if max_position_ratio <= 0:
        max_position_ratio = fallback_ratio

    current_position_value = sum(
        Decimal(str(getattr(pos, "quantity", 0))) * Decimal(str(getattr(pos, "entry_price", 0)))
        for pos in account.get_all_positions()
    )
    max_position_value = account.equity * max_position_ratio
    remaining_budget = max(Decimal("0"), max_position_value - current_position_value)
    if remaining_budget < min_amount:
        return 0.0

    amount = min(max_amount, remaining_budget)
    return float(amount / current_price)
