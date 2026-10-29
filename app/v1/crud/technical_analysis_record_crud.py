#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标分析生成记录 CRUD
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.inner_models.technical_analysis_record_model import TechnicalAnalysisRecordModel


async def create_technical_analysis_record(
    session: AsyncSession,
    user_id: str,
    symbol: str,
    analysis_date: Optional[str],
    timeframe: str,
    lookback_days: int,
    temperature: Optional[float],
    llm_model_id: Optional[int],
    llm_model_name: Optional[str],
    success: bool,
    error_message: Optional[str],
    summary_preview: Optional[str],
    result_payload: Optional[Dict[str, Any]],
) -> TechnicalAnalysisRecordModel:
    rec = TechnicalAnalysisRecordModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        symbol=symbol,
        analysis_date=analysis_date,
        timeframe=timeframe,
        lookback_days=lookback_days,
        temperature=temperature,
        llm_model_id=llm_model_id,
        llm_model_name=llm_model_name,
        success=success,
        error_message=error_message,
        summary_preview=summary_preview,
        result_payload=result_payload,
        created_at=datetime.now(),
    )
    session.add(rec)
    await session.flush()
    return rec


async def list_technical_analysis_records(
    session: AsyncSession,
    user_id: str,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[TechnicalAnalysisRecordModel], int]:
    q = select(TechnicalAnalysisRecordModel).where(
        TechnicalAnalysisRecordModel.user_id == user_id
    )
    q = q.order_by(desc(TechnicalAnalysisRecordModel.created_at)).offset(skip).limit(limit)
    res = await session.execute(q)
    rows = list(res.scalars().all())

    cnt_q = select(func.count(TechnicalAnalysisRecordModel.id)).where(
        TechnicalAnalysisRecordModel.user_id == user_id
    )
    total = (await session.execute(cnt_q)).scalar() or 0
    return rows, int(total)


async def get_technical_analysis_record(
    session: AsyncSession,
    record_id: str,
    user_id: str,
) -> Optional[TechnicalAnalysisRecordModel]:
    q = select(TechnicalAnalysisRecordModel).where(
        and_(
            TechnicalAnalysisRecordModel.id == record_id,
            TechnicalAnalysisRecordModel.user_id == user_id,
        )
    )
    res = await session.execute(q)
    return res.scalar_one_or_none()


async def get_latest_successful_record_for_symbol_before(
    session: AsyncSession,
    user_id: str,
    symbol: str,
    before: datetime,
    timeframe: Optional[str] = None,
) -> Optional[TechnicalAnalysisRecordModel]:
    """
    在 as_of 时刻之前，用户该交易对最近一条成功的技术面分析记录（用于回测对齐历史）。
    """
    cond = [
        TechnicalAnalysisRecordModel.user_id == user_id,
        TechnicalAnalysisRecordModel.symbol == symbol,
        TechnicalAnalysisRecordModel.success.is_(True),
        TechnicalAnalysisRecordModel.created_at <= before,
    ]
    if timeframe:
        cond.append(
            func.lower(TechnicalAnalysisRecordModel.timeframe) == timeframe.lower()
        )
    q = (
        select(TechnicalAnalysisRecordModel)
        .where(and_(*cond))
        .order_by(desc(TechnicalAnalysisRecordModel.created_at))
        .limit(1)
    )
    res = await session.execute(q)
    return res.scalar_one_or_none()


async def get_exact_successful_record_for_symbol_at(
    session: AsyncSession,
    user_id: str,
    symbol: str,
    analysis_at: str,
    timeframe: str,
) -> Optional[TechnicalAnalysisRecordModel]:
    """按用户/交易对/周期/分析时点精确命中成功记录，作为回测技术报告缓存。"""
    q = (
        select(TechnicalAnalysisRecordModel)
        .where(
            and_(
                TechnicalAnalysisRecordModel.user_id == user_id,
                TechnicalAnalysisRecordModel.symbol == symbol,
                TechnicalAnalysisRecordModel.success.is_(True),
                TechnicalAnalysisRecordModel.analysis_date == analysis_at,
                func.lower(TechnicalAnalysisRecordModel.timeframe) == timeframe.lower(),
            )
        )
        .order_by(desc(TechnicalAnalysisRecordModel.created_at))
        .limit(1)
    )
    res = await session.execute(q)
    return res.scalar_one_or_none()


async def get_technical_record_for_decision_context(
    session: AsyncSession,
    user_id: str,
    symbol: str,
    as_of: datetime,
    timeframe: Optional[str] = None,
) -> Optional[TechnicalAnalysisRecordModel]:
    """
    决策/回测注入用：优先按 analysis_date 与决策时刻精确对齐。
    - 新格式：analysis_date 存完整 ISO 时间，要求 <= as_of
    - 旧格式：analysis_date 仅有 YYYY-MM-DD 时，只允许取严格早于 as_of 所在日期的记录，
      避免同一天的日级记录在回测中造成未来数据泄漏
    否则回退到 created_at <= as_of 的旧逻辑。
    """
    as_of_date = as_of.strftime("%Y-%m-%d")
    as_of_iso = as_of.replace(microsecond=0).isoformat()
    cond_base = [
        TechnicalAnalysisRecordModel.user_id == user_id,
        TechnicalAnalysisRecordModel.symbol == symbol,
        TechnicalAnalysisRecordModel.success.is_(True),
    ]
    if timeframe:
        cond_base.append(
            func.lower(TechnicalAnalysisRecordModel.timeframe) == timeframe.lower()
        )

    q1 = (
        select(TechnicalAnalysisRecordModel)
        .where(
            and_(
                *cond_base,
                TechnicalAnalysisRecordModel.analysis_date.isnot(None),
                or_(
                    and_(
                        func.length(TechnicalAnalysisRecordModel.analysis_date) > 10,
                        TechnicalAnalysisRecordModel.analysis_date <= as_of_iso,
                    ),
                    and_(
                        func.length(TechnicalAnalysisRecordModel.analysis_date) <= 10,
                        TechnicalAnalysisRecordModel.analysis_date < as_of_date,
                    ),
                ),
            )
        )
        .order_by(
            desc(TechnicalAnalysisRecordModel.analysis_date),
            desc(TechnicalAnalysisRecordModel.created_at),
        )
        .limit(1)
    )
    res = await session.execute(q1)
    hit = res.scalar_one_or_none()
    if hit:
        return hit
    return await get_latest_successful_record_for_symbol_before(
        session, user_id, symbol, as_of, timeframe
    )
