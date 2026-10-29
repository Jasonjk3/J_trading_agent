#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测系统 CRUD 操作
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import defer, load_only

from models.inner_models.backtest_model import (
    BacktestTaskModel,
    BacktestStatus,
    KlineInterval,
    BacktestTradeModel,
    BacktestEquityModel,
    BacktestDecisionModel,
    HistoricalKlineModel
)
from lib.okx.symbol_utils import normalize_okx_symbol


def _kline_symbol_candidates(symbol: str) -> List[str]:
    """查询时兼容 BTCUSDT 与 BTC-USDT 两种历史键。"""
    raw = (symbol or "").strip()
    norm = normalize_okx_symbol(raw)
    candidates = []
    for s in (norm, raw):
        if s and s not in candidates:
            candidates.append(s)
    return candidates


def _kline_symbol_condition(symbol: str):
    candidates = _kline_symbol_candidates(symbol)
    if len(candidates) == 1:
        return HistoricalKlineModel.symbol == candidates[0]
    return HistoricalKlineModel.symbol.in_(candidates)


# ==================== BacktestTask CRUD ====================

async def get_backtest_by_id(
    session: AsyncSession,
    backtest_id: str
) -> Optional[BacktestTaskModel]:
    """根据 ID 获取任务主体；大快照仅允许专用进度/详情查询按字段读取。"""
    query = (
        select(BacktestTaskModel)
        .options(defer(BacktestTaskModel.progress_snapshot))
        .where(BacktestTaskModel.id == backtest_id)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_backtest_by_id_and_user(
    session: AsyncSession,
    backtest_id: str,
    user_id: str
) -> Optional[BacktestTaskModel]:
    """根据 ID 和用户获取任务主体，不为鉴权加载大快照。"""
    query = (
        select(BacktestTaskModel)
        .options(defer(BacktestTaskModel.progress_snapshot))
        .where(
            and_(
                BacktestTaskModel.id == backtest_id,
                BacktestTaskModel.user_id == user_id,
            )
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


def _compact_progress_snapshot_columns(*, include_series: bool = True):
    """数据库侧只提取页面需要的进度字段，避免传输整块历史 LLM 审计 JSON。"""
    snapshot = BacktestTaskModel.progress_snapshot
    columns = (
        snapshot["currentTime"].as_string().label("snapshot_current_time"),
        snapshot["message"].as_string().label("snapshot_message"),
        snapshot["currentStep"].as_integer().label("snapshot_current_step"),
        snapshot["totalSteps"].as_integer().label("snapshot_total_steps"),
        snapshot["intervalSeconds"].as_integer().label("snapshot_interval_seconds"),
        snapshot["heartbeatAt"].as_string().label("snapshot_heartbeat_at"),
        snapshot["leaseExpiresAt"].as_string().label("snapshot_lease_expires_at"),
        snapshot["workerId"].as_string().label("snapshot_worker_id"),
        snapshot[("livePreview", "equity")].as_float().label("preview_equity"),
        snapshot[("livePreview", "cash")].as_float().label("preview_cash"),
        snapshot[("livePreview", "statistics")].label("preview_statistics"),
        snapshot[("livePreview", "openPositions")].label("preview_open_positions"),
        snapshot[("livePreview", "activeOrders")].label("preview_active_orders"),
        snapshot[("livePreview", "decisionLogTotal")].as_integer().label("preview_decision_total"),
        snapshot[("livePreview", "decisionLogTruncated")].as_boolean().label("preview_decision_truncated"),
        func.json_length(
            snapshot[("livePreview", "decisionLog")]
        ).label("preview_legacy_decision_total"),
    )
    if not include_series:
        return columns
    return columns + (
        snapshot[("livePreview", "equityCurve")].label("preview_equity_curve"),
        snapshot[("livePreview", "drawdownCurve")].label("preview_drawdown_curve"),
        snapshot[("livePreview", "benchmarkCurve")].label("preview_benchmark_curve"),
        snapshot[("livePreview", "trades")].label("preview_trades"),
    )


def _build_compact_progress_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    """把 JSON_EXTRACT 的结果恢复成兼容原接口的轻量快照。"""
    snapshot_keys = {
        "currentTime": "snapshot_current_time",
        "message": "snapshot_message",
        "currentStep": "snapshot_current_step",
        "totalSteps": "snapshot_total_steps",
        "intervalSeconds": "snapshot_interval_seconds",
        "heartbeatAt": "snapshot_heartbeat_at",
        "leaseExpiresAt": "snapshot_lease_expires_at",
        "workerId": "snapshot_worker_id",
    }
    snapshot = {
        target: row.get(source)
        for target, source in snapshot_keys.items()
        if row.get(source) is not None
    }

    preview_keys = {
        "equity": "preview_equity",
        "cash": "preview_cash",
        "statistics": "preview_statistics",
        "equityCurve": "preview_equity_curve",
        "drawdownCurve": "preview_drawdown_curve",
        "benchmarkCurve": "preview_benchmark_curve",
        "trades": "preview_trades",
        "openPositions": "preview_open_positions",
        "activeOrders": "preview_active_orders",
        "decisionLogTruncated": "preview_decision_truncated",
    }
    preview = {
        target: row.get(source)
        for target, source in preview_keys.items()
        if row.get(source) is not None
    }
    decision_total = row.get("preview_decision_total")
    if decision_total is None:
        decision_total = row.get("preview_legacy_decision_total")
    if decision_total is not None:
        preview["decisionLogTotal"] = int(decision_total)
    if preview:
        snapshot["livePreview"] = preview
    return snapshot


async def get_backtest_detail_by_id_and_user(
    session: AsyncSession,
    backtest_id: str,
    user_id: str,
) -> Optional[tuple[BacktestTaskModel, Dict[str, Any]]]:
    """读取详情列和轻量快照；明确排除可能非常大的 progress_snapshot 原文。"""
    query = (
        select(
            BacktestTaskModel,
            *_compact_progress_snapshot_columns(include_series=False),
        )
        .options(
            load_only(
                BacktestTaskModel.id,
                BacktestTaskModel.name,
                BacktestTaskModel.status,
                BacktestTaskModel.progress,
                BacktestTaskModel.agent_id,
                BacktestTaskModel.agent_name,
                BacktestTaskModel.strategy_config,
                BacktestTaskModel.exchange,
                BacktestTaskModel.symbols,
                BacktestTaskModel.interval,
                BacktestTaskModel.start_time,
                BacktestTaskModel.end_time,
                BacktestTaskModel.initial_capital,
                BacktestTaskModel.maker_fee,
                BacktestTaskModel.taker_fee,
                BacktestTaskModel.slippage,
                BacktestTaskModel.result_statistics,
                BacktestTaskModel.error_message,
                BacktestTaskModel.started_at,
                BacktestTaskModel.completed_at,
                BacktestTaskModel.created_at,
            )
        )
        .where(
            and_(
                BacktestTaskModel.id == backtest_id,
                BacktestTaskModel.user_id == user_id,
            )
        )
    )
    result = (await session.execute(query)).one_or_none()
    if result is None:
        return None
    backtest = result[0]
    row = dict(result._mapping)
    return backtest, _build_compact_progress_snapshot(row)


async def get_backtest_progress_by_id_and_user(
    session: AsyncSession,
    backtest_id: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """只读取进度接口需要的列，并在数据库侧排除完整决策审计 JSON。"""
    query = select(
        BacktestTaskModel.status,
        BacktestTaskModel.progress,
        BacktestTaskModel.error_message,
        *_compact_progress_snapshot_columns(),
    ).where(
        and_(
            BacktestTaskModel.id == backtest_id,
            BacktestTaskModel.user_id == user_id,
        )
    )
    row = (await session.execute(query)).mappings().one_or_none()
    if row is None:
        return None
    data = dict(row)
    data["progress_snapshot"] = _build_compact_progress_snapshot(data)
    return data


async def get_backtest_current_time(
    session: AsyncSession,
    backtest_id: str,
) -> Optional[str]:
    """只读取 K 线截断需要的模拟时刻。"""
    query = select(
        BacktestTaskModel.progress_snapshot["currentTime"].as_string()
    ).where(BacktestTaskModel.id == backtest_id)
    return (await session.execute(query)).scalar_one_or_none()


async def get_backtests(
    session: AsyncSession,
    user_id: str,
    status: Optional[BacktestStatus] = None,
    skip: int = 0,
    limit: int = 20
) -> List[BacktestTaskModel]:
    """获取回测任务列表（仅加载列表展示所需列，避免 progress_snapshot 等大 JSON 参与排序）"""
    conditions = [BacktestTaskModel.user_id == user_id]
    
    if status is not None:
        conditions.append(BacktestTaskModel.status == status)
    
    query = (
        select(BacktestTaskModel)
        .options(
            load_only(
                BacktestTaskModel.id,
                BacktestTaskModel.user_id,
                BacktestTaskModel.name,
                BacktestTaskModel.status,
                BacktestTaskModel.agent_id,
                BacktestTaskModel.agent_name,
                BacktestTaskModel.exchange,
                BacktestTaskModel.symbols,
                BacktestTaskModel.start_time,
                BacktestTaskModel.end_time,
                BacktestTaskModel.initial_capital,
                BacktestTaskModel.result_statistics,
                BacktestTaskModel.created_at,
                BacktestTaskModel.completed_at,
            )
        )
        .where(and_(*conditions))
        .order_by(desc(BacktestTaskModel.created_at))
        .offset(skip)
        .limit(limit)
    )
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_backtests(
    session: AsyncSession,
    user_id: str,
    status: Optional[BacktestStatus] = None,
) -> int:
    """统计回测任务数量"""
    conditions = [BacktestTaskModel.user_id == user_id]
    
    if status is not None:
        conditions.append(BacktestTaskModel.status == status)
    
    query = select(func.count(BacktestTaskModel.id)).where(and_(*conditions))
    result = await session.execute(query)
    return result.scalar() or 0


async def create_backtest(
    session: AsyncSession,
    user_id: str,
    name: str,
    agent_id: str,
    agent_name: Optional[str],
    strategy_type: str,
    strategy_config: Dict[str, Any],
    exchange: str,
    symbols: List[str],
    interval: KlineInterval,
    start_time: datetime,
    end_time: datetime,
    initial_capital: Decimal,
    maker_fee: Decimal = Decimal('0.1'),
    taker_fee: Decimal = Decimal('0.1'),
    slippage: Decimal = Decimal('0.05')
) -> BacktestTaskModel:
    """创建回测任务"""
    backtest = BacktestTaskModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        status=BacktestStatus.PENDING,
        progress=0,
        agent_id=agent_id,
        agent_name=agent_name,
        strategy_type=strategy_type,
        strategy_config=strategy_config,
        exchange=exchange,
        symbols=symbols,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        initial_capital=initial_capital,
        maker_fee=maker_fee,
        taker_fee=taker_fee,
        slippage=slippage,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    session.add(backtest)
    await session.flush()
    await session.refresh(backtest)
    return backtest


async def update_backtest(
    session: AsyncSession,
    backtest_id: str,
    data: Dict[str, Any]
) -> Optional[BacktestTaskModel]:
    """更新回测任务"""
    backtest = await get_backtest_by_id(session, backtest_id)
    if not backtest:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(backtest, key, value)
    
    backtest.updated_at = datetime.now()
    await session.flush()
    await session.refresh(backtest)
    return backtest


async def update_backtest_status(
    session: AsyncSession,
    backtest_id: str,
    status: BacktestStatus,
    progress: Optional[int] = None,
    error_message: Optional[str] = None,
    progress_snapshot: Optional[Any] = None,
) -> Optional[BacktestTaskModel]:
    """更新回测任务状态"""
    if status == BacktestStatus.RUNNING:
        # 只允许 pending/running 写入进度；终态不能被迟到的进度回调复活。
        values: Dict[str, Any] = {"status": status, "updated_at": datetime.now()}
        if progress is not None:
            values["progress"] = progress
        if error_message is not None:
            values["error_message"] = error_message
        if progress_snapshot is not None:
            values["progress_snapshot"] = progress_snapshot
        values["started_at"] = func.coalesce(
            BacktestTaskModel.started_at, datetime.now()
        )
        statement = (
            BacktestTaskModel.__table__.update()
            .where(
                and_(
                    BacktestTaskModel.id == backtest_id,
                    BacktestTaskModel.status.in_((
                        BacktestStatus.PENDING,
                        BacktestStatus.RUNNING,
                    )),
                )
            )
            .values(**values)
        )
        await session.execute(statement)
        session.expire_all()
        return await get_backtest_by_id(session, backtest_id)

    backtest = await get_backtest_by_id(session, backtest_id)
    if not backtest:
        return None

    # cancelled 是终态。迟到的进度回调不得把用户已取消的任务复活为 running。
    if backtest.status == BacktestStatus.CANCELLED and status != BacktestStatus.CANCELLED:
        return backtest
    
    backtest.status = status
    if progress is not None:
        backtest.progress = progress
    if error_message is not None:
        backtest.error_message = error_message
    if progress_snapshot is not None:
        backtest.progress_snapshot = progress_snapshot
    elif status == BacktestStatus.COMPLETED:
        backtest.progress_snapshot = None
    
    if status == BacktestStatus.RUNNING and backtest.started_at is None:
        backtest.started_at = datetime.now()
    elif status in (
        BacktestStatus.COMPLETED,
        BacktestStatus.FAILED,
        BacktestStatus.CANCELLED,
    ):
        backtest.completed_at = datetime.now()
    
    backtest.updated_at = datetime.now()
    await session.flush()
    await session.refresh(backtest)
    return backtest


async def update_backtest_result(
    session: AsyncSession,
    backtest_id: str,
    result_statistics: Dict[str, Any]
) -> Optional[BacktestTaskModel]:
    """仅将仍在 running 的任务原子更新为完成，取消状态不可被覆盖。"""
    now = datetime.now()
    statement = (
        BacktestTaskModel.__table__.update()
        .where(
            and_(
                BacktestTaskModel.id == backtest_id,
                BacktestTaskModel.status == BacktestStatus.RUNNING,
            )
        )
        .values(
            result_statistics=result_statistics,
            status=BacktestStatus.COMPLETED,
            progress=100,
            progress_snapshot=None,
            completed_at=now,
            updated_at=now,
        )
    )
    await session.execute(statement)
    session.expire_all()
    return await get_backtest_by_id(session, backtest_id)


async def expire_stale_running_backtests(
    session: AsyncSession,
    stale_before: datetime,
) -> int:
    """回收心跳过期的 running 任务，防止进程退出后任务永久卡住。"""
    now = datetime.now()
    statement = (
        BacktestTaskModel.__table__.update()
        .where(
            and_(
                BacktestTaskModel.status == BacktestStatus.RUNNING,
                BacktestTaskModel.updated_at < stale_before,
            )
        )
        .values(
            status=BacktestStatus.FAILED,
            error_message="回测任务租约过期：执行进程已退出或心跳中断",
            completed_at=now,
            updated_at=now,
        )
    )
    result = await session.execute(statement)
    return int(result.rowcount or 0)


async def renew_backtest_lease(session: AsyncSession, backtest_id: str) -> bool:
    """仅在任务仍为 running 时原子续租，避免与完成/失败状态竞争。"""
    statement = (
        BacktestTaskModel.__table__.update()
        .where(
            and_(
                BacktestTaskModel.id == backtest_id,
                BacktestTaskModel.status == BacktestStatus.RUNNING,
            )
        )
        .values(updated_at=datetime.now())
    )
    result = await session.execute(statement)
    return bool(result.rowcount)


async def delete_backtest(
    session: AsyncSession,
    backtest_id: str
) -> bool:
    """删除回测任务及其明细，不为删除操作读取任务大字段。"""
    # 删除相关交易记录
    await session.execute(
        BacktestTradeModel.__table__.delete().where(
            BacktestTradeModel.backtest_id == backtest_id
        )
    )
    
    # 删除相关权益记录
    await session.execute(
        BacktestEquityModel.__table__.delete().where(
            BacktestEquityModel.backtest_id == backtest_id
        )
    )

    await session.execute(
        BacktestDecisionModel.__table__.delete().where(
            BacktestDecisionModel.backtest_id == backtest_id
        )
    )
    
    result = await session.execute(
        BacktestTaskModel.__table__.delete().where(
            BacktestTaskModel.id == backtest_id
        )
    )
    return bool(result.rowcount)


# ==================== BacktestTrade CRUD ====================

async def get_backtest_trades(
    session: AsyncSession,
    backtest_id: str,
    skip: int = 0,
    limit: Optional[int] = 1000,
    order: str = "asc",
) -> List[BacktestTradeModel]:
    """获取回测交易记录列表；limit=None 表示不截断。"""
    query = select(BacktestTradeModel).where(
        BacktestTradeModel.backtest_id == backtest_id
    )
    ordering = (
        BacktestTradeModel.timestamp.desc()
        if str(order).lower() == "desc"
        else BacktestTradeModel.timestamp.asc()
    )
    query = query.order_by(ordering, BacktestTradeModel.id).offset(skip)
    if limit is not None:
        query = query.limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_backtest_trades(
    session: AsyncSession,
    backtest_id: str
) -> int:
    """统计回测交易记录数量"""
    query = select(func.count(BacktestTradeModel.id)).where(
        BacktestTradeModel.backtest_id == backtest_id
    )
    result = await session.execute(query)
    return result.scalar() or 0


async def create_backtest_trade(
    session: AsyncSession,
    backtest_id: str,
    timestamp: datetime,
    symbol: str,
    side: str,
    trade_type: str,
    price: Decimal,
    quantity: Decimal,
    amount: Decimal,
    fee: Decimal,
    pnl: Decimal,
    pnl_percent: Decimal,
    balance: Decimal,
    reasoning: Optional[str] = None,
    signals: Optional[List[str]] = None,
    chain_of_thought: Optional[List[Dict]] = None,
    action: Optional[str] = None,
    leverage: Decimal = Decimal('1'),
    margin_used: Decimal = Decimal('0'),
) -> BacktestTradeModel:
    """创建回测交易记录"""
    trade = BacktestTradeModel(
        id=str(uuid.uuid4()),
        backtest_id=backtest_id,
        timestamp=timestamp,
        symbol=symbol,
        side=side,
        trade_type=trade_type,
        action=action,
        leverage=leverage,
        margin_used=margin_used,
        price=price,
        quantity=quantity,
        amount=amount,
        fee=fee,
        pnl=pnl,
        pnl_percent=pnl_percent,
        balance=balance,
        reasoning=reasoning,
        signals=signals,
        chain_of_thought=chain_of_thought,
        created_at=datetime.now()
    )
    session.add(trade)
    await session.flush()
    return trade


async def get_existing_backtest_trade_ids(
    session: AsyncSession,
    trade_ids: List[str],
) -> set:
    """查询已存在的成交主键，用于增量落库去重。"""
    if not trade_ids:
        return set()
    result = await session.execute(
        select(BacktestTradeModel.id).where(BacktestTradeModel.id.in_(trade_ids))
    )
    return {row[0] for row in result.all()}


async def batch_create_backtest_trades(
    session: AsyncSession,
    trades: List[Dict[str, Any]]
) -> int:
    """批量创建回测交易记录（自动跳过已存在的主键）。"""
    if not trades:
        return 0

    candidate_ids = [str(t.get("id") or "") for t in trades if t.get("id")]
    existing_ids = await get_existing_backtest_trade_ids(session, candidate_ids)

    trade_models = []
    for trade_data in trades:
        trade_id = str(trade_data.get("id") or uuid.uuid4())
        if trade_id in existing_ids:
            continue
        trade = BacktestTradeModel(
            id=trade_id,
            backtest_id=trade_data['backtest_id'],
            timestamp=trade_data['timestamp'],
            symbol=trade_data['symbol'],
            side=trade_data['side'],
            trade_type=trade_data['trade_type'],
            action=trade_data.get('action'),
            leverage=Decimal(str(trade_data.get('leverage', 1))),
            margin_used=Decimal(str(trade_data.get('margin_used', 0))),
            price=Decimal(str(trade_data['price'])),
            quantity=Decimal(str(trade_data['quantity'])),
            amount=Decimal(str(trade_data['amount'])),
            fee=Decimal(str(trade_data.get('fee', 0))),
            pnl=Decimal(str(trade_data.get('pnl', 0))),
            pnl_percent=Decimal(str(trade_data.get('pnl_percent', 0))),
            balance=Decimal(str(trade_data['balance'])),
            reasoning=trade_data.get('reasoning'),
            signals=trade_data.get('signals'),
            chain_of_thought=trade_data.get('chain_of_thought'),
            created_at=datetime.now()
        )
        trade_models.append(trade)
        existing_ids.add(trade_id)

    if not trade_models:
        return 0

    session.add_all(trade_models)
    await session.flush()
    return len(trade_models)


# ==================== BacktestEquity CRUD ====================

async def get_backtest_equity_records(
    session: AsyncSession,
    backtest_id: str,
    skip: int = 0,
    limit: int = 10000
) -> List[BacktestEquityModel]:
    """获取回测权益曲线记录"""
    query = select(BacktestEquityModel).where(
        BacktestEquityModel.backtest_id == backtest_id
    )
    query = query.order_by(BacktestEquityModel.timestamp).offset(skip).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_backtest_equity(
    session: AsyncSession,
    backtest_id: str,
    timestamp: datetime,
    equity: Decimal,
    drawdown: Decimal = Decimal('0'),
    benchmark: Optional[Decimal] = None
) -> BacktestEquityModel:
    """创建回测权益记录"""
    record = BacktestEquityModel(
        id=str(uuid.uuid4()),
        backtest_id=backtest_id,
        timestamp=timestamp,
        equity=equity,
        drawdown=drawdown,
        benchmark=benchmark,
        created_at=datetime.now()
    )
    session.add(record)
    await session.flush()
    return record


async def batch_create_backtest_equity(
    session: AsyncSession,
    equity_records: List[Dict[str, Any]]
) -> int:
    """批量创建回测权益记录"""
    equity_models = []
    for record_data in equity_records:
        record = BacktestEquityModel(
            id=str(uuid.uuid4()),
            backtest_id=record_data['backtest_id'],
            timestamp=record_data['timestamp'],
            equity=Decimal(str(record_data['equity'])),
            drawdown=Decimal(str(record_data.get('drawdown', 0))),
            benchmark=Decimal(str(record_data['benchmark'])) if record_data.get('benchmark') else None,
            unrealized_pnl=Decimal(str(record_data['unrealized_pnl'])) if record_data.get('unrealized_pnl') is not None else None,
            unrealized_pnl_rate=Decimal(str(record_data['unrealized_pnl_rate'])) if record_data.get('unrealized_pnl_rate') is not None else None,
            created_at=datetime.now()
        )
        equity_models.append(record)
    
    session.add_all(equity_models)
    await session.flush()
    return len(equity_models)


# ==================== BacktestDecision CRUD ====================

async def get_backtest_decisions(
    session: AsyncSession,
    backtest_id: str,
    skip: int = 0,
    limit: Optional[int] = 5000,
    summary_only: bool = True,
) -> List[BacktestDecisionModel]:
    """获取决策分页；列表默认排除 Prompt、原始响应和技术分析大字段。"""
    query = select(BacktestDecisionModel).where(
        BacktestDecisionModel.backtest_id == backtest_id
    )
    if summary_only:
        query = query.options(
            load_only(
                BacktestDecisionModel.id,
                BacktestDecisionModel.timestamp,
                BacktestDecisionModel.action,
                BacktestDecisionModel.symbol,
                BacktestDecisionModel.quantity,
                BacktestDecisionModel.reasoning,
                BacktestDecisionModel.decision_analysis,
                BacktestDecisionModel.reference_price,
                BacktestDecisionModel.execution_result,
            )
        )
    query = query.order_by(
        desc(BacktestDecisionModel.timestamp),
        desc(BacktestDecisionModel.created_at),
        desc(BacktestDecisionModel.id),
    ).offset(skip)
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_backtest_decision_by_id_and_user(
    session: AsyncSession,
    backtest_id: str,
    decision_id: str,
    user_id: str,
) -> Optional[BacktestDecisionModel]:
    """按主键读取单条完整决策，并同时校验任务归属。"""
    query = (
        select(BacktestDecisionModel)
        .join(
            BacktestTaskModel,
            BacktestTaskModel.id == BacktestDecisionModel.backtest_id,
        )
        .where(
            and_(
                BacktestDecisionModel.id == decision_id,
                BacktestDecisionModel.backtest_id == backtest_id,
                BacktestTaskModel.user_id == user_id,
            )
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def count_backtest_decisions(
    session: AsyncSession,
    backtest_id: str
) -> int:
    """统计回测决策记录数量"""
    query = select(func.count(BacktestDecisionModel.id)).where(
        BacktestDecisionModel.backtest_id == backtest_id
    )
    result = await session.execute(query)
    return result.scalar() or 0


async def get_existing_backtest_decision_ids(
    session: AsyncSession,
    decision_ids: List[str],
) -> set:
    """查询已落库的决策主键，供运行中增量持久化去重。"""
    if not decision_ids:
        return set()
    result = await session.execute(
        select(BacktestDecisionModel.id).where(
            BacktestDecisionModel.id.in_(decision_ids)
        )
    )
    return {row[0] for row in result.all()}


async def batch_create_backtest_decisions(
    session: AsyncSession,
    decisions: List[Dict[str, Any]]
) -> int:
    """批量创建回测决策记录"""
    if not decisions:
        return 0

    candidate_ids = [str(d.get('id') or '') for d in decisions if d.get('id')]
    existing_ids = await get_existing_backtest_decision_ids(session, candidate_ids)
    decision_models = []
    for d in decisions:
        decision_id = str(d.get('id') or uuid.uuid4())
        if decision_id in existing_ids:
            continue
        ts = d.get('timestamp')
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        ref_p = d.get('reference_price')
        if ref_p is None:
            ref_p = d.get('current_price')
        rec = BacktestDecisionModel(
            id=decision_id,
            backtest_id=d['backtest_id'],
            timestamp=ts,
            action=d.get('action', 'hold'),
            symbol=d.get('symbol'),
            quantity=Decimal(str(d['quantity'])) if d.get('quantity') is not None else None,
            reasoning=d.get('reasoning') or d.get('reason'),
            decision_analysis=(
                d.get('decision_analysis')
                or d.get('decisionAnalysis')
                or d.get('reasoning')
                or d.get('reason')
            ),
            technical_analysis=d.get('technical_analysis') or d.get('technicalAnalysis'),
            chain_of_thought=d.get('chain_of_thought') or d.get('chainOfThought'),
            reference_price=Decimal(str(ref_p)) if ref_p is not None else None,
            execution_result=d.get('execution_result') or d.get('executionResult'),
            created_at=datetime.now()
        )
        decision_models.append(rec)
        existing_ids.add(decision_id)
    if not decision_models:
        return 0
    session.add_all(decision_models)
    await session.flush()
    return len(decision_models)


# ==================== HistoricalKline CRUD ====================

async def get_klines(
    session: AsyncSession,
    exchange: str,
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
    limit: int = 10000
) -> List[HistoricalKlineModel]:
    """获取历史K线数据"""
    query = select(HistoricalKlineModel).where(
        and_(
            HistoricalKlineModel.exchange == exchange,
            _kline_symbol_condition(symbol),
            HistoricalKlineModel.interval == interval,
            HistoricalKlineModel.timestamp >= start_time,
            HistoricalKlineModel.timestamp <= end_time
        )
    )
    query = query.order_by(HistoricalKlineModel.timestamp).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_latest_kline(
    session: AsyncSession,
    exchange: str,
    symbol: str,
    interval: str
) -> Optional[HistoricalKlineModel]:
    """获取最新的K线数据"""
    query = select(HistoricalKlineModel).where(
        and_(
            HistoricalKlineModel.exchange == exchange,
            _kline_symbol_condition(symbol),
            HistoricalKlineModel.interval == interval
        )
    ).order_by(desc(HistoricalKlineModel.timestamp)).limit(1)
    
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_earliest_kline(
    session: AsyncSession,
    exchange: str,
    symbol: str,
    interval: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> Optional[HistoricalKlineModel]:
    """获取指定区间内最早的 K 线（用于检测历史段缺口）。"""
    conditions = [
        HistoricalKlineModel.exchange == exchange,
        _kline_symbol_condition(symbol),
        HistoricalKlineModel.interval == interval,
    ]
    if start_time is not None:
        conditions.append(HistoricalKlineModel.timestamp >= start_time)
    if end_time is not None:
        conditions.append(HistoricalKlineModel.timestamp <= end_time)

    query = (
        select(HistoricalKlineModel)
        .where(and_(*conditions))
        .order_by(HistoricalKlineModel.timestamp)
        .limit(1)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_kline(
    session: AsyncSession,
    exchange: str,
    symbol: str,
    interval: str,
    timestamp: datetime,
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    volume: Decimal,
    quote_volume: Optional[Decimal] = None
) -> HistoricalKlineModel:
    """创建历史K线记录"""
    kline = HistoricalKlineModel(
        exchange=exchange,
        symbol=symbol,
        interval=interval,
        timestamp=timestamp,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
        quote_volume=quote_volume,
        created_at=datetime.now()
    )
    session.add(kline)
    await session.flush()
    await session.refresh(kline)
    return kline


async def batch_create_klines(
    session: AsyncSession,
    klines: List[Dict[str, Any]]
) -> int:
    """批量创建历史K线记录（使用 IGNORE 避免重复）"""
    from sqlalchemy.dialects.mysql import insert
    
    if not klines:
        return 0
    
    # 使用 INSERT IGNORE 语法避免重复
    stmt = insert(HistoricalKlineModel).values(klines).prefix_with('IGNORE')
    await session.execute(stmt)
    await session.flush()
    return len(klines)


async def count_klines(
    session: AsyncSession,
    exchange: str,
    symbol: str,
    interval: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> int:
    """统计K线数据数量"""
    conditions = [
        HistoricalKlineModel.exchange == exchange,
        _kline_symbol_condition(symbol),
        HistoricalKlineModel.interval == interval
    ]
    
    if start_time is not None:
        conditions.append(HistoricalKlineModel.timestamp >= start_time)
    if end_time is not None:
        conditions.append(HistoricalKlineModel.timestamp <= end_time)
    
    query = select(func.count(HistoricalKlineModel.id)).where(and_(*conditions))
    result = await session.execute(query)
    return result.scalar() or 0
