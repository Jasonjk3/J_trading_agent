#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/02/07
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
通用 OpenAI 兼容 LLM 客户端
支持所有兼容 OpenAI API 格式的第三方服务商
"""

import logging
import requests
from typing import Any, Dict, List, Mapping, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from loguru import logger as runtime_logger

from core.llm.base.base_llm import (
    BaseLLM,
    chat_completion_diagnostics,
    retry_with_backoff,
)
from core.llm.openai_compatible_url import normalize_chat_completions_url

logger = logging.getLogger(__name__)


class GenericOpenAICompatibleLLM(BaseLLM):
    """
    通用 OpenAI 兼容 LLM 客户端
    
    支持所有兼容 OpenAI Chat Completions API 格式的服务商，包括：
    - OpenAI 官方 API
    - 各种中转 API 服务商
    - 私有部署的兼容服务
    - DeepSeek、Moonshot 等国产模型（它们都兼容 OpenAI 格式）
    
    特点：
    - 不依赖模型名称推断，完全配置驱动
    - 支持直接传递 API Key（不依赖环境变量）
    - 灵活的参数处理
    - 完整的错误日志
    """
    
    api_key: str
    """API 密钥"""
    
    model_name: str
    """模型名称"""
    
    api_url: str = "https://api.openai.com/v1/chat/completions"
    """API URL，支持自定义第三方服务地址"""
    
    temperature: float = 0.7
    """生成时的温度参数，控制随机性"""
    
    max_tokens: Optional[int] = None
    """生成的最大 token 数"""
    
    max_completion_tokens: Optional[int] = None
    """最大完成 token 数（某些模型使用此参数替代 max_tokens）"""
    
    use_max_completion_tokens: bool = False
    """是否使用 max_completion_tokens 替代 max_tokens（用于 o1/o3 等模型）"""
    
    extra_headers: Optional[Dict[str, str]] = None
    """额外的请求头（某些服务商可能需要）"""
    
    extra_body: Optional[Dict[str, Any]] = None
    """额外的请求体参数（某些服务商可能需要特殊参数）"""
    
    class Config:
        """模型配置项"""
        arbitrary_types_allowed = True
    
    @property
    def _llm_type(self) -> str:
        """返回 LLM 类型"""
        return "generic_openai_compatible"
    
    def _normalize_api_url(self, url: str) -> str:
        """见 core.llm.openai_compatible_url.normalize_chat_completions_url"""
        return normalize_chat_completions_url(url)
    
    @retry_with_backoff()
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """
        调用 API 生成文本
        
        Args:
            prompt: 提示文本
            stop: 停止标记
            run_manager: 运行管理器
            
        Returns:
            str: 生成的文本
        """
        import time
        start_time = time.time()
        
        # 规范化 API URL（自动补全路径）
        normalized_api_url = self._normalize_api_url(self.api_url)
        
        # 准备请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 添加额外的请求头
        if self.extra_headers:
            headers.update(self.extra_headers)
        
        # 准备请求数据
        # 检查是否有图片（通过kwargs传递）
        images = kwargs.get("images")
        
        # 构建消息内容
        if images and isinstance(images, list) and len(images) > 0:
            # 多模态：content是数组，包含文本和图片
            content = []
            if prompt:
                content.append({"type": "text", "text": prompt})
            for img in images:
                # 支持base64格式的图片
                if isinstance(img, str):
                    if img.startswith("data:image"):
                        # 已经是完整的data URL
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": img}
                        })
                    elif img.startswith("http://") or img.startswith("https://"):
                        # URL格式
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": img}
                        })
                    else:
                        # 假设是base64，添加data URL前缀
                        # 尝试检测图片格式
                        img_format = "jpeg"  # 默认
                        if img.startswith("/9j/"):  # JPEG
                            img_format = "jpeg"
                        elif img.startswith("iVBORw0KGgo"):  # PNG
                            img_format = "png"
                        elif img.startswith("UklGR"):  # WebP
                            img_format = "webp"
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{img_format};base64,{img}"}
                        })
        else:
            # 纯文本：content是字符串
            content = prompt
        
        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content}],
            "temperature": self.temperature
        }
        
        # 处理 max_tokens 参数
        if self.use_max_completion_tokens:
            # 某些模型（如 o1/o3 系列）使用 max_completion_tokens
            if self.max_completion_tokens is not None:
                data["max_completion_tokens"] = self.max_completion_tokens
            elif self.max_tokens is not None:
                data["max_completion_tokens"] = self.max_tokens
        else:
            # 标准模型使用 max_tokens
            if self.max_tokens is not None:
                data["max_tokens"] = self.max_tokens
        
        # 添加停止标记
        if stop:
            data["stop"] = stop
        
        # 添加额外的请求体参数
        if self.extra_body:
            data.update(self.extra_body)
        
        # 获取代理配置
        proxies = self._get_proxies()
        
        if proxies:
            logger.debug(f"使用代理进行 API 调用: {proxies}")
        
        logger.info(
            f"GenericOpenAICompatibleLLM 请求追踪: model={self.model_name}, "
            f"api_url={self.api_url}, normalized_url={normalized_api_url}"
        )
        
        try:
            # 发送 HTTP 请求
            response = requests.post(
                normalized_api_url,
                headers=headers,
                json=data,
                timeout=self.timeout,
                proxies=proxies
            )
            
            # 计算响应时间
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # 处理错误响应
            if response.status_code != 200:
                self._log_error_response(response)
            
            response.raise_for_status()
            
            # 检查响应内容类型
            content_type = response.headers.get("Content-Type", "").lower()
            response_text = response.text
            
            # 如果返回的是HTML，说明API URL可能配置错误（指向了前端页面而不是API端点）
            if "text/html" in content_type or response_text.strip().startswith("<!DOCTYPE") or response_text.strip().startswith("<html"):
                error_msg = (
                    f"API返回了HTML内容而不是JSON，这通常表示API URL配置错误。\n"
                    f"请检查API URL是否正确指向API端点（例如：https://api.example.com/v1/chat/completions），\n"
                    f"而不是前端页面（例如：https://example.com）。\n"
                    f"原始API URL: {self.api_url}\n"
                    f"规范化后URL: {normalized_api_url}\n"
                    f"响应内容预览: {response_text[:200]}"
                )
                logger.error(error_msg)
                self._track_usage(
                    prompt=prompt,
                    completion="",
                    response_time_ms=response_time_ms,
                    status="failed",
                    error_message="API返回HTML而非JSON，URL配置可能错误"
                )
                raise ValueError(error_msg)
            
            # 解析响应
            response_data = response.json()
            runtime_logger.info(
                "GenericOpenAICompatibleLLM 响应诊断: {}",
                chat_completion_diagnostics(response_data, data),
            )
            
            if "choices" in response_data and len(response_data["choices"]) > 0:
                choice = response_data["choices"][0]
                
                # 兼容不同格式的响应
                if "message" in choice:
                    content = choice["message"].get("content", "")
                elif "text" in choice:
                    # 某些旧版 API 可能使用 text 字段
                    content = choice["text"]
                else:
                    content = ""
                
                # 提取 usage 信息并记录追踪
                usage = response_data.get("usage", {})
                self._track_usage(
                    prompt=prompt,
                    completion=content,
                    response_time_ms=response_time_ms,
                    status="success",
                    usage=usage
                )
                
                return content
            else:
                logger.error(f"API 返回异常响应: {response_data}")
                raise ValueError("API 返回异常响应，无法生成内容。")
                
        except requests.exceptions.JSONDecodeError as e:
            # JSON 解析错误，通常是响应为空或非 JSON 格式
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # 获取响应内容用于诊断
            response_text = ""
            content_type = ""
            if 'response' in locals():
                response_text = response.text
                content_type = response.headers.get("Content-Type", "").lower()
            
            # 检查是否是HTML响应
            is_html = (
                "text/html" in content_type or
                response_text.strip().startswith("<!DOCTYPE") or
                response_text.strip().startswith("<html")
            )

            if is_html:
                normalized_url = self._normalize_api_url(self.api_url)
                error_msg = (
                    f"API返回了HTML内容而不是JSON，这通常表示API URL配置错误。\n"
                    f"请检查API URL是否正确指向API端点（例如：https://api.example.com/v1/chat/completions），\n"
                    f"而不是前端页面（例如：https://example.com）。\n"
                    f"原始API URL: {self.api_url}\n"
                    f"规范化后URL: {normalized_url}\n"
                    f"响应状态码: {response.status_code if 'response' in locals() else 'N/A'}\n"
                    f"响应内容预览: {response_text[:300]}"
                )
                logger.error(error_msg)
                logger.error(f"完整响应内容: {response_text[:1000]}")
            else:
                error_msg = (
                    f"API 响应解析失败（非 JSON 格式）: {str(e)}\n"
                    f"响应状态码: {response.status_code if 'response' in locals() else 'N/A'}\n"
                    f"响应内容类型: {content_type or '未知'}\n"
                    f"响应内容预览: {response_text[:300] if response_text else '空响应'}\n"
                    f"请检查 API URL 和 Key 是否正确"
                )
                logger.error(error_msg)
                logger.error(f"完整响应内容: {response_text[:1000] if response_text else 'N/A'}")
            
            self._track_usage(
                prompt=prompt,
                completion="",
                response_time_ms=response_time_ms,
                status="failed",
                error_message="JSON解析失败" if not is_html else "API返回HTML而非JSON，URL配置可能错误"
            )
            
            raise ValueError(error_msg)
            
        except Exception as e:
            # 计算响应时间
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # 记录失败的调用
            status = "timeout" if "timeout" in str(e).lower() else "failed"
            self._track_usage(
                prompt=prompt,
                completion="",
                response_time_ms=response_time_ms,
                status=status,
                error_message=str(e)
            )
            
            raise
    
    def _log_error_response(self, response: requests.Response) -> None:
        """
        记录错误响应的详细信息
        
        Args:
            response: HTTP 响应对象
        """
        try:
            error_data = response.json()
            if "error" in error_data:
                error_info = error_data["error"]
                error_message = error_info.get("message", "")
                error_type = error_info.get("type", "")
                error_param = error_info.get("param", "")
                error_code = error_info.get("code", "")
                
                error_detail = f"错误类型: {error_type}, 错误消息: {error_message}"
                if error_param:
                    error_detail += f", 参数: {error_param}"
                if error_code:
                    error_detail += f", 错误代码: {error_code}"
                
                logger.error(f"API 返回 HTTP {response.status_code} 错误: {error_detail}")
                logger.error(f"完整错误响应: {error_data}")
            else:
                logger.error(f"API 返回 HTTP {response.status_code} 错误: {error_data}")
        except Exception as e:
            logger.error(f"解析错误响应失败: {str(e)}")
            logger.error(f"原始响应: {response.text[:500]}")
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """获取识别参数"""
        return {
            "model_name": self.model_name,
            "api_url": self.api_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "max_completion_tokens": self.max_completion_tokens,
            "use_max_completion_tokens": self.use_max_completion_tokens,
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "timeout": self.timeout,
            "proxies": self.proxies
        }
