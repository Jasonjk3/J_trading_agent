"""Shared query provenance and server-owned exchange environment selection."""
import os
from datetime import datetime, timezone


def trading_sandbox_mode():
    value = os.getenv("TRADING_SANDBOX_MODE", "true").strip().lower()
    if value not in {"true", "false", "1", "0"}:
        raise ValueError("TRADING_SANDBOX_MODE must be true or false")
    return value in {"true", "1"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class QueryUnavailable(RuntimeError):
    pass


def query_coverage(total, failed):
    if total and len(failed) == total:
        raise QueryUnavailable("所有账户查询失败，不能解释为空仓或零收益")
    return {"complete": not failed, "accountsRequested": total, "accountsSucceeded": total - len(failed),
            "failedAccountIds": failed, "warnings": ["部分账户查询失败，汇总不完整"] if failed else [],
            "as_of": utc_now(), "environment": "sandbox" if trading_sandbox_mode() else "live"}
