"""Check/apply only the three additive tables from migration 022."""

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(apply=False):
    from loguru import logger
    logger.remove()
    logging.disable(logging.CRITICAL)
    from sqlalchemy import text
    from configs.config import app_config
    from core.infrastructure.database.async_database import AsyncDatabase
    from core.agent_runtime.run_repository import ConversationRunRepository
    db = AsyncDatabase(app_config)
    try:
        before = await ConversationRunRepository(db).ready()
        if apply:
            source = Path(__file__).resolve().parents[1] / "migrations/022_create_conversation_runs.sql"
            sql = re.sub(r"--[^\n]*", "", source.read_text(encoding="utf-8"))
            statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
            names = {"agent_conversation_runs", "agent_conversation_steps", "agent_conversation_events"}
            if len(statements) != 3:
                raise ValueError("unexpected migration statement count")
            for statement in statements:
                match = re.match(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)\s*\(", statement)
                if not match or match[1] not in names:
                    raise ValueError("unexpected migration operation")
            async with db.engine.begin() as connection:
                for statement in statements:
                    await connection.execute(text(statement))
        after = await ConversationRunRepository(db).ready()
        print(json.dumps({"environment": app_config.ENVIRONMENT, "applied": apply,
                          "ready_before": before, "ready_after": after}), flush=True)
        return 0 if after else 1
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__}), flush=True)
        return 1
    finally:
        await db.engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    raise SystemExit(asyncio.run(main(parser.parse_args().apply)))
