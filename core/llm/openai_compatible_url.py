"""
OpenAI 兼容 Chat Completions 端点的 URL 规范化。

中转 / 自建网关常只填到 .../v1，必须补全为 .../v1/chat/completions 才能 POST。
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def normalize_chat_completions_url(url: str) -> str:
    """
    将基础地址或仅含 /v1 的地址补全为可请求的 chat completions 端点。

    例如：
        https://www.dmxapi.cn -> https://www.dmxapi.cn/v1/chat/completions
        https://api.xxx.com/v1 -> https://api.xxx.com/v1/chat/completions
    """
    if not url:
        return url

    url = url.strip()

    if "/v1/chat/completions" in url:
        return url

    if url.endswith("/"):
        url = url.rstrip("/")

    parsed = urlparse(url)

    if not parsed.path or parsed.path == "/":
        normalized_url = f"{url}/v1/chat/completions"
        logger.info(f"自动补全API URL: {url} -> {normalized_url}")
        return normalized_url

    if parsed.path.endswith("/v1") or parsed.path == "/v1":
        normalized_url = f"{url}/chat/completions"
        logger.info(f"自动补全API URL: {url} -> {normalized_url}")
        return normalized_url

    if parsed.path.startswith("/v1/") and "chat/completions" not in parsed.path:
        normalized_url = f"{url}/chat/completions"
        logger.info(f"自动补全API URL: {url} -> {normalized_url}")
        return normalized_url

    return url
