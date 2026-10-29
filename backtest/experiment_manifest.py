#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build immutable fingerprints for a completed backtest experiment."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from backtest.llm_replay_cache import LLMReplayCache, model_fingerprint, model_identity


def _hash_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def code_version() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"], capture_output=True, check=True, timeout=15
        ).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout.split(b"\0")
        digest = hashlib.sha256(diff)
        for raw_path in sorted(path for path in untracked if path):
            digest.update(raw_path)
            try:
                digest.update(Path(raw_path.decode("utf-8")).read_bytes())
            except (OSError, UnicodeDecodeError):
                digest.update(b"<unreadable>")
        return f"{commit}-dirty-{digest.hexdigest()[:16]}" if diff or untracked != [b""] else commit
    except Exception:
        return "unknown"


def market_data_version(kline_data: Dict[str, Iterable[Any]]) -> str:
    rows = []
    for symbol in sorted(kline_data):
        for bar in kline_data[symbol]:
            rows.append(
                [symbol, bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.quote_volume]
            )
    return _hash_json(rows)


def build_experiment_manifest(
    engine: Any,
    strategy_config: Dict[str, Any],
    llm: Any,
    replay_cache: Optional[LLMReplayCache] = None,
) -> Dict[str, Any]:
    decision_prompt_hashes = {
        str((row.get("llm_metadata") or {}).get("prompt_hash"))
        for row in engine.decision_log
        if (row.get("llm_metadata") or {}).get("prompt_hash")
    }
    replay_manifest = replay_cache.session_manifest() if replay_cache is not None else {}
    prompt_hashes = sorted(
        decision_prompt_hashes | set(replay_manifest.get("promptHashes") or [])
    )
    return {
        "schemaVersion": 1,
        "codeVersion": code_version(),
        "strategyConfigHash": _hash_json(strategy_config),
        "marketDataVersion": market_data_version(engine.kline_data),
        "modelIdentity": model_identity(llm) if llm is not None else None,
        "modelFingerprint": model_fingerprint(llm) if llm is not None else None,
        "promptHashes": prompt_hashes,
        "promptSetHash": _hash_json(prompt_hashes),
        "replayCache": replay_manifest,
        "temperature": 0.0,
        "executionSemantics": "previous_closed_bar_signal_next_open_fill_intrabar_conservative",
    }
