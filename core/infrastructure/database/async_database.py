#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/17 15:39
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
异步数据库管理器
提供数据库连接和会话管理功能
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
import os


def create_async_mysql_engine(config):
    """创建异步MySQL引擎"""
    db_url = (
        f"mysql+aiomysql://{config.MYSQL_USERNAME}:{config.MYSQL_PASSWORD}"
        f"@{config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DB}"
        f"?charset=utf8mb4"
    )
    return create_async_engine(
        db_url,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=os.getenv("SQL_DEBUG", False)
    )


class AsyncDatabase:
    """异步数据库管理器"""

    def __init__(self, config):
        self.engine = create_async_mysql_engine(config)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncSession:
        """获取异步会话"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

