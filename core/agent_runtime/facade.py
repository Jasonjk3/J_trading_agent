"""Bridge the conversation kernel into the existing AgentExecutor contract."""

import asyncio
import base64

from core.agent_runtime.contracts import AgentResult
from core.agent_runtime.llm_contracts import LLMMessage
from core.agent_runtime.loop.controller import ConversationLoop
from core.agent_runtime.loop.budget import AgentLoopBudgetExceededError
from core.agent_runtime.loop.validation import AgentLoopOutputInvalidError
from core.agent_runtime.provider import ConversationProviderError
from core.agent_runtime.tools import ToolGateway


def user_content(message, images):
    if not images:
        return message
    content = [{"type": "text", "text": message}]
    for image in images:
        if not image.startswith(("data:image/", "https://", "http://")):
            mime = "png" if image.startswith("iVBOR") else "webp" if image.startswith("UklGR") else "jpeg"
            # Validate base64 rather than silently sending arbitrary strings.
            base64.b64decode(image, validate=True)
            image = f"data:image/{mime};base64,{image}"
        content.append({"type": "image_url", "image_url": {"url": image}})
    return content


class AgentRuntimeFacade:
    def __init__(self, provider, tools, settings):
        self.provider, self.tools, self.settings = provider, tools, settings
        self.last_result = None

    async def execute(self, request):
        provider = self.provider
        gateway_type = ToolGateway
        gateway_options = {}
        if request.context.journal is not None:
            from core.agent_runtime.run_journal import JournalProvider, JournalToolGateway
            provider = JournalProvider(provider, request.context.journal)
            gateway_type = JournalToolGateway
            gateway_options["journal"] = request.context.journal
        gateway = gateway_type(self.tools, request.context,
                              timeout_seconds=self.settings.tool_timeout_seconds,
                              max_output_bytes=self.settings.tool_max_output_bytes, **gateway_options)
        loop = ConversationLoop(provider, gateway, self.settings, output_schema=request.output_schema)
        result = AgentResult(request.context.trace_id, "error")
        try:
            if not request.context.principal.user_id:
                raise PermissionError("对话需要已认证的用户身份")
            messages = [LLMMessage("system", request.system_prompt),
                        *request.history,
                        LLMMessage("user", user_content(request.message, request.images))]
            result.response = await loop.run(messages)
            result.status = "success"
        except asyncio.CancelledError:
            result.status, result.error_code, result.error = "cancelled", "AGENT_CANCELLED", "对话已取消"
            raise
        except (AgentLoopBudgetExceededError, AgentLoopOutputInvalidError, ConversationProviderError) as exc:
            result.error_code, result.error = exc.code, str(exc)
        except asyncio.TimeoutError:
            result.error_code, result.error = "AGENT_TIMEOUT", "对话执行超时，请稍后重试"
        except PermissionError as exc:
            result.error_code, result.error = "AGENT_UNAUTHORIZED", str(exc)
        except Exception as exc:
            if request.context.journal is not None:
                from core.agent_runtime.run_repository import RunError
                if isinstance(exc, RunError):
                    result.error_code, result.error = exc.code, str(exc)
                else:
                    result.error_code, result.error = "AGENT_EXECUTION_FAILED", "对话执行失败，请稍后重试"
            else:
                result.error_code, result.error = "AGENT_EXECUTION_FAILED", "对话执行失败，请稍后重试"
        finally:
            state = loop.state
            result.runtime = {
                "version": "conversation-v1", "phase": state.phase.value,
                "model_turns": state.model_turns, "tool_actions": state.tool_actions,
                "total_tokens": state.total_tokens, "compactions": state.compaction_count,
                "output_repairs": state.output_repair_attempts, "tool_audit": gateway.audit,
            }
            self.last_result = result
        return result
