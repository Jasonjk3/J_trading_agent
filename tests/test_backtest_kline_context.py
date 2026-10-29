from datetime import datetime, timedelta

from backtest.backtest_engine import (
    KLINE_CONTEXT_LOOKBACK_DAYS,
    bars_for_lookback_days,
    kline_context_start,
)
from backtest.backtest_runner import _compute_kline_fetch_start, _kline_query_limit


def test_chart_and_runner_share_the_same_kline_context_start():
    start = datetime(2026, 10, 4)
    interval = "15m"
    expected_bars = bars_for_lookback_days(interval, KLINE_CONTEXT_LOOKBACK_DAYS)
    expected_start = start - timedelta(minutes=15 * expected_bars)

    assert kline_context_start(start, interval) == expected_start
    assert _compute_kline_fetch_start(start, interval) == expected_start
    assert expected_start < start - timedelta(days=7)


def test_high_frequency_context_is_not_truncated_at_ten_thousand_rows():
    start = datetime(2026, 10, 4)
    context_start = kline_context_start(start, "1m")
    end = datetime(2026, 10, 8)

    assert _kline_query_limit(context_start, end, "1m") > 10000
