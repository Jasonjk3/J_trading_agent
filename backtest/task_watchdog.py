#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lease watchdog for orphaned backtest tasks."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta

from loguru import logger

from app.v1.crud.backtest_crud import expire_stale_running_backtests


async def backtest_watchdog_loop(db, interval_seconds: float = 60.0) -> None:
    lease_seconds = max(60, int(os.getenv("BACKTEST_LEASE_SECONDS", "600")))
    while True:
        try:
            stale_before = datetime.now() - timedelta(seconds=lease_seconds)
            async with db.get_session() as session:
                count = await expire_stale_running_backtests(session, stale_before)
            if count:
                logger.warning(f"已回收 {count} 个租约过期的回测任务")
            await asyncio.sleep(max(10.0, interval_seconds))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"回测任务租约检查失败: {exc}")
            await asyncio.sleep(max(10.0, interval_seconds))
