#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测任务执行器
用于异步执行回测任务并更新数据库
"""
import asyncio
import os
import socket
import time
import uuid
from contextlib import nullcontext
from decimal import Decimal
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta, timezone
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backtest.backtest_engine import (
    BacktestEngine,
    BacktestConfig,
    KlineData,
    INTERVAL_SECONDS,
    KLINE_CONTEXT_LOOKBACK_DAYS,
    bars_for_lookback_days,
    kline_context_start,
)
from models.inner_models.backtest_model import BacktestStatus
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_factory import ApiType, LLMFactory
from app.v1.crud.backtest_crud import (
    get_backtest_by_id,
    update_backtest_status,
    update_backtest_result,
    batch_create_backtest_trades,
    batch_create_backtest_decisions,
    batch_create_backtest_equity,
    get_existing_backtest_trade_ids,
    get_existing_backtest_decision_ids,
    get_klines,
    renew_backtest_lease,
)
from app.v1.crud.trading_agent_crud import get_trading_agent_by_id_and_user
from app.v1.services.managed_llm_service import build_decision_llm, resolve_decision_llm_temperature
from agent_applications.service_agents.backtest_trading_agent import BacktestTradingAgent
from app.v1.schemas.trading_agent_schema import expand_strategy_config_for_backtest
from decision.rule_context_builder import build_rule_decision_context
from decision.types import resolve_decision_mode

PROGRESS_COMMIT_MIN_INTERVAL_SECONDS = 5.0
PROGRESS_COMMIT_MIN_PROGRESS_STEP = 10
BACKTEST_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
BACKTEST_LEASE_SECONDS = max(60, int(os.getenv("BACKTEST_LEASE_SECONDS", "600")))
BACKTEST_CANCEL_POLL_SECONDS = max(
    0.2, float(os.getenv("BACKTEST_CANCEL_POLL_SECONDS", "1.0"))
)
_BACKGROUND_TASKS: Dict[str, asyncio.Task] = {}


def start_backtest_task(backtest_id: str, db) -> asyncio.Task:
    """启动并登记后台任务，使停止接口能够真正取消对应协程。"""
    existing = _BACKGROUND_TASKS.get(backtest_id)
    if existing is not None and not existing.done():
        return existing
    task = asyncio.create_task(run_backtest_task(backtest_id=backtest_id, db=db))
    _BACKGROUND_TASKS[backtest_id] = task

    def _cleanup(done: asyncio.Task) -> None:
        if _BACKGROUND_TASKS.get(backtest_id) is done:
            _BACKGROUND_TASKS.pop(backtest_id, None)

    task.add_done_callback(_cleanup)
    return task


def cancel_backtest_task(backtest_id: str) -> bool:
    """取消当前进程登记的任务；跨进程取消由数据库 cancelled 状态兜底。"""
    task = _BACKGROUND_TASKS.get(backtest_id)
    cancelled = False
    if task is not None and not task.done():
        task.cancel()
        cancelled = True
    if _runner is not None:
        cancelled = _runner.cancel_backtest(backtest_id) or cancelled
    return cancelled


def _get_interval_seconds(interval: str) -> int:
    """根据 K 线周期返回每根 K 线的秒数"""
    return INTERVAL_SECONDS.get(interval, 900)


def _lookback_bars(interval: str) -> int:
    """预热 + 决策上下文所需 K 线根数（至少覆盖 7 天）。"""
    return bars_for_lookback_days(interval, KLINE_CONTEXT_LOOKBACK_DAYS)


class MissingHistoricalKlineError(ValueError):
    """正式回测所需真实 K 线缺失或不连续。"""


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _validate_real_kline_coverage(
    klines: List[Any],
    *,
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
) -> None:
    """要求交易区间连续，并具备完整的短线指标预热窗口。"""
    if not klines:
        raise MissingHistoricalKlineError(
            f"{symbol} {interval} 在回测区间没有真实 K 线，正式回测已终止"
        )
    start = _naive_utc(start_time)
    end = _naive_utc(end_time)
    seconds = _get_interval_seconds(interval)
    actual = {_naive_utc(item.timestamp) for item in klines}
    expected_count = int((end - start).total_seconds() // seconds) + 1
    missing: List[datetime] = []
    for index in range(expected_count):
        timestamp = start + timedelta(seconds=index * seconds)
        if timestamp not in actual:
            missing.append(timestamp)
            if len(missing) >= 5:
                break
    if missing:
        sample = ", ".join(item.isoformat() for item in missing)
        raise MissingHistoricalKlineError(
            f"{symbol} {interval} 回测区间 K 线不连续，缺失示例: {sample}；"
            "正式回测禁止使用模拟数据补齐"
        )
    lookback_count = sum(1 for timestamp in actual if timestamp < start)
    required_lookback = _lookback_bars(interval)
    if lookback_count < required_lookback:
        raise MissingHistoricalKlineError(
            f"{symbol} {interval} 指标预热 K 线不足："
            f"需要 {required_lookback} 根，实际 {lookback_count} 根；正式回测已终止"
        )


def _map_api_type(api_type_raw: Optional[str]) -> str:
    """将库中的 API 类型映射为 LLMFactory 常量。"""
    if not api_type_raw:
        return ApiType.GENERIC
    x = str(api_type_raw).strip().lower()
    if x in ("openai", "open_ai"):
        return ApiType.OPENAI
    if x == "deepseek":
        return ApiType.DEEPSEEK
    return ApiType.GENERIC


def _get_runtime_tuning(strategy_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从策略配置提取回测运行时防卡参数，统一做类型与下限处理。
    """
    cfg = strategy_config or {}

    def _f(key: str, default: float, min_value: float = 0.1) -> float:
        try:
            return max(min_value, float(cfg.get(key, default)))
        except (TypeError, ValueError):
            return default

    def _i(key: str, default: int, min_value: int = 1) -> int:
        try:
            return max(min_value, int(cfg.get(key, default)))
        except (TypeError, ValueError):
            return default

    return {
        "decision_timeout_seconds": _f("decisionTimeoutSeconds", 180.0),
        "risk_timeout_seconds": _f("riskTimeoutSeconds", 10.0),
        "progress_timeout_seconds": _f("progressTimeoutSeconds", 180.0),
        "max_consecutive_decision_errors": _i("maxConsecutiveDecisionErrors", 3),
        "decision_cooldown_steps": _i("decisionCooldownSteps", 5),
    }


def _freeze_backtest_runtime(backtest) -> Dict[str, Any]:
    """
    将回测 ORM 对象转成普通值，避免后续在闭包或异常恢复路径中
    访问已失效实例时触发 AsyncSession 隐式 IO。
    """
    interval_obj = getattr(backtest, "interval", None)
    return {
        "name": str(getattr(backtest, "name", "") or ""),
        "user_id": str(getattr(backtest, "user_id", "") or ""),
        "agent_id": str(getattr(backtest, "agent_id", "") or "") or None,
        "exchange": getattr(backtest, "exchange", None),
        "symbols": list(getattr(backtest, "symbols", None) or []),
        "interval": interval_obj.value if interval_obj else "15m",
        "start_time": getattr(backtest, "start_time", None),
        "end_time": getattr(backtest, "end_time", None),
        "initial_capital": getattr(backtest, "initial_capital", None),
        "maker_fee": (
            getattr(backtest, "maker_fee", None)
            if getattr(backtest, "maker_fee", None) is not None
            else Decimal("0.1")
        ),
        "taker_fee": (
            getattr(backtest, "taker_fee", None)
            if getattr(backtest, "taker_fee", None) is not None
            else Decimal("0.1")
        ),
        "slippage": (
            getattr(backtest, "slippage", None)
            if getattr(backtest, "slippage", None) is not None
            else Decimal("0.05")
        ),
        "strategy_config": dict(getattr(backtest, "strategy_config", None) or {}),
    }


async def _build_managed_llm_for_backtest(
    session: AsyncSession,
    user_id: str,
    agent_id: Optional[str],
    strategy_config: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[BaseLLM], Optional[int], Optional[str]]:
    """
    构造回测决策 LLM。

    优先级：策略 decisionLlmModelId → Agent.llm_model_id → strategy_config.llm 环境变量。
    """
    agent_llm_model_id = None
    if agent_id:
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        agent_llm_model_id = agent.llm_model_id if agent else None

    # 回测必须在模型实例创建之前锁定温度；之后修改 strategy_config.llm
    # 无法影响已经注入的 managed LLM。
    temperature = 0.0
    llm, model_id, name = await build_decision_llm(
        session,
        strategy_config,
        agent_llm_model_id=agent_llm_model_id,
        temperature=temperature,
    )
    if model_id is not None and llm is not None:
        logger.info(
            f"回测 Agent 已使用决策 LLM: llm_model_id={model_id}, "
            f"display_name={name}, temperature={temperature}"
        )
    return llm, model_id, name


async def _decision_with_analysis_context(
    session: AsyncSession,
    user_id: str,
    strategy_config: dict,
    symbols: List[str],
    trading_agent,
    snapshot,
    account,
    risk_manager,
    analysis_context_cache: Optional[Dict[str, Any]] = None,
    perf_stats: Optional[Dict[str, Any]] = None,
    open_orders: Optional[List[Dict[str, Any]]] = None,
):
    """每次决策前构建分析/规则上下文，再交给交易决策 Agent。"""
    try:
        cfg = strategy_config or {}
        mode = resolve_decision_mode(cfg)

        logger.info(
            "回测决策链路追踪: "
            f"decisionMode={mode}, "
            f"strategy_llm={cfg.get('llm')}, "
            f"technicalAnalysisLlmModelId={cfg.get('technicalAnalysisLlmModelId')}, "
            f"symbols={symbols}, "
            f"ts={snapshot.timestamp.isoformat() if getattr(snapshot, 'timestamp', None) else None}"
        )

        context_started_at = time.perf_counter()
        if mode == "rule":
            ctx = build_rule_decision_context(snapshot, cfg, symbols or [])
        else:
            from app.v1.services.trading_analysis_context_service import build_trading_analysis_context

            ctx = await build_trading_analysis_context(
                session,
                user_id,
                cfg,
                symbols or [],
                as_of=snapshot.timestamp,
                runtime_cache=analysis_context_cache,
                market_snapshot=snapshot,
            )
            # 上下文查询完成后立即释放事务级 metadata lock；LLM 调用可能
            # 持续数十秒，等待模型期间不能占着数据库表的读锁。
            await session.rollback()
            # 活动挂单属于当前执行状态，必须每轮完整交给交易员管理。
            ctx["open_orders"] = list(open_orders or [])
        context_ms = (time.perf_counter() - context_started_at) * 1000
        decision_started_at = time.perf_counter()
        decision = await trading_agent.make_decision(
            snapshot, account, risk_manager, analysis_context=ctx, decision_mode=mode
        )
        if isinstance(decision, dict):
            decision["technical_analysis"] = (ctx.get("technical_text") or "").strip()
            decision["decision_analysis"] = (
                decision.get("decision_analysis")
                or decision.get("reason")
                or decision.get("reasoning")
                or ""
            )
        decision_ms = (time.perf_counter() - decision_started_at) * 1000
        total_ms = context_ms + decision_ms
        cache_meta = ctx.get("_cache_meta") if isinstance(ctx, dict) else None
        if perf_stats is not None:
            perf_stats["steps"] = perf_stats.get("steps", 0) + 1
            perf_stats["context_ms"] = perf_stats.get("context_ms", 0.0) + context_ms
            perf_stats["decision_ms"] = perf_stats.get("decision_ms", 0.0) + decision_ms
            perf_stats["total_ms"] = perf_stats.get("total_ms", 0.0) + total_ms
            if isinstance(cache_meta, dict):
                perf_stats["cache_hits"] = perf_stats.get("cache_hits", 0) + int(cache_meta.get("hits", 0))
                perf_stats["cache_misses"] = perf_stats.get("cache_misses", 0) + int(cache_meta.get("misses", 0))
                perf_stats["cache_generations"] = perf_stats.get("cache_generations", 0) + int(cache_meta.get("generated", 0))
        if total_ms >= 500 or (isinstance(cache_meta, dict) and cache_meta.get("generated")):
            logger.info(
                "回测决策耗时: "
                f"ts={snapshot.timestamp.isoformat()}, "
                f"context={context_ms:.1f}ms, decision={decision_ms:.1f}ms, total={total_ms:.1f}ms, "
                f"cache_hits={cache_meta.get('hits', 0) if isinstance(cache_meta, dict) else 0}, "
                f"cache_misses={cache_meta.get('misses', 0) if isinstance(cache_meta, dict) else 0}, "
                f"generated={cache_meta.get('generated', 0) if isinstance(cache_meta, dict) else 0}"
            )
        return decision
    except asyncio.CancelledError:
        # wait_for 超时取消不会走 Exception 分支；必须 rollback，否则后续 8s2b/xd2s
        try:
            await session.rollback()
        except Exception as rb_err:
            logger.warning(f"回测决策取消后 session.rollback 异常: {rb_err}")
        raise
    except Exception:
        # 任一步失败若已触达 DB，会话会处于 invalid；不 rollback 则后续 progress/查询持续报 8s2b
        try:
            await session.rollback()
        except Exception as rb_err:
            logger.warning(f"回测决策失败后 session.rollback 异常: {rb_err}")
        raise


def _compute_kline_fetch_start(start_time: datetime, interval: str) -> datetime:
    """
    计算 K 线拉取的起始时间（向前扩展 lookback）
    回测仍只模拟 [start_time, end_time]，但需要更早的数据：
    - 指标预热（MA20/MACD 等）
    - 决策 LLM 多周期 K 线（15m/1h/4h）聚合上下文
    """
    return kline_context_start(start_time, interval)


def _kline_query_limit(start_time: datetime, end_time: datetime, interval: str) -> int:
    """避免 1m 等高频周期被默认 10000 条截断，确保完整加载决策上下文。"""
    seconds = _get_interval_seconds(interval)
    expected_rows = int((end_time - start_time).total_seconds() / seconds) + 2
    return max(10000, expected_rows)


def _trade_to_db_row(backtest_id: str, trade) -> Dict[str, Any]:
    """将引擎内存成交转为 DB 写入结构。"""
    return {
        'id': trade.id,
        'backtest_id': backtest_id,
        'timestamp': trade.timestamp,
        'symbol': trade.symbol,
        'side': trade.side,
        'trade_type': trade.trade_type,
        'action': getattr(trade, 'action', None),
        'leverage': getattr(trade, 'leverage', 1),
        'margin_used': (
            trade.amount / getattr(trade, 'leverage', Decimal('1'))
            if getattr(trade, 'leverage', Decimal('1')) else trade.amount
        ),
        'price': trade.price,
        'quantity': trade.quantity,
        'amount': trade.amount,
        'fee': trade.fee,
        'pnl': trade.pnl,
        'pnl_percent': trade.pnl_percent,
        'balance': trade.balance,
        'reasoning': trade.reasoning,
        'signals': trade.signals,
        'chain_of_thought': trade.chain_of_thought,
    }


def _decision_to_db_row(backtest_id: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    """将引擎内存决策转为包含完整审计内容的 DB 写入结构。"""
    return {
        'id': decision.get('id'),
        'backtest_id': backtest_id,
        'timestamp': decision.get('timestamp'),
        'action': decision.get('action', 'hold'),
        'symbol': decision.get('symbol'),
        'quantity': decision.get('quantity'),
        'reasoning': decision.get('reasoning') or decision.get('reason', ''),
        'decision_analysis': (
            decision.get('decision_analysis')
            or decision.get('reasoning')
            or decision.get('reason', '')
        ),
        'technical_analysis': decision.get('technical_analysis') or '',
        'chain_of_thought': _decision_chain_with_audit(decision),
        'reference_price': decision.get('current_price'),
        'execution_result': decision.get('execution_result'),
    }


async def _persist_new_trades(
    session: AsyncSession,
    backtest_id: str,
    trades: List,
    persisted_count: List[int],
) -> int:
    """
    增量写入尚未落库的交易记录。
    返回「若本事务成功提交后」应更新的已落库条数；调用方须在 commit 成功后再写回 persisted_count。

    若进度回调已成功写入，但内存计数因回滚/超时未推进，会先按已存在 id 对齐起点，避免重复 INSERT。
    """
    if not trades:
        return 0

    # 与 DB 对齐：找出内存成交列表中前缀已落库的长度
    trade_ids = [getattr(t, "id", None) for t in trades]
    trade_ids = [str(i) for i in trade_ids if i]
    if trade_ids:
        existing_ids = await get_existing_backtest_trade_ids(session, trade_ids)
        aligned = 0
        for t in trades:
            tid = getattr(t, "id", None)
            if tid and str(tid) in existing_ids:
                aligned += 1
            else:
                break
        if aligned > persisted_count[0]:
            logger.info(
                f"回测成交计数与 DB 对齐: backtest_id={backtest_id}, "
                f"mem={persisted_count[0]} -> db_prefix={aligned}"
            )
            persisted_count[0] = aligned

    start = persisted_count[0]
    if start >= len(trades):
        return start
    rows = [_trade_to_db_row(backtest_id, t) for t in trades[start:]]
    if rows:
        await batch_create_backtest_trades(session, rows)
    return len(trades)


async def _persist_new_decisions(
    session: AsyncSession,
    backtest_id: str,
    decisions: List[Dict[str, Any]],
    persisted_count: List[int],
) -> int:
    """增量写入完整决策详情，供 /decisions 按需查询。"""
    if not decisions:
        return 0

    for decision in decisions:
        decision.setdefault('id', str(uuid.uuid4()))
    decision_ids = [str(d.get('id') or '') for d in decisions if d.get('id')]
    if decision_ids:
        existing_ids = await get_existing_backtest_decision_ids(session, decision_ids)
        aligned = 0
        for decision in decisions:
            decision_id = decision.get('id')
            if decision_id and str(decision_id) in existing_ids:
                aligned += 1
            else:
                break
        if aligned > persisted_count[0]:
            persisted_count[0] = aligned

    start = persisted_count[0]
    if start >= len(decisions):
        return start
    rows = [
        _decision_to_db_row(backtest_id, decision)
        for decision in decisions[start:]
    ]
    await batch_create_backtest_decisions(session, rows)
    return len(decisions)


def _engine_progress_snapshot(
    current_time: datetime,
    message: str,
    detail: Optional[Dict[str, Any]] = None,
    live_preview: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """写入 backtest_tasks.progress_snapshot，供进度接口与前端展示。"""
    snap: Dict[str, Any] = {
        "currentTime": current_time.isoformat(),
        "message": message,
        "heartbeatAt": datetime.now().isoformat(),
        "leaseExpiresAt": (datetime.now() + timedelta(seconds=BACKTEST_LEASE_SECONDS)).isoformat(),
        "workerId": BACKTEST_WORKER_ID,
    }
    if detail:
        if detail.get("currentStep") is not None:
            snap["currentStep"] = detail["currentStep"]
        if detail.get("totalSteps") is not None:
            snap["totalSteps"] = detail["totalSteps"]
        if detail.get("intervalSeconds") is not None:
            snap["intervalSeconds"] = detail["intervalSeconds"]
    if live_preview is not None:
        snap["livePreview"] = live_preview
    return snap


async def _write_progress_with_isolated_session(
    bind,
    backtest_id: str,
    progress: int,
    current_time: datetime,
    message: str,
    detail: Optional[Dict[str, Any]],
    engine_ref: Dict[str, Any],
    persisted_trade_count: List[int],
    persisted_decision_count: List[int],
) -> bool:
    """
    用独立 session 写进度，避免与决策共用会话。

    进度回调会被引擎 asyncio.wait_for 超时取消；若取消时打在主 session 上，
    会留下 invalid transaction，后续决策持续 8s2b / greenlet xd2s。
    """
    maker = async_sessionmaker(
        bind=bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with maker() as progress_session:
        pending_trade_count = persisted_trade_count[0]
        pending_decision_count = persisted_decision_count[0]
        try:
            task_row = await get_backtest_by_id(progress_session, backtest_id)
            if task_row is None or task_row.status == BacktestStatus.CANCELLED:
                raise asyncio.CancelledError()
            eng = engine_ref.get("engine")
            live_preview = None
            if eng is not None:
                pending_trade_count = await _persist_new_trades(
                    progress_session,
                    backtest_id,
                    eng.account.trades,
                    persisted_trade_count,
                )
                pending_decision_count = await _persist_new_decisions(
                    progress_session,
                    backtest_id,
                    eng.decision_log,
                    persisted_decision_count,
                )
                live_preview = eng.build_live_preview()
            snapshot = _engine_progress_snapshot(
                current_time, message, detail, live_preview=live_preview
            )
            updated = await update_backtest_status(
                progress_session,
                backtest_id,
                BacktestStatus.RUNNING,
                progress=progress,
                progress_snapshot=snapshot,
            )
            if updated is None or updated.status != BacktestStatus.RUNNING:
                raise asyncio.CancelledError()
            await progress_session.commit()
            # 仅在事务真正提交后推进计数，避免回滚后重复 INSERT 撞主键
            persisted_trade_count[0] = pending_trade_count
            persisted_decision_count[0] = pending_decision_count
            return True
        except asyncio.CancelledError:
            try:
                await progress_session.rollback()
            except Exception:
                pass
            raise
        except Exception as pe:
            logger.warning(f"回测进度更新失败: {pe}")
            try:
                await progress_session.rollback()
            except Exception:
                pass
            return False


async def _backtest_lease_heartbeat(bind, backtest_id: str) -> None:
    """独立于 K 线/LLM 执行周期续租，慢调用期间也不会被 watchdog 误回收。"""
    maker = async_sessionmaker(
        bind=bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    interval = max(10.0, min(60.0, BACKTEST_LEASE_SECONDS / 3))
    while True:
        await asyncio.sleep(interval)
        try:
            async with maker() as heartbeat_session:
                renewed = await renew_backtest_lease(heartbeat_session, backtest_id)
                await heartbeat_session.commit()
            if not renewed:
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"回测任务续租失败: backtest_id={backtest_id}, error={exc}")


async def _backtest_cancellation_watch(
    bind,
    backtest_id: str,
    owner_task: asyncio.Task,
) -> None:
    """跨进程监听数据库取消终态，并取消本 worker 中的实际执行协程。"""
    maker = async_sessionmaker(
        bind=bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    while True:
        await asyncio.sleep(BACKTEST_CANCEL_POLL_SECONDS)
        try:
            async with maker() as watch_session:
                row = await get_backtest_by_id(watch_session, backtest_id)
                if row is None or row.status == BacktestStatus.CANCELLED:
                    if not owner_task.done():
                        owner_task.cancel()
                    return
                if row.status in (BacktestStatus.COMPLETED, BacktestStatus.FAILED):
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                f"回测取消状态检查失败: backtest_id={backtest_id}, error={exc}"
            )


def _log_decision_perf_summary(backtest_id: str, perf_stats: Dict[str, Any]) -> None:
    """输出回测决策链路平均耗时与缓存命中概况。"""
    steps = int(perf_stats.get("steps") or 0)
    if steps <= 0:
        return
    logger.info(
        "回测决策汇总: "
        f"backtest_id={backtest_id}, steps={steps}, "
        f"avg_context={perf_stats.get('context_ms', 0.0) / steps:.2f}ms, "
        f"avg_decision={perf_stats.get('decision_ms', 0.0) / steps:.2f}ms, "
        f"avg_total={perf_stats.get('total_ms', 0.0) / steps:.2f}ms, "
        f"cache_hits={int(perf_stats.get('cache_hits', 0))}, "
        f"cache_misses={int(perf_stats.get('cache_misses', 0))}, "
        f"generated={int(perf_stats.get('cache_generations', 0))}"
    )


def _decision_chain_with_audit(decision: Dict[str, Any]) -> List[Dict[str, Any]]:
    chain = list(decision.get("chain_of_thought") or [])
    if decision.get("action") == "system_error":
        chain.append(
            {
                "type": "system_error",
                "errorType": decision.get("error_type") or "unknown_system_error",
                "signals": decision.get("signals") or [],
            }
        )
    audit_payload = {
        "type": "llm_audit",
        "decisionPrompt": decision.get("decision_prompt") or "",
        "llmRawResponse": decision.get("llm_raw_response") or "",
        "parsedDecision": decision.get("parsed_decision") or "",
        "llmMetadata": decision.get("llm_metadata") or {},
    }
    if any(
        [
            audit_payload["decisionPrompt"],
            audit_payload["llmRawResponse"],
            audit_payload["parsedDecision"],
            audit_payload["llmMetadata"],
        ]
    ):
        chain.append(audit_payload)

    if decision.get("decision_mode") == "rule" or decision.get("rule_hits"):
        chain.append(
            {
                "type": "rule_audit",
                "decisionMode": decision.get("decision_mode") or "rule",
                "regime": decision.get("regime"),
                "ruleHits": decision.get("rule_hits") or [],
                "signals": decision.get("signals") or [],
                "indicatorsSnapshot": decision.get("indicators_snapshot") or {},
            }
        )
    return chain


class BacktestRunner:
    """回测任务执行器"""
    
    def __init__(self, session_factory):
        """
        初始化执行器
        
        Args:
            session_factory: 数据库 session 工厂
        """
        self.session_factory = session_factory
        self.running_tasks: Dict[str, asyncio.Task] = {}
    
    async def run_backtest(self, backtest_id: str):
        """
        执行回测任务
        
        Args:
            backtest_id: 回测任务 ID
        """
        async with self.session_factory() as session:
            lease_task: Optional[asyncio.Task] = None
            cancel_watch_task: Optional[asyncio.Task] = None
            try:
                # 获取回测任务
                backtest = await get_backtest_by_id(session, backtest_id)
                if not backtest:
                    logger.error(f"回测任务不存在: {backtest_id}")
                    return
                if backtest.status == BacktestStatus.CANCELLED:
                    logger.info(f"回测任务启动前已取消: {backtest_id}")
                    return
                backtest_runtime = _freeze_backtest_runtime(backtest)
                
                # 更新状态为运行中
                claimed = await update_backtest_status(
                    session, backtest_id,
                    BacktestStatus.RUNNING,
                    progress=0
                )
                await session.commit()
                if claimed is None or claimed.status != BacktestStatus.RUNNING:
                    logger.info(f"回测任务未取得执行权，终止启动: {backtest_id}")
                    return
                lease_task = asyncio.create_task(
                    _backtest_lease_heartbeat(session.bind, backtest_id)
                )
                cancel_watch_task = asyncio.create_task(
                    _backtest_cancellation_watch(
                        session.bind,
                        backtest_id,
                        asyncio.current_task(),
                    )
                )
                
                logger.info(f"开始执行回测: {backtest_id}, 名称: {backtest_runtime['name']}")
                
                strategy_config = expand_strategy_config_for_backtest(
                    backtest_runtime["strategy_config"],
                    interval=backtest_runtime["interval"],
                )
                # 注入与成交侧一致的费率，供决策 prompt 成本公式使用（单位 %）
                strategy_config.setdefault("makerFee", float(backtest_runtime["maker_fee"]))
                strategy_config.setdefault("takerFee", float(backtest_runtime["taker_fee"]))
                strategy_config.setdefault("slippage", float(backtest_runtime["slippage"]))
                # 回测默认多给一次解析重试，降低偶发 JSON 失败污染结果
                strategy_config.setdefault("llmParseRetries", 2)
                runtime_tuning = _get_runtime_tuning(strategy_config)
                logger.info(
                    f"回测策略(含推导): leverage={strategy_config.get('leverage')}, "
                    f"maxPositionRatio={strategy_config.get('maxPositionRatio')}, "
                    f"execTf={strategy_config.get('technicalAnalysisTimeframe')}, "
                    f"analysisTf={strategy_config.get('analysisTimeframe')}"
                )
                
                # 构建回测配置
                config = BacktestConfig(
                    start_time=backtest_runtime["start_time"],
                    end_time=backtest_runtime["end_time"],
                    initial_capital=backtest_runtime["initial_capital"],
                    symbols=backtest_runtime["symbols"],
                    interval=backtest_runtime["interval"],
                    maker_fee=backtest_runtime["maker_fee"],
                    taker_fee=backtest_runtime["taker_fee"],
                    slippage=backtest_runtime["slippage"],
                    market_impact_bps=Decimal(str(strategy_config.get("marketImpactBps", 2.0))),
                    impact_volatility_weight=Decimal(str(strategy_config.get("impactVolatilityWeight", 0.10))),
                    max_impact_pct=Decimal(str(strategy_config.get("maxImpactPct", 0.25))),
                    max_participation_rate=Decimal(str(strategy_config.get("maxParticipationRate", 5.0))),
                    funding_rate_per_interval=Decimal(str(strategy_config.get("fundingRatePerInterval", 0.0))),
                    funding_interval_hours=int(strategy_config.get("fundingIntervalHours", 8)),
                    strategy_config=strategy_config,
                    **runtime_tuning,
                )
                
                # 进度写入 DB：进一步限制提交频率，避免高频 commit 拖慢回测
                _last_pb = [0]
                _last_commit_mono = [0.0]
                _persisted_trade_count = [0]
                _persisted_decision_count = [0]
                engine_ref: Dict[str, Any] = {}
                decision_perf_stats: Dict[str, Any] = {}

                async def progress_callback(
                    progress: int,
                    current_time: datetime,
                    message: str,
                    detail: Optional[Dict[str, Any]] = None,
                ):
                    now_m = time.monotonic()
                    if (
                        progress < 100
                        and (now_m - _last_commit_mono[0]) < PROGRESS_COMMIT_MIN_INTERVAL_SECONDS
                        and (progress - _last_pb[0]) < PROGRESS_COMMIT_MIN_PROGRESS_STEP
                    ):
                        return
                    ok = await _write_progress_with_isolated_session(
                        session.bind,
                        backtest_id,
                        progress,
                        current_time,
                        message,
                        detail,
                        engine_ref,
                        _persisted_trade_count,
                        _persisted_decision_count,
                    )
                    if ok:
                        _last_pb[0] = progress
                        _last_commit_mono[0] = now_m
                
                # 判断决策模式
                decision_mode = resolve_decision_mode(strategy_config)
                use_trader = decision_mode == "trader"

                managed_llm: Optional[BaseLLM] = None
                managed_llm_model_id: Optional[int] = None
                managed_llm_model_name: Optional[str] = None
                if backtest_runtime["agent_id"]:
                    managed_llm, managed_llm_model_id, managed_llm_model_name = await _build_managed_llm_for_backtest(
                        session,
                        backtest_runtime["user_id"],
                        backtest_runtime["agent_id"],
                        strategy_config,
                    )
                    if (
                        managed_llm_model_id is not None
                        and not strategy_config.get("technicalAnalysisLlmModelId")
                    ):
                        strategy_config["technicalAnalysisLlmModelId"] = managed_llm_model_id
                    logger.info(
                        "回测链路追踪: 已将 technicalAnalysisLlmModelId 回填为 "
                        f"{managed_llm_model_id}"
                    )
                    if use_trader and managed_llm_model_id is not None and managed_llm is None:
                        raise ValueError(
                            f"回测 Agent 绑定的模型(id={managed_llm_model_id})加载失败，"
                            "已阻止回退到默认 DeepSeek，请检查模型管理中的 API 配置"
                        )

                strategy_config["_managedDecisionLlmModelId"] = managed_llm_model_id
                strategy_config["_managedDecisionLlmModelName"] = managed_llm_model_name
                strategy_config["decisionLlmTemperature"] = 0.0
                strategy_config["technicalAnalysisTemperature"] = 0.0

                if use_trader and managed_llm is None and 'llm' not in strategy_config:
                    strategy_config['llm'] = {
                        'model': 'deepseek-chat',
                        'apiKeyEnv': 'DEEPSEEK_API_KEY',
                        'temperature': 0.0
                    }
                elif use_trader and isinstance(strategy_config.get("llm"), dict):
                    strategy_config["llm"]["temperature"] = 0.0

                # 创建回测交易 Agent
                trading_agent = BacktestTradingAgent(
                    agent_id=backtest_runtime["agent_id"],
                    agent_name=f"回测-{backtest_runtime['name']}",
                    llm=managed_llm,
                    strategy_config=strategy_config,
                )
                logger.info(
                    "回测链路追踪: BacktestTradingAgent 已创建, "
                    f"llm_injected={managed_llm is not None}, "
                    f"llm_class={managed_llm.__class__.__name__ if managed_llm else None}, "
                    f"llm_api_url={getattr(managed_llm, 'api_url', None) if managed_llm else None}, "
                    f"strategy_llm={strategy_config.get('llm')}, "
                    f"technicalAnalysisLlmModelId={strategy_config.get('technicalAnalysisLlmModelId')}"
                )
                from app.v1.services.trading_analysis_context_service import (
                    prepare_backtest_analysis_context_cache,
                )
                analysis_context_cache: Optional[Dict[str, Any]] = None
                if decision_mode == "trader":
                    analysis_context_cache = await prepare_backtest_analysis_context_cache(
                        session,
                        backtest_runtime["user_id"],
                        strategy_config,
                        backtest_runtime["symbols"],
                    )
                
                # 创建决策回调（可选注入消息面/技术面）
                async def decision_callback(snapshot, account, risk_manager):
                    engine = engine_ref.get("engine")
                    return await _decision_with_analysis_context(
                        session,
                        backtest_runtime["user_id"],
                        strategy_config,
                        backtest_runtime["symbols"],
                        trading_agent,
                        snapshot,
                        account,
                        risk_manager,
                        analysis_context_cache=analysis_context_cache,
                        perf_stats=decision_perf_stats,
                        open_orders=(
                            engine.active_orders_snapshot(
                                as_of=snapshot.timestamp,
                                prices=snapshot.prices,
                            ) if engine is not None else []
                        ),
                    )
                
                # 创建回测引擎
                engine = BacktestEngine(
                    config=config,
                    decision_callback=decision_callback,
                    progress_callback=progress_callback
                )
                engine_ref["engine"] = engine
                
                # 先补全 MySQL 历史 K 线缓存，再加载（与 run_backtest_task 一致）
                interval_str = backtest_runtime["interval"]
                fetch_start = _compute_kline_fetch_start(backtest_runtime["start_time"], interval_str)
                try:
                    from backtest.kline_fetcher import ensure_kline_data
                    await ensure_kline_data(
                        session=session,
                        exchange=backtest_runtime["exchange"],
                        symbols=backtest_runtime["symbols"],
                        interval=interval_str,
                        start_time=fetch_start,
                        end_time=backtest_runtime["end_time"],
                    )
                except Exception as e:
                    logger.warning(
                        f"补全 K 线缓存失败: {e}，将校验库内真实数据；"
                        "数据不足时回测直接失败"
                    )
                
                # 加载 K 线数据
                await self._load_kline_data(session, engine, backtest_runtime)

                # 引擎运行只使用内存 K 线，释放准备阶段的只读事务。
                await session.rollback()
                
                # 执行回测
                from backtest.llm_replay_cache import activate_replay_cache

                cache_mode = str(strategy_config.get("llmCacheMode") or "fresh").lower()
                cache_context = (
                    activate_replay_cache(
                        strategy_config.get("llmReplayCachePath"), mode="record"
                    )
                    if cache_mode == "record"
                    else nullcontext(None)
                )
                logger.info(f"回测 LLM 响应处理模式: {cache_mode}")
                with cache_context as replay_cache:
                    result = await engine.run()
                from backtest.experiment_manifest import build_experiment_manifest

                result.statistics["experimentMetadata"] = build_experiment_manifest(
                    engine,
                    strategy_config,
                    managed_llm or getattr(trading_agent, "llm", None),
                    replay_cache,
                )
                _log_decision_perf_summary(backtest_id, decision_perf_stats)
                
                # 保存结果
                await self._save_result(
                    session,
                    backtest_id,
                    result,
                    _persisted_trade_count[0],
                    _persisted_decision_count[0],
                )
                
                # 更新状态为完成
                completed = await update_backtest_result(
                    session, backtest_id,
                    result.statistics
                )
                await session.commit()
                if completed is None or completed.status != BacktestStatus.COMPLETED:
                    logger.info(f"回测完成结果因任务已取消而未覆盖状态: {backtest_id}")
                    return
                logger.info(f"回测完成: {backtest_id}, 总收益: {result.statistics.get('totalReturn', 0):.2f}%")
                
            except asyncio.CancelledError:
                logger.info(f"回测任务被取消: {backtest_id}")
                try:
                    await session.rollback()
                    current = await get_backtest_by_id(session, backtest_id)
                    if current is not None and current.status != BacktestStatus.CANCELLED:
                        await update_backtest_status(
                            session, backtest_id,
                            BacktestStatus.CANCELLED,
                            error_message="用户手动停止",
                        )
                    await session.commit()
                except Exception as cancel_err:
                    logger.warning(f"保存回测取消状态失败: {backtest_id}, error={cancel_err}")

            except Exception as e:
                logger.error(f"回测执行失败: {backtest_id}, 错误: {e}")
                try:
                    await session.rollback()
                except Exception as rb_err:
                    logger.warning(f"回测失败后 session.rollback 异常: {rb_err}")
                await update_backtest_status(
                    session, backtest_id,
                    BacktestStatus.FAILED,
                    error_message=str(e)
                )
                await session.commit()
            finally:
                if cancel_watch_task is not None:
                    cancel_watch_task.cancel()
                    try:
                        await cancel_watch_task
                    except asyncio.CancelledError:
                        pass
                if lease_task is not None:
                    lease_task.cancel()
                    try:
                        await lease_task
                    except asyncio.CancelledError:
                        pass
    
    async def _load_kline_data(
        self,
        session: AsyncSession,
        engine: BacktestEngine,
        backtest_runtime: Dict[str, Any]
    ):
        """加载 K 线数据（含 lookback 预热数据，供 MA20/MACD 等指标计算）"""
        interval_str = backtest_runtime["interval"]
        fetch_start = _compute_kline_fetch_start(backtest_runtime["start_time"], interval_str)
        for symbol in backtest_runtime["symbols"]:
            # 从数据库获取 K 线（扩展起始时间以包含预热数据）
            klines = await get_klines(
                session,
                exchange=backtest_runtime["exchange"],
                symbol=symbol,
                interval=interval_str,
                start_time=fetch_start,
                end_time=backtest_runtime["end_time"],
                limit=_kline_query_limit(
                    fetch_start, backtest_runtime["end_time"], interval_str
                ),
            )
            
            if klines:
                _validate_real_kline_coverage(
                    klines,
                    symbol=symbol,
                    interval=interval_str,
                    start_time=backtest_runtime["start_time"],
                    end_time=backtest_runtime["end_time"],
                )
                # 转换为引擎使用的格式
                kline_data = [
                    KlineData(
                        timestamp=k.timestamp,
                        open=k.open_price,
                        high=k.high_price,
                        low=k.low_price,
                        close=k.close_price,
                        volume=k.volume,
                        quote_volume=k.quote_volume
                    )
                    for k in klines
                ]
                engine.load_klines(symbol, kline_data)
                logger.info(
                    f"加载 {symbol} K线数据: {len(kline_data)} 条"
                    f"（含 {_lookback_bars(interval_str)} 根 lookback / "
                    f"{KLINE_CONTEXT_LOOKBACK_DAYS} 天）"
                )
            else:
                raise MissingHistoricalKlineError(
                    f"{symbol} {interval_str} 在回测区间没有真实 K 线，"
                    "正式回测禁止回退到模拟数据"
                )
    
    async def _save_result(
        self,
        session: AsyncSession,
        backtest_id: str,
        result,
        persisted_trade_count: int = 0,
        persisted_decision_count: int = 0,
    ):
        """保存回测结果到数据库"""
        # 保存尚未落库的交易记录
        if result.trades and persisted_trade_count < len(result.trades):
            trades_data = [
                _trade_to_db_row(backtest_id, t)
                for t in result.trades[persisted_trade_count:]
            ]
            await batch_create_backtest_trades(session, trades_data)
        
        # 保存权益曲线
        if result.equity_curve:
            equity_data = []
            for i, eq in enumerate(result.equity_curve):
                benchmark = None
                if i < len(result.benchmark_curve):
                    benchmark = result.benchmark_curve[i].get('value')
                
                drawdown = Decimal('0')
                if i < len(result.drawdown_curve):
                    drawdown = Decimal(str(result.drawdown_curve[i].get('value', 0)))
                
                equity_data.append({
                    'backtest_id': backtest_id,
                    'timestamp': datetime.fromisoformat(eq['time']),
                    'equity': eq['value'],
                    'drawdown': drawdown,
                    'benchmark': benchmark,
                    'unrealized_pnl': eq.get('unrealizedPnl'),
                    'unrealized_pnl_rate': eq.get('unrealizedPnlRate'),
                })
            
            await batch_create_backtest_equity(session, equity_data)

        # 保存决策记录（每次决策含 hold）
        if (
            getattr(result, 'decision_log', None)
            and persisted_decision_count < len(result.decision_log)
        ):
            decisions_data = [
                _decision_to_db_row(backtest_id, d)
                for d in result.decision_log[persisted_decision_count:]
            ]
            await batch_create_backtest_decisions(session, decisions_data)
    
    def start_backtest(self, backtest_id: str) -> asyncio.Task:
        """
        启动回测任务（非阻塞）
        
        Args:
            backtest_id: 回测任务 ID
            
        Returns:
            asyncio.Task
        """
        task = asyncio.create_task(self.run_backtest(backtest_id))
        self.running_tasks[backtest_id] = task
        return task
    
    def cancel_backtest(self, backtest_id: str) -> bool:
        """
        取消回测任务
        
        Args:
            backtest_id: 回测任务 ID
            
        Returns:
            是否成功取消
        """
        task = self.running_tasks.get(backtest_id)
        if task and not task.done():
            task.cancel()
            return True
        return False
    
    def is_running(self, backtest_id: str) -> bool:
        """检查回测任务是否在运行"""
        task = self.running_tasks.get(backtest_id)
        return task is not None and not task.done()


# 全局实例
_runner: Optional[BacktestRunner] = None


def get_backtest_runner(session_factory) -> BacktestRunner:
    """获取回测执行器实例"""
    global _runner
    if _runner is None:
        _runner = BacktestRunner(session_factory)
    return _runner


async def run_backtest_task(backtest_id: str, db):
    """
    独立的回测任务执行函数，用于 BackgroundTasks
    
    Args:
        backtest_id: 回测任务 ID
        db: 数据库实例 (app.state.db)
    """
    async with db.get_session() as session:
        lease_task: Optional[asyncio.Task] = None
        cancel_watch_task: Optional[asyncio.Task] = None
        try:
            # 获取回测任务
            backtest = await get_backtest_by_id(session, backtest_id)
            if not backtest:
                logger.error(f"回测任务不存在: {backtest_id}")
                return
            if backtest.status == BacktestStatus.CANCELLED:
                logger.info(f"回测任务启动前已取消: {backtest_id}")
                return
            backtest_runtime = _freeze_backtest_runtime(backtest)
            
            # 更新状态为运行中
            claimed = await update_backtest_status(
                session, backtest_id,
                BacktestStatus.RUNNING,
                progress=0
            )
            await session.commit()
            if claimed is None or claimed.status != BacktestStatus.RUNNING:
                logger.info(f"回测任务未取得执行权，终止启动: {backtest_id}")
                return
            lease_task = asyncio.create_task(
                _backtest_lease_heartbeat(session.bind, backtest_id)
            )
            cancel_watch_task = asyncio.create_task(
                _backtest_cancellation_watch(
                    session.bind,
                    backtest_id,
                    asyncio.current_task(),
                )
            )
            
            logger.info(f"开始执行回测: {backtest_id}, 名称: {backtest_runtime['name']}")
            
            strategy_config = expand_strategy_config_for_backtest(
                backtest_runtime["strategy_config"],
                interval=backtest_runtime["interval"],
            )
            # 注入与成交侧一致的费率，供决策 prompt 成本公式使用（单位 %）
            strategy_config.setdefault("makerFee", float(backtest_runtime["maker_fee"]))
            strategy_config.setdefault("takerFee", float(backtest_runtime["taker_fee"]))
            strategy_config.setdefault("slippage", float(backtest_runtime["slippage"]))
            # 回测默认多给一次解析重试，降低偶发 JSON 失败污染结果
            strategy_config.setdefault("llmParseRetries", 2)
            runtime_tuning = _get_runtime_tuning(strategy_config)
            logger.info(
                f"回测策略(含推导): leverage={strategy_config.get('leverage')}, "
                f"maxPositionRatio={strategy_config.get('maxPositionRatio')}, "
                f"execTf={strategy_config.get('technicalAnalysisTimeframe')}, "
                f"analysisTf={strategy_config.get('analysisTimeframe')}"
            )
            
            # 构建回测配置
            config = BacktestConfig(
                start_time=backtest_runtime["start_time"],
                end_time=backtest_runtime["end_time"],
                initial_capital=backtest_runtime["initial_capital"],
                symbols=backtest_runtime["symbols"],
                interval=backtest_runtime["interval"],
                maker_fee=backtest_runtime["maker_fee"],
                taker_fee=backtest_runtime["taker_fee"],
                slippage=backtest_runtime["slippage"],
                market_impact_bps=Decimal(str(strategy_config.get("marketImpactBps", 2.0))),
                impact_volatility_weight=Decimal(str(strategy_config.get("impactVolatilityWeight", 0.10))),
                max_impact_pct=Decimal(str(strategy_config.get("maxImpactPct", 0.25))),
                max_participation_rate=Decimal(str(strategy_config.get("maxParticipationRate", 5.0))),
                funding_rate_per_interval=Decimal(str(strategy_config.get("fundingRatePerInterval", 0.0))),
                funding_interval_hours=int(strategy_config.get("fundingIntervalHours", 8)),
                strategy_config=strategy_config,
                **runtime_tuning,
            )
            
            # 进度写入：进一步降频，减少运行中高频 commit 对回测速度的影响
            last_progress = 0
            last_commit_mono = 0.0
            _persisted_trade_count = [0]
            _persisted_decision_count = [0]
            engine_ref: Dict[str, Any] = {}
            decision_perf_stats: Dict[str, Any] = {}
            
            async def progress_callback(
                progress: int,
                current_time: datetime,
                message: str,
                detail: Optional[Dict[str, Any]] = None,
            ):
                nonlocal last_progress, last_commit_mono
                now_m = time.monotonic()
                if (
                    progress < 100
                    and (now_m - last_commit_mono) < PROGRESS_COMMIT_MIN_INTERVAL_SECONDS
                    and (progress - last_progress) < PROGRESS_COMMIT_MIN_PROGRESS_STEP
                ):
                    return
                ok = await _write_progress_with_isolated_session(
                    session.bind,
                    backtest_id,
                    progress,
                    current_time,
                    message,
                    detail,
                    engine_ref,
                    _persisted_trade_count,
                    _persisted_decision_count,
                )
                if ok:
                    last_progress = progress
                    last_commit_mono = now_m
            
            # 判断决策模式
            decision_mode = resolve_decision_mode(strategy_config)
            use_trader = decision_mode == "trader"
            
            logger.info(f"策略配置: {strategy_config}")
            logger.info(f"decisionMode: {decision_mode}")
            
            if backtest_runtime["agent_id"]:
                logger.info(f"回测关联 Agent: {backtest_runtime['agent_id']}")

            managed_llm: Optional[BaseLLM] = None
            managed_llm_model_id: Optional[int] = None
            managed_llm_model_name: Optional[str] = None
            if backtest_runtime["agent_id"]:
                managed_llm, managed_llm_model_id, managed_llm_model_name = await _build_managed_llm_for_backtest(
                    session,
                    backtest_runtime["user_id"],
                    backtest_runtime["agent_id"],
                    strategy_config,
                )
                if (
                    managed_llm_model_id is not None
                    and not strategy_config.get("technicalAnalysisLlmModelId")
                ):
                    # 技术面自动补算时默认复用交易 Agent 绑定的模型管理配置，
                    # 避免决策走第三方网关、技术分析却回退到官方 DeepSeek。
                    strategy_config["technicalAnalysisLlmModelId"] = managed_llm_model_id
                    logger.info(
                        "回测链路追踪: 已将 technicalAnalysisLlmModelId 回填为 "
                        f"{managed_llm_model_id}"
                    )

            if use_trader and managed_llm_model_id is not None and managed_llm is None:
                raise ValueError(
                    f"回测 Agent 绑定的模型(id={managed_llm_model_id})加载失败，"
                    "已阻止回退到默认 DeepSeek，请检查模型管理中的 API 配置"
                )

            strategy_config["_managedDecisionLlmModelId"] = managed_llm_model_id
            strategy_config["_managedDecisionLlmModelName"] = managed_llm_model_name
            strategy_config["decisionLlmTemperature"] = 0.0
            strategy_config["technicalAnalysisTemperature"] = 0.0

            if use_trader and managed_llm is None and 'llm' not in strategy_config:
                # 如果没有 LLM 配置，使用默认配置
                strategy_config['llm'] = {
                    'model': 'deepseek-chat',
                    'apiKeyEnv': 'DEEPSEEK_API_KEY',
                    'temperature': 0.0
                }
            elif use_trader and isinstance(strategy_config.get("llm"), dict):
                strategy_config["llm"]["temperature"] = 0.0
            
            # 创建回测交易 Agent
            trading_agent = BacktestTradingAgent(
                agent_id=backtest_runtime["agent_id"],
                agent_name=f"回测-{backtest_runtime['name']}",
                llm=managed_llm,
                strategy_config=strategy_config,
            )
            logger.info(
                "回测链路追踪: BacktestTradingAgent 已创建, "
                f"llm_injected={managed_llm is not None}, "
                f"llm_class={managed_llm.__class__.__name__ if managed_llm else None}, "
                f"llm_api_url={getattr(managed_llm, 'api_url', None) if managed_llm else None}, "
                f"strategy_llm={strategy_config.get('llm')}, "
                f"technicalAnalysisLlmModelId={strategy_config.get('technicalAnalysisLlmModelId')}"
            )
            from app.v1.services.trading_analysis_context_service import (
                prepare_backtest_analysis_context_cache,
            )
            analysis_context_cache: Optional[Dict[str, Any]] = None
            if decision_mode == "trader":
                analysis_context_cache = await prepare_backtest_analysis_context_cache(
                    session,
                    backtest_runtime["user_id"],
                    strategy_config,
                    backtest_runtime["symbols"],
                )
            
            # 创建决策回调（使用 Agent 的决策方法，可选消息面/技术面注入）
            async def agent_decision_callback(snapshot, account, risk_manager):
                engine = engine_ref.get("engine")
                return await _decision_with_analysis_context(
                    session,
                    backtest_runtime["user_id"],
                    strategy_config,
                    backtest_runtime["symbols"],
                    trading_agent,
                    snapshot,
                    account,
                    risk_manager,
                    analysis_context_cache=analysis_context_cache,
                    perf_stats=decision_perf_stats,
                    open_orders=(
                        engine.active_orders_snapshot(
                            as_of=snapshot.timestamp,
                            prices=snapshot.prices,
                        ) if engine is not None else []
                    ),
                )
            
            decision_callback = agent_decision_callback
            
            if decision_mode == "trader":
                logger.info("使用自主交易员模式 (BacktestTradingAgent)")
            else:
                logger.info("使用规则策略模式 (BacktestTradingAgent)")
            
            # 创建回测引擎
            engine = BacktestEngine(
                config=config,
                decision_callback=decision_callback,
                progress_callback=progress_callback
            )
            engine_ref["engine"] = engine
            
            # 尝试从交易所获取真实K线数据（含 lookback 预热）
            interval_str = backtest_runtime["interval"]
            fetch_start = _compute_kline_fetch_start(backtest_runtime["start_time"], interval_str)
            try:
                from backtest.kline_fetcher import ensure_kline_data
                logger.info(f"尝试从交易所获取历史数据...")
                await ensure_kline_data(
                    session=session,
                    exchange=backtest_runtime["exchange"],
                    symbols=backtest_runtime["symbols"],
                    interval=interval_str,
                    start_time=fetch_start,
                    end_time=backtest_runtime["end_time"]
                )
            except Exception as e:
                logger.warning(
                    f"获取交易所数据失败: {e}，将校验库内真实数据；"
                    "数据不足时回测直接失败"
                )
            
            # 加载 K 线数据（含 lookback）
            for symbol in backtest_runtime["symbols"]:
                klines = await get_klines(
                    session,
                    exchange=backtest_runtime["exchange"],
                    symbol=symbol,
                    interval=interval_str,
                    start_time=fetch_start,
                    end_time=backtest_runtime["end_time"],
                    limit=_kline_query_limit(
                        fetch_start, backtest_runtime["end_time"], interval_str
                    ),
                )
                
                if klines:
                    _validate_real_kline_coverage(
                        klines,
                        symbol=symbol,
                        interval=interval_str,
                        start_time=backtest_runtime["start_time"],
                        end_time=backtest_runtime["end_time"],
                    )
                    kline_data = [
                        KlineData(
                            timestamp=k.timestamp,
                            open=k.open_price,
                            high=k.high_price,
                            low=k.low_price,
                            close=k.close_price,
                            volume=k.volume,
                            quote_volume=k.quote_volume
                        )
                        for k in klines
                    ]
                    engine.load_klines(symbol, kline_data)
                    logger.info(
                        f"加载真实 {symbol} K线数据: {len(kline_data)} 条"
                        f"（含 {_lookback_bars(interval_str)} 根 lookback / "
                        f"{KLINE_CONTEXT_LOOKBACK_DAYS} 天）"
                    )
                else:
                    raise MissingHistoricalKlineError(
                        f"{symbol} {interval_str} 在回测区间没有真实 K 线，"
                        "正式回测禁止回退到模拟数据"
                    )

            # K 线和配置均已复制到内存，释放准备阶段的只读事务。
            await session.rollback()
            
            # 执行回测
            from backtest.llm_replay_cache import activate_replay_cache

            cache_mode = str(strategy_config.get("llmCacheMode") or "fresh").lower()
            cache_context = (
                activate_replay_cache(
                    strategy_config.get("llmReplayCachePath"), mode="record"
                )
                if cache_mode == "record"
                else nullcontext(None)
            )
            logger.info(f"回测 LLM 响应处理模式: {cache_mode}")
            with cache_context as replay_cache:
                result = await engine.run()
            from backtest.experiment_manifest import build_experiment_manifest

            result.statistics["experimentMetadata"] = build_experiment_manifest(
                engine,
                strategy_config,
                managed_llm or getattr(trading_agent, "llm", None),
                replay_cache,
            )
            _log_decision_perf_summary(backtest_id, decision_perf_stats)
            
            # 保存尚未落库的交易记录（提交成功后再推进计数）
            pending_trade_count = await _persist_new_trades(
                session, backtest_id, result.trades, _persisted_trade_count
            )
            pending_decision_count = await _persist_new_decisions(
                session,
                backtest_id,
                result.decision_log,
                _persisted_decision_count,
            )
            
            # 保存权益曲线
            if result.equity_curve:
                equity_data = []
                for i, eq in enumerate(result.equity_curve):
                    benchmark = None
                    if i < len(result.benchmark_curve):
                        benchmark = result.benchmark_curve[i].get('value')
                    
                    drawdown = Decimal('0')
                    if i < len(result.drawdown_curve):
                        drawdown = Decimal(str(result.drawdown_curve[i].get('value', 0)))
                    
                    equity_data.append({
                        'backtest_id': backtest_id,
                        'timestamp': datetime.fromisoformat(eq['time']),
                        'equity': eq['value'],
                        'drawdown': drawdown,
                        'benchmark': benchmark,
                        'unrealized_pnl': eq.get('unrealizedPnl'),
                        'unrealized_pnl_rate': eq.get('unrealizedPnlRate'),
                    })
                
                await batch_create_backtest_equity(session, equity_data)

            # 更新状态为完成
            completed = await update_backtest_result(
                session, backtest_id,
                result.statistics
            )
            await session.commit()
            if completed is None or completed.status != BacktestStatus.COMPLETED:
                logger.info(f"回测完成结果因任务已取消而未覆盖状态: {backtest_id}")
                return
            _persisted_trade_count[0] = pending_trade_count
            _persisted_decision_count[0] = pending_decision_count
            
            logger.info(f"回测完成: {backtest_id}, 总收益: {result.statistics.get('totalReturn', 0):.2f}%")
            
        except asyncio.CancelledError:
            logger.info(f"回测任务被取消: {backtest_id}")
            try:
                await session.rollback()
                current = await get_backtest_by_id(session, backtest_id)
                if current is not None and current.status != BacktestStatus.CANCELLED:
                    await update_backtest_status(
                        session, backtest_id,
                        BacktestStatus.CANCELLED,
                        error_message="用户手动停止",
                    )
                await session.commit()
            except Exception as cancel_err:
                logger.warning(f"保存回测取消状态失败: {backtest_id}, error={cancel_err}")

        except Exception as e:
            logger.error(f"回测执行失败: {backtest_id}, 错误: {e}")
            import traceback
            traceback.print_exc()
            try:
                await session.rollback()
            except Exception as rb_err:
                logger.warning(f"回测失败后 session.rollback 异常: {rb_err}")
            await update_backtest_status(
                session, backtest_id,
                BacktestStatus.FAILED,
                error_message=str(e)
            )
            await session.commit()
        finally:
            if cancel_watch_task is not None:
                cancel_watch_task.cancel()
                try:
                    await cancel_watch_task
                except asyncio.CancelledError:
                    pass
            if lease_task is not None:
                lease_task.cancel()
                try:
                    await lease_task
                except asyncio.CancelledError:
                    pass
