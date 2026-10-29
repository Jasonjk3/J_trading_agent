"""Deterministic progress accounting for Agent Loop observations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from core.agent_runtime.loop.budget import AgentLoopBudget, AgentLoopBudgetExceededError
from core.agent_runtime.loop.contracts import AgentDecision, AgentLoopState, Fact


class ProgressEvaluator:
    def __init__(self, budget: AgentLoopBudget) -> None:
        self.budget = budget

    def incorporate(self, state: AgentLoopState, fact: Fact) -> bool:
        known = {str(item.get("fact_id")) for item in state.facts}
        is_new = fact.fact_id not in known
        if is_new:
            state.facts.append(fact.to_payload())
            state.no_progress_turns = 0
        else:
            state.no_progress_turns += 1
        state.consecutive_failures = (
            state.consecutive_failures + 1 if fact.failed else 0
        )
        if state.no_progress_turns >= self.budget.max_no_progress_turns:
            raise AgentLoopBudgetExceededError(
                "AGENT_NO_PROGRESS_LIMIT",
                "agent loop stopped after repeated observations without new facts",
            )
        if state.consecutive_failures >= self.budget.max_consecutive_failures:
            raise AgentLoopBudgetExceededError(
                "AGENT_CONSECUTIVE_FAILURE_LIMIT",
                "agent loop stopped after consecutive action failures",
            )
        return is_new

    @staticmethod
    def decision_fingerprint(
        state: AgentLoopState, decision: AgentDecision
    ) -> str:
        fact_ids = sorted(str(item.get("fact_id") or "") for item in state.facts)
        return ProgressEvaluator._digest({
            "kind": decision.kind.value,
            "actions": [action.semantic_key for action in decision.actions],
            "facts": fact_ids,
        })

    @staticmethod
    def strategy_fingerprint(decision: AgentDecision) -> str:
        return ProgressEvaluator._digest({
            "kind": decision.kind.value,
            "actions": [action.semantic_key for action in decision.actions],
        })

    @staticmethod
    def is_abab_oscillation(fingerprints: Sequence[str]) -> bool:
        if len(fingerprints) < 4:
            return False
        first, second, third, fourth = fingerprints[-4:]
        return first == third and second == fourth and first != second

    @staticmethod
    def _digest(value: object) -> str:
        return hashlib.sha256(
            json.dumps(
                value, sort_keys=True, ensure_ascii=False, default=str
            ).encode("utf-8")
        ).hexdigest()[:32]
