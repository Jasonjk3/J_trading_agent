#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测系统 API
"""
import re
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.database import get_db_session
from app.public.dependencies.auth import get_current_user
from app.public.dependencies.response import ApiResponse, ResponseCode
from models.inner_models.user_model import UserModel
from models.inner_models.backtest_model import BacktestStatus
from app.v1.services.backtest_service import BacktestService
from app.v1.schemas.backtest_schema import (
    CreateBacktestRequest,
    BacktestConfigSchema
)


router = APIRouter(prefix="/backtest", tags=["回测系统"])

_service = BacktestService()


def get_backtest_service() -> BacktestService:
    """获取回测服务实例"""
    return _service


_RERUN_SUFFIX_RE = re.compile(r"(\s*\(重测(?:\s\d{4}-\d{2}-\d{2}\s\d{2}:\d{2})?\))+$")


def _build_rerun_name(original_name: str) -> str:
    """重测命名：去掉已有 (重测) 后缀，追加带当前时间的单一后缀。"""
    base = _RERUN_SUFFIX_RE.sub("", (original_name or "").strip()).strip() or "回测"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"{base} (重测 {ts})"


@router.get("", summary="获取回测任务列表")
async def get_backtest_list(
    status: Optional[BacktestStatus] = Query(None, description="任务状态"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    获取当前用户的回测任务列表
    
    - **status**: 可选，筛选任务状态 (pending/running/completed/failed)
    - **page**: 页码，默认1
    - **pageSize**: 每页数量，默认20
    """
    try:
        backtests, total = await service.get_list(
            session=session,
            user_id=current_user.id,
            status=status,
            page=page,
            page_size=pageSize
        )
        
        backtest_list = [service.model_to_list_item(bt) for bt in backtests]
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"list": backtest_list, "total": total}
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取列表失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{backtest_id}", summary="获取回测任务详情")
async def get_backtest_detail(
    backtest_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    获取指定回测任务的详细信息，包括配置、结果和交易记录
    """
    try:
        detail = await service.get_detail_by_id(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id
        )
        
        if not detail:
            return ApiResponse.failed_response(
                msg="回测任务不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        backtest, compact_progress_snapshot = detail
        
        # 首屏只返回任务配置和统计；成交、曲线、决策均由独立接口按需加载。
        response_data = service.model_to_detail_response(
            backtest,
            [],
            [],
            [],
            progress_snapshot_override=compact_progress_snapshot,
        )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=response_data
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取详情失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("", summary="创建回测任务")
async def create_backtest(
    request: CreateBacktestRequest,
    req: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    创建新的回测任务
    
    创建后会自动开始执行
    """
    try:
        backtest = await service.create(
            session=session,
            user_id=current_user.id,
            name=request.name,
            config=request.config
        )
        
        await session.commit()
        
        # 在后台启动并登记任务，停止接口可据此取消实际执行协程。
        from backtest.backtest_runner import start_backtest_task
        start_backtest_task(backtest_id=backtest.id, db=req.app.state.db)
        
        return ApiResponse.success_response(
            msg="创建成功",
            data={"id": backtest.id}
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"创建失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{backtest_id}/kline", summary="获取回测决策上下文及执行区间K线")
async def get_backtest_kline(
    backtest_id: str,
    symbol: Optional[str] = Query(None, description="交易对，默认取配置中的第一个"),
    include_future: bool = Query(
        False,
        alias="includeFuture",
        description="是否读取模拟当前时刻之后、回测截止时间之前的 K 线",
    ),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    获取指定交易对的 K 线数据，包含与决策 LLM 一致的回测前置上下文。
    """
    try:
        data = await service.get_kline_data(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id,
            symbol=symbol,
            include_future=include_future,
        )
        if data is None:
            return ApiResponse.failed_response(
                msg="回测任务不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        return ApiResponse.success_response(msg="获取成功", data=data)
    except ValueError as e:
        return ApiResponse.failed_response(
            msg=str(e),
            code=ResponseCode.FAILED.value
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取K线失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{backtest_id}/progress", summary="获取回测进度")
async def get_backtest_progress(
    backtest_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    获取回测任务的执行进度
    """
    try:
        progress = await service.get_progress(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id
        )
        
        if not progress:
            return ApiResponse.failed_response(
                msg="回测任务不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        return ApiResponse.success_response(
            msg="获取成功",
            data=progress
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取进度失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/{backtest_id}/stop", summary="停止回测任务")
async def stop_backtest(
    backtest_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    停止正在执行的回测任务
    """
    try:
        success, message = await service.stop(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id
        )
        
        if not success:
            return ApiResponse.failed_response(
                msg=message,
                code=ResponseCode.FAILED.value
            )
        
        await session.commit()

        # 数据库 cancelled 状态用于跨进程协作；本进程任务句柄用于立即取消。
        from backtest.backtest_runner import cancel_backtest_task
        cancel_backtest_task(backtest_id)
        
        return ApiResponse.success_response(
            msg=message,
            data={"success": True}
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"停止失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.post("/{backtest_id}/rerun", summary="重新运行回测")
async def rerun_backtest(
    backtest_id: str,
    req: Request,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    基于现有回测配置重新创建并运行回测任务
    """
    try:
        # 获取原回测任务
        original = await service.get_by_id(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id
        )
        
        if not original:
            return ApiResponse.failed_response(
                msg="回测任务不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        # 创建新的回测任务（复制配置）
        from app.v1.schemas.backtest_schema import BacktestConfigSchema
        from app.v1.schemas.trading_agent_schema import StrategyConfigSchema
        
        # 重建配置
        strategy_config = StrategyConfigSchema(**original.strategy_config) if original.strategy_config else None
        
        config = BacktestConfigSchema(
            agentId=original.agent_id,
            agentName=original.agent_name,
            strategyConfig=strategy_config,
            startTime=original.start_time.strftime("%Y-%m-%d"),
            endTime=original.end_time.strftime("%Y-%m-%d"),
            initialCapital=float(original.initial_capital),
            exchange=original.exchange,
            symbols=original.symbols or [],
            interval=original.interval,
            makerFee=float(original.maker_fee) if original.maker_fee else 0.1,
            takerFee=float(original.taker_fee) if original.taker_fee else 0.1,
            slippage=float(original.slippage) if original.slippage else 0.05
        )
        
        # 创建新任务
        new_backtest = await service.create(
            session=session,
            user_id=current_user.id,
            name=_build_rerun_name(original.name),
            config=config
        )
        
        await session.commit()
        
        # 在后台启动并登记任务
        from backtest.backtest_runner import start_backtest_task
        start_backtest_task(backtest_id=new_backtest.id, db=req.app.state.db)
        
        return ApiResponse.success_response(
            msg="重测任务已创建",
            data={"id": new_backtest.id}
        )
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"重测失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.delete("/{backtest_id}", summary="删除回测任务")
async def delete_backtest(
    backtest_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    删除指定的回测任务
    
    注意：运行中的回测任务无法删除
    """
    try:
        success, message = await service.delete(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id
        )
        
        if not success:
            return ApiResponse.failed_response(
                msg=message,
                code=ResponseCode.FAILED.value
            )
        
        await session.commit()
        
        return ApiResponse.success_response(msg=message)
    except Exception as e:
        await session.rollback()
        return ApiResponse.failed_response(
            msg=f"删除失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{backtest_id}/trades", summary="获取回测交易明细")
async def get_backtest_trades(
    backtest_id: str,
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="时间排序"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    获取回测任务的交易明细列表
    """
    try:
        trades, total = await service.get_trades(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            order=order,
        )
        
        trade_list = [service.trade_to_response(t) for t in trades]
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={"list": trade_list, "total": total}
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取交易明细失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{backtest_id}/decisions", summary="获取回测决策明细")
async def get_backtest_decisions_api(
    backtest_id: str,
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """分页获取回测决策记录（含 hold）。"""
    try:
        decisions, total = await service.get_decisions(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id,
            skip=skip,
            limit=limit,
        )
        decision_list = [service.decision_summary_to_response(d) for d in decisions]
        return ApiResponse.success_response(
            msg="获取成功",
            data={"list": decision_list, "total": total},
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取决策明细失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get("/{backtest_id}/decisions/{decision_id}", summary="获取单条回测决策详情")
async def get_backtest_decision_api(
    backtest_id: str,
    decision_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """按需获取单条完整决策，包括 Prompt、LLM 原始响应和审计信息。"""
    try:
        decision = await service.get_decision(
            session=session,
            backtest_id=backtest_id,
            decision_id=decision_id,
            user_id=current_user.id,
        )
        if decision is None:
            return ApiResponse.failed_response(
                msg="决策记录不存在",
                code=ResponseCode.NOT_FOUND.value,
            )
        return ApiResponse.success_response(
            msg="获取成功",
            data=service.decision_to_response(decision),
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取决策详情失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get("/{backtest_id}/equity-curve", summary="获取权益曲线")
async def get_equity_curve(
    backtest_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    获取回测任务的权益曲线数据
    """
    try:
        equity_records, backtest = await service.get_equity_curve(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id
        )
        
        if backtest is None:
            return ApiResponse.failed_response(
                msg="回测任务不存在",
                code=ResponseCode.NOT_FOUND.value
            )
        
        # 构建曲线数据
        equity_curve = []
        drawdown_curve = []
        benchmark_curve = []
        
        for record in equity_records:
            time_str = record.timestamp.isoformat()
            equity_curve.append({
                "time": time_str,
                "value": float(record.equity),
                "unrealizedPnl": float(record.unrealized_pnl) if record.unrealized_pnl is not None else None,
                "unrealizedPnlRate": float(record.unrealized_pnl_rate) if record.unrealized_pnl_rate is not None else None,
            })
            drawdown_curve.append({
                "time": time_str,
                "value": float(record.drawdown) if record.drawdown else 0
            })
            if record.benchmark:
                benchmark_curve.append({
                    "time": time_str,
                    "value": float(record.benchmark)
                })

        # 兼容尚未增量落库的旧失败任务：仅在专用曲线接口中读取快照曲线。
        if not equity_records:
            progress_data = await service.get_progress(
                session=session,
                backtest_id=backtest_id,
                user_id=current_user.id,
            )
            live_preview = (progress_data or {}).get("livePreview") or {}
            if isinstance(live_preview, dict):
                equity_curve = live_preview.get("equityCurve") or []
                drawdown_curve = live_preview.get("drawdownCurve") or []
                benchmark_curve = live_preview.get("benchmarkCurve") or []
        
        return ApiResponse.success_response(
            msg="获取成功",
            data={
                "equityCurve": equity_curve,
                "drawdownCurve": drawdown_curve,
                "benchmarkCurve": benchmark_curve
            }
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"获取权益曲线失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )


@router.get("/{backtest_id}/export", summary="导出回测报告")
async def export_backtest_report(
    backtest_id: str,
    format: str = Query("csv", description="导出格式: csv/pdf"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service)
):
    """
    导出回测报告
    
    - **format**: 目前支持 csv；pdf 暂未实现
    """
    try:
        from fastapi.responses import StreamingResponse
        from urllib.parse import quote

        fmt = (format or "csv").lower().strip()
        if fmt == "pdf":
            return ApiResponse.failed_response(
                msg="PDF 导出暂未实现，请使用 CSV",
                code=ResponseCode.FAILED.value,
            )
        if fmt != "csv":
            return ApiResponse.failed_response(
                msg="不支持的导出格式，请使用 csv",
                code=ResponseCode.FAILED.value,
            )

        payload = await service.build_export_csv(
            session=session,
            backtest_id=backtest_id,
            user_id=current_user.id,
        )
        if payload is None:
            return ApiResponse.failed_response(
                msg="回测任务不存在",
                code=ResponseCode.NOT_FOUND.value,
            )
        if payload.get("error"):
            return ApiResponse.failed_response(
                msg=payload["error"],
                code=ResponseCode.FAILED.value,
            )

        content: bytes = payload["content"]
        filename: str = payload["filename"]
        encoded = quote(filename)

        return StreamingResponse(
            iter([content]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            },
        )
    except Exception as e:
        return ApiResponse.failed_response(
            msg=f"导出失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value
        )
