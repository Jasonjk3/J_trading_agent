"""Bounded, credential-free results for quant research tools."""
import re
from datetime import date, datetime, timezone
from decimal import Decimal

from app.v1.services.query_contracts import utc_now

_PRIVATE = re.compile(r"secret|password|passphrase|api.?key|authorization|webhook|chain.?of.?thought|prompt|signature", re.I)


def safe_value(value, depth=0):
    if depth > 12:
        return "[嵌套内容已省略]"
    if isinstance(value, dict):
        return {str(k): safe_value(v, depth + 1) for k, v in value.items() if not _PRIVATE.search(str(k))}
    if isinstance(value, (tuple, list)):
        return [safe_value(item, depth + 1) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, str):
        return value[:4000] + ("…[已截断]" if len(value) > 4000 else "")
    return value


def fields(value, names):
    if isinstance(value, dict):
        return safe_value({name: value.get(name) for name in names})
    return safe_value({name: getattr(value, name, None) for name in names})


def result(source, data=None, *, environment="research", complete=True, warnings=None):
    return safe_value({"source": source, "environment": environment, "as_of": utc_now(),
                       "complete": complete, "warnings": warnings or [], **(data or {})})


def decimal(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("非有限数值")
    return number


def instant(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def drawdown_analysis(points, initial_capital=None):
    """Full-curve deterministic maximum drawdown (not sampled curve inference)."""
    peak = decimal(initial_capital) if initial_capital is not None else Decimal(0)
    peak_time, worst, start, trough, recovery = None, Decimal(0), None, None, None
    for point in points:
        equity = decimal(point["equity"])
        time = point["timestamp"]
        if equity > peak:
            peak, peak_time = equity, time
        if peak > 0:
            drop = (peak - equity) / peak * 100
            if drop > worst:
                worst, start, trough, recovery = drop, peak_time, time, None
    if trough is not None:
        trough_seen = False
        baseline = decimal(initial_capital) if initial_capital is not None else Decimal(0)
        for point in points:
            if not trough_seen:
                baseline = max(baseline, decimal(point["equity"]))
            if point["timestamp"] == trough:
                trough_seen = True
                continue
            if trough_seen and decimal(point["equity"]) >= baseline:
                recovery = point["timestamp"]
                break
    return safe_value({"maxDrawdownPercent": str(worst), "peakAt": start, "troughAt": trough,
                       "recoveredAt": recovery, "pointCount": len(points)})
