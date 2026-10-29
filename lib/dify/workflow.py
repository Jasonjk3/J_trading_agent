#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/21 15:58
# @Author : Jason
# @Email : Jasonforjob@qq.com
import json
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator, List, Union, Dict, Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field, validator

from .dify_client import BaseDifyClient, DifyConfig, DifyAPIError


class WorkflowRequest(BaseModel):
    inputs: Dict[str, Any]
    response_mode: str = Field("blocking", pattern="^(blocking|streaming)$")
    user: Optional[str] = Field(None, min_length=1)
    files: Optional[Dict[str, str]] = None


class WorkflowExecutionResult(BaseModel):
    workflow_id: str
    task_id: str
    status: str = Field(..., pattern="^(queued|running|succeeded|failed)$")
    outputs: Optional[Dict[str, Any]] = None
    execution_time: float
    cost: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class WorkflowBlockingDataResponse(BaseModel):
    id: str
    workflow_id: str
    status: str = Field(...)
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    elapsed_time: float
    total_tokens: int
    total_steps: int
    created_at: int
    finished_at: int


class WorkflowBlockingResponse(BaseModel):
    workflow_run_id: str
    task_id: str
    data: WorkflowBlockingDataResponse


class WorkflowStreamChunk(BaseModel):
    event: str
    task_id: str
    workflow_run_id: Optional[str] = None
    data: Dict[str, Any]


class WorkflowDifyClient(BaseDifyClient):
    def __init__(self, config: DifyConfig):
        super().__init__(config)

    async def execute_blocking_workflow(
            self,
            request: WorkflowRequest
    ) -> WorkflowBlockingResponse:
        """Execute a blocking workflow and return the result."""
        if request.response_mode != "blocking":
            raise ValueError("Response mode must be 'blocking' for this method.")

        endpoint = "/workflows/run"

        # 构造multipart数据
        files = []
        if request.files:
            for key, path in request.files.items():
                files.append((key, (path, open(path, 'rb'))))

        try:
            response = await self._request("POST", endpoint, data=request.json(), files=files)
            return self._parse_response(response.json(), WorkflowBlockingResponse)
        except httpx.HTTPStatusError as e:
            raise DifyAPIError(
                message="Unknown API error",
            ) from e

    @asynccontextmanager
    async def execute_streaming_workflow(
            self,
            request: WorkflowRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a streaming workflow and yield chunks of the response."""
        if request.response_mode != "streaming":
            raise ValueError("Response mode must be 'streaming' for this method.")

        endpoint = "/workflows/run"

        # 创建主生成器函数
        async def stream_generator() -> AsyncGenerator[Dict[str, Any], None]:
            # 构造multipart数据
            files = []
            if request.files:
                for key, path in request.files.items():
                    files.append((key, (path, open(path, 'rb'))))

            async with self.client.stream("POST", endpoint, data=request.json(), files=files) as response:
                response.raise_for_status()
                async for chunk in response.aiter_lines():
                    if chunk.strip():  # 跳过空行
                        parsed_chunk = self._parse_stream_chunk(chunk)
                        if parsed_chunk:
                            yield parsed_chunk

        try:
            yield stream_generator()  # 直接返回生成器对象
        except httpx.HTTPStatusError as e:
            # 处理流式响应中的错误事件
            # 如果没有错误事件，抛出默认错误
            raise DifyAPIError(
                message=f"Unexpected error in streaming response",
            ) from e

    def _parse_stream_chunk(self, chunk: str) -> Optional[Dict[str, Any]]:
        """解析单个流式响应块"""
        try:
            # 去掉前缀 "data: " 并解析 JSON
            if chunk.startswith("data: "):
                raw_data = json.loads(chunk[6:])  # 去掉 "data: " 前缀
                event_type = raw_data.get("event")

                # 根据 event 类型解析数据
                if event_type == "workflow_started":
                    return self._parse_workflow_started(raw_data)
                elif event_type == "node_started":
                    return self._parse_node_started(raw_data)
                elif event_type == "node_finished":
                    return self._parse_node_finished(raw_data)
                elif event_type == "workflow_finished":
                    return self._parse_workflow_finished(raw_data)
                elif event_type == "tts_message":
                    return self._parse_tts_message(raw_data)
                elif event_type == 'text_chunk':
                    return self._parse_text_chunk(raw_data)
                else:
                    logger.warning(f"Unknown event type: {event_type},chunk:{chunk}")
                    return None
            elif chunk.startswith("event: ping"):
                return {"event": "ping", "message": "Keep-alive ping"}
            else:
                logger.warning(f"Invalid chunk format: {chunk}")
                return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON chunk: {chunk}. Error: {e}")
            return None

    def _parse_workflow_started(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event": "workflow_started",
            "task_id": data["task_id"],
            "workflow_run_id": data["workflow_run_id"],
            "details": data["data"]
        }

    def _parse_node_started(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event": "node_started",
            "task_id": data["task_id"],
            "workflow_run_id": data["workflow_run_id"],
            "details": data["data"]
        }

    def _parse_node_finished(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event": "node_finished",
            "task_id": data["task_id"],
            "workflow_run_id": data["workflow_run_id"],
            "details": data["data"]
        }

    def _parse_workflow_finished(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event": "workflow_finished",
            "task_id": data["task_id"],
            "workflow_run_id": data["workflow_run_id"],
            "details": data["data"]
        }

    def _parse_tts_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event": "tts_message",
            "task_id": data["task_id"],
            "message_id": data["message_id"],
            "audio": data["audio"],
            "created_at": data["created_at"]
        }

    def _extract_error_message(self, response: httpx.Response) -> str:
        """从 HTTP 响应中提取错误信息"""
        try:
            error_data = response.json()
            return f"{error_data.get('code', 'Unknown')}: {error_data.get('message', 'No details')}"
        except (json.JSONDecodeError, KeyError):
            return response.text or "No error details available"

    def _parse_text_chunk(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """解析 text_chunk 事件"""
        try:
            return {
                "event": "text_chunk",
                "task_id": data["task_id"],
                "workflow_run_id": data["workflow_run_id"],
                "text": data["data"]["text"],
                "from_variable_selector": data["data"]["from_variable_selector"]
            }
        except KeyError as e:
            logger.error(f"Missing key in text_chunk data: {e}, data: {data}")
            return None
