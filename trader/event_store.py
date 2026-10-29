"""只追加的交易员审计事件流。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from models.inner_models.trader_state_model import (
    TraderEventModel,
    TraderOrderProposalModel,
    TraderTurnModel,
)
from trader.schemas import OrderProposal, TraderTurn, utc_now


def _db_datetime(value: datetime) -> datetime:
    """MySQL DATETIME 不保存时区；统一以无时区 UTC 写入。"""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class TraderEventStore(Protocol):
    async def append(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        *,
        decision_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> None: ...

    async def save_turn(self, turn: TraderTurn) -> None: ...

    async def save_proposal(self, proposal: OrderProposal) -> None: ...


class InMemoryTraderEventStore:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.turns: List[TraderTurn] = []
        self.proposals: List[OrderProposal] = []
        self._lock = asyncio.Lock()

    async def append(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        *,
        decision_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> None:
        async with self._lock:
            self.events.append({
                "id": str(uuid4()),
                "session_id": session_id,
                "decision_id": decision_id,
                "event_type": event_type,
                "payload": dict(payload),
                "occurred_at": occurred_at or utc_now(),
            })

    async def save_turn(self, turn: TraderTurn) -> None:
        async with self._lock:
            self.turns.append(turn.model_copy(deep=True))

    async def save_proposal(self, proposal: OrderProposal) -> None:
        async with self._lock:
            for index, item in enumerate(self.proposals):
                if item.proposal_id == proposal.proposal_id:
                    self.proposals[index] = proposal.model_copy(deep=True)
                    break
            else:
                self.proposals.append(proposal.model_copy(deep=True))


class SqlTraderEventStore:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def append(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        *,
        decision_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> None:
        async with self._session_factory() as db:
            db.add(TraderEventModel(
                id=str(uuid4()),
                session_id=session_id,
                decision_id=decision_id,
                event_type=event_type,
                payload_json=payload,
                occurred_at=_db_datetime(occurred_at or utc_now()),
            ))
            await db.commit()

    async def save_turn(self, turn: TraderTurn) -> None:
        async with self._session_factory() as db:
            db.add(TraderTurnModel(
                decision_id=turn.decision_id,
                session_id=turn.session_id,
                as_of=_db_datetime(turn.as_of),
                status=turn.status,
                turn_json=turn.model_dump(mode="json"),
                next_review_at=(
                    _db_datetime(turn.next_review.at) if turn.next_review.at else None
                ),
            ))
            await db.commit()

    async def save_proposal(self, proposal: OrderProposal) -> None:
        async with self._session_factory() as db:
            row = await db.get(TraderOrderProposalModel, proposal.proposal_id)
            payload = proposal.model_dump(mode="json")
            if row is None:
                row = TraderOrderProposalModel(
                    proposal_id=proposal.proposal_id,
                    decision_id=proposal.decision_id,
                    session_id=proposal.session_id,
                    status=proposal.status,
                    commit_status=proposal.commit_status,
                    proposal_json=payload,
                    as_of=_db_datetime(proposal.as_of),
                )
                db.add(row)
            else:
                row.status = proposal.status
                row.commit_status = proposal.commit_status
                row.proposal_json = payload
            await db.commit()
