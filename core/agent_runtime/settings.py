"""Server-controlled conversation limits and rollout switch."""

import os
from dataclasses import dataclass

from core.agent_runtime.loop.budget import AgentLoopBudget


@dataclass(frozen=True)
class ConversationRuntimeSettings:
    enabled: bool = True
    history_messages: int = 24
    max_model_turns: int = 8
    max_tool_actions: int = 16
    max_total_tokens: int = 32000
    max_output_tokens: int = 4096
    max_same_action_repeats: int = 2
    max_no_progress_turns: int = 3
    max_consecutive_failures: int = 3
    max_context_chars: int = 60000
    timeout_seconds: float = 180
    tool_timeout_seconds: float = 15
    tool_max_output_bytes: int = 32768

    def __post_init__(self):
        self.budget()
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if self.history_messages < 2 or self.max_context_chars < 1024:
            raise ValueError("conversation history/context limits are too small")
        if self.timeout_seconds <= 0 or self.tool_timeout_seconds <= 0:
            raise ValueError("conversation timeouts must be positive")
        if self.tool_max_output_bytes < 256:
            raise ValueError("tool_max_output_bytes must be at least 256")

    def budget(self) -> AgentLoopBudget:
        return AgentLoopBudget(
            max_model_turns=self.max_model_turns,
            max_tool_actions=self.max_tool_actions,
            max_total_tokens=self.max_total_tokens,
            max_same_action_repeats=self.max_same_action_repeats,
            max_no_progress_turns=self.max_no_progress_turns,
            max_consecutive_failures=self.max_consecutive_failures,
            max_output_repair_attempts=1,
        )

    @classmethod
    def from_env(cls):
        values = {}
        for name, field in cls.__dataclass_fields__.items():
            raw = os.getenv("AGENT_CONVERSATION_" + name.upper())
            if raw is None:
                continue
            if name == "enabled":
                if raw.lower() not in {"true", "false", "1", "0"}:
                    raise ValueError("AGENT_CONVERSATION_ENABLED must be true or false")
                values[name] = raw.lower() in {"true", "1"}
            else:
                values[name] = type(field.default)(raw)
        return cls(**values)
