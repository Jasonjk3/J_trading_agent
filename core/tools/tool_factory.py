#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
工具工厂
用于自动创建和注册工具
"""
from typing import Dict, Any, List, Optional
from loguru import logger

from core.tools.base.base_tool import BaseTool
from core.tools.feishu import (
    FeishuContactTool,
    FeishuApprovalTool,
    FeishuBitableTool,
    FeishuImTool,
    FeishuTaskTool,
)
from core.tools.feishu.feishu_mcp_tool import FeishuMCPTool
from core.tools.common.text2datetime import Text2DateTimeTool
from core.tools.text2sql import Text2SQLTool


class ToolFactory:
    """工具工厂类，用于自动创建工具"""
    
    # 工具类型映射
    TOOL_CLASSES = {
        'feishu_contact': FeishuContactTool,
        'feishu_approval': FeishuApprovalTool,
        'feishu_bitable': FeishuBitableTool,
        'feishu_im': FeishuImTool,
        'feishu_task': FeishuTaskTool,
        'feishu_mcp': FeishuMCPTool,
        'text2datetime': Text2DateTimeTool,
        'text2sql': Text2SQLTool,
    }
    
    # 通用工具列表（所有Agent都应该自动加载的工具）
    COMMON_TOOLS = [
        'text2datetime',  # 文本转日期时间工具
        # 可以在这里添加更多通用工具
    ]
    
    @classmethod
    def create_tool(
        cls,
        tool_type: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[BaseTool]:
        """
        创建工具实例
        
        Args:
            tool_type: 工具类型，可选值：
                - feishu_contact: 飞书通讯录工具
                - feishu_approval: 飞书审批工具
                - feishu_bitable: 飞书多维表格工具
                - feishu_im: 飞书即时消息工具
                - feishu_mcp: 飞书 MCP 工具
            config: 工具配置字典，包含工具初始化所需的参数
        
        Returns:
            工具实例，如果创建失败返回 None
        """
        if tool_type not in cls.TOOL_CLASSES:
            logger.error(f'未知的工具类型: {tool_type}')
            return None
        
        tool_class = cls.TOOL_CLASSES[tool_type]
        config = config or {}
        
        try:
            # 根据工具类型创建实例
            if tool_type in ['feishu_contact', 'feishu_approval', 'feishu_bitable', 'feishu_im', 'feishu_task']:
                # 飞书 SDK 工具需要 app_id 和 app_secret
                app_id = config.get('app_id')
                app_secret = config.get('app_secret')
                timeout = config.get('timeout', 30)
                
                if not app_id or not app_secret:
                    logger.error(f'创建 {tool_type} 工具失败：缺少 app_id 或 app_secret')
                    return None
                
                return tool_class(app_id=app_id, app_secret=app_secret, timeout=timeout)
            
            elif tool_type == 'feishu_mcp':
                # MCP 工具可以自定义配置
                command = config.get('command', 'npx')
                args = config.get('args')
                env = config.get('env')
                timeout = config.get('timeout', 30)
                
                return FeishuMCPTool(
                    command=command,
                    args=args,
                    env=env,
                    timeout=timeout
                )
            
            elif tool_type == 'text2datetime':
                # 文本转日期时间工具需要 LLM
                llm = config.get('llm')
                if not llm:
                    logger.error(f'创建 {tool_type} 工具失败：缺少 llm 参数')
                    return None
                
                return Text2DateTimeTool(llm=llm)
            
            elif tool_type == 'text2sql':
                # Text2SQL 工具需要 LLM 和数据库配置（支持单数据源和多数据源）
                llm = config.get('llm')
                db_url = config.get('db_url')
                db_sources = config.get('db_sources')
                
                if not llm:
                    logger.error(f'创建 {tool_type} 工具失败：缺少 llm 参数')
                    return None
                
                if not db_url and not db_sources:
                    logger.error(f'创建 {tool_type} 工具失败：缺少 db_url 或 db_sources 参数')
                    return None
                
                return Text2SQLTool(
                    llm=llm,
                    db_url=db_url,
                    db_sources=db_sources,
                    default_source=config.get('default_source'),
                    max_results=config.get('max_results', 100),
                    cache_schema=config.get('cache_schema', True),
                    schema_cache_ttl=config.get('schema_cache_ttl', 3600),
                    allowed_schemas=config.get('allowed_schemas'),
                    allowed_tables=config.get('allowed_tables'),
                    excluded_tables=config.get('excluded_tables'),
                    include_sample_data=config.get('include_sample_data', False)
                )
            
            else:
                logger.error(f'不支持的工具类型: {tool_type}')
                return None
                
        except Exception as e:
            logger.error(f'创建工具 {tool_type} 失败: {e}')
            return None
    
    @classmethod
    def create_tools(
        cls,
        tool_configs: List[Dict[str, Any]]
    ) -> List[BaseTool]:
        """
        批量创建工具
        
        Args:
            tool_configs: 工具配置列表，每个配置包含：
                - type: 工具类型
                - config: 工具配置字典（可选）
        
        Returns:
            工具实例列表
        """
        tools = []
        
        for tool_config in tool_configs:
            if isinstance(tool_config, str):
                # 如果直接是字符串，当作工具类型
                tool = cls.create_tool(tool_config)
            elif isinstance(tool_config, dict):
                # 如果是字典，提取 type 和 config
                tool_type = tool_config.get('type')
                config = tool_config.get('config', {})
                tool = cls.create_tool(tool_type, config)
            else:
                logger.warning(f'无效的工具配置: {tool_config}')
                continue
            
            if tool:
                tools.append(tool)
        
        return tools
    
    @classmethod
    def get_available_tool_types(cls) -> List[str]:
        """
        获取可用的工具类型列表
        
        Returns:
            工具类型列表
        """
        return list(cls.TOOL_CLASSES.keys())
    
    @classmethod
    def get_common_tools(cls) -> List[str]:
        """
        获取通用工具列表（所有Agent都应该自动加载的工具）
        
        Returns:
            通用工具类型列表
        """
        return cls.COMMON_TOOLS.copy()
    
    @classmethod
    def create_common_tools(cls, llm=None, **kwargs) -> List[BaseTool]:
        """
        创建通用工具实例
        
        Args:
            llm: LLM实例（某些通用工具需要，如text2datetime）
            **kwargs: 其他配置参数
        
        Returns:
            通用工具实例列表
        """
        tools = []
        for tool_type in cls.COMMON_TOOLS:
            config = {}
            
            # 为需要LLM的工具提供配置
            if tool_type == 'text2datetime':
                if llm:
                    config['llm'] = llm
                else:
                    logger.warning(f'创建通用工具 {tool_type} 需要 llm 参数，跳过')
                    continue
            
            tool = cls.create_tool(tool_type, config)
            if tool:
                tools.append(tool)
            else:
                logger.warning(f'创建通用工具 {tool_type} 失败')
        
        return tools

