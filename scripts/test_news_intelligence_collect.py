#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息面采集联调脚本：直连数据库，调用与线上一致的采集逻辑，验证 LLM 能否返回可解析 JSON 并写入条目。

用法（在项目根目录执行）：
    python scripts/test_news_intelligence_collect.py
    python scripts/test_news_intelligence_collect.py --agent-id <uuid>
    python scripts/test_news_intelligence_collect.py --tick
    python scripts/test_news_intelligence_collect.py --list

环境变量与主程序相同（MYSQL_* 等），需已存在「运行中」的采集任务及可用的模型/API 配置。

说明：
    默认对指定或首个运行中任务 **忽略采集间隔**（等价于 collect_one_agent(..., ignore_interval=True)），便于立刻看到结果。
    --tick 与线上一致，会遵守 interval_minutes。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from configs.config import app_config
from core.infrastructure.database.async_database import AsyncDatabase
from app.v1.crud import news_intelligence_crud as crud
from app.v1.services.news_intelligence_collector import (
    collect_one_agent,
    run_news_intelligence_tick,
)


async def _list_running(db: AsyncDatabase) -> None:
    async with db.get_session() as session:
        agents = await crud.list_running_agents_all_users(session)
    if not agents:
        print("当前没有 status=running 的面采集任务。")
        return
    print(f"共 {len(agents)} 个运行中任务：")
    for a in agents:
        print(f"  id={a.id}  name={a.name!r}  llm_model_id={a.llm_model_id}  last_run_at={a.last_run_at}")


async def _run_single(db: AsyncDatabase, agent_id: str | None, ignore_interval: bool) -> None:
    async with db.get_session() as session:
        if agent_id:
            agents = [await crud.get_agent_by_id(session, agent_id)]
            if not agents[0]:
                print(f"错误：找不到任务 id={agent_id}")
                return
        else:
            agents = await crud.list_running_agents_all_users(session)
            if not agents:
                print("错误：没有运行中的任务。请先在前端启动任务或使用 --list 查看。")
                return
            agent_id = agents[0].id
            print(f"未指定 --agent-id，使用首个运行中任务: {agent_id} ({agents[0].name!r})")

    print(f"开始采集 agent_id={agent_id}，ignore_interval={ignore_interval} ...")
    async with db.get_session() as session:
        n = await collect_one_agent(session, agent_id, ignore_interval=ignore_interval)
    print(f"完成：写入 {n} 条（去重后新增）。")


async def _run_tick(db: AsyncDatabase) -> None:
    print("执行一轮 run_news_intelligence_tick（遵守采集间隔）...")
    await run_news_intelligence_tick(db)
    print("本轮 tick 已结束（详见日志）。")


async def amain() -> int:
    parser = argparse.ArgumentParser(description="消息面采集联调")
    parser.add_argument("--agent-id", type=str, default=None, help="指定任务 UUID；默认取首个 running")
    parser.add_argument(
        "--tick",
        action="store_true",
        help="执行完整 tick（与 Worker 一致，遵守 interval）",
    )
    parser.add_argument(
        "--respect-interval",
        action="store_true",
        help="单任务模式下也遵守 interval（默认单任务会忽略间隔）",
    )
    parser.add_argument("--list", action="store_true", help="仅列出运行中任务并退出")
    args = parser.parse_args()

    db = AsyncDatabase(app_config)
    try:
        if args.list:
            await _list_running(db)
            return 0
        if args.tick:
            await _run_tick(db)
            return 0
        ignore_interval = not args.respect_interval
        await _run_single(db, args.agent_id, ignore_interval=ignore_interval)
        return 0
    finally:
        await db.engine.dispose()


def main() -> None:
    try:
        raise SystemExit(asyncio.run(amain()))
    except KeyboardInterrupt:
        print("已中断。")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
