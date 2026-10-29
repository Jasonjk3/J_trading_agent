#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:14
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
API Gateway V1版本
"""
from fastapi import APIRouter
from app.v1.api import (
    chat_router, 
    conversation_run_router,
    agent_router, 
    llm_router, 
    service_monitor_router,
    llm_monitor_router,
    model_compare_router,
    model_management_router,
    auth_router,
    user_router,
    prompt_template_router,
    exchange_account_router,
    position_router,
    market_router,
    manual_trading_router,
    analytics_router,
    trading_agent_router,
    backtest_router,
    news_intelligence_router,
    technical_analysis_router,
    paper_trading_router,
    message_push_router,
    data_monitor_router,
)

# 创建V1版本的主路由器
v1_router = APIRouter(prefix="/v1")

# 注册子路由
v1_router.include_router(auth_router)
v1_router.include_router(user_router)
v1_router.include_router(chat_router)
v1_router.include_router(conversation_run_router)
v1_router.include_router(agent_router)
v1_router.include_router(llm_router)
v1_router.include_router(service_monitor_router)
v1_router.include_router(llm_monitor_router)
v1_router.include_router(model_compare_router)
v1_router.include_router(model_management_router)
v1_router.include_router(prompt_template_router)
v1_router.include_router(exchange_account_router)
v1_router.include_router(position_router)
v1_router.include_router(market_router)
v1_router.include_router(manual_trading_router)
v1_router.include_router(analytics_router)
v1_router.include_router(trading_agent_router)
v1_router.include_router(backtest_router)
v1_router.include_router(news_intelligence_router)
v1_router.include_router(technical_analysis_router)
v1_router.include_router(paper_trading_router)
v1_router.include_router(message_push_router)
v1_router.include_router(data_monitor_router)

__all__ = ["v1_router"]
