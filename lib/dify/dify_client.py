import json
from typing import Optional, Any, Dict, AsyncGenerator, List
import httpx
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, AsyncRetrying
import logging

logger = logging.getLogger("dify.client")


class DifyConfig(BaseModel):
    api_key: str = Field(...)
    base_url: str = "https://api.dify.ai/v1"
    timeout: int = Field(120, gt=0)
    max_retries: int = Field(3, ge=0)


class AppInfo(BaseModel):
    name: str = Field(...)
    description: str = Field(...)
    tags: List[str] = []


class DifyAPIError(Exception):
    """Base exception for Dify API errors"""

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class BaseDifyClient:
    def __init__(self, config: BaseModel):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=self.config.timeout,
            http2=True
        )

    async def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        ):
            with attempt:
                try:
                    response = await self.client.request(
                        method,
                        endpoint,
                        **kwargs
                    )
                    response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as e:
                    error_data = e.response.json()
                    logger.error(f"Dify API Error [{e.response.status_code}]: {error_data}")
                    raise DifyAPIError(
                        message=error_data.get("message", "Unknown API error"),
                        code=error_data.get("code")
                    )
                except httpx.RequestError as e:
                    logger.error(f"Network error: {str(e)}")
                    raise DifyAPIError("Network connectivity error")

    def _parse_response(self, data: dict, response_model):
        """Validate and parse API response"""
        try:
            return response_model(**data)
        except KeyError as e:
            logger.error(f"Invalid response structure: {data}")
            raise DifyAPIError("Invalid API response format") from e
        except Exception as e:
            logger.error(f"Response parsing failed: {str(e)}")
            raise DifyAPIError("Response validation error") from e

    async def _handle_stream(self, response: httpx.Response) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle the streaming response and yield parsed chunks."""
        buffer = ""
        async for raw_chunk in response.aiter_text():
            buffer += raw_chunk
            while "\n\n" in buffer:
                chunk, buffer = buffer.split("\n\n", 1)
                if chunk.startswith("data: "):
                    chunk = chunk[6:]
                    try:
                        data = json.loads(chunk)
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode JSON chunk: {chunk}. Error: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error while processing chunk: {chunk}. Error: {e}")
                else:
                    logger.warning(f"Unexpected chunk format: {chunk}")


    def _parse_chunk(self, chunk: str) -> Optional[Dict]:
        """解析单个数据块，提取有效信息"""
        try:
            chunk = chunk.strip('data: ')
            data = json.loads(chunk)
            if "data" in data:
                return data["data"]
            return None
        except json.JSONDecodeError:
            # 如果数据块不是有效的 JSON，记录日志并跳过
            logger.warning(f"Invalid JSON chunk: {chunk}")
            return None

    def _parse_event(self, lines: list):
        """处理错误事件，确保在流式响应中能够捕获异常"""
        for line in lines:
            try:
                data = json.loads(line)
                if "error" in data:
                    error_data = data["error"]
                    raise DifyAPIError(
                        message=error_data.get("message", "Unknown error"),
                        code=error_data.get("code")
                    )
            except json.JSONDecodeError:
                continue
        return None

    async def get_app_info(self):
        """Retrieve workflow execution status"""
        response = await self._request(
            "GET",
            "/info"
        )
        return self._parse_response(response.json(),AppInfo)

    async def close(self):
        """Graceful shutdown"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        await self.close()

