"""交易员工作记忆存储。实盘使用数据库，回测默认使用隔离的内存存储。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Protocol

from sqlalchemy import select

from models.inner_models.trader_state_model import TraderStateModel
from trader.schemas import TraderState


def _db_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """MySQL DATETIME 不保存时区；统一以无时区 UTC 写入。"""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class TraderStateStore(Protocol):
    async def load(self, session_id: str) -> Optional[TraderState]: ...

    async def save(self, state: TraderState) -> None: ...


class InMemoryTraderStateStore:
    def __init__(self) -> None:
        self._states: Dict[str, TraderState] = {}
        self._lock = asyncio.Lock()

    async def load(self, session_id: str) -> Optional[TraderState]:
        async with self._lock:
            state = self._states.get(session_id)
            return state.model_copy(deep=True) if state else None

    async def save(self, state: TraderState) -> None:
        async with self._lock:
            self._states[state.session_id] = state.model_copy(deep=True)


class SqlTraderStateStore:
    """使用独立短会话保存状态，允许 Agent 在进程重启后恢复。"""

    def __init__(self, session_factory, agent_id: str) -> None:
        self._session_factory = session_factory
        self._agent_id = agent_id

    async def load(self, session_id: str) -> Optional[TraderState]:
        async with self._session_factory() as db:
            result = await db.execute(
                select(TraderStateModel).where(TraderStateModel.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return TraderState.model_validate(row.state_json)

    async def save(self, state: TraderState) -> None:
        payload = state.model_dump(mode="json")
        async with self._session_factory() as db:
            result = await db.execute(
                select(TraderStateModel).where(TraderStateModel.session_id == state.session_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = TraderStateModel(
                    session_id=state.session_id,
                    agent_id=self._agent_id,
                    revision=state.revision,
                    state_json=payload,
                    next_review_at=_db_datetime(state.next_review.at),
                )
                db.add(row)
            else:
                row.revision = state.revision
                row.state_json = payload
                row.next_review_at = _db_datetime(state.next_review.at)
            await db.commit()
