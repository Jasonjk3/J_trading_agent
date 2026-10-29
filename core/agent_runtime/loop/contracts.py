"""Typed decisions and state for the first Agent Loop implementation phase."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.agent_runtime.llm_contracts import ToolCall


class LoopPhase(str, Enum):
    DECIDING = "deciding"
    VALIDATING_DECISION = "validating_decision"
    EXECUTING_ACTIONS = "executing_actions"
    INCORPORATING_RESULTS = "incorporating_results"
    FINALIZING = "finalizing"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"


class DecisionKind(str, Enum):
    ACT = "act"
    FINISH = "finish"
    ASK_USER = "ask_user"
    REQUEST_APPROVAL = "request_approval"


@dataclass(frozen=True, slots=True)
class AgentAction:
    """One runtime-owned action normalized from a model tool call."""

    action_id: str
    semantic_key: str
    call: ToolCall


@dataclass(frozen=True, slots=True)
class AgentDecision:
    """A model proposal after normalization; it does not grant authority."""

    decision_id: str
    kind: DecisionKind
    summary: str
    actions: tuple[AgentAction, ...] = ()


@dataclass(frozen=True, slots=True)
class Fact:
    fact_id: str
    content: dict[str, Any]
    source_type: str
    source_id: str
    failed: bool = False
    subject_key: str = ""
    confidence: float | None = None
    sensitivity: str = "filtered"

    def to_payload(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "content": self.content,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "failed": self.failed,
            "subject_key": self.subject_key,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
        }


@dataclass(slots=True)
class AgentLoopState:
    """In-memory Phase 0 state; RunStep remains the durable store for now."""

    phase: LoopPhase = LoopPhase.DECIDING
    model_turns: int = 0
    tool_actions: int = 0
    total_tokens: int = 0
    decision_ids: list[str] = field(default_factory=list)
    action_counts: dict[str, int] = field(default_factory=dict)
    wait: dict[str, object] | None = None
    facts: list[dict[str, Any]] = field(default_factory=list)
    no_progress_turns: int = 0
    consecutive_failures: int = 0
    compaction_count: int = 0
    decision_fingerprints: list[str] = field(default_factory=list)
    oscillation_count: int = 0
    soft_budget_warned: bool = False
    output_repair_attempts: int = 0
    fact_conflict_count: int = 0
