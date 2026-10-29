#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Persistent, deterministic replay cache for LLM calls made during backtests."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple


_active_cache: ContextVar[Optional["LLMReplayCache"]] = ContextVar(
    "backtest_llm_replay_cache", default=None
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def model_identity(llm: Any) -> Dict[str, Any]:
    return {
        "class": llm.__class__.__name__,
        "model": getattr(llm, "model_name", None) or getattr(llm, "model", None),
        "model_version": getattr(llm, "model_version", None),
        "api_url": getattr(llm, "api_url", None),
        "temperature": 0.0,
    }


def model_fingerprint(llm: Any) -> str:
    payload = model_identity(llm)
    return _sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


@dataclass(frozen=True)
class ReplayCallMetadata:
    cache_key: str
    prompt_hash: str
    model_fingerprint: str
    cache_hit: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cache_key": self.cache_key,
            "prompt_hash": self.prompt_hash,
            "model_fingerprint": self.model_fingerprint,
            "cache_hit": self.cache_hit,
        }


class LLMReplayCache:
    """Small SQLite cache safe for repeated runs and multiple worker threads."""

    def __init__(self, path: str, mode: str = "record"):
        self.path = str(Path(path).resolve())
        if mode not in {"replay", "record"}:
            raise ValueError(f"Unsupported LLM cache mode: {mode}")
        self.mode = mode
        self._init_lock = threading.Lock()
        self._initialized = False
        self._stats_lock = threading.Lock()
        self._prompt_hashes = set()
        self._model_fingerprints = set()
        self._hits = 0
        self._misses = 0

    def record_call(self, metadata: ReplayCallMetadata) -> None:
        with self._stats_lock:
            self._prompt_hashes.add(metadata.prompt_hash)
            self._model_fingerprints.add(metadata.model_fingerprint)
            if metadata.cache_hit:
                self._hits += 1
            else:
                self._misses += 1

    def session_manifest(self) -> Dict[str, Any]:
        with self._stats_lock:
            return {
                "mode": self.mode,
                "cachePath": self.path,
                "promptHashes": sorted(self._prompt_hashes),
                "modelFingerprints": sorted(self._model_fingerprints),
                "cacheHits": self._hits,
                "cacheMisses": self._misses,
            }

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_replay_cache (
                        cache_key TEXT PRIMARY KEY,
                        prompt_hash TEXT NOT NULL,
                        model_fingerprint TEXT NOT NULL,
                        response TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_hit_at TEXT,
                        hit_count INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_llm_replay_prompt ON llm_replay_cache(prompt_hash)"
                )
            self._initialized = True

    @staticmethod
    def key_for(llm: Any, prompt: str) -> Tuple[str, str, str]:
        prompt_hash = _sha256(prompt)
        fingerprint = model_fingerprint(llm)
        return _sha256(f"{fingerprint}:{prompt_hash}"), prompt_hash, fingerprint

    def get(self, cache_key: str) -> Optional[str]:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response FROM llm_replay_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE llm_replay_cache
                SET hit_count = hit_count + 1, last_hit_at = CURRENT_TIMESTAMP
                WHERE cache_key = ?
                """,
                (cache_key,),
            )
            return str(row[0])

    def put(
        self,
        cache_key: str,
        prompt_hash: str,
        fingerprint: str,
        response: str,
    ) -> None:
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO llm_replay_cache
                    (cache_key, prompt_hash, model_fingerprint, response)
                VALUES (?, ?, ?, ?)
                """,
                (cache_key, prompt_hash, fingerprint, response),
            )


def default_cache_path() -> str:
    configured = os.getenv("BACKTEST_LLM_REPLAY_CACHE")
    if configured:
        return configured
    return str(Path.cwd() / ".runtime" / "backtest_llm_replay.sqlite3")


@contextmanager
def activate_replay_cache(
    path: Optional[str] = None,
    *,
    mode: str = "record",
) -> Iterator[LLMReplayCache]:
    """激活缓存上下文；生产回测只使用 record，replay 仅保留给确定性测试工具。"""
    cache = LLMReplayCache(path or default_cache_path(), mode=mode)
    token = _active_cache.set(cache)
    try:
        yield cache
    finally:
        _active_cache.reset(token)


def get_active_replay_cache() -> Optional[LLMReplayCache]:
    return _active_cache.get()


async def call_llm_with_replay(llm: Any, prompt: str) -> Tuple[str, ReplayCallMetadata]:
    cache = get_active_replay_cache()
    cache_key, prompt_hash, fingerprint = LLMReplayCache.key_for(llm, prompt)
    if cache is not None and cache.mode == "replay":
        cached = await asyncio.to_thread(cache.get, cache_key)
        if cached is not None:
            metadata = ReplayCallMetadata(cache_key, prompt_hash, fingerprint, True)
            cache.record_call(metadata)
            return cached, metadata

    raw = await asyncio.to_thread(llm._call, prompt)
    response = raw if isinstance(raw, str) else str(raw)
    if cache is not None and cache.mode == "replay":
        await asyncio.to_thread(cache.put, cache_key, prompt_hash, fingerprint, response)
    metadata = ReplayCallMetadata(cache_key, prompt_hash, fingerprint, False)
    if cache is not None:
        cache.record_call(metadata)
    return response, metadata


async def record_successful_llm_response(llm: Any, prompt: str, response: str) -> bool:
    """仅在 record 模式且上层确认解析成功后保存响应；从不参与读取。"""
    cache = get_active_replay_cache()
    if cache is None or cache.mode != "record" or not isinstance(response, str) or not response:
        return False
    cache_key, prompt_hash, fingerprint = LLMReplayCache.key_for(llm, prompt)
    await asyncio.to_thread(cache.put, cache_key, prompt_hash, fingerprint, response)
    return True
