#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""决策模式与规则类型定义。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

DecisionMode = Literal["trader", "rule"]

DEFAULT_ENABLED_RULES: List[str] = [
    "regime_detector",
    "breakout",
    "trend_follow",
    "bollinger_range",
    "rsi_threshold",
    "volume_confirm",
    "trailing_stop",
    "fixed_pct_stop",
]

RULE_PRESETS: Dict[str, List[str]] = {
    "balanced_auto": list(DEFAULT_ENABLED_RULES),
    "trend_rider": [
        "regime_detector",
        "breakout",
        "trend_follow",
        "volume_confirm",
        "trailing_stop",
        "fixed_pct_stop",
    ],
    "range_scalper": [
        "regime_detector",
        "bollinger_range",
        "rsi_threshold",
        "fixed_pct_stop",
    ],
    "conservative": [
        "regime_detector",
        "trend_follow",
        "bollinger_range",
        "trailing_stop",
        "fixed_pct_stop",
    ],
}


def resolve_decision_mode(cfg: Optional[Dict[str, Any]]) -> DecisionMode:
    """解析决策模式；旧 ``llm`` 模式已被明确废弃。"""
    cfg = cfg or {}
    explicit = str(cfg.get("decisionMode") or "trader").strip().lower()
    if explicit == "llm":
        raise ValueError("decisionMode=llm 已废弃，请迁移为 decisionMode=trader")
    if explicit in ("trader", "rule"):
        return explicit  # type: ignore[return-value]
    raise ValueError(f"不支持的 decisionMode: {explicit}")


def resolve_enabled_rules(cfg: Optional[Dict[str, Any]]) -> List[str]:
    """解析启用的规则 ID 列表。"""
    cfg = cfg or {}
    rule_cfg = cfg.get("ruleConfig") or {}
    if not isinstance(rule_cfg, dict):
        rule_cfg = {}

    preset = str(rule_cfg.get("preset") or "").strip()
    if preset and preset in RULE_PRESETS:
        enabled = list(RULE_PRESETS[preset])
    else:
        raw = rule_cfg.get("enabledRules")
        if isinstance(raw, list) and raw:
            enabled = [str(x).strip() for x in raw if str(x).strip()]
        else:
            enabled = list(DEFAULT_ENABLED_RULES)

    overrides = rule_cfg.get("disabledRules")
    if isinstance(overrides, list) and overrides:
        disabled = {str(x).strip() for x in overrides if str(x).strip()}
        enabled = [r for r in enabled if r not in disabled]

    return enabled


@dataclass
class RuleHit:
    rule_id: str
    action: str
    reason: str
    confidence: float = 0.0
    signals: List[str] = field(default_factory=list)
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
            "signals": list(self.signals),
            "score": self.score,
            "metadata": dict(self.metadata),
        }
