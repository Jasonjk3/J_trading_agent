#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:15
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
API路由模块
"""
from app.v1.api.auth_api import router as auth_router
from app.v1.api.user_api import router as user_router
from app.v1.api.chat_api import router as chat_router
from app.v1.api.conversation_run_api import router as conversation_run_router
from app.v1.api.agent_api import router as agent_router
from app.v1.api.llm_api import router as llm_router
from app.v1.api.service_monitor_api import router as service_monitor_router
from app.v1.api.llm_monitor_api import router as llm_monitor_router
from app.v1.api.model_compare_api import router as model_compare_router
from app.v1.api.model_management_api import router as model_management_router
from app.v1.api.prompt_template_api import router as prompt_template_router
from app.v1.api.exchange_account_api import router as exchange_account_router
from app.v1.api.position_api import router as position_router
from app.v1.api.market_api import router as market_router
from app.v1.api.manual_trading_api import router as manual_trading_router
from app.v1.api.analytics_api import router as analytics_router
from app.v1.api.trading_agent_api import router as trading_agent_router
from app.v1.api.backtest_api import router as backtest_router
from app.v1.api.news_intelligence_api import router as news_intelligence_router
from app.v1.api.technical_analysis_api import router as technical_analysis_router
from app.v1.api.paper_trading_api import router as paper_trading_router
from app.v1.api.message_push_api import router as message_push_router
from app.v1.api.data_monitor_api import router as data_monitor_router

__all__ = [
    "auth_router",
    "user_router",
    "chat_router", 
    "conversation_run_router",
    "agent_router", 
    "llm_router", 
    "service_monitor_router",
    "llm_monitor_router",
    "model_compare_router",
    "model_management_router",
    "prompt_template_router",
    "exchange_account_router",
    "position_router",
    "market_router",
    "manual_trading_router",
    "analytics_router",
    "trading_agent_router",
    "backtest_router",
    "news_intelligence_router",
    "technical_analysis_router",
    "paper_trading_router",
    "message_push_router",
    "data_monitor_router",
]
