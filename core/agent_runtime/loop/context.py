"""Deterministic, protocol-safe context compaction for Agent Loop turns."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Sequence

from core.agent_runtime.llm_contracts import LLMMessage


_SUMMARY_MARKER = "[Agent Loop context summary]"


@dataclass(frozen=True, slots=True)
class ContextCompaction:
    messages: tuple[LLMMessage, ...]
    compacted: bool
    source_digest: str
    result_digest: str
    omitted_blocks: int = 0


class LoopContextManager:
    """Bounds history without separating a tool call from its observations."""

    def __init__(
        self,
        *,
        max_chars: int = 200_000,
        retain_recent_blocks: int = 8,
        max_summary_facts: int = 24,
    ) -> None:
        if max_chars < 256:
            raise ValueError("max_chars must be at least 256")
        if retain_recent_blocks < 1:
            raise ValueError("retain_recent_blocks must be at least 1")
        if max_summary_facts < 1:
            raise ValueError("max_summary_facts must be at least 1")
        self.max_chars = max_chars
        self.retain_recent_blocks = retain_recent_blocks
        self.max_summary_facts = max_summary_facts

    def compact(
        self,
        messages: Sequence[LLMMessage],
        *,
        facts: Sequence[dict[str, Any]] = (),
    ) -> ContextCompaction:
        source = tuple(messages)
        source_digest = self._digest(source)
        if self._size(source) <= self.max_chars:
            return ContextCompaction(
                source, False, source_digest, source_digest
            )

        permanent: list[LLMMessage] = []
        conversation: list[LLMMessage] = []
        for message in source:
            if message.role == "system":
                if not self._is_summary(message):
                    permanent.append(message)
            else:
                conversation.append(message)

        blocks = self._blocks(conversation)
        if len(blocks) <= self.retain_recent_blocks + 1:
            return ContextCompaction(
                source, False, source_digest, source_digest
            )

        first = blocks[:1]
        recent = blocks[-self.retain_recent_blocks :]
        omitted = blocks[1 : -self.retain_recent_blocks]
        if not omitted:
            return ContextCompaction(
                source, False, source_digest, source_digest
            )

        summary = LLMMessage(
            role="system",
            content=self._summary(omitted, facts),
        )
        compacted = tuple(
            [*permanent, *self._flatten(first), summary, *self._flatten(recent)]
        )
        return ContextCompaction(
            compacted,
            True,
            source_digest,
            self._digest(compacted),
            len(omitted),
        )

    @staticmethod
    def _blocks(messages: Sequence[LLMMessage]) -> list[list[LLMMessage]]:
        blocks: list[list[LLMMessage]] = []
        index = 0
        while index < len(messages):
            message = messages[index]
            block = [message]
            index += 1
            if message.role == "assistant" and message.tool_calls:
                while index < len(messages) and messages[index].role == "tool":
                    block.append(messages[index])
                    index += 1
            blocks.append(block)
        return blocks

    @staticmethod
    def _flatten(blocks: Sequence[Sequence[LLMMessage]]) -> list[LLMMessage]:
        return [message for block in blocks for message in block]

    def _summary(
        self,
        omitted: Sequence[Sequence[LLMMessage]],
        facts: Sequence[dict[str, Any]],
    ) -> str:
        fact_views = [
            {
                "fact_id": str(fact.get("fact_id") or ""),
                "content": fact.get("content"),
                "failed": bool(fact.get("failed")),
                "source_type": fact.get("source_type"),
                "source_id": fact.get("source_id"),
                "confidence": fact.get("confidence"),
                "sensitivity": fact.get("sensitivity"),
                "conflicts_with": list(fact.get("conflicts_with") or []),
            }
            for fact in facts[-self.max_summary_facts :]
        ]
        omitted_digest = hashlib.sha256(
            json.dumps(
                [message.to_payload() for message in self._flatten(omitted)],
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:32]
        payload = {
            "omitted_blocks": len(omitted),
            "omitted_digest": omitted_digest,
            "known_facts": fact_views,
        }
        return f"{_SUMMARY_MARKER}\n" + json.dumps(
            payload, sort_keys=True, ensure_ascii=False, default=str
        )

    @staticmethod
    def _is_summary(message: LLMMessage) -> bool:
        return isinstance(message.content, str) and message.content.startswith(
            _SUMMARY_MARKER
        )

    @staticmethod
    def _size(messages: Sequence[LLMMessage]) -> int:
        payloads = [message.to_payload() for message in messages]
        # Meter image attachments separately from the text context, preserving
        # existing multimodal chat without counting base64 as text tokens.
        for payload in payloads:
            if isinstance(payload.get("content"), list):
                payload["content"] = [
                    {"type": "image_url", "image_url": "[image attachment]"}
                    if item.get("type") == "image_url" else item
                    for item in payload["content"]
                ]
        return len(
            json.dumps(
                payloads,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
        )

    @classmethod
    def _digest(cls, messages: Sequence[LLMMessage]) -> str:
        return hashlib.sha256(
            json.dumps(
                [message.to_payload() for message in messages],
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:32]
