import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
from app.v1.schemas.chat_schema import ChatRequest
from app.v1.services.agent_conversation_service import AgentConversationService
from app.v1.services.conversation_run_service import ConversationRunService
from core.agent_runtime.llm_contracts import LLMResponse, LLMUsage, ToolCall
from core.agent_runtime.provider import ExistingLLMProvider
from core.agent_runtime.run_repository import ConversationRunRepository, LeaseLost, RunError
from core.component.executor.agent_executor import AgentExecutor
from core.component.storage.session_store import SessionStore
from core.component.storage.task_queue import TaskQueue
from models.inner_models.base import Base
from models.inner_models.conversation_run_model import ConversationRunModel as Run, ConversationStepModel as Step, ConversationEventModel as Event
from models.inner_models.session_model import SessionModel
from models.inner_models.message_model import MessageModel
from models.inner_models.user_model import UserModel


class TestDB:
    __test__ = False

    def __init__(self, path):
        self.engine = create_async_engine("sqlite+aiosqlite:///" + path.as_posix())
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def get_session(self):
        async with self.factory() as session:
            async with session.begin():
                yield session


async def setup(path):
    db = TestDB(path)
    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[
            SessionModel.__table__, MessageModel.__table__, UserModel.__table__,
            Run.__table__, Step.__table__, Event.__table__]))
    async with db.get_session() as session:
        session.add(UserModel(id="owner", username="test-owner", password_hash="unused", is_active=True))
    conversation = AgentConversationService(SessionStore(db), TaskQueue(db), AgentExecutor())
    conversation._resolve_llm = AsyncMock(return_value=object())
    service = ConversationRunService(db, conversation, AgentExecutor(), poll_seconds=0.01, lease_seconds=2,
                                     heartbeat_seconds=0.02, concurrency=1)
    service.available = True
    return db, service


def answer(content="完成", calls=()):
    return LLMResponse(content, "test", usage=LLMUsage(5, 5, 10), tool_calls=tuple(calls))


async def submit(service, message="hello", session_id=None, key=None, agent=None):
    return await service.submit("owner", ChatRequest(message=message, session_id=session_id),
                                agent or IntelligentAssistantAgent(), key)


def test_repository_idempotency_owner_isolation_and_session_lock(tmp_path):
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        try:
            row, created = await submit(service, key="same")
            duplicate, created_again = await submit(service, key="same")
            assert created and not created_again and duplicate.id == row.id
            with pytest.raises(RunError) as wrong_key:
                await submit(service, message="different", key="same")
            assert wrong_key.value.code == "IDEMPOTENCY_CONFLICT"
            with pytest.raises(RunError) as wrong_owner:
                await service.repository.get(row.id, "other")
            assert wrong_owner.value.status_code == 404
            with pytest.raises(RunError) as busy:
                await submit(service, session_id=row.session_id)
            assert busy.value.code == "SESSION_BUSY"
            with pytest.raises(RunError) as session_owner:
                await service.repository.submit("other", {"message": "read", "session_id": row.session_id})
            assert session_owner.value.code == "SESSION_NOT_FOUND"
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_expired_lease_can_be_reclaimed_but_old_worker_cannot_write(tmp_path):
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        try:
            row, _ = await submit(service)
            first = await service.repository.claim(2)
            async with db.get_session() as session:
                await session.execute(update(Run).where(Run.id == row.id).values(lease_expires_at=datetime.utcnow()-timedelta(seconds=1)))
            second = await service.repository.claim(2)
            assert second.attempt == 2 and first.lease_token != second.lease_token
            with pytest.raises(LeaseLost):
                await service.repository.step(row.id, first.lease_token, "model:0", "model", "digest", {"text": "stale"})
            with pytest.raises(LeaseLost):
                await service.repository.finish(row.id, first.lease_token, {"success": True, "response": "stale"})
            await service.repository.finish(row.id, second.lease_token, {"success": True, "response": "fresh"})
            async with db.get_session() as session:
                assert (await session.execute(select(func.count()).select_from(MessageModel))).scalar_one() == 2
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_completed_run_publishes_once_and_events_are_owner_scoped(tmp_path, monkeypatch):
    responses = [answer("", [ToolCall("clock", "current_time", {})]), answer()]
    async def complete(self, *args, **kwargs):
        return responses.pop(0)
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        try:
            row, _ = await submit(service)
            assert await service.run_once()
            final = await service.repository.get(row.id, "owner")
            assert final.status == "succeeded" and final.result["response"] == "完成"
            assert final.active_session is None
            assert final.result["runtime"]["tool_audit"][0]["tool"] == "current_time"
            assert not await service.run_once()
            events = await service.repository.events(row.id, "owner")
            assert len({e["id"] for e in events}) == len(events)
            assert events[-1]["type"] == "run.succeeded" and events[-1]["data"]["response"] == "完成"
            resumed = await service.repository.events(row.id, "owner", events[0]["id"])
            assert len(resumed) == len(events)-1
            with pytest.raises(RunError):
                await service.repository.events(row.id, "other")
            async with db.get_session() as session:
                assert (await session.execute(select(func.count()).select_from(Step))).scalar_one() == 3
                assert (await session.execute(select(func.count()).select_from(MessageModel))).scalar_one() == 2
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_shutdown_and_restart_reuse_model_and_tool_checkpoints(tmp_path, monkeypatch):
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        waiting = asyncio.Event()
        calls = []
        async def complete(self, *args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return answer("", [ToolCall("clock", "current_time", {})])
            if len(calls) == 2:
                waiting.set()
                await asyncio.sleep(20)
            return answer()
        monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
        try:
            row, _ = await submit(service)
            worker = asyncio.create_task(service.run_once())
            await asyncio.wait_for(waiting.wait(), 3)
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker
            queued = await service.repository.get(row.id, "owner")
            assert queued.status == "queued"
            restarted = ConversationRunService(db, service.conversation, AgentExecutor(), heartbeat_seconds=0.02)
            assert await restarted.run_once()
            final = await service.repository.get(row.id, "owner")
            assert final.status == "succeeded" and final.attempt == 2
            assert len(calls) == 3  # First model response replayed, no extra charge.
            events = await service.repository.events(row.id, "owner")
            assert sum(e["type"] == "tool.started" for e in events) == 1
            assert sum(e["type"] == "tool.completed" for e in events) == 1
            async with db.get_session() as session:
                assert (await session.execute(select(func.count()).select_from(MessageModel))).scalar_one() == 2
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


@pytest.mark.parametrize("operation,expected", [("pause", "paused"), ("cancel", "cancelled")])
def test_running_control_stops_model_and_never_publishes_partial_answer(tmp_path, monkeypatch, operation, expected):
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        waiting = asyncio.Event()
        async def complete(self, *args, **kwargs):
            waiting.set()
            await asyncio.sleep(20)
        monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
        try:
            row, _ = await submit(service)
            worker = asyncio.create_task(service.run_once())
            await asyncio.wait_for(waiting.wait(), 3)
            await service.control(row.id, "owner", operation)
            await asyncio.wait_for(worker, 3)
            final = await service.repository.get(row.id, "owner")
            assert final.status == expected
            async with db.get_session() as session:
                assert (await session.execute(select(func.count()).select_from(MessageModel))).scalar_one() == 0
            if operation == "pause":
                await service.control(row.id, "owner", "resume")
                async def finish(self, *args, **kwargs):
                    return answer()
                monkeypatch.setattr(ExistingLLMProvider, "complete", finish)
                assert await service.run_once()
                assert (await service.repository.get(row.id, "owner")).status == "succeeded"
            else:
                with pytest.raises(RunError):
                    await service.control(row.id, "owner", "resume")
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_two_workers_cannot_claim_the_same_run(tmp_path):
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        try:
            await submit(service)
            a, b = await asyncio.gather(service.repository.claim(2), ConversationRunRepository(db).claim(2))
            assert sum(row is not None for row in (a, b)) == 1
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_http_api_identity_sse_cursor_and_controls(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from app.v1.api.conversation_run_api import router
    from app.public.dependencies.auth import get_current_user
    async def complete(self, *args, **kwargs):
        return answer("仅验证后的答案")
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        user = SimpleNamespace(id="owner")
        async def current_user():
            return user
        app = FastAPI()
        app.include_router(router, prefix="/v1")
        app.state.conversation_runs = service
        async def choose_agent(agent_name):
            assert agent_name is None
            return IntelligentAssistantAgent()
        app.state.chat_service = SimpleNamespace(_select_agent_direct=choose_agent)
        app.dependency_overrides[get_current_user] = current_user
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                created = await client.post("/v1/chat/runs", json={"message": "hello", "user_id": "other"}, headers={"Idempotency-Key": "http-test"})
                assert created.status_code == 202
                run_id = created.json()["data"]["run"]["run_id"]
                assert (await service.repository.get(run_id, "owner")).user_id == "owner"
                session_id = created.json()["data"]["run"]["session_id"]
                listing = await client.get("/v1/chat/runs", params={"session_id": session_id})
                assert listing.status_code == 200
                item = listing.json()["data"]["items"][0]
                assert item["run_id"] == run_id and item["message"] == "hello"
                assert "system_prompt" not in item and "payload" not in item
                assert (await client.get("/v1/chat/runs", params={"session_id": session_id, "limit": 101})).status_code == 422
                assert await service.run_once()
                record = await client.get(f"/v1/chat/runs/{run_id}")
                assert record.json()["data"]["response"] == "仅验证后的答案"
                events = await service.repository.events(run_id, "owner")
                stream = await client.get(f"/v1/chat/runs/{run_id}/events", headers={"Last-Event-ID": str(events[0]["id"])})
                assert stream.status_code == 200
                assert "event: run.succeeded" in stream.text and "仅验证后的答案" in stream.text
                assert "event: run.queued" not in stream.text
                assert "tool_audit" not in stream.text and "system_prompt" not in stream.text
                assert (await client.get(f"/v1/chat/runs/{run_id}/events", headers={"Last-Event-ID": "bad"})).status_code == 422
                user.id = "other"
                assert (await client.get("/v1/chat/runs", params={"session_id": session_id})).json()["data"]["items"] == []
                assert (await client.get(f"/v1/chat/runs/{run_id}")).status_code == 404
                assert (await client.get(f"/v1/chat/runs/{run_id}/events")).status_code == 404
                assert (await client.post(f"/v1/chat/runs/{run_id}/cancel")).status_code == 404
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_assistant_model_metadata_filters_private_inactive_and_shadowed_configs(tmp_path):
    from fastapi import FastAPI
    from sqlalchemy import Integer, MetaData
    from sqlalchemy.dialects.mysql import TINYINT
    from app.v1.api.chat_api import router
    from app.public.dependencies.auth import get_current_user
    from models.inner_models.model_compare_model import ModelCompareApiConfig as Config, ModelCompareModel as Model

    async def scenario():
        db, service = await setup(tmp_path / "models.sqlite3")
        try:
            metadata = MetaData()
            for table in (Config.__table__, Model.__table__):
                clone = table.to_metadata(metadata)
                for column in clone.columns:
                    if isinstance(column.type, TINYINT):
                        column.type = Integer()
            async with db.engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
            async with db.get_session() as session:
                session.add_all([
                    Config(id=1, name="shared", provider="unit", api_key="private-value", is_active=1),
                    Config(id=2, name="inactive", provider="unit", api_key="private-value", is_active=0),
                    Config(id=3, name="private", provider="unit", api_key="private-value", user_id="other", is_active=1),
                ])
                await session.flush()
                for i, (name, owner, config, active) in enumerate([
                    ("shared", None, 1, 1), ("mine", "owner", 1, 1), ("others", "other", 1, 1),
                    ("off", None, 2, 1), ("private-config", None, 3, 1), ("disabled", None, 1, 0),
                    ("shadowed", None, 1, 1), ("shadowed", "owner", 2, 1),
                ], 1):
                    session.add(Model(id=i, model_id=name, name=name, provider="unit", user_id=owner, api_config_id=config, is_active=active))
            app = FastAPI()
            app.include_router(router, prefix="/v1")
            app.state.db = db
            app.state.chat_service = SimpleNamespace(conversation_runtime=service.conversation)
            async def user():
                return SimpleNamespace(id="owner")
            app.dependency_overrides[get_current_user] = user
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                response = await client.get("/v1/chat/models")
                assert response.status_code == 200
                items = response.json()["data"]["items"]
                assert {item["model_id"] for item in items} == {"shared", "mine"}
                assert all(set(item) == {"model_id", "name", "provider"} for item in items)
                assert "private-value" not in response.text
                capability = await client.get("/v1/chat/tools")
                names = {item["name"] for item in capability.json()["data"]["items"]}
                assert len(names) == 48 and "list_positions" in names and "monitor_tasks" not in names
                assert "parameters" not in capability.text and "private-value" not in capability.text
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_sse_drains_final_event_committed_between_poll_and_status_read():
    async def scenario():
        repository = SimpleNamespace(
            events=AsyncMock(side_effect=[[], [{"id": 9, "type": "run.succeeded", "data": {"response": "final"}}]]),
            get=AsyncMock(return_value=SimpleNamespace(status="succeeded")))
        service = ConversationRunService(None, None, None, repository=repository)
        service.available = True
        events = [event async for event in service.stream("run", "owner")]
        assert len(events) == 1 and "final" in events[0]
    asyncio.run(scenario())


def test_readiness_guard_keeps_unmigrated_database_disabled(tmp_path):
    async def scenario():
        db = TestDB(tmp_path / "empty.sqlite3")
        try:
            service = ConversationRunService(db, None, None)
            await service.start()
            assert not service.available and not service._workers
            with pytest.raises(RunError) as error:
                service.require_ready()
            assert error.value.status_code == 503
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_old_synchronous_chat_uses_the_same_durable_execution(tmp_path, monkeypatch):
    from app.v1.services.chat_service import ChatService
    async def complete(self, *args, **kwargs):
        return answer()
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        try:
            chat = ChatService(object(), SessionStore(db), TaskQueue(db))
            chat._select_agent_direct = AsyncMock(return_value=IntelligentAssistantAgent())
            chat.conversation_runs = service
            request = asyncio.create_task(chat.chat("hello", user_id="owner"))
            for _ in range(100):
                if await service.run_once():
                    break
                await asyncio.sleep(0.01)
            response = await asyncio.wait_for(request, 3)
            assert response.success and response.response == "完成" and len(response.history) == 2
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_checkpoint_does_not_duplicate_raw_credential_arguments(tmp_path, monkeypatch):
    responses = [answer("", [ToolCall("unsafe", "current_time", {"api_key": "opaque-private-data"},
                                    raw_arguments='{"api_key":"opaque-private-data"}')]), answer("参数被拒绝")]
    async def complete(self, *args, **kwargs):
        return responses.pop(0)
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        try:
            row, _ = await submit(service)
            await service.run_once()
            async with db.get_session() as session:
                outputs = (await session.execute(select(Step.output).where(Step.run_id == row.id))).scalars().all()
                assert "opaque-private-data" not in __import__("json").dumps(outputs)
                assert outputs[0]["replayable"] is False
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())


def test_rollback_switch_disables_durable_workers_and_submissions(tmp_path):
    from dataclasses import replace
    async def scenario():
        db, service = await setup(tmp_path / "db.sqlite3")
        try:
            service.conversation.settings = replace(service.conversation.settings, enabled=False)
            await service.start()
            assert not service.available and not service._workers
            with pytest.raises(RunError):
                await submit(service)
        finally:
            await db.engine.dispose()
    asyncio.run(scenario())
