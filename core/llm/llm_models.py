#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/01/20
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
LLM 模型名称常量
统一管理所有支持的模型名称
"""


class LLMModels:
    """
    LLM 模型名称常量类
    
    提供统一的模型名称定义，避免硬编码字符串
    """
    
    # ==================== DeepSeek 模型 ====================
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_REASONER = "deepseek-reasoner"
    
    # ==================== OpenAI GPT 模型 ====================
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_4 = "gpt-4"
    GPT_35_TURBO = "gpt-3.5-turbo"
    GPT_51 = "gpt-5.1"
    GPT_52 = "gpt-5.2"
    
    # ==================== OpenAI O 系列模型 ====================
    O1 = "o1"
    # 注意：O1_PREVIEW 和 O1_MINI 已于 2025 年被 OpenAI 弃用
    # O1_PREVIEW = "o1-preview"  # 已弃用
    # O1_MINI = "o1-mini"  # 已弃用
    O3_MINI = "o3-mini"
    
    # ==================== 默认模型 ====================
    DEFAULT = GPT_4O  # 默认使用 GPT-4O
    
    # ==================== API Key 环境变量 ====================
    DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
    OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
    
    @classmethod
    def get_api_key_env(cls, model_name: str) -> str:
        """
        根据模型名称获取对应的 API Key 环境变量名
        
        Args:
            model_name: 模型名称
            
        Returns:
            API Key 环境变量名
        """
        if model_name.startswith("deepseek"):
            return cls.DEEPSEEK_API_KEY_ENV
        elif model_name.startswith(("gpt", "o1", "o3")):
            return cls.OPENAI_API_KEY_ENV
        else:
            # 默认返回 OpenAI
            return cls.OPENAI_API_KEY_ENV
    
    @classmethod
    def is_deepseek_model(cls, model_name: str) -> bool:
        """判断是否为 DeepSeek 模型"""
        return model_name.startswith("deepseek")
    
    @classmethod
    def is_openai_model(cls, model_name: str) -> bool:
        """判断是否为 OpenAI 模型"""
        return model_name.startswith(("gpt", "o1", "o3"))
    
    @classmethod
    def get_all_models(cls) -> list:
        """获取所有支持的模型列表"""
        return [
            cls.DEEPSEEK_CHAT,
            cls.DEEPSEEK_REASONER,
            cls.GPT_4O,
            cls.GPT_4O_MINI,
            cls.GPT_4_TURBO,
            cls.GPT_4,
            cls.GPT_35_TURBO,
            cls.GPT_51,
            cls.GPT_52,
            cls.O1,
            # O1_PREVIEW 和 O1_MINI 已弃用
            cls.O3_MINI,
        ]
