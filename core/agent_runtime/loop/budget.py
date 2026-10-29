"""Multi-dimensional hard budgets for Agent Loop execution."""

from __future__ import annotations

from dataclasses import dataclass

from core.agent_runtime.loop.contracts import AgentAction, AgentLoopState
from core.agent_runtime.llm_contracts import LLMUsage


class AgentLoopBudgetExceededError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AgentLoopBudget:
    max_model_turns: int = 8
    max_tool_actions: int = 64
    max_total_tokens: int | None = None
    max_same_action_repeats: int = 2
    max_no_progress_turns: int = 3
    max_consecutive_failures: int = 3
    max_oscillation_cycles: int | None = None
    soft_budget_ratio: float | None = None
    max_output_repair_attempts: int = 1

    def __post_init__(self) -> None:
        if self.max_model_turns < 1:
            raise ValueError("max_model_turns must be at least 1")
        if self.max_tool_actions < 1:
            raise ValueError("max_tool_actions must be at least 1")
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be positive when configured")
        if self.max_same_action_repeats < 1:
            raise ValueError("max_same_action_repeats must be at least 1")
        if self.max_no_progress_turns < 1:
            raise ValueError("max_no_progress_turns must be at least 1")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1")
        if self.max_oscillation_cycles is not None and self.max_oscillation_cycles < 1:
            raise ValueError("max_oscillation_cycles must be at least 1")
        if self.soft_budget_ratio is not None and not 0 < self.soft_budget_ratio < 1:
            raise ValueError("soft_budget_ratio must be between 0 and 1")
        if self.max_output_repair_attempts < 0:
            raise ValueError("max_output_repair_attempts must be non-negative")


class AgentLoopBudgetTracker:
    def __init__(self, budget: AgentLoopBudget, state: AgentLoopState) -> None:
        self.budget = budget
        self.state = state

    def record_model_turn(self, usage: LLMUsage) -> None:
        self.state.model_turns += 1
        self.state.total_tokens += usage.total_tokens
        if (
            self.budget.max_total_tokens is not None
            and self.state.total_tokens > self.budget.max_total_tokens
        ):
            raise AgentLoopBudgetExceededError(
                "AGENT_TOKEN_BUDGET_EXHAUSTED",
                "agent loop exceeded its total token budget",
            )

    def ensure_can_continue_after_action_decision(self) -> None:
        if self.state.model_turns >= self.budget.max_model_turns:
            raise AgentLoopBudgetExceededError(
                "AGENT_MODEL_TURN_LIMIT",
                f"agent loop exceeded maximum of {self.budget.max_model_turns} model turns",
            )

    def record_action(self, action: AgentAction) -> None:
        if self.state.tool_actions >= self.budget.max_tool_actions:
            raise AgentLoopBudgetExceededError(
                "AGENT_TOOL_ACTION_LIMIT",
                f"agent loop exceeded maximum of {self.budget.max_tool_actions} tool actions",
            )
        repeats = self.state.action_counts.get(action.semantic_key, 0) + 1
        if repeats > self.budget.max_same_action_repeats:
            raise AgentLoopBudgetExceededError(
                "AGENT_REPEATED_ACTION_LIMIT",
                "agent loop repeated an equivalent tool action without making progress",
            )
        self.state.action_counts[action.semantic_key] = repeats
        self.state.tool_actions += 1
