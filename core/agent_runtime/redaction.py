"""Audience-safe, bounded views for tool inputs, outputs, and errors."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


_SENSITIVE_KEYS = {
    "authorization", "cookie", "set-cookie", "password", "passwd",
    "secret", "token", "access_token", "refresh_token", "api_key",
    "apikey", "private_key", "client_secret",
}
_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
)
_NORMALIZED_SENSITIVE_KEYS = {re.sub(r"[^a-z0-9]", "", key) for key in _SENSITIVE_KEYS}


@dataclass(frozen=True, slots=True)
class RedactedView:
    value: dict[str, Any]
    digest: str
    original_bytes: int


class ToolRedactor:
    def __init__(self, *, max_text_chars: int = 2_000) -> None:
        if max_text_chars < 64:
            raise ValueError("max_text_chars must be at least 64")
        self.max_text_chars = max_text_chars

    def view(self, value: dict[str, Any]) -> RedactedView:
        serialized = json.dumps(
            value, sort_keys=True, ensure_ascii=False, default=str
        ).encode("utf-8")
        sanitized = self._sanitize(value)
        digest = hashlib.sha256(serialized).hexdigest()
        return RedactedView(sanitized, digest, len(serialized))

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): (
                    "[REDACTED]"
                    if re.sub(r"[^a-z0-9]", "", str(key).casefold()) in _NORMALIZED_SENSITIVE_KEYS
                    else self._sanitize(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str):
            text = value
            for pattern in _CREDENTIAL_PATTERNS:
                text = pattern.sub("[REDACTED_CREDENTIAL]", text)
            if len(text) > self.max_text_chars:
                return {
                    "truncated": text[: self.max_text_chars],
                    "original_chars": len(text),
                    "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                }
            return text
        return value
