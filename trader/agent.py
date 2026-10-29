"""持续状态的 LLM 交易员；判断与硬风险裁决严格分离。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from loguru import logger

from core.agent_base.service_base_agent import ServiceBaseAgent
from core.agent_mixin.service_agent_mixin import ServiceAgentMixin
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_factory import LLMFactory
from decision.rule_engine import RuleDecisionEngine
from decision.rule_params import resolve_rule_params
from decision.types import resolve_decision_mode
from trader.event_store import TraderEventStore
from trader.orchestrator import TraderOrchestrator
from trader.risk_kernel import HardRiskPolicy
from trader.schemas import OrderIntent, OrderProposal, ToolRequest, TraderState, TraderTurn
from trader.state_store import TraderStateStore
from trader.tool_gateway import TraderToolGateway


class LLMTransportError(RuntimeError):
    """LLM 客户端已完成自身重试，但没有返回模型响应。"""


class TraderAgent(ServiceAgentMixin, ServiceBaseAgent):
    """维护观点与计划，并提出订单意图的交易员入口。"""

    AGENT_TYPE = "trader"
    DEFAULT_CAPABILITIES = ["trading", "trader_turn", "portfolio_management"]

    _INTERVAL_SECONDS = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "6h": 21600,
        "12h": 43200,
        "1d": 86400,
    }

    SYSTEM_PROMPT = """你是持续管理交易组合的交易员，不是信号打分器。
你会继承上一轮的市场观点和交易计划；没有新证据时不要无意义地改变 thesis。
你可以自主选择分析框架，并明确区分事实、推断、反证与不确定性。
你可以更新观察计划并提出零个或多个订单意图。订单意图不是成交，仍需风险内核批准。
新增或增加风险必须定义保护性止损。信息不足时不应编造，应说明不交易原因和下一复核条件。
每笔新增风险都要自主选择 requested_leverage：结合波动、止损距离、预期持有时间与保证金效率决定，
并严格落在 hard_risk_policy.min_leverage 与 max_leverage 之间；杠杆不能替代止损，也不能扩大既定亏损预算。
不要输出隐藏思维链，只输出协议要求的简洁 JSON 对象。"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "交易员Agent",
        llm: Optional[BaseLLM] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        state_store: Optional[TraderStateStore] = None,
        event_store: Optional[TraderEventStore] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=self.AGENT_TYPE,
            capabilities=self.DEFAULT_CAPABILITIES,
            max_concurrent_tasks=1,
            llm=llm,
            **kwargs,
        )
        self.strategy_config = dict(strategy_config or {})
        self.decision_mode = resolve_decision_mode(self.strategy_config)
        self.trading_style = str(
            self.strategy_config.get("tradingStyle") or "balanced"
        ).lower()
        self.trading_cycle = str(
            self.strategy_config.get("tradingCycle") or "short_term"
        ).lower()
        self.aggressive_trend_starter_fraction = max(
            0.2,
            min(
                0.5,
                float(
                    self.strategy_config.get("aggressiveTrendStarterFraction")
                    or 0.35
                ),
            ),
        )
        self.symbols = [str(item).upper() for item in self.strategy_config.get("symbols") or []]
        self.policy = HardRiskPolicy.from_strategy_config(self.strategy_config)
        trader_config = self.strategy_config.get("traderConfig") or {}
        scope = str(trader_config.get("stateScope") or "runtime")
        identity = str(agent_id or uuid4())
        session_id = str(trader_config.get("sessionId") or f"{scope}:{identity}")
        self.orchestrator = TraderOrchestrator(
            session_id,
            state_store=state_store,
            event_store=event_store,
            execution_mode=str(trader_config.get("executionMode") or "shadow").lower(),
        )
        self.max_tool_calls = max(0, min(20, int(trader_config.get("maxToolCallsPerTurn") or 6)))
        self.max_order_revisions = max(0, min(3, int(trader_config.get("maxOrderRevisionsPerTurn") or 1)))
        self.max_parse_retries = max(
            0, min(3, int(self.strategy_config.get("llmParseRetries", 1)))
        )
        self.pending_order_max_bars = max(
            1, min(24, int(self.strategy_config.get("pendingOrderMaxBars") or 6))
        )
        self.pending_order_max_distance_pct = max(
            0.1,
            min(
                20.0,
                float(
                    self.strategy_config.get("pendingOrderMaxDistancePct")
                    or self.strategy_config.get("priceDeviationUpper")
                    or 2.0
                ),
            ),
        )
        self._turn_artifacts: Dict[str, Dict[str, Any]] = {}
        self._last_failed_artifacts: Dict[str, Any] = {}
        if self.decision_mode == "trader" and self.llm is None:
            self._init_model()

    def _init_model(self) -> None:
        cfg = self.strategy_config.get("llm") or {}
        extra: Dict[str, Any] = {"max_tokens": int(cfg.get("maxTokens") or 4096)}
        api_url = cfg.get("apiUrl") or cfg.get("api_url")
        if api_url:
            extra["api_url"] = api_url
        self.llm = LLMFactory.create_llm(
            model_name=cfg.get("model", "deepseek-chat"),
            api_key_env=cfg.get("apiKeyEnv", "DEEPSEEK_API_KEY"),
            temperature=float(cfg.get("temperature", 0.0)),
            **extra,
        )

    async def make_decision(
        self,
        snapshot: Any,
        account: Any,
        risk_manager: Any = None,
        analysis_context: Optional[Dict[str, Any]] = None,
        decision_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        mode = decision_mode or self.decision_mode
        if mode == "rule":
            decision = await RuleDecisionEngine(self.strategy_config).evaluate(
                snapshot, account, analysis_context
            )
            self._attach_rule_protection(decision, snapshot)
            decision["decision_mode"] = "rule"
            return decision
        if mode != "trader":
            return self._system_error("unsupported_decision_mode", f"不支持的决策模式: {mode}")
        if self.llm is None:
            return self._system_error("trader_model_unavailable", "交易员模型不可用")

        context = analysis_context or {}
        as_of = getattr(snapshot, "timestamp", None) or datetime.now(timezone.utc)
        wake_reason = str(context.get("_wake_reason") or "bar_closed")
        self._last_failed_artifacts = {}
        try:
            turn, state = await self.orchestrator.run_turn(
                as_of=as_of,
                wake_reason=wake_reason,
                prepare_state=lambda previous: self._reconcile_previous_state(
                    previous, account, context
                ),
                generate=lambda previous: self._generate_turn(
                    previous, snapshot, account, context, as_of
                ),
            )
            proposal = self.orchestrator.propose_orders(turn, snapshot, account, self.policy)
            await self.orchestrator.record_proposal(proposal)
            if self.orchestrator.execution_mode == "live" and (
                turn.order_intents or turn.cancel_order_intents
            ):
                turn, proposal = await self._confirm_proposal(
                    turn, proposal, snapshot, account, context
                )
            decision = self.orchestrator.to_execution_decision(
                turn, snapshot, account, self.policy, proposal=proposal
            )
            artifacts = self._turn_artifacts.pop(turn.decision_id, {})
            decision.update(artifacts)
            decision["trader_state_revision"] = state.revision
            decision["parsed_decision"] = json.dumps(
                decision, ensure_ascii=False, default=str
            )
            return decision
        except LLMTransportError as exc:
            logger.error(f"[{self.agent_name}] LLM 服务调用失败: {exc}")
            decision = self._system_error("llm_transport_error", str(exc))
            decision.update(self._last_failed_artifacts)
            return decision
        except Exception as exc:
            logger.exception(f"[{self.agent_name}] 交易员回合失败: {exc}")
            decision = self._system_error("trader_turn_failed", str(exc))
            decision.update(self._last_failed_artifacts)
            return decision

    def _reconcile_previous_state(
        self,
        previous: TraderState,
        account: Any,
        context: Dict[str, Any],
    ) -> TraderState:
        """用当前账户事实清理已被风控/执行层终结的 active 计划。"""
        if self.orchestrator.execution_mode != "live":
            return previous
        exposure_symbols = set()
        for position in list(account.get_all_positions() or []):
            quantity = Decimal(str(getattr(position, "quantity", 0) or 0))
            if quantity > 0:
                exposure_symbols.add(str(getattr(position, "symbol", "")).upper())
        for order in context.get("open_orders") or []:
            if not isinstance(order, dict):
                continue
            action = str(order.get("action") or "").lower()
            if action.startswith("open_") or action.startswith("add_"):
                exposure_symbols.add(str(order.get("symbol") or "").upper())

        plans = dict(previous.plans)
        removed = [
            symbol
            for symbol, plan in plans.items()
            if plan.status == "active" and symbol.upper() not in exposure_symbols
        ]
        if not removed:
            return previous
        for symbol in removed:
            plans.pop(symbol, None)
        watchlist = sorted(
            plan.symbol for plan in plans.values() if plan.status == "watching"
        )
        return previous.model_copy(update={
            "revision": previous.revision + 1,
            "plans": plans,
            "watchlist": watchlist,
            "updated_at": datetime.now(timezone.utc),
        })

    async def _generate_turn(
        self,
        previous: TraderState,
        snapshot: Any,
        account: Any,
        context: Dict[str, Any],
        as_of: datetime,
    ) -> TraderTurn:
        active_orders = [
            item for item in (context.get("open_orders") or [])
            if isinstance(item, dict) and item.get("order_id")
        ]
        gateway = TraderToolGateway(
            snapshot=snapshot,
            account=account,
            context=context,
            as_of=as_of,
            authorized_symbols=self.symbols,
        )
        prompt = self._build_prompt(previous, snapshot, account, context)
        from backtest.llm_replay_cache import (
            call_llm_with_replay,
            record_successful_llm_response,
        )
        prompts = []
        tool_results = []
        total_calls = 0
        replay_meta = None
        parse_failures: List[Dict[str, str]] = []
        while True:
            prompts.append(prompt)
            response, replay_meta = await call_llm_with_replay(self.llm, prompt)
            if self._is_llm_service_error_response(response):
                self._last_failed_artifacts = {
                    "decision_prompt": "\n\n--- TOOL ROUND ---\n\n".join(prompts),
                    "llm_raw_response": response,
                    "llm_metadata": {
                        "mode": "trader",
                        "protocol": "trader-turn-v2-tools",
                        "model": getattr(self.llm, "model_name", None),
                        "tool_call_count": total_calls,
                        "tool_results": tool_results,
                        "parse_retry_count": len(parse_failures),
                        "validation_failures": list(parse_failures),
                        "failure_kind": "transport",
                        **replay_meta.to_dict(),
                    },
                }
                raise LLMTransportError(response)
            try:
                payload = self._json_object(response)
            except Exception as exc:
                parse_failures.append({
                    "error": str(exc)[:4000],
                    "response": response[:20000],
                })
                if len(parse_failures) <= self.max_parse_retries:
                    prompt = self._turn_repair_prompt(
                        response,
                        exc,
                        active_orders,
                        runtime_context=self._runtime_context_payload(
                            previous, snapshot, account, context
                        ),
                    )
                    continue
                self._last_failed_artifacts = {
                    "decision_prompt": "\n\n--- TOOL ROUND ---\n\n".join(prompts),
                    "llm_raw_response": response,
                    "llm_metadata": {
                        "mode": "trader",
                        "protocol": "trader-turn-v2-tools",
                        "model": getattr(self.llm, "model_name", None),
                        "tool_call_count": total_calls,
                        "tool_results": tool_results,
                        "parse_retry_count": len(parse_failures) - 1,
                        "validation_failures": list(parse_failures),
                        "failure_kind": "protocol",
                        **replay_meta.to_dict(),
                    },
                }
                raise
            requests = payload.get("tool_requests") or []
            if payload.get("response_type") == "investigate" or requests:
                if not requests:
                    raise ValueError("investigate 响应必须包含 tool_requests")
                parsed = [ToolRequest.model_validate(item) for item in requests]
                if total_calls + len(parsed) > self.max_tool_calls:
                    raise ValueError("本轮只读工具调用超过硬上限")
                results = [gateway.execute(item) for item in parsed]
                await record_successful_llm_response(self.llm, prompt, response)
                total_calls += len(results)
                tool_results.extend(item.model_dump(mode="json") for item in results)
                for item in results:
                    await self.orchestrator.event_store.append(
                        self.orchestrator.session_id,
                        "tool_result_observed",
                        item.model_dump(mode="json"),
                        occurred_at=as_of,
                    )
                prompt = self._tool_followup_prompt(
                    previous,
                    tool_results,
                    context,
                    snapshot=snapshot,
                    account=account,
                )
                continue
            artifacts = {
                "decision_prompt": "\n\n--- TOOL ROUND ---\n\n".join(prompts),
                "llm_raw_response": response,
                "llm_metadata": {
                    "mode": "trader",
                    "protocol": "trader-turn-v2-tools",
                    "model": getattr(self.llm, "model_name", None),
                    "tool_call_count": total_calls,
                    "tool_results": tool_results,
                    "parse_retry_count": len(parse_failures),
                    "validation_failures": list(parse_failures),
                    **replay_meta.to_dict(),
                },
            }
            try:
                turn = self._parse_turn(response, as_of, active_orders)
            except Exception as exc:
                parse_failures.append({
                    "error": str(exc)[:4000],
                    "response": response[:20000],
                })
                if len(parse_failures) <= self.max_parse_retries:
                    prompt = self._turn_repair_prompt(
                        response,
                        exc,
                        active_orders,
                        runtime_context=self._runtime_context_payload(
                            previous, snapshot, account, context
                        ),
                    )
                    continue
                try:
                    fail_closed = self._parse_turn_rejecting_invalid_orders(
                        response, as_of, active_orders
                    )
                except Exception:
                    # 响应若还包含订单之外的协议错误，不能把它伪装成成功回合。
                    fail_closed = None
                if fail_closed is not None:
                    turn, rejected = fail_closed
                    artifacts["llm_metadata"]["parse_retry_count"] = len(parse_failures) - 1
                    artifacts["llm_metadata"]["validation_failures"] = list(parse_failures)
                    artifacts["llm_metadata"]["rejected_order_intents"] = rejected
                    logger.warning(
                        "交易员订单意图在协议纠错后仍不合法，已安全拒绝 {} 个意图",
                        len(rejected),
                    )
                    break
                # 校验失败也必须保留原始响应与完整 Prompt，便于审计和复现。
                artifacts["llm_metadata"]["parse_retry_count"] = len(parse_failures) - 1
                artifacts["llm_metadata"]["validation_failures"] = list(parse_failures)
                self._last_failed_artifacts = artifacts
                raise
            await record_successful_llm_response(self.llm, prompt, response)
            break
        self._turn_artifacts[turn.decision_id] = artifacts
        return turn

    def _turn_repair_prompt(
        self,
        response: str,
        error: Exception,
        active_orders: Optional[List[Dict[str, Any]]] = None,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """要求模型修正协议结构；涉及交易方向时不由代码猜测。"""
        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            "你上一条 final 响应未通过交易协议校验。请依据错误修正后，"
            "只返回一个完整的 response_type=final JSON，不要解释，不要请求新工具。\n"
            f"{self._final_output_contract()}\n"
            "完整结构模板（所有键必须保留）：\n"
            f"{json.dumps(self._final_output_template(), ensure_ascii=False)}\n"
            "本轮不可变账户与风险上下文（仍然有效，不得声称缺失）：\n"
            f"{json.dumps(runtime_context or {}, ensure_ascii=False, default=str)}\n"
            f"校验错误：\n{str(error)[:4000]}\n\n"
            f"当前活动挂单：\n{json.dumps(active_orders or [], ensure_ascii=False, default=str)}\n\n"
            f"待修正响应：\n{response[:20000]}"
        )

    def _build_prompt(
        self,
        previous: TraderState,
        snapshot: Any,
        account: Any,
        context: Dict[str, Any],
    ) -> str:
        payload = self._runtime_context_payload(previous, snapshot, account, context)
        payload.update({
            "available_read_tools": TraderToolGateway.catalog(),
            "tool_budget": self.max_tool_calls,
            "not_preloaded": ["recent_ohlcv", "technical_facts", "news"],
        })
        schema = self._final_output_template()
        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            "你先收到最小必要上下文。需要更多证据时输出 "
            "{\"response_type\":\"investigate\",\"tool_requests\":[{name,arguments}]}；"
            "信息充分后输出 response_type=final 及 trader-turn 业务字段。\n"
            "当前最小上下文与上一轮工作记忆（JSON）：\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            "输出 trader-turn-v1 的业务字段。decision_id、session_id、as_of 由系统注入。\n"
            f"{self._final_output_contract()}\n"
            "完整结构模板（所有键必须保留）：\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )

    def _runtime_context_payload(
        self,
        previous: TraderState,
        snapshot: Any,
        account: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构造每次 LLM 调用都必须携带的账户事实与硬风险边界。"""
        context = context or {}
        account_positions = []
        for position in list(account.get_all_positions() or []):
            account_positions.append({
                "symbol": str(getattr(position, "symbol", "")),
                "side": str(getattr(position, "side", "")),
                "quantity": float(getattr(position, "quantity", 0) or 0),
                "entry_price": float(getattr(position, "entry_price", 0) or 0),
                "leverage": float(getattr(position, "leverage", 1) or 1),
                "margin_used": float(getattr(position, "margin_used", 0) or 0),
            })
        return {
            "previous_state": previous.model_dump(mode="json"),
            "authorized_symbols": self.symbols,
            "hard_risk_policy": self.policy.public_summary(),
            "preferences": self.strategy_config.get("preferences") or {},
            "execution_profile": {
                "trading_style": self.trading_style,
                "trading_cycle": self.trading_cycle,
                "aggressive_trend_entry": {
                    "enabled": self.trading_style == "aggressive",
                    "starter_order_type": "market",
                    "pullback_order_type": "limit",
                    "starter_risk_fraction": self.aggressive_trend_starter_fraction,
                    "pullback_risk_fraction": 1.0
                    - self.aggressive_trend_starter_fraction,
                    "max_combined_risk_pct_equity": float(
                        self.policy.max_risk_per_trade_pct
                    ),
                },
            },
            "account": {
                "balance": float(getattr(account, "balance", 0) or 0),
                "equity": float(getattr(account, "equity", 0) or 0),
                "default_leverage": float(getattr(account, "leverage", 1) or 1),
                "positions": account_positions,
            },
            "market": {
                "as_of": getattr(snapshot, "timestamp", None),
                "prices": getattr(snapshot, "prices", {}) or {},
            },
            "active_orders": list(context.get("open_orders") or []),
        }

    def _tool_followup_prompt(
        self,
        previous: TraderState,
        results: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        *,
        snapshot: Any,
        account: Any,
    ) -> str:
        runtime_context = self._runtime_context_payload(
            previous, snapshot, account, context
        )
        return (
            f"{self.SYSTEM_PROMPT}\n\n"
            "以下是你主动请求的只读工具结果。所有数据都受 as_of 时间边界约束。"
            "你可以继续调查，或输出 response_type=final 的完整 trader-turn-v1 业务字段。\n"
            f"{self._final_output_contract()}\n"
            "完整结构模板（所有键必须保留）：\n"
            f"{json.dumps(self._final_output_template(), ensure_ascii=False)}\n"
            "previous_state 只是只读工作记忆，禁止照抄其存储字段 plans、watchlist、"
            "pending_hypotheses；计划变化只能写入 plan_updates。工具结果是本轮最新事实，"
            "与 previous_state 冲突时以工具结果和当前 as_of 为准。\n"
            "本轮不可变账户与风险上下文（工具调用后仍然有效，不得声称缺失）：\n"
            f"runtime_context={json.dumps(runtime_context, ensure_ascii=False, default=str)}\n"
            f"available_read_tools={json.dumps(TraderToolGateway.catalog(), ensure_ascii=False)}\n"
            f"remaining_tool_budget={max(0, self.max_tool_calls - len(results))}\n"
            f"tool_results={json.dumps(results, ensure_ascii=False, default=str)}"
        )

    def _final_output_contract(self) -> str:
        return (
            "FINAL 输出硬契约：只能输出一个 JSON 对象；顶层必须逐一包含 "
            "schema_version、response_type、market_view、plan_updates、order_intents、"
            "cancel_order_intents、pending_order_actions、no_trade_reason、next_review，任何键都不能省略。"
            "schema_version 必须为 trader-turn-v1，response_type 必须为 final，且禁止输出"
            "模板之外的 plans、watchlist、pending_hypotheses 等顶层字段。market_view 必须包含 summary、regime、"
            "trend_state、key_drivers、counter_evidence、uncertainties；trend_state 只能是 "
            "strong_bullish、strong_bearish、weak_bullish、weak_bearish、range、unclear。"
            "plan_updates、order_intents、"
            "cancel_order_intents、pending_order_actions 必须是数组，没有内容也要输出 []。"
            "对 active_orders 中每一个活动挂单，pending_order_actions 必须逐单且仅一次明确输出 "
            "keep、replace 或 cancel；replace 必须通过 replacement_client_intent_id 指向本轮 "
            "order_intents 中具有相同 client_intent_id 的替代订单。没有活动挂单时必须输出 []。"
            "不得在 keep 时重复提交同方向订单。next_review 必须包含 "
            "at、events、conditions。no_trade_reason 每次都要输出：存在 order_intents、"
            "cancel_order_intents 或 pending_order_actions 的 replace/cancel 时为 null；"
            "只有 keep 或完全没有订单动作时必须为非空字符串。每个 order_intent 必须包含 "
            "client_intent_id、symbol、side、"
            "effect、position_side、order_type、execution_role、parent_intent_id、limit_price、"
            "requested_leverage、size、protection、rationale、"
            "thesis、invalidation、expires_at；size 必须包含 mode、risk_pct_equity、"
            "notional_usdt、quantity；protection 必须包含 stop_loss_price、take_profit_price。"
            "不适用的值写 null，不能删除键。limit 订单必须填写 limit_price；open/add 必须填写"
            "保护性 stop_loss_price。effect=open|add|reduce|close；position_side=long|short。"
            f"所有 limit 订单必须填写 expires_at，且必须在当前 as_of 之后、最多 "
            f"{self.pending_order_max_bars} 根执行周期内失效。活动挂单最多保留 "
            f"{self.pending_order_max_bars} 根；当 active_orders 的 age_bars 达到上限，"
            f"或 distance_pct 绝对值超过 {self.pending_order_max_distance_pct:g}% 时，"
            "禁止 keep，只能 replace 或 cancel。keep 的 reason 必须说明等待时长、"
            "距现价、原 thesis 与当前止损/盈亏比为何仍有效。"
            "open/add 的 requested_leverage 必须是 hard_risk_policy.min_leverage 到 "
            "hard_risk_policy.max_leverage 之间的数字；激进风格下限为 2x，均衡下限为 1x，"
            "稳定风格上下限均为 1x；"
            "reduce/close 必须写 null，不得通过平仓动作改变杠杆。"
            "当 execution_profile.aggressive_trend_entry.enabled=true，且你确认 trend_state 为 "
            "strong_bullish 或 strong_bearish，并决定从空仓主动入场时，禁止只挂一个等待单："
            "必须在同一轮按顺序输出两笔同标的、同方向、同杠杆、同 thesis/invalidation/止损的意图。"
            "第一笔必须是 effect=open、order_type=market、execution_role=trend_starter、"
            "parent_intent_id=null 的轻仓主动首仓；第二笔必须是 effect=add、order_type=limit、"
            "execution_role=pullback_add，并用 parent_intent_id 指向第一笔 client_intent_id。"
            "两笔 size.mode 都必须为 risk_budget，首仓风险不得超过总单笔风险预算的 "
            f"{self.aggressive_trend_starter_fraction:.0%}，两笔 risk_pct_equity 合计不得超过 "
            "hard_risk_policy.max_risk_per_trade_pct。回撤价由你根据短线结构确定，不能为了成交随意贴近现价。"
            "证据不足、追价位置不佳或盈亏比不合格时仍可不交易；该机制不强迫产生订单。"
            "非上述两段订单使用 execution_role=standalone 且 parent_intent_id=null。"
            "next_review.events 只能使用 bar_closed、news_arrived、order_updated、risk_changed；"
            "next_review.at 若非 null 必须晚于当前 as_of。不要使用 qty、stop_loss、"
            "take_profit、reason 等旧订单字段。所有展示给用户的决策原因必须由你直接使用中文"
            "输出，至少包括 no_trade_reason、order_intents.rationale、"
            "cancel_order_intents.reason、pending_order_actions.reason；禁止返回英文原因，"
            "系统不会代为翻译。"
        )

    @staticmethod
    def _final_output_template() -> Dict[str, Any]:
        return {
            "schema_version": "trader-turn-v1",
            "response_type": "final",
            "market_view": {
                "summary": "当前观点摘要",
                "regime": None,
                "trend_state": "unclear",
                "key_drivers": ["关键事实"],
                "counter_evidence": ["反证"],
                "uncertainties": ["未知项"],
            },
            "plan_updates": [{
                "symbol": "授权交易对",
                "status": "watching|active|invalidated|closed",
                "thesis": "核心观点",
                "invalidation": "失效条件",
                "evidence": [],
                "counter_evidence": [],
                "review_triggers": [],
            }],
            "order_intents": [{
                "client_intent_id": "本轮唯一且稳定的意图ID",
                "symbol": "授权交易对",
                "side": "buy|sell",
                "effect": "open|add|reduce|close",
                "position_side": "long|short",
                "order_type": "market|limit",
                "execution_role": "standalone|trend_starter|pullback_add",
                "parent_intent_id": None,
                "limit_price": None,
                "requested_leverage": None,
                "size": {
                    "mode": "risk_budget|notional|quantity",
                    "risk_pct_equity": None,
                    "notional_usdt": None,
                    "quantity": None,
                },
                "protection": {
                    "stop_loss_price": None,
                    "take_profit_price": None,
                },
                "rationale": "精炼理由",
                "thesis": "订单绑定的观点",
                "invalidation": "观点失效条件",
                "expires_at": None,
            }],
            "cancel_order_intents": [{
                "order_id": "通过 get_positions_and_orders 获得的订单ID",
                "symbol": "授权交易对",
                "reason": "撤单理由",
            }],
            "pending_order_actions": [{
                "order_id": "active_orders 中的订单ID",
                "symbol": "授权交易对",
                "action": "keep|replace|cancel",
                "reason": "保留、替换或撤销的明确理由",
                "replacement_client_intent_id": None,
            }],
            "no_trade_reason": None,
            "next_review": {
                "at": None,
                "events": ["bar_closed|news_arrived|order_updated|risk_changed"],
                "conditions": ["价格或事实条件"],
            },
        }

    async def _confirm_proposal(
        self,
        turn: TraderTurn,
        proposal: OrderProposal,
        snapshot: Any,
        account: Any,
        context: Dict[str, Any],
    ) -> tuple[TraderTurn, OrderProposal]:
        """RiskKernel 反馈给交易员；只有显式 accept 才提交。"""
        from backtest.llm_replay_cache import call_llm_with_replay

        current_turn = turn
        current = proposal
        for revision in range(self.max_order_revisions + 1):
            prompt = (
                f"{self.SYSTEM_PROMPT}\n\n"
                "这是 RiskKernel 对订单提案的裁决。你必须明确选择："
                "accept（接受获批/缩量后的订单）、abandon（放弃全部），或 revise（给出完整 order_intents）。"
                "只输出 JSON：{\"action\":\"accept|abandon|revise\",\"order_intents\":[]}。\n"
                f"proposal={json.dumps(current.model_dump(mode='json'), ensure_ascii=False, default=str)}"
            )
            response, _ = await call_llm_with_replay(self.llm, prompt)
            payload = self._json_object(response)
            action = str(payload.get("action") or "").lower()
            if action == "accept":
                current = current.model_copy(update={
                    "commit_status": "committed",
                    "committed_at": current_turn.as_of,
                })
                await self.orchestrator.record_commit(current)
                return current_turn, current
            if action == "abandon":
                current = current.model_copy(update={"commit_status": "abandoned"})
                await self.orchestrator.record_commit(current)
                return current_turn, current
            if action != "revise" or revision >= self.max_order_revisions:
                break
            revised_payload = current_turn.model_dump(mode="python")
            revised_payload["order_intents"] = payload.get("order_intents") or []
            current_turn = TraderTurn.model_validate(revised_payload)
            current = self.orchestrator.propose_orders(
                current_turn, snapshot, account, self.policy
            )
            await self.orchestrator.record_proposal(current)
        current = current.model_copy(update={"commit_status": "abandoned"})
        await self.orchestrator.record_commit(current)
        return current_turn, current

    @staticmethod
    def _json_object(response: str) -> Dict[str, Any]:
        raw = str(response or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            payload = None
            for index, char in enumerate(raw):
                if char != "{":
                    continue
                try:
                    payload, _ = decoder.raw_decode(raw[index:])
                    break
                except json.JSONDecodeError:
                    continue
        if not isinstance(payload, dict):
            raise ValueError("交易员响应不是合法 JSON 对象")
        return payload

    @staticmethod
    def _is_llm_service_error_response(response: str) -> bool:
        """兼容旧 LLM 客户端把请求异常作为普通字符串返回的行为。"""
        text = str(response or "").strip()
        return text.startswith((
            "AI服务认证失败",
            "AI服务请求参数错误",
            "AI服务请求失败",
            "AI服务请求超时",
            "AI服务请求连接错误",
            "AI服务网络请求异常",
            "调用AI服务时发生错误",
        ))

    def _parse_turn(
        self,
        response: str,
        as_of: datetime,
        active_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> TraderTurn:
        payload = self._json_object(response)

        return self._validate_turn_payload(payload, as_of, active_orders)

    def _parse_turn_rejecting_invalid_orders(
        self,
        response: str,
        as_of: datetime,
        active_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[tuple[TraderTurn, List[Dict[str, Any]]]]:
        """重试耗尽后安全拒绝不合法订单，不推测缺失的交易语义。"""
        payload = self._json_object(response)
        raw_intents = payload.get("order_intents")
        if not isinstance(raw_intents, list) or not raw_intents:
            return None

        valid_intents: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_intents):
            try:
                intent = OrderIntent.model_validate(item)
            except Exception as exc:
                source = item if isinstance(item, dict) else {}
                rejected.append({
                    "index": index,
                    "client_intent_id": str(
                        source.get("client_intent_id")
                        or source.get("intent_id")
                        or ""
                    )[:200],
                    "symbol": str(source.get("symbol") or "")[:40],
                    "error": str(exc)[:4000],
                })
                continue
            valid_intents.append(intent.model_dump(mode="python"))

        if not rejected:
            return None

        payload["order_intents"] = valid_intents
        if not valid_intents and not payload.get("cancel_order_intents"):
            payload["no_trade_reason"] = (
                f"模型返回的 {len(rejected)} 个订单意图未通过交易协议校验，"
                "已按安全策略拒绝，本轮不执行交易"
            )
        return self._validate_turn_payload(payload, as_of, active_orders), rejected

    def _validate_turn_payload(
        self,
        payload: Dict[str, Any],
        as_of: datetime,
        active_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> TraderTurn:
        self._validate_final_response_contract(payload, as_of, active_orders)

        payload.update({
            "schema_version": "trader-turn-v1",
            "decision_id": str(uuid4()),
            "session_id": self.orchestrator.session_id,
            "as_of": as_of,
        })
        turn = TraderTurn.model_validate(payload)
        unauthorized = {
            item.symbol for item in [
                *turn.plan_updates, *turn.order_intents, *turn.cancel_order_intents,
                *turn.pending_order_actions,
            ]
            if item.symbol not in self.symbols
        }
        if unauthorized:
            raise ValueError(f"交易员返回了未授权交易对: {sorted(unauthorized)}")
        return turn

    def _validate_final_response_contract(
        self,
        payload: Dict[str, Any],
        as_of: datetime,
        active_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """校验模型必须亲自输出的固定信封；系统不补写业务字段。"""
        required = {
            "schema_version", "response_type", "market_view", "plan_updates",
            "order_intents", "cancel_order_intents", "pending_order_actions",
            "no_trade_reason", "next_review",
        }
        missing = sorted(required - payload.keys())
        if missing:
            raise ValueError(f"final 响应缺少必填顶层字段: {missing}")
        unknown = sorted(payload.keys() - required)
        if unknown:
            raise ValueError(f"final 响应包含未定义顶层字段: {unknown}")
        if payload.get("schema_version") != "trader-turn-v1":
            raise ValueError("schema_version 必须为 trader-turn-v1")
        if payload.get("response_type") != "final":
            raise ValueError("final 响应的 response_type 必须为 final")

        market_view = payload.get("market_view")
        if not isinstance(market_view, dict):
            raise ValueError("market_view 必须是对象")
        market_required = {
            "summary", "regime", "trend_state", "key_drivers", "counter_evidence",
            "uncertainties",
        }
        market_missing = sorted(market_required - market_view.keys())
        if market_missing:
            raise ValueError(f"market_view 缺少必填字段: {market_missing}")
        if not str(market_view.get("summary") or "").strip():
            raise ValueError("market_view.summary 必须是非空字符串")

        for key in (
            "plan_updates", "order_intents", "cancel_order_intents",
            "pending_order_actions",
        ):
            if not isinstance(payload.get(key), list):
                raise ValueError(f"{key} 必须是数组")

        plan_required = {
            "symbol", "status", "thesis", "invalidation", "evidence",
            "counter_evidence", "review_triggers",
        }
        for index, plan in enumerate(payload["plan_updates"]):
            if not isinstance(plan, dict):
                raise ValueError(f"plan_updates.{index} 必须是对象")
            item_missing = sorted(plan_required - plan.keys())
            if item_missing:
                raise ValueError(
                    f"plan_updates.{index} 缺少必填字段: {item_missing}"
                )

        intent_required = {
            "client_intent_id", "symbol", "side", "effect", "position_side", "order_type",
            "execution_role", "parent_intent_id", "limit_price", "requested_leverage",
            "size", "protection", "rationale", "thesis", "invalidation", "expires_at",
        }
        size_required = {
            "mode", "risk_pct_equity", "notional_usdt", "quantity",
        }
        protection_required = {"stop_loss_price", "take_profit_price"}
        for index, intent in enumerate(payload["order_intents"]):
            if not isinstance(intent, dict):
                raise ValueError(f"order_intents.{index} 必须是对象")
            item_missing = sorted(intent_required - intent.keys())
            if item_missing:
                raise ValueError(
                    f"order_intents.{index} 缺少必填字段: {item_missing}"
                )
            size = intent.get("size")
            if not isinstance(size, dict):
                raise ValueError(f"order_intents.{index}.size 必须是对象")
            size_missing = sorted(size_required - size.keys())
            if size_missing:
                raise ValueError(
                    f"order_intents.{index}.size 缺少必填字段: {size_missing}"
                )
            protection = intent.get("protection")
            if not isinstance(protection, dict):
                raise ValueError(f"order_intents.{index}.protection 必须是对象")
            protection_missing = sorted(protection_required - protection.keys())
            if protection_missing:
                raise ValueError(
                    f"order_intents.{index}.protection 缺少必填字段: {protection_missing}"
                )
            if str(intent.get("effect") or "").lower() in {"open", "add"}:
                try:
                    requested_leverage = Decimal(str(intent.get("requested_leverage")))
                except Exception as exc:
                    raise ValueError(
                        f"order_intents.{index}.requested_leverage 必须是数字"
                    ) from exc
                if not (
                    self.policy.min_leverage
                    <= requested_leverage
                    <= self.policy.max_leverage
                ):
                    raise ValueError(
                        f"order_intents.{index}.requested_leverage={requested_leverage} "
                        f"不符合当前交易风格允许范围 "
                        f"[{self.policy.min_leverage}, {self.policy.max_leverage}]"
                    )
            self._require_chinese_reason(
                intent.get("rationale"), f"order_intents.{index}.rationale"
            )
            if str(intent.get("order_type") or "").lower() == "limit":
                raw_expiry = intent.get("expires_at")
                if raw_expiry is None:
                    raise ValueError(
                        f"order_intents.{index}.expires_at：短线 limit 订单必须设置有效期"
                    )
                try:
                    expiry = (
                        raw_expiry
                        if isinstance(raw_expiry, datetime)
                        else datetime.fromisoformat(str(raw_expiry).replace("Z", "+00:00"))
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"order_intents.{index}.expires_at 必须为 ISO 时间"
                    ) from exc
                normalized_as_of = as_of
                if normalized_as_of.tzinfo is None:
                    normalized_as_of = normalized_as_of.replace(tzinfo=timezone.utc)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                interval = str(
                    self.strategy_config.get("interval")
                    or self.strategy_config.get("analysisTimeframe")
                    or "15m"
                ).lower()
                max_expiry = normalized_as_of + timedelta(
                    seconds=self._INTERVAL_SECONDS.get(interval, 900)
                    * self.pending_order_max_bars
                )
                if expiry <= normalized_as_of:
                    raise ValueError(
                        f"order_intents.{index}.expires_at 必须晚于当前 as_of"
                    )
                if expiry > max_expiry:
                    raise ValueError(
                        f"order_intents.{index}.expires_at 超过短线挂单上限 "
                        f"{self.pending_order_max_bars} 根"
                    )

        self._validate_aggressive_trend_entries(payload)

        cancel_required = {"order_id", "symbol", "reason"}
        for index, intent in enumerate(payload["cancel_order_intents"]):
            if not isinstance(intent, dict):
                raise ValueError(f"cancel_order_intents.{index} 必须是对象")
            item_missing = sorted(cancel_required - intent.keys())
            if item_missing:
                raise ValueError(
                    f"cancel_order_intents.{index} 缺少必填字段: {item_missing}"
                )
            self._require_chinese_reason(
                intent.get("reason"), f"cancel_order_intents.{index}.reason"
            )

        pending_required = {
            "order_id", "symbol", "action", "reason",
            "replacement_client_intent_id",
        }
        pending_actions = payload["pending_order_actions"]
        for index, item in enumerate(pending_actions):
            if not isinstance(item, dict):
                raise ValueError(f"pending_order_actions.{index} 必须是对象")
            item_missing = sorted(pending_required - item.keys())
            if item_missing:
                raise ValueError(
                    f"pending_order_actions.{index} 缺少必填字段: {item_missing}"
                )
            self._require_chinese_reason(
                item.get("reason"), f"pending_order_actions.{index}.reason"
            )

        active_by_id = {
            str(item.get("order_id")): item
            for item in (active_orders or [])
            if isinstance(item, dict) and item.get("order_id")
        }
        reviewed_ids = [str(item.get("order_id") or "") for item in pending_actions]
        duplicates = sorted({order_id for order_id in reviewed_ids if reviewed_ids.count(order_id) > 1})
        if duplicates:
            raise ValueError(f"活动挂单被重复处置: {duplicates}")
        missing_reviews = sorted(set(active_by_id) - set(reviewed_ids))
        unknown_reviews = sorted(set(reviewed_ids) - set(active_by_id))
        if missing_reviews:
            raise ValueError(f"以下活动挂单缺少 keep|replace|cancel 决策: {missing_reviews}")
        if unknown_reviews:
            raise ValueError(f"pending_order_actions 包含非活动订单: {unknown_reviews}")

        intent_ids = {
            str(item.get("client_intent_id") or "")
            for item in payload["order_intents"]
            if isinstance(item, dict) and item.get("client_intent_id")
        }
        cancelled_ids = {
            str(item.get("order_id") or "") for item in payload["cancel_order_intents"]
        }
        intents_by_id = {
            str(item.get("client_intent_id")): item
            for item in payload["order_intents"]
            if isinstance(item, dict) and item.get("client_intent_id")
        }
        for item in pending_actions:
            order_id = str(item.get("order_id") or "")
            active = active_by_id.get(order_id) or {}
            if str(item.get("symbol") or "").upper() != str(active.get("symbol") or "").upper():
                raise ValueError(f"pending_order_actions[{order_id}] 的 symbol 与活动订单不一致")
            action = item.get("action")
            replacement_id = str(item.get("replacement_client_intent_id") or "")
            if action == "replace" and replacement_id not in intent_ids:
                raise ValueError(
                    f"replace 订单 {order_id} 未指向本轮有效 replacement_client_intent_id"
                )
            if action == "keep" and order_id in cancelled_ids:
                raise ValueError(f"订单 {order_id} 不能同时 keep 和 cancel")
            if action == "keep":
                age_bars = active.get("age_bars")
                if age_bars is not None and float(age_bars) >= self.pending_order_max_bars:
                    raise ValueError(
                        f"订单 {order_id} 已等待 {age_bars} 根，达到短线挂单上限，"
                        "必须 replace 或 cancel"
                    )
                distance_pct = active.get("distance_pct")
                if (
                    distance_pct is not None
                    and abs(float(distance_pct)) > self.pending_order_max_distance_pct
                ):
                    raise ValueError(
                        f"订单 {order_id} 距现价 {float(distance_pct):.2f}%，超过 "
                        f"{self.pending_order_max_distance_pct:g}% 上限，必须 replace 或 cancel"
                    )
            active_position_side = str(active.get("position_side") or "").lower()
            same_direction_new_intents = [
                intent for intent in payload["order_intents"]
                if str(intent.get("symbol") or "").upper()
                == str(active.get("symbol") or "").upper()
                and str(intent.get("position_side") or "").lower() == active_position_side
                and str(intent.get("effect") or "").lower() in {"open", "add"}
            ]
            if action == "keep" and same_direction_new_intents:
                raise ValueError(
                    f"订单 {order_id} 已选择 keep，不能再提交同标的同方向新增风险订单"
                )
            if action == "replace":
                replacement = intents_by_id.get(replacement_id) or {}
                if (
                    str(replacement.get("symbol") or "").upper()
                    != str(active.get("symbol") or "").upper()
                    or str(replacement.get("position_side") or "").lower()
                    != active_position_side
                    or str(replacement.get("effect") or "").lower() not in {"open", "add"}
                ):
                    raise ValueError(
                        f"replace 订单 {order_id} 的替代意图必须是同标的同方向的 open/add"
                    )

        next_review = payload.get("next_review")
        if not isinstance(next_review, dict):
            raise ValueError("next_review 必须是对象")
        review_missing = sorted({"at", "events", "conditions"} - next_review.keys())
        if review_missing:
            raise ValueError(f"next_review 缺少必填字段: {review_missing}")
        if not isinstance(next_review.get("events"), list) or not isinstance(
            next_review.get("conditions"), list
        ):
            raise ValueError("next_review.events 和 conditions 必须是数组")
        allowed_events = {
            "bar_closed", "news_arrived", "order_updated", "risk_changed",
        }
        invalid_events = sorted({
            str(item) for item in next_review["events"] if str(item) not in allowed_events
        })
        if invalid_events:
            raise ValueError(f"next_review.events 包含未定义事件: {invalid_events}")
        review_at = next_review.get("at")
        if review_at is not None:
            try:
                parsed_review_at = (
                    review_at
                    if isinstance(review_at, datetime)
                    else datetime.fromisoformat(str(review_at).replace("Z", "+00:00"))
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("next_review.at 必须为 ISO 时间或 null") from exc
            normalized_as_of = as_of
            if normalized_as_of.tzinfo is None:
                normalized_as_of = normalized_as_of.replace(tzinfo=timezone.utc)
            if parsed_review_at.tzinfo is None:
                parsed_review_at = parsed_review_at.replace(tzinfo=timezone.utc)
            if parsed_review_at <= normalized_as_of:
                raise ValueError("next_review.at 必须晚于当前 as_of")

        manages_order = any(
            item.get("action") in {"replace", "cancel"}
            for item in pending_actions
        )
        if (
            not payload["order_intents"]
            and not payload["cancel_order_intents"]
            and not manages_order
        ):
            if not str(payload.get("no_trade_reason") or "").strip():
                raise ValueError("无订单及撤单意图时 no_trade_reason 必须是非空字符串")
            self._require_chinese_reason(
                payload.get("no_trade_reason"), "no_trade_reason"
            )
        elif payload.get("no_trade_reason") is not None:
            raise ValueError("存在订单或撤单意图时 no_trade_reason 必须为 null")

    def _validate_aggressive_trend_entries(self, payload: Dict[str, Any]) -> None:
        """强趋势主动入场必须形成一个可审计、合并计险的两段计划。"""
        intents = payload["order_intents"]
        intent_ids = [str(item.get("client_intent_id") or "") for item in intents]
        if len(intent_ids) != len(set(intent_ids)):
            raise ValueError("order_intents.client_intent_id 本轮内必须唯一")

        staged = [
            item for item in intents
            if item.get("execution_role") in {"trend_starter", "pullback_add"}
        ]
        if staged and self.trading_style != "aggressive":
            raise ValueError("趋势首仓+回撤加仓机制仅允许激进风格使用")

        trend_state = str(payload["market_view"].get("trend_state") or "unclear")
        expected_side = {
            "strong_bullish": "long",
            "strong_bearish": "short",
        }.get(trend_state)
        if starters := [
            item for item in intents if item.get("execution_role") == "trend_starter"
        ]:
            if expected_side is None:
                raise ValueError("只有确认 strong_bullish/strong_bearish 后才能使用两段趋势入场")
            if any(item.get("position_side") != expected_side for item in starters):
                raise ValueError("两段趋势入场方向必须与 market_view.trend_state 一致")
        opening = [
            item for item in intents
            if str(item.get("effect") or "").lower() == "open"
        ]
        if self.trading_style == "aggressive" and expected_side and opening:
            invalid = [
                item for item in opening
                if item.get("execution_role") != "trend_starter"
                or item.get("position_side") != expected_side
            ]
            if invalid:
                raise ValueError(
                    "激进风格确认强趋势后，主动开仓必须使用同方向的 "
                    "trend_starter + pullback_add 两段计划"
                )

        by_id = {
            str(item.get("client_intent_id") or ""): (index, item)
            for index, item in enumerate(intents)
        }
        children_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for item in intents:
            if item.get("execution_role") == "pullback_add":
                parent_id = str(item.get("parent_intent_id") or "")
                children_by_parent.setdefault(parent_id, []).append(item)
                parent = by_id.get(parent_id)
                if parent is None or parent[1].get("execution_role") != "trend_starter":
                    raise ValueError("pullback_add 必须指向本轮有效的 trend_starter")
                if parent[0] >= by_id[str(item.get("client_intent_id") or "")][0]:
                    raise ValueError("pullback_add 必须排在其 trend_starter 之后")

        max_combined_risk = self.policy.max_risk_per_trade_pct
        starter_cap = max_combined_risk * Decimal(
            str(self.aggressive_trend_starter_fraction)
        )
        for starter in starters:
            starter_id = str(starter.get("client_intent_id") or "")
            children = children_by_parent.get(starter_id) or []
            if len(children) != 1:
                raise ValueError("每个 trend_starter 必须且只能有一个 pullback_add")
            add = children[0]
            for field in ("symbol", "side", "position_side", "requested_leverage", "thesis", "invalidation"):
                if starter.get(field) != add.get(field):
                    raise ValueError(f"两段趋势入场的 {field} 必须一致")
            starter_stop = (starter.get("protection") or {}).get("stop_loss_price")
            add_stop = (add.get("protection") or {}).get("stop_loss_price")
            if starter_stop != add_stop:
                raise ValueError("两段趋势入场必须共享同一保护性止损")
            if starter.get("order_type") != "market" or starter.get("effect") != "open":
                raise ValueError("trend_starter 必须是 market open")
            if add.get("order_type") != "limit" or add.get("effect") != "add":
                raise ValueError("pullback_add 必须是 limit add")
            if starter.get("parent_intent_id") is not None:
                raise ValueError("trend_starter.parent_intent_id 必须为 null")
            if any((item.get("size") or {}).get("mode") != "risk_budget" for item in (starter, add)):
                raise ValueError("两段趋势入场的 size.mode 必须为 risk_budget")
            try:
                starter_risk = Decimal(str(starter["size"]["risk_pct_equity"]))
                add_risk = Decimal(str(add["size"]["risk_pct_equity"]))
            except Exception as exc:
                raise ValueError("两段趋势入场必须填写 risk_pct_equity") from exc
            if starter_risk <= 0 or add_risk <= 0:
                raise ValueError("两段趋势入场的 risk_pct_equity 必须大于 0")
            if starter_risk > starter_cap:
                raise ValueError(
                    f"主动首仓风险不得超过 {starter_cap}% equity"
                )
            if starter_risk + add_risk > max_combined_risk:
                raise ValueError(
                    "主动首仓与回撤加仓的合计风险不得超过单笔风险预算"
                )

        orphan_parent_ids = sorted(set(children_by_parent) - {str(item.get("client_intent_id")) for item in starters})
        if orphan_parent_ids:
            raise ValueError(f"存在没有主动首仓的回撤加仓: {orphan_parent_ids}")

    @staticmethod
    def _require_chinese_reason(value: Any, path: str) -> None:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{path} 必须是非空中文文本")
        if not any("\u4e00" <= char <= "\u9fff" for char in text):
            raise ValueError(f"{path} 必须使用中文说明，禁止仅返回英文")

    @staticmethod
    def _system_error(error_type: str, reason: str) -> Dict[str, Any]:
        return {
            "action": "system_error",
            "error_type": error_type,
            "reason": reason[:1000],
            "signals": [error_type],
            "decision_mode": "trader",
        }

    def _attach_rule_protection(self, decision: Dict[str, Any], snapshot: Any) -> None:
        action = str(decision.get("action") or "")
        if action not in {"open_long", "open_short", "add_long", "add_short"}:
            return
        symbol = str(decision.get("symbol") or "")
        price = Decimal(str((getattr(snapshot, "prices", {}) or {}).get(symbol) or 0))
        if price <= 0:
            return
        params = resolve_rule_params(self.strategy_config)
        signals = [str(item).lower() for item in decision.get("signals") or []]
        is_range = any("range" in item or "boll" in item for item in signals)
        stop_pct = Decimal(str(params["range_stop_loss" if is_range else "trend_stop_loss"])) / 100
        take_pct = Decimal(str(params["range_take_profit" if is_range else "trend_take_profit"])) / 100
        is_long = action.endswith("_long")
        stop = price * (Decimal("1") - stop_pct if is_long else Decimal("1") + stop_pct)
        take = price * (Decimal("1") + take_pct if is_long else Decimal("1") - take_pct)
        decision["stop_loss_price"] = float(stop)
        decision["take_profit_price"] = float(take)
        decision["trade_plan"] = {
            "thesis": decision.get("reason") or "rule strategy entry",
            "invalidation": "protective stop reached",
            "stop_loss_price": float(stop),
            "take_profit_price": float(take),
        }

    async def _run_service_loop(self) -> None:
        return None

    async def _service_tick(self) -> None:
        return None

    async def _handle_task(self, task: Any) -> Any:
        return None
