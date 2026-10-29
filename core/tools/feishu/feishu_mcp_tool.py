#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MCP 工具封装
将 MCP 客户端封装为 Agent 可用的工具
"""
from typing import Any, Dict, Optional, List
from loguru import logger

from core.tools.base.base_tool import BaseTool
from core.mcp import FeishuMCPClient


class FeishuMCPTool(BaseTool):
    """飞书 MCP 工具，用于搜索飞书开发者文档"""
    
    def __init__(
        self,
        command: str = 'npx',
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ):
        """
        初始化飞书 MCP 工具
        
        Args:
            command: MCP 服务器启动命令
            args: 命令参数列表
            env: 环境变量字典
            timeout: 请求超时时间（秒）
        """
        super().__init__(
            tool_name="search_feishu_documents",
            tool_description="搜索飞书开发者文档，获取 API 使用说明、代码示例等技术文档",
            tool_type="mcp_search"
        )
        
        self.mcp_client = FeishuMCPClient(
            command=command,
            args=args,
            env=env,
            timeout=timeout
        )
        self._client_started = False
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数模式
        
        Returns:
            参数模式字典
        """
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，例如：'如何发送消息'、'审批流程'、'API 接口'等"
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量限制，可选，默认返回所有结果",
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["query"]
        }
    
    async def execute(self, query: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        执行工具：搜索飞书开发者文档
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            执行结果，包含：
                - success: 是否成功
                - documents: 文档列表
                - error: 错误信息（如果失败）
        """
        try:
            # 确保客户端已启动
            if not self._client_started:
                self.mcp_client.start()
                self._client_started = True
                logger.info('MCP 客户端已启动')
            
            # 搜索文档
            documents = self.mcp_client.search_documents(query=query, limit=limit)
            
            return {
                "success": True,
                "documents": documents,
                "count": len(documents),
                "query": query
            }
            
        except Exception as e:
            logger.error(f'搜索飞书文档失败: {e}')
            return {
                "success": False,
                "error": str(e),
                "query": query
            }
    
    async def cleanup(self):
        """清理资源"""
        if self._client_started and self.mcp_client:
            try:
                self.mcp_client.stop()
                self._client_started = False
                logger.info('MCP 客户端已停止')
            except Exception as e:
                logger.error(f'停止 MCP 客户端失败: {e}')

