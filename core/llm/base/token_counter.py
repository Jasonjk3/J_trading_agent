#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
Token 计数器
支持 tiktoken（OpenAI）和字符估算两种方式
"""
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 尝试导入 tiktoken
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken 未安装，将使用字符估算方式计算 token 数量。建议安装: pip install tiktoken")


class TokenCounter:
    """
    Token 计数器
    
    支持两种计算方式：
    1. tiktoken：精确计算 OpenAI 系列模型的 token 数
    2. 字符估算：适用于其他模型，基于字符数估算
    """
    
    # OpenAI 模型对应的编码名称
    MODEL_ENCODING_MAP = {
        # GPT-4 系列
        "gpt-4": "cl100k_base",
        "gpt-4o": "o200k_base",
        "gpt-4o-mini": "o200k_base",
        "gpt-4-turbo": "cl100k_base",
        "gpt-4-turbo-preview": "cl100k_base",
        # GPT-3.5 系列
        "gpt-3.5-turbo": "cl100k_base",
        "gpt-3.5-turbo-16k": "cl100k_base",
        # o1 系列
        "o1": "o200k_base",
        # 注意：o1-mini 和 o1-preview 已于 2025 年被 OpenAI 弃用
        # o3 系列
        "o3-mini": "o200k_base",
    }
    
    # 字符估算比例（平均每个 token 对应的字符数）
    # 中文约 1.5 字符/token，英文约 4 字符/token
    CHAR_TO_TOKEN_RATIO_CJK = 1.5  # 中日韩字符
    CHAR_TO_TOKEN_RATIO_LATIN = 4.0  # 拉丁字符（英文等）
    
    def __init__(self, default_model: str = "gpt-4o"):
        """
        初始化 Token 计数器
        
        Args:
            default_model: 默认模型名称，用于选择编码方式
        """
        self.default_model = default_model
        self._encoders = {}  # 缓存编码器
    
    def _get_encoder(self, model_name: str):
        """
        获取指定模型的编码器
        
        Args:
            model_name: 模型名称
            
        Returns:
            tiktoken 编码器，如果不可用则返回 None
        """
        if not TIKTOKEN_AVAILABLE:
            return None
        
        # 从缓存获取
        if model_name in self._encoders:
            return self._encoders[model_name]
        
        # 获取编码名称
        encoding_name = self.MODEL_ENCODING_MAP.get(model_name)
        
        try:
            if encoding_name:
                encoder = tiktoken.get_encoding(encoding_name)
            else:
                # 尝试通过模型名获取编码器
                try:
                    encoder = tiktoken.encoding_for_model(model_name)
                except KeyError:
                    # 使用默认编码
                    encoder = tiktoken.get_encoding("cl100k_base")
            
            self._encoders[model_name] = encoder
            return encoder
        except Exception as e:
            logger.warning(f"获取 tiktoken 编码器失败（模型: {model_name}）: {e}")
            return None
    
    def _estimate_by_chars(self, text: str) -> int:
        """
        使用字符估算方式计算 token 数量
        
        Args:
            text: 输入文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        
        # 统计中日韩字符数量
        cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
        cjk_chars = len(cjk_pattern.findall(text))
        
        # 其他字符（主要是拉丁字符）
        other_chars = len(text) - cjk_chars
        
        # 计算估算的 token 数
        estimated_tokens = (
            cjk_chars / self.CHAR_TO_TOKEN_RATIO_CJK +
            other_chars / self.CHAR_TO_TOKEN_RATIO_LATIN
        )
        
        return max(1, int(estimated_tokens))
    
    def count_tokens(
        self,
        text: str,
        model_name: Optional[str] = None,
        use_estimation: bool = False
    ) -> int:
        """
        计算文本的 token 数量
        
        Args:
            text: 输入文本
            model_name: 模型名称，如果为 None 则使用默认模型
            use_estimation: 是否强制使用字符估算
            
        Returns:
            token 数量
        """
        if not text:
            return 0
        
        model = model_name or self.default_model
        
        # 如果强制使用估算或 tiktoken 不可用
        if use_estimation or not TIKTOKEN_AVAILABLE:
            return self._estimate_by_chars(text)
        
        # 尝试使用 tiktoken
        encoder = self._get_encoder(model)
        if encoder:
            try:
                tokens = encoder.encode(text)
                return len(tokens)
            except Exception as e:
                logger.warning(f"tiktoken 编码失败，使用字符估算: {e}")
                return self._estimate_by_chars(text)
        
        # 回退到字符估算
        return self._estimate_by_chars(text)
    
    def count_messages_tokens(
        self,
        messages: list,
        model_name: Optional[str] = None
    ) -> int:
        """
        计算消息列表的 token 数量（适用于 Chat API 格式）
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            model_name: 模型名称
            
        Returns:
            token 数量
        """
        if not messages:
            return 0
        
        total_tokens = 0
        
        # 每条消息有额外的 token 开销（角色标记等）
        # 参考 OpenAI 官方文档，每条消息约有 4 个额外 token
        tokens_per_message = 4
        
        for message in messages:
            total_tokens += tokens_per_message
            
            # 计算 content 的 token
            content = message.get("content", "")
            if content:
                total_tokens += self.count_tokens(content, model_name)
            
            # role 字段约 1 token
            total_tokens += 1
        
        # 每个请求有固定开销（约 3 tokens）
        total_tokens += 3
        
        return total_tokens
    
    def count_prompt_completion(
        self,
        prompt: str,
        completion: str,
        model_name: Optional[str] = None
    ) -> Tuple[int, int, int]:
        """
        分别计算 prompt 和 completion 的 token 数量
        
        Args:
            prompt: 输入提示
            completion: 生成的回复
            model_name: 模型名称
            
        Returns:
            (prompt_tokens, completion_tokens, total_tokens)
        """
        prompt_tokens = self.count_tokens(prompt, model_name)
        completion_tokens = self.count_tokens(completion, model_name)
        total_tokens = prompt_tokens + completion_tokens
        
        return prompt_tokens, completion_tokens, total_tokens


# 全局单例实例
_token_counter: Optional[TokenCounter] = None


def get_token_counter() -> TokenCounter:
    """获取全局 Token 计数器实例"""
    global _token_counter
    if _token_counter is None:
        _token_counter = TokenCounter()
    return _token_counter


def count_tokens(text: str, model_name: Optional[str] = None) -> int:
    """
    便捷函数：计算文本的 token 数量
    
    Args:
        text: 输入文本
        model_name: 模型名称
        
    Returns:
        token 数量
    """
    return get_token_counter().count_tokens(text, model_name)


def count_prompt_completion(
    prompt: str,
    completion: str,
    model_name: Optional[str] = None
) -> Tuple[int, int, int]:
    """
    便捷函数：计算 prompt 和 completion 的 token 数量
    
    Args:
        prompt: 输入提示
        completion: 生成的回复
        model_name: 模型名称
        
    Returns:
        (prompt_tokens, completion_tokens, total_tokens)
    """
    return get_token_counter().count_prompt_completion(prompt, completion, model_name)
