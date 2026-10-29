#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:25
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
LLM基类
提供通用的重试机制、错误处理等功能
支持 LLM 调用追踪和监控
"""
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

import requests
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM

logger = logging.getLogger(__name__)

# 追踪器延迟导入标记
_tracker_imported = False
_usage_tracker = None


def _safe_payload_length(value: Any) -> int:
    """返回响应字段的内容长度，不把字段正文写入日志。"""
    if value is None:
        return 0
    if isinstance(value, (str, bytes, bytearray)):
        return len(value)
    if isinstance(value, list):
        return sum(_safe_payload_length(item) for item in value)
    if isinstance(value, dict):
        # 兼容 OpenAI 多段 content：优先统计 text/content 字段，避免把键名计入长度。
        for key in ("text", "content", "value"):
            if key in value:
                return _safe_payload_length(value.get(key))
        return sum(_safe_payload_length(item) for item in value.values())
    return len(str(value))


def _safe_usage_summary(value: Any) -> Any:
    """仅保留 usage 中的标量计数和嵌套计数，不记录任意文本载荷。"""
    if isinstance(value, dict):
        return {
            str(key): _safe_usage_summary(item)
            for key, item in value.items()
            if isinstance(item, (dict, int, float, bool)) or item is None
        }
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"


def chat_completion_diagnostics(
    response_data: Any,
    request_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """生成不含 Prompt、响应正文或凭据的 Chat Completions 诊断信息。"""
    request_data = request_data or {}
    choice: Dict[str, Any] = {}
    message: Dict[str, Any] = {}
    if isinstance(response_data, dict):
        choices = response_data.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            choice = choices[0]
            if isinstance(choice.get("message"), dict):
                message = choice["message"]

    content = message.get("content")
    reasoning_content = message.get("reasoning_content")
    return {
        "finish_reason": choice.get("finish_reason"),
        "message_fields": sorted(str(key) for key in message.keys()),
        "content_type": type(content).__name__,
        "content_length": _safe_payload_length(content),
        "content_items": len(content) if isinstance(content, list) else None,
        "reasoning_content_type": type(reasoning_content).__name__,
        "reasoning_content_length": _safe_payload_length(reasoning_content),
        "usage": _safe_usage_summary(
            response_data.get("usage") if isinstance(response_data, dict) else None
        ),
        "request_max_tokens": request_data.get("max_tokens"),
        "request_max_completion_tokens": request_data.get("max_completion_tokens"),
    }


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    is_retryable_error_func=None
):
    """
    重试装饰器，支持指数退避
    
    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        is_retryable_error_func: 判断错误是否可重试的函数，接收(error, status_code)参数
    
    Usage:
        @retry_with_backoff(max_retries=3)
        def my_api_call(self):
            ...
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # 如果实例有这些属性，优先使用实例属性
            retries = getattr(self, 'max_retries', max_retries)
            delay_base = getattr(self, 'base_delay', base_delay)
            delay_max = getattr(self, 'max_delay', max_delay)
            
            # 使用实例的错误判断函数，如果没有则使用默认的
            is_retryable = is_retryable_error_func
            if not is_retryable and hasattr(self, '_is_retryable_error'):
                is_retryable = self._is_retryable_error
            
            last_error = None
            last_status_code = None
            
            # 重试循环
            for attempt in range(retries + 1):
                try:
                    result = func(self, *args, **kwargs)
                    if attempt > 0:
                        logger.info(f"{func.__name__} 成功（第{attempt + 1}次尝试）")
                    return result
                
                except requests.exceptions.HTTPError as e:
                    last_error = e
                    last_status_code = e.response.status_code if e.response else None
                    
                    # 401和400错误应该立即返回，不重试
                    if last_status_code == 401:
                        logger.error(f"API认证失败（HTTP 401），请检查API密钥: {str(e)}")
                        # 尝试从响应中提取更详细的错误信息
                        error_detail = ""
                        try:
                            if e.response:
                                error_data = e.response.json()
                                if "error" in error_data:
                                    error_info = error_data["error"]
                                    error_message = error_info.get("message", "")
                                    if error_message:
                                        error_detail = f" 错误详情: {error_message}"
                        except:
                            pass
                        return f"AI服务认证失败，请检查API密钥配置。{error_detail}"
                    elif last_status_code == 400:
                        logger.error(f"API请求参数错误（HTTP 400）: {str(e)}")
                        return f"AI服务请求参数错误: {str(e)}"
                    
                    # 判断是否可重试
                    if is_retryable:
                        retryable = is_retryable(e, last_status_code)
                    else:
                        # 默认判断逻辑：只有5xx服务器错误和429请求过多可重试
                        # 4xx客户端错误（除了429）不可重试
                        retryable = (last_status_code is None or 
                                   (last_status_code is not None and last_status_code >= 500) or 
                                   last_status_code == 429)
                    
                    if not retryable:
                        # 不可重试的错误（4xx客户端错误，除了429）
                        logger.error(f"API HTTP错误（不可重试，HTTP {last_status_code}）: {str(e)}")
                        return f"AI服务请求失败（HTTP {last_status_code}）: {str(e)}"
                    
                    # 可重试的错误
                    if attempt < retries:
                        delay = _calculate_backoff_delay(attempt, delay_base, delay_max)
                        logger.warning(
                            f"{func.__name__} 失败（HTTP {last_status_code}），"
                            f"将在 {delay:.2f} 秒后重试（第 {attempt + 1}/{retries} 次）: {str(e)}"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"{func.__name__} 失败，已达到最大重试次数: {str(e)}")
                        return f"AI服务请求失败，已重试{retries}次: {str(e)}"
                
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    last_error = e
                    error_type = "超时" if isinstance(e, requests.exceptions.Timeout) else "连接错误"
                    
                    if attempt < retries:
                        delay = _calculate_backoff_delay(attempt, delay_base, delay_max)
                        logger.warning(
                            f"{func.__name__} {error_type}，"
                            f"将在 {delay:.2f} 秒后重试（第 {attempt + 1}/{retries} 次）: {str(e)}"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"{func.__name__} {error_type}，已达到最大重试次数: {str(e)}")
                        return f"AI服务请求{error_type}，已重试{retries}次，请稍后再试。"
                
                except requests.exceptions.RequestException as e:
                    last_error = e
                    if attempt < retries:
                        delay = _calculate_backoff_delay(attempt, delay_base, delay_max)
                        logger.warning(
                            f"{func.__name__} 请求异常，"
                            f"将在 {delay:.2f} 秒后重试（第 {attempt + 1}/{retries} 次）: {str(e)}"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"{func.__name__} 请求异常，已达到最大重试次数: {str(e)}")
                        return f"AI服务网络请求异常: {str(e)}"
                
                except Exception as e:
                    # 其他未知错误不可重试
                    logger.error(f"调用{func.__name__}时发生未知错误: {str(e)}")
                    return f"调用AI服务时发生错误: {str(e)}"
            
            # 所有重试都失败
            if last_error:
                logger.error(f"{func.__name__} 最终失败: {str(last_error)}")
                return f"AI服务请求失败: {str(last_error)}"
            
            return "AI服务请求失败，未知错误。"
        
        return wrapper
    return decorator


def _calculate_backoff_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """
    计算指数退避延迟时间（辅助函数）
    
    Args:
        attempt: 当前尝试次数（从0开始）
        base_delay: 基础延迟时间
        max_delay: 最大延迟时间
        
    Returns:
        float: 延迟时间（秒）
    """
    # 指数退避：base_delay * (2 ^ attempt)
    delay = base_delay * (2 ** attempt)
    
    # 添加随机抖动，避免同时重试
    jitter = random.uniform(0, delay * 0.1)
    delay = delay + jitter
    
    # 限制最大延迟时间
    delay = min(delay, max_delay)
    
    return delay


def _get_usage_tracker():
    """延迟获取使用量追踪器，避免循环导入"""
    global _tracker_imported, _usage_tracker
    if not _tracker_imported:
        try:
            from core.llm.base.usage_tracker import get_usage_tracker
            _usage_tracker = get_usage_tracker()
            _tracker_imported = True
        except ImportError as e:
            logger.warning(f"无法导入 usage_tracker: {e}")
            _tracker_imported = True  # 标记已尝试导入，避免重复
    return _usage_tracker


class BaseLLM(LLM, ABC):
    """LLM基类，提供通用的重试和错误处理机制，支持调用追踪"""
    
    max_retries: int = 3
    """最大重试次数，默认为3次"""
    
    base_delay: float = 1.0
    """指数退避的基础延迟时间（秒），默认为1秒"""
    
    max_delay: float = 60.0
    """最大延迟时间（秒），默认为60秒"""
    
    timeout: float = 180.0
    """请求超时时间（秒），默认为180秒（3分钟）"""
    
    proxies: Optional[Union[str, Dict[str, str]]] = None
    """代理设置，支持字典格式，如 {"http": "http://proxy.example.com:8080", "https": "https://proxy.example.com:8080"}
    也可以设置为字符串，如 "http://proxy.example.com:8080"，会自动应用到http和https
    """
    
    enable_tracking: bool = True
    """是否启用调用追踪，默认为True"""
    
    class Config:
        """模型配置项"""
        arbitrary_types_allowed = True
    
    def _track_usage(
        self,
        prompt: str,
        completion: str,
        response_time_ms: int,
        status: str = "success",
        error_message: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        usage: Optional[Dict[str, int]] = None,
        agent_name: Optional[str] = None,
        task_type: Optional[str] = None,
        **kwargs
    ):
        """
        记录 LLM 调用使用情况
        
        Args:
            prompt: 输入提示
            completion: 生成的回复
            response_time_ms: 响应时间（毫秒）
            status: 状态（success, failed, timeout）
            error_message: 错误信息
            prompt_tokens: 输入 token 数（如果 API 返回）
            completion_tokens: 输出 token 数（如果 API 返回）
            usage: API 返回的 usage 字典
            agent_name: Agent 名称（可选）
            task_type: 任务类型（可选）
            **kwargs: 其他参数（如 user_id, session_id, extra_data）
        """
        if not self.enable_tracking:
            return
        
        tracker = _get_usage_tracker()
        if not tracker:
            return
        
        try:
            # 获取模型名称（子类需要实现 model_name 属性）
            model_name = getattr(self, 'model_name', 'unknown')
            
            # 如果提供了 usage 字典，优先使用
            if usage:
                prompt_tokens = usage.get('prompt_tokens', prompt_tokens)
                completion_tokens = usage.get('completion_tokens', completion_tokens)
            
            tracker.record(
                model_name=model_name,
                prompt=prompt,
                completion=completion,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                response_time_ms=response_time_ms,
                status=status,
                error_message=error_message,
                agent_name=agent_name,
                task_type=task_type,
                **kwargs
            )
        except Exception as e:
            # 追踪失败不应该影响主业务
            logger.debug(f"记录 LLM 使用情况失败: {e}")
    
    def _get_proxies(self) -> Optional[Dict[str, str]]:
        """
        获取代理配置，支持字符串和字典格式
        
        Returns:
            Optional[Dict[str, str]]: 代理配置字典
        """
        if self.proxies is None:
            return None
        
        # 如果是字符串，转换为字典格式
        if isinstance(self.proxies, str):
            return {
                "http": self.proxies,
                "https": self.proxies
            }
        
        # 如果已经是字典，直接返回
        if isinstance(self.proxies, dict):
            return self.proxies
        
        return None
    
    def verify_proxy(self, test_url: str = "https://httpbin.org/ip") -> Dict[str, Any]:
        """
        验证代理是否正常工作
        
        Args:
            test_url: 测试URL，默认为 httpbin.org/ip，会返回当前IP地址
            
        Returns:
            Dict[str, Any]: 验证结果，包含：
                - success: 是否成功
                - proxy_configured: 是否配置了代理
                - proxy_used: 实际使用的代理
                - ip_address: 通过代理访问的IP地址（如果成功）
                - error: 错误信息（如果失败）
        """
        result = {
            "success": False,
            "proxy_configured": self.proxies is not None,
            "proxy_used": None,
            "ip_address": None,
            "error": None
        }
        
        proxies = self._get_proxies()
        result["proxy_used"] = proxies
        
        try:
            logger.info(f"验证代理配置，测试URL: {test_url}")
            if proxies:
                logger.info(f"使用代理: {proxies}")
            else:
                logger.info("未配置代理，使用直连")
            
            response = requests.get(
                test_url,
                proxies=proxies,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            result["ip_address"] = data.get("origin", "未知")
            result["success"] = True
            
            if proxies:
                logger.info(f"代理验证成功，当前IP: {result['ip_address']}")
            else:
                logger.info(f"直连验证成功，当前IP: {result['ip_address']}")
                
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"代理验证失败: {str(e)}")
        
        return result
    
    def _is_retryable_error(self, error: Exception, status_code: Optional[int] = None) -> bool:
        """
        判断错误是否可重试
        
        Args:
            error: 异常对象
            status_code: HTTP状态码（如果有）
            
        Returns:
            bool: 是否可重试
        """
        # 网络超时和连接错误可重试
        if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return True
        
        # HTTP错误：5xx服务器错误和429请求过多可重试
        if isinstance(error, requests.exceptions.HTTPError) and status_code:
            if status_code >= 500:  # 服务器错误
                return True
            if status_code == 429:  # 请求过多
                return True
            # 4xx客户端错误（除了429）不可重试
            return False
        
        # 其他网络相关错误可重试
        if isinstance(error, requests.exceptions.RequestException):
            return True
        
        # 其他错误不可重试
        return False
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        计算指数退避延迟时间
        
        Args:
            attempt: 当前尝试次数（从0开始）
            
        Returns:
            float: 延迟时间（秒）
        """
        # 指数退避：base_delay * (2 ^ attempt)
        delay = self.base_delay * (2 ** attempt)
        
        # 添加随机抖动，避免同时重试
        jitter = random.uniform(0, delay * 0.1)
        delay = delay + jitter
        
        # 限制最大延迟时间
        delay = min(delay, self.max_delay)
        
        return delay
    
    def _handle_http_error(self, error: requests.exceptions.HTTPError, attempt: int) -> Optional[str]:
        """
        处理HTTP错误
        
        Args:
            error: HTTP异常对象
            attempt: 当前尝试次数
            
        Returns:
            错误消息字符串，如果应该继续重试则返回None
        """
        status_code = error.response.status_code if error.response else None
        
        # 判断是否可重试
        if not self._is_retryable_error(error, status_code):
            # 不可重试的错误
            if status_code == 401:
                logger.error("API认证失败，请检查API密钥")
                return "AI服务认证失败，请检查API密钥配置。"
            elif status_code == 400:
                logger.error(f"API请求参数错误: {str(error)}")
                return f"AI服务请求参数错误: {str(error)}"
            else:
                logger.error(f"API HTTP错误（不可重试）: {str(error)}")
                return f"AI服务请求失败: {str(error)}"
        
        # 可重试的错误
        if attempt < self.max_retries:
            delay = self._calculate_backoff_delay(attempt)
            logger.warning(
                f"API请求失败（HTTP {status_code}），"
                f"将在 {delay:.2f} 秒后重试（第 {attempt + 1}/{self.max_retries} 次）: {str(error)}"
            )
            time.sleep(delay)
            return None  # 继续重试
        else:
            logger.error(f"API请求失败，已达到最大重试次数: {str(error)}")
            return f"AI服务请求失败，已重试{self.max_retries}次: {str(error)}"
    
    def _handle_network_error(
        self,
        error: Exception,
        attempt: int,
        error_type: str = "网络错误"
    ) -> Optional[str]:
        """
        处理网络错误（超时、连接错误等）
        
        Args:
            error: 异常对象
            attempt: 当前尝试次数
            error_type: 错误类型描述
            
        Returns:
            错误消息字符串，如果应该继续重试则返回None
        """
        if attempt < self.max_retries:
            delay = self._calculate_backoff_delay(attempt)
            logger.warning(
                f"API请求{error_type}，"
                f"将在 {delay:.2f} 秒后重试（第 {attempt + 1}/{self.max_retries} 次）: {str(error)}"
            )
            time.sleep(delay)
            return None  # 继续重试
        else:
            logger.error(f"API请求{error_type}，已达到最大重试次数: {str(error)}")
            return f"AI服务请求{error_type}，已重试{self.max_retries}次，请稍后再试。"
    
    
    @abstractmethod
    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """
        调用LLM API生成文本（子类必须实现）
        
        Args:
            prompt: 提示文本
            stop: 停止标记
            run_manager: 运行管理器
            **kwargs: 其他参数
            
        Returns:
            str: 生成的文本
        """
        pass
    
    # 注意：_llm_type 和 _identifying_params 在 LangChain 的 LLM 基类中已定义
    # 子类需要实现这些属性（使用 @property 装饰器）
