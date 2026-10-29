#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交易决策用的消息面/技术面上下文：由 Service 查库组装，交给 TradingDecisionAgent。
"""
import asyncio
import json
import time
from bisect import bisect_left, bisect_right
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.crud.news_intelligence_crud import get_agent_by_id_and_user, list_items
from app.v1.crud.technical_analysis_record_crud import (
    get_exact_successful_record_for_symbol_at,
    get_technical_record_for_decision_context,
)
from models.inner_models.technical_analysis_record_model import TechnicalAnalysisRecordModel

# 暂停技术面 LLM（含多周期并行生成）。决策仅消费快照指标结构化事实 + 可选消息面。
TECHNICAL_ANALYSIS_LLM_ENABLED = False


def _format_news_items(items) -> str:
    lines = []
    for it in items:
        t = it.sort_time.strftime("%Y-%m-%d %H:%M") if it.sort_time else ""
        summ = (it.summary or "")[:500]
        lines.append(f"- [{t}] {it.title}: {summ}")
    return "\n".join(lines) if lines else "（该时点之前无资讯条目）"


def _compact_technical_analysis_text(
    symbol: str,
    timeframe: Optional[str],
    analysis: Optional[Dict[str, Any]],
    summary_preview: Optional[str] = None,
) -> str:
    analysis = analysis if isinstance(analysis, dict) else {}
    lines = [f"{symbol} 技术摘要", f"- 周期: {timeframe or '-'}"]

    summary = analysis.get("summary") or summary_preview
    if isinstance(summary, str) and summary.strip():
        lines.append(f"- 市场摘要: {summary.strip()[:240]}")

    trend = analysis.get("trend") if isinstance(analysis.get("trend"), dict) else {}
    trend_desc = str(trend.get("description") or "").strip()
    if trend or trend_desc:
        lines.append(
            f"- 趋势: {trend.get('direction', 'neutral')} / {trend.get('strength', 'weak')}"
            f"{f' | {trend_desc[:120]}' if trend_desc else ''}"
        )

    momentum = analysis.get("momentum") if isinstance(analysis.get("momentum"), dict) else {}
    if momentum:
        lines.append(
            f"- 动量: RSI={momentum.get('rsi_status', 'neutral')} | "
            f"MACD={momentum.get('macd_status', 'neutral')}"
        )

    volatility = analysis.get("volatility") if isinstance(analysis.get("volatility"), dict) else {}
    if volatility:
        lines.append(
            f"- 波动: {volatility.get('status', 'medium')} | "
            f"布林位置={volatility.get('bollinger_position', 'middle')}"
        )

    sr = analysis.get("supportResistance") or analysis.get("support_resistance") or {}
    if isinstance(sr, dict) and sr:
        supports = sr.get("key_support") or []
        resistances = sr.get("key_resistance") or []
        fib = sr.get("fibonacci_levels") or sr.get("fibonacciLevels") or "N/A"
        support_text = ", ".join(str(x) for x in supports[:2]) if supports else "N/A"
        resistance_text = ", ".join(str(x) for x in resistances[:2]) if resistances else "N/A"
        lines.append(
            f"- 关键位: 支撑={support_text} | 阻力={resistance_text} | 斐波那契={fib}"
        )

    signals = analysis.get("signals") or []
    if isinstance(signals, list) and signals:
        signal_parts = []
        for item in signals[:3]:
            if isinstance(item, dict):
                indicator = item.get("indicator", "N/A")
                sig_type = item.get("type", "neutral")
                desc = str(item.get("description") or "").strip()
                signal_parts.append(
                    f"{sig_type}:{indicator}{f'({desc[:60]})' if desc else ''}"
                )
            else:
                signal_parts.append(str(item)[:60])
        lines.append(f"- 主要信号: {'; '.join(signal_parts)}")

    recommendation = analysis.get("recommendation") if isinstance(analysis.get("recommendation"), dict) else {}
    risk_warning = recommendation.get("risk_warning") or recommendation.get("riskWarning")
    if isinstance(risk_warning, str) and risk_warning.strip():
        lines.append(f"- 风险: {risk_warning.strip()[:180]}")

    if len(lines) <= 2:
        fallback = json.dumps(analysis, ensure_ascii=False) if analysis else "无结构化分析结果"
        lines.append(f"- 详情: {fallback[:300]}")
    return "\n".join(lines)


def _format_technical_service_payload(data: Dict[str, Any], symbol: str) -> str:
    """由 technical_analysis_service.analyze 返回的字典格式化为决策注入文本。"""
    if not data.get("success"):
        err = data.get("error") or "未知错误"
        return f"{symbol}: （自动生成技术面失败: {err}）"
    report = data.get("decisionReport")
    if isinstance(report, str) and report.strip():
        return report.strip()
    analysis = data.get("analysis") or {}
    return _compact_technical_analysis_text(
        symbol=symbol,
        timeframe=str(data.get("timeframe") or "-"),
        analysis=analysis if isinstance(analysis, dict) else None,
    )


def _format_technical_record(rec, symbol: str) -> str:
    if not rec:
        return f"{symbol}: （该时点之前无已成功生成的技术面分析记录）"
    payload = rec.result_payload
    if isinstance(payload, dict):
        report = payload.get("decisionReport")
        if isinstance(report, str) and report.strip():
            return report.strip()
    analysis = payload.get("analysis") if isinstance(payload, dict) else None
    return _compact_technical_analysis_text(
        symbol=symbol,
        timeframe=getattr(rec, "timeframe", None),
        analysis=analysis if isinstance(analysis, dict) else None,
        summary_preview=getattr(rec, "summary_preview", None),
    )


def _normalize_timeframe(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    tf = str(raw).strip().lower()
    aliases = {
        "60m": "1h",
        "120m": "2h",
        "240m": "4h",
        "360m": "6h",
        "720m": "12h",
        "d": "1d",
        "w": "1w",
    }
    return aliases.get(tf, tf) or None


def _timeframe_sort_key(tf: str) -> int:
    order = {
        "1m": 10,
        "5m": 20,
        "15m": 30,
        "30m": 40,
        "1h": 50,
        "2h": 60,
        "4h": 70,
        "6h": 80,
        "12h": 90,
        "1d": 100,
        "1w": 110,
    }
    return order.get(str(tf).strip().lower(), 999)


def _dedupe_timeframes(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values:
        tf = _normalize_timeframe(raw)
        if not tf or tf in seen:
            continue
        out.append(tf)
        seen.add(tf)
    return out


def _resolve_execution_timeframe(strategy_config: Dict[str, Any]) -> str:
    """解析决策执行周期：显式配置 > analysisTimeframe > interval > 15m。"""
    cfg = strategy_config or {}
    for key in ("technicalAnalysisTimeframe", "analysisTimeframe", "interval"):
        tf = _normalize_timeframe(cfg.get(key)) if cfg.get(key) else None
        if tf:
            return tf
    return "15m"


_SMALL_EXECUTION_TIMEFRAMES = frozenset({"1m", "5m", "15m"})


def _should_include_execution_in_technical_analysis(execution_tf: str) -> bool:
    key = _normalize_timeframe(execution_tf) or execution_tf
    return key not in _SMALL_EXECUTION_TIMEFRAMES


def _filter_small_technical_timeframes(timeframes: List[str]) -> List[str]:
    return [
        tf
        for tf in timeframes
        if (_normalize_timeframe(tf) or tf) not in _SMALL_EXECUTION_TIMEFRAMES
    ]


def _default_background_timeframes(execution_tf: str) -> List[str]:
    key = _normalize_timeframe(execution_tf) or "15m"
    if key in {"1m", "5m", "15m"}:
        return ["1h", "4h", "1d"]
    if key in {"30m", "1h", "2h"}:
        return ["4h", "1d"]
    if key in {"4h", "6h", "12h"}:
        return ["1d", "1w"]
    if key == "1d":
        return ["1w"]
    return []


def _resolve_analysis_timeframes(strategy_config: Dict[str, Any]) -> List[str]:
    execution_tf = _resolve_execution_timeframe(strategy_config or {})
    configured = strategy_config.get("technicalAnalysisContextTimeframes")
    if isinstance(configured, list) and configured:
        tfs = _dedupe_timeframes(configured)
    else:
        tfs = _dedupe_timeframes(_default_background_timeframes(execution_tf))

    if _should_include_execution_in_technical_analysis(execution_tf):
        exec_norm = _normalize_timeframe(execution_tf)
        existing = {_normalize_timeframe(tf) for tf in tfs}
        if exec_norm and exec_norm not in existing:
            tfs = _dedupe_timeframes([execution_tf, *tfs])

    return _filter_small_technical_timeframes(tfs)


def _resolve_effective_timeframe(strategy_config: Dict[str, Any]) -> str:
    return _resolve_execution_timeframe(strategy_config or {})


def _extract_analysis_bundle(
    timeframe: str,
    analysis: Optional[Dict[str, Any]],
    technical_facts: Optional[Dict[str, Any]] = None,
    analysis_date: Optional[str] = None,
    summary_preview: Optional[str] = None,
) -> Dict[str, Any]:
    data = analysis if isinstance(analysis, dict) else {}
    recommendation = data.get("recommendation") if isinstance(data.get("recommendation"), dict) else {}
    risk_warning = recommendation.get("risk_warning") or recommendation.get("riskWarning")
    return {
        "timeframe": _normalize_timeframe(timeframe) or str(timeframe or "-"),
        "analysis": data,
        "technical_facts": technical_facts if isinstance(technical_facts, dict) else {},
        "analysis_date": str(analysis_date or "").strip() or None,
        "summary_preview": summary_preview,
        "risk_warning": risk_warning.strip() if isinstance(risk_warning, str) and risk_warning.strip() else None,
    }


def _safe_round(value: Any, digits: int = 4) -> Optional[float]:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _normalize_strength(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"strong", "moderate", "weak"}:
        return text
    if text in {"medium", "mid"}:
        return "moderate"
    return "weak"


def _normalize_boll_pos(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "upper": "upper",
        "上轨": "upper",
        "middle": "middle",
        "mid": "middle",
        "中轨": "middle",
        "lower": "lower",
        "下轨": "lower",
    }
    return mapping.get(text, "middle")


def _parse_analysis_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) > 10:
            return datetime.fromisoformat(text.replace("Z", "+00:00").split("+")[0])
        return datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _signal_age_minutes(analysis_date: Any, as_of: datetime) -> Optional[int]:
    analysis_dt = _parse_analysis_datetime(analysis_date)
    if analysis_dt is None:
        return None
    delta = (as_of - analysis_dt).total_seconds() / 60
    return max(0, int(delta))


def _derive_timeframe_facts(entry: Dict[str, Any], as_of: datetime) -> Dict[str, Any]:
    existing = entry.get("technical_facts")
    if isinstance(existing, dict) and existing:
        fact = dict(existing)
    else:
        analysis = entry.get("analysis") or {}
        trend = analysis.get("trend") if isinstance(analysis.get("trend"), dict) else {}
        momentum = analysis.get("momentum") if isinstance(analysis.get("momentum"), dict) else {}
        volatility = analysis.get("volatility") if isinstance(analysis.get("volatility"), dict) else {}
        sr = analysis.get("supportResistance") or analysis.get("support_resistance") or {}
        fact = {
            "summary": str(analysis.get("summary") or entry.get("summary_preview") or "").strip()[:160],
            "trend": str(trend.get("direction") or "neutral").strip().lower() or "neutral",
            "trend_strength": _normalize_strength(trend.get("strength")),
            "rsi_14": None,
            "macd_hist": None,
            "boll_pos": _normalize_boll_pos(volatility.get("bollinger_position")),
            "atr_pct": None,
            "volume_ratio": None,
            "supports": [_safe_round(x, 4) for x in (sr.get("key_support") or [])[:3] if _safe_round(x, 4) is not None],
            "resistances": [_safe_round(x, 4) for x in (sr.get("key_resistance") or [])[:3] if _safe_round(x, 4) is not None],
            "risk_flags": [],
        }
        if str(momentum.get("rsi_status") or "").strip().lower() == "overbought":
            fact["risk_flags"].append("overbought")
        elif str(momentum.get("rsi_status") or "").strip().lower() == "oversold":
            fact["risk_flags"].append("oversold")

    fact["trend"] = str(fact.get("trend") or "neutral").strip().lower() or "neutral"
    fact["trend_strength"] = _normalize_strength(fact.get("trend_strength"))
    fact["boll_pos"] = _normalize_boll_pos(fact.get("boll_pos"))
    fact["signal_age_minutes"] = _signal_age_minutes(entry.get("analysis_date"), as_of)
    return {
        "trend": fact.get("trend", "neutral"),
        "trend_strength": fact.get("trend_strength", "weak"),
        "rsi_14": _safe_round(fact.get("rsi_14"), 2),
        "macd_hist": _safe_round(fact.get("macd_hist"), 4),
        "boll_pos": fact.get("boll_pos", "middle"),
        "atr_pct": _safe_round(fact.get("atr_pct"), 2),
        "volume_ratio": _safe_round(fact.get("volume_ratio"), 2),
        "supports": [_safe_round(x, 4) for x in (fact.get("supports") or [])[:3] if _safe_round(x, 4) is not None],
        "resistances": [_safe_round(x, 4) for x in (fact.get("resistances") or [])[:3] if _safe_round(x, 4) is not None],
        "summary": str(fact.get("summary") or "").strip()[:160],
        "signal_age_minutes": fact.get("signal_age_minutes"),
        "risk_flags": list(dict.fromkeys(str(x) for x in (fact.get("risk_flags") or []) if str(x).strip())),
    }


def _pick_primary_technical_timeframe(
    timeframes: Dict[str, Dict[str, Any]],
    execution_tf: str,
) -> str:
    if execution_tf in timeframes:
        return execution_tf
    if not timeframes:
        return execution_tf
    return min(timeframes.keys(), key=_timeframe_sort_key)


def _derive_symbol_consensus(timeframes: Dict[str, Dict[str, Any]], execution_tf: str) -> str:
    primary_tf = _pick_primary_technical_timeframe(timeframes, execution_tf)
    execution = timeframes.get(primary_tf) or {}
    execution_dir = execution.get("trend", "neutral")
    higher_dirs = [
        facts.get("trend", "neutral")
        for tf, facts in sorted(timeframes.items(), key=lambda item: _timeframe_sort_key(item[0]))
        if tf != primary_tf
    ]
    if execution_dir == "bullish" and any(x == "bullish" for x in higher_dirs):
        return "mtf_bullish"
    if execution_dir == "bearish" and any(x == "bearish" for x in higher_dirs):
        return "mtf_bearish"
    if execution_dir in {"bullish", "bearish"}:
        return f"single_tf_{execution_dir}"
    return "mixed"


def _build_symbol_technical_facts(
    symbol: str,
    execution_tf: str,
    entries: List[Dict[str, Any]],
    as_of: datetime,
) -> Dict[str, Any]:
    tf_map: Dict[str, Dict[str, Any]] = {}
    risk_flags: List[str] = []
    for entry in sorted(entries, key=lambda x: _timeframe_sort_key(x["timeframe"])):
        tf = entry["timeframe"]
        facts = _derive_timeframe_facts(entry, as_of)
        tf_map[tf] = facts
        for flag in facts.get("risk_flags") or []:
            if flag not in risk_flags:
                risk_flags.append(flag)

    execution_fact = tf_map.get(execution_tf) or {}
    if not execution_fact and tf_map:
        primary_tf = _pick_primary_technical_timeframe(tf_map, execution_tf)
        execution_fact = tf_map.get(primary_tf) or {}
    return {
        "symbol": symbol,
        "as_of": as_of.replace(microsecond=0).isoformat(),
        "execution_tf": execution_tf,
        "signal_age_minutes": execution_fact.get("signal_age_minutes"),
        "timeframes": tf_map,
        "consensus": _derive_symbol_consensus(tf_map, execution_tf),
        "risk_flags": risk_flags[:8],
        "summary": execution_fact.get("summary") or "",
    }


def _build_symbol_compact_text(symbol: str, symbol_facts: Dict[str, Any]) -> str:
    execution_tf = symbol_facts.get("execution_tf") or "-"
    timeframes = symbol_facts.get("timeframes") or {}
    execution = timeframes.get(execution_tf) or {}
    primary_tf = _pick_primary_technical_timeframe(timeframes, execution_tf)
    primary = timeframes.get(primary_tf) or {}
    higher_parts: List[str] = []
    for tf, facts in sorted(timeframes.items(), key=lambda item: _timeframe_sort_key(item[0])):
        if tf == primary_tf:
            continue
        higher_parts.append(f"{tf}:{facts.get('trend', 'neutral')}/{facts.get('trend_strength', 'weak')}")

    lines = [f"{symbol} 技术摘要"]
    if execution:
        lines.append(
            f"- 执行({execution_tf}): "
            f"{execution.get('trend', 'neutral')}/{execution.get('trend_strength', 'weak')} | "
            f"RSI14={execution.get('rsi_14', 'N/A')} | "
            f"MACD={execution.get('macd_hist', 'N/A')} | "
            f"布林={execution.get('boll_pos', 'middle')}"
        )
    elif primary:
        lines.append(
            f"- 主参考({primary_tf}): "
            f"{primary.get('trend', 'neutral')}/{primary.get('trend_strength', 'weak')} | "
            f"RSI14={primary.get('rsi_14', 'N/A')} | "
            f"MACD={primary.get('macd_hist', 'N/A')} | "
            f"布林={primary.get('boll_pos', 'middle')}"
        )
    if higher_parts:
        lines.append(f"- 背景: {'; '.join(higher_parts[:3])}")
    lines.append(f"- 共识: {symbol_facts.get('consensus', 'mixed')}")
    if symbol_facts.get("risk_flags"):
        lines.append(f"- 风险: {', '.join((symbol_facts.get('risk_flags') or [])[:4])}")
    return "\n".join(lines)


def _timeframe_role_label(timeframe: str, execution_tf: str) -> str:
    tf = _normalize_timeframe(timeframe) or timeframe
    if tf == execution_tf:
        return "执行周期"
    if tf in {"1h", "2h"}:
        return "确认周期"
    if tf in {"4h", "6h", "12h"}:
        return "主趋势"
    if tf in {"1d", "1w"}:
        return "大级别"
    return "背景周期"


def _build_timeframe_detail_line(entry: Dict[str, Any], execution_tf: str) -> str:
    tf = entry["timeframe"]
    label = _timeframe_role_label(tf, execution_tf)
    analysis = entry.get("analysis") or {}
    summary = analysis.get("summary") or entry.get("summary_preview")
    trend = analysis.get("trend") if isinstance(analysis.get("trend"), dict) else {}
    momentum = analysis.get("momentum") if isinstance(analysis.get("momentum"), dict) else {}
    parts: List[str] = []
    if isinstance(summary, str) and summary.strip():
        parts.append(summary.strip()[:120])
    if trend:
        parts.append(f"趋势={trend.get('direction', 'neutral')}/{trend.get('strength', 'weak')}")
    if momentum:
        parts.append(
            f"动量=RSI {momentum.get('rsi_status', 'neutral')} / MACD {momentum.get('macd_status', 'neutral')}"
        )
    if not parts:
        parts.append("暂无有效结构化结论")
    return f"- {label}({tf}): {'；'.join(parts)}"


def _trend_direction(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return "neutral"
    analysis = entry.get("analysis") or {}
    trend = analysis.get("trend") if isinstance(analysis.get("trend"), dict) else {}
    direction = str(trend.get("direction") or "neutral").strip().lower()
    return direction if direction in {"bullish", "bearish", "neutral"} else "neutral"


def _pick_first_direction(entries: List[Dict[str, Any]], timeframes: List[str]) -> str:
    lookup = {
        (_normalize_timeframe(entry.get("timeframe")) or str(entry.get("timeframe") or "")): entry
        for entry in entries
    }
    for tf in timeframes:
        direction = _trend_direction(lookup.get(tf))
        if direction != "neutral":
            return direction
    return "neutral"


def _build_multitimeframe_consensus(entries: List[Dict[str, Any]], execution_tf: str) -> str:
    direction_text = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}
    execution_tf = _normalize_timeframe(execution_tf) or execution_tf
    execution_dir = _pick_first_direction(entries, [execution_tf])
    confirm_dir = _pick_first_direction(entries, ["1h", "2h"])
    core_dir = _pick_first_direction(entries, ["4h", "6h", "12h"])
    macro_dir = _pick_first_direction(entries, ["1d", "1w"])

    higher_dir = next((x for x in [macro_dir, core_dir, confirm_dir] if x != "neutral"), "neutral")

    if execution_dir != "neutral" and core_dir != "neutral" and macro_dir != "neutral":
        if execution_dir == core_dir == macro_dir:
            return (
                f"{execution_tf}/中周期/大级别同向，属于{direction_text[execution_dir]}多周期共振，"
                "优先寻找顺势入场而非逆势猜顶抄底。"
            )
        if execution_dir != core_dir and core_dir == macro_dir:
            return (
                f"执行周期与 4h/日线主方向相反，当前更像逆大级别的短线"
                f"{'反弹' if execution_dir == 'bullish' else '回撤'}，"
                f"高周期仍以{direction_text[core_dir]}为主。"
            )
        if execution_dir == core_dir and macro_dir != execution_dir:
            return (
                f"执行周期与中周期同向，但与大级别{direction_text[macro_dir]}背景分歧，"
                "可以参与但不宜放大仓位。"
            )

    if execution_dir != "neutral" and confirm_dir != "neutral" and execution_dir == confirm_dir and core_dir == "neutral":
        return f"执行周期与确认周期同向，形成短中周期共振，但更高周期仍未给出明确方向。"

    if execution_dir != "neutral" and core_dir != "neutral":
        if execution_dir == core_dir:
            return f"执行周期与主趋势同向，当前以{direction_text[core_dir]}顺势思路为主。"
        return (
            f"执行周期与主趋势分歧，当前更像短线{'反弹' if execution_dir == 'bullish' else '回撤'}，"
            f"不要忽视高周期{direction_text[core_dir]}背景。"
        )

    if higher_dir != "neutral":
        return f"高周期主导方向为{direction_text[higher_dir]}，执行层信号需优先服从大级别方向。"
    if execution_dir != "neutral":
        return f"当前只有执行周期给出明确{direction_text[execution_dir]}倾向，高周期仍偏中性。"
    return "各周期暂未形成清晰共识，优先等待更高质量信号。"


def _build_multitimeframe_symbol_text(
    symbol: str,
    execution_tf: str,
    entries: List[Dict[str, Any]],
) -> str:
    sorted_entries = sorted(entries, key=lambda x: _timeframe_sort_key(x["timeframe"]))
    lines = [f"{symbol} 多周期技术摘要", f"- 周期覆盖: {', '.join(e['timeframe'] for e in sorted_entries)}"]
    for entry in sorted_entries:
        lines.append(_build_timeframe_detail_line(entry, execution_tf))

    lines.append(f"- 周期共识: {_build_multitimeframe_consensus(sorted_entries, execution_tf)}")

    highest_sr_entry = None
    for entry in sorted(sorted_entries, key=lambda x: _timeframe_sort_key(x["timeframe"]), reverse=True):
        analysis = entry.get("analysis") or {}
        sr = analysis.get("supportResistance") or analysis.get("support_resistance") or {}
        if isinstance(sr, dict) and (sr.get("key_support") or sr.get("key_resistance")):
            highest_sr_entry = entry
            break
    if highest_sr_entry is not None:
        sr = highest_sr_entry["analysis"].get("supportResistance") or highest_sr_entry["analysis"].get("support_resistance") or {}
        support_text = ", ".join(str(x) for x in (sr.get("key_support") or [])[:2]) or "N/A"
        resistance_text = ", ".join(str(x) for x in (sr.get("key_resistance") or [])[:2]) or "N/A"
        lines.append(
            f"- 大级别关键位({highest_sr_entry['timeframe']}): 支撑={support_text} | 阻力={resistance_text}"
        )

    risk_entry = next(
        (
            entry
            for entry in sorted(sorted_entries, key=lambda x: _timeframe_sort_key(x["timeframe"]), reverse=True)
            if entry.get("risk_warning")
        ),
        None,
    )
    if risk_entry is not None:
        lines.append(f"- 关键风险: {risk_entry['risk_warning'][:180]}")

    return "\n".join(lines)


def _resolve_max_age_hours(strategy_config: Dict[str, Any], timeframe: str) -> float:
    """
    根据策略配置和时间周期计算技术报告的最大有效时长。
    
    逻辑：
    - 如果用户在策略中配置了 technicalAnalysisMaxAgeHours，使用该值
    - 否则根据 timeframe 自动推算默认有效期，避免高周期被低频决策重复重算
    """
    explicit = strategy_config.get("technicalAnalysisMaxAgeHours")
    if explicit is not None:
        try:
            return max(0.25, float(explicit))
        except (TypeError, ValueError):
            pass

    timeframe_to_hours = {
        "1m": 0.5,
        "5m": 0.5,
        "15m": 0.5,
        "30m": 1.0,
        "1h": 1,
        "2h": 2,
        "4h": 4,
        "6h": 6,
        "12h": 12,
        "1d": 24,
        "1w": 168,
    }
    tf_lower = timeframe.strip().lower()
    return timeframe_to_hours.get(tf_lower, 4.0)


def _record_created_at(rec) -> datetime:
    created_at = getattr(rec, "created_at", None)
    return created_at if isinstance(created_at, datetime) else datetime.min


def _new_runtime_technical_bucket() -> Dict[str, Any]:
    return {
        "exact": {},
        "iso_keys": [],
        "iso_records": [],
        "date_keys": [],
        "date_records": [],
        "created_keys": [],
        "created_records": [],
    }


def _append_record_to_runtime_bucket(bucket: Dict[str, Any], rec) -> None:
    analysis_date = str(getattr(rec, "analysis_date", None) or "")
    created_at = _record_created_at(rec)

    idx_created = bisect_right(bucket["created_keys"], created_at)
    bucket["created_keys"].insert(idx_created, created_at)
    bucket["created_records"].insert(idx_created, rec)

    if not analysis_date:
        return

    prev = bucket["exact"].get(analysis_date)
    if prev is None or _record_created_at(prev) <= created_at:
        bucket["exact"][analysis_date] = rec

    analysis_key = (analysis_date, created_at)
    if len(analysis_date) > 10:
        idx = bisect_right(bucket["iso_keys"], analysis_key)
        bucket["iso_keys"].insert(idx, analysis_key)
        bucket["iso_records"].insert(idx, rec)
    else:
        idx = bisect_right(bucket["date_keys"], analysis_key)
        bucket["date_keys"].insert(idx, analysis_key)
        bucket["date_records"].insert(idx, rec)


def _is_record_stale(
    rec,
    as_of: datetime,
    max_age_hours: float = 4.0,
) -> bool:
    """
    检查技术分析记录是否过期。
    
    Args:
        rec: 技术分析记录
        as_of: 当前决策时点
        max_age_hours: 最大有效时长（小时），默认 4 小时
    
    Returns:
        True 表示记录已过期，需要重新生成
    """
    analysis_date_str = str(getattr(rec, "analysis_date", None) or "")
    if not analysis_date_str:
        created_at = _record_created_at(rec)
        if created_at == datetime.min:
            return True
        age_hours = (as_of - created_at).total_seconds() / 3600
        return age_hours > max_age_hours

    try:
        if len(analysis_date_str) > 10:
            analysis_dt = datetime.fromisoformat(analysis_date_str.replace("Z", "+00:00").split("+")[0])
        else:
            analysis_dt = datetime.strptime(analysis_date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return True

    age_hours = (as_of - analysis_dt).total_seconds() / 3600
    return age_hours > max_age_hours


def _select_runtime_cached_record(
    bucket: Dict[str, Any],
    as_of: datetime,
    as_of_marker: str,
    max_age_hours: float = 4.0,
):
    """
    从缓存中选择技术分析记录。
    
    Args:
        bucket: 缓存桶
        as_of: 决策时点
        as_of_marker: 决策时点的 ISO 格式字符串
        max_age_hours: 记录最大有效时长（小时），超过则视为未命中
    
    Returns:
        (record, match_type) 或 (None, None)
    """
    rec = bucket["exact"].get(as_of_marker)
    if rec is not None:
        if not _is_record_stale(rec, as_of, max_age_hours):
            return rec, "exact"
        logger.debug(f"技术分析记录已过期（exact match）: analysis_date={getattr(rec, 'analysis_date', None)}")

    as_of_date = as_of.strftime("%Y-%m-%d")
    best = None

    iso_idx = bisect_right(bucket["iso_keys"], (as_of_marker, datetime.max)) - 1
    if iso_idx >= 0:
        candidate = bucket["iso_records"][iso_idx]
        if not _is_record_stale(candidate, as_of, max_age_hours):
            best = candidate

    date_idx = bisect_left(bucket["date_keys"], (as_of_date, datetime.min)) - 1
    if date_idx >= 0:
        date_rec = bucket["date_records"][date_idx]
        if not _is_record_stale(date_rec, as_of, max_age_hours):
            if best is None or (
                str(getattr(date_rec, "analysis_date", "") or ""),
                _record_created_at(date_rec),
            ) > (
                str(getattr(best, "analysis_date", "") or ""),
                _record_created_at(best),
            ):
                best = date_rec

    if best is not None:
        return best, "context"

    created_idx = bisect_right(bucket["created_keys"], as_of) - 1
    if created_idx >= 0:
        candidate = bucket["created_records"][created_idx]
        if not _is_record_stale(candidate, as_of, max_age_hours):
            return candidate, "created"
        logger.debug(f"技术分析记录已过期（created fallback）: created_at={_record_created_at(candidate)}")

    return None, None


def _render_cached_record(runtime_cache: Optional[Dict[str, Any]], rec, symbol: str) -> str:
    if runtime_cache is None:
        return _format_technical_record(rec, symbol)
    rendered_cache = runtime_cache.setdefault("rendered", {})
    cache_key = (
        symbol,
        getattr(rec, "id", None),
        str(getattr(rec, "analysis_date", None) or ""),
        _record_created_at(rec).isoformat(),
    )
    text = rendered_cache.get(cache_key)
    if text is None:
        text = _format_technical_record(rec, symbol)
        rendered_cache[cache_key] = text
    return text


def _entry_from_technical_record(rec, tf: str) -> Dict[str, Any]:
    payload = rec.result_payload if isinstance(rec.result_payload, dict) else {}
    analysis = payload.get("analysis") if isinstance(payload, dict) else None
    return _extract_analysis_bundle(
        tf,
        analysis if isinstance(analysis, dict) else None,
        payload.get("technicalFacts") if isinstance(payload, dict) else None,
        getattr(rec, "analysis_date", None),
        getattr(rec, "summary_preview", None),
    )


def _entry_from_formatted_analysis(
    formatted: Dict[str, Any],
    tf: str,
    as_of_marker: str,
) -> Dict[str, Any]:
    analysis = formatted.get("analysis") if isinstance(formatted, dict) else None
    summary_preview = analysis.get("summary") if isinstance(analysis, dict) else None
    return _extract_analysis_bundle(
        tf,
        analysis if isinstance(analysis, dict) else None,
        formatted.get("technicalFacts") if isinstance(formatted, dict) else None,
        formatted.get("analysisDate") if isinstance(formatted, dict) else as_of_marker,
        summary_preview,
    )


async def _lookup_technical_record(
    session: AsyncSession,
    user_id: str,
    sym: str,
    tf: str,
    as_of: datetime,
    as_of_marker: str,
    max_age_hours: float,
    runtime_cache: Optional[Dict[str, Any]],
) -> Optional[Any]:
    """查找可用的技术分析记录，未命中返回 None。"""
    if runtime_cache is not None:
        bucket = runtime_cache.setdefault("technical", {}).setdefault(
            (sym, tf), _new_runtime_technical_bucket()
        )
        rec, _ = _select_runtime_cached_record(
            bucket, as_of, as_of_marker, max_age_hours=max_age_hours
        )
        return rec

    rec = await get_exact_successful_record_for_symbol_at(
        session, user_id, sym, as_of_marker, tf
    )
    if rec is not None and _is_record_stale(rec, as_of, max_age_hours):
        logger.debug(
            f"技术分析记录已过期（exact DB match）: "
            f"symbol={sym}, timeframe={tf}, analysis_date={getattr(rec, 'analysis_date', None)}"
        )
        rec = None

    if rec is None:
        rec = await get_technical_record_for_decision_context(
            session, user_id, sym, as_of, timeframe=tf
        )
        if rec is not None and _is_record_stale(rec, as_of, max_age_hours):
            logger.debug(
                f"技术分析记录已过期（context DB match）: "
                f"symbol={sym}, timeframe={tf}, analysis_date={getattr(rec, 'analysis_date', None)}"
            )
            rec = None
    return rec


async def _generate_technical_analysis_isolated(
    parent_session: AsyncSession,
    *,
    sym: str,
    tf: str,
    as_of_marker: str,
    lookback: int,
    llm_mid: Optional[int],
    temp: float,
    user_id: str,
) -> Tuple[str, str, Dict[str, Any]]:
    """在独立 DB 会话中生成单周期技术分析，供并行调用。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.v1.services.technical_analysis_service import technical_analysis_service

    maker = async_sessionmaker(
        bind=parent_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with maker() as isolated_session:
        try:
            formatted = await technical_analysis_service.analyze(
                symbol=sym,
                analysis_date=as_of_marker,
                timeframe=tf,
                lookback_days=lookback,
                llm_model_id=llm_mid,
                temperature=temp,
                session=isolated_session,
                user_id=user_id,
            )
            await isolated_session.commit()
            return sym, tf, formatted
        except Exception:
            await isolated_session.rollback()
            raise


async def _generate_technical_analysis_sequential(
    session: AsyncSession,
    *,
    sym: str,
    tf: str,
    as_of_marker: str,
    lookback: int,
    llm_mid: Optional[int],
    temp: float,
    user_id: str,
) -> Tuple[str, str, Dict[str, Any]]:
    """在调用方会话中串行生成单周期技术分析。"""
    from app.v1.services.technical_analysis_service import technical_analysis_service

    formatted = await technical_analysis_service.analyze(
        symbol=sym,
        analysis_date=as_of_marker,
        timeframe=tf,
        lookback_days=lookback,
        llm_model_id=llm_mid,
        temperature=temp,
        session=session,
        user_id=user_id,
    )
    try:
        await session.commit()
    except Exception as ce:
        logger.warning(f"技术面自动生成后 commit 失败: {ce}")
        try:
            await session.rollback()
        except Exception as rb_err:
            logger.warning(f"技术面 commit 失败后 session.rollback 异常: {rb_err}")
    return sym, tf, formatted


async def _generate_missing_technical_analyses(
    session: AsyncSession,
    pending: List[Tuple[str, str]],
    *,
    as_of_marker: str,
    lookback: int,
    llm_mid: Optional[int],
    temp: float,
    user_id: str,
) -> List[Tuple[str, str, Dict[str, Any]]]:
    """并行或串行生成缺失的多周期技术分析。"""
    if not TECHNICAL_ANALYSIS_LLM_ENABLED:
        logger.warning(
            f"技术面 LLM 已暂停，跳过自动生成: count={len(pending)}, pairs={pending}"
        )
        return [
            (sym, tf, {"success": False, "symbol": sym, "error": "technical_analysis_llm_paused"})
            for sym, tf in pending
        ]
    if not pending:
        return []

    for sym, tf in pending:
        logger.info(
            f"技术面无可用/有效记录，自动生成: symbol={sym}, analysis_at={as_of_marker}, "
            f"timeframe={tf}, technicalAnalysisLlmModelId={llm_mid}"
        )

    if len(pending) == 1:
        sym, tf = pending[0]
        result = await _generate_technical_analysis_sequential(
            session,
            sym=sym,
            tf=tf,
            as_of_marker=as_of_marker,
            lookback=lookback,
            llm_mid=llm_mid,
            temp=temp,
            user_id=user_id,
        )
        return [result]

    started_at = time.perf_counter()
    logger.info(
        "技术面并行自动生成: "
        f"count={len(pending)}, pairs={pending}, technicalAnalysisLlmModelId={llm_mid}"
    )
    tasks = [
        _generate_technical_analysis_isolated(
            session,
            sym=sym,
            tf=tf,
            as_of_marker=as_of_marker,
            lookback=lookback,
            llm_mid=llm_mid,
            temp=temp,
            user_id=user_id,
        )
        for sym, tf in pending
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    results: List[Tuple[str, str, Dict[str, Any]]] = []
    for item, (sym, tf) in zip(raw_results, pending):
        if isinstance(item, Exception):
            logger.error(
                f"技术面并行生成失败: symbol={sym}, timeframe={tf}, error={item}"
            )
            results.append(
                (
                    sym,
                    tf,
                    {"success": False, "symbol": sym, "error": str(item)},
                )
            )
            continue
        results.append(item)

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        f"技术面并行自动生成完成: count={len(pending)}, elapsed={elapsed_ms:.1f}ms"
    )
    return results


def _cache_generated_technical_record(
    runtime_cache: Optional[Dict[str, Any]],
    symbol: str,
    timeframe: str,
    analysis_date: str,
    formatted: Dict[str, Any],
) -> None:
    if runtime_cache is None:
        return
    technical_cache = runtime_cache.setdefault("technical", {})
    bucket = technical_cache.setdefault((symbol, timeframe), _new_runtime_technical_bucket())
    analysis = formatted.get("analysis") or {}
    summary_preview = None
    if isinstance(analysis, dict):
        summary = analysis.get("summary")
        if isinstance(summary, str) and summary.strip():
            summary_preview = summary.strip()[:500]
    rec = SimpleNamespace(
        id=formatted.get("recordId"),
        analysis_date=analysis_date,
        timeframe=timeframe,
        created_at=datetime.now(),
        summary_preview=summary_preview,
        result_payload=dict(formatted),
    )
    _append_record_to_runtime_bucket(bucket, rec)


def _snapshot_has_klines(market_snapshot: Any) -> bool:
    klines = getattr(market_snapshot, "klines", None) if market_snapshot is not None else None
    return isinstance(klines, dict) and any(bool(v) for v in klines.values())


def _fill_indicator_technical_context(
    out: Dict[str, Any],
    market_snapshot: Any,
    strategy_config: Dict[str, Any],
    symbols: List[str],
    as_of: datetime,
) -> None:
    """用快照 K 线指标填充 technical_facts / technical_text，不调用技术面 LLM。"""
    from decision.symbol_context import (
        build_symbol_context,
        structured_technical_facts_from_context,
    )

    execution_tf = _resolve_execution_timeframe(strategy_config or {})
    blocks: List[str] = []
    for sym in symbols or []:
        ctx = build_symbol_context(market_snapshot, sym)
        if not ctx:
            logger.warning(
                f"技术面指标事实跳过: symbol={sym}, reason=klines_insufficient_or_missing"
            )
            continue
        facts = structured_technical_facts_from_context(ctx, execution_tf, as_of)
        out["technical_facts"][sym] = facts
        out["signal_age_minutes"][sym] = 0
        blocks.append(_build_symbol_compact_text(sym, facts))

    if blocks:
        out["technical_text"] = "\n\n".join(blocks)
    else:
        out["technical_text"] = "（技术面 LLM 已暂停，且快照指标不足，无法生成结构化事实）"
    out["_cache_meta"] = {
        "hits": 0,
        "misses": 0,
        "generated": 0,
        "mode": "indicator_facts",
        "symbols_ready": len(blocks),
    }


async def prepare_backtest_analysis_context_cache(
    session: AsyncSession,
    user_id: str,
    strategy_config: Dict[str, Any],
    symbols: List[str],
) -> Dict[str, Any]:
    """回测启动前预加载技术分析记录索引，运行中按 as_of 在内存命中。"""
    eff_tfs = _resolve_analysis_timeframes(strategy_config or {})
    cache: Dict[str, Any] = {
        "technical": {},
        "rendered": {},
        "meta": {"timeframes": list(eff_tfs), "symbols": list(symbols or [])},
    }
    if not TECHNICAL_ANALYSIS_LLM_ENABLED:
        cache["meta"]["skipped"] = "technical_analysis_llm_paused"
        logger.info("技术面 LLM 已暂停，跳过回测技术分析记录预热")
        return cache
    symbol_list = [str(sym) for sym in symbols or [] if sym]
    if not symbol_list or not eff_tfs:
        return cache

    q = (
        select(TechnicalAnalysisRecordModel)
        .where(
            and_(
                TechnicalAnalysisRecordModel.user_id == user_id,
                TechnicalAnalysisRecordModel.success.is_(True),
                TechnicalAnalysisRecordModel.symbol.in_(symbol_list),
                func.lower(TechnicalAnalysisRecordModel.timeframe).in_([tf.lower() for tf in eff_tfs]),
            )
        )
        .order_by(
            TechnicalAnalysisRecordModel.symbol,
            TechnicalAnalysisRecordModel.timeframe,
            TechnicalAnalysisRecordModel.analysis_date,
            TechnicalAnalysisRecordModel.created_at,
        )
    )
    rows = list((await session.execute(q)).scalars().all())
    for rec in rows:
        key = (rec.symbol, _normalize_timeframe(rec.timeframe) or str(rec.timeframe).lower())
        bucket = cache["technical"].setdefault(key, _new_runtime_technical_bucket())
        _append_record_to_runtime_bucket(bucket, rec)
    logger.info(
        "回测分析缓存预热: "
        f"timeframes={eff_tfs}, symbols={len(symbol_list)}, records={len(rows)}"
    )
    return cache


async def build_trading_analysis_context(
    session: AsyncSession,
    user_id: str,
    strategy_config: Dict[str, Any],
    symbols: List[str],
    as_of: Optional[datetime] = None,
    runtime_cache: Optional[Dict[str, Any]] = None,
    market_snapshot: Any = None,
    readonly: bool = False,
) -> Dict[str, Any]:
    """
    按策略配置拉取消息面/技术面文本。

    - 回测：as_of 传当前 K 线时间，资讯按 sort_time <= as_of 取最近 N 条。
    - 技术面：默认暂停技术面 LLM（含多周期并行生成），优先用 market_snapshot 指标
      生成 technical_facts；无快照时仅读库已有记录，miss 不自动生成。
    - 实盘：as_of 默认当前时间。
    """
    cfg = strategy_config or {}
    as_of = as_of or datetime.now()
    use_news = bool(cfg.get("useNewsAnalysis"))
    use_technical = bool(symbols)
    cache_meta = {"hits": 0, "misses": 0, "generated": 0}

    out: Dict[str, Any] = {
        "news_text": "",
        "technical_text": "",
        "technical_facts": {},
        "signal_age_minutes": {},
    }

    if not use_news and not use_technical:
        return out

    if use_news:
        aid = cfg.get("newsIntelligenceAgentId")
        max_items = int(cfg.get("newsContextMaxItems") or 15)
        max_items = max(1, min(50, max_items))
        if not aid:
            out["news_text"] = "（已开启消息面但未配置 newsIntelligenceAgentId）"
        else:
            ag = await get_agent_by_id_and_user(session, str(aid), user_id)
            if not ag:
                out["news_text"] = "（消息面 Agent 不存在或不属于当前用户）"
            else:
                items, _ = await list_items(
                    session,
                    str(aid),
                    order="desc",
                    page=1,
                    page_size=max_items,
                    time_to=as_of,
                )
                out["news_text"] = _format_news_items(items)
                logger.debug(
                    f"build_trading_analysis_context: news agent={aid}, items={len(items)}, as_of={as_of}"
                )

    if use_technical:
        if readonly or not TECHNICAL_ANALYSIS_LLM_ENABLED:
            logger.info(
                "技术面 LLM 已暂停: 使用快照指标结构化事实（跳过多周期技术面 LLM 生成）"
            )
            if _snapshot_has_klines(market_snapshot):
                _fill_indicator_technical_context(out, market_snapshot, cfg, symbols, as_of)
            else:
                # 无 K 线时仅读库、不生成，避免实盘路径误触发 LLM
                await _fill_readonly_technical_context_from_db(
                    session=session,
                    user_id=user_id,
                    strategy_config=cfg,
                    symbols=symbols,
                    as_of=as_of,
                    runtime_cache=runtime_cache,
                    out=out,
                    cache_meta=cache_meta,
                )
            if any(cache_meta.values()) and "_cache_meta" not in out:
                out["_cache_meta"] = cache_meta
            return out

        lookback = int(cfg.get("technicalAnalysisLookbackDays") or 30)
        lookback = max(1, min(365, lookback))
        temp = cfg.get("technicalAnalysisTemperature")
        temp = float(temp) if temp is not None else 0.3
        llm_mid = cfg.get("technicalAnalysisLlmModelId")
        if llm_mid is not None:
            try:
                llm_mid = int(llm_mid)
            except (TypeError, ValueError):
                llm_mid = None
        timeframes = _resolve_analysis_timeframes(cfg)
        execution_tf = _resolve_execution_timeframe(cfg)

        logger.info(
            "技术面上下文追踪: "
            f"symbols={symbols}, timeframes={timeframes}, lookback={lookback}, "
            f"temperature={temp}, technicalAnalysisLlmModelId={llm_mid}, "
            f"executionTf={execution_tf}"
        )

        blocks = []
        as_of_marker = as_of.replace(microsecond=0).isoformat()
        pending_generations: List[Tuple[str, str]] = []
        cached_entries: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for sym in symbols or []:
            for tf in timeframes:
                max_age_hours = _resolve_max_age_hours(cfg, tf)
                rec = await _lookup_technical_record(
                    session,
                    user_id,
                    sym,
                    tf,
                    as_of,
                    as_of_marker,
                    max_age_hours,
                    runtime_cache,
                )
                if runtime_cache is not None:
                    if rec is not None:
                        cache_meta["hits"] += 1
                    else:
                        cache_meta["misses"] += 1

                if rec is None:
                    pending_generations.append((sym, tf))
                else:
                    cached_entries[(sym, tf)] = _entry_from_technical_record(rec, tf)

        generated_entries: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if pending_generations:
            generated_results = await _generate_missing_technical_analyses(
                session,
                pending_generations,
                as_of_marker=as_of_marker,
                lookback=lookback,
                llm_mid=llm_mid,
                temp=temp,
                user_id=user_id,
            )
            for sym, tf, formatted in generated_results:
                _cache_generated_technical_record(runtime_cache, sym, tf, as_of_marker, formatted)
                cache_meta["generated"] += 1
                generated_entries[(sym, tf)] = _entry_from_formatted_analysis(
                    formatted, tf, as_of_marker
                )

        for sym in symbols or []:
            timeframe_entries: List[Dict[str, Any]] = []
            for tf in timeframes:
                key = (sym, tf)
                if key in cached_entries:
                    timeframe_entries.append(cached_entries[key])
                elif key in generated_entries:
                    timeframe_entries.append(generated_entries[key])
                else:
                    timeframe_entries.append(
                        _extract_analysis_bundle(tf, None, None, as_of_marker, None)
                    )

            symbol_facts = _build_symbol_technical_facts(sym, execution_tf, timeframe_entries, as_of)
            out["technical_facts"][sym] = symbol_facts
            out["signal_age_minutes"][sym] = symbol_facts.get("signal_age_minutes")
            blocks.append(_build_symbol_compact_text(sym, symbol_facts))
        out["technical_text"] = (
            "\n\n".join(blocks) if blocks else "（未配置交易对，无法拉取技术面）"
        )

    if any(cache_meta.values()):
        out["_cache_meta"] = cache_meta
        logger.debug(
            "build_trading_analysis_context cache: "
            f"hits={cache_meta['hits']}, misses={cache_meta['misses']}, generated={cache_meta['generated']}"
        )

    return out


async def _fill_readonly_technical_context_from_db(
    *,
    session: AsyncSession,
    user_id: str,
    strategy_config: Dict[str, Any],
    symbols: List[str],
    as_of: datetime,
    runtime_cache: Optional[Dict[str, Any]],
    out: Dict[str, Any],
    cache_meta: Dict[str, Any],
) -> None:
    """技术面 LLM 暂停且无行情 K 线时：仅读已有记录，miss 不生成。"""
    cfg = strategy_config or {}
    timeframes = _resolve_analysis_timeframes(cfg)
    execution_tf = _resolve_execution_timeframe(cfg)
    as_of_marker = as_of.replace(microsecond=0).isoformat()
    cached_entries: Dict[Tuple[str, str], Dict[str, Any]] = {}
    misses = 0

    for sym in symbols or []:
        for tf in timeframes:
            max_age_hours = _resolve_max_age_hours(cfg, tf)
            rec = await _lookup_technical_record(
                session,
                user_id,
                sym,
                tf,
                as_of,
                as_of_marker,
                max_age_hours,
                runtime_cache,
            )
            if rec is None:
                misses += 1
                cache_meta["misses"] = cache_meta.get("misses", 0) + 1
            else:
                cache_meta["hits"] = cache_meta.get("hits", 0) + 1
                cached_entries[(sym, tf)] = _entry_from_technical_record(rec, tf)

    blocks: List[str] = []
    for sym in symbols or []:
        timeframe_entries: List[Dict[str, Any]] = []
        for tf in timeframes:
            key = (sym, tf)
            if key in cached_entries:
                timeframe_entries.append(cached_entries[key])
            else:
                timeframe_entries.append(
                    _extract_analysis_bundle(tf, None, None, as_of_marker, None)
                )
        if not any(
            (e.get("analysis") or e.get("technical_facts") or e.get("summary_preview"))
            for e in timeframe_entries
        ):
            continue
        symbol_facts = _build_symbol_technical_facts(sym, execution_tf, timeframe_entries, as_of)
        out["technical_facts"][sym] = symbol_facts
        out["signal_age_minutes"][sym] = symbol_facts.get("signal_age_minutes")
        blocks.append(_build_symbol_compact_text(sym, symbol_facts))

    if blocks:
        out["technical_text"] = "\n\n".join(blocks)
    else:
        out["technical_text"] = (
            "（技术面 LLM 已暂停：无行情 K 线且库中无可用技术面记录，请依赖决策 Agent 持有/观望）"
        )
    cache_meta["mode"] = "db_readonly_no_llm"
    cache_meta["generated"] = 0
    out["_cache_meta"] = dict(cache_meta)
    if misses:
        logger.warning(
            f"技术面 LLM 已暂停且无快照 K 线，只读库 miss={misses}，未触发自动生成"
        )
