"""Transactional Run, step and event storage with fenced worker leases."""

import hashlib
import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, inspect, or_, select, update
from sqlalchemy.exc import IntegrityError
from models.inner_models.conversation_run_model import ConversationRunModel as Run, ConversationStepModel as Step, ConversationEventModel as Event
from models.inner_models.session_model import SessionModel
from models.inner_models.message_model import MessageModel

TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


class RunError(RuntimeError):
    def __init__(self, code, message, status_code=409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class LeaseLost(RunError):
    def __init__(self):
        super().__init__("RUN_LEASE_LOST", "执行租约已失效")


class RunControlRequested(RunError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ConversationRunRepository:
    def __init__(self, db):
        self.db = db

    async def ready(self):
        async with self.db.engine.connect() as conn:
            def check(connection):
                inspector = inspect(connection)
                for model in (Run, Step, Event):
                    name = model.__tablename__
                    if not inspector.has_table(name):
                        return False
                    columns = {column["name"] for column in inspector.get_columns(name)}
                    if not set(model.__table__.columns.keys()) <= columns:
                        return False
                for model, required in ((Run, {("idempotency_key",), ("active_session",)}),
                                         (Step, {("run_id", "step_key")})):
                    name = model.__tablename__
                    unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(name)}
                    unique.update(tuple(item["column_names"]) for item in inspector.get_indexes(name) if item.get("unique"))
                    if not required <= unique:
                        return False
                return True
            return await conn.run_sync(check)

    @staticmethod
    def event(session, run_id, kind, data=None):
        session.add(Event(run_id=run_id, event_type=kind, data=data or {}))

    async def get(self, run_id, user_id):
        async with self.db.get_session() as session:
            row = (await session.execute(select(Run).where(Run.id == run_id, Run.user_id == user_id))).scalar_one_or_none()
            if row is None:
                raise RunError("RUN_NOT_FOUND", "执行记录不存在或不可访问", 404)
            return row

    async def list_session(self, session_id, user_id, limit=50):
        async with self.db.get_session() as session:
            return (await session.execute(select(Run).where(
                Run.session_id == session_id, Run.user_id == user_id
            ).order_by(Run.created_at.desc()).limit(limit))).scalars().all()

    async def submit(self, user_id, payload, idempotency_key=None, history_limit=24):
        fingerprint = digest({key: payload.get(key) for key in ("message", "session_id", "model_id", "images")})
        key = digest([user_id, idempotency_key]) if idempotency_key else None
        try:
            async with self.db.get_session() as session:
                if key:
                    existing = (await session.execute(select(Run).where(Run.idempotency_key == key))).scalar_one_or_none()
                    if existing:
                        if existing.input_digest != fingerprint:
                            raise RunError("IDEMPOTENCY_CONFLICT", "幂等键已用于不同请求")
                        return existing, False
                session_id = payload.get("session_id")
                if session_id:
                    conversation = (await session.execute(select(SessionModel).where(
                        SessionModel.session_id == session_id, SessionModel.user_id == user_id,
                        SessionModel.is_active == True).with_for_update())).scalar_one_or_none()
                    if conversation is None or (conversation.expires_at and conversation.expires_at < datetime.now()):
                        raise RunError("SESSION_NOT_FOUND", "会话不存在或不可访问", 404)
                else:
                    session_id = str(uuid4())
                    session.add(SessionModel(session_id=session_id, user_id=user_id, title=payload["message"][:40],
                                             context={}, expires_at=datetime.now() + timedelta(hours=24)))
                history = (await session.execute(select(MessageModel).where(MessageModel.session_id == session_id,
                    MessageModel.user_id == user_id).order_by(MessageModel.id.desc()).limit(history_limit)
                    .with_for_update())).scalars().all()
                snapshot = {**payload, "session_id": session_id, "history": [
                    {"role": m.role, "content": m.content, "images": m.images} for m in reversed(history)]}
                row = Run(id=str(uuid4()), user_id=user_id, session_id=session_id, trace_id=uuid4().hex,
                          input_digest=fingerprint, idempotency_key=key, active_session=digest([user_id, session_id]),
                          payload=snapshot, status="queued", attempt=0)
                session.add(row)
                self.event(session, row.id, "run.queued")
                await session.flush()
                return row, True
        except IntegrityError:
            if key:
                async with self.db.get_session() as session:
                    existing = (await session.execute(select(Run).where(Run.idempotency_key == key))).scalar_one_or_none()
                    if existing and existing.input_digest == fingerprint:
                        return existing, False
            raise RunError("SESSION_BUSY", "此会话已有执行中的任务") from None

    async def claim(self, lease_seconds, *, run_id=None):
        now = datetime.utcnow()
        async with self.db.get_session() as session:
            eligible = or_(Run.status == "queued", and_(Run.status == "running", Run.lease_expires_at < now))
            if run_id is not None:
                eligible = and_(eligible, Run.id == run_id)
            candidate = (await session.execute(select(Run.id).where(eligible).order_by(Run.created_at).limit(1))).scalar_one_or_none()
            if candidate is None:
                return None
            token = str(uuid4())
            changed = await session.execute(update(Run).where(Run.id == candidate, eligible).values(
                status="running", lease_token=token, lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempt=Run.attempt + 1, updated_at=now))
            if changed.rowcount != 1:
                return None
            self.event(session, candidate, "run.started")
            return (await session.execute(select(Run).where(Run.id == candidate))).scalar_one()

    async def locked(self, session, run_id, token, *, allow_control=False):
        row = (await session.execute(select(Run).where(Run.id == run_id).with_for_update())).scalar_one()
        if row.status != "running" or row.lease_token != token or row.lease_expires_at <= datetime.utcnow():
            raise LeaseLost()
        if row.control and not allow_control:
            raise RunControlRequested("RUN_" + row.control.upper(), "执行控制请求")
        return row

    async def heartbeat(self, run_id, token, lease_seconds):
        async with self.db.get_session() as session:
            row = await self.locked(session, run_id, token, allow_control=True)
            row.lease_expires_at = datetime.utcnow() + timedelta(seconds=lease_seconds)
            row.updated_at = datetime.utcnow()
            return row.control

    async def step(self, run_id, token, key, kind, fingerprint, output=None):
        async with self.db.get_session() as session:
            await self.locked(session, run_id, token)
            row = (await session.execute(select(Step).where(Step.run_id == run_id, Step.step_key == key))).scalar_one_or_none()
            if row and row.input_digest != fingerprint:
                raise RunError("RUN_CHECKPOINT_MISMATCH", "执行输入与检查点不一致")
            if row and row.status == "succeeded":
                return row.output
            if row is None:
                row = Step(run_id=run_id, step_key=key, kind=kind, input_digest=fingerprint, status="running")
                session.add(row)
                self.event(session, run_id, kind + ".started", {"step_key": key})
            if output is not None:
                row.status, row.output = "succeeded", output
                self.event(session, run_id, kind + ".completed", {"step_key": key})
            return None

    async def finish(self, run_id, token, result=None, *, release=False):
        async with self.db.get_session() as session:
            row = await self.locked(session, run_id, token, allow_control=True)
            if row.control == "cancel":
                status = "cancelled"
                row.error_code, row.error = "RUN_CANCELLED", "对话已取消"
            elif row.control == "pause":
                status = "paused"
                row.error_code, row.error = "RUN_PAUSED", "对话已暂停"
            elif release:
                status = "queued"
            else:
                status = "succeeded" if result.get("success") else "failed"
                row.result = result
                row.error_code, row.error = result.get("error_code"), result.get("error")
                if status == "succeeded":
                    # Publish the answer and both history messages in one commit.
                    session.add_all([
                        MessageModel(session_id=row.session_id, user_id=row.user_id, role="user",
                                     content=row.payload["message"], images=row.payload.get("images")),
                        MessageModel(session_id=row.session_id, user_id=row.user_id, role="assistant", content=result["response"]),
                    ])
                    conversation = (await session.execute(select(SessionModel).where(SessionModel.session_id == row.session_id))).scalar_one()
                    conversation.expires_at = datetime.now() + timedelta(hours=24)
            row.status, row.control = status, None
            row.lease_token, row.lease_expires_at = None, None
            row.updated_at = datetime.utcnow()
            if status in TERMINAL:
                row.active_session = None
            data = {"error_code": row.error_code, "status": status}
            if status == "succeeded":
                data["response"] = result["response"]
                data["trace_id"] = row.trace_id
            self.event(session, run_id, "run." + status, data)
            return row

    async def control(self, run_id, user_id, operation):
        async with self.db.get_session() as session:
            row = (await session.execute(select(Run).where(Run.id == run_id, Run.user_id == user_id).with_for_update())).scalar_one_or_none()
            if row is None:
                raise RunError("RUN_NOT_FOUND", "执行记录不存在或不可访问", 404)
            if operation == "resume":
                if row.status != "paused":
                    raise RunError("RUN_NOT_PAUSED", "只有暂停的任务可以恢复")
                row.status, row.control = "queued", None
                row.error_code, row.error = None, None
            elif row.status in TERMINAL:
                return row
            elif row.status == "running":
                # A cancellation request always takes priority over pause.
                row.control = "cancel" if operation == "cancel" or row.control == "cancel" else "pause"
            else:
                row.status = "cancelled" if operation == "cancel" else "paused"
                row.error_code = "RUN_CANCELLED" if operation == "cancel" else "RUN_PAUSED"
                row.error = "对话已取消" if operation == "cancel" else "对话已暂停"
                if row.status == "cancelled":
                    row.active_session = None
            row.updated_at = datetime.utcnow()
            event_type = "run." + (row.status if row.status in {"queued", "paused", "cancelled"} else operation + "_requested")
            self.event(session, run_id, event_type, {"status": row.status, "control": row.control})
            return row

    async def events(self, run_id, user_id, after=0, limit=100):
        await self.get(run_id, user_id)
        async with self.db.get_session() as session:
            rows = (await session.execute(select(Event).where(Event.run_id == run_id, Event.id > after)
                .order_by(Event.id).limit(limit))).scalars().all()
            return [{"id": e.id, "type": e.event_type, "data": e.data} for e in rows]
