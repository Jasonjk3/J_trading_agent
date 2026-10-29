#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
对话历史管理 Mixin
专门负责维护 Agent 的多会话历史记录
"""
from typing import Dict, List, Optional
from loguru import logger


class HistoryMixin:
    """
    对话历史管理 Mixin
    
    支持多 session 的历史记录存储和自动截断
    """

    @property
    def conversation_history(self) -> Dict[str, List[Dict[str, str]]]:
        """获取会话历史字典（延迟初始化）"""
        if not hasattr(self, '_history_dict'):
            self._history_dict: Dict[str, List[Dict[str, str]]] = {}
        return self._history_dict

    def _update_history(self, session_id: str, role: str, content: str, max_rounds: int = 20):
        """
        更新历史记录
        
        Args:
            session_id: 会话ID
            role: 角色 (user/assistant)
            content: 内容
            max_rounds: 保留的对话轮数
        """
        if session_id not in self.conversation_history:
            self.conversation_history[session_id] = []
            
        history = self.conversation_history[session_id]
        history.append({"role": role, "content": content})
        
        # 截断历史 (每轮对话 2 条消息)
        limit = max_rounds * 2
        if len(history) > limit:
            self.conversation_history[session_id] = history[-limit:]

    async def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """获取指定会话的历史"""
        history = self.conversation_history.get(session_id, [])
        return history[-limit * 2:] if limit > 0 else history

    async def clear_history(self, session_id: str):
        """清除历史"""
        if session_id in self.conversation_history:
            del self.conversation_history[session_id]
            logger.info(f"已清除会话历史: {session_id}")

