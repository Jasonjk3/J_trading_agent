#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""容器启动时的幂等数据库初始化。

做两件事：
1. 按当前 ORM 模型创建缺失的表（create_all 只建表，不改已有表结构）；
2. 执行 scripts/ 下的种子 SQL（可重复执行；"表/列已存在"类错误会被忽略）。

用法：
    python deployment/init_db.py
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import models.inner_models as model_package  # noqa: E402
from models.inner_models.base import Base  # noqa: E402
from configs.config import app_config  # noqa: E402
from core.infrastructure.database.async_database import AsyncDatabase  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

# 种子 SQL：只包含 CREATE TABLE IF NOT EXISTS / INSERT ... ON DUPLICATE KEY /
# 幂等 ALTER，用于补齐早期通过 SQL 而非 ORM 创建的数据（模型价格、标签等）
SEED_FILES = (
    "scripts/init_llm_monitor_tables.sql",
    "scripts/init_model_compare_tables.sql",
    "scripts/add_model_tags_migration.sql",
)

# 1050 表已存在 / 1060 列已存在 / 1061 索引名重复 / 1091 待删除的列不存在
IGNORED_MYSQL_ERRNOS = {1050, 1060, 1061, 1091}


def iter_statements(raw_sql: str):
    """把 SQL 文件拆成单条语句（跳过 -- / # 注释行）。"""
    buffer: list[str] = []
    for line in raw_sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--") or stripped.startswith("#"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            buffer = []
            if statement:
                yield statement
    tail = "\n".join(buffer).strip().rstrip(";").strip()
    if tail:
        yield tail


async def apply_seed_file(db: AsyncDatabase, path: Path) -> None:
    applied = ignored = failed = 0
    for statement in iter_statements(path.read_text(encoding="utf-8")):
        try:
            async with db.engine.begin() as connection:
                await connection.exec_driver_sql(statement)
            applied += 1
        except DBAPIError as exc:
            errno = (getattr(getattr(exc, "orig", None), "args", None) or [None])[0]
            if isinstance(errno, int) and errno in IGNORED_MYSQL_ERRNOS:
                ignored += 1
            else:
                failed += 1
                detail = str(getattr(exc, "orig", exc)).replace("\n", " ")[:200]
                print(f"[init_db] 跳过失败语句（{path.name}）：{errno} {detail}", flush=True)
    print(
        f"[init_db] {path.name}：执行 {applied} 条，忽略 {ignored} 条，失败 {failed} 条",
        flush=True,
    )


async def main() -> int:
    # 导入所有模型模块，确保 Base.metadata 完整
    for module in pkgutil.iter_modules(model_package.__path__):
        importlib.import_module(f"models.inner_models.{module.name}")

    print(
        "[init_db] 目标库："
        f"{app_config.MYSQL_USERNAME}@{app_config.MYSQL_HOST}:"
        f"{app_config.MYSQL_PORT}/{app_config.MYSQL_DB}",
        flush=True,
    )

    db = AsyncDatabase(app_config)
    try:
        async with db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        print(f"[init_db] 表结构就绪，共 {len(Base.metadata.tables)} 张表", flush=True)

        for relative_path in SEED_FILES:
            path = ROOT / relative_path
            if path.exists():
                await apply_seed_file(db, path)
            else:
                print(f"[init_db] 未找到 {relative_path}，跳过", flush=True)
    finally:
        await db.engine.dispose()

    print("[init_db] 初始化完成", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
