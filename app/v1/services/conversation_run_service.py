"""Durable conversation workers and owner-scoped control/event operations."""

import asyncio
import json
import logging
import time
from contextlib import suppress
from dataclasses import asdict

from app.v1.services.agent_conversation_service import SYSTEM_INSTRUCTIONS, conversation_tools, tools_for_user
from core.agent_runtime.contracts import AgentRequest, ExecutionContext, PrincipalSnapshot, RuntimeInvocation
from core.agent_runtime.facade import AgentRuntimeFacade, user_content
from core.agent_runtime.llm_contracts import LLMMessage
from core.agent_runtime.provider import ExistingLLMProvider
from core.agent_runtime.run_journal import RunJournal
from core.agent_runtime.run_repository import ConversationRunRepository, LeaseLost, RunError, TERMINAL
from core.agent_runtime.settings import ConversationRuntimeSettings
from core.agent_runtime.tools import ConversationTool

log = logging.getLogger(__name__)


def public_run(row):
    result = row.result or {}
    return {"run_id": row.id, "session_id": row.session_id, "trace_id": row.trace_id,
            "status": row.status, "control": row.control, "attempt": row.attempt,
            "response": result.get("response"), "error_code": row.error_code, "error": row.error,
            "runtime": {k: v for k, v in (result.get("runtime") or {}).items() if k != "tool_audit"},
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}


class ConversationRunService:
    def __init__(self, db, conversation, executor, *, repository=None, poll_seconds=0.5,
                 lease_seconds=30, heartbeat_seconds=5, concurrency=2):
        if not 0 < heartbeat_seconds < lease_seconds or poll_seconds <= 0 or concurrency < 1:
            raise ValueError("invalid conversation worker configuration")
        self.db, self.conversation, self.executor = db, conversation, executor
        self.repository = repository or ConversationRunRepository(db)
        self.poll_seconds, self.lease_seconds = poll_seconds, lease_seconds
        self.heartbeat_seconds, self.concurrency = heartbeat_seconds, concurrency
        self.available = False
        self._workers, self._active = [], {}

    async def start(self):
        if self.conversation is not None and not self.conversation.settings.enabled:
            self.available = False
            return
        self.available = await self.repository.ready()
        if not self.available:
            log.warning("Conversation Run tables are absent; apply migration 022 to enable durable conversations")
            return
        if not self._workers:
            self._workers = [asyncio.create_task(self._worker(), name=f"conversation-worker-{i}") for i in range(self.concurrency)]

    async def stop(self):
        workers, self._workers = self._workers, []
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    def require_ready(self):
        if not self.available:
            raise RunError("CONVERSATION_RUN_UNAVAILABLE", "请先执行对话运行表迁移并启动 Worker", 503)

    async def submit(self, user_id, request, agent, idempotency_key=None):
        self.require_ready()
        if not user_id:
            raise RunError("AGENT_UNAUTHORIZED", "对话执行需要登录用户", 401)
        payload = {"message": request.message, "session_id": request.session_id,
                   "model_id": request.model_id, "images": request.images,
                   "agent_id": agent.agent_id, "system_prompt":
                       (getattr(agent, "_custom_system_prompt", None) or agent._get_system_prompt()) + "\n" + SYSTEM_INSTRUCTIONS,
                   "settings": asdict(self.conversation.settings), "runtime_version": "conversation-v2-durable",
                   "toolset_version": "quant-read-v1"}
        return await self.repository.submit(str(user_id), payload, idempotency_key, self.conversation.settings.history_messages)

    async def _worker(self):
        while True:
            try:
                if not await self.run_once():
                    await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Conversation worker error: %s", type(exc).__name__)
                await asyncio.sleep(self.poll_seconds)

    async def run_once(self):
        row = await self.repository.claim(self.lease_seconds)
        if row is None:
            return False
        self._active[row.id] = asyncio.current_task()
        work = asyncio.create_task(self._execute(row))
        stop_heartbeat = asyncio.Event()

        async def heartbeat():
            try:
                while True:
                    try:
                        await asyncio.wait_for(stop_heartbeat.wait(), self.heartbeat_seconds)
                        return
                    except asyncio.TimeoutError:
                        pass
                    if await self.repository.heartbeat(row.id, row.lease_token, self.lease_seconds):
                        work.cancel()
                        return
            except Exception:
                work.cancel()  # No further external work after losing lease or DB connectivity.

        beat = asyncio.create_task(heartbeat())

        async def stop_beat():
            # Do not cancel a heartbeat while its DB transaction is committing.
            # Finish it before publishing/releasing the run's lease.
            stop_heartbeat.set()
            await asyncio.shield(beat)

        try:
            result = await work
            await stop_beat()
            await self.repository.finish(row.id, row.lease_token, result)
        except asyncio.CancelledError:
            await stop_beat()
            work.cancel()
            with suppress(asyncio.CancelledError):
                await work
            with suppress(LeaseLost):
                await self.repository.finish(row.id, row.lease_token, release=True)
            if asyncio.current_task().cancelling():
                raise
        except LeaseLost:
            pass
        except Exception as exc:
            await stop_beat()
            code = exc.code if isinstance(exc, RunError) else "AGENT_EXECUTION_FAILED"
            with suppress(LeaseLost):
                await self.repository.finish(row.id, row.lease_token,
                    {"success": False, "error_code": code, "error": "对话执行失败，请检查配置后重试"})
        finally:
            with suppress(asyncio.CancelledError):
                await stop_beat()
            self._active.pop(row.id, None)
        return True

    async def _execute(self, row):
        from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
        if row.attempt > 10:
            raise RunError("RUN_RECOVERY_LIMIT", "任务恢复次数已达到上限")
        if row.payload.get("runtime_version") != "conversation-v2-durable":
            raise RunError("RUN_VERSION_MISMATCH", "运行时版本与任务检查点不兼容")
        async with self.db.get_session() as session:
            from sqlalchemy import select
            from models.inner_models.user_model import UserModel
            active = (await session.execute(select(UserModel.id).where(UserModel.id == row.user_id,
                                                                       UserModel.is_active == True))).scalar_one_or_none()
            if active is None:
                raise RunError("AGENT_UNAUTHORIZED", "任务所属用户已被停用")
            from datetime import datetime
            from models.inner_models.session_model import SessionModel
            conversation = (await session.execute(select(SessionModel).where(
                SessionModel.session_id == row.session_id, SessionModel.user_id == row.user_id,
                SessionModel.is_active == True))).scalar_one_or_none()
            if conversation is None or (conversation.expires_at and conversation.expires_at <= datetime.now()):
                raise RunError("SESSION_NOT_FOUND", "任务所属会话已失效")
            agent = IntelligentAssistantAgent(agent_id=row.payload["agent_id"])
            llm = await self.conversation._resolve_llm(agent, row.payload.get("model_id"), session, row.user_id)
        # Each tool gets a fresh DB session, not a transaction spanning model I/O.
        tools = []
        include_quant = row.payload.get("toolset_version") == "quant-read-v1"
        async with self.db.get_session() as session:
            templates = await tools_for_user(row.user_id, session, include_quant=include_quant)
        for template in templates:
            def bind(name):
                async def callback(**kwargs):
                    async with self.db.get_session() as session:
                        tool = next(t for t in await tools_for_user(row.user_id, session, include_quant=include_quant) if t.name == name)
                        return await tool.callback(**kwargs)
                return callback
            tools.append(ConversationTool(template.name, template.description, template.parameters, bind(template.name), version=template.version))
        journal = RunJournal(self.repository, row.id, row.lease_token)
        context = ExecutionContext(PrincipalSnapshot(row.user_id, frozenset(t.name for t in tools)),
                                   row.payload["agent_id"], row.session_id, trace_id=row.trace_id, journal=journal)
        history, pending = [], None
        for item in row.payload["history"]:
            if item["role"] == "user":
                pending = item
            elif item["role"] == "assistant" and pending:
                if item["content"] and not item["content"].startswith("抱歉，处理失败:"):
                    history.extend([LLMMessage("user", user_content(pending["content"], pending.get("images") or [])),
                                    LLMMessage("assistant", item["content"])])
                pending = None
        request = AgentRequest(row.payload["message"], context, row.payload["system_prompt"],
                               history=tuple(history), images=tuple(row.payload.get("images") or []))
        facade = AgentRuntimeFacade(ExistingLLMProvider(llm), tools, ConversationRuntimeSettings(**row.payload["settings"]))
        execution = await self.executor.execute(agent, {"task_id": row.id, "message": request.message, "session_id": row.session_id},
                                               context={"_conversation_runtime": RuntimeInvocation(facade, request)}, task_id=row.id)
        return execution.get("result") or {"success": False, "error_code": "AGENT_EXECUTION_FAILED", "error": "对话执行失败"}

    async def control(self, run_id, user_id, operation):
        self.require_ready()
        row = await self.repository.control(run_id, str(user_id), operation)
        # A live worker observes persisted control through heartbeat/checkpoints.
        return row

    async def stream(self, run_id, user_id, after=0):
        self.require_ready()
        heartbeat_at = time.monotonic()
        while True:
            events = await self.repository.events(run_id, str(user_id), after)
            for event in events:
                after = event["id"]
                yield f"id: {after}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            row = await self.repository.get(run_id, str(user_id))
            if row.status in TERMINAL and not events:
                # Finish and its final event commit atomically, but the event
                # query above may have preceded that commit. Drain once more
                # after observing the terminal state to avoid losing the answer.
                tail = await self.repository.events(run_id, str(user_id), after)
                for event in tail:
                    after = event["id"]
                    yield f"id: {after}\nevent: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                return
            if not events and time.monotonic() - heartbeat_at >= 15:
                yield ": keepalive\n\n"
                heartbeat_at = time.monotonic()
            await asyncio.sleep(self.poll_seconds)

    async def wait(self, run_id, user_id):
        while True:
            row = await self.repository.get(run_id, str(user_id))
            if row.status in TERMINAL or row.status == "paused":
                return row
            await asyncio.sleep(self.poll_seconds)
