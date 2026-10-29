#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测系统服务
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.inner_models.backtest_model import (
    BacktestTaskModel,
    BacktestStatus,
    KlineInterval,
    BacktestTradeModel,
    BacktestEquityModel,
    BacktestDecisionModel,
)
from app.v1.crud.backtest_crud import (
    get_backtests,
    get_backtest_by_id,
    get_backtest_by_id_and_user,
    get_backtest_detail_by_id_and_user,
    get_backtest_progress_by_id_and_user,
    get_backtest_current_time,
    count_backtests,
    create_backtest,
    update_backtest,
    update_backtest_status,
    update_backtest_result,
    delete_backtest,
    get_backtest_trades,
    count_backtest_trades,
    get_backtest_equity_records,
    get_backtest_decisions,
    get_backtest_decision_by_id_and_user,
    count_backtest_decisions,
    batch_create_backtest_trades,
    batch_create_backtest_equity
)
from app.v1.schemas.backtest_schema import (
    BacktestConfigSchema,
    BacktestStatisticsSchema,
    BacktestTradeItem,
    TimeSeriesPoint
)


class BacktestService:
    """回测系统服务"""
    
    async def get_list(
        self,
        session: AsyncSession,
        user_id: str,
        status: Optional[BacktestStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[BacktestTaskModel], int]:
        """获取回测任务列表"""
        skip = (page - 1) * page_size
        backtests = await get_backtests(
            session=session,
            user_id=user_id,
            status=status,
            skip=skip,
            limit=page_size
        )
        total = await count_backtests(
            session=session,
            user_id=user_id,
            status=status,
        )
        return backtests, total
    
    async def get_by_id(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str
    ) -> Optional[BacktestTaskModel]:
        """根据ID获取回测任务"""
        return await get_backtest_by_id_and_user(session, backtest_id, user_id)

    async def get_detail_by_id(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str,
    ) -> Optional[Tuple[BacktestTaskModel, Dict[str, Any]]]:
        """获取详情主体与不含完整决策正文的轻量进度快照。"""
        return await get_backtest_detail_by_id_and_user(
            session, backtest_id, user_id
        )
    
    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        config: BacktestConfigSchema
    ) -> BacktestTaskModel:
        """创建回测任务"""
        # 解析日期
        start_time = datetime.strptime(config.startTime, "%Y-%m-%d") if isinstance(config.startTime, str) else config.startTime
        end_time = datetime.strptime(config.endTime, "%Y-%m-%d") if isinstance(config.endTime, str) else config.endTime
        
        # 转换策略配置为字典
        strategy_config_dict = config.strategyConfig.model_dump() if config.strategyConfig else {}
        strategy_config_dict.update({
            "marketImpactBps": config.marketImpactBps,
            "impactVolatilityWeight": config.impactVolatilityWeight,
            "maxImpactPct": config.maxImpactPct,
            "maxParticipationRate": config.maxParticipationRate,
            "fundingRatePerInterval": config.fundingRatePerInterval,
            "fundingIntervalHours": config.fundingIntervalHours,
        })
        
        backtest = await create_backtest(
            session=session,
            user_id=user_id,
            name=name,
            agent_id=config.agentId,
            agent_name=config.agentName,
            strategy_type="momentum",
            strategy_config=strategy_config_dict,
            exchange=config.exchange,
            symbols=config.symbols,
            interval=config.interval,
            start_time=start_time,
            end_time=end_time,
            initial_capital=Decimal(str(config.initialCapital)),
            maker_fee=Decimal(str(config.makerFee)),
            taker_fee=Decimal(str(config.takerFee)),
            slippage=Decimal(str(config.slippage))
        )
        
        logger.info(f"创建回测任务: {backtest.id}, 名称: {name}, 用户: {user_id}")
        return backtest
    
    async def get_progress(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """获取回测进度"""
        progress_row = await get_backtest_progress_by_id_and_user(
            session, backtest_id, user_id
        )
        if not progress_row:
            return None

        status = progress_row["status"]
        snap_raw = progress_row.get("progress_snapshot")
        snap = dict(snap_raw) if isinstance(snap_raw, dict) else {}
        live_preview_raw = snap.get("livePreview")
        if isinstance(live_preview_raw, dict):
            live_preview = dict(live_preview_raw)
            decision_log = live_preview.get("decisionLog")
            if isinstance(decision_log, list):
                summary_keys = {
                    "id", "timestamp", "action", "errorType", "symbol",
                    "quantity", "currentPrice", "reasoning", "decisionAnalysis",
                    "decisionMode", "outcomeType", "regime", "signals",
                    "executionResult",
                }
                live_preview["decisionLog"] = [
                    {
                        key: value
                        for key, value in row.items()
                        if key in summary_keys
                    }
                    for row in decision_log
                    if isinstance(row, dict)
                ]
            snap["livePreview"] = live_preview
        msg = snap.get("message") if status == BacktestStatus.RUNNING else None
        if not msg:
            if status == BacktestStatus.PENDING:
                msg = "等待执行..."
            elif status == BacktestStatus.RUNNING:
                msg = f"正在回测... {progress_row.get('progress') or 0}%"
            elif status == BacktestStatus.COMPLETED:
                msg = "回测完成"
            elif status == BacktestStatus.FAILED:
                msg = f"回测失败: {progress_row.get('error_message') or '未知错误'}"
            elif status == BacktestStatus.CANCELLED:
                msg = "回测已取消"
            else:
                msg = ""
        return {
            "status": status.value,
            "progress": progress_row.get("progress") or 0,
            "currentTime": snap.get("currentTime"),
            "message": msg,
            "currentStep": snap.get("currentStep"),
            "totalSteps": snap.get("totalSteps"),
            "intervalSeconds": snap.get("intervalSeconds"),
            "livePreview": snap.get("livePreview"),
        }
    
    def _get_progress_message(self, backtest: BacktestTaskModel) -> str:
        """获取进度消息"""
        if backtest.status == BacktestStatus.PENDING:
            return "等待执行..."
        elif backtest.status == BacktestStatus.RUNNING:
            return f"正在回测... {backtest.progress}%"
        elif backtest.status == BacktestStatus.COMPLETED:
            return "回测完成"
        elif backtest.status == BacktestStatus.FAILED:
            return f"回测失败: {backtest.error_message or '未知错误'}"
        elif backtest.status == BacktestStatus.CANCELLED:
            return "回测已取消"
        return ""
    
    async def stop(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str
    ) -> Tuple[bool, str]:
        """停止回测任务"""
        backtest = await get_backtest_by_id_and_user(session, backtest_id, user_id)
        if not backtest:
            return False, "回测任务不存在"
        
        if backtest.status not in (BacktestStatus.PENDING, BacktestStatus.RUNNING):
            return False, f"无法停止状态为 {backtest.status.value} 的回测"
        
        await update_backtest_status(
            session=session,
            backtest_id=backtest_id,
            status=BacktestStatus.CANCELLED,
            error_message="用户手动停止"
        )
        
        logger.info(f"停止回测任务: {backtest_id}")
        return True, "回测已停止"
    
    async def delete(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str
    ) -> Tuple[bool, str]:
        """删除回测任务"""
        backtest = await get_backtest_by_id_and_user(session, backtest_id, user_id)
        if not backtest:
            return False, "回测任务不存在"
        
        if backtest.status == BacktestStatus.RUNNING:
            return False, "无法删除运行中的回测"
        
        result = await delete_backtest(session, backtest_id)
        if result:
            logger.info(f"删除回测任务: {backtest_id}")
            return True, "删除成功"
        return False, "删除失败"
    
    async def get_trades(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 1000,
        order: str = "asc",
    ) -> Tuple[List[BacktestTradeModel], int]:
        """获取回测交易记录"""
        backtest = await get_backtest_by_id_and_user(session, backtest_id, user_id)
        if not backtest:
            return [], 0
        
        trades = await get_backtest_trades(
            session=session,
            backtest_id=backtest_id,
            skip=skip,
            limit=limit,
            order=order,
        )
        total = await count_backtest_trades(session=session, backtest_id=backtest_id)
        return trades, total

    async def get_decisions(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 1000,
    ) -> Tuple[List[BacktestDecisionModel], int]:
        """分页获取回测决策记录"""
        backtest = await get_backtest_by_id_and_user(session, backtest_id, user_id)
        if not backtest:
            return [], 0

        decisions = await get_backtest_decisions(
            session=session,
            backtest_id=backtest_id,
            skip=skip,
            limit=limit,
        )
        total = await count_backtest_decisions(session=session, backtest_id=backtest_id)
        return decisions, total

    async def get_decision(
        self,
        session: AsyncSession,
        backtest_id: str,
        decision_id: str,
        user_id: str,
    ) -> Optional[BacktestDecisionModel]:
        """按需获取一条完整决策详情。"""
        return await get_backtest_decision_by_id_and_user(
            session, backtest_id, decision_id, user_id
        )

    def decision_to_response(self, decision: BacktestDecisionModel) -> dict:
        """将决策记录模型转换为响应格式"""
        rule_meta = self._extract_rule_audit(decision.chain_of_thought)
        llm_meta = self._extract_llm_audit(decision.chain_of_thought)
        row = {
            "id": decision.id,
            "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
            "action": decision.action,
            "symbol": decision.symbol,
            "quantity": float(decision.quantity) if decision.quantity is not None else None,
            "reasoning": decision.reasoning,
            "decisionAnalysis": decision.decision_analysis or decision.reasoning,
            "technicalAnalysis": decision.technical_analysis,
            "chainOfThought": decision.chain_of_thought or [],
            "currentPrice": float(decision.reference_price) if decision.reference_price is not None else None,
            "executionResult": decision.execution_result,
        }
        row.update(llm_meta)
        row.update(rule_meta)
        if not row.get("decisionMode") and row.get("decisionPrompt"):
            row["decisionMode"] = "trader"
        return row

    @staticmethod
    def decision_summary_to_response(decision: BacktestDecisionModel) -> dict:
        """决策列表摘要；完整审计字段只由单条详情接口返回。"""
        return {
            "id": decision.id,
            "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
            "action": decision.action,
            "symbol": decision.symbol,
            "quantity": float(decision.quantity) if decision.quantity is not None else None,
            "reasoning": decision.reasoning,
            "decisionAnalysis": decision.decision_analysis or decision.reasoning,
            "currentPrice": float(decision.reference_price) if decision.reference_price is not None else None,
            "executionResult": decision.execution_result,
        }

    async def build_export_csv(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """构建 CSV 导出内容（含摘要与全部成交）。"""
        import csv
        import io

        backtest = await get_backtest_by_id_and_user(session, backtest_id, user_id)
        if not backtest:
            return None
        if backtest.status != BacktestStatus.COMPLETED:
            return {"error": "只能导出已完成的回测报告"}

        trades = await get_backtest_trades(session, backtest_id, skip=0, limit=None)
        stats = backtest.result_statistics or {}

        buf = io.StringIO()
        writer = csv.writer(buf)

        writer.writerow(["section", "key", "value"])
        writer.writerow(["meta", "id", backtest.id])
        writer.writerow(["meta", "name", backtest.name])
        writer.writerow(["meta", "agentName", backtest.agent_name or ""])
        writer.writerow(["meta", "exchange", backtest.exchange or ""])
        writer.writerow(["meta", "symbols", ",".join(backtest.symbols or [])])
        writer.writerow(["meta", "interval", backtest.interval.value if backtest.interval else ""])
        writer.writerow(["meta", "startTime", backtest.start_time.isoformat() if backtest.start_time else ""])
        writer.writerow(["meta", "endTime", backtest.end_time.isoformat() if backtest.end_time else ""])
        writer.writerow(["meta", "initialCapital", float(backtest.initial_capital)])
        writer.writerow(["meta", "completedAt", backtest.completed_at.isoformat() if backtest.completed_at else ""])

        for key in (
            "totalReturn",
            "annualizedReturn",
            "maxDrawdown",
            "sharpeRatio",
            "winRate",
            "profitFactor",
            "totalTrades",
            "closedTrades",
            "winTrades",
            "lossTrades",
            "finalCapital",
            "balanceAtEnd",
            "unrealizedPnlTotal",
        ):
            if key in stats and stats[key] is not None:
                writer.writerow(["statistics", key, stats[key]])

        writer.writerow([])
        writer.writerow([
            "timestamp",
            "symbol",
            "side",
            "type",
            "action",
            "price",
            "quantity",
            "amount",
            "fee",
            "pnl",
            "pnlPercent",
            "balance",
            "reasoning",
        ])
        for trade in trades:
            writer.writerow([
                trade.timestamp.isoformat() if trade.timestamp else "",
                trade.symbol,
                trade.side,
                trade.trade_type,
                trade.action or "",
                float(trade.price),
                float(trade.quantity),
                float(trade.amount),
                float(trade.fee),
                float(trade.pnl),
                float(trade.pnl_percent),
                float(trade.balance),
                (trade.reasoning or "").replace("\n", " ").strip(),
            ])

        # utf-8-sig 便于 Excel 直接打开
        content = buf.getvalue().encode("utf-8-sig")
        safe_name = (backtest.name or "backtest").replace("/", "-").replace("\\", "-")
        filename = f"{safe_name}_{backtest_id[:8]}.csv"
        return {"content": content, "filename": filename}
    
    async def get_equity_curve(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str
    ) -> Tuple[List[BacktestEquityModel], Optional[BacktestTaskModel]]:
        """获取权益曲线数据"""
        backtest = await get_backtest_by_id_and_user(session, backtest_id, user_id)
        if not backtest:
            return [], None
        
        records = await get_backtest_equity_records(
            session=session,
            backtest_id=backtest_id
        )
        return records, backtest
    
    def model_to_list_item(self, backtest: BacktestTaskModel) -> dict:
        """将模型转换为列表项响应格式"""
        # 从结果统计中提取收益指标
        total_return = None
        max_drawdown = None
        win_rate = None
        
        if backtest.result_statistics:
            stats = backtest.result_statistics
            total_return = stats.get('totalReturn')
            max_drawdown = stats.get('maxDrawdown')
            win_rate = stats.get('winRate')
        
        return {
            "id": backtest.id,
            "name": backtest.name,
            "status": backtest.status.value,
            "agentId": backtest.agent_id,
            "agentName": backtest.agent_name,
            "exchange": backtest.exchange,
            "symbols": backtest.symbols or [],
            "startTime": backtest.start_time.strftime("%Y-%m-%d"),
            "endTime": backtest.end_time.strftime("%Y-%m-%d"),
            "initialCapital": float(backtest.initial_capital),
            "totalReturn": total_return,
            "maxDrawdown": max_drawdown,
            "winRate": win_rate,
            "createdAt": backtest.created_at.isoformat(),
            "completedAt": backtest.completed_at.isoformat() if backtest.completed_at else None
        }
    
    def model_to_detail_response(
        self,
        backtest: BacktestTaskModel,
        trades: List[BacktestTradeModel],
        equity_records: List[BacktestEquityModel],
        decision_records: Optional[List] = None,
        progress_snapshot_override: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """将模型转换为详情响应格式"""
        # 构建配置
        from app.v1.schemas.trading_agent_schema import StrategyConfigSchema
        
        strategy_config = None
        runtime_cost_config = dict(backtest.strategy_config or {})
        if backtest.strategy_config:
            try:
                strategy_config = StrategyConfigSchema(**backtest.strategy_config).model_dump()
            except Exception:
                strategy_config = backtest.strategy_config
        
        config = {
            "agentId": backtest.agent_id,
            "agentName": backtest.agent_name,
            "strategyConfig": strategy_config,
            "startTime": backtest.start_time.strftime("%Y-%m-%d"),
            "endTime": backtest.end_time.strftime("%Y-%m-%d"),
            "initialCapital": float(backtest.initial_capital),
            "exchange": backtest.exchange,
            "symbols": backtest.symbols or [],
            "interval": backtest.interval.value if backtest.interval else "15m",
            "makerFee": float(backtest.maker_fee) if backtest.maker_fee is not None else 0.1,
            "takerFee": float(backtest.taker_fee) if backtest.taker_fee is not None else 0.1,
            "slippage": float(backtest.slippage) if backtest.slippage is not None else 0.05,
            "marketImpactBps": float(runtime_cost_config.get("marketImpactBps", 2.0)),
            "impactVolatilityWeight": float(runtime_cost_config.get("impactVolatilityWeight", 0.10)),
            "maxImpactPct": float(runtime_cost_config.get("maxImpactPct", 0.25)),
            "maxParticipationRate": float(runtime_cost_config.get("maxParticipationRate", 5.0)),
            "fundingRatePerInterval": float(runtime_cost_config.get("fundingRatePerInterval", 0.0)),
            "fundingIntervalHours": int(runtime_cost_config.get("fundingIntervalHours", 8)),
        }
        
        # 构建结果。失败任务也要返回中断前已经持久化的记录；如果数据库增量记录
        # 尚未写入，则使用最后一次 progress_snapshot 中的 livePreview 兜底。
        result = None
        if backtest.status == BacktestStatus.COMPLETED and backtest.result_statistics:
            result = self._build_result_response(
                backtest.result_statistics,
                trades,
                equity_records,
                decision_records or []
            )

        snapshot_source = (
            backtest.progress_snapshot
            if progress_snapshot_override is None
            else progress_snapshot_override
        )
        progress_snapshot = (
            dict(snapshot_source)
            if isinstance(snapshot_source, dict)
            else None
        )
        if backtest.status in (BacktestStatus.FAILED, BacktestStatus.CANCELLED):
            live_preview = (
                progress_snapshot.get("livePreview")
                if isinstance(progress_snapshot, dict)
                else None
            )
            live_preview = live_preview if isinstance(live_preview, dict) else {}
            has_partial_records = bool(
                trades
                or equity_records
                or decision_records
                or backtest.result_statistics
                or live_preview.get("statistics")
                or live_preview.get("equity") is not None
                or live_preview.get("trades")
                or live_preview.get("decisionLog")
                or live_preview.get("equityCurve")
            )
            if has_partial_records:
                partial_statistics = dict(
                    backtest.result_statistics
                    or live_preview.get("statistics")
                    or {}
                )
                initial_capital = float(backtest.initial_capital)
                latest_equity = (
                    float(equity_records[-1].equity)
                    if equity_records
                    else float(live_preview.get("equity", initial_capital))
                )
                partial_statistics.setdefault("totalReturn", (
                    ((latest_equity - initial_capital) / initial_capital * 100)
                    if initial_capital else 0.0
                ))
                partial_statistics.setdefault("annualizedReturn", 0.0)
                partial_statistics.setdefault("maxDrawdown", 0.0)
                partial_statistics.setdefault("sharpeRatio", 0.0)
                partial_statistics.setdefault("sortinoRatio", None)
                partial_statistics.setdefault("winRate", 0.0)
                partial_statistics.setdefault("profitFactor", 0.0)
                partial_statistics.setdefault("totalTrades", len(trades) or len(live_preview.get("trades") or []))
                partial_statistics.setdefault("closedTrades", 0)
                partial_statistics.setdefault("winTrades", 0)
                partial_statistics.setdefault("lossTrades", 0)
                partial_statistics.setdefault("avgProfit", 0.0)
                partial_statistics.setdefault("avgLoss", 0.0)
                partial_statistics.setdefault("avgHoldingTime", "-")
                partial_statistics.setdefault("maxConsecutiveWins", 0)
                partial_statistics.setdefault("maxConsecutiveLosses", 0)
                partial_statistics.setdefault("finalCapital", latest_equity)

                result = self._build_result_response(
                    partial_statistics,
                    trades,
                    equity_records,
                    decision_records or [],
                )
                if not result["trades"] and isinstance(live_preview.get("trades"), list):
                    result["trades"] = live_preview["trades"]
                if not result["decisionLog"] and isinstance(live_preview.get("decisionLog"), list):
                    result["decisionLog"] = live_preview["decisionLog"]
                if not result["equityCurve"] and isinstance(live_preview.get("equityCurve"), list):
                    result["equityCurve"] = live_preview["equityCurve"]
                if not result["drawdownCurve"] and isinstance(live_preview.get("drawdownCurve"), list):
                    result["drawdownCurve"] = live_preview["drawdownCurve"]
                if not result["benchmarkCurve"] and isinstance(live_preview.get("benchmarkCurve"), list):
                    result["benchmarkCurve"] = live_preview["benchmarkCurve"]
        
        running_progress = None
        if backtest.status in (
            BacktestStatus.RUNNING,
            BacktestStatus.FAILED,
            BacktestStatus.CANCELLED,
        ) and progress_snapshot:
            running_progress = progress_snapshot

        return {
            "id": backtest.id,
            "name": backtest.name,
            "status": backtest.status.value,
            "progress": backtest.progress,
            "createdAt": backtest.created_at.isoformat(),
            "startedAt": backtest.started_at.isoformat() if backtest.started_at else None,
            "completedAt": backtest.completed_at.isoformat() if backtest.completed_at else None,
            "config": config,
            "result": result,
            "errorMessage": backtest.error_message,
            "runningProgress": running_progress,
        }
    
    @staticmethod
    def _extract_rule_audit(chain_of_thought: Optional[List]) -> Dict[str, Any]:
        if not chain_of_thought:
            return {}
        for item in reversed(chain_of_thought):
            if isinstance(item, dict) and item.get("type") == "rule_audit":
                return {
                    "decisionMode": item.get("decisionMode") or "rule",
                    "regime": item.get("regime"),
                    "ruleHits": item.get("ruleHits") or [],
                    "signals": item.get("signals") or [],
                    "indicatorsSnapshot": item.get("indicatorsSnapshot") or {},
                }
        return {}

    @staticmethod
    def _extract_llm_audit(chain_of_thought: Optional[List]) -> Dict[str, Any]:
        """从 chain_of_thought 中提取 LLM 审计字段（含决策 prompt）。"""
        if not chain_of_thought:
            return {}
        for item in reversed(chain_of_thought):
            if isinstance(item, dict) and item.get("type") == "llm_audit":
                out: Dict[str, Any] = {}
                if item.get("decisionPrompt"):
                    out["decisionPrompt"] = item.get("decisionPrompt")
                if item.get("llmRawResponse"):
                    out["llmRawResponse"] = item.get("llmRawResponse")
                if item.get("parsedDecision"):
                    out["parsedDecision"] = item.get("parsedDecision")
                if item.get("llmMetadata"):
                    out["llmMetadata"] = item.get("llmMetadata")
                return out
        return {}

    def _build_result_response(
        self,
        statistics: Dict[str, Any],
        trades: List[BacktestTradeModel],
        equity_records: List[BacktestEquityModel],
        decision_records: List = None
    ) -> dict:
        """构建回测结果响应"""
        decision_records = decision_records or []
        # 转换决策记录
        decision_log = []
        for d in decision_records:
            rule_meta = self._extract_rule_audit(d.chain_of_thought)
            llm_meta = self._extract_llm_audit(d.chain_of_thought)
            row = {
                "timestamp": d.timestamp.isoformat(),
                "action": d.action,
                "symbol": d.symbol,
                "quantity": float(d.quantity) if d.quantity is not None else None,
                "reasoning": d.reasoning,
                "decisionAnalysis": d.decision_analysis or d.reasoning,
                "technicalAnalysis": d.technical_analysis,
                "chainOfThought": d.chain_of_thought or [],
                "currentPrice": float(d.reference_price) if d.reference_price is not None else None,
                "executionResult": d.execution_result,
            }
            row.update(llm_meta)
            row.update(rule_meta)
            if not row.get("decisionMode") and row.get("decisionPrompt"):
                row["decisionMode"] = "trader"
            decision_log.append(row)
        # 转换交易记录
        trades_response = [
            {
                "id": trade.id,
                "timestamp": trade.timestamp.isoformat(),
                "symbol": trade.symbol,
                "side": trade.side,
                "type": trade.trade_type,
                "action": trade.action,
                "price": float(trade.price),
                "quantity": float(trade.quantity),
                "amount": float(trade.amount),
                "fee": float(trade.fee),
                "pnl": float(trade.pnl),
                "pnlPercent": float(trade.pnl_percent),
                "balance": float(trade.balance),
                "reasoning": trade.reasoning,
                "signals": trade.signals,
                "chainOfThought": trade.chain_of_thought or []
            }
            for trade in trades
        ]
        
        # 转换权益曲线
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
        
        return {
            "statistics": statistics,
            "equityCurve": equity_curve,
            "drawdownCurve": drawdown_curve,
            "benchmarkCurve": benchmark_curve,
            "positionHistory": [],
            "decisionLog": decision_log,
            "trades": trades_response
        }
    
    def trade_to_response(self, trade: BacktestTradeModel) -> dict:
        """将交易记录模型转换为响应格式"""
        leverage = Decimal(str(trade.leverage or 1))
        stored_margin = Decimal(str(trade.margin_used or 0))
        # 迁移前的历史成交会得到 margin_used=0；按 1x/已存杠杆还原展示值。
        margin_used = (
            stored_margin
            if stored_margin > 0
            else Decimal(str(trade.amount or 0)) / max(Decimal("1"), leverage)
        )
        return {
            "id": trade.id,
            "timestamp": trade.timestamp.isoformat(),
            "symbol": trade.symbol,
            "side": trade.side,
            "type": trade.trade_type,
            "action": trade.action,
            "leverage": float(leverage),
            "marginUsed": float(margin_used),
            "price": float(trade.price),
            "quantity": float(trade.quantity),
            "amount": float(trade.amount),
            "fee": float(trade.fee),
            "pnl": float(trade.pnl),
            "pnlPercent": float(trade.pnl_percent),
            "balance": float(trade.balance),
            "reasoning": trade.reasoning,
            "signals": trade.signals,
            "chainOfThought": trade.chain_of_thought or []
        }

    async def get_kline_data(
        self,
        session: AsyncSession,
        backtest_id: str,
        user_id: str,
        symbol: Optional[str] = None,
        include_future: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """获取决策预热上下文及回测区间内指定交易对的 K 线数据。"""
        backtest = await get_backtest_by_id_and_user(session, backtest_id, user_id)
        if not backtest:
            return None

        symbols = backtest.symbols or []
        if not symbols:
            raise ValueError("回测未配置交易对")

        target_symbol = (symbol or symbols[0]).strip()
        symbol_upper = target_symbol.upper()
        configured = {str(s).upper() for s in symbols}
        if symbol_upper not in configured:
            raise ValueError("交易对不在回测配置中")

        from backtest.backtest_engine import (
            INTERVAL_SECONDS,
            KLINE_CONTEXT_LOOKBACK_DAYS,
            bars_for_lookback_days,
            kline_context_start,
        )
        from backtest.kline_fetcher import ensure_and_get_klines

        interval = backtest.interval.value if hasattr(backtest.interval, "value") else str(backtest.interval)
        context_start = kline_context_start(backtest.start_time, interval)
        interval_seconds = INTERVAL_SECONDS.get(interval, 900)
        query_end = backtest.end_time
        if not include_future and backtest.status != BacktestStatus.COMPLETED:
            current_time_raw = await get_backtest_current_time(session, backtest_id)
            if current_time_raw:
                try:
                    query_end = datetime.fromisoformat(
                        current_time_raw.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    query_end = backtest.start_time
            else:
                query_end = backtest.start_time
            query_end = min(max(query_end, backtest.start_time), backtest.end_time)

        expected_rows = int(
            (query_end - context_start).total_seconds() / interval_seconds
        ) + 2
        rows = await ensure_and_get_klines(
            session,
            exchange=backtest.exchange,
            symbol=target_symbol,
            interval=interval,
            start_time=context_start,
            end_time=query_end,
            limit=max(10000, expected_rows),
        )

        kline_list = []
        for row in rows:
            kline_list.append({
                "time": row.timestamp.isoformat(),
                "open": str(row.open_price),
                "high": str(row.high_price),
                "low": str(row.low_price),
                "close": str(row.close_price),
                "volume": str(row.volume),
            })

        return {
            "symbol": target_symbol,
            "interval": interval,
            "startTime": context_start.isoformat(),
            "endTime": query_end.isoformat(),
            "backtestEndTime": backtest.end_time.isoformat(),
            "backtestStartTime": backtest.start_time.isoformat(),
            "contextLookbackBars": bars_for_lookback_days(
                interval, KLINE_CONTEXT_LOOKBACK_DAYS
            ),
            "list": kline_list,
        }
