#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交易 Agent CRUD 操作
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models.inner_models.trading_agent_model import (
    TradingAgentModel,
    TradingAgentStatus,
    StrategyType,
    AgentOperationModel,
    AgentProfitRecordModel,
    OperationType,
    OperationResult
)


# ==================== TradingAgent CRUD ====================

async def get_trading_agent_by_id(
    session: AsyncSession,
    agent_id: str
) -> Optional[TradingAgentModel]:
    """根据ID获取交易 Agent"""
    query = select(TradingAgentModel).where(TradingAgentModel.id == agent_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_trading_agent_by_id_and_user(
    session: AsyncSession,
    agent_id: str,
    user_id: str
) -> Optional[TradingAgentModel]:
    """根据ID和用户ID获取交易 Agent"""
    query = select(TradingAgentModel).where(
        and_(
            TradingAgentModel.id == agent_id,
            TradingAgentModel.user_id == user_id
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_trading_agents(
    session: AsyncSession,
    user_id: str,
    status: Optional[TradingAgentStatus] = None,
    skip: int = 0,
    limit: int = 100
) -> List[TradingAgentModel]:
    """获取交易 Agent 列表"""
    conditions = [TradingAgentModel.user_id == user_id]
    
    if status is not None:
        conditions.append(TradingAgentModel.status == status)
    
    query = select(TradingAgentModel).where(and_(*conditions))
    query = query.order_by(desc(TradingAgentModel.created_at)).offset(skip).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def count_trading_agents(
    session: AsyncSession,
    user_id: str,
    status: Optional[TradingAgentStatus] = None,
) -> int:
    """统计交易 Agent 数量"""
    conditions = [TradingAgentModel.user_id == user_id]
    
    if status is not None:
        conditions.append(TradingAgentModel.status == status)
    
    query = select(func.count(TradingAgentModel.id)).where(and_(*conditions))
    result = await session.execute(query)
    return result.scalar() or 0


async def create_trading_agent(
    session: AsyncSession,
    user_id: str,
    name: str,
    strategy_type: StrategyType,
    exchange_account_id: Optional[str] = None,
    llm_model_id: Optional[int] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
    remark: Optional[str] = None
) -> TradingAgentModel:
    """创建交易 Agent"""
    agent = TradingAgentModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        strategy_type=strategy_type,
        exchange_account_id=exchange_account_id,
        llm_model_id=llm_model_id,
        strategy_config=strategy_config or {},
        remark=remark,
        status=TradingAgentStatus.STOPPED,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    return agent


async def update_trading_agent(
    session: AsyncSession,
    agent_id: str,
    data: Dict[str, Any]
) -> Optional[TradingAgentModel]:
    """更新交易 Agent"""
    agent = await get_trading_agent_by_id(session, agent_id)
    if not agent:
        return None
    
    for key, value in data.items():
        if value is not None:
            setattr(agent, key, value)
    
    agent.updated_at = datetime.now()
    await session.flush()
    await session.refresh(agent)
    return agent


async def delete_trading_agent(
    session: AsyncSession,
    agent_id: str
) -> bool:
    """删除交易 Agent"""
    agent = await get_trading_agent_by_id(session, agent_id)
    if not agent:
        return False
    
    await session.delete(agent)
    await session.flush()
    return True


async def update_trading_agent_status(
    session: AsyncSession,
    agent_id: str,
    status: TradingAgentStatus,
    last_run_at: Optional[datetime] = None
) -> Optional[TradingAgentModel]:
    """更新交易 Agent 状态"""
    agent = await get_trading_agent_by_id(session, agent_id)
    if not agent:
        return None
    
    agent.status = status
    if last_run_at:
        agent.last_run_at = last_run_at
    agent.updated_at = datetime.now()
    
    await session.flush()
    await session.refresh(agent)
    return agent


# ==================== AgentOperation CRUD ====================

async def get_agent_operations(
    session: AsyncSession,
    agent_id: str,
    operation_type: Optional[OperationType] = None,
    result: Optional[OperationResult] = None,
    skip: int = 0,
    limit: int = 50
) -> List[AgentOperationModel]:
    """获取 Agent 操作记录列表"""
    conditions = [AgentOperationModel.agent_id == agent_id]
    
    if operation_type is not None:
        conditions.append(AgentOperationModel.type == operation_type)
    if result is not None:
        conditions.append(AgentOperationModel.result == result)
    
    query = select(AgentOperationModel).where(and_(*conditions))
    query = query.order_by(desc(AgentOperationModel.created_at)).offset(skip).limit(limit)
    
    result_data = await session.execute(query)
    return list(result_data.scalars().all())


async def count_agent_operations(
    session: AsyncSession,
    agent_id: str,
    operation_type: Optional[OperationType] = None,
    result: Optional[OperationResult] = None
) -> int:
    """统计 Agent 操作记录数量"""
    conditions = [AgentOperationModel.agent_id == agent_id]
    
    if operation_type is not None:
        conditions.append(AgentOperationModel.type == operation_type)
    if result is not None:
        conditions.append(AgentOperationModel.result == result)
    
    query = select(func.count(AgentOperationModel.id)).where(and_(*conditions))
    result_data = await session.execute(query)
    return result_data.scalar() or 0


async def create_agent_operation(
    session: AsyncSession,
    agent_id: str,
    operation_type: OperationType,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    quantity: Optional[str] = None,
    price: Optional[str] = None,
    reason: Optional[str] = None,
    result: Optional[OperationResult] = None,
    chain_of_thought: Optional[List[Dict]] = None,
    order_id: Optional[str] = None,
    error_message: Optional[str] = None
) -> AgentOperationModel:
    """创建 Agent 操作记录"""
    operation = AgentOperationModel(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        type=operation_type,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        reason=reason,
        result=result,
        chain_of_thought=chain_of_thought or [],
        order_id=order_id,
        error_message=error_message,
        created_at=datetime.now()
    )
    session.add(operation)
    await session.flush()
    await session.refresh(operation)
    return operation


# ==================== AgentProfitRecord CRUD ====================

async def get_agent_profit_records(
    session: AsyncSession,
    agent_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000
) -> List[AgentProfitRecordModel]:
    """获取 Agent 收益记录列表"""
    conditions = [AgentProfitRecordModel.agent_id == agent_id]
    
    if start_time is not None:
        conditions.append(AgentProfitRecordModel.record_time >= start_time)
    if end_time is not None:
        conditions.append(AgentProfitRecordModel.record_time <= end_time)
    
    query = select(AgentProfitRecordModel).where(and_(*conditions))
    query = query.order_by(AgentProfitRecordModel.record_time).offset(skip).limit(limit)
    
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_agent_profit_record(
    session: AsyncSession,
    agent_id: str,
    record_time: datetime,
    value: str,
    cumulative: str,
    equity: Optional[str] = None,
    unrealized_pnl: Optional[str] = None,
    unrealized_pnl_rate: Optional[str] = None,
) -> AgentProfitRecordModel:
    """创建 Agent 收益记录"""
    from decimal import Decimal
    
    record = AgentProfitRecordModel(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        record_time=record_time,
        value=Decimal(value),
        cumulative=Decimal(cumulative),
        equity=Decimal(equity) if equity else None,
        unrealized_pnl=Decimal(unrealized_pnl) if unrealized_pnl is not None else None,
        unrealized_pnl_rate=Decimal(unrealized_pnl_rate) if unrealized_pnl_rate is not None else None,
        created_at=datetime.now()
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record
