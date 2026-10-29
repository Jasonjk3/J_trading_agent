#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""规则模式决策上下文构建（不依赖 LLM 技术分析）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from decision.symbol_context import build_symbol_context, indicators_snapshot


def build_rule_decision_context(
    snapshot: Any,
    strategy_config: Optional[Dict[str, Any]],
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    从 snapshot K 线直接计算指标上下文，供 RuleDecisionEngine 使用。

    不强制要求 technical_text；若上游已注入 news_text / technical_facts 会保留合并。
    """
    cfg = strategy_config or {}
    syms = symbols or cfg.get("symbols") or []
    symbol_contexts: Dict[str, Any] = {}
    technical_facts: Dict[str, Any] = {}

    for sym in syms:
        ctx = build_symbol_context(snapshot, sym)
        if not ctx:
            continue
        symbol_contexts[sym] = ctx
        technical_facts[sym] = indicators_snapshot(ctx)

    return {
        "decision_mode": "rule",
        "technical_text": "",
        "technical_facts": technical_facts,
        "news_text": "",
        "symbol_contexts": symbol_contexts,
        "as_of": getattr(snapshot, "timestamp", None),
    }
