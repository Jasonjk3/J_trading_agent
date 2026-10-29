#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书 MCP 客户端
提供与飞书开发者文档搜索 MCP 服务器的通信功能
"""
from typing import Optional, Dict, Any, List
from loguru import logger

from core.mcp.feishu.mcp_client import MCPClient


class FeishuMCPClient(MCPClient):
    """飞书 MCP 客户端，用于搜索飞书开发者文档"""
    
    def __init__(
        self,
        command: str = 'npx',
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ):
        """
        初始化飞书 MCP 客户端
        
        Args:
            command: MCP 服务器启动命令，默认 'npx'
            args: 命令参数列表，默认使用飞书文档搜索配置
            env: 环境变量字典
            timeout: 请求超时时间（秒），默认 30 秒
        """
        if args is None:
            args = [
                '-y',
                '@larksuiteoapi/lark-mcp',
                'recall-developer-documents'
            ]
        
        super().__init__(
            command=command,
            args=args,
            env=env,
            timeout=timeout
        )
    
    def search_documents(
        self,
        query: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索飞书开发者文档
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量限制，可选
            
        Returns:
            文档搜索结果列表，每个结果包含 text 和 metadata 字段
        """
        try:
            # 构建工具调用参数
            tool_params = {'query': query}
            if limit is not None:
                tool_params['limit'] = limit
            
            # 调用 MCP 工具
            result = self.call('tools/call', {
                'name': 'recall-developer-documents',
                'arguments': tool_params
            })
            
            # 解析结果
            documents = []
            if isinstance(result, dict):
                # MCP 工具调用返回格式：{ "content": [...] }
                content = result.get('content', [])
                
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            # 提取文本和元数据
                            text = item.get('text', '')
                            if text:
                                documents.append({
                                    'text': text,
                                    'metadata': item.get('metadata', {})
                                })
                elif isinstance(content, str):
                    # 如果 content 是字符串
                    documents.append({
                        'text': content,
                        'metadata': {}
                    })
            
            logger.info(f'搜索到 {len(documents)} 条文档结果')
            return documents
            
        except Exception as e:
            logger.error(f'搜索飞书文档失败: {e}')
            raise RuntimeError(f'搜索飞书文档失败: {str(e)}')
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        列出可用的 MCP 工具
        
        Returns:
            工具列表
        """
        try:
            result = self.call('tools/list')
            
            if isinstance(result, dict):
                tools = result.get('tools', [])
                return tools if isinstance(tools, list) else []
            
            return []
        except Exception as e:
            logger.error(f'获取工具列表失败: {e}')
            return []

