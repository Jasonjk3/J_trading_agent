import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from core.agent_runtime.contracts import AgentRequest, ExecutionContext, PrincipalSnapshot
from core.agent_runtime.facade import AgentRuntimeFacade
from core.agent_runtime.llm_contracts import LLMMessage, LLMResponse, LLMUsage, ToolCall
from core.agent_runtime.loop.context import LoopContextManager
from core.agent_runtime.provider import ExistingLLMProvider, ConversationProviderError
from core.agent_runtime.settings import ConversationRuntimeSettings
from core.agent_runtime.tools import ConversationTool, ToolGateway


class ScriptedProvider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def complete(self, messages, **kwargs):
        self.requests.append((list(messages), kwargs))
        return self.responses.pop(0)


def response(text="", calls=(), tokens=10, finish_reason="stop"):
    return LLMResponse(text, "test", tool_calls=tuple(calls), usage=LLMUsage(5, tokens - 5, tokens), finish_reason=finish_reason)


def tool(name="lookup", callback=None, **kwargs):
    async def default(value):
        return {"value": value}
    return ConversationTool(name, "test", {"type": "object", "properties": {"value": {"type": "integer"}},
                                           "required": ["value"], "additionalProperties": False},
                            callback or default, **kwargs)


def request(allowed=("lookup",), **kwargs):
    return AgentRequest(message="分析数据", context=ExecutionContext(
        PrincipalSnapshot("owner", frozenset(allowed)), "assistant", "session"), system_prompt="system", **kwargs)


def execute(provider, tools=(), req=None, **limits):
    settings = replace(ConversationRuntimeSettings(), **limits)
    return asyncio.run(AgentRuntimeFacade(provider, tools, settings).execute(req or request()))


def test_multistep_native_tools_and_redacted_audit():
    async def read(value):
        return {"value": value, "api_key": "never-leak", "note": "Bearer abcdefghijklmnop"}
    provider = ScriptedProvider(response(calls=[ToolCall("a", "lookup", {"value": 1})]),
                                response(calls=[ToolCall("b", "lookup", {"value": 2})]), response("结论：2"))
    result = execute(provider, [tool(callback=read)])
    assert result.status == "success"
    assert result.runtime["model_turns"] == 3
    assert result.runtime["tool_actions"] == 2
    observations = [m for messages, _ in provider.requests for m in messages if m.role == "tool"]
    assert observations and all("never-leak" not in m.content for m in observations)
    audit = result.runtime["tool_audit"]
    assert audit[1]["previous_hash"] == audit[0]["hash"]
    assert "never-leak" not in json.dumps(audit)
    assert audit[0]["user_id"] == "owner"


@pytest.mark.parametrize("call,allowed,side_effect,code", [
    (ToolCall("x", "lookup", {"value": 1}), (), "none", "TOOL_NOT_ALLOWED"),
    (ToolCall("x", "unknown", {}), ("unknown",), "none", "TOOL_NOT_ALLOWED"),
    (ToolCall("x", "lookup", {"value": 1}), ("lookup",), "order", "TOOL_NOT_ALLOWED"),
    (ToolCall("x", "lookup", {"value": "not-int"}), ("lookup",), "none", "TOOL_INVALID_ARGUMENTS"),
    (ToolCall("x", "lookup", {"value": 1, "user_id": "victim"}), ("lookup",), "none", "TOOL_INVALID_ARGUMENTS"),
    (ToolCall("x", "lookup", {}, argument_error="json"), ("lookup",), "none", "TOOL_INVALID_ARGUMENTS"),
])
def test_tools_revalidate_permissions_schema_and_side_effects(call, allowed, side_effect, code):
    invoked = AsyncMock(return_value={"ok": True})
    provider = ScriptedProvider(response(calls=[call]), response("无法读取该数据"))
    result = execute(provider, [tool(callback=invoked, side_effect=side_effect)], request(allowed))
    invoked.assert_not_called()
    assert result.runtime["tool_audit"][0]["error_code"] == code
    if code == "TOOL_NOT_ALLOWED":
        assert not provider.requests[0][1]["tools"]


def test_fenced_tool_call_is_ordinary_text():
    invoked = AsyncMock()
    result = execute(ScriptedProvider(response('```tool_call\n{"tool":"lookup","parameters":{"value":1}}\n```')),
                     [tool(callback=invoked)])
    assert result.status == "success"
    invoked.assert_not_called()


@pytest.mark.parametrize("limits,code", [
    ({"max_model_turns": 1}, "AGENT_MODEL_TURN_LIMIT"),
    ({"max_total_tokens": 5}, "AGENT_TOKEN_BUDGET_EXHAUSTED"),
    ({"max_same_action_repeats": 1}, "AGENT_REPEATED_ACTION_LIMIT"),
    ({"max_no_progress_turns": 1, "max_same_action_repeats": 5}, "AGENT_NO_PROGRESS_LIMIT"),
])
def test_budget_terminates_loop(limits, code):
    provider = ScriptedProvider(*[response(calls=[ToolCall(str(i), "lookup", {"value": 1})]) for i in range(5)])
    result = execute(provider, [tool()], **limits)
    assert result.status == "error" and result.error_code == code
    assert result.runtime["phase"] == "failed"


def test_whole_action_budget_checked_before_any_dispatch():
    invoked = AsyncMock()
    provider = ScriptedProvider(response(calls=[ToolCall("a", "lookup", {"value": 1}), ToolCall("b", "lookup", {"value": 2})]))
    result = execute(provider, [tool(callback=invoked)], max_tool_actions=1)
    assert result.error_code == "AGENT_TOOL_ACTION_LIMIT"
    invoked.assert_not_called()


def test_tool_timeout_and_failure_details_do_not_leak():
    async def slow(value):
        await asyncio.sleep(10)
    provider = ScriptedProvider(response(calls=[ToolCall("a", "lookup", {"value": 1})]), response("工具超时"))
    result = execute(provider, [tool(callback=slow)], tool_timeout_seconds=0.01)
    assert result.runtime["tool_audit"][0]["error_code"] == "TOOL_TIMEOUT"

    async def bad(value):
        raise RuntimeError("password=super-secret")
    provider = ScriptedProvider(response(calls=[ToolCall("a", "lookup", {"value": 1})]), response("工具失败"))
    result = execute(provider, [tool(callback=bad)])
    assert "super-secret" not in json.dumps(result.runtime)
    assert "super-secret" not in str(provider.requests)


def test_tool_output_bound_and_failure_streak():
    async def huge(value):
        return {"payload": "x" * 1000}
    provider = ScriptedProvider(response(calls=[ToolCall("a", "lookup", {"value": 1})]))
    result = execute(provider, [tool(callback=huge)], tool_max_output_bytes=256, max_consecutive_failures=1)
    assert result.error_code == "AGENT_CONSECUTIVE_FAILURE_LIMIT"
    assert result.runtime["tool_audit"][0]["error_code"] == "TOOL_OUTPUT_TOO_LARGE"


def test_invalid_final_output_is_repaired_once():
    provider = ScriptedProvider(response(""), response("完整回答"))
    assert execute(provider).runtime["output_repairs"] == 1
    result = execute(ScriptedProvider(response(""), response("")))
    assert result.error_code == "AGENT_OUTPUT_INVALID"


def test_final_json_schema_and_truncated_output():
    provider = ScriptedProvider(response('{"ok":true}'))
    req = request(output_schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}})
    assert execute(provider, req=req).status == "success"
    result = execute(ScriptedProvider(response("unfinished", finish_reason="length"), response("finished")))
    assert result.status == "success" and result.response == "finished"


def test_context_compaction_preserves_tool_protocol_and_images():
    messages = [LLMMessage("system", "system"), LLMMessage("user", "original")]
    for i in range(7):
        messages.extend([LLMMessage("assistant", "x" * 200, tool_calls=(ToolCall(str(i), "lookup", {}),)),
                         LLMMessage("tool", "y" * 200, tool_call_id=str(i))])
    result = LoopContextManager(max_chars=1500, retain_recent_blocks=1).compact(messages)
    assert result.compacted
    assert result.messages[-2].tool_calls[0].id == result.messages[-1].tool_call_id
    image = LLMMessage("user", [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 200000}}])
    assert LoopContextManager._size([image]) < 1000
    assert execute(ScriptedProvider(response("图片内容")), req=request(images=("data:image/png;base64,AAAA",))).status == "success"


def test_oversized_context_stops_before_model_call():
    provider = ScriptedProvider()
    result = execute(provider, req=replace(request(), message="x" * 2000), max_context_chars=1024)
    assert result.error_code == "AGENT_CONTEXT_LIMIT" and not provider.requests


def llm_config(**kwargs):
    config = dict(model_name="configured", api_url="https://models.test/v1", api_key="config-secret",
                  temperature=0.5, max_tokens=100, max_retries=0, timeout=5,
                  _get_proxies=lambda: None)
    config.update(kwargs)
    return SimpleNamespace(**config)


def test_provider_uses_native_messages_tools_and_config_without_override():
    seen = []
    def handler(req):
        seen.append(json.loads(req.content))
        assert req.headers["Authorization"] == "Bearer config-secret"
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "a", "function": {"name": "lookup", "arguments": "{bad json"}}]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}})
    config = llm_config(use_max_completion_tokens=True, extra_headers={"authorization": "Bearer wrong"},
                        extra_body={"messages": [], "tools": ["bad"], "stream": True, "max_tokens": 9999},
                        _track_usage=lambda **kw: None)
    provider = ExistingLLMProvider(config, transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.complete([LLMMessage("system", "safe"), LLMMessage("user", "question")],
                                           tools=[tool().definition()], max_tokens=20))
    assert seen[0]["messages"][0]["role"] == "system"
    assert seen[0]["tools"][0]["function"]["name"] == "lookup"
    assert seen[0]["max_completion_tokens"] == 20 and "max_tokens" not in seen[0]
    assert seen[0]["stream"] is False
    assert result.tool_calls[0].argument_error and result.usage.total_tokens == 7


@pytest.mark.parametrize("status,code", [(401, "LLM_AUTH_FAILED"), (429, "LLM_RATE_LIMITED"), (400, "LLM_REQUEST_FAILED")])
def test_provider_classifies_errors_and_never_returns_upstream_secrets(status, code):
    provider = ExistingLLMProvider(llm_config(), transport=httpx.MockTransport(
        lambda _: httpx.Response(status, text="api_key=config-secret")))
    with pytest.raises(ConversationProviderError) as err:
        asyncio.run(provider.complete([LLMMessage("user", "hello")]))
    assert err.value.code == code and "config-secret" not in str(err.value)


def test_provider_fallback_usage_and_success_tracking():
    tracking = []
    config = llm_config(_track_usage=lambda **kw: tracking.append(kw))
    provider = ExistingLLMProvider(config, transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}]})))
    result = asyncio.run(provider.complete([LLMMessage("user", "private prompt")]))
    assert result.usage.total_tokens > 0
    assert tracking[0]["prompt"] == tracking[0]["completion"] == ""
    assert tracking[0]["prompt_tokens"] > 0


def test_cancellation_propagates_and_records_tool_cancellation():
    async def scenario():
        started = asyncio.Event()
        async def blocking(value):
            started.set()
            await asyncio.sleep(10)
        facade = AgentRuntimeFacade(ScriptedProvider(response(calls=[ToolCall("a", "lookup", {"value": 1})])),
                                    [tool(callback=blocking)], ConversationRuntimeSettings())
        task = asyncio.create_task(facade.execute(request()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert facade.last_result.runtime["phase"] == "cancelled"
        assert facade.last_result.runtime["tool_audit"][0]["status"] == "cancelled"
    asyncio.run(scenario())


def test_total_deadline_stops_model_and_settings_are_server_controlled(monkeypatch):
    class SlowProvider:
        async def complete(self, *args, **kwargs):
            await asyncio.sleep(10)
    result = execute(SlowProvider(), timeout_seconds=0.01)
    assert result.error_code == "AGENT_TIMEOUT"
    monkeypatch.setenv("AGENT_CONVERSATION_ENABLED", "false")
    monkeypatch.setenv("AGENT_CONVERSATION_MAX_MODEL_TURNS", "4")
    settings = ConversationRuntimeSettings.from_env()
    assert not settings.enabled and settings.max_model_turns == 4
    monkeypatch.setenv("AGENT_CONVERSATION_MAX_MODEL_TURNS", "0")
    with pytest.raises(ValueError):
        ConversationRuntimeSettings.from_env()
