#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/07
# @Author : AI Assistant
"""
模型对比服务 2.0
处理模型对比测试的业务逻辑，支持数据持久化
"""
import asyncio
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.schemas.model_compare_schema import (
    ModelInfo,
    ProviderInfo,
    ModelsListResponse,
    ModelCompareRequest,
    ModelCompareResponse,
    ModelResult,
    TokenUsage,
    CompareSummary,
    CostInfo,
    ApiConfig,
    # 2.0 新增
    ApiConfigCreate,
    ApiConfigUpdate,
    ApiConfigResponse,
    ModelManageCreate,
    ModelManageUpdate,
    ModelManageResponse,
    ModelTestRequest,
    ModelTestResult,
    ModelTestResponse,
    CompareHistoryItem,
    CompareHistoryDetailResponse,
)
from app.v1.crud import model_compare_crud as crud
from app.v1.crud import model_management_crud as mgmt_crud
from core.llm.llm_factory import LLMFactory, ApiType
from core.llm.llm_models import LLMModels
from core.llm.base.cost_calculator import (
    get_cost_calculator,
)


def _infer_provider_from_model_id(model_id: str) -> str:
    """根据模型 ID 推断提供商（仅用于显示）"""
    model_id_lower = model_id.lower()
    if model_id_lower.startswith("deepseek"):
        return "DeepSeek"
    elif model_id_lower.startswith(("gpt", "o1", "o3")):
        return "OpenAI"
    elif model_id_lower.startswith("claude"):
        return "Anthropic"
    elif model_id_lower.startswith("gemini"):
        return "Google"
    else:
        return "Custom"


def _get_api_key_env_for_provider(provider: str) -> str:
    """
    根据提供商名称获取对应的 API Key 环境变量名
    
    Args:
        provider: 提供商名称（如 "OpenAI", "DeepSeek", "Anthropic", "Google"）
        
    Returns:
        API Key 环境变量名
    """
    provider_lower = provider.lower() if provider else ""
    
    if "deepseek" in provider_lower:
        return LLMModels.DEEPSEEK_API_KEY_ENV
    elif "openai" in provider_lower:
        return LLMModels.OPENAI_API_KEY_ENV
    elif "anthropic" in provider_lower:
        return "ANTHROPIC_API_KEY"
    elif "google" in provider_lower:
        return "GOOGLE_API_KEY"
    else:
        # 默认返回 OpenAI 的环境变量名
        return LLMModels.OPENAI_API_KEY_ENV


class ModelCompareService:
    """模型对比服务"""

    def __init__(self):
        """初始化服务"""
        self.cost_calculator = get_cost_calculator()
        # 异步任务存储（生产环境建议使用 Redis）
        self._tasks: Dict[str, Dict[str, Any]] = {}
        # 模型配置缓存（从数据库加载）
        self._model_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_loaded: bool = False

    async def _load_model_cache(self, session: AsyncSession) -> None:
        """
        从数据库加载模型配置到缓存
        
        Args:
            session: 数据库会话
        """
        try:
            models = await crud.get_models(session, is_active=True)
            self._model_cache = {}
            for model in models:
                self._model_cache[model.model_id] = {
                    "id": model.id,
                    "name": model.name,
                    "provider": model.provider,
                    "description": model.description,
                    "max_tokens": model.max_tokens,
                    "supports_streaming": bool(model.supports_streaming),
                    "supports_thinking": bool(model.supports_thinking),
                    "input_price_per_1m": float(model.input_price_per_1m) if model.input_price_per_1m else 0,
                    "output_price_per_1m": float(model.output_price_per_1m) if model.output_price_per_1m else 0,
                    "api_config_id": model.api_config_id,
                    "status": model.status,
                    "api_key_env": _get_api_key_env_for_provider(model.provider),
                }
            self._cache_loaded = True
            logger.info(f"已从数据库加载 {len(self._model_cache)} 个模型配置")
        except Exception as e:
            logger.error(f"加载模型配置缓存失败: {e}")
            self._model_cache = {}

    async def get_model_config(
        self, 
        model_id: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取单个模型配置
        
        Args:
            model_id: 模型 ID
            session: 数据库会话
            
        Returns:
            模型配置字典，不存在则返回 None
        """
        # 先从缓存获取
        if model_id in self._model_cache:
            return self._model_cache[model_id]
        
        # 如果缓存中没有，尝试从数据库查询
        if session:
            model = await crud.get_model_by_model_id(session, model_id)
            if model:
                config = {
                    "id": model.id,
                    "name": model.name,
                    "provider": model.provider,
                    "description": model.description,
                    "max_tokens": model.max_tokens,
                    "supports_streaming": bool(model.supports_streaming),
                    "supports_thinking": bool(model.supports_thinking),
                    "input_price_per_1m": float(model.input_price_per_1m) if model.input_price_per_1m else 0,
                    "output_price_per_1m": float(model.output_price_per_1m) if model.output_price_per_1m else 0,
                    "api_config_id": model.api_config_id,
                    "status": model.status,
                    "api_key_env": _get_api_key_env_for_provider(model.provider),
                }
                # 更新缓存
                self._model_cache[model_id] = config
                return config
        
        return None

    def clear_model_cache(self) -> None:
        """清除模型配置缓存"""
        self._model_cache = {}
        self._cache_loaded = False
        logger.info("已清除模型配置缓存")

    async def get_available_models(
        self, 
        session: AsyncSession
    ) -> ModelsListResponse:
        """
        获取可用模型列表（从数据库读取）
        
        Args:
            session: 数据库会话
            
        Returns:
            ModelsListResponse: 模型列表响应
        """
        # 从数据库加载模型
        db_models = await crud.get_models(session, is_active=True)
        
        models: List[ModelInfo] = []
        providers_dict: Dict[str, List[str]] = {}

        for db_model in db_models:
            # 获取价格信息（优先使用数据库配置）
            cost_info = None
            if db_model.input_price_per_1m or db_model.output_price_per_1m:
                cost_info = CostInfo(
                    prompt=db_model.input_price_per_1k,
                    completion=db_model.output_price_per_1k,
                    currency="USD"
                )
            else:
                # 回退到默认价格配置
                pricing = self.cost_calculator.get_pricing(db_model.model_id)
                if pricing:
                    cost_info = CostInfo(
                        prompt=pricing.input_price_per_1k,
                        completion=pricing.output_price_per_1k,
                        currency="USD"
                    )

            model_info = ModelInfo(
                id=db_model.model_id,
                name=db_model.name,
                provider=db_model.provider,
                description=db_model.description,
                enabled=bool(db_model.is_active),
                max_tokens=db_model.max_tokens,
                supports_streaming=bool(db_model.supports_streaming),
                supports_thinking=bool(db_model.supports_thinking),
                cost_per_1k_tokens=cost_info,
            )
            models.append(model_info)

            # 按提供商分组
            provider = db_model.provider
            if provider not in providers_dict:
                providers_dict[provider] = []
            providers_dict[provider].append(db_model.model_id)
            
            # 更新缓存
            self._model_cache[db_model.model_id] = {
                "id": db_model.id,
                "name": db_model.name,
                "provider": db_model.provider,
                "description": db_model.description,
                "max_tokens": db_model.max_tokens,
                "supports_streaming": bool(db_model.supports_streaming),
                "supports_thinking": bool(db_model.supports_thinking),
                "input_price_per_1m": float(db_model.input_price_per_1m) if db_model.input_price_per_1m else 0,
                "output_price_per_1m": float(db_model.output_price_per_1m) if db_model.output_price_per_1m else 0,
                "api_config_id": db_model.api_config_id,
                "status": db_model.status,
                "api_key_env": _get_api_key_env_for_provider(db_model.provider),
            }

        # 构建提供商列表
        providers = [
            ProviderInfo(name=name, models=model_ids)
            for name, model_ids in providers_dict.items()
        ]
        
        self._cache_loaded = True

        return ModelsListResponse(models=models, providers=providers)

    async def compare_models(
        self,
        request: ModelCompareRequest,
        session: Optional[AsyncSession] = None,
        save_to_db: bool = True
    ) -> ModelCompareResponse:
        """
        执行模型对比测试（同步等待所有结果）
        
        Args:
            request: 对比请求
            session: 数据库会话（可选，如需持久化则必须提供）
            save_to_db: 是否保存到数据库
            
        Returns:
            ModelCompareResponse: 对比结果
        """
        task_id = f"compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now()

        # 获取 API 配置（优先使用前端传递的配置）
        api_config = request.api_config
        
        # 如果前端没有传递 API 配置，或传递的是脱敏值（***），尝试从数据库获取
        # 1. 先尝试获取默认 API 配置
        # 2. 然后根据每个模型获取其关联的 API 配置
        default_db_api_config = None
        model_api_configs: Dict[str, ApiConfig] = {}  # 存储每个模型的 API 配置
        
        # 检查前端传递的 api_config 是否有效（不是脱敏值）
        is_api_config_valid = (
            api_config and 
            api_config.api_key and 
            api_config.api_key.strip() != "***" and 
            len(api_config.api_key.strip()) > 3
        )
        
        if session and not is_api_config_valid:
            # 获取默认 API 配置
            default_config = await crud.get_default_api_config(session)
            if default_config:
                # 检查 API 密钥是否有效（不是脱敏值）
                default_api_key = default_config.api_key
                if default_api_key and default_api_key.strip() != "***" and len(default_api_key.strip()) > 3:
                    default_db_api_config = ApiConfig(
                        api_key=default_api_key.strip(),
                        api_url=default_config.api_url
                    )
                    logger.info(f"使用数据库默认 API 配置: {default_config.name}")
                else:
                    logger.warning(f"默认 API 配置密钥无效（可能是脱敏值），跳过使用")
            
            # 获取每个模型关联的 API 配置
            for model_id in request.models:
                managed_model = await crud.get_model_by_model_id(session, model_id)
                if managed_model and managed_model.api_config_id:
                    config = await crud.get_api_config_by_id(session, managed_model.api_config_id)
                    if config:
                        # 检查 API 密钥是否有效（不是脱敏值）
                        model_api_key = config.api_key
                        if model_api_key and model_api_key.strip() != "***" and len(model_api_key.strip()) > 3:
                            model_api_configs[model_id] = ApiConfig(
                                api_key=model_api_key.strip(),
                                api_url=config.api_url
                            )
                            logger.info(f"模型 {model_id} 使用关联的 API 配置: {config.name}")
                        else:
                            logger.warning(f"模型 {model_id} 关联的 API 配置密钥无效（可能是脱敏值），跳过使用")

        # 加载模型缓存（如果还没有加载）
        if session and not self._cache_loaded:
            await self._load_model_cache(session)

        # 验证模型列表
        # 优先从数据库/缓存获取配置，也支持自定义 API 配置
        valid_models = []
        for model_id in request.models:
            # 1. 先检查缓存（数据库模型）
            if model_id in self._model_cache:
                valid_models.append(model_id)
                logger.info(f"使用数据库模型配置: {model_id}")
            elif is_api_config_valid:
                # 2. 使用自定义 API 配置时，接受任意模型名称
                valid_models.append(model_id)
                logger.info(f"使用自定义 API 配置测试模型: {model_id}")
            elif model_id in model_api_configs:
                # 3. 使用模型关联的 API 配置
                valid_models.append(model_id)
                logger.info(f"使用模型关联 API 配置测试模型: {model_id}")
            elif default_db_api_config:
                # 4. 使用默认 API 配置
                valid_models.append(model_id)
                logger.info(f"使用默认 API 配置测试模型: {model_id}")
            else:
                logger.warning(f"忽略未知模型: {model_id}")

        if not valid_models:
            raise ValueError("没有有效的模型可供测试")

        # 并发调用所有模型
        tasks = [
            self._call_single_model(
                model_id=model_id,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout=request.timeout or 60,
                # 优先级：前端配置（有效） > 模型关联配置 > 默认配置
                api_config=api_config if is_api_config_valid 
                    else model_api_configs.get(model_id, default_db_api_config),
                session=session,
            )
            for model_id in valid_models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        model_results: List[ModelResult] = []
        for i, result in enumerate(results):
            model_id = valid_models[i]
            if isinstance(result, Exception):
                # 异常情况，从缓存获取配置
                config = self._model_cache.get(model_id, {"name": model_id, "provider": "Custom"})
                model_results.append(ModelResult(
                    model_id=model_id,
                    model_name=config.get("name", model_id),
                    provider=config.get("provider", "Custom"),
                    status="error",
                    error=str(result),
                ))
            else:
                model_results.append(result)

        completed_at = datetime.now()

        # 计算统计摘要
        summary = self._calculate_summary(model_results)

        response = ModelCompareResponse(
            task_id=task_id,
            prompt=request.user_prompt,
            system_prompt=request.system_prompt,
            created_at=created_at,
            completed_at=completed_at,
            results=model_results,
            summary=summary,
        )

        # 保存到数据库
        if save_to_db and session and request.save_history:
            try:
                await self._save_compare_history(
                    session=session,
                    task_id=task_id,
                    request=request,
                    results=model_results,
                    summary=summary,
                    created_at=created_at,
                    completed_at=completed_at
                )
            except Exception as e:
                logger.error(f"保存对比历史记录失败: {e}", exc_info=True)
                # 不影响返回结果

        return response

    async def _save_compare_history(
        self,
        session: AsyncSession,
        task_id: str,
        request: ModelCompareRequest,
        results: List[ModelResult],
        summary: CompareSummary,
        created_at: datetime,
        completed_at: datetime
    ) -> None:
        """保存对比历史记录到数据库"""
        # 创建历史记录
        history_data = {
            "task_id": task_id,
            "system_prompt": request.system_prompt,
            "user_prompt": request.user_prompt,
            "temperature": Decimal(str(request.temperature)) if request.temperature else None,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout,
            "model_ids": request.models,
            "api_config_id": None,  # 如果使用的是保存的配置，可以在这里关联
            "total_models": summary.total_models,
            "success_count": summary.success_count,
            "failed_count": summary.failed_count,
            "avg_latency_ms": int(summary.avg_latency_ms) if summary.avg_latency_ms else None,
            "total_tokens": summary.total_tokens,
            "total_cost_usd": Decimal(str(summary.total_cost_usd or 0)),
            "total_cost_cny": Decimal(str(summary.total_cost_cny or 0)),
            "user_id": request.user_id,
            "created_at": created_at,
            "completed_at": completed_at,
        }
        history = await crud.create_compare_history(session, history_data)

        # 创建结果记录
        results_data = []
        for r in results:
            result_data = {
                "history_id": history.id,
                "model_id": r.model_id,
                "model_name": r.model_name,
                "provider": r.provider,
                "status": r.status,
                "response": r.response,
                "prompt_tokens": r.token_usage.prompt_tokens if r.token_usage else 0,
                "completion_tokens": r.token_usage.completion_tokens if r.token_usage else 0,
                "total_tokens": r.token_usage.total_tokens if r.token_usage else 0,
                "latency_ms": r.latency_ms,
                "cost_usd": Decimal(str(r.cost_usd or 0)),
                "cost_cny": Decimal(str(r.cost_cny or 0)),
                "error": r.error,
            }
            results_data.append(result_data)

        await crud.batch_create_compare_results(session, results_data)
        await session.commit()
        logger.info(f"对比历史记录已保存: task_id={task_id}, history_id={history.id}")

    async def _call_single_model(
        self,
        model_id: str,
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = None,
        timeout: int = 60,
        api_config: Optional[ApiConfig] = None,
        session: Optional[AsyncSession] = None,
    ) -> ModelResult:
        """
        调用单个模型
        
        Args:
            model_id: 模型ID
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大 Token 数
            timeout: 超时时间（秒）
            api_config: 自定义 API 配置
            session: 数据库会话
            
        Returns:
            ModelResult: 模型测试结果
        """
        # 优先从缓存/数据库获取模型配置
        config = self._model_cache.get(model_id)
        
        # 如果缓存中没有，尝试从数据库查询
        if not config and session:
            config = await self.get_model_config(model_id, session)
        
        # 如果没有数据库配置但提供了自定义 API 配置，创建临时配置
        if not config and api_config and api_config.api_key:
            inferred_provider = _infer_provider_from_model_id(model_id)
            config = {
                "name": model_id,
                "provider": inferred_provider,
                "api_key_env": _get_api_key_env_for_provider(inferred_provider),
            }
        elif not config:
            return ModelResult(
                model_id=model_id,
                model_name=model_id,
                provider="unknown",
                status="error",
                error=f"未知模型: {model_id}，请在数据库中配置该模型或提供 API 配置",
            )

        start_time = time.time()
        
        try:
            # 获取 API 配置信息
            api_key = ""
            api_url = None
            api_type = ApiType.GENERIC  # 默认使用通用类型
            use_max_completion_tokens = config.get("use_max_completion_tokens", False)
            extra_headers = None
            extra_body = None
            
            # 优先使用传入的 api_config（前端配置或模型关联配置）
            # 注意：需要检查 api_key 是否为脱敏值（***），如果是则忽略
            if api_config and api_config.api_key:
                # 检查是否为脱敏值或无效值
                api_key_value = api_config.api_key.strip()
                if api_key_value and api_key_value != "***" and len(api_key_value) > 3:
                    api_key = api_key_value
                    api_url = api_config.api_url
                    logger.debug(f"使用前端传递的 API 配置，API Key 长度: {len(api_key)}")
                    # 从 api_config 获取额外配置（如果有）
                    if hasattr(api_config, 'api_type') and api_config.api_type:
                        api_type = api_config.api_type
                    if hasattr(api_config, 'extra_headers') and api_config.extra_headers:
                        extra_headers = api_config.extra_headers
                    if hasattr(api_config, 'extra_params') and api_config.extra_params:
                        extra_body = api_config.extra_params
                else:
                    logger.warning(f"检测到无效的 API Key（可能是脱敏值），将尝试从数据库获取: {api_key_value[:10] if api_key_value else 'None'}")
            
            if not api_key:
                logger.error(f"模型 {model_id} 未获取到有效的 API Key，请检查配置")
                return ModelResult(
                    model_id=model_id,
                    model_name=config.get("name", model_id),
                    provider=config.get("provider", "Custom"),
                    status="error",
                    error="未提供有效的 API Key，请检查 API 密钥配置（注意：脱敏值 *** 不能用于API调用）",
                    latency_ms=int((time.time() - start_time) * 1000),
                )
            
            # 使用新的 LLMFactory.create_llm_direct 方法
            llm = LLMFactory.create_llm_direct(
                model_name=model_id,
                api_key=api_key,
                api_type=api_type,
                api_url=api_url,
                temperature=temperature,
                max_tokens=max_tokens,
                use_max_completion_tokens=use_max_completion_tokens,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )

            if not llm:
                return ModelResult(
                    model_id=model_id,
                    model_name=config["name"],
                    provider=config.get("provider", "Custom"),
                    status="error",
                    error="创建 LLM 实例失败，请检查 API 配置",
                    latency_ms=int((time.time() - start_time) * 1000),
                )

            # 构建消息
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})

            # 调用模型（使用 asyncio.wait_for 设置超时）
            try:
                # 在线程池中执行同步调用
                loop = asyncio.get_event_loop()
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: llm.invoke(user_prompt if not system_prompt else f"{system_prompt}\n\n{user_prompt}")
                    ),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                return ModelResult(
                    model_id=model_id,
                    model_name=config["name"],
                    provider=config.get("provider", "Custom"),
                    status="timeout",
                    error=f"请求超时（{timeout}秒）",
                    latency_ms=int((time.time() - start_time) * 1000),
                )

            latency_ms = int((time.time() - start_time) * 1000)

            # 检查响应是否为错误消息（retry_with_backoff 装饰器会返回错误字符串而不是抛出异常）
            error_prefixes = [
                "AI服务认证失败",
                "AI服务请求参数错误",
                "AI服务请求失败",
                "AI服务网络请求异常",
                "AI服务请求超时",
                "调用AI服务时发生错误",
                "API 响应解析失败",
            ]
            
            is_error_response = False
            if response and isinstance(response, str):
                for prefix in error_prefixes:
                    if response.startswith(prefix) or prefix in response:
                        is_error_response = True
                        break
            
            if is_error_response:
                return ModelResult(
                    model_id=model_id,
                    model_name=config["name"],
                    provider=config.get("provider", "Custom"),
                    status="error",
                    error=response,
                    latency_ms=latency_ms,
                )

            # 获取 Token 使用量（从 LLM 实例获取，如果支持的话）
            # 这里使用估算方式，实际应从 API 响应中获取
            prompt_tokens = self._estimate_tokens(
                (system_prompt or "") + user_prompt
            )
            completion_tokens = self._estimate_tokens(response)
            total_tokens = prompt_tokens + completion_tokens

            # 计算费用
            cost_usd, cost_cny = self.cost_calculator.calculate_cost(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model_name=model_id,
            )

            return ModelResult(
                model_id=model_id,
                model_name=config["name"],
                provider=config.get("provider", "Custom"),
                status="success",
                response=response,
                token_usage=TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                ),
                latency_ms=latency_ms,
                cost_usd=float(cost_usd),
                cost_cny=float(cost_cny),
            )

        except Exception as e:
            logger.error(f"调用模型 {model_id} 失败: {e}", exc_info=True)
            return ModelResult(
                model_id=model_id,
                model_name=config["name"],
                provider=config.get("provider", "Custom"),
                status="error",
                error=str(e),
                latency_ms=int((time.time() - start_time) * 1000),
            )

    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的 Token 数量
        
        简单估算：中文约1.5字符/token，英文约4字符/token
        实际应使用 tiktoken 等库精确计算
        
        Args:
            text: 文本内容
            
        Returns:
            估算的 Token 数量
        """
        if not text:
            return 0
        
        # 统计中文字符和其他字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        # 估算 Token 数
        estimated = int(chinese_chars / 1.5 + other_chars / 4)
        return max(1, estimated)

    def _calculate_summary(self, results: List[ModelResult]) -> CompareSummary:
        """
        计算统计摘要
        
        Args:
            results: 模型测试结果列表
            
        Returns:
            CompareSummary: 统计摘要
        """
        total_models = len(results)
        success_count = sum(1 for r in results if r.status == "success")
        failed_count = total_models - success_count

        # 计算延迟统计
        latencies = [r.latency_ms for r in results if r.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else None
        min_latency = min(latencies) if latencies else None
        max_latency = max(latencies) if latencies else None

        # 计算 Token 和费用统计
        total_tokens = sum(
            r.token_usage.total_tokens if r.token_usage else 0
            for r in results
        )
        total_cost_usd = sum(
            r.cost_usd or 0 for r in results
        )
        total_cost_cny = sum(
            r.cost_cny or 0 for r in results
        )

        return CompareSummary(
            total_models=total_models,
            success_count=success_count,
            failed_count=failed_count,
            avg_latency_ms=round(avg_latency, 2) if avg_latency else None,
            min_latency_ms=min_latency,
            max_latency_ms=max_latency,
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost_usd, 6) if total_cost_usd else None,
            total_cost_cny=round(total_cost_cny, 4) if total_cost_cny else None,
        )

    # ============================================================================
    # 2.0 新增：API 配置管理
    # ============================================================================

    async def get_api_configs(
        self,
        session: AsyncSession,
        provider: Optional[str] = None,
        is_active: Optional[bool] = None,
        user_id: Optional[str] = None
    ) -> List[ApiConfigResponse]:
        """获取 API 配置列表"""
        configs = await crud.get_api_configs(
            session, provider=provider, is_active=is_active, user_id=user_id
        )
        return [ApiConfigResponse(**c.to_dict(hide_key=True)) for c in configs]

    async def get_api_config(
        self,
        session: AsyncSession,
        config_id: int
    ) -> Optional[ApiConfigResponse]:
        """获取单个 API 配置"""
        config = await crud.get_api_config_by_id(session, config_id)
        if config:
            return ApiConfigResponse(**config.to_dict(hide_key=True))
        return None

    async def create_api_config(
        self,
        session: AsyncSession,
        data: ApiConfigCreate
    ) -> ApiConfigResponse:
        """创建 API 配置"""
        config = await crud.create_api_config(session, data.model_dump())
        await session.commit()
        return ApiConfigResponse(**config.to_dict(hide_key=True))

    async def update_api_config(
        self,
        session: AsyncSession,
        config_id: int,
        data: ApiConfigUpdate
    ) -> Optional[ApiConfigResponse]:
        """更新 API 配置"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        config = await crud.update_api_config(session, config_id, update_data)
        if config:
            await session.commit()
            return ApiConfigResponse(**config.to_dict(hide_key=True))
        return None

    async def delete_api_config(
        self,
        session: AsyncSession,
        config_id: int
    ) -> bool:
        """删除 API 配置"""
        result = await crud.delete_api_config(session, config_id)
        if result:
            await session.commit()
        return result

    async def set_default_api_config(
        self,
        session: AsyncSession,
        config_id: int,
        user_id: Optional[str] = None
    ) -> bool:
        """设置默认 API 配置"""
        result = await crud.set_default_api_config(session, config_id, user_id)
        if result:
            await session.commit()
        return result

    # ============================================================================
    # 2.0 新增：模型管理
    # ============================================================================

    async def get_managed_models(
        self,
        session: AsyncSession,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        is_active: Optional[bool] = None,
        user_id: Optional[str] = None
    ) -> List[ModelManageResponse]:
        """获取管理的模型列表"""
        models = await crud.get_models(
            session, provider=provider, status=status, 
            is_active=is_active, user_id=user_id
        )
        return [ModelManageResponse(**m.to_dict()) for m in models]

    async def get_managed_model(
        self,
        session: AsyncSession,
        model_id: int
    ) -> Optional[ModelManageResponse]:
        """获取单个管理的模型"""
        model = await crud.get_model_by_id(session, model_id)
        if model:
            return ModelManageResponse(**model.to_dict())
        return None

    async def create_managed_model(
        self,
        session: AsyncSession,
        data: ModelManageCreate
    ) -> ModelManageResponse:
        """创建管理的模型"""
        model_data = data.model_dump()
        # 转换价格字段为 Decimal
        if 'input_price_per_1m' in model_data:
            model_data['input_price_per_1m'] = Decimal(str(model_data['input_price_per_1m']))
        if 'output_price_per_1m' in model_data:
            model_data['output_price_per_1m'] = Decimal(str(model_data['output_price_per_1m']))
        
        model = await crud.create_model(session, model_data)
        await session.commit()
        return ModelManageResponse(**model.to_dict())

    async def update_managed_model(
        self,
        session: AsyncSession,
        model_id: int,
        data: ModelManageUpdate
    ) -> Optional[ModelManageResponse]:
        """更新管理的模型"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        # 转换价格字段为 Decimal
        if 'input_price_per_1m' in update_data:
            update_data['input_price_per_1m'] = Decimal(str(update_data['input_price_per_1m']))
        if 'output_price_per_1m' in update_data:
            update_data['output_price_per_1m'] = Decimal(str(update_data['output_price_per_1m']))
        
        model = await crud.update_model(session, model_id, update_data)
        if model:
            await session.commit()
            return ModelManageResponse(**model.to_dict())
        return None

    async def delete_managed_model(
        self,
        session: AsyncSession,
        model_id: int
    ) -> bool:
        """删除管理的模型"""
        result = await crud.delete_model(session, model_id)
        if result:
            await session.commit()
        return result

    async def test_models(
        self,
        session: AsyncSession,
        request: ModelTestRequest,
        user_id: Optional[str] = None
    ) -> ModelTestResponse:
        """
        测试模型连通性
        
        Args:
            session: 数据库会话
            request: 测试请求
            user_id: 用户ID
            
        Returns:
            ModelTestResponse: 测试响应
        """
        # 获取要测试的模型
        if request.model_ids:
            # 测试指定的模型
            models = []
            for mid in request.model_ids:
                model = await crud.get_model_by_id(session, mid)
                if model:
                    models.append(model)
        else:
            # 测试所有启用的模型
            models = await crud.get_models(session, is_active=True, user_id=user_id)

        if not models:
            return ModelTestResponse(
                total=0,
                available=0,
                unavailable=0,
                results=[]
            )

        # 并发测试所有模型
        test_tasks = []
        for model in models:
            test_tasks.append(
                self._test_single_model(
                    session=session,
                    model=model,
                    test_prompt=request.test_prompt,
                    timeout=request.timeout
                )
            )

        results = await asyncio.gather(*test_tasks, return_exceptions=True)

        # 处理结果
        test_results: List[ModelTestResult] = []
        available_count = 0
        unavailable_count = 0

        for i, result in enumerate(results):
            model = models[i]
            if isinstance(result, Exception):
                test_results.append(ModelTestResult(
                    id=model.id,
                    model_id=model.model_id,
                    name=model.name,
                    status="unavailable",
                    error=str(result)
                ))
                unavailable_count += 1
            else:
                test_results.append(result)
                if result.status == "available":
                    available_count += 1
                else:
                    unavailable_count += 1

        await session.commit()

        return ModelTestResponse(
            total=len(models),
            available=available_count,
            unavailable=unavailable_count,
            results=test_results
        )

    async def _test_single_model(
        self,
        session: AsyncSession,
        model,
        test_prompt: str,
        timeout: int
    ) -> ModelTestResult:
        """测试单个模型的连通性"""
        start_time = time.time()
        
        try:
            # 获取 API 配置（从模型关联的 api_config 获取）
            api_key = ""
            api_url = None
            api_type = ApiType.GENERIC
            extra_headers = None
            extra_body = None
            
            if model.api_config_id:
                config = await crud.get_api_config_by_id(session, model.api_config_id)
                if config:
                    api_key_value = config.api_key
                    # 检查 API 密钥是否有效（不是脱敏值）
                    if api_key_value and api_key_value.strip() != "***" and len(api_key_value.strip()) > 3:
                        api_key = api_key_value.strip()
                        api_url = config.api_url
                        api_type = config.api_type or ApiType.GENERIC
                        extra_headers = config.extra_headers
                        extra_body = config.extra_params
                    else:
                        logger.warning(f"模型 {model.model_id} 关联的 API 配置密钥无效（可能是脱敏值）")
            
            if not api_key:
                return ModelTestResult(
                    id=model.id,
                    model_id=model.model_id,
                    name=model.name,
                    status="unavailable",
                    error="未配置 API Key，请先关联 API 配置"
                )
            
            # 使用新的 LLMFactory.create_llm_direct 方法
            llm = LLMFactory.create_llm_direct(
                model_name=model.model_id,
                api_key=api_key,
                api_type=api_type,
                api_url=api_url,
                temperature=0.1,
                max_tokens=50,
                use_max_completion_tokens=bool(model.use_max_completion_tokens),
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
            
            if not llm:
                # 更新模型状态
                await crud.update_model_test_status(
                    session, model.id, "unavailable", 
                    error="创建 LLM 实例失败"
                )
                return ModelTestResult(
                    id=model.id,
                    model_id=model.model_id,
                    name=model.name,
                    status="unavailable",
                    error="创建 LLM 实例失败"
                )

            # 调用模型
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: llm.invoke(test_prompt)),
                timeout=timeout
            )

            latency_ms = int((time.time() - start_time) * 1000)
            
            # 检查响应是否为错误消息（retry_with_backoff 装饰器会返回错误字符串而不是抛出异常）
            error_prefixes = [
                "AI服务认证失败",
                "AI服务请求参数错误",
                "AI服务请求失败",
                "AI服务网络请求异常",
                "AI服务请求超时",
                "调用AI服务时发生错误",
                "API 响应解析失败",
            ]
            
            is_error_response = False
            error_msg = None
            if response and isinstance(response, str):
                for prefix in error_prefixes:
                    if response.startswith(prefix) or prefix in response:
                        is_error_response = True
                        error_msg = response
                        break
            
            if is_error_response:
                # 更新模型状态为不可用
                await crud.update_model_test_status(
                    session, model.id, "unavailable",
                    latency_ms=latency_ms, error=error_msg
                )
                
                return ModelTestResult(
                    id=model.id,
                    model_id=model.model_id,
                    name=model.name,
                    status="unavailable",
                    latency_ms=latency_ms,
                    error=error_msg
                )
            
            # 更新模型状态为可用
            await crud.update_model_test_status(
                session, model.id, "available", latency_ms=latency_ms
            )
            
            return ModelTestResult(
                id=model.id,
                model_id=model.model_id,
                name=model.name,
                status="available",
                latency_ms=latency_ms
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = f"请求超时（{timeout}秒）"
            
            # 更新模型状态
            await crud.update_model_test_status(
                session, model.id, "unavailable", 
                latency_ms=latency_ms, error=error_msg
            )
            
            return ModelTestResult(
                id=model.id,
                model_id=model.model_id,
                name=model.name,
                status="unavailable",
                latency_ms=latency_ms,
                error=error_msg
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            
            # 更新模型状态
            await crud.update_model_test_status(
                session, model.id, "unavailable",
                latency_ms=latency_ms, error=error_msg
            )
            
            return ModelTestResult(
                id=model.id,
                model_id=model.model_id,
                name=model.name,
                status="unavailable",
                latency_ms=latency_ms,
                error=error_msg
            )

    # ============================================================================
    # 2.0 新增：对比历史记录
    # ============================================================================

    async def get_compare_histories(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[CompareHistoryItem], int]:
        """获取对比历史记录列表"""
        histories, total = await crud.get_compare_histories(
            session, user_id=user_id, start_time=start_time, 
            end_time=end_time, page=page, page_size=page_size
        )
        
        items = []
        for h in histories:
            # 截断用户提示词
            user_prompt = h.user_prompt
            if len(user_prompt) > 100:
                user_prompt = user_prompt[:100] + "..."
            
            items.append(CompareHistoryItem(
                id=h.id,
                task_id=h.task_id,
                user_prompt=user_prompt,
                system_prompt=h.system_prompt[:50] + "..." if h.system_prompt and len(h.system_prompt) > 50 else h.system_prompt,
                model_ids=h.model_ids,
                total_models=h.total_models,
                success_count=h.success_count,
                failed_count=h.failed_count,
                avg_latency_ms=h.avg_latency_ms,
                total_tokens=h.total_tokens,
                total_cost_cny=float(h.total_cost_cny or 0),
                created_at=h.created_at,
            ))
        
        return items, total

    async def get_compare_history_detail(
        self,
        session: AsyncSession,
        history_id: int
    ) -> Optional[CompareHistoryDetailResponse]:
        """获取对比历史记录详情"""
        history = await crud.get_compare_history_by_id(session, history_id)
        if not history:
            return None
        
        # 获取结果
        results = await crud.get_compare_results(session, history.id)
        
        model_results = []
        for r in results:
            model_results.append(ModelResult(
                model_id=r.model_id,
                model_name=r.model_name,
                provider=r.provider,
                status=r.status,
                response=r.response,
                token_usage=TokenUsage(
                    prompt_tokens=r.prompt_tokens,
                    completion_tokens=r.completion_tokens,
                    total_tokens=r.total_tokens,
                ) if r.total_tokens > 0 else None,
                latency_ms=r.latency_ms,
                cost_usd=float(r.cost_usd or 0),
                cost_cny=float(r.cost_cny or 0),
                error=r.error,
            ))
        
        return CompareHistoryDetailResponse(
            id=history.id,
            task_id=history.task_id,
            system_prompt=history.system_prompt,
            user_prompt=history.user_prompt,
            temperature=float(history.temperature) if history.temperature else None,
            max_tokens=history.max_tokens,
            model_ids=history.model_ids,
            api_config_id=history.api_config_id,
            total_models=history.total_models,
            success_count=history.success_count,
            failed_count=history.failed_count,
            avg_latency_ms=history.avg_latency_ms,
            total_tokens=history.total_tokens,
            total_cost_usd=float(history.total_cost_usd or 0),
            total_cost_cny=float(history.total_cost_cny or 0),
            created_at=history.created_at,
            completed_at=history.completed_at,
            results=model_results,
        )

    async def delete_compare_history(
        self,
        session: AsyncSession,
        history_id: int
    ) -> bool:
        """删除对比历史记录"""
        result = await crud.delete_compare_history(session, history_id)
        if result:
            await session.commit()
        return result

    # ============================================================================
    # 2.0 新增：统计功能
    # ============================================================================

    async def get_compare_stats(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """获取对比统计数据"""
        return await crud.get_compare_stats(
            session, user_id=user_id, start_time=start_time, end_time=end_time
        )

    async def get_model_usage_stats(
        self,
        session: AsyncSession,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取模型使用统计"""
        return await crud.get_model_usage_stats(
            session, user_id=user_id, start_time=start_time, 
            end_time=end_time, limit=limit
        )

    # ============================================================================
    # 2.0 新增：标签管理
    # ============================================================================

    async def get_tags(
        self,
        session: AsyncSession,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """获取标签列表"""
        tags = await mgmt_crud.get_tags(session, is_active=is_active)
        return [tag.to_dict() for tag in tags]

    async def get_tag(
        self,
        session: AsyncSession,
        tag_id: int
    ) -> Optional[Dict[str, Any]]:
        """获取单个标签"""
        tag = await mgmt_crud.get_tag_by_id(session, tag_id)
        if tag:
            return tag.to_dict()
        return None

    async def create_tag(
        self,
        session: AsyncSession,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建标签"""
        tag = await mgmt_crud.create_tag(session, data)
        await session.commit()
        return tag.to_dict()

    async def update_tag(
        self,
        session: AsyncSession,
        tag_id: int,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新标签"""
        tag = await mgmt_crud.update_tag(session, tag_id, data)
        if tag:
            await session.commit()
            return tag.to_dict()
        return None

    async def delete_tag(
        self,
        session: AsyncSession,
        tag_id: int
    ) -> bool:
        """删除标签"""
        result = await mgmt_crud.delete_tag(session, tag_id)
        if result:
            await session.commit()
        return result


# 全局服务实例
_model_compare_service: Optional[ModelCompareService] = None


def get_model_compare_service() -> ModelCompareService:
    """获取模型对比服务实例"""
    global _model_compare_service
    if _model_compare_service is None:
        _model_compare_service = ModelCompareService()
    return _model_compare_service
