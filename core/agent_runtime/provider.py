"""Native Chat Completions adapter over the project's existing LLM configuration.

The legacy string-only _call() path is intentionally not used: it discards tool
calls and usage. HTTP is asynchronous so cancellation reaches the transport.
"""

import asyncio
import json
import time
from typing import Any

import httpx

from core.agent_runtime.llm_contracts import LLMResponse, LLMUsage, ToolCall
from core.llm.openai_compatible_url import normalize_chat_completions_url


class ConversationProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def estimate_tokens(payload: Any) -> int:
    # Conservative fallback when a compatible provider omits usage. Never count
    # an unmetered response as zero against the loop's token budget.
    def meter(value):
        if isinstance(value, dict):
            if value.get("type") == "image_url":
                return "[image]" * 256
            return {key: meter(item) for key, item in value.items()}
        if isinstance(value, list):
            return [meter(item) for item in value]
        return value
    return max(1, len(json.dumps(meter(payload), ensure_ascii=False).encode("utf-8")))


class ExistingLLMProvider:
    def __init__(self, llm, *, transport=None):
        self.llm = llm
        self.transport = transport

    async def complete(self, messages, *, tools=None, max_tokens=None,
                       timeout_seconds=None, metadata=None, **_):
        llm = self.llm
        model = str(llm.model_name)
        extra = dict(getattr(llm, "extra_body", None) or {})
        # Model custom parameters may not replace identity, messages or the
        # authorized tool list, or turn the request into an unmanaged stream.
        for key in ("model", "messages", "tools", "tool_choice", "stream",
                    "max_tokens", "max_completion_tokens", "n", "functions", "function_call"):
            extra.pop(key, None)
        payload = {**extra, "model": model,
                   "messages": [item.to_payload() for item in messages],
                   "temperature": getattr(llm, "temperature", 0.7), "stream": False}
        completion_limit = getattr(llm, "max_completion_tokens", None)
        use_completion = bool(getattr(llm, "use_max_completion_tokens", False) or
                              completion_limit is not None or model.startswith(("o1", "o3")))
        configured_limit = completion_limit or getattr(llm, "max_tokens", None) or 2048
        payload["max_completion_tokens" if use_completion else "max_tokens"] = min(
            configured_limit, max_tokens if max_tokens is not None else configured_limit)
        if tools:
            payload["tools"] = [tool.to_payload() for tool in tools]
        headers = httpx.Headers({"Content-Type": "application/json", **(getattr(llm, "extra_headers", None) or {})})
        headers["Authorization"] = "Bearer " + str(llm.api_key)
        organization = getattr(llm, "organization", None)
        if organization:
            headers["OpenAI-Organization"] = organization
        url = normalize_chat_completions_url(llm.api_url)
        proxies = llm._get_proxies() if hasattr(llm, "_get_proxies") else None
        proxy = proxies.get("https" if url.startswith("https:") else "http") if proxies else None
        timeout = min(float(getattr(llm, "timeout", 180)), timeout_seconds or 180)
        started = time.monotonic()
        status, error_code, response = "failed", None, None
        retries = max(0, min(int(getattr(llm, "max_retries", 2)), 2))
        try:
            async with httpx.AsyncClient(timeout=timeout, proxy=proxy, transport=self.transport) as client:
                for attempt in range(retries + 1):
                    try:
                        http_response = await client.post(url, json=payload, headers=headers)
                    except (httpx.TimeoutException, httpx.TransportError) as exc:
                        # Retrying only model calls, never tool side effects.
                        if attempt < retries:
                            await asyncio.sleep(0.25 * (2 ** attempt))
                            continue
                        code = "LLM_TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "LLM_UNAVAILABLE"
                        raise ConversationProviderError(code, "模型服务暂时不可用，请稍后重试") from None
                    if http_response.status_code == 429 or http_response.status_code >= 500:
                        if attempt < retries:
                            await asyncio.sleep(0.25 * (2 ** attempt))
                            continue
                    if http_response.is_error:
                        code = {401: "LLM_AUTH_FAILED", 403: "LLM_AUTH_FAILED", 429: "LLM_RATE_LIMITED"}.get(
                            http_response.status_code, "LLM_REQUEST_FAILED")
                        raise ConversationProviderError(code, "模型请求失败，请检查模型配置或稍后重试")
                    try:
                        response = self._parse(http_response.json(), model, payload)
                    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                        raise ConversationProviderError("LLM_INVALID_RESPONSE", "模型服务返回了无效的响应") from None
                    status = "success"
                    return response
        except ConversationProviderError as exc:
            error_code = exc.code
            raise
        finally:
            # Preserve the existing usage/cost monitor without copying prompts,
            # tool arguments or model output into its logs.
            if hasattr(llm, "_track_usage"):
                try:
                    usage = response.usage if response else LLMUsage()
                    llm._track_usage(
                        prompt="", completion="", status=status, error_message=error_code,
                        response_time_ms=int((time.monotonic() - started) * 1000),
                        prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
                        agent_name=(metadata or {}).get("agent_name"), task_type="agent_conversation",
                        user_id=(metadata or {}).get("user_id"), session_id=(metadata or {}).get("session_id"),
                    )
                except Exception:
                    pass  # Monitoring must not break a completed conversation.

    @staticmethod
    def _parse(data, model, payload):
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content if item.get("type") == "text")
        if not isinstance(content, str):
            raise ValueError("invalid content")
        calls = []
        for index, item in enumerate(message.get("tool_calls") or []):
            function = item["function"]
            raw = function.get("arguments", "{}")
            if not isinstance(raw, str):
                raw = json.dumps(raw, ensure_ascii=False)
            error = None
            try:
                arguments = json.loads(raw)
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be object")
            except (ValueError, TypeError):
                arguments, error = {}, "invalid_json_arguments"
            calls.append(ToolCall(str(item.get("id") or f"call_{index}"),
                                  str(function["name"]), arguments, raw_arguments=raw,
                                  argument_error=error))
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or estimate_tokens(payload))
        completion_tokens = int(usage.get("completion_tokens") or estimate_tokens(message))
        total = max(prompt_tokens + completion_tokens, int(usage.get("total_tokens") or 0))
        return LLMResponse(content=content, model=model, finish_reason=choice.get("finish_reason"),
                           usage=LLMUsage(prompt_tokens, completion_tokens, total), tool_calls=tuple(calls))
