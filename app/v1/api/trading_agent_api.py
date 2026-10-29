#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
交易 Agent 管理 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.database import get_db_session
from app.public.dependencies.auth import get_current_user
from app.public.dependencies.response import ApiResponse, ResponseCode
from models.inner_models.user_model import UserModel
from models.inner_models.trading_agent_model import TradingAgentStatus
from app.v1.services.trading_agent_service import TradingAgentService
from app.v1.schemas.trading_agent_schema import (
    CreateTradingAgentRequest,
    UpdateTradingAgentRequest,
    UpdateStrategyConfigRequest,
    StrategyConfigSchema
)


router = APIRouter(prefix="/trading-agents", tags=["交易Agent管理"])

_service = TradingAgentService()


def get_trading_agent_service() -> TradingAgentService:
    """获取交易 Agent 服务实例"""
    return _service


@router.get("", summary="获取交易 Agent 列表")
async def get_trading_agent_list(
    status: Optional[TradingAgentStatus] = Query(None, description="运行状态"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取当前用户的交易 Agent 列表
    
    - **status**: 可选，筛选运行状态 (running/stopped)
    """
    try:
        agents, total = await service.get_list(
            session=session,
            user_id=current_user.id,
            status=status,
        )
        
        agent_list = [service.model_to_response(agent) for agent in agents]
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"list": agent_list, "total": total}
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}", summary="获取交易 Agent 详情")
async def get_trading_agent_detail(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取指定交易 Agent 的详细信息
    """
    try:
        agent = await service.get_by_id(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not agent:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=service.model_to_response(agent)
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取详情失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("", summary="创建交易 Agent")
async def create_trading_agent(
    request: CreateTradingAgentRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    创建新的交易 Agent
    """
    try:
        strategy_config = None
        if request.strategyConfig:
            strategy_config = request.strategyConfig.model_dump()
        
        agent = await service.create(
            session=session,
            user_id=current_user.id,
            name=request.name,
            exchange_account_id=request.exchangeId,
            llm_model_id=request.llmModelId,
            strategy_config=strategy_config,
            remark=request.remark
        )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="创建成功",
            data=service.model_to_response(agent)
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/{agent_id}", summary="更新交易 Agent")
async def update_trading_agent(
    agent_id: str,
    request: UpdateTradingAgentRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    更新指定交易 Agent 的信息
    """
    try:
        strategy_config = None
        if request.strategyConfig:
            strategy_config = request.strategyConfig.model_dump()
        
        agent = await service.update(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id,
            name=request.name,
            exchange_account_id=request.exchangeId,
            llm_model_id=request.llmModelId,
            strategy_config=strategy_config,
            remark=request.remark
        )
        
        if not agent:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="更新成功",
            data=service.model_to_response(agent)
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"更新失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/{agent_id}", summary="删除交易 Agent")
async def delete_trading_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    删除指定交易 Agent
    
    注意：运行中的 Agent 无法删除，需要先停止
    """
    try:
        result = await service.delete(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not result:
            return ApiResponse.failed_response(
                msg="Agent 不存在或正在运行中",
                code=ResponseCode.FAILED.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(msg="删除成功")
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/{agent_id}/start", summary="启动交易 Agent")
async def start_trading_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    启动指定交易 Agent
    """
    try:
        success, message = await service.start(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not success:
            return ApiResponse.failed_response(
                msg=message,
                code=ResponseCode.FAILED.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg=message,
            data={"success": True, "message": message}
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"启动失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/{agent_id}/stop", summary="停止交易 Agent")
async def stop_trading_agent(
    agent_id: str,
    close_positions: bool = Query(False, description="是否同时平掉所有持仓"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    停止指定交易 Agent
    
    - **close_positions**: 是否同时平掉所有持仓并撤销未成交订单
    """
    try:
        success, message = await service.stop(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id,
            close_positions=close_positions
        )
        
        if not success:
            return ApiResponse.failed_response(
                msg=message,
                code=ResponseCode.FAILED.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg=message,
            data={"success": True, "message": message}
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"停止失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/live-status", summary="获取实盘运行状态")
async def get_live_status(
    agent_id: str,
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取 Agent 的实盘运行状态
    
    返回：
    - **state**: 当前状态 (idle/running/error/cooldown)
    - **lastDecisionTime**: 上次决策时间
    - **nextDecisionTime**: 下次预计决策时间
    - **consecutiveErrors**: 连续错误次数
    - **lastError**: 最后一次错误信息
    - **cooldownUntil**: 冷却结束时间（如果处于冷却状态）
    """
    try:
        status = service.get_live_status(agent_id)
        
        if not status:
            return ApiResponse.success_response(
                msg="获取成功",
                data={
                    "inScheduler": False,
                    "message": "Agent 未在调度器中运行"
                }
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "inScheduler": True,
                "state": status.get("state"),
                "lastDecisionTime": status.get("last_decision_time"),
                "nextDecisionTime": status.get("next_decision_time"),
                "consecutiveErrors": status.get("consecutive_errors"),
                "lastError": status.get("last_error"),
                "cooldownUntil": status.get("cooldown_until"),
            }
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取状态失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/account-snapshot", summary="获取实时账户快照")
async def get_account_snapshot(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取 Agent 绑定交易所账户的实时快照
    
    返回：
    - **timestamp**: 快照时间
    - **equity**: 账户总权益
    - **availableBalance**: 可用余额
    - **positions**: 当前持仓列表
    - **prices**: 配置交易对的当前价格
    """
    try:
        snapshot = await service.get_live_account_snapshot(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not snapshot:
            return ApiResponse.failed_response(
                msg="无法获取账户快照，请检查 Agent 是否绑定了交易所账户",
                code=ResponseCode.FAILED.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=snapshot
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取账户快照失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/trader-runtime", summary="获取 AI 交易员当前状态与审计事件")
async def get_trader_runtime(
    agent_id: str,
    limit: int = Query(20, ge=1, le=100, description="回合和事件返回数量"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service),
):
    """返回结构化工作记忆、最近 TraderTurn 和事件，不返回隐藏思维链。"""
    try:
        runtime = await service.get_trader_runtime(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id,
            limit=limit,
        )
        if runtime is None:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value,
            )
        return ApiResponse.success_response(msg="获取成功", data=runtime)
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取交易员状态失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.post("/{agent_id}/trigger-decision", summary="触发交易决策并执行（可能下单）")
async def trigger_manual_decision(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    手动触发一次决策执行
    
    用于测试或紧急情况下手动触发 Agent 进行一次决策。
    Agent 必须处于运行状态才能触发。
    
    返回决策结果，包括 action、reason、confidence 等。
    """
    try:
        success, message, decision = await service.trigger_manual_decision(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        await session.commit()
        
        if not success:
            return ApiResponse.failed_response(
                msg=message,
                code=ResponseCode.FAILED.value
            )
        
        return ApiResponse.success_response(
            msg=message,
            data={
                "success": True,
                "decision": decision
            }
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"触发决策失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/strategy-config", summary="获取策略配置")
async def get_strategy_config(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取指定 Agent 的策略配置
    返回用户配置的简化参数
    """
    try:
        agent = await service.get_by_id(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not agent:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"strategyConfig": agent.strategy_config}
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取策略配置失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/strategy-config/full", summary="获取完整策略配置（含推导参数）")
async def get_full_strategy_config(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取指定 Agent 的完整策略配置
    包含用户配置的简化参数以及系统自动推导的详细参数
    
    推导参数包括：
    - maxPositionRatio: 最大持仓比例
    - maxDailyTrades: 单日最大交易次数
    - priceDeviationUpper/Lower: 挂单价格偏离范围
    - leverage: 杠杆倍数
    - holdingPeriodHours: 预期持仓时长
    - analysisTimeframe: 分析K线周期
    - signalSensitivity: 信号敏感度
    - targetProfitAmount: 目标利润绝对值
    - targetProfitPercentage: 目标利润百分比
    """
    try:
        agent = await service.get_by_id(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not agent:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        # 获取用户配置
        user_config = agent.strategy_config or {}
        
        # 转换为 Schema 并获取推导参数
        from app.v1.schemas.trading_agent_schema import StrategyConfigSchema
        try:
            config_schema = StrategyConfigSchema(**user_config)
            derived_params = config_schema.get_derived_params()
        except Exception:
            derived_params = {}
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "userConfig": user_config,
                "derivedParams": derived_params,
                "fullConfig": {**user_config, **derived_params}
            }
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取完整策略配置失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.put("/{agent_id}/strategy-config", summary="更新策略配置")
async def update_strategy_config(
    agent_id: str,
    request: UpdateStrategyConfigRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    更新指定 Agent 的策略配置
    """
    try:
        strategy_config = request.strategyConfig.model_dump()
        
        success, agent = await service.update_strategy_config(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id,
            strategy_config=strategy_config
        )
        
        if not success:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(
            msg="更新成功",
            data={"success": True}
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"更新策略配置失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/profit-curve", summary="获取收益曲线")
async def get_profit_curve(
    agent_id: str,
    period: Optional[str] = Query(None, description="时间周期: 1d/7d/30d/90d"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取指定 Agent 的收益曲线数据
    """
    try:
        records = await service.get_profit_curve(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id,
            period=period
        )
        
        points = [service.profit_record_to_response(r) for r in records]
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"points": points, "period": period}
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取收益曲线失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/operations", summary="获取操作记录")
async def get_operations(
    agent_id: str,
    limit: int = Query(50, description="返回数量限制"),
    period: Optional[str] = Query(None, description="时间周期: 1d/7d/30d/90d"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取指定 Agent 的操作记录（含思维链）
    """
    try:
        operations, total = await service.get_operations(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id,
            limit=limit
        )
        
        operation_list = [service.operation_to_response(op) for op in operations]
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"list": operation_list, "total": total}
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取操作记录失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/positions", summary="获取当前持仓")
async def get_positions(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取 Agent 绑定账户的当前持仓信息
    
    返回持仓列表，每个持仓包含：
    - symbol: 交易对
    - side: 持仓方向 (long/short)
    - size: 持仓数量
    - avgPrice: 开仓均价
    - unrealizedPnl: 未实现盈亏
    - unrealizedPnlRatio: 未实现盈亏比例
    - leverage: 杠杆倍数
    - liquidationPrice: 强平价格
    """
    try:
        agent = await service.get_by_id(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not agent:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        if not agent.exchange_account_id:
            return ApiResponse.success_response(
                msg="获取成功",
                data={"list": [], "total": 0, "message": "Agent 未绑定交易所账户"}
            )
        
        try:
            from app.v1.services.live_trading_executor import create_live_executor
            executor = await create_live_executor(session, agent)
            
            cfg = agent.strategy_config or {}
            symbols = cfg.get("symbols", [])
            
            positions = []
            for symbol in symbols:
                okx_symbol = executor._normalize_symbol(symbol)
                try:
                    pos_list = await executor.trading_service.get_position_info(okx_symbol)
                    for pos in pos_list:
                        positions.append({
                            "symbol": symbol,
                            "instId": pos.get("instId"),
                            "side": pos.get("posSide"),
                            "size": pos.get("pos"),
                            "avgPrice": pos.get("avgPx"),
                            "unrealizedPnl": pos.get("upl"),
                            "unrealizedPnlRatio": pos.get("uplRatio"),
                            "leverage": pos.get("lever"),
                            "liquidationPrice": pos.get("liqPx"),
                            "margin": pos.get("margin"),
                        })
                except Exception:
                    pass
            
            return ApiResponse.success_response(
                msg="获取成功",
                data={"list": positions, "total": len(positions)}
            )
        except Exception as e:
            return ApiResponse.success_response(
                msg="获取成功",
                data={"list": [], "total": 0, "message": f"获取持仓失败: {str(e)}"}
            )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取持仓失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{agent_id}/orders", summary="获取订单记录")
async def get_orders(
    agent_id: str,
    page: int = Query(1, description="页码"),
    pageSize: int = Query(20, description="每页数量"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: TradingAgentService = Depends(get_trading_agent_service)
):
    """
    获取 Agent 的订单记录
    
    返回订单列表，包含历史订单和未成交订单。
    """
    try:
        agent = await service.get_by_id(
            session=session,
            agent_id=agent_id,
            user_id=current_user.id
        )
        
        if not agent:
            return ApiResponse.failed_response(
                msg="Agent 不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        if not agent.exchange_account_id:
            return ApiResponse.success_response(
                msg="获取成功",
                data={"list": [], "total": 0, "page": page, "pageSize": pageSize, "message": "Agent 未绑定交易所账户"}
            )
        
        try:
            from app.v1.services.live_trading_executor import create_live_executor
            executor = await create_live_executor(session, agent)
            
            cfg = agent.strategy_config or {}
            symbols = cfg.get("symbols", [])
            
            all_orders = []
            for symbol in symbols:
                okx_symbol = executor._normalize_symbol(symbol)
                
                try:
                    pending = await executor.trading_service.get_pending_orders(okx_symbol)
                    for order in pending:
                        all_orders.append({
                            "orderId": order.get("ordId"),
                            "symbol": symbol,
                            "instId": order.get("instId"),
                            "side": order.get("side"),
                            "posSide": order.get("posSide"),
                            "orderType": order.get("ordType"),
                            "size": order.get("sz"),
                            "price": order.get("px"),
                            "state": order.get("state", "live"),
                            "filledSize": order.get("accFillSz"),
                            "avgFilledPrice": order.get("avgPx"),
                            "fee": order.get("fee"),
                            "pnl": order.get("pnl"),
                            "createdAt": order.get("cTime"),
                            "updatedAt": order.get("uTime"),
                        })
                except Exception:
                    pass
                
                try:
                    history = await executor.trading_service.api.get_orders_history(
                        inst_type="SWAP",
                        inst_id=okx_symbol,
                        limit=str(pageSize)
                    )
                    for order in history:
                        all_orders.append({
                            "orderId": order.get("ordId"),
                            "symbol": symbol,
                            "instId": order.get("instId"),
                            "side": order.get("side"),
                            "posSide": order.get("posSide"),
                            "orderType": order.get("ordType"),
                            "size": order.get("sz"),
                            "price": order.get("px"),
                            "state": order.get("state"),
                            "filledSize": order.get("accFillSz"),
                            "avgFilledPrice": order.get("avgPx"),
                            "fee": order.get("fee"),
                            "pnl": order.get("pnl"),
                            "createdAt": order.get("cTime"),
                            "updatedAt": order.get("uTime"),
                        })
                except Exception:
                    pass
            
            all_orders.sort(key=lambda x: x.get("createdAt", "0"), reverse=True)
            
            start = (page - 1) * pageSize
            end = start + pageSize
            paged_orders = all_orders[start:end]
            
            return ApiResponse.success_response(
                msg="获取成功",
                data={
                    "list": paged_orders,
                    "total": len(all_orders),
                    "page": page,
                    "pageSize": pageSize
                }
            )
        except Exception as e:
            return ApiResponse.success_response(
                msg="获取成功",
                data={"list": [], "total": 0, "page": page, "pageSize": pageSize, "message": f"获取订单失败: {str(e)}"}
            )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取订单失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/preview-config", summary="预览策略配置推导结果")
async def preview_strategy_config(
    request: StrategyConfigSchema,
    current_user: UserModel = Depends(get_current_user)
):
    """
    预览策略配置的推导结果
    
    用户可以在创建 Agent 前，通过此接口预览系统会如何根据简化参数推导详细的交易策略参数。
    
    **简化配置参数说明：**
    
    1. **symbols** - 交易对列表，如 ["BTCUSDT", "ETHUSDT"]
    2. **tradingStyle** - 交易风格
       - aggressive: 激进（高频率、高仓位、高杠杆）
       - balanced: 均衡（适中的风险收益比）
       - conservative: 稳定（低频率、低仓位、无杠杆）
    3. **initialCapital** - 初始本金(USDT)
    4. **targetProfit** - 目标利润配置
       - type: "fixed"(固定金额) 或 "percentage"(本金百分比)
       - value: 对应的数值
    5. **tradingCycle** - 交易周期
       - short_term: 短线（日内/几天，1小时K线分析）
       - medium_term: 中线（数周，4小时K线分析）
       - long_term: 长线（数月，日K线分析）
    6. **minOrderAmount / maxOrderAmount** - 单次交易金额上下限(USDT)
    """
    try:
        # 获取推导参数
        derived_params = request.get_derived_params()
        user_config = request.model_dump()
        
        return ApiResponse.success_response(
            msg="预览成功",
            data={
                "userConfig": user_config,
                "derivedParams": derived_params,
                "fullConfig": {**user_config, **derived_params},
                "explanation": {
                    "tradingStyle": _get_style_explanation(request.tradingStyle),
                    "tradingCycle": _get_cycle_explanation(request.tradingCycle),
                    "targetProfit": _get_profit_explanation(request.targetProfit, request.initialCapital)
                }
            }
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"预览失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


def _get_style_explanation(style) -> str:
    """获取交易风格说明"""
    from models.inner_models.trading_agent_model import TradingStyle
    explanations = {
        TradingStyle.AGGRESSIVE: "激进模式：最大持仓50%，单日最多100笔交易，默认5倍杠杆，追求高收益高风险",
        TradingStyle.BALANCED: "均衡模式：最大持仓30%，单日最多50笔交易，默认2倍杠杆，平衡风险收益",
        TradingStyle.CONSERVATIVE: "稳定模式：最大持仓20%，单日最多20笔交易，无杠杆，追求稳健收益"
    }
    return explanations.get(style, "")


def _get_cycle_explanation(cycle) -> str:
    """获取交易周期说明"""
    from models.inner_models.trading_agent_model import TradingCycle
    explanations = {
        TradingCycle.SHORT_TERM: "短线交易：基于1小时K线分析，预期持仓1天内，高敏感度信号",
        TradingCycle.MEDIUM_TERM: "中线交易：基于4小时K线分析，预期持仓约1周，中等敏感度信号",
        TradingCycle.LONG_TERM: "长线交易：基于日K线分析，预期持仓约1个月，低敏感度信号"
    }
    return explanations.get(cycle, "")


def _get_profit_explanation(target_profit, initial_capital: float) -> str:
    """获取目标利润说明"""
    if target_profit.type == "percentage":
        amount = initial_capital * target_profit.value / 100
        return f"目标利润：本金的{target_profit.value}%，即{amount:.2f} USDT"
    else:
        percentage = (target_profit.value / initial_capital) * 100
        return f"目标利润：{target_profit.value:.2f} USDT，占本金的{percentage:.2f}%"
