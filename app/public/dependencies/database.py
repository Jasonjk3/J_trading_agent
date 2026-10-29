#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/7 13:55
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
数据库会话依赖注入

使用方式:
    from app.public.dependencies.database import get_db_session
    
    @router.get("/example")
    async def example(session: AsyncSession = Depends(get_db_session)):
        # session 是一个 AsyncSession 实例
        pass
"""
from fastapi import Depends, Request
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话（依赖注入）
    
    通过 Request 对象获取应用实例，从而访问 app.state.db
    这样避免了循环导入问题
    
    Args:
        request: FastAPI 请求对象
        
    Yields:
        AsyncSession: 异步数据库会话
    """
    db = request.app.state.db
    async with db.get_session() as session:
        yield session
