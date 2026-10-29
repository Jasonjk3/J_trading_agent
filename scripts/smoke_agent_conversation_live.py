"""Opt-in real conversation smoke test using configured DB and model.

Creates only a labelled conversation and its tasks/messages. It does not start
the application lifecycle, trading schedulers or any order execution service.
Reports counters and stable errors, never keys or model/user data contents.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from sqlalchemy import select


async def public_main(args):
    """Real model/public market, synthetic identity and isolated local SQLite."""
    logger.remove()
    logging.disable(logging.CRITICAL)
    from contextlib import asynccontextmanager
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from configs.config import app_config
    from core.infrastructure.database.async_database import AsyncDatabase
    from core.component.storage.session_store import SessionStore
    from core.component.storage.task_queue import TaskQueue
    from core.component.executor.agent_executor import AgentExecutor
    from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
    from app.v1.services.agent_conversation_service import AgentConversationService
    from models.inner_models.base import Base
    from models.inner_models.session_model import SessionModel
    from models.inner_models.message_model import MessageModel
    from models.inner_models.task_model import TaskModel
    from models.inner_models.model_compare_model import ModelCompareModel

    class LocalDB:
        def __init__(self, path):
            self.engine = create_async_engine("sqlite+aiosqlite:///" + path.as_posix())
            self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

        @asynccontextmanager
        async def get_session(self):
            async with self.factory() as session:
                async with session.begin():
                    yield session

    path = Path(args.report).resolve().with_suffix(".sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    local = LocalDB(path)
    remote = AsyncDatabase(app_config)
    report = {"mode": "public", "existing_database_writes": False, "private_data_egress": False, "cases": []}
    try:
        async with local.engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[SessionModel.__table__, MessageModel.__table__, TaskModel.__table__]))
        async with remote.get_session() as session:
            model_id = args.model_id or (await session.execute(select(ModelCompareModel.model_id).where(
                ModelCompareModel.is_active == 1, ModelCompareModel.user_id.is_(None),
                ModelCompareModel.model_id.like("deepseek%")).order_by(ModelCompareModel.id.desc()).limit(1))).scalar_one()
        report["model_id"] = model_id
        svc = AgentConversationService(SessionStore(local), TaskQueue(local), AgentExecutor())
        resolver = svc._resolve_llm
        async def resolve(agent, chosen_model, _db, _user):
            async with remote.get_session() as session:
                llm = await resolver(agent, chosen_model, session, "integration-public")
                if urlsplit(llm.api_url).hostname != args.expected_host:
                    raise RuntimeError("MODEL_DESTINATION_NOT_APPROVED")
                updates = {"max_tokens": 4096, "max_retries": 0, "enable_tracking": False}
                if getattr(llm, "max_completion_tokens", None) is not None:
                    updates["max_completion_tokens"] = 4096
                return llm.copy(update=updates)
        svc._resolve_llm = resolve
        agent, session_id = IntelligentAssistantAgent(), None
        for label, message in [
            ("native_tool", "请调用 current_time 查询北京时间，回答一句日期和时间。"),
            ("history", "不再调用工具，把上一条回答中的北京时间转换成 UTC，同时列出原北京时间。"),
            ("market", "请调用 market_kline 查询 BTC-USDT 最近5根1小时K线，只报告数据起止时间和最后收盘价。"),
            ("quote_indicators", "请调用 market_quote 查询 BTC-USDT 最新价格，并调用 technical_indicators 查询1小时RSI，只报告价格、数据时间和指标；不足时明确说明，不要给交易建议。"),
        ]:
            started = time.monotonic()
            result = await svc.chat(agent, message, session_id=session_id, user_id="integration-public", model_id=model_id)
            session_id = result.session_id
            async with local.get_session() as session:
                task = (await session.execute(select(TaskModel).where(TaskModel.session_id == session_id)
                    .order_by(TaskModel.created_at.desc()).limit(1))).scalar_one()
                audit = ((task.result or {}).get("runtime") or {}).get("tool_audit", [])
            case = {"case": label, "success": result.success, "error_code": result.error_code,
                    "duration_seconds": round(time.monotonic() - started, 2), "runtime": result.runtime,
                    "task_persisted": task.result is not None,
                    "tools": [{"name": a["tool"], "status": a["status"], "error_code": a.get("error_code"),
                               "duration_ms": a["duration_ms"]} for a in audit]}
            report["cases"].append(case)
            print(json.dumps(case, ensure_ascii=True), flush=True)
            if not result.success:
                break
        report["session_isolation"] = await svc.session_store.get_session(session_id, user_id="unrelated-synthetic-user") is None
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        print(json.dumps({"error_type": type(exc).__name__}), flush=True)
    finally:
        await local.engine.dispose()
        await remote.engine.dispose()
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if len(report["cases"]) == 4 and all(c["success"] for c in report["cases"]) else 1


async def main(args):
    if args.mode == "public":
        return await public_main(args)
    if not args.allow_private_data:
        raise SystemExit("Private smoke requires explicit --allow-private-data and user authorization")
    logger.remove()
    logging.disable(logging.CRITICAL)
    from configs.config import app_config
    from core.infrastructure.database.async_database import AsyncDatabase
    from core.component.storage.session_store import SessionStore
    from core.component.storage.task_queue import TaskQueue
    from core.component.executor.agent_executor import AgentExecutor
    from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
    from app.v1.services.agent_conversation_service import AgentConversationService
    from models.inner_models.user_model import UserModel, UserRole
    from models.inner_models.task_model import TaskModel
    from models.inner_models.message_model import MessageModel
    from models.inner_models.model_compare_model import ModelCompareModel

    db = AsyncDatabase(app_config)
    report = {"environment": app_config.ENVIRONMENT, "cases": []}
    try:
        async with db.get_session() as session:
            user_id = args.user_id or (await session.execute(
                select(UserModel.id).where(UserModel.is_active == True, UserModel.role == UserRole.ADMIN)
                .order_by(UserModel.created_at).limit(1)
            )).scalar_one()
            model_id = args.model_id or (await session.execute(
                select(ModelCompareModel.model_id).where(ModelCompareModel.is_active == 1,
                    ModelCompareModel.user_id.is_(None), ModelCompareModel.model_id.like("deepseek%"))
                .order_by(ModelCompareModel.id.desc()).limit(1)
            )).scalar_one()
            report["model_id"] = model_id
            store = SessionStore(db)
            svc = AgentConversationService(store, TaskQueue(db), AgentExecutor())
            original_resolver = svc._resolve_llm

            async def bounded_resolver(*values):
                llm = await original_resolver(*values)
                if urlsplit(llm.api_url).hostname != args.expected_host:
                    raise RuntimeError("MODEL_DESTINATION_NOT_APPROVED")
                updates = {"max_tokens": 4096, "max_retries": 0, "enable_tracking": False}
                if getattr(llm, "max_completion_tokens", None) is not None:
                    updates["max_completion_tokens"] = 4096
                return llm.copy(update=updates)

            svc._resolve_llm = bounded_resolver
            agent = IntelligentAssistantAgent()
            conversation = await store.create_session(user_id=user_id, context={"purpose": "agent_conversation_live_smoke"})
            await store.update_session(conversation.session_id, title="[对话联调] Agent 能力验证", extend_ttl=False)
            report["session_id"] = conversation.session_id
            cases = [
                ("native_tool", "请调用 current_time 查询当前北京时间，只用一句中文报告日期和时间。"),
                ("history", "不再调用工具，把上一条回答中的时间转换成 UTC，回答中同时保留上一条的北京时间。"),
                ("backtest", "请调用 list_backtests 查询我最近的1个回测，只概括任务状态、收益和最大回撤；没有任务就明确说没有。"),
                ("market", "请调用 market_kline 查询 BTC-USDT 最近5根1小时K线，报告数据起止时间和最后收盘价，不要给交易建议。"),
            ]
            for label, message in cases:
                started = time.monotonic()
                result = await svc.chat(agent, message, session_id=conversation.session_id,
                                        user_id=user_id, model_id=model_id, db_session=session)
                # A fresh transaction must verify writes performed by the
                # service's independent sessions under MySQL REPEATABLE READ.
                async with db.get_session() as verification:
                    task = (await verification.execute(select(TaskModel).where(
                        TaskModel.session_id == conversation.session_id).order_by(TaskModel.created_at.desc()).limit(1)
                    )).scalar_one()
                audit = ((task.result or {}).get("runtime") or {}).get("tool_audit", [])
                item = {"case": label, "success": result.success, "error_code": result.error_code,
                        "duration_seconds": round(time.monotonic() - started, 2),
                        "runtime": result.runtime, "task_persisted": task.result is not None,
                        "tools": [{"name": e["tool"], "status": e["status"], "error_code": e.get("error_code"),
                                   "duration_ms": e["duration_ms"]} for e in audit]}
                report["cases"].append(item)
                print(json.dumps(item, ensure_ascii=True), flush=True)
                if not result.success:
                    break
            async with db.get_session() as verification:
                report["message_count"] = len((await verification.execute(select(MessageModel.id).where(
                    MessageModel.session_id == conversation.session_id))).scalars().all())
            # Validate session isolation without sending a second user's data to
            # the model or creating another identity in the database.
            invisible = await store.get_session(conversation.session_id, user_id="smoke-not-the-owner")
            report["session_isolation"] = invisible is None
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        print(json.dumps({"error_type": type(exc).__name__}), flush=True)
    finally:
        await db.engine.dispose()
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if len(report["cases"]) == 4 and all(c["success"] for c in report["cases"]) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id")
    parser.add_argument("--mode", choices=["public", "private"], default="public")
    parser.add_argument("--allow-private-data", action="store_true")
    parser.add_argument("--expected-host", default="www.dmxapi.cn")
    parser.add_argument("--user-id")
    parser.add_argument("--report", default=".codex-tmp/agent_conversation_live_report.json")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
