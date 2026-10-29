"""Authenticated internal conversation APIs; not the Agent Open API platform."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.public.dependencies.auth import get_current_user
from app.public.dependencies.response import ApiResponse
from app.v1.api.chat_api import get_chat_service
from app.v1.schemas.chat_schema import ChatRequest
from app.v1.services.conversation_run_service import public_run
from core.agent_runtime.run_repository import RunError

router = APIRouter(prefix="/chat/runs", tags=["对话执行"])


def run_service(request: Request):
    service = getattr(request.app.state, "conversation_runs", None)
    if service is None or not service.available:
        raise HTTPException(503, detail={"code": "CONVERSATION_RUN_UNAVAILABLE", "message": "对话执行服务未启用，请检查迁移与 Worker"})
    return service


def fail(exc):
    raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from None


@router.post("", status_code=202, summary="提交可恢复的对话执行")
async def submit(request: ChatRequest, user=Depends(get_current_user), service=Depends(run_service),
                 chat=Depends(get_chat_service), idempotency_key: str | None = Header(None, max_length=128)):
    if request.thinking_mode not in {"normal", "deep"}:
        raise HTTPException(422, detail="异步对话仅支持 normal/deep 模式")
    agent = await chat._select_agent_direct(None)
    if agent is None:
        raise HTTPException(503, detail="没有可用的智能助手")
    try:
        row, created = await service.submit(user.id, request, agent, idempotency_key)
        response = ApiResponse.success_response(data={"run": public_run(row), "created": created})
        response.status_code = 202
        return response
    except RunError as exc:
        fail(exc)


@router.get("", summary="查询当前用户会话的执行记录")
async def list_runs(session_id: str = Query(..., min_length=1, max_length=64),
                    limit: int = Query(50, ge=1, le=100), user=Depends(get_current_user),
                    service=Depends(run_service)):
    rows = await service.repository.list_session(session_id, str(user.id), limit)
    return ApiResponse.success_response(data={"items": [
        {**public_run(row), "message": row.payload.get("message", ""),
         "model_id": row.payload.get("model_id")} for row in rows]})


@router.get("/{run_id}", summary="查询对话执行结果")
async def get_run(run_id: str, user=Depends(get_current_user), service=Depends(run_service)):
    try:
        return ApiResponse.success_response(data=public_run(await service.repository.get(run_id, str(user.id))))
    except RunError as exc:
        fail(exc)


async def control(run_id, operation, user, service):
    try:
        return ApiResponse.success_response(data=public_run(await service.control(run_id, user.id, operation)))
    except RunError as exc:
        fail(exc)


@router.post("/{run_id}/cancel", summary="取消对话执行")
async def cancel(run_id: str, user=Depends(get_current_user), service=Depends(run_service)):
    return await control(run_id, "cancel", user, service)


@router.post("/{run_id}/pause", summary="暂停对话执行")
async def pause(run_id: str, user=Depends(get_current_user), service=Depends(run_service)):
    return await control(run_id, "pause", user, service)


@router.post("/{run_id}/resume", summary="恢复暂停的对话执行")
async def resume(run_id: str, user=Depends(get_current_user), service=Depends(run_service)):
    return await control(run_id, "resume", user, service)


@router.get("/{run_id}/events", summary="订阅可续读的对话 SSE 事件")
async def events(run_id: str, after: int = 0, last_event_id: str | None = Header(None),
                 user=Depends(get_current_user), service=Depends(run_service)):
    try:
        cursor = int(last_event_id) if last_event_id is not None else after
        if cursor < 0:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, detail="事件游标必须是非负整数") from None
    try:
        await service.repository.get(run_id, str(user.id))  # Authorize before opening the stream.
    except RunError as exc:
        fail(exc)
    return StreamingResponse(service.stream(run_id, user.id, cursor), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
