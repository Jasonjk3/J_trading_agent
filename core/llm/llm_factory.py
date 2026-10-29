#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/XX XX:XX
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
LLM工厂类
统一管理LLM实例的创建，支持多种LLM类型和配置

支持两种创建方式：
1. 环境变量方式（Agent 用）：通过 api_key_env 指定环境变量名
2. 直接传递方式（网关用）：通过 api_key 直接传递密钥
"""
import os
from typing import Any, Dict, Optional
from loguru import logger

from core.llm.base.base_llm import BaseLLM


# API 类型常量
class ApiType:
    """API 协议类型"""
    OPENAI = "openai"           # OpenAI 官方 API
    DEEPSEEK = "deepseek"       # DeepSeek API
    GENERIC = "generic"         # 通用 OpenAI 兼容 API（第三方服务商）


class LLMFactory:
    """
    LLM工厂类
    
    统一管理LLM实例的创建，提供：
    1. 统一的创建接口
    2. 支持多种LLM类型
    3. 可选的实例缓存
    4. 支持环境变量和直接传递 API Key 两种方式
    
    使用示例：
    
    # 方式1：环境变量方式（Agent 用）
    llm = LLMFactory.create_llm(
        model_name="gpt-4o",
        api_key_env="OPENAI_API_KEY"
    )
    
    # 方式2：直接传递方式（网关用）
    llm = LLMFactory.create_llm_direct(
        model_name="gpt-4o",
        api_key="sk-xxx",
        api_url="https://api.third-party.com/v1/chat/completions",
        api_type=ApiType.GENERIC
    )
    """
    
    # 实例缓存（可选，如果需要单例模式可以启用）
    _instances: Dict[str, BaseLLM] = {}
    _use_cache: bool = False  # 默认不启用缓存，每个Agent创建独立实例
    
    # 模型名称到 LLM 类型的映射规则（用于自动推断）
    MODEL_TYPE_MAPPING = {
        "deepseek": ApiType.DEEPSEEK,
        "gpt": ApiType.OPENAI,
        "o1": ApiType.OPENAI,
        "o3": ApiType.OPENAI,
    }
    
    @classmethod
    def _infer_api_type(cls, model_name: str) -> str:
        """
        从模型名称推断 API 类型
        
        Args:
            model_name: 模型名称
            
        Returns:
            API 类型
        """
        if not model_name:
            return ApiType.GENERIC
        
        model_name_lower = model_name.lower()
        
        for prefix, api_type in cls.MODEL_TYPE_MAPPING.items():
            if model_name_lower.startswith(prefix):
                return api_type
        
        # 无法推断时使用通用类型
        return ApiType.GENERIC
    
    @classmethod
    def create_llm(
        cls,
        model_name: str = "deepseek-chat",
        api_key_env: str = "DEEPSEEK_API_KEY",
        use_cache: Optional[bool] = None,
        **kwargs
    ) -> Optional[BaseLLM]:
        """
        创建LLM实例（环境变量方式，适用于 Agent）
        
        Args:
            model_name: 模型名称（如 deepseek-chat, gpt-4, gpt-3.5-turbo 等）
            api_key_env: API Key环境变量名
            use_cache: 是否使用缓存，如果为None则使用类默认值
            **kwargs: 其他LLM参数
                - temperature: 温度参数
                - max_tokens: 最大token数
                - api_url: API地址
                - proxies: 代理配置
            
        Returns:
            LLM实例，如果创建失败则返回None
        """
        # 从环境变量读取 API Key
        api_key = os.getenv(api_key_env, "")
        if not api_key:
            logger.warning(f"未配置{api_key_env}环境变量，LLM可能无法正常工作")
        
        # 推断 API 类型
        api_type = cls._infer_api_type(model_name)
        
        return cls.create_llm_direct(
            model_name=model_name,
            api_key=api_key,
            api_type=api_type,
            use_cache=use_cache,
            **kwargs
        )
    
    @classmethod
    def create_llm_direct(
        cls,
        model_name: str,
        api_key: str,
        api_type: str = ApiType.GENERIC,
        api_url: Optional[str] = None,
        use_cache: Optional[bool] = None,
        **kwargs
    ) -> Optional[BaseLLM]:
        """
        创建LLM实例（直接传递方式，适用于网关/第三方服务商）
        
        Args:
            model_name: 模型名称
            api_key: API 密钥（直接传递）
            api_type: API 类型（openai/deepseek/generic）
            api_url: API URL（可选，第三方服务商需要提供）
            use_cache: 是否使用缓存
            **kwargs: 其他LLM参数
                - temperature: 温度参数
                - max_tokens: 最大token数
                - use_max_completion_tokens: 是否使用 max_completion_tokens
                - extra_headers: 额外请求头
                - extra_body: 额外请求体参数
                - proxies: 代理配置
            
        Returns:
            LLM实例，如果创建失败则返回None
        """
        try:
            if not api_key or not api_key.strip():
                error_msg = f"API Key 为空，无法创建 LLM 实例（model: {model_name}）"
                logger.error(error_msg)
                return None
            
            # 构建 LLM 参数
            llm_params = {
                "api_key": api_key.strip(),
                "model_name": model_name,
            }
            
            # 设置 API URL
            if api_url:
                llm_params["api_url"] = api_url
            
            # 添加 temperature
            temperature = kwargs.get("temperature")
            if temperature is not None:
                llm_params["temperature"] = temperature
            
            # 处理 max_tokens
            max_tokens = kwargs.get("max_tokens")
            use_max_completion_tokens = kwargs.get("use_max_completion_tokens", False)
            
            # 自动检测是否需要使用 max_completion_tokens（o 系列模型）
            model_name_lower = model_name.lower()
            if model_name_lower.startswith(("o1", "o3")):
                use_max_completion_tokens = True
            
            if api_type == ApiType.GENERIC:
                # 通用客户端支持灵活配置
                llm_params["use_max_completion_tokens"] = use_max_completion_tokens
                if max_tokens is not None:
                    llm_params["max_tokens"] = max_tokens
            elif use_max_completion_tokens and max_tokens is not None:
                llm_params["max_completion_tokens"] = max_tokens
            elif max_tokens is not None:
                llm_params["max_tokens"] = max_tokens
            
            # 添加其他参数
            for key in ["max_completion_tokens", "organization", "proxies", 
                       "extra_headers", "extra_body", "timeout"]:
                value = kwargs.get(key)
                if value is not None:
                    llm_params[key] = value
            
            # 检查缓存
            cache_key = None
            if use_cache if use_cache is not None else cls._use_cache:
                cache_key = f"{api_type}_{hash(str(sorted(llm_params.items())))}"
                if cache_key in cls._instances:
                    logger.debug(f"使用缓存的LLM实例: {cache_key}")
                    return cls._instances[cache_key]
            
            # 创建 LLM 实例
            logger.info(
                "LLMFactory.create_llm_direct 追踪: "
                f"model={model_name}, api_type={api_type}, api_url={api_url or 'default'}, "
                f"extra_keys={sorted([k for k in kwargs.keys() if kwargs.get(k) is not None])}"
            )
            llm = cls._create_llm_by_type(api_type, **llm_params)
            
            if not llm:
                logger.error(f"创建LLM实例失败: model={model_name}, type={api_type}")
                return None
            
            # 缓存实例
            if cache_key:
                cls._instances[cache_key] = llm
                logger.debug(f"缓存LLM实例: {cache_key}")
            
            logger.info(
                f"成功创建LLM实例: model={model_name}, type={api_type}, "
                f"url={api_url or 'default'}"
            )
            
            return llm
            
        except Exception as e:
            logger.error(f"创建LLM实例时发生错误: {e}", exc_info=True)
            return None
    
    @classmethod
    def _create_llm_by_type(cls, api_type: str, **kwargs) -> Optional[BaseLLM]:
        """
        根据 API 类型创建 LLM 实例
        
        Args:
            api_type: API 类型
            **kwargs: LLM 参数
            
        Returns:
            LLM 实例
        """
        try:
            if api_type == ApiType.DEEPSEEK:
                from core.llm.deepseek_llm import DeepSeekLLM
                # 过滤掉 DeepSeekLLM 不支持的参数
                supported_keys = ["api_key", "model_name", "temperature", "max_tokens", 
                                 "api_url", "proxies", "timeout", "max_retries", 
                                 "base_delay", "max_delay", "enable_tracking"]
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in supported_keys}
                logger.info(
                    "LLMFactory 路由追踪: DeepSeekLLM "
                    f"model={filtered_kwargs.get('model_name')}, "
                    f"api_url={filtered_kwargs.get('api_url', 'default')}"
                )
                return DeepSeekLLM(**filtered_kwargs)
            
            elif api_type == ApiType.OPENAI:
                from core.llm.openai_llm import OpenAIGPTLLM
                # 过滤掉 OpenAIGPTLLM 不支持的参数
                supported_keys = ["api_key", "model_name", "temperature", "max_tokens",
                                 "max_completion_tokens", "api_url", "organization",
                                 "proxies", "timeout", "max_retries", "base_delay", 
                                 "max_delay", "enable_tracking"]
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in supported_keys}
                logger.info(
                    "LLMFactory 路由追踪: OpenAIGPTLLM "
                    f"model={filtered_kwargs.get('model_name')}, "
                    f"api_url={filtered_kwargs.get('api_url', 'default')}"
                )
                return OpenAIGPTLLM(**filtered_kwargs)
            
            elif api_type == ApiType.GENERIC:
                logger.info(
                    "LLMFactory 路由追踪: GenericOpenAICompatibleLLM "
                    f"model={kwargs.get('model_name')}, api_url={kwargs.get('api_url', 'default')}"
                )
                from core.llm.generic_llm import GenericOpenAICompatibleLLM
                return GenericOpenAICompatibleLLM(**kwargs)
            
            else:
                logger.error(f"不支持的 API 类型: {api_type}")
                return None
                
        except Exception as e:
            logger.error(f"创建 {api_type} LLM 实例失败: {e}", exc_info=True)
            return None
    
    @classmethod
    def clear_cache(cls):
        """清除实例缓存"""
        cls._instances.clear()
        logger.info("已清除LLM实例缓存")
    
    @classmethod
    def enable_cache(cls, enable: bool = True):
        """
        启用或禁用实例缓存
        
        Args:
            enable: 是否启用缓存
        """
        cls._use_cache = enable
        if not enable:
            cls.clear_cache()
        logger.info(f"LLM实例缓存已{'启用' if enable else '禁用'}")

