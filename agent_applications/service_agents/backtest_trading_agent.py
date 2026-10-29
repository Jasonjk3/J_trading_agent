#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测场景下的交易决策 Agent（与实盘共用 TradingDecisionAgent 实现）
"""
from agent_applications.service_agents.trading_decision_agent import TradingDecisionAgent

# 历史代码与文档中的类名保留为别名
BacktestTradingAgent = TradingDecisionAgent

__all__ = ["BacktestTradingAgent", "TradingDecisionAgent"]
