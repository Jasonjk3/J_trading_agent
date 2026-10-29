"""Bounded conversation loop, adapted from my-multi-agent without Durable Run."""

import asyncio
import hashlib
import json

from core.agent_runtime.llm_contracts import LLMMessage
from core.agent_runtime.loop.budget import AgentLoopBudgetExceededError, AgentLoopBudgetTracker
from core.agent_runtime.loop.context import LoopContextManager
from core.agent_runtime.loop.contracts import AgentAction, AgentDecision, AgentLoopState, DecisionKind, Fact, LoopPhase
from core.agent_runtime.loop.progress import ProgressEvaluator
from core.agent_runtime.loop.validation import AgentLoopOutputInvalidError, FinalResponseValidator


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class ConversationLoop:
    def __init__(self, provider, gateway, settings, *, output_schema=None):
        self.provider = provider
        self.gateway = gateway
        self.settings = settings
        self.state = AgentLoopState()
        self.budget = settings.budget()
        self.tracker = AgentLoopBudgetTracker(self.budget, self.state)
        self.progress = ProgressEvaluator(self.budget)
        self.context_manager = LoopContextManager(max_chars=settings.max_context_chars, retain_recent_blocks=2)
        self.validator = FinalResponseValidator(output_schema)

    async def run(self, messages):
        try:
            return await asyncio.wait_for(self._run(list(messages)), self.settings.timeout_seconds)
        except asyncio.CancelledError:
            self.state.phase = LoopPhase.CANCELLED
            raise
        except Exception:
            self.state.phase = LoopPhase.FAILED
            raise

    async def _run(self, history):
        while self.state.model_turns < self.budget.max_model_turns:
            self.state.phase = LoopPhase.DECIDING
            compacted = self.context_manager.compact(history, facts=self.state.facts)
            history = list(compacted.messages)
            self.state.compaction_count += int(compacted.compacted)
            if self.context_manager._size(history) > self.settings.max_context_chars:
                raise AgentLoopBudgetExceededError("AGENT_CONTEXT_LIMIT", "对话上下文过长，请缩短消息或新建会话")
            remaining = self.settings.max_total_tokens - self.state.total_tokens
            if remaining <= 0:
                raise AgentLoopBudgetExceededError("AGENT_TOKEN_BUDGET_EXHAUSTED", "对话 Token 预算已耗尽")
            response = await self.provider.complete(
                history, tools=self.gateway.definitions(), max_tokens=min(remaining, self.settings.max_output_tokens),
                timeout_seconds=self.settings.timeout_seconds,
                metadata={"agent_name": self.gateway.context.agent_id,
                          "user_id": self.gateway.context.principal.user_id,
                          "session_id": self.gateway.context.session_id},
            )
            self.tracker.record_model_turn(response.usage)
            self.state.phase = LoopPhase.VALIDATING_DECISION
            if not response.tool_calls:
                errors = self.validator.errors(response.content)
                # A token-truncated answer is a draft, not a validated final result.
                if response.finish_reason == "length":
                    errors.append({"path": "$", "rule": "complete", "message": "response truncated"})
                if errors:
                    if self.state.output_repair_attempts >= self.budget.max_output_repair_attempts:
                        raise AgentLoopOutputInvalidError("模型未能返回符合要求的完整回答")
                    self.state.output_repair_attempts += 1
                    history.extend([LLMMessage("assistant", response.content), LLMMessage(
                        "user", "请重新给出完整、非空且符合输出格式要求的最终回答。")])
                    continue
                self.state.phase = LoopPhase.SUCCEEDED
                return response.content
            self.tracker.ensure_can_continue_after_action_decision()
            # Normalize only structured function calls; never execute fenced
            # code embedded in ordinary text, history or tool observations.
            decision_id = digest({"turn": self.state.model_turns, "trace": self.gateway.context.trace_id})
            actions = tuple(AgentAction(
                action_id=digest({"decision": decision_id, "index": index}),
                semantic_key=digest({"name": call.name, "arguments": call.arguments,
                                     "argument_error": call.argument_error}),
                call=call,
            ) for index, call in enumerate(response.tool_calls))
            decision = AgentDecision(decision_id, DecisionKind.ACT, "tool action proposal", actions)
            self.state.decision_ids.append(decision_id)
            self.state.decision_fingerprints.append(self.progress.strategy_fingerprint(decision))
            if self.progress.is_abab_oscillation(self.state.decision_fingerprints):
                self.state.oscillation_count += 1
                if self.state.oscillation_count >= 2:
                    raise AgentLoopBudgetExceededError("AGENT_OSCILLATION_LIMIT", "工具调用反复切换且未完成任务")
            # Validate the entire decision's action budget before dispatching.
            for action in actions:
                self.tracker.record_action(action)
            history.append(LLMMessage("assistant", response.content, tool_calls=response.tool_calls))
            self.state.phase = LoopPhase.EXECUTING_ACTIONS
            for action in actions:
                output, failed = await self.gateway.execute(action.call, action.action_id)
                self.state.phase = LoopPhase.INCORPORATING_RESULTS
                self.progress.incorporate(self.state, Fact(
                    fact_id=digest({"tool": action.call.name, "output": output, "failed": failed}),
                    content={"tool": action.call.name, "data": output}, source_type="tool",
                    source_id=action.action_id, failed=failed, subject_key=action.semantic_key,
                ))
                history.append(LLMMessage("tool", json.dumps(output, ensure_ascii=False, default=str),
                                          name=action.call.name, tool_call_id=action.call.id))
        raise AgentLoopBudgetExceededError("AGENT_MODEL_TURN_LIMIT", "对话已达到模型调用轮次上限")
