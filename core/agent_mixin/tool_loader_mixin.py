#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/26
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
工具加载 Mixin
提供统一的工具加载能力，可被各类 Agent 复用
"""
from typing import Any, Dict, List, Optional
from loguru import logger

from core.tools.base.base_tool import BaseTool
from core.tools.tool_factory import ToolFactory
from core.agent_mixin.mixin_utils import (
    get_tools,
    get_llm,
)


class ToolLoaderMixin:
    """
    工具加载 Mixin
    
    提供统一的工具加载、注册、配置管理能力。
    依赖 ToolManagementMixin 提供 register_tool 方法。
    """
    
    # ==================== 可覆盖的类属性 ====================
    
    # 飞书相关工具类型
    FEISHU_TOOL_TYPES: List[str] = [
        'feishu_contact', 
        'feishu_approval', 
        'feishu_bitable', 
        'feishu_im', 
        'feishu_task'
    ]
    
    # 默认加载的工具列表（子类应覆盖）
    DEFAULT_TOOLS: List[str] = []
    
    # ==================== 工具加载方法 ====================
    
    def _get_default_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        获取各类工具的默认配置
        
        子类可覆盖此方法以添加更多配置类型。
        
        Returns:
            配置字典 {"feishu": {...}, "text2sql": {...}, ...}
        """
        configs = {}
        kwargs = getattr(self, 'kwargs', {})
        llm = get_llm(self)
        
        # 飞书工具配置
        if 'feishu_app_id' in kwargs and 'feishu_app_secret' in kwargs:
            configs['feishu'] = {
                'app_id': kwargs.get('feishu_app_id'),
                'app_secret': kwargs.get('feishu_app_secret'),
                'timeout': kwargs.get('feishu_timeout', 30)
            }
        
        # Text2SQL 工具配置（支持单数据源和多数据源）
        if llm and ('db_url' in kwargs or 'db_sources' in kwargs):
            text2sql_config = {
                'llm': llm,
                'max_results': kwargs.get('text2sql_max_results', 100),
                'allowed_schemas': kwargs.get('text2sql_allowed_schemas'),
                'excluded_tables': kwargs.get('text2sql_excluded_tables'),
            }
            # 多数据源模式
            if 'db_sources' in kwargs:
                text2sql_config['db_sources'] = kwargs.get('db_sources')
                text2sql_config['default_source'] = kwargs.get('text2sql_default_source')
            # 单数据源模式
            elif 'db_url' in kwargs:
                text2sql_config['db_url'] = kwargs.get('db_url')
            
            configs['text2sql'] = text2sql_config
        
        # Text2DateTime 工具配置
        if llm:
            configs['text2datetime'] = {
                'llm': llm
            }
        
        return configs
    
    def _build_tool_config(
        self, 
        tool_type: str, 
        custom_config: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        构建单个工具的配置
        
        根据工具类型自动选择对应的默认配置，并与自定义配置合并。
        
        Args:
            tool_type: 工具类型
            custom_config: 自定义配置（可选）
            
        Returns:
            工具配置字典 {"type": ..., "config": {...}}，如果配置不完整返回 None
        """
        default_configs = self._get_default_configs()
        config = custom_config.copy() if custom_config else {}
        
        # 飞书工具
        if tool_type in self.FEISHU_TOOL_TYPES:
            if not config.get('app_id'):
                if 'feishu' in default_configs:
                    config.update(default_configs['feishu'])
                else:
                    logger.warning(f'加载 {tool_type} 工具需要 feishu_app_id 和 feishu_app_secret')
                    return None
        
        # Text2SQL 工具
        elif tool_type == 'text2sql':
            # 支持单数据源 (db_url) 和多数据源 (db_sources) 模式
            if not config.get('llm') or (not config.get('db_url') and not config.get('db_sources')):
                if 'text2sql' in default_configs:
                    config.update(default_configs['text2sql'])
                else:
                    logger.warning(f'加载 {tool_type} 工具需要 llm 和 (db_url 或 db_sources) 配置')
                    return None
        
        # Text2DateTime 工具
        elif tool_type == 'text2datetime':
            if not config.get('llm'):
                if 'text2datetime' in default_configs:
                    config.update(default_configs['text2datetime'])
                else:
                    logger.warning(f'加载 {tool_type} 工具需要 llm 配置')
                    return None
        
        return {'type': tool_type, 'config': config}
    
    def _load_and_register_tools(self, tool_configs: List[Dict[str, Any]]) -> List[str]:
        """
        加载并注册工具
        
        Args:
            tool_configs: 工具配置列表，格式 [{"type": ..., "config": {...}}, ...]
            
        Returns:
            成功加载的工具名称列表
        """
        loaded_tools = []
        tools = ToolFactory.create_tools(tool_configs)
        
        for tool in tools:
            if tool:
                self._register_tool_internal(tool)
                loaded_tools.append(tool.tool_name)
                logger.info(f'自动加载工具: {tool.tool_name}')
        
        return loaded_tools
    
    def _register_tool_internal(self, tool: BaseTool) -> None:
        """
        内部工具注册方法（委托给 ToolManagementMixin）
        """
        if hasattr(self, 'register_tool'):
            self.register_tool(tool)
        else:
            # 降级方案
            from core.agent_mixin.mixin_utils import register_tool_unified
            register_tool_unified(self, tool)
    
    async def _load_default_tools(self) -> List[str]:
        """
        加载默认工具
        
        根据 DEFAULT_TOOLS 类属性加载工具，跳过已存在的工具。
        
        Returns:
            成功加载的工具名称列表
        """
        tool_configs = []
        tools = get_tools(self)
        
        for tool_type in self.DEFAULT_TOOLS:
            # 跳过已经存在的工具
            if tool_type in tools:
                continue
            config = self._build_tool_config(tool_type)
            if config:
                tool_configs.append(config)
        
        if tool_configs:
            return self._load_and_register_tools(tool_configs)
        return []
    
    async def _auto_load_tools(self) -> List[str]:
        """
        根据 auto_load_tools 配置加载工具
        
        支持两种配置格式：
        1. 字符串格式：["tool_type1", "tool_type2"]
        2. 字典格式：[{"type": "tool_type", "config": {...}}, ...]
        
        Returns:
            成功加载的工具名称列表
        """
        auto_load_tools = getattr(self, 'auto_load_tools', None)
        if not auto_load_tools:
            return []
        
        tool_configs = []
        
        for item in auto_load_tools:
            if isinstance(item, str):
                # 字符串格式：工具类型名
                config = self._build_tool_config(item)
                if config:
                    tool_configs.append(config)
            elif isinstance(item, dict):
                # 字典格式：{type: 工具类型, config: 自定义配置}
                tool_type = item.get('type')
                custom_config = item.get('config', {})
                config = self._build_tool_config(tool_type, custom_config)
                if config:
                    tool_configs.append(config)
        
        if tool_configs:
            return self._load_and_register_tools(tool_configs)
        return []
    
    async def _load_common_tools(self) -> List[str]:
        """
        加载通用工具（所有 Agent 都应该有的工具）
        
        Returns:
            成功加载的工具名称列表
        """
        loaded_tools = []
        tools = get_tools(self)
        llm = get_llm(self)
        
        if not llm:
            return loaded_tools
        
        # 从 ToolFactory 获取通用工具列表
        common_tool_types = ToolFactory.get_common_tools()
        
        for tool_type in common_tool_types:
            # 跳过已存在的工具
            if tool_type in tools:
                continue
            
            config = self._build_tool_config(tool_type)
            if config:
                result = self._load_and_register_tools([config])
                loaded_tools.extend(result)
        
        return loaded_tools
    
    async def _initialize_tools(self) -> List[str]:
        """
        初始化工具（统一入口）
        
        加载顺序：
        1. 通用工具（COMMON_TOOLS）- 所有 Agent 都有
        2. 默认工具（DEFAULT_TOOLS）或用户配置（auto_load_tools）
        
        Returns:
            成功加载的工具名称列表
        """
        all_loaded = []
        
        # 1. 加载通用工具
        common_loaded = await self._load_common_tools()
        all_loaded.extend(common_loaded)
        
        # 2. 加载默认/配置的工具
        auto_load_tools = getattr(self, 'auto_load_tools', None)
        if auto_load_tools:
            business_loaded = await self._auto_load_tools()
        else:
            business_loaded = await self._load_default_tools()
        all_loaded.extend(business_loaded)
        
        return all_loaded

