"""Request-local contracts; identities are supplied by the authenticated service."""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from core.agent_runtime.llm_contracts import LLMMessage


@dataclass(frozen=True)
class PrincipalSnapshot:
    user_id: str
    allowed_tools: frozenset[str] = frozenset()
    tenant_id: str = "default"


@dataclass(frozen=True)
class ExecutionContext:
    principal: PrincipalSnapshot
    agent_id: str
    session_id: str
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    journal: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class AgentRequest:
    message: str
    context: ExecutionContext
    system_prompt: str
    history: tuple[LLMMessage, ...] = ()
    images: tuple[str, ...] = ()
    output_schema: dict[str, Any] | None = None


@dataclass
class AgentResult:
    trace_id: str
    status: str
    response: str | None = None
    error_code: str | None = None
    error: str | None = None
    runtime: dict[str, Any] = field(default_factory=dict)

    def to_legacy(self) -> dict[str, Any]:
        return {
            "success": self.status == "success", "response": self.response,
            "error": self.error, "error_code": self.error_code,
            "trace_id": self.trace_id, "runtime": self.runtime,
        }


@dataclass
class RuntimeInvocation:
    """Internal capability object, never deserialized from request JSON."""

    facade: Any
    request: AgentRequest

    async def execute(self) -> dict[str, Any]:
        return (await self.facade.execute(self.request)).to_legacy()
