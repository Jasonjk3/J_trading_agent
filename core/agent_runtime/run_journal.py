"""Replay completed model/tool steps without repeating external work."""

from dataclasses import asdict
from core.agent_runtime.llm_contracts import LLMResponse, LLMUsage, ToolCall
from core.agent_runtime.redaction import ToolRedactor
from core.agent_runtime.run_repository import RunError, digest
from core.agent_runtime.tools import ToolGateway


class RunJournal:
    def __init__(self, repository, run_id, token):
        self.repository, self.run_id, self.token = repository, run_id, token

    async def step(self, key, kind, fingerprint, output=None):
        return await self.repository.step(self.run_id, self.token, key, kind, fingerprint, output)


class JournalProvider:
    def __init__(self, provider, journal):
        self.provider, self.journal = provider, journal
        self.turn = 0

    async def complete(self, messages, **kwargs):
        key = f"model:{self.turn}"
        self.turn += 1
        fingerprint = digest({"messages": [m.to_payload() for m in messages],
                              "tools": [t.to_payload() for t in kwargs.get("tools") or []],
                              "max_tokens": kwargs.get("max_tokens")})
        cached = await self.journal.step(key, "model", fingerprint)
        if cached is not None:
            if not cached.get("replayable", True):
                raise RunError("RUN_CHECKPOINT_NOT_REPLAYABLE", "此检查点包含已脱敏参数，不能自动重放")
            return LLMResponse(content=cached["content"], model=cached["model"],
                               finish_reason=cached["finish_reason"], usage=LLMUsage(**cached["usage"]),
                               tool_calls=tuple(ToolCall(**call) for call in cached["tool_calls"]))
        result = await self.provider.complete(messages, **kwargs)
        calls = []
        replayable = True
        redactor = ToolRedactor()
        for call in result.tool_calls:
            values = asdict(call)
            safe = redactor.view(call.arguments).value
            replayable &= safe == call.arguments
            values["arguments"] = safe
            # Parsed arguments are sufficient for valid function calls. Never
            # duplicate a JSON string containing credentials in the checkpoint.
            # Malformed JSON cannot be reliably redacted/replayed as a call.
            values["raw_arguments"] = None
            if call.argument_error:
                replayable = False
            calls.append(values)
        await self.journal.step(key, "model", fingerprint, {
            "content": result.content, "model": result.model, "finish_reason": result.finish_reason,
            "usage": asdict(result.usage), "tool_calls": calls, "replayable": replayable,
        })
        return result


class JournalToolGateway(ToolGateway):
    def __init__(self, *args, journal, **kwargs):
        super().__init__(*args, **kwargs)
        self.journal = journal

    async def execute(self, call, action_id):
        fingerprint = digest({"name": call.name, "arguments": call.arguments, "argument_error": call.argument_error,
                              "version": self.tools[call.name].version if call.name in self.tools else None,
                              "user": self.context.principal.user_id})
        cached = await self.journal.step("tool:" + action_id, "tool", fingerprint)
        if cached is not None:
            # Current authorization always precedes checkpoint reuse.
            if not self._allowed(call.name):
                return await super().execute(call, action_id)
            self.audit.append(cached["audit"])
            return cached["output"], cached["failed"]
        output, failed = await super().execute(call, action_id)
        await self.journal.step("tool:" + action_id, "tool", fingerprint,
                                {"output": output, "failed": failed, "audit": self.audit[-1]})
        return output, failed
