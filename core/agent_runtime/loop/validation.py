"""Final response validation used before an Agent Loop commits output."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator


class AgentLoopOutputInvalidError(RuntimeError):
    code = "AGENT_OUTPUT_INVALID"


class FinalResponseValidator:
    def __init__(self, schema: dict[str, Any] | None = None) -> None:
        self.schema = dict(schema or {
            "type": "string",
            "minLength": 1,
            "pattern": r"\S",
        })
        Draft202012Validator.check_schema(self.schema)
        self._validator = Draft202012Validator(self.schema)

    def errors(self, content: str) -> list[dict[str, str]]:
        value: Any = content
        expected_type = self.schema.get("type")
        if expected_type in {"object", "array"}:
            try:
                value = json.loads(content)
            except (TypeError, ValueError):
                return [{"path": "$", "rule": "json", "message": "invalid JSON"}]
        return [
            {
                "path": "$" + "".join(
                    f"[{item}]" if isinstance(item, int) else f".{item}"
                    for item in error.absolute_path
                ),
                "rule": str(error.validator or "schema"),
                "message": error.message,
            }
            for error in self._validator.iter_errors(value)
        ]
