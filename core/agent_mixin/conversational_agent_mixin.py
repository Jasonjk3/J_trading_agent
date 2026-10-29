#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
对话式 Agent 公共方法 Mixin
仅包含对话相关的公共逻辑（如工具调用处理），不包含执行流程。
"""
from typing import Any, List
from loguru import logger
from .history_mixin import HistoryMixin
from .tool_management_mixin import ToolManagementMixin


class ConversationalAgentMixin(HistoryMixin, ToolManagementMixin):
    """
    对话式 Agent 的功能增强包
    组合了历史记录管理和工具管理能力
    """
    
    async def _handle_tool_calling(
        self,
        response: str,
        messages: list,
        session_id: str,
        max_iterations: int = 3
    ) -> str:
        """处理 LLM 的工具调用指令"""
        import json
        import re
        iteration = 0
        current_response = response
        
        while iteration < max_iterations:
            # 提取工具调用块
            tool_calls = []
            pattern = r'```tool_call\s*\n(.*?)\n```'
            matches = re.findall(pattern, current_response, re.DOTALL)
            for match in matches:
                try:
                    call = json.loads(match.strip())
                    if isinstance(call, dict) and 'tool' in call:
                        tool_calls.append(call)
                except: continue
                
            if not tool_calls:
                return current_response
            
            # 执行工具
            tool_results = []
            for tool_call in tool_calls:
                name = tool_call.get('tool')
                params = tool_call.get('parameters', {})
                if name in self.tools:
                    try:
                        logger.info(f"调用工具: {name}")
                        res = await self.tools[name].execute(**params)
                        tool_results.append(f"工具 {name} 结果: {json.dumps(res, ensure_ascii=False)}")
                    except Exception as e:
                        tool_results.append(f"工具 {name} 报错: {str(e)}")
                else:
                    tool_results.append(f"错误: 未知工具 {name}")
            
            # 将结果反馈给 LLM
            messages.append({"role": "assistant", "content": current_response})
            messages.append({
                "role": "user", 
                "content": f"工具执行结果：\n" + "\n".join(tool_results) + "\n请根据结果继续回复。"
            })
            
            current_response = await self._call_llm_with_messages(messages)
            iteration += 1
            
        return current_response
