from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """OpenAI-compatible function tool definition supplied to a provider."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A normalized function call requested by an LLM response."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str | None = None
    argument_error: str | None = None


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: str
    content: str | list[dict[str, Any]]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.raw_arguments
                        if call.argument_error and call.raw_arguments is not None
                        else json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in self.tool_calls
            ]
        return payload


@dataclass(frozen=True, slots=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str
    finish_reason: str | None = None
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw: dict[str, Any] = field(default_factory=dict)
    response_headers: dict[str, str] = field(default_factory=dict)
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMStreamChunk:
    content: str = ""
    model: str | None = None
    finish_reason: str | None = None
    usage: LLMUsage | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    tool_calls: tuple[ToolCall, ...] = ()


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[ToolDefinition] | None = None,
        metadata: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> LLMResponse:
        ...

    def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[ToolDefinition] | None = None,
        metadata: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        ...
