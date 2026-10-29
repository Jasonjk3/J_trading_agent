"""
自定义的OpenAI GPT LLM类，用于与LangChain集成
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


class OpenAIGPTLLM(BaseLLM):
    """OpenAI GPT API集成的LLM封装类"""
    
    api_key: str
    """OpenAI API密钥"""
    
    model_name: str = "gpt-4o"
    """模型名称，默认为gpt-4o，支持gpt-4o、gpt-4o-mini、gpt-4-turbo、gpt-3.5-turbo等"""
    
    api_url: str = "https://api.openai.com/v1/chat/completions"
    """OpenAI API URL，可自定义为代理地址"""
    
    temperature: float = 0.7
    """生成时的温度参数，控制随机性"""
    
    max_tokens: Optional[int] = None
    """生成的最大token数（某些模型不支持，会自动使用max_completion_tokens）"""
    
    max_completion_tokens: Optional[int] = None
    """最大完成token数（某些新模型使用此参数替代max_tokens，如o1系列）"""
    
    organization: Optional[str] = None
    """OpenAI组织ID（可选）"""
    
    class Config:
        """模型配置项"""
        arbitrary_types_allowed = True
    
    @property
    def _llm_type(self) -> str:
        """返回LLM类型"""
        return "openai_gpt"
    
    @retry_with_backoff()
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """
        调用OpenAI GPT API生成文本，使用装饰器的重试机制
        
        Args:
            prompt: 提示文本
            stop: 停止标记
            run_manager: 运行管理器
            
        Returns:
            str: 生成的文本
        """
        import time
        start_time = time.time()
        
        # 准备请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 如果设置了组织ID，添加到请求头
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        
        # 准备请求数据
        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature
        }
        
        # 根据模型类型选择使用max_tokens或max_completion_tokens
        # 某些新模型（如o1系列）使用max_completion_tokens而不是max_tokens
        if self.max_completion_tokens is not None:
            data["max_completion_tokens"] = self.max_completion_tokens
        elif self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        
        if stop:
            data["stop"] = stop
        
        # 获取代理配置
        proxies = self._get_proxies()
        
        # 记录代理使用情况
        if proxies:
            logger.debug(f"使用代理进行API调用: {proxies}")

        post_url = normalize_chat_completions_url(self.api_url)
        logger.info(
            f"OpenAIGPTLLM 请求追踪: model={self.model_name}, "
            f"api_url={self.api_url}, post_url={post_url}"
        )

        try:
            # 发送HTTP请求（与 generic 一致：仅填到 /v1 时自动补全 chat/completions，兼容 Qwen 中转等）
            response = requests.post(
                post_url,
                headers=headers,
                json=data,
                timeout=self.timeout,
                proxies=proxies
            )
            
            # 计算响应时间
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # 检查响应状态码，如果是错误状态码，记录详细错误信息
            if response.status_code != 200:
                error_detail = ""
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
                        
                        logger.error(f"OpenAI GPT API返回HTTP {response.status_code}错误: {error_detail}")
                        logger.error(f"完整错误响应: {error_data}")
                except Exception as e:
                    logger.error(f"解析错误响应失败: {str(e)}")

            response.raise_for_status()
            
            # 检查响应内容类型
            content_type = response.headers.get("Content-Type", "").lower()
            response_text = response.text
            
            # 如果返回的是HTML，说明API URL可能配置错误（指向了前端页面而不是API端点）
            if "text/html" in content_type or response_text.strip().startswith("<!DOCTYPE") or response_text.strip().startswith("<html"):
                error_msg = (
                    f"API返回了HTML内容而不是JSON，这通常表示API URL配置错误。\n"
                    f"请检查API URL是否正确指向API端点（例如：https://api.openai.com/v1/chat/completions），\n"
                    f"而不是前端页面（例如：https://example.com）。\n"
                    f"当前API URL: {self.api_url}（实际请求: {post_url}）\n"
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
            try:
                response_data = response.json()
            except requests.exceptions.JSONDecodeError as e:
                # JSON 解析错误处理
                is_html = (
                    "text/html" in content_type or 
                    response_text.strip().startswith("<!DOCTYPE") or 
                    response_text.strip().startswith("<html")
                )
                
                if is_html:
                    error_msg = (
                        f"API返回了HTML内容而不是JSON，这通常表示API URL配置错误。\n"
                        f"请检查API URL是否正确指向API端点（例如：https://api.openai.com/v1/chat/completions），\n"
                        f"而不是前端页面（例如：https://example.com）。\n"
                        f"当前API URL: {self.api_url}（实际请求: {post_url}）\n"
                        f"响应状态码: {response.status_code}\n"
                        f"响应内容预览: {response_text[:300]}"
                    )
                else:
                    error_msg = (
                        f"API 响应解析失败（非 JSON 格式）: {str(e)}\n"
                        f"响应状态码: {response.status_code}\n"
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
            runtime_logger.info(
                "OpenAIGPTLLM 响应诊断: {}",
                chat_completion_diagnostics(response_data, data),
            )
            if "choices" in response_data and len(response_data["choices"]) > 0:
                content = response_data["choices"][0]["message"]["content"]
                
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
                logger.error(f"OpenAI GPT API返回异常响应: {response_data}")
                raise ValueError("OpenAI GPT API返回异常响应，无法生成内容。")
                
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
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """获取识别参数"""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "max_completion_tokens": self.max_completion_tokens,
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "timeout": self.timeout,
            "organization": self.organization,
            "proxies": self.proxies
        }

