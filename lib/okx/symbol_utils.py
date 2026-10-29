# -*- coding: utf-8 -*-
"""
OKX 交易对 / instId 规范化（与 app MarketService「大盘走势」一致）
"""


def normalize_okx_symbol(symbol: str) -> str:
    """
    将用户输入统一为 OKX 公共接口常用的 ``instId`` 形式。

    - ``BTCUSDT`` / ``btcusdt`` → ``BTC-USDT``
    - 已含 ``-`` 的（如 ``BTC-USDT``、``BTC-USDT-SWAP``）原样返回（仅 strip）
    """
    if not symbol or not isinstance(symbol, str):
        return symbol if isinstance(symbol, str) else ""
    s = symbol.strip()
    if not s:
        return s
    if "-" in s:
        return s
    s = s.upper()
    for quote in ["USDT", "USDC", "USD", "BTC", "ETH"]:
        if s.endswith(quote):
            base = s[:-len(quote)]
            return f"{base}-{quote}"
    return s
