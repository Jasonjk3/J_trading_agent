#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
工具注册管理 Mixin
专门负责 Agent 的工具注册、注销和访问
"""
from typing import Dict, Optional, List
from loguru import logger
from core.tools.base.base_tool import BaseTool
from core.agent_mixin.mixin_utils import (
    register_tool_unified,
    unregister_tool_unified,
    cleanup_tools_unified
)


class ToolManagementMixin:
    """
    工具注册管理 Mixin
    
    管理 Agent 实例持有的工具字典
    """

    @property
    def tools(self) -> Dict[str, BaseTool]:
        """获取工具字典（延迟初始化）"""
        if not hasattr(self, '_tools_dict'):
            self._tools_dict: Dict[str, BaseTool] = {}
        return self._tools_dict

    def register_tool(self, tool: BaseTool) -> None:
        """注册工具"""
        register_tool_unified(self, tool)

    def unregister_tool(self, tool_name: str) -> None:
        """注销工具"""
        unregister_tool_unified(self, tool_name)

    async def _cleanup_tools(self) -> None:
        """清理所有工具资源"""
        await cleanup_tools_unified(self)
        self.tools.clear()

    def _get_tools_description(self) -> str:
        """获取工具的文本描述（用于 Prompt）"""
        if not self.tools or not getattr(self, 'enable_tool_calling', False):
            return ""
            
        import json
        tools_prompt = "\n\n你可以使用以下工具来帮助完成任务：\n"
        for tool_name, tool in self.tools.items():
            schema = tool.get_schema()
            tools_prompt += f"\n工具名称：{tool_name}\n"
            tools_prompt += f"描述：{schema.get('description', '')}\n"
            
            params = schema.get('parameters', {})
            if params:
                tools_prompt += f"参数：{json.dumps(params, ensure_ascii=False, indent=2)}\n"
        
        tools_prompt += "\n当需要使用工具时，请在回复中使用以下格式：\n"
        tools_prompt += "```tool_call\n{\n  \"tool\": \"工具名称\",\n  \"parameters\": {\"参数名\": \"参数值\"}\n}\n```\n"
        return tools_prompt

