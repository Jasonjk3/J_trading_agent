#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
工具基类
定义工具的基本接口
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from loguru import logger


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_type: str = "function",
        **kwargs
    ):
        """
        初始化工具
        
        Args:
            tool_name: 工具名称
            tool_description: 工具描述
            tool_type: 工具类型
            **kwargs: 其他参数
        """
        self.tool_name = tool_name
        self.tool_description = tool_description
        self.tool_type = tool_type
        self.metadata = kwargs.get('metadata', {})
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具（抽象方法，子类必须实现）
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            执行结果
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具的描述信息（用于 LLM 理解工具功能）
        
        Returns:
            工具描述字典
        """
        return {
            "name": self.tool_name,
            "description": self.tool_description,
            "type": self.tool_type,
            "parameters": self._get_parameters_schema()
        }
    
    @abstractmethod
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数模式（抽象方法，子类必须实现）
        
        Returns:
            参数模式字典
        """
        pass
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.tool_name})>"
