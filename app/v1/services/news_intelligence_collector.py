#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息面采集后台任务：轮询「运行中」的任务，按间隔调用 LLM（OpenAI 兼容），解析 JSON 后写入资讯表。

需在 init_services 中启动 asyncio 后台循环；仅改数据库状态为 running 不会自动采集。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.crud import news_intelligence_crud as crud
from app.v1.crud.model_management_crud import get_api_config_by_id, get_model_by_id
from core.infrastructure.database.async_database import AsyncDatabase
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_factory import ApiType, LLMFactory
from models.inner_models.news_intelligence_model import (
    NewsIntelligenceAgentModel,
    NewsIntelligenceAgentStatus,
)

SECTOR_LABELS = {
    "banking": "银行",
    "securities": "证券",
    "insurance": "保险",
    "fund": "基金",
    "fintech": "金融科技",
    "macro": "宏观政策",
    "market_sentiment": "市场舆情",
}


def _parse_sectors(sectors: Any) -> list:
    if isinstance(sectors, list):
        return sectors
    if isinstance(sectors, str) and sectors.strip():
        try:
            data = json.loads(sectors)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _sector_text(sectors: Any) -> str:
    sectors = _parse_sectors(sectors)
    if not sectors:
        return ""
    parts = []
    for s in sectors:
        parts.append(SECTOR_LABELS.get(str(s), str(s)))
    return "、".join(parts) if parts else ""


def _agent_is_running(agent: NewsIntelligenceAgentModel) -> bool:
    s = agent.status
    if isinstance(s, NewsIntelligenceAgentStatus):
        return s == NewsIntelligenceAgentStatus.RUNNING
    return str(s).lower() in ("running", NewsIntelligenceAgentStatus.RUNNING.value)


def _normalize_llm_output(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    if hasattr(text, "content"):
        c = getattr(text, "content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            parts = []
            for block in c:
                if isinstance(block, dict) and "text" in block:
                    parts.append(str(block["text"]))
                else:
                    parts.append(str(block))
            return "".join(parts)
    return str(text)


def _looks_like_llm_error_message(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    prefixes = ("AI服务", "调用AI", "API认证", "请求失败")
    return any(t.startswith(p) for p in prefixes)


def _build_prompt(agent: NewsIntelligenceAgentModel) -> str:
    sectors = _sector_text(agent.sectors)
    kw = (agent.custom_keywords or "").strip()
    syms = (agent.symbol_codes or "").strip()
    max_n = max(1, min(50, agent.max_items_per_batch or 10))
    return f"""你是财经资讯整理助手。请结合你的检索能力（若模型支持联网/搜索，请检索公开信息），围绕下列范围汇总近期与金融、市场相关的资讯要点。

【关注方向】{sectors or '（未指定）'}
【补充关键词】{kw or '无'}
【相关标的代码】{syms or '无'}

硬性要求：
1. 只输出一个 JSON 数组（不要 Markdown 代码围栏以外的说明文字），数组元素为对象，字段名必须如下（英文键）：
   title, summary, sourceUrl, sourceName, eventTime
2. eventTime 尽量填资讯发布时间（ISO8601 字符串）；无法确定则填 null。
3. sourceUrl 填可访问的原文或报道链接；若确实没有则填 null。
4. 最多 {max_n} 条，按重要性排序。
5. summary 用 1～3 句中文概括。"""


def _first_balanced_json_array_substring(s: str) -> Optional[str]:
    """从首个 `[` 起按括号深度（忽略字符串内括号）截取到匹配的 `]`。"""
    start = s.find("[")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if escape:
            escape = False
            continue
        if in_str:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _extract_json_array(text: str) -> Optional[List[Any]]:
    if not text or not text.strip():
        return None
    s = text.strip()
    if "```" in s:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
        if m:
            s = m.group(1).strip()
    try:
        data = json.loads(s)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            return data["items"]
    except json.JSONDecodeError:
        pass
    chunk = _first_balanced_json_array_substring(s)
    if chunk:
        try:
            data = json.loads(chunk)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return None


def _dedup_hash(title: str, url: Optional[str]) -> str:
    raw = f"{title}|{url or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_event_time(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _map_api_type(s: Optional[str]) -> str:
    x = (s or "generic").lower()
    if x == "openai":
        return ApiType.OPENAI
    if x == "deepseek":
        return ApiType.DEEPSEEK
    return ApiType.GENERIC


async def build_llm_for_news_agent(
    session: AsyncSession,
    agent: NewsIntelligenceAgentModel,
) -> Tuple[Optional[BaseLLM], Optional[str]]:
    """根据模型管理中的记录与 API 配置构造 LLM。"""
    model = await get_model_by_id(session, agent.llm_model_id)
    if not model:
        return None, f"未找到模型 id={agent.llm_model_id}"
    if not model.api_config_id:
        return None, "模型未绑定 API 配置"
    cfg = await get_api_config_by_id(session, model.api_config_id)
    if not cfg or not (cfg.api_key or "").strip():
        return None, "API 配置缺失或 Key 为空"

    api_type = _map_api_type(cfg.api_type)
    extra_headers = dict(cfg.extra_headers) if cfg.extra_headers else None
    extra_body: Dict[str, Any] = {}
    if cfg.extra_params:
        extra_body.update(dict(cfg.extra_params))
    if model.custom_params:
        extra_body.update(dict(model.custom_params))
    # OpenAI/DeepSeek 封装类不合并 extra_body；带扩展参数时走 generic
    if extra_body and api_type in (ApiType.OPENAI, ApiType.DEEPSEEK):
        logger.debug("模型含 extra 参数，消息面采集改用 generic 客户端")
        api_type = ApiType.GENERIC

    llm = LLMFactory.create_llm_direct(
        model_name=model.model_id,
        api_key=cfg.api_key.strip(),
        api_type=api_type,
        api_url=cfg.api_url,
        temperature=float(agent.temperature),
        max_tokens=getattr(model, "max_output_tokens", None) or model.max_tokens or 4096,
        use_max_completion_tokens=bool(model.use_max_completion_tokens),
        extra_headers=extra_headers,
        extra_body=extra_body if extra_body else None,
    )
    if not llm:
        return None, "LLMFactory 创建失败"
    return llm, None


async def collect_one_agent(
    session: AsyncSession,
    agent_id: str,
    *,
    ignore_interval: bool = False,
    ignore_running_check: bool = False,
) -> int:
    """
    对单个任务执行一次采集；返回写入条数。
    调用方需使用独立 session 并在结束时 commit（AsyncDatabase.get_session 会 commit）。

    Args:
        ignore_interval: 为 True 时忽略「距上次采集」间隔（供脚本/运维单次试跑）。
        ignore_running_check: 为 True 时不校验「运行中」状态（供用户手动「立即采集」）。
    """
    agent = await crud.get_agent_by_id(session, agent_id)
    if not agent:
        return 0
    if not ignore_running_check and not _agent_is_running(agent):
        return 0

    now = datetime.now()
    if not ignore_interval and agent.last_run_at is not None:
        delta_sec = (now - agent.last_run_at).total_seconds()
        need_sec = max(60, int(agent.interval_minutes) * 60)
        if delta_sec < need_sec:
            return 0

    llm, err = await build_llm_for_news_agent(session, agent)
    if not llm:
        logger.warning(f"[消息面采集] {agent_id} 跳过: {err}")
        return 0

    prompt = _build_prompt(agent)
    loop = asyncio.get_event_loop()
    try:
        raw = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: llm.invoke(prompt)),
            timeout=300.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"[消息面采集] {agent_id} LLM 超时")
        return 0
    except Exception as e:
        logger.exception(f"[消息面采集] {agent_id} LLM 调用失败: {e}")
        return 0

    text = _normalize_llm_output(raw)
    if _looks_like_llm_error_message(text):
        logger.error(
            f"[消息面采集] {agent_id} LLM 返回错误类内容（非 JSON），请检查 API Key/URL/模型配置: {text[:800]}"
        )
        return 0

    rows = _extract_json_array(text)
    if not rows:
        logger.warning(
            f"[消息面采集] {agent_id} 未解析到 JSON 数组，原始片段: {(text or '')[:800]}"
        )
        await crud.update_agent(session, agent_id, {"last_run_at": now})
        return 0

    ingested = now
    inserted = 0
    for raw in rows[: agent.max_items_per_batch or 10]:
        if not isinstance(raw, dict):
            continue
        title = (raw.get("title") or raw.get("Title") or "").strip() or "无标题"
        summary = raw.get("summary") or raw.get("Summary")
        if summary is not None:
            summary = str(summary).strip() or None
        url = raw.get("sourceUrl") or raw.get("source_url") or raw.get("url")
        if url is not None:
            url = str(url).strip() or None
        source_name = raw.get("sourceName") or raw.get("source_name")
        if source_name is not None:
            source_name = str(source_name).strip() or None
        event_time = _parse_event_time(raw.get("eventTime") or raw.get("event_time"))

        dh = _dedup_hash(title, url)
        if await crud.item_dedup_exists(session, agent_id, dh):
            continue

        sort_time = event_time or ingested

        await crud.create_item(
            session,
            agent_id=agent_id,
            title=title,
            summary=summary,
            source_url=url,
            source_name=source_name,
            event_time=event_time,
            ingested_at=ingested,
            sort_time=sort_time,
            dedup_hash=dh,
        )
        inserted += 1

    await crud.update_agent(session, agent_id, {"last_run_at": now})
    logger.info(f"[消息面采集] {agent_id} 完成，写入 {inserted} 条")
    return inserted


async def run_news_intelligence_tick(db: AsyncDatabase) -> None:
    """扫描所有运行中任务并执行到期采集。"""
    async with db.get_session() as session:
        agents = await crud.list_running_agents_all_users(session)
        ids = [a.id for a in agents]

    if not ids:
        logger.debug("[消息面采集] 当前无运行中任务，跳过本轮")
        return

    logger.info(f"[消息面采集] 本轮扫描到 {len(ids)} 个运行中任务")

    for aid in ids:
        try:
            async with db.get_session() as session:
                await collect_one_agent(session, aid)
        except Exception:
            logger.exception(f"[消息面采集] 任务 {aid} 未处理异常")


async def news_intelligence_worker_loop(db: AsyncDatabase, interval_sec: float = 60.0) -> None:
    """后台协程：周期性执行 run_news_intelligence_tick。"""
    await asyncio.sleep(2)
    while True:
        try:
            await run_news_intelligence_tick(db)
        except Exception:
            logger.exception("[消息面采集] tick 异常")
        await asyncio.sleep(interval_sec)
