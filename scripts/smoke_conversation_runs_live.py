"""Opt-in authenticated Run/SSE smoke using only a labelled test conversation."""

import argparse
import asyncio
import json
import logging
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(args):
    if not args.allow_private_data:
        raise SystemExit("Requires explicit user authorization and --allow-private-data")
    from loguru import logger
    logger.remove()
    logging.disable(logging.CRITICAL)
    import httpx
    from fastapi import FastAPI
    from sqlalchemy import select, func
    from configs.config import app_config
    from core.infrastructure.database.async_database import AsyncDatabase
    from core.component.storage.session_store import SessionStore
    from core.component.storage.task_queue import TaskQueue
    from core.component.executor.agent_executor import AgentExecutor
    from core.component.registry.agent_registry import AgentRegistry
    from core.agent_runtime.run_repository import ConversationRunRepository
    from app.v1.services.chat_service import ChatService
    from app.v1.services.conversation_run_service import ConversationRunService
    from app.v1.services.auth_service import AuthService
    from app.v1.api.conversation_run_api import router
    from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
    from models.inner_models.user_model import UserModel, UserRole
    from models.inner_models.conversation_run_model import ConversationStepModel

    class ScopedRepository(ConversationRunRepository):
        run_id = None
        async def claim(self, lease_seconds):
            return await super().claim(lease_seconds, run_id=self.run_id) if self.run_id else None

    db = AsyncDatabase(app_config)
    service = None
    report = {"environment": app_config.ENVIRONMENT, "destination_host": args.expected_host, "checks": {}}
    try:
        async with db.get_session() as session:
            user = (await session.execute(select(UserModel).where(UserModel.is_active == True,
                UserModel.role == UserRole.ADMIN).order_by(UserModel.created_at).limit(1))).scalar_one()
        registry = AgentRegistry()
        agent = IntelligentAssistantAgent()
        if not await registry.register(agent):
            raise RuntimeError("AGENT_REGISTRATION_FAILED")
        chat = ChatService(registry, SessionStore(db), TaskQueue(db), AgentExecutor())
        resolver = chat.conversation_runtime._resolve_llm
        async def approved_resolver(*values):
            llm = await resolver(*values)
            if urlsplit(llm.api_url).hostname != args.expected_host:
                raise RuntimeError("MODEL_DESTINATION_NOT_APPROVED")
            return llm
        chat.conversation_runtime._resolve_llm = approved_resolver
        repository = ScopedRepository(db)
        service = ConversationRunService(db, chat.conversation_runtime, chat.agent_executor, repository=repository)
        service.available = await repository.ready()
        chat.conversation_runs = service
        app = FastAPI()
        app.include_router(router, prefix="/v1")
        app.state.db, app.state.chat_service, app.state.conversation_runs = db, chat, service
        token = AuthService.create_access_token({"sub": user.id, "role": "admin"}, expires_delta=timedelta(minutes=5))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://local-smoke",
                                      headers={"Authorization": "Bearer " + token}) as client:
            body = {"message": "[对话联调] 请调用 current_time，再调用 list_backtests 查询我最近1个回测；只用两句报告时间、状态和收益/回撤，没有数据则明确说明。",
                    "model_id": args.model_id}
            key = "live-run-" + __import__("uuid").uuid4().hex
            submitted = await client.post("/v1/chat/runs", json=body, headers={"Idempotency-Key": key})
            report["checks"]["accepted_202"] = submitted.status_code == 202
            if submitted.status_code != 202:
                raise RuntimeError("RUN_SUBMISSION_FAILED")
            run_id = submitted.json()["data"]["run"]["run_id"]
            repository.run_id = run_id
            report["run_id"] = run_id
            pause = await client.post(f"/v1/chat/runs/{run_id}/pause")
            report["checks"]["pause_queued"] = pause.json()["data"]["status"] == "paused"
            resume = await client.post(f"/v1/chat/runs/{run_id}/resume")
            report["checks"]["resume_queued"] = resume.json()["data"]["status"] == "queued"
            await service.start()
            stream = await asyncio.wait_for(client.get(f"/v1/chat/runs/{run_id}/events"), timeout=200)
            ids = [int(line[4:]) for line in stream.text.splitlines() if line.startswith("id: ")]
            report["checks"]["sse_final_answer"] = "event: run.succeeded" in stream.text
            report["checks"]["sse_ordered_ids"] = bool(ids) and ids == sorted(set(ids))
            record = await client.get(f"/v1/chat/runs/{run_id}")
            data = record.json()["data"]
            report["status"], report["error_code"], report["runtime"] = data["status"], data["error_code"], data["runtime"]
            report["checks"]["succeeded"] = data["status"] == "succeeded"
            report["checks"]["no_public_audit_payload"] = "tool_audit" not in data["runtime"]
            if ids:
                replay = await client.get(f"/v1/chat/runs/{run_id}/events", headers={"Last-Event-ID": str(ids[0])})
                replay_ids = [int(line[4:]) for line in replay.text.splitlines() if line.startswith("id: ")]
                report["checks"]["sse_resume"] = replay_ids == ids[1:]
            duplicate = await client.post("/v1/chat/runs", json=body, headers={"Idempotency-Key": key})
            report["checks"]["idempotent_submit"] = duplicate.json()["data"]["run"]["run_id"] == run_id
            unauthorized = await client.get(f"/v1/chat/runs/{run_id}", headers={"Authorization": ""})
            report["checks"]["unauthenticated_denied"] = unauthorized.status_code == 401
            async with db.get_session() as session:
                report["checkpoint_count"] = (await session.execute(select(func.count()).select_from(
                    ConversationStepModel).where(ConversationStepModel.run_id == run_id))).scalar_one()
        print(json.dumps(report, ensure_ascii=True), flush=True)
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        print(json.dumps({"error_type": type(exc).__name__}), flush=True)
    finally:
        if service:
            await service.stop()
        await db.engine.dispose()
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["checks"] and all(report["checks"].values()) and "error_type" not in report else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-data", action="store_true")
    parser.add_argument("--model-id", default="deepseek-v4.1-flash")
    parser.add_argument("--expected-host", default="www.dmxapi.cn")
    parser.add_argument("--report", default=".codex-tmp/conversation_runs_live_report.json")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
