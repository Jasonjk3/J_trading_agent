#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""根据模型管理记录构造 LLM 实例。"""
from typing import Any, Dict, Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.crud.model_management_crud import get_api_config_by_id, get_model_by_id
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_factory import ApiType, LLMFactory


def _map_api_type(api_type_raw: Optional[str]) -> str:
    if not api_type_raw:
        return ApiType.GENERIC
    x = str(api_type_raw).strip().lower()
    if x in ("openai", "open_ai"):
        return ApiType.OPENAI
    if x == "deepseek":
        return ApiType.DEEPSEEK
    return ApiType.GENERIC


def resolve_decision_llm_model_id(
    strategy_config: Optional[Dict[str, Any]],
    agent_llm_model_id: Optional[int] = None,
) -> Optional[int]:
    """策略配置优先，其次 Agent 表上的 llm_model_id。"""
    cfg = strategy_config or {}
    mid = cfg.get("decisionLlmModelId")
    if mid is not None:
        try:
            return int(mid)
        except (TypeError, ValueError):
            pass
    if agent_llm_model_id is not None:
        return int(agent_llm_model_id)
    return None


def resolve_decision_llm_temperature(strategy_config: Optional[Dict[str, Any]], default: float = 0.3) -> float:
    cfg = strategy_config or {}
    temp = cfg.get("decisionLlmTemperature")
    if temp is not None:
        try:
            return float(temp)
        except (TypeError, ValueError):
            pass
    llm_cfg = cfg.get("llm") or {}
    temp = llm_cfg.get("temperature")
    if temp is not None:
        try:
            return float(temp)
        except (TypeError, ValueError):
            pass
    return default


async def build_llm_from_managed_model(
    session: AsyncSession,
    llm_model_id: int,
    temperature: float = 0.3,
) -> Tuple[Optional[BaseLLM], Optional[str], Optional[str]]:
    """
    根据模型管理记录构造 LLM。

    Returns:
        (llm, error_message, model_display_name)
    """
    model = await get_model_by_id(session, llm_model_id)
    if not model:
        return None, f"未找到模型 id={llm_model_id}", None
    if not model.api_config_id:
        return None, "模型未绑定 API 配置", None

    cfg = await get_api_config_by_id(session, model.api_config_id)
    if not cfg or not (cfg.api_key or "").strip():
        return None, "API 配置缺失或 Key 为空", None

    api_type = _map_api_type(cfg.api_type)
    extra_headers = dict(cfg.extra_headers) if cfg.extra_headers else None
    extra_body: Dict[str, Any] = {}
    if cfg.extra_params:
        extra_body.update(dict(cfg.extra_params))
    if model.custom_params:
        extra_body.update(dict(model.custom_params))
    if extra_body and api_type in (ApiType.OPENAI, ApiType.DEEPSEEK):
        logger.debug("模型含 extra 参数，改用 generic 客户端")
        api_type = ApiType.GENERIC

    display_name = (model.name or "").strip() or model.model_id
    configured_output_tokens = getattr(model, "max_output_tokens", None)
    output_tokens = configured_output_tokens or model.max_tokens or 4096
    logger.info(
        "决策 LLM 输出额度: "
        f"model={model.model_id}, max_output_tokens={output_tokens}, "
        f"configured_output_tokens={configured_output_tokens}, "
        f"context_limit={model.max_tokens}, "
        f"use_max_completion_tokens={bool(model.use_max_completion_tokens)}"
    )
    llm = LLMFactory.create_llm_direct(
        model_name=model.model_id,
        api_key=cfg.api_key.strip(),
        api_type=api_type,
        api_url=cfg.api_url,
        temperature=float(temperature),
        max_tokens=output_tokens,
        use_max_completion_tokens=bool(model.use_max_completion_tokens),
        extra_headers=extra_headers,
        extra_body=extra_body if extra_body else None,
    )
    if not llm:
        return None, "LLMFactory 创建失败", None
    return llm, None, display_name


def build_llm_from_env_config(strategy_config: Optional[Dict[str, Any]], temperature: Optional[float] = None) -> Optional[BaseLLM]:
    """使用 strategy_config.llm 或默认 DeepSeek 环境变量构造 LLM。"""
    cfg = strategy_config or {}
    llm_config = cfg.get("llm") or {}
    model_name = llm_config.get("model", "deepseek-chat")
    api_key_env = llm_config.get("apiKeyEnv", "DEEPSEEK_API_KEY")
    temp = temperature if temperature is not None else resolve_decision_llm_temperature(cfg)
    api_url = llm_config.get("apiUrl") or llm_config.get("api_url")

    extra: Dict[str, Any] = {"max_tokens": 1024}
    if api_url:
        extra["api_url"] = api_url

    return LLMFactory.create_llm(
        model_name=model_name,
        api_key_env=api_key_env,
        temperature=temp,
        **extra,
    )


async def build_decision_llm(
    session: AsyncSession,
    strategy_config: Optional[Dict[str, Any]],
    agent_llm_model_id: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Tuple[Optional[BaseLLM], Optional[int], Optional[str]]:
    """
    为交易决策 Agent 构造 LLM。

    优先级：策略 decisionLlmModelId → Agent.llm_model_id → strategy_config.llm 环境变量。
    """
    cfg = strategy_config or {}
    temp = temperature if temperature is not None else resolve_decision_llm_temperature(cfg)
    model_id = resolve_decision_llm_model_id(cfg, agent_llm_model_id)

    if model_id is not None:
        llm, err, name = await build_llm_from_managed_model(session, model_id, temp)
        if llm:
            logger.info(
                f"决策 LLM 已使用模型管理: llm_model_id={model_id}, "
                f"display_name={name}, temperature={temp}"
            )
            return llm, model_id, name
        logger.warning(f"决策 LLM 模型管理加载失败(id={model_id}): {err}")

    llm = build_llm_from_env_config(cfg, temp)
    if llm:
        logger.info(
            f"决策 LLM 已使用环境变量配置: model={getattr(llm, 'model_name', None)}, temperature={temp}"
        )
    return llm, model_id, None
