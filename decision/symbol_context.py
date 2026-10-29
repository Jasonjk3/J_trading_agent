#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从市场快照构建单 symbol 指标上下文。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backtest.indicators import compute_all_indicators, rsi as calc_rsi


def classify_trend_strength(
    adx_val: Optional[float],
    ma20_slope_pct: float,
    ind: Dict[str, Any],
) -> str:
    macd_val = ind.get("macd")
    boll = ind.get("boll") or {}
    bandwidth_pct = float(boll.get("bandwidth_pct") or 0.0)
    hist_abs = abs(macd_val["histogram"]) if macd_val else 0.0

    score = 0.0
    if adx_val is not None:
        if adx_val >= 30:
            score += 3
        elif adx_val >= 25:
            score += 2
        elif adx_val >= 20:
            score += 1

    slope_abs = abs(ma20_slope_pct)
    if slope_abs >= 0.15:
        score += 2
    elif slope_abs >= 0.08:
        score += 1

    if bandwidth_pct >= 4.0:
        score += 1
    elif bandwidth_pct >= 3.0:
        score += 0.5

    if hist_abs >= 0.1:
        score += 1

    if score >= 5:
        return "strong"
    if score >= 2.5:
        return "medium"
    return "weak"


def detect_market_regime(ctx: Dict[str, Any], params: Dict[str, Any]) -> Tuple[str, Dict[str, float]]:
    forced = params["market_mode"]
    if forced == "trend_only":
        return "trending", {"forced": 1.0}
    if forced == "range_only":
        return "ranging", {"forced": 1.0}

    ma5 = ctx["ma5"]
    ma20 = ctx["ma20"]
    current_f = ctx["current_f"]
    ind = ctx["indicators"]
    macd_val = ind.get("macd")
    boll = ind.get("boll") or {}
    rsi_val = ind.get("rsi")

    ma_gap_pct = abs(ma5 - ma20) / ma20 * 100 if ma20 else 0.0
    slope_abs = abs(ctx["ma20_slope_pct"])
    hist_pct = (
        abs(macd_val["histogram"]) / current_f * 100
        if macd_val and current_f > 0
        else 0.0
    )
    bandwidth_pct = float(boll.get("bandwidth_pct") or 0.0)

    trend_score = 0
    range_score = 0

    if ma_gap_pct >= 0.35:
        trend_score += 1
    elif ma_gap_pct <= 0.18:
        range_score += 1

    if slope_abs >= 0.12:
        trend_score += 1
    elif slope_abs <= 0.05:
        range_score += 1

    if bandwidth_pct >= 3.5:
        trend_score += 1
    elif 0 < bandwidth_pct <= 2.8:
        range_score += 1

    if hist_pct >= 0.08:
        trend_score += 1
    elif (rsi_val is None or 42 <= rsi_val <= 58) and hist_pct <= 0.05:
        range_score += 1

    if trend_score >= 3 and trend_score > range_score:
        regime = "trending"
    elif range_score >= 3 and range_score >= trend_score:
        regime = "ranging"
    else:
        regime = "trending" if (ma_gap_pct >= 0.25 and slope_abs >= 0.08) else "ranging"

    return regime, {
        "ma_gap_pct": round(ma_gap_pct, 4),
        "ma20_slope_pct": round(ctx["ma20_slope_pct"], 4),
        "hist_pct": round(hist_pct, 4),
        "bandwidth_pct": round(bandwidth_pct, 4),
        "trend_score": float(trend_score),
        "range_score": float(range_score),
    }


def build_symbol_context(snapshot: Any, symbol: str, min_bars: int = 35) -> Optional[Dict[str, Any]]:
    price = snapshot.prices.get(symbol)
    if not price:
        return None
    klines = snapshot.klines.get(symbol, [])
    if len(klines) < 20:
        return None

    closes = [float(k.close) for k in klines]
    highs = [float(k.high) for k in klines]
    lows = [float(k.low) for k in klines]
    volumes = [float(k.volume) for k in klines if hasattr(k, "volume") and k.volume is not None]
    current_f = float(price)
    ind = compute_all_indicators(
        closes,
        highs,
        lows,
        current_f,
        min_bars=min_bars,
        volumes=volumes if len(volumes) == len(klines) else None,
    )
    ma5 = ind["ma5"]
    ma20 = ind["ma20"]
    if ma5 is None or ma20 is None:
        return None

    ma5_prev = sum(closes[-6:-1]) / 5 if len(closes) >= 6 else ma5
    ma20_prev = sum(closes[-21:-1]) / 20 if len(closes) >= 21 else ma20
    ma5_slope_pct = ((ma5 - ma5_prev) / ma5_prev * 100) if ma5_prev else 0.0
    ma20_slope_pct = ((ma20 - ma20_prev) / ma20_prev * 100) if ma20_prev else 0.0
    recent_change = (
        (closes[-1] - closes[-5]) / closes[-5] * 100
        if len(closes) >= 5 and closes[-5] > 0
        else 0.0
    )
    rsi_fast = calc_rsi(closes, 7) if len(closes) >= 8 else None
    recent = klines[-3:]
    bullish_momentum = sum(1 for k in recent if k.close > k.open) >= 2
    bearish_momentum = sum(1 for k in recent if k.close < k.open) >= 2
    recent_rebound = len(closes) >= 2 and closes[-1] >= closes[-2]
    recent_fade = len(closes) >= 2 and closes[-1] <= closes[-2]
    last_bar = klines[-1]
    prev_bar = klines[-2] if len(klines) >= 2 else None
    last_bar_bullish = bool(last_bar.close >= last_bar.open)
    last_bar_bearish = bool(last_bar.close <= last_bar.open)
    higher_low = bool(prev_bar and last_bar.low >= prev_bar.low)
    lower_high = bool(prev_bar and last_bar.high <= prev_bar.high)
    lower_low = bool(prev_bar and last_bar.low < prev_bar.low)
    higher_high = bool(prev_bar and last_bar.high > prev_bar.high)
    recent_high_lookback = max(highs[-7:-1]) if len(highs) >= 7 else max(highs[:-1], default=current_f)
    recent_low_lookback = min(lows[-7:-1]) if len(lows) >= 7 else min(lows[:-1], default=current_f)
    atr_val = ind.get("atr")
    atr_pct = (float(atr_val) / current_f * 100) if atr_val and current_f > 0 else None

    adx_data = ind.get("adx")
    adx_val = adx_data.get("adx") if adx_data else None
    plus_di = adx_data.get("plus_di") if adx_data else None
    minus_di = adx_data.get("minus_di") if adx_data else None
    volume_ratio = ind.get("volume_ratio")
    volume_sma = ind.get("volume_sma")
    trend_strength = classify_trend_strength(adx_val, ma20_slope_pct, ind)

    return {
        "symbol": symbol,
        "price": price,
        "current_f": current_f,
        "klines": klines,
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": volumes,
        "indicators": ind,
        "ma5": ma5,
        "ma20": ma20,
        "ma5_slope_pct": ma5_slope_pct,
        "ma20_slope_pct": ma20_slope_pct,
        "recent_change": recent_change,
        "rsi_fast": rsi_fast,
        "bullish_momentum": bullish_momentum,
        "bearish_momentum": bearish_momentum,
        "recent_rebound": recent_rebound,
        "recent_fade": recent_fade,
        "last_bar_bullish": last_bar_bullish,
        "last_bar_bearish": last_bar_bearish,
        "higher_low": higher_low,
        "lower_high": lower_high,
        "lower_low": lower_low,
        "higher_high": higher_high,
        "recent_high_lookback": recent_high_lookback,
        "recent_low_lookback": recent_low_lookback,
        "atr_pct": atr_pct,
        "adx": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "volume_ratio": volume_ratio,
        "volume_sma": volume_sma,
        "trend_strength": trend_strength,
    }


def indicators_snapshot(ctx: Dict[str, Any]) -> Dict[str, Any]:
    ind = ctx.get("indicators") or {}
    macd_val = ind.get("macd") or {}
    return {
        "ma5": ctx.get("ma5"),
        "ma20": ctx.get("ma20"),
        "rsi_14": ind.get("rsi"),
        "macd_hist": macd_val.get("histogram") if isinstance(macd_val, dict) else None,
        "adx": ctx.get("adx"),
        "atr_pct": ctx.get("atr_pct"),
    }


def _safe_round(value: Any, digits: int = 4) -> Optional[float]:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def structured_technical_facts_from_context(
    ctx: Dict[str, Any],
    execution_tf: str = "15m",
    as_of: Any = None,
) -> Dict[str, Any]:
    """
    由快照指标上下文生成决策 Agent 可用的 technical_facts（不经技术面 LLM）。
    """
    ind = ctx.get("indicators") or {}
    macd_val = ind.get("macd") if isinstance(ind.get("macd"), dict) else {}
    boll = ind.get("boll") if isinstance(ind.get("boll"), dict) else {}
    rsi_val = ind.get("rsi")
    ma5 = ctx.get("ma5")
    ma20 = ctx.get("ma20")
    current_f = float(ctx.get("current_f") or 0)

    if ma5 is not None and ma20 is not None:
        if ma5 > ma20:
            trend = "bullish"
        elif ma5 < ma20:
            trend = "bearish"
        else:
            trend = "neutral"
    else:
        trend = "neutral"

    strength_raw = str(ctx.get("trend_strength") or "weak")
    trend_strength = {"strong": "strong", "medium": "moderate", "weak": "weak"}.get(
        strength_raw, "weak"
    )

    boll_pos = "middle"
    if boll:
        upper = boll.get("upper")
        lower = boll.get("lower")
        middle = boll.get("middle")
        if upper and lower and middle and current_f > 0:
            if current_f >= float(upper):
                boll_pos = "upper"
            elif current_f <= float(lower):
                boll_pos = "lower"
            else:
                boll_pos = "middle"

    risk_flags: List[str] = []
    if rsi_val is not None:
        if float(rsi_val) >= 70:
            risk_flags.append("overbought")
        elif float(rsi_val) <= 30:
            risk_flags.append("oversold")

    supports: List[float] = []
    resistances: List[float] = []
    if boll.get("lower") is not None:
        v = _safe_round(boll.get("lower"), 4)
        if v is not None:
            supports.append(v)
    low_lb = _safe_round(ctx.get("recent_low_lookback"), 4)
    if low_lb is not None and low_lb not in supports:
        supports.append(low_lb)
    if boll.get("upper") is not None:
        v = _safe_round(boll.get("upper"), 4)
        if v is not None:
            resistances.append(v)
    high_lb = _safe_round(ctx.get("recent_high_lookback"), 4)
    if high_lb is not None and high_lb not in resistances:
        resistances.append(high_lb)

    summary = (
        f"MA5={'%.2f' % ma5 if ma5 is not None else 'N/A'} "
        f"MA20={'%.2f' % ma20 if ma20 is not None else 'N/A'} "
        f"趋势={trend}/{trend_strength} "
        f"RSI={_safe_round(rsi_val, 1) if rsi_val is not None else 'N/A'} "
        f"ADX={_safe_round(ctx.get('adx'), 1) if ctx.get('adx') is not None else 'N/A'}"
    )

    if as_of is not None and hasattr(as_of, "replace"):
        as_of_text = as_of.replace(microsecond=0).isoformat()
    else:
        as_of_text = str(as_of or "")

    tf_fact = {
        "trend": trend,
        "trend_strength": trend_strength,
        "rsi_14": _safe_round(rsi_val, 2),
        "macd_hist": _safe_round(macd_val.get("histogram"), 4) if macd_val else None,
        "boll_pos": boll_pos,
        "atr_pct": _safe_round(ctx.get("atr_pct"), 2),
        "volume_ratio": _safe_round(ctx.get("volume_ratio"), 2),
        "supports": supports[:3],
        "resistances": resistances[:3],
        "summary": summary[:160],
        "signal_age_minutes": 0,
        "risk_flags": list(risk_flags),
        "ma5": _safe_round(ma5, 4),
        "ma20": _safe_round(ma20, 4),
        "adx": _safe_round(ctx.get("adx"), 2),
    }
    adx_value = _safe_round(ctx.get("adx"), 2)
    directional_consensus = (
        f"single_tf_{trend}"
        if trend in {"bullish", "bearish"}
        and trend_strength in {"moderate", "strong"}
        and (adx_value is None or adx_value >= 20)
        else "mixed"
    )
    return {
        "symbol": ctx.get("symbol"),
        "as_of": as_of_text,
        "execution_tf": execution_tf,
        "signal_age_minutes": 0,
        "timeframes": {execution_tf: tf_fact},
        "consensus": directional_consensus,
        "risk_flags": risk_flags[:8],
        "summary": summary[:160],
        "source": "indicator_snapshot",
    }
