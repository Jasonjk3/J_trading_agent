#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标计算模块
用于回测与 LLM 决策的 MACD、布林带、RSI、斐波那契回撤等
输入为 float 列表，与 KlineData 解耦
"""
from typing import List, Dict, Optional, Tuple


def _ema(prices: List[float], period: int) -> List[float]:
    """指数移动平均，前 period-1 个为 None 用 0 占位，实际使用时从 period-1 下标取有效值"""
    if len(prices) < period:
        return []
    alpha = 2.0 / (period + 1)
    result: List[float] = []
    # 第一个 EMA 用前 period 的 SMA
    s = sum(prices[:period])
    for i in range(period - 1):
        result.append(0.0)  # 占位
    result.append(s / period)
    for i in range(period, len(prices)):
        ema_val = alpha * prices[i] + (1 - alpha) * result[-1]
        result.append(ema_val)
    return result


def macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Optional[Dict[str, float]]:
    """
    MACD 指标
    Returns:
        dif, dea, histogram 当前值；若数据不足返回 None
    """
    n = len(closes)
    if n < slow + signal:
        return None
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    if not ema_fast or not ema_slow or len(ema_fast) < slow or len(ema_slow) < slow:
        return None
    # DIF 从 slow-1 开始有效（两条 EMA 都有的起点）
    start = slow - 1
    dif_list = [ema_fast[start + i] - ema_slow[start + i] for i in range(n - start)]
    dea_list = _ema(dif_list, signal)
    if len(dea_list) < signal:
        return None
    # 当前为最后一根
    dif = dif_list[-1]
    dea = dea_list[-1]
    histogram = dif - dea
    return {"dif": dif, "dea": dea, "histogram": histogram}


def bollinger_bands(
    closes: List[float],
    period: int = 20,
    num_std: float = 2.0
) -> Optional[Dict[str, float]]:
    """
    布林带
    Returns:
        upper, middle, lower 当前值；若数据不足返回 None
    """
    if len(closes) < period:
        return None
    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((x - middle) ** 2 for x in window) / period
    std = variance ** 0.5 if variance > 0 else 0.0
    upper = middle + num_std * std
    lower = middle - num_std * std
    return {"upper": upper, "middle": middle, "lower": lower}


def rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """RSI，若数据不足返回 None"""
    if len(closes) < period + 1:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(change if change > 0 else 0.0)
        losses.append(-change if change < 0 else 0.0)
    # 取最近 period 段
    g = gains[-period:]
    l = losses[-period:]
    avg_gain = sum(g) / period
    avg_loss = sum(l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Optional[float]:
    """ATR，衡量当前市场波动幅度。"""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    window = trs[-period:]
    return sum(window) / period if window else None


def fibonacci_retracement(
    highs: List[float],
    lows: List[float],
    current_price: float,
    lookback: int = 20
) -> Optional[Dict[str, float]]:
    """
    斐波那契回撤位（基于 lookback 内最高最低）
    Returns:
        high, low, 以及 0.236, 0.382, 0.5, 0.618 位；若数据不足返回 None
    """
    if len(highs) < lookback or len(lows) < lookback:
        return None
    h = max(highs[-lookback:])
    l = min(lows[-lookback:])
    diff = h - l
    if diff == 0:
        return None
    levels = {
        "high": h,
        "low": l,
        "level_0": h,
        "level_236": h - 0.236 * diff,
        "level_382": h - 0.382 * diff,
        "level_500": h - 0.5 * diff,
        "level_618": h - 0.618 * diff,
        "level_100": l,
    }
    levels["current_price"] = current_price
    return levels


def _fib_position_desc(levels: Dict[str, float]) -> str:
    """根据当前价与斐波那契位的关系返回简短描述"""
    p = levels["current_price"]
    h = levels["high"]
    l = levels["low"]
    if p >= h * 0.999:
        return "接近区间高点"
    if p <= l * 1.001:
        return "接近区间低点"
    if p >= levels["level_382"]:
        return "在0.382之上（偏强）"
    if p >= levels["level_500"]:
        return "在0.382-0.5之间"
    if p >= levels["level_618"]:
        return "在0.5-0.618之间（常见支撑）"
    return "在0.618之下（偏弱）"


def adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Optional[Dict[str, float]]:
    """
    ADX (Average Directional Index) 趋势强度指标
    Returns:
        adx: ADX 值 (0-100)，>25 通常表示趋势存在
        plus_di: +DI 值
        minus_di: -DI 值
    """
    n = len(closes)
    if n < period * 2 + 1 or len(highs) < n or len(lows) < n:
        return None

    plus_dm: List[float] = []
    minus_dm: List[float] = []
    tr_list: List[float] = []

    for i in range(1, n):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]
        plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0.0)
        minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0.0)
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return None

    def wilder_smooth(data: List[float], period: int) -> List[float]:
        result = [sum(data[:period])]
        for i in range(period, len(data)):
            result.append(result[-1] - result[-1] / period + data[i])
        return result

    smoothed_tr = wilder_smooth(tr_list, period)
    smoothed_plus_dm = wilder_smooth(plus_dm, period)
    smoothed_minus_dm = wilder_smooth(minus_dm, period)

    if not smoothed_tr or smoothed_tr[-1] == 0:
        return None

    plus_di = (smoothed_plus_dm[-1] / smoothed_tr[-1]) * 100
    minus_di = (smoothed_minus_dm[-1] / smoothed_tr[-1]) * 100

    dx_list: List[float] = []
    for i in range(len(smoothed_tr)):
        di_sum = smoothed_plus_dm[i] / smoothed_tr[i] * 100 + smoothed_minus_dm[i] / smoothed_tr[i] * 100
        di_diff = abs(smoothed_plus_dm[i] / smoothed_tr[i] * 100 - smoothed_minus_dm[i] / smoothed_tr[i] * 100)
        if di_sum > 0:
            dx_list.append((di_diff / di_sum) * 100)
        else:
            dx_list.append(0.0)

    if len(dx_list) < period:
        return None

    adx_val = sum(dx_list[-period:]) / period

    return {
        "adx": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
    }


def volume_sma(volumes: List[float], period: int = 20) -> Optional[float]:
    """计算成交量简单移动平均"""
    if len(volumes) < period:
        return None
    return sum(volumes[-period:]) / period


def volume_ratio(volumes: List[float], period: int = 20) -> Optional[float]:
    """
    计算成交量比率（当前成交量 / 平均成交量）
    > 1.5 通常表示放量
    """
    if len(volumes) < period:
        return None
    avg = sum(volumes[-period:]) / period
    if avg <= 0:
        return None
    return volumes[-1] / avg if volumes else None


def compute_all_indicators(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    current_price: float,
    min_bars: int = 35,
    volumes: Optional[List[float]] = None,
) -> Dict[str, Optional[any]]:
    """
    一次性计算常用指标，供 prompt 与规则使用。
    需要至少 min_bars 根 K 线（默认 35，满足 MACD）。
    
    新增指标:
    - adx: 趋势强度指标 (ADX, +DI, -DI)
    - volume_sma: 成交量均值
    - volume_ratio: 成交量比率（放量/缩量判断）
    """
    n = len(closes)
    out: Dict[str, Optional[object]] = {
        "ma5": None,
        "ma20": None,
        "macd": None,
        "boll": None,
        "rsi": None,
        "atr": None,
        "fib": None,
        "fib_desc": None,
        "adx": None,
        "volume_sma": None,
        "volume_ratio": None,
    }
    if n < 5:
        return out
    out["ma5"] = sum(closes[-5:]) / 5
    if n >= 20:
        out["ma20"] = sum(closes[-20:]) / 20
    if n >= min_bars:
        out["macd"] = macd(closes, 12, 26, 9)
        out["boll"] = bollinger_bands(closes, 20, 2.0)
        out["rsi"] = rsi(closes, 14)
        out["atr"] = atr(highs, lows, closes, 14)
        out["adx"] = adx(highs, lows, closes, 14)
        if out["boll"] and out["boll"]["middle"]:
            middle = out["boll"]["middle"]
            out["boll"]["bandwidth_pct"] = ((out["boll"]["upper"] - out["boll"]["lower"]) / middle) * 100
    if n >= 20 and len(highs) >= 20 and len(lows) >= 20:
        fib = fibonacci_retracement(highs, lows, current_price, 20)
        out["fib"] = fib
        if fib:
            out["fib_desc"] = _fib_position_desc(fib)
    if volumes and len(volumes) >= 20:
        out["volume_sma"] = volume_sma(volumes, 20)
        out["volume_ratio"] = volume_ratio(volumes, 20)
    return out
