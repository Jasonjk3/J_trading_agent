import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
from app.v1.services.agent_conversation_service import AgentConversationService, conversation_tools
from core.agent_runtime.llm_contracts import LLMResponse, LLMUsage
from core.agent_runtime.provider import ExistingLLMProvider
from core.agent_runtime.settings import ConversationRuntimeSettings
from core.component.executor.agent_executor import AgentExecutor
from core.models.agent_models import Session, TaskStatus


class MemorySessions:
    def __init__(self):
        self.sessions, self.messages = {}, {}

    async def create_session(self, user_id, context):
        session = Session(user_id=user_id, context=context or {})
        self.sessions[session.session_id] = session
        self.messages[session.session_id] = []
        return session

    async def get_session(self, session_id, user_id=None):
        session = self.sessions.get(session_id)
        return session if session and session.user_id == user_id else None

    async def get_history(self, session_id, user_id, limit):
        return list(self.messages[session_id][-limit:])

    async def add_history(self, session_id, user_id, message):
        assert self.sessions[session_id].user_id == user_id
        self.messages[session_id].append(message)

    async def update_session(self, session_id, title, extend_ttl):
        self.sessions[session_id].title = title


class MemoryTasks:
    def __init__(self):
        self.tasks = {}

    async def update_task(self, task):
        self.tasks[task.task_id] = task


def service():
    svc = AgentConversationService(MemorySessions(), MemoryTasks(), AgentExecutor())
    svc._resolve_llm = AsyncMock(return_value=object())
    return svc


def test_real_agent_executor_uses_persisted_history_without_mutating_shared_llm(monkeypatch):
    seen = []
    async def complete(self, messages, **kwargs):
        seen.append(messages)
        return LLMResponse("结果", "test", usage=LLMUsage(5, 5, 10))
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        svc = service()
        agent = IntelligentAssistantAgent()
        original_llm = agent.llm
        first = await svc.chat(agent, "第一次", user_id="alice")
        assert first.success and first.trace_id and first.runtime["model_turns"] == 1
        assert "tool_audit" not in first.runtime
        # A reconstructed service simulates the process losing agent memory.
        restored = AgentConversationService(svc.session_store, svc.task_queue, AgentExecutor())
        restored._resolve_llm = svc._resolve_llm
        second = await restored.chat(agent, "第二次", session_id=first.session_id, user_id="alice")
        assert second.success
        assert [(m.role, m.content) for m in seen[1][1:]] == [
            ("user", "第一次"), ("assistant", "结果"), ("user", "第二次")]
        assert agent.llm is original_llm
        assert not agent.conversation_history
        assert agent.current_tasks == 0
        assert all(t.status == TaskStatus.COMPLETED for t in svc.task_queue.tasks.values())
        assert all(t.result["runtime"]["version"] == "conversation-v1" for t in svc.task_queue.tasks.values())
    asyncio.run(scenario())


def test_other_users_session_is_denied_before_history_or_model(monkeypatch):
    async def scenario():
        svc = service()
        session = await svc.session_store.create_session("victim", {})
        result = await svc.chat(IntelligentAssistantAgent(), "steal", session_id=session.session_id, user_id="attacker")
        assert not result.success and result.error_code == "SESSION_NOT_FOUND"
        svc._resolve_llm.assert_not_called()
        assert not svc.task_queue.tasks
    asyncio.run(scenario())


def test_concurrent_selected_models_remain_request_local(monkeypatch):
    async def complete(self, messages, **kwargs):
        await asyncio.sleep(0)
        return LLMResponse(self.llm.model_name, self.llm.model_name, usage=LLMUsage(5, 5, 10))
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        svc = service()
        async def resolve(agent, model_id, db_session, user_id):
            await asyncio.sleep(0)
            return SimpleNamespace(model_name=model_id)
        svc._resolve_llm = resolve
        agent = IntelligentAssistantAgent()
        a, b = await asyncio.gather(svc.chat(agent, "one", user_id="alice", model_id="model-a"),
                                    svc.chat(agent, "two", user_id="bob", model_id="model-b"))
        assert (a.response, b.response) == ("model-a", "model-b")
        assert agent.llm is None and agent.current_tasks == 0
    asyncio.run(scenario())


def test_chat_service_routes_normal_and_deep_but_has_server_rollback(monkeypatch):
    from app.v1.services.chat_service import ChatService
    from app.v1.schemas.chat_schema import ChatResponse
    async def scenario():
        svc = ChatService(object(), MemorySessions(), MemoryTasks(), AgentExecutor())
        agent = IntelligentAssistantAgent()
        svc._select_agent_direct = AsyncMock(return_value=agent)
        svc.conversation_runtime.chat = AsyncMock(return_value=ChatResponse(success=True, session_id="s", response="runtime"))
        svc._generate_title = AsyncMock(return_value=None)
        for mode in ("normal", "deep"):
            result = await svc.chat("hello", user_id="alice", thinking_mode=mode,
                                    context={"principal": "forged", "allowed_tools": ["place_order"]})
            assert result.response == "runtime"
        svc.conversation_runtime.settings = replace(svc.conversation_runtime.settings, enabled=False)
        svc.agent_executor.execute = AsyncMock(return_value={"status": "completed", "result": {"success": True, "response": "legacy"}})
        result = await svc.chat("legacy", user_id="alice")
        assert result.response == "legacy"
        assert svc.conversation_runtime.chat.await_count == 2
    asyncio.run(scenario())


def test_backtest_tool_binds_user_and_never_advertises_write_tools(monkeypatch):
    from app.v1.services.backtest_service import BacktestService
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(BacktestService, "get_by_id", lookup)
    async def scenario():
        db = object()
        tools = {t.name: t for t in conversation_tools("alice", db)}
        assert {"current_time", "market_kline", "list_backtests", "backtest_summary", "market_quote", "list_positions", "backtest_decisions"} <= set(tools)
        assert not {"place_order", "trigger_manual_decision", "stop_trading_agent", "create_backtest", "monitor_tasks"} & set(tools)
        assert all(t.side_effect == "none" and t.parameters["additionalProperties"] is False for t in tools.values())
        assert all("user_id" not in t.parameters["properties"] for t in tools.values())
        result = await tools["backtest_summary"].callback("victim-backtest")
        assert result["found"] is False
        lookup.assert_awaited_once_with(db, "victim-backtest", user_id="alice")
    asyncio.run(scenario())


def test_selected_model_preserves_managed_config_and_enforces_ownership(monkeypatch):
    from app.v1.crud import model_management_crud
    from app.v1.services import managed_llm_service
    async def scenario():
        svc = service()
        # Use the real resolver for this test, with SQL execution stubbed.
        model = SimpleNamespace(id=7, api_config_id=3, user_id="alice")
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: model)))
        config = SimpleNamespace(is_active=1, user_id="alice")
        monkeypatch.setattr(model_management_crud, "get_api_config_by_id", AsyncMock(return_value=config))
        built = object()
        builder = AsyncMock(return_value=(built, None, "Model"))
        monkeypatch.setattr(managed_llm_service, "build_llm_from_managed_model", builder)
        llm = await AgentConversationService._resolve_llm(svc, object(), "selected", db, "alice")
        assert llm is built
        builder.assert_awaited_once_with(db, 7, temperature=0.7)
        query = db.execute.call_args.args[0]
        params = query.compile().params
        assert "alice" in params.values() and "selected" in params.values()
        model.user_id = "victim"
        with pytest.raises(Exception, match="不可访问"):
            await AgentConversationService._resolve_llm(svc, object(), "selected", db, "alice")
        assert builder.await_count == 1
    asyncio.run(scenario())


def test_failed_turns_are_not_reinjected_and_tasks_keep_audit(monkeypatch):
    seen = []
    async def complete(self, messages, **kwargs):
        seen.append(messages)
        if len(seen) <= 2:
            return LLMResponse("", "test", usage=LLMUsage(5, 5, 10))
        return LLMResponse("恢复成功", "test", usage=LLMUsage(5, 5, 10))
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        svc = service()
        agent = IntelligentAssistantAgent()
        first = await svc.chat(agent, "失败问题", user_id="alice")
        assert not first.success and first.error_code == "AGENT_OUTPUT_INVALID"
        assert not svc.session_store.messages[first.session_id]
        task = next(iter(svc.task_queue.tasks.values()))
        assert task.status == TaskStatus.FAILED and task.result["runtime"]["phase"] == "failed"
        second = await svc.chat(agent, "新问题", session_id=first.session_id, user_id="alice")
        assert second.success and len(seen[-1]) == 2
    asyncio.run(scenario())


def test_same_session_requests_are_serialized(monkeypatch):
    seen = []
    async def complete(self, messages, **kwargs):
        seen.append(messages)
        await asyncio.sleep(0.01)
        return LLMResponse("答复", "test", usage=LLMUsage(5, 5, 10))
    monkeypatch.setattr(ExistingLLMProvider, "complete", complete)
    async def scenario():
        svc = service()
        session = await svc.session_store.create_session("alice", {})
        agent = IntelligentAssistantAgent()
        a, b = await asyncio.gather(svc.chat(agent, "one", session_id=session.session_id, user_id="alice"),
                                    svc.chat(agent, "two", session_id=session.session_id, user_id="alice"))
        assert a.success and b.success
        assert len(seen[0]) == 2 and len(seen[1]) == 4
    asyncio.run(scenario())


def test_default_model_cannot_inherit_mutable_legacy_request_credentials(monkeypatch):
    from core.llm.llm_factory import LLMFactory
    async def scenario():
        svc = service()
        safe = object()
        seen = []
        def create(**kwargs):
            seen.append(kwargs)
            return safe
        monkeypatch.setattr(LLMFactory, "create_llm", create)
        agent = IntelligentAssistantAgent()
        private = SimpleNamespace(api_key="another-users-private-key")
        agent.llm = private
        result = await AgentConversationService._resolve_llm(svc, agent, None, None, "alice")
        assert result is safe and agent.llm is private
        assert seen[0]["api_key_env"] == agent.LLM_CONFIG["api_key_env"]
        assert seen[0]["use_cache"] is False
    asyncio.run(scenario())
