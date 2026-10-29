#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息面采集 CRUD
"""
import uuid
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import and_, desc, asc, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.news_intelligence_model import (
    NewsIntelligenceAgentModel,
    NewsIntelligenceItemModel,
    NewsIntelligenceAgentStatus,
)


async def get_agent_by_id(session: AsyncSession, agent_id: str) -> Optional[NewsIntelligenceAgentModel]:
    q = select(NewsIntelligenceAgentModel).where(NewsIntelligenceAgentModel.id == agent_id)
    r = await session.execute(q)
    return r.scalar_one_or_none()


async def get_agent_by_id_and_user(
    session: AsyncSession, agent_id: str, user_id: str
) -> Optional[NewsIntelligenceAgentModel]:
    q = select(NewsIntelligenceAgentModel).where(
        and_(NewsIntelligenceAgentModel.id == agent_id, NewsIntelligenceAgentModel.user_id == user_id)
    )
    r = await session.execute(q)
    return r.scalar_one_or_none()


async def list_running_agents_all_users(session: AsyncSession) -> List[NewsIntelligenceAgentModel]:
    """所有处于运行中的采集任务（后台 Worker 使用）"""
    q = (
        select(NewsIntelligenceAgentModel)
        .where(NewsIntelligenceAgentModel.status == NewsIntelligenceAgentStatus.RUNNING)
        .order_by(NewsIntelligenceAgentModel.updated_at)
    )
    r = await session.execute(q)
    return list(r.scalars().all())


async def list_agents_by_user(
    session: AsyncSession,
    user_id: str,
    status: Optional[NewsIntelligenceAgentStatus] = None,
) -> List[NewsIntelligenceAgentModel]:
    cond = [NewsIntelligenceAgentModel.user_id == user_id]
    if status is not None:
        cond.append(NewsIntelligenceAgentModel.status == status)
    q = select(NewsIntelligenceAgentModel).where(and_(*cond)).order_by(desc(NewsIntelligenceAgentModel.created_at))
    r = await session.execute(q)
    return list(r.scalars().all())


async def count_agents_by_user(
    session: AsyncSession,
    user_id: str,
    status: Optional[NewsIntelligenceAgentStatus] = None,
) -> int:
    cond = [NewsIntelligenceAgentModel.user_id == user_id]
    if status is not None:
        cond.append(NewsIntelligenceAgentModel.status == status)
    q = select(func.count(NewsIntelligenceAgentModel.id)).where(and_(*cond))
    r = await session.execute(q)
    return r.scalar() or 0


async def create_agent(
    session: AsyncSession,
    user_id: str,
    name: str,
    sectors: List[str],
    llm_model_id: int,
    interval_minutes: int,
    max_items_per_batch: int,
    temperature: float,
    remark: Optional[str] = None,
    custom_keywords: Optional[str] = None,
    symbol_codes: Optional[str] = None,
    initial_status: NewsIntelligenceAgentStatus = NewsIntelligenceAgentStatus.STOPPED,
) -> NewsIntelligenceAgentModel:
    now = datetime.now()
    agent = NewsIntelligenceAgentModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        remark=remark,
        sectors=sectors,
        custom_keywords=custom_keywords,
        symbol_codes=symbol_codes,
        llm_model_id=llm_model_id,
        interval_minutes=interval_minutes,
        max_items_per_batch=max_items_per_batch,
        temperature=temperature,
        status=initial_status,
        last_run_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    return agent


async def update_agent(
    session: AsyncSession, agent_id: str, data: dict
) -> Optional[NewsIntelligenceAgentModel]:
    agent = await get_agent_by_id(session, agent_id)
    if not agent:
        return None
    for k, v in data.items():
        if v is not None:
            setattr(agent, k, v)
        elif k == "last_run_at":
            setattr(agent, k, None)
    agent.updated_at = datetime.now()
    await session.flush()
    await session.refresh(agent)
    return agent


async def delete_agent(session: AsyncSession, agent_id: str) -> bool:
    agent = await get_agent_by_id(session, agent_id)
    if not agent:
        return False
    await session.delete(agent)
    return True


async def delete_items_by_agent(session: AsyncSession, agent_id: str) -> None:
    await session.execute(
        delete(NewsIntelligenceItemModel).where(NewsIntelligenceItemModel.agent_id == agent_id)
    )


async def list_items(
    session: AsyncSession,
    agent_id: str,
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    time_from: Optional[datetime] = None,
    time_to: Optional[datetime] = None,
) -> Tuple[List[NewsIntelligenceItemModel], int]:
    cond = [NewsIntelligenceItemModel.agent_id == agent_id]
    if time_from is not None:
        cond.append(NewsIntelligenceItemModel.sort_time >= time_from)
    if time_to is not None:
        cond.append(NewsIntelligenceItemModel.sort_time <= time_to)
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        cond.append(
            or_(
                NewsIntelligenceItemModel.title.like(kw),
                NewsIntelligenceItemModel.summary.like(kw),
            )
        )

    count_q = select(func.count(NewsIntelligenceItemModel.id)).where(and_(*cond))
    total_r = await session.execute(count_q)
    total = total_r.scalar() or 0

    q = select(NewsIntelligenceItemModel).where(and_(*cond))
    if order == "asc":
        q = q.order_by(asc(NewsIntelligenceItemModel.sort_time))
    else:
        q = q.order_by(desc(NewsIntelligenceItemModel.sort_time))

    skip = max(0, (page - 1) * page_size)
    q = q.offset(skip).limit(page_size)
    r = await session.execute(q)
    return list(r.scalars().all()), total


async def item_dedup_exists(
    session: AsyncSession,
    agent_id: str,
    dedup_hash: str,
) -> bool:
    if not dedup_hash:
        return False
    q = select(func.count(NewsIntelligenceItemModel.id)).where(
        and_(
            NewsIntelligenceItemModel.agent_id == agent_id,
            NewsIntelligenceItemModel.dedup_hash == dedup_hash,
        )
    )
    r = await session.execute(q)
    return (r.scalar() or 0) > 0


async def create_item(
    session: AsyncSession,
    agent_id: str,
    title: str,
    summary: Optional[str],
    source_url: Optional[str],
    source_name: Optional[str],
    event_time: Optional[datetime],
    ingested_at: datetime,
    sort_time: datetime,
    dedup_hash: Optional[str] = None,
) -> NewsIntelligenceItemModel:
    """单条写入资讯（供后续 LLM 采集任务调用）"""
    row = NewsIntelligenceItemModel(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        title=title[:500],
        summary=summary,
        source_url=source_url[:2000] if source_url else None,
        source_name=source_name[:200] if source_name else None,
        event_time=event_time,
        ingested_at=ingested_at,
        sort_time=sort_time,
        dedup_hash=dedup_hash,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row
