"""Explicit read-only tool registry and authoritative execution gateway."""

import asyncio
import hashlib
import inspect
import json
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import uuid4

from jsonschema import Draft202012Validator

from core.agent_runtime.llm_contracts import ToolDefinition
from core.agent_runtime.redaction import ToolRedactor


@dataclass(frozen=True)
class ConversationTool:
    name: str
    description: str
    parameters: dict[str, Any]
    callback: Callable[..., Awaitable[dict[str, Any]]]
    version: str = "1"
    side_effect: str = "none"

    def definition(self):
        return ToolDefinition(self.name, self.description, self.parameters)


class ToolGateway:
    def __init__(self, tools, context, *, timeout_seconds=15, max_output_bytes=32768):
        self.tools = {}
        self.context = context
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.redactor = ToolRedactor()
        self.audit: list[dict[str, Any]] = []
        for tool in tools:
            if tool.name in self.tools:
                raise ValueError("duplicate conversation tool: " + tool.name)
            Draft202012Validator.check_schema(tool.parameters)
            self.tools[tool.name] = tool

    def _allowed(self, name):
        tool = self.tools.get(name)
        return bool(tool and tool.side_effect == "none" and
                    name in self.context.principal.allowed_tools and self.context.principal.user_id)

    def definitions(self):
        return [tool.definition() for name, tool in self.tools.items() if self._allowed(name)]

    async def execute(self, call, action_id):
        started = time.monotonic()
        entry = {
            "invocation_id": uuid4().hex, "action_id": action_id,
            "trace_id": self.context.trace_id, "tool": call.name,
            "agent_id": self.context.agent_id, "session_id": self.context.session_id,
            "user_id": self.context.principal.user_id,
            "tenant_id": self.context.principal.tenant_id,
            "input": self.redactor.view(call.arguments).value,
        }
        tool = self.tools.get(call.name)
        if tool:
            entry["tool_version"] = tool.version
        code = None
        output = {}
        failed = False
        try:
            # Recheck at execution, even if the model invents a call that was
            # absent from the advertised definitions.
            if not self._allowed(call.name):
                code = "TOOL_NOT_ALLOWED"
            elif call.argument_error or not isinstance(call.arguments, dict):
                code = "TOOL_INVALID_ARGUMENTS"
            elif any(Draft202012Validator(tool.parameters).iter_errors(call.arguments)):
                code = "TOOL_INVALID_ARGUMENTS"
            elif not inspect.iscoroutinefunction(tool.callback):
                # Thread timeouts cannot stop a blocking function or its side
                # effects. Only reviewed async callbacks belong in this phase.
                code = "TOOL_ASYNC_REQUIRED"
            else:
                output = await asyncio.wait_for(tool.callback(**call.arguments), self.timeout_seconds)
                if not isinstance(output, dict):
                    code = "TOOL_INVALID_RESULT"
                elif len(json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")) > self.max_output_bytes:
                    code = "TOOL_OUTPUT_TOO_LARGE"
                elif output.get("success") is False:
                    code = "TOOL_REPORTED_FAILURE"
        except asyncio.CancelledError:
            entry["status"] = "cancelled"
            raise
        except asyncio.TimeoutError:
            code = "TOOL_TIMEOUT"
        except PermissionError:
            code = "TOOL_ACCESS_DENIED"
        except Exception:
            code = "TOOL_FAILED"  # Never propagate a tool's raw exception.
        finally:
            if entry.get("status") == "cancelled":
                self._append_audit(entry, started)
        if code:
            output, failed = {"error_code": code, "error": "工具调用未完成"}, True
        else:
            output = self.redactor.view(json.loads(json.dumps(output, ensure_ascii=False, default=str))).value
        entry.update(status="failed" if failed else "succeeded", error_code=code,
                     output=self.redactor.view(output).value)
        self._append_audit(entry, started)
        return output, failed

    def _append_audit(self, entry, started):
        entry["duration_ms"] = int((time.monotonic() - started) * 1000)
        entry["previous_hash"] = self.audit[-1]["hash"] if self.audit else ""
        entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()
        self.audit.append(entry)
