import asyncio
from unittest.mock import AsyncMock

from core.infrastructure.database.schema_compatibility import (
    enum_column_contains,
    ensure_runtime_schema_compatibility,
)


class _BeginContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return _BeginContext(self.connection)


def _connection_with_column_type(column_type):
    result = AsyncMock()
    result.scalar_one_or_none = lambda: column_type
    connection = AsyncMock()
    connection.execute = AsyncMock(return_value=result)
    return connection


def test_enum_column_contains_exact_enum_value():
    column_type = "enum('pending','running','completed','failed','cancelled')"
    assert enum_column_contains(column_type, "cancelled") is True
    assert enum_column_contains(column_type, "cancel") is False


def test_schema_guard_adds_missing_cancelled_status():
    connection = _connection_with_column_type(
        "enum('pending','running','completed','failed')"
    )
    changed = asyncio.run(ensure_runtime_schema_compatibility(_Engine(connection)))
    assert changed is True
    assert connection.execute.await_count == 3
    alter_sql = str(connection.execute.await_args_list[2].args[0])
    assert "ALTER TABLE `backtest_tasks`" in alter_sql
    assert "'cancelled'" in alter_sql


def test_schema_guard_is_noop_when_cancelled_status_exists():
    connection = _connection_with_column_type(
        "enum('pending','running','completed','failed','cancelled')"
    )
    changed = asyncio.run(ensure_runtime_schema_compatibility(_Engine(connection)))
    assert changed is False
    assert connection.execute.await_count == 1
