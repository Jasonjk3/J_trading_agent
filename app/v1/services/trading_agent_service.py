#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交易 Agent 服务
"""
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

from app.v1.services.trading_analysis_context_service import build_trading_analysis_context
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from loguru import logger

from models.inner_models.trading_agent_model import (
    TradingAgentModel,
    TradingAgentStatus,
    StrategyType,
    AgentOperationModel,
    AgentProfitRecordModel,
    OperationType,
    OperationResult
)
from models.inner_models.trader_state_model import (
    TraderEventModel,
    TraderStateModel,
    TraderTurnModel,
)
from app.v1.crud.trading_agent_crud import (
    get_trading_agents,
    get_trading_agent_by_id_and_user,
    get_trading_agent_by_id,
    create_trading_agent,
    update_trading_agent,
    delete_trading_agent,
    update_trading_agent_status,
    count_trading_agents,
    get_agent_operations,
    count_agent_operations,
    get_agent_profit_records,
    create_agent_operation
)
from app.v1.schemas.trading_agent_schema import StrategyConfigSchema


class TradingAgentService:
    """交易 Agent 服务"""
    
    async def get_list(
        self,
        session: AsyncSession,
        user_id: str,
        status: Optional[TradingAgentStatus] = None,
    ) -> Tuple[List[TradingAgentModel], int]:
        """获取交易 Agent 列表"""
        agents = await get_trading_agents(
            session=session,
            user_id=user_id,
            status=status,
        )
        total = await count_trading_agents(
            session=session,
            user_id=user_id,
            status=status,
        )
        return agents, total
    
    async def get_by_id(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str
    ) -> Optional[TradingAgentModel]:
        """根据ID获取交易 Agent"""
        return await get_trading_agent_by_id_and_user(session, agent_id, user_id)

    async def get_trader_runtime(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        limit: int = 20,
    ) -> Optional[Dict[str, Any]]:
        """读取当前工作记忆和最近审计记录，不暴露隐藏思维链。"""
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if agent is None:
            return None
        session_id = f"live:{agent_id}"
        safe_limit = min(100, max(1, int(limit)))

        state_result = await session.execute(
            select(TraderStateModel).where(TraderStateModel.session_id == session_id)
        )
        state = state_result.scalar_one_or_none()
        turns_result = await session.execute(
            select(TraderTurnModel)
            .where(TraderTurnModel.session_id == session_id)
            .order_by(desc(TraderTurnModel.as_of))
            .limit(safe_limit)
        )
        events_result = await session.execute(
            select(TraderEventModel)
            .where(TraderEventModel.session_id == session_id)
            .order_by(desc(TraderEventModel.occurred_at))
            .limit(safe_limit)
        )
        return {
            "sessionId": session_id,
            "state": state.state_json if state else None,
            "stateRevision": state.revision if state else 0,
            "nextReviewAt": state.next_review_at.isoformat() if state and state.next_review_at else None,
            "turns": [row.turn_json for row in turns_result.scalars().all()],
            "events": [
                {
                    "id": row.id,
                    "decisionId": row.decision_id,
                    "type": row.event_type,
                    "payload": row.payload_json,
                    "occurredAt": row.occurred_at.isoformat(),
                }
                for row in events_result.scalars().all()
            ],
        }
    
    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        exchange_account_id: Optional[str] = None,
        llm_model_id: Optional[int] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        remark: Optional[str] = None
    ) -> TradingAgentModel:
        """创建交易 Agent"""
        agent = await create_trading_agent(
            session=session,
            user_id=user_id,
            name=name,
            strategy_type=StrategyType.MOMENTUM,
            exchange_account_id=exchange_account_id,
            llm_model_id=llm_model_id,
            strategy_config=strategy_config,
            remark=remark
        )
        logger.info(f"创建交易 Agent: {agent.id}, 名称: {name}, 用户: {user_id}")
        return agent
    
    async def update(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        name: Optional[str] = None,
        exchange_account_id: Optional[str] = None,
        llm_model_id: Optional[int] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        remark: Optional[str] = None
    ) -> Optional[TradingAgentModel]:
        """更新交易 Agent"""
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return None
        
        update_data = {}
        if name is not None:
            update_data['name'] = name
        if exchange_account_id is not None:
            update_data['exchange_account_id'] = exchange_account_id
        if llm_model_id is not None:
            update_data['llm_model_id'] = llm_model_id
        if strategy_config is not None:
            update_data['strategy_config'] = strategy_config
        if remark is not None:
            update_data['remark'] = remark
        
        if not update_data:
            return agent
        
        updated_agent = await update_trading_agent(session, agent_id, update_data)
        logger.info(f"更新交易 Agent: {agent_id}, 更新字段: {list(update_data.keys())}")
        return updated_agent
    
    async def delete(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str
    ) -> bool:
        """删除交易 Agent"""
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False
        
        if agent.status == TradingAgentStatus.RUNNING:
            logger.warning(f"尝试删除运行中的 Agent: {agent_id}")
            return False
        
        result = await delete_trading_agent(session, agent_id)
        if result:
            logger.info(f"删除交易 Agent: {agent_id}")
        return result
    
    async def start(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str
    ) -> Tuple[bool, str]:
        """启动交易 Agent"""
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, "Agent 不存在"
        
        if agent.status == TradingAgentStatus.RUNNING:
            return False, "Agent 已在运行中"
        
        if not agent.exchange_account_id:
            return False, "请先绑定交易所账户"
        
        from app.v1.crud.exchange_account_crud import get_exchange_account_by_id
        exchange_account = await get_exchange_account_by_id(session, agent.exchange_account_id)
        if not exchange_account:
            return False, "绑定的交易所账户不存在"
        
        if not exchange_account.enabled:
            return False, "交易所账户已禁用"
        
        if exchange_account.read_only:
            return False, "交易所账户为只读模式，无法进行实盘交易"
        
        await update_trading_agent_status(
            session=session,
            agent_id=agent_id,
            status=TradingAgentStatus.RUNNING,
            last_run_at=datetime.now()
        )
        
        await create_agent_operation(
            session=session,
            agent_id=agent_id,
            operation_type=OperationType.OTHER,
            reason="Agent 启动",
            result=OperationResult.SUCCESS,
        )
        
        from app.v1.services.live_trading_scheduler import get_live_trading_scheduler
        scheduler = get_live_trading_scheduler()
        if scheduler and scheduler.is_running:
            await scheduler.add_agent(agent_id)
            logger.info(f"启动交易 Agent 并加入调度器: {agent_id}")
        else:
            logger.info(f"启动交易 Agent (调度器未运行): {agent_id}")
        
        return True, "Agent 已启动"
    
    async def stop(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        close_positions: bool = False
    ) -> Tuple[bool, str]:
        """
        停止交易 Agent
        
        Args:
            session: 数据库会话
            agent_id: Agent ID
            user_id: 用户 ID
            close_positions: 是否平掉所有持仓
        """
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, "Agent 不存在"
        
        if agent.status == TradingAgentStatus.STOPPED:
            return False, "Agent 已停止"
        
        from app.v1.services.live_trading_scheduler import get_live_trading_scheduler
        scheduler = get_live_trading_scheduler()
        
        if close_positions and scheduler:
            runner_status = scheduler.get_agent_status(agent_id)
            if runner_status:
                try:
                    from app.v1.services.live_trading_executor import create_live_executor
                    executor = await create_live_executor(session, agent)
                    
                    cfg = agent.strategy_config or {}
                    symbols = cfg.get("symbols", [])
                    
                    for symbol in symbols:
                        await executor.cancel_all_pending_orders(symbol)
                        await executor.close_all_positions(symbol)
                    
                    logger.info(f"Agent {agent_id} 已撤销订单并平仓")
                except Exception as e:
                    logger.error(f"Agent {agent_id} 平仓失败: {e}")
        
        if scheduler and scheduler.is_running:
            await scheduler.remove_agent(agent_id)
        
        await update_trading_agent_status(
            session=session,
            agent_id=agent_id,
            status=TradingAgentStatus.STOPPED
        )
        
        await create_agent_operation(
            session=session,
            agent_id=agent_id,
            operation_type=OperationType.OTHER,
            reason=f"Agent 停止{' (已平仓)' if close_positions else ''}",
            result=OperationResult.SUCCESS,
        )
        
        logger.info(f"停止交易 Agent: {agent_id}")
        return True, "Agent 已停止"
    
    async def update_strategy_config(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        strategy_config: Dict[str, Any]
    ) -> Tuple[bool, Optional[TradingAgentModel]]:
        """更新策略配置"""
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, None
        
        updated_agent = await update_trading_agent(
            session=session,
            agent_id=agent_id,
            data={'strategy_config': strategy_config}
        )
        
        logger.info(f"更新 Agent 策略配置: {agent_id}")
        return True, updated_agent
    
    async def get_operations(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        limit: int = 50
    ) -> Tuple[List[AgentOperationModel], int]:
        """获取操作记录"""
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return [], 0
        
        operations = await get_agent_operations(
            session=session,
            agent_id=agent_id,
            limit=limit
        )
        total = await count_agent_operations(session=session, agent_id=agent_id)
        return operations, total
    
    async def get_profit_curve(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        period: Optional[str] = None
    ) -> List[AgentProfitRecordModel]:
        """获取收益曲线"""
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return []
        
        start_time = None
        if period:
            from datetime import timedelta
            now = datetime.now()
            period_map = {
                '1d': timedelta(days=1),
                '7d': timedelta(days=7),
                '30d': timedelta(days=30),
                '90d': timedelta(days=90),
            }
            if period in period_map:
                start_time = now - period_map[period]
        
        records = await get_agent_profit_records(
            session=session,
            agent_id=agent_id,
            start_time=start_time
        )
        return records

    async def build_trading_analysis_context_for_agent(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str,
        as_of: Optional[datetime] = None,
        readonly: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        按 Agent 当前 strategy_config 从数据库组装消息面/技术面文本，供实盘调度或调试调用。
        """
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return None
        cfg = agent.strategy_config or {}
        symbols = cfg.get("symbols") if isinstance(cfg.get("symbols"), list) else []
        return await build_trading_analysis_context(
            session, user_id, cfg, symbols or [], as_of=as_of, readonly=readonly
        )

    def get_live_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 Agent 的实盘运行状态
        
        Returns:
            运行状态信息，包括：
            - state: 当前状态 (idle/running/error/cooldown)
            - last_decision_time: 上次决策时间
            - next_decision_time: 下次决策时间
            - consecutive_errors: 连续错误次数
            - last_error: 最后错误信息
        """
        from app.v1.services.live_trading_scheduler import get_live_trading_scheduler
        scheduler = get_live_trading_scheduler()
        if not scheduler:
            return None
        return scheduler.get_agent_status(agent_id)

    async def get_live_account_snapshot(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取 Agent 绑定账户的实时快照
        
        Returns:
            账户快照，包括余额、持仓、价格等
        """
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return None
        
        if not agent.exchange_account_id:
            return None
        
        try:
            from app.v1.services.live_trading_executor import create_live_executor
            executor = await create_live_executor(session, agent)
            
            cfg = agent.strategy_config or {}
            symbols = cfg.get("symbols", [])
            
            snapshot = await executor.get_account_snapshot(symbols)
            
            return {
                "timestamp": snapshot.timestamp.isoformat(),
                "equity": str(snapshot.equity),
                "availableBalance": str(snapshot.available_balance),
                "positions": snapshot.positions,
                "prices": {k: str(v) for k, v in snapshot.prices.items()},
            }
        except Exception as e:
            logger.error(f"获取账户快照失败: {e}")
            return None

    async def trigger_manual_decision(
        self,
        session: AsyncSession,
        agent_id: str,
        user_id: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        手动触发一次交易决策并经过实际执行路径；不是只读分析。
        
        Returns:
            (是否成功, 消息, 决策结果)
        """
        agent = await get_trading_agent_by_id_and_user(session, agent_id, user_id)
        if not agent:
            return False, "Agent 不存在", None
        
        if agent.status != TradingAgentStatus.RUNNING:
            return False, "Agent 未运行", None
        
        try:
            from app.v1.services.live_trading_executor import create_live_executor
            from agent_applications.service_agents.trading_decision_agent import TradingDecisionAgent
            from app.v1.services.managed_llm_service import build_decision_llm
            from decision.rule_context_builder import build_rule_decision_context
            from decision.types import resolve_decision_mode
            from trader.event_store import SqlTraderEventStore
            from trader.state_store import SqlTraderStateStore
            
            executor = await create_live_executor(session, agent)
            
            cfg = agent.strategy_config or {}
            symbols = cfg.get("symbols", [])
            decision_mode = resolve_decision_mode(cfg)
            
            account_snapshot = await executor.get_account_snapshot(symbols)
            live_account = executor.build_live_account(account_snapshot)
            market_snapshot = executor.build_market_snapshot(account_snapshot)
            
            if decision_mode == "rule":
                analysis_context = build_rule_decision_context(
                    market_snapshot,
                    cfg,
                    symbols,
                )
            else:
                analysis_context = await build_trading_analysis_context(
                    session=session,
                    user_id=user_id,
                    strategy_config=cfg,
                    symbols=symbols,
                    as_of=datetime.now(),
                    market_snapshot=market_snapshot,
                )
                analysis_context["open_orders"] = list(
                    account_snapshot.pending_orders or []
                )
            
            llm = None
            managed_model_id = None
            managed_model_name = None
            if decision_mode == "trader":
                llm, managed_model_id, managed_model_name = await build_decision_llm(
                    session,
                    cfg,
                    agent_llm_model_id=agent.llm_model_id,
                )
                if managed_model_id is not None:
                    cfg = dict(cfg)
                    cfg["_managedDecisionLlmModelId"] = managed_model_id
                    cfg["_managedDecisionLlmModelName"] = managed_model_name

                cfg = dict(cfg)
                trader_config = dict(cfg.get("traderConfig") or {})
                trader_config["stateScope"] = "live"
                trader_config["sessionId"] = f"live:{agent.id}"
                cfg["traderConfig"] = trader_config

            state_store = None
            event_store = None
            if decision_mode == "trader":
                isolated_sessions = async_sessionmaker(
                    session.bind, expire_on_commit=False, autoflush=False
                )
                state_store = SqlTraderStateStore(isolated_sessions, agent.id)
                event_store = SqlTraderEventStore(isolated_sessions)
            
            decision_agent = TradingDecisionAgent(
                agent_id=agent.id,
                agent_name=f"Manual-{agent.name}",
                llm=llm,
                strategy_config=cfg,
                state_store=state_store,
                event_store=event_store,
            )
            
            decision_call = decision_agent.make_decision(
                snapshot=market_snapshot,
                account=live_account,
                risk_manager=None,
                analysis_context=analysis_context,
                decision_mode=decision_mode,
            )
            if decision_mode == "trader":
                trader_config = cfg.get("traderConfig") or {}
                try:
                    timeout_seconds = min(
                        300, max(5, int(trader_config.get("turnTimeoutSeconds") or 60))
                    )
                except (TypeError, ValueError):
                    timeout_seconds = 60
                decision = await asyncio.wait_for(decision_call, timeout=timeout_seconds)
            else:
                decision = await decision_call
            
            success, error, order_result = await executor.execute_decision(
                session=session,
                decision=decision,
                account_snapshot=account_snapshot,
            )
            
            if success:
                return True, f"决策执行成功: {decision.get('action')}", decision
            else:
                return False, f"决策执行失败: {error}", decision
                
        except Exception as e:
            logger.error(f"手动触发决策失败: {e}")
            return False, str(e), None

    def model_to_response(
        self, 
        agent: TradingAgentModel,
        exchange_info: Optional[Dict] = None,
        llm_model_info: Optional[Dict] = None
    ) -> dict:
        """将模型转换为响应格式"""
        strategy_config = None
        if agent.strategy_config:
            try:
                strategy_config = StrategyConfigSchema(**agent.strategy_config).model_dump()
            except Exception:
                strategy_config = agent.strategy_config
        
        return {
            "id": agent.id,
            "name": agent.name,
            "exchangeId": agent.exchange_account_id,
            "exchange": exchange_info.get('exchange') if exchange_info else None,
            "llmModelId": agent.llm_model_id,
            "llmModelName": llm_model_info.get('name') if llm_model_info else None,
            "status": agent.status.value,
            "remark": agent.remark,
            "lastRunAt": agent.last_run_at.isoformat() if agent.last_run_at else None,
            "createdAt": agent.created_at.isoformat(),
            "updatedAt": agent.updated_at.isoformat() if agent.updated_at else None,
            "strategyConfig": strategy_config
        }
    
    def operation_to_response(self, operation: AgentOperationModel) -> dict:
        """将操作记录模型转换为响应格式"""
        return {
            "id": operation.id,
            "agentId": operation.agent_id,
            "type": operation.type.value,
            "symbol": operation.symbol,
            "side": operation.side,
            "quantity": operation.quantity,
            "price": operation.price,
            "reason": operation.reason,
            "result": operation.result.value if operation.result else None,
            "createdAt": operation.created_at.isoformat(),
            "chainOfThought": operation.chain_of_thought
        }
    
    def profit_record_to_response(self, record: AgentProfitRecordModel) -> dict:
        """将收益记录模型转换为响应格式"""
        return {
            "time": record.record_time.isoformat(),
            "value": str(record.value),
            "cumulative": str(record.cumulative) if record.cumulative else None,
            "unrealizedPnl": str(record.unrealized_pnl) if record.unrealized_pnl is not None else None,
            "unrealizedPnlRate": str(record.unrealized_pnl_rate) if record.unrealized_pnl_rate is not None else None,
        }
