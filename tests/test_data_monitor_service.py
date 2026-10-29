from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.v1.schemas.data_monitor_schema import RulePayload, TaskPayload, TemplatePayload
from app.v1.services.data_monitor_service import condition_matches, movement_values, render_template, scheduled_slot, trigger_due


def test_threshold_and_crossing_edges():
    assert condition_matches(101, 100, ">", None)
    assert not condition_matches(100, 100, ">", None)
    assert condition_matches(101, 100, "cross_up", 100)
    assert not condition_matches(101, 100, "cross_up", None)
    assert not condition_matches(101, 100, "cross_up", 101)
    assert condition_matches(99, 100, "cross_down", 100)


def test_cooldown_and_crossing():
    now = datetime.now()
    assert trigger_due(101, 100, ">", 99, False, None, 900, now)
    assert not trigger_due(101, 100, ">", 101, True, now - timedelta(minutes=5), 900, now)
    assert trigger_due(101, 100, ">", 101, True, now - timedelta(minutes=16), 900, now)
    assert trigger_due(101, 100, "cross_up", 99, False, None, 900, now)
    assert not trigger_due(101, 100, "cross_up", 101, True, now - timedelta(hours=1), 900, now)


def test_template_variables_are_explicitly_limited():
    assert render_template("{{symbol}}={{current_value}}", {"symbol": "BTC-USDT", "current_value": "101"}) == "BTC-USDT=101"
    with pytest.raises(ValidationError):
        TemplatePayload(name="bad", title="{{secret}}", content="x")


def test_task_rejects_unsupported_exchange_and_invalid_rsi():
    payload = dict(name="RSI", symbol="BTC-USDT", metric="rsi", operator=">", threshold=101,
                   pushConfigId="channel", templateId="preset-standard")
    with pytest.raises(ValidationError):
        TaskPayload(**payload)
    payload["threshold"] = 70
    payload["exchange"] = "Binance"
    with pytest.raises(ValidationError):
        TaskPayload(**payload)


def test_daily_report_slots_and_overnight_window():
    assert scheduled_slot(datetime(2026, 10, 21, 9, 59), "09:00", "18:00", 60) == datetime(2026, 10, 21, 9)
    assert scheduled_slot(datetime(2026, 10, 21, 18), "09:00", "18:00", 60) is None
    assert scheduled_slot(datetime(2026, 10, 22, 1, 15), "22:00", "02:00", 30) == datetime(2026, 10, 22, 1)


def test_movement_direction_and_units():
    assert movement_values(103, 100, "either", "percent", 3)[0]
    assert not movement_values(103, 100, "down", "percent", 3)[0]
    assert movement_values(97, 100, "down", "amount", 3)[0]
    assert movement_values(103, 100, "either", "percent", 4)[0] is False


def test_new_rule_payload_validation():
    RulePayload(name="report", ruleType="scheduled", startTime="09:00", endTime="18:00", reportIntervalMinutes=15)
    RulePayload(name="move", ruleType="movement", threshold=3, windowMinutes=60, movementUnit="percent", movementDirection="either")
    with pytest.raises(ValidationError):
        RulePayload(name="bad report", ruleType="scheduled", startTime="09:00", endTime="09:00", reportIntervalMinutes=15)
    with pytest.raises(ValidationError):
        RulePayload(name="bad move", ruleType="movement", threshold=0, windowMinutes=60, movementUnit="percent", movementDirection="either")
    with pytest.raises(ValidationError):
        TaskPayload(name="too slow", symbol="BTC-USDT", ruleType="scheduled", startTime="09:00", endTime="18:00", reportIntervalMinutes=1, frequencySeconds=300, pushConfigId="channel", templateId="preset-report")


