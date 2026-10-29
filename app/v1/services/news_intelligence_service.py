#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息面采集 业务服务
"""
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.inner_models.news_intelligence_model import (
    NewsIntelligenceAgentModel,
    NewsIntelligenceItemModel,
    NewsIntelligenceAgentStatus,
)
from app.v1.crud import news_intelligence_crud as crud
from app.v1.crud.model_management_crud import get_model_by_id
from app.v1.services.news_intelligence_collector import collect_one_agent


class NewsIntelligenceService:
    """消息面采集"""

    async def _llm_name(self, session: AsyncSession, llm_model_id: int) -> Optional[str]:
        m = await get_model_by_id(session, llm_model_id)
        return m.name if m else None

    def agent_to_dict(
        self,
        agent: NewsIntelligenceAgentModel,
        llm_model_name: Optional[str] = None,
    ) -> dict:
        sectors = agent.sectors if isinstance(agent.sectors, list) else []
        return {
            "id": agent.id,
            "name": agent.name,
            "remark": agent.remark,
            "sectors": sectors,
            "customKeywords": agent.custom_keywords,
            "symbolCodes": agent.symbol_codes,
            "llmModelId": agent.llm_model_id,
            "llmModelName": llm_model_name,
            "intervalMinutes": agent.interval_minutes,
            "maxItemsPerBatch": agent.max_items_per_batch,
            "temperature": agent.temperature,
            "status": agent.status.value,
            "lastRunAt": agent.last_run_at.isoformat() if agent.last_run_at else None,
            "createdAt": agent.created_at.isoformat() if agent.created_at else "",
            "updatedAt": agent.updated_at.isoformat() if agent.updated_at else "",
        }

    def item_to_dict(self, item: NewsIntelligenceItemModel) -> dict:
        return {
            "id": item.id,
            "agentId": item.agent_id,
            "title": item.title,
            "summary": item.summary,
            "sourceUrl": item.source_url,
            "sourceName": item.source_name,
            "eventTime": item.event_time.isoformat() if item.event_time else None,
            "ingestedAt": item.ingested_at.isoformat() if item.ingested_at else "",
            "sortTime": item.sort_time.isoformat() if item.sort_time else "",
        }

    async def get_list(
        self,
        session: AsyncSession,
        user_id: str,
        status: Optional[NewsIntelligenceAgentStatus] = None,
    ) -> Tuple[List[dict], int]:
        agents = await crud.list_agents_by_user(session, user_id, status=status)
        total = await crud.count_agents_by_user(session, user_id, status=status)
        out = []
        for a in agents:
            name = await self._llm_name(session, a.llm_model_id)
            out.append(self.agent_to_dict(a, name))
        return out, total

    async def get_by_id(
        self, session: AsyncSession, agent_id: str, user_id: str
    ) -> Optional[dict]:
        agent = await crud.get_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return None
        name = await self._llm_name(session, agent.llm_model_id)
        return self.agent_to_dict(agent, name)

    async def create(
        self,
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
        run_on_create: bool = False,
    ) -> dict:
        initial = (
            NewsIntelligenceAgentStatus.RUNNING if run_on_create else NewsIntelligenceAgentStatus.STOPPED
        )
        agent = await crud.create_agent(
            session,
            user_id=user_id,
            name=name,
            sectors=sectors,
            llm_model_id=llm_model_id,
            interval_minutes=interval_minutes,
            max_items_per_batch=max_items_per_batch,
            temperature=temperature,
            remark=remark,
            custom_keywords=custom_keywords,
            symbol_codes=symbol_codes,
            initial_status=initial,
        )
        logger.info(f"创建消息面采集任务: {agent.id}, user={user_id}")
        llm_name = await self._llm_name(session, agent.llm_model_id)
        return self.agent_to_dict(agent, llm_name)

    async def update(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        **fields,
    ) -> Optional[dict]:
        agent = await crud.get_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return None

        mapping = {
            "name": fields.get("name"),
            "remark": fields.get("remark"),
            "sectors": fields.get("sectors"),
            "custom_keywords": fields.get("custom_keywords"),
            "symbol_codes": fields.get("symbol_codes"),
            "llm_model_id": fields.get("llm_model_id"),
            "interval_minutes": fields.get("interval_minutes"),
            "max_items_per_batch": fields.get("max_items_per_batch"),
            "temperature": fields.get("temperature"),
        }
        data = {k: v for k, v in mapping.items() if v is not None}
        if not data:
            llm_name = await self._llm_name(session, agent.llm_model_id)
            return self.agent_to_dict(agent, llm_name)

        updated = await crud.update_agent(session, agent_id, data)
        if not updated:
            return None
        llm_name = await self._llm_name(session, updated.llm_model_id)
        return self.agent_to_dict(updated, llm_name)

    async def delete(self, session: AsyncSession, agent_id: str, user_id: str) -> Tuple[bool, str]:
        agent = await crud.get_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, "任务不存在"
        if agent.status == NewsIntelligenceAgentStatus.RUNNING:
            return False, "请先停止采集任务再删除"
        await crud.delete_items_by_agent(session, agent_id)
        ok = await crud.delete_agent(session, agent_id)
        if ok:
            logger.info(f"删除消息面采集任务: {agent_id}")
            return True, ""
        return False, "删除失败"

    async def start(self, session: AsyncSession, agent_id: str, user_id: str) -> Tuple[bool, str]:
        agent = await crud.get_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, "任务不存在"
        if agent.status == NewsIntelligenceAgentStatus.RUNNING:
            return False, "已在运行中"
        await crud.update_agent(
            session,
            agent_id,
            {
                "status": NewsIntelligenceAgentStatus.RUNNING,
                "last_run_at": None,
            },
        )
        logger.info(f"启动消息面采集: {agent_id}")
        return True, "已启动"

    async def stop(self, session: AsyncSession, agent_id: str, user_id: str) -> Tuple[bool, str]:
        agent = await crud.get_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, "任务不存在"
        if agent.status == NewsIntelligenceAgentStatus.STOPPED:
            return False, "已停止"
        await crud.update_agent(
            session,
            agent_id,
            {"status": NewsIntelligenceAgentStatus.STOPPED},
        )
        logger.info(f"停止消息面采集: {agent_id}")
        return True, "已停止"

    async def collect_now(
        self, session: AsyncSession, agent_id: str, user_id: str
    ) -> Tuple[bool, str, int]:
        """
        立即执行一轮采集（忽略调度间隔；不要求任务处于「运行中」）。
        返回 (是否成功, 提示文案, 本次写入条数)。
        """
        agent = await crud.get_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, "任务不存在", 0
        try:
            inserted = await collect_one_agent(
                session,
                agent_id,
                ignore_interval=True,
                ignore_running_check=True,
            )
        except Exception as e:
            logger.exception(f"立即采集失败 agent={agent_id}: {e}")
            return False, f"采集异常: {e}", 0
        if inserted > 0:
            return True, f"已写入 {inserted} 条资讯", inserted
        return True, "本轮未新增资讯（可能均为重复或模型未返回有效数据）", 0

    async def list_timeline_items(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        time_from: Optional[datetime] = None,
        time_to: Optional[datetime] = None,
    ) -> Tuple[List[dict], int]:
        agent = await crud.get_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return [], 0
        items, total = await crud.list_items(
            session,
            agent_id,
            order=order,
            page=page,
            page_size=page_size,
            keyword=keyword,
            time_from=time_from,
            time_to=time_to,
        )
        return [self.item_to_dict(x) for x in items], total

