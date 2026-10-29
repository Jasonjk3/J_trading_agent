#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测引擎核心
时间驱动的回测执行器
"""
import asyncio
import math
import time
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from uuid import uuid4
from loguru import logger

from backtest.virtual_account import VirtualAccount, Trade
from backtest.risk_manager import RiskManager, RiskConfig
from decision.types import resolve_decision_mode
from trader.risk_kernel import RiskKernel

# 决策 LLM / 指标上下文默认至少覆盖当前时点往前 7 天 K 线
KLINE_CONTEXT_LOOKBACK_DAYS = 7
# 指标预热下限（MA20/MACD 等）
MIN_INDICATOR_LOOKBACK_BARS = 50
# 决策 prompt 多周期：15m×96 / 1h×48 / 4h×24（由基础周期聚合）
PROMPT_KLINE_SPECS = (
    ("15m", 96),
    ("1h", 48),
    ("4h", 24),
)

INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
}


def bars_for_prompt_mtf(interval: str) -> int:
    """为聚合出 prompt 所需 15m/1h/4h 根数，计算基础周期最少需要多少根。"""
    base_seconds = INTERVAL_SECONDS.get(str(interval or "").strip().lower(), 900)
    if base_seconds <= 0:
        base_seconds = 900
    need = MIN_INDICATOR_LOOKBACK_BARS
    for tf, count in PROMPT_KLINE_SPECS:
        tf_seconds = INTERVAL_SECONDS.get(tf)
        if not tf_seconds or tf_seconds < base_seconds:
            continue
        if tf_seconds % base_seconds != 0:
            continue
        need = max(need, int(count) * (tf_seconds // base_seconds))
    return need


def bars_for_lookback_days(
    interval: str,
    days: int = KLINE_CONTEXT_LOOKBACK_DAYS,
    min_bars: int = MIN_INDICATOR_LOOKBACK_BARS,
) -> int:
    """按周期计算 lookback 根数，至少覆盖指定天数，并满足多周期 prompt 聚合需求。"""
    seconds = INTERVAL_SECONDS.get(str(interval or "").strip().lower(), 900)
    if seconds <= 0:
        seconds = 900
    days = max(1, int(days))
    by_days = int(days * 24 * 3600 / seconds) + 1
    return max(min_bars, by_days, bars_for_prompt_mtf(interval))


def kline_context_start(
    start_time: datetime,
    interval: str,
    days: int = KLINE_CONTEXT_LOOKBACK_DAYS,
) -> datetime:
    """返回决策上下文所需 K 线的起始时间，供执行引擎和审计图表共用。"""
    seconds = INTERVAL_SECONDS.get(str(interval or "").strip().lower(), 900)
    if seconds <= 0:
        seconds = 900
    return start_time - timedelta(
        seconds=bars_for_lookback_days(interval, days) * seconds
    )


@dataclass
class KlineData:
    """K线数据"""
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Optional[Decimal] = None


@dataclass
class MarketSnapshot:
    """市场快照"""
    timestamp: datetime
    prices: Dict[str, Decimal]  # symbol -> price
    klines: Dict[str, List[KlineData]]  # symbol -> kline history
    execution_prices: Dict[str, Decimal] = None  # 当前执行 K 线 open
    current_bars: Dict[str, KlineData] = None  # 当前执行 K 线（不进入信号历史）
    
    def get_price(self, symbol: str) -> Optional[Decimal]:
        return self.prices.get(symbol)


@dataclass
class PendingBacktestOrder:
    order_id: str
    proposal_id: Optional[str]
    decision: Dict[str, Any]
    remaining_quantity: Decimal
    created_at: datetime
    expires_at: Optional[datetime] = None
    status: str = "submitted"


@dataclass
class BacktestConfig:
    """回测配置"""
    start_time: datetime
    end_time: datetime
    initial_capital: Decimal
    symbols: List[str]
    interval: str  # '1m', '5m', '15m', '1h', '4h', '1d'
    maker_fee: Decimal = Decimal('0.1')  # %
    taker_fee: Decimal = Decimal('0.1')  # %
    slippage: Decimal = Decimal('0.05')  # %
    market_impact_bps: Decimal = Decimal('2')
    impact_volatility_weight: Decimal = Decimal('0.10')
    max_impact_pct: Decimal = Decimal('0.25')
    max_participation_rate: Decimal = Decimal('5')
    funding_rate_per_interval: Decimal = Decimal('0')
    funding_interval_hours: int = 8
    strategy_config: Dict = None
    decision_timeout_seconds: float = 180.0
    risk_timeout_seconds: float = 10.0
    progress_timeout_seconds: float = 180.0
    max_consecutive_decision_errors: int = 3
    decision_cooldown_steps: int = 5


class BacktestResult:
    """回测结果"""
    
    def __init__(self):
        self.statistics: Dict = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []
        self.drawdown_curve: List[Dict] = []
        self.benchmark_curve: List[Dict] = []
        self.decision_log: List[Dict] = []
        self.order_events: List[Dict] = []
    
    def to_dict(self) -> Dict:
        return {
            'statistics': self.statistics,
            'trades': [self._trade_to_dict(t) for t in self.trades],
            'equityCurve': self.equity_curve,
            'drawdownCurve': self.drawdown_curve,
            'benchmarkCurve': self.benchmark_curve,
            'decisionLog': [self._decision_to_dict(d) for d in self.decision_log],
            'orderEvents': list(self.order_events),
        }
    
    def _decision_to_dict(self, d: Dict) -> Dict:
        row = {
            'timestamp': d.get('timestamp'),
            'action': d.get('action', 'hold'),
            'symbol': d.get('symbol'),
            'quantity': d.get('quantity'),
            'reasoning': d.get('reasoning') or d.get('reason', ''),
            'chainOfThought': d.get('chain_of_thought') or [],
        }
        if d.get('current_price') is not None:
            row['currentPrice'] = d['current_price']
        if d.get('decision_analysis') is not None:
            row['decisionAnalysis'] = d.get('decision_analysis')
        if d.get('technical_analysis') is not None:
            row['technicalAnalysis'] = d.get('technical_analysis')
        if d.get('decision_prompt') is not None:
            row['decisionPrompt'] = d.get('decision_prompt')
        if d.get('llm_raw_response') is not None:
            row['llmRawResponse'] = d.get('llm_raw_response')
        if d.get('parsed_decision') is not None:
            row['parsedDecision'] = d.get('parsed_decision')
        if d.get('llm_metadata') is not None:
            row['llmMetadata'] = d.get('llm_metadata')
        if d.get('error_type') is not None:
            row['errorType'] = d.get('error_type')
        if d.get('outcome_type') is not None:
            row['outcomeType'] = d.get('outcome_type')
        if d.get('execution_result') is not None:
            row['executionResult'] = d.get('execution_result')
        return row
    
    def _trade_to_dict(self, trade: Trade) -> Dict:
        return {
            'id': trade.id,
            'timestamp': trade.timestamp.isoformat() if trade.timestamp else None,
            'symbol': trade.symbol,
            'side': trade.side,
            'type': trade.trade_type,
            'action': trade.action,
            'price': float(trade.price),
            'quantity': float(trade.quantity),
            'amount': float(trade.amount),
            'fee': float(trade.fee),
            'pnl': float(trade.pnl),
            'pnlPercent': float(trade.pnl_percent),
            'balance': float(trade.balance),
            'reasoning': trade.reasoning,
            'signals': trade.signals
        }


class BacktestEngine:
    """回测引擎"""
    
    def __init__(
        self,
        config: BacktestConfig,
        decision_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None
    ):
        """
        初始化回测引擎
        
        Args:
            config: 回测配置
            decision_callback: 决策回调函数，接收 (market_snapshot, account, risk_manager) 返回决策
            progress_callback: 进度回调 async (progress, current_time, message, detail)；
                detail 含 currentStep、totalSteps、intervalSeconds
        """
        self.config = config
        self.decision_callback = decision_callback
        self.progress_callback = progress_callback
        self.decision_log: List[Dict] = []  # 每次决策记录（含 hold），用于前端决策表格
        
        # 初始化虚拟账户
        strategy = config.strategy_config or {}
        self.decision_mode = resolve_decision_mode(strategy)
        leverage = Decimal(str(strategy.get('leverage', 1)))
        self.account = VirtualAccount(
            initial_capital=config.initial_capital,
            maker_fee=config.maker_fee,
            taker_fee=config.taker_fee,
            slippage=config.slippage,
            leverage=leverage
        )
        
        # 初始化风控管理器
        risk_config_dict = config.strategy_config or {}
        self.risk_manager = RiskManager.from_strategy_config(risk_config_dict)
        self.risk_kernel = RiskKernel.from_strategy_config(risk_config_dict)
        
        # K线数据存储
        self.kline_data: Dict[str, List[KlineData]] = {symbol: [] for symbol in config.symbols}
        self._kline_cursor_indices: Dict[str, int] = {symbol: -1 for symbol in config.symbols}
        
        # 基准数据（买入持有）
        self.benchmark_start_prices: Dict[str, Decimal] = {}
        # 最近一次市场快照价格（供 livePreview 持仓现价）
        self._last_mark_prices: Dict[str, Decimal] = {}
        
        # 运行状态
        self.is_running = False
        self.is_cancelled = False
        
        # 运行时性能统计
        self._perf_totals: Dict[str, float] = {
            'snapshot_ms': 0.0,
            'risk_ms': 0.0,
            'decision_ms': 0.0,
            'equity_ms': 0.0,
            'progress_ms': 0.0,
            'step_ms': 0.0,
        }
        self._perf_samples = 0
        self._perf_log_every_steps = 100
        self._decision_error_streak = 0
        self._decision_cooldown_remaining = 0
        self._settled_funding_slots = set()
        self.pending_orders: Dict[str, PendingBacktestOrder] = {}
        self.order_events: List[Dict[str, Any]] = []
    
    def load_klines(self, symbol: str, klines: List[KlineData]):
        """加载K线数据"""
        self.kline_data[symbol] = sorted(klines, key=lambda k: k.timestamp)
        self._kline_cursor_indices[symbol] = -1

    @staticmethod
    def _pending_order_group(decision: Dict[str, Any]) -> tuple[str, str, str]:
        action = str(decision.get('action') or '').lower()
        effect, _, position_side = action.partition('_')
        risk_group = 'increase' if effect in {'open', 'add'} else effect
        return (
            str(decision.get('symbol') or '').upper(),
            position_side,
            risk_group,
        )

    @staticmethod
    def _pending_order_plan_key(decision: Dict[str, Any]) -> Optional[tuple[str, str]]:
        def normalize(value: Any) -> str:
            return ' '.join(str(value or '').strip().lower().split())
        plan = decision.get('trade_plan') or {}
        key = (
            normalize(decision.get('thesis') or plan.get('thesis')),
            normalize(decision.get('invalidation') or plan.get('invalidation')),
        )
        return key if any(key) else None

    def _pending_order_max_bars(self) -> int:
        config = self.config.strategy_config or {}
        return max(1, min(24, int(config.get('pendingOrderMaxBars') or 6)))

    def _pending_order_max_distance_pct(self) -> float:
        config = self.config.strategy_config or {}
        return max(0.1, min(20.0, float(
            config.get('pendingOrderMaxDistancePct')
            or config.get('priceDeviationUpper')
            or 2.0
        )))

    def _normalize_pending_order_expiry(
        self,
        created_at: datetime,
        requested: Any,
    ) -> datetime:
        max_expiry = created_at + timedelta(
            seconds=self._get_interval_seconds() * self._pending_order_max_bars()
        )
        if isinstance(requested, str):
            requested = datetime.fromisoformat(requested.replace('Z', '+00:00'))
        if not isinstance(requested, datetime):
            return max_expiry
        if requested.tzinfo is None and max_expiry.tzinfo is not None:
            requested = requested.replace(tzinfo=max_expiry.tzinfo)
        elif requested.tzinfo is not None and max_expiry.tzinfo is None:
            requested = requested.replace(tzinfo=None)
        if requested <= created_at:
            return max_expiry
        return min(requested, max_expiry)

    def active_orders_snapshot(
        self,
        *,
        as_of: Optional[datetime] = None,
        prices: Optional[Dict[str, Decimal]] = None,
    ) -> List[Dict[str, Any]]:
        """给交易员的完整活动挂单快照，不暴露未来行情。"""
        rows: List[Dict[str, Any]] = []
        interval_seconds = self._get_interval_seconds()
        current_prices = prices or self._last_mark_prices
        for order in sorted(
            self.pending_orders.values(), key=lambda item: (item.created_at, item.order_id)
        ):
            decision = order.decision
            plan = decision.get('trade_plan') or {}
            action = str(decision.get('action') or '')
            effect, _, position_side = action.partition('_')
            side = 'buy' if (effect, position_side) in {
                ('open', 'long'), ('add', 'long'), ('reduce', 'short'), ('close', 'short')
            } else 'sell'
            age_bars = None
            if as_of is not None:
                age_bars = max(
                    0,
                    int((as_of - order.created_at).total_seconds() // interval_seconds),
                )
            current_price = current_prices.get(str(decision.get('symbol') or ''))
            limit_price = Decimal(str(decision.get('limit_price') or 0))
            distance_pct = None
            if current_price is not None and Decimal(str(current_price)) > 0 and limit_price > 0:
                distance_pct = float(
                    (limit_price / Decimal(str(current_price)) - Decimal('1'))
                    * Decimal('100')
                )
            rows.append({
                'order_id': order.order_id,
                'proposal_id': order.proposal_id,
                'client_intent_id': decision.get('client_intent_id'),
                'parent_intent_id': decision.get('parent_intent_id'),
                'parent_position_id': decision.get('parent_position_id'),
                'symbol': decision.get('symbol'),
                'action': action,
                'side': decision.get('side') or side,
                'position_side': position_side,
                'order_type': decision.get('order_type') or 'limit',
                'execution_role': decision.get('execution_role') or 'standalone',
                'limit_price': decision.get('limit_price'),
                'current_price': float(current_price) if current_price is not None else None,
                'distance_pct': distance_pct,
                'quantity': float(Decimal(str(decision.get('quantity') or 0))),
                'remaining_quantity': float(order.remaining_quantity),
                'filled_quantity': float(max(
                    Decimal('0'),
                    Decimal(str(decision.get('quantity') or 0))
                    - order.remaining_quantity,
                )),
                'requested_leverage': decision.get('requested_leverage'),
                'stop_loss_price': (
                    decision.get('stop_loss_price')
                    if decision.get('stop_loss_price') is not None
                    else plan.get('stop_loss_price')
                ),
                'take_profit_price': (
                    decision.get('take_profit_price')
                    if decision.get('take_profit_price') is not None
                    else plan.get('take_profit_price')
                ),
                'thesis': decision.get('thesis') or plan.get('thesis'),
                'invalidation': decision.get('invalidation') or plan.get('invalidation'),
                'rationale': decision.get('reason') or decision.get('reasoning'),
                'created_at': order.created_at.isoformat(),
                'expires_at': order.expires_at.isoformat() if order.expires_at else None,
                'age_bars': age_bars,
                'max_age_bars': self._pending_order_max_bars(),
                'max_distance_pct': self._pending_order_max_distance_pct(),
                'status': order.status,
            })
        return rows

    def _serialize_live_active_orders(self, as_of: Optional[datetime]) -> List[Dict[str, Any]]:
        """前端使用的活动委托快照；保留 LLM 上下文的 snake_case 协议不变。"""
        key_map = {
            'order_id': 'orderId',
            'proposal_id': 'proposalId',
            'client_intent_id': 'clientIntentId',
            'parent_intent_id': 'parentIntentId',
            'parent_position_id': 'parentPositionId',
            'position_side': 'positionSide',
            'order_type': 'orderType',
            'execution_role': 'executionRole',
            'limit_price': 'limitPrice',
            'current_price': 'currentPrice',
            'distance_pct': 'distancePct',
            'remaining_quantity': 'remainingQuantity',
            'filled_quantity': 'filledQuantity',
            'requested_leverage': 'requestedLeverage',
            'stop_loss_price': 'stopLossPrice',
            'take_profit_price': 'takeProfitPrice',
            'created_at': 'createdAt',
            'expires_at': 'expiresAt',
            'age_bars': 'ageBars',
            'max_age_bars': 'maxAgeBars',
            'max_distance_pct': 'maxDistancePct',
        }
        return [
            {key_map.get(key, key): value for key, value in row.items()}
            for row in self.active_orders_snapshot(
                as_of=as_of,
                prices=self._last_mark_prices,
            )
        ]

    @staticmethod
    def _decision_position_side(decision: Dict[str, Any]) -> str:
        action = str(decision.get('action') or '').lower()
        _, _, side = action.partition('_')
        return side

    def _bind_child_order_to_parent_position(
        self,
        decision: Dict[str, Any],
        existing_orders: Optional[List[PendingBacktestOrder]] = None,
    ) -> Optional[str]:
        """将回撤加仓单绑定到真实持仓生命周期。

        parent_intent_id 只是 LLM 当轮的逻辑关系；parent_position_id 才是
        执行层的稳定关系。替换已有子单时可继承原单绑定，但必须
        确认父仓仍然存在且方向一致。
        """
        action = str(decision.get('action') or '').lower()
        role = str(decision.get('execution_role') or '').lower()
        inherited_parent_id = next((
            str(order.decision.get('parent_position_id'))
            for order in (existing_orders or [])
            if order.decision.get('parent_position_id')
        ), None)
        is_child = role == 'pullback_add' or bool(decision.get('parent_intent_id'))
        if not is_child and action not in {'add_long', 'add_short'}:
            return None

        symbol = str(decision.get('symbol') or '')
        expected_side = self._decision_position_side(decision)
        position = self.account.get_position(symbol)
        if position is None or str(position.side).lower() != expected_side:
            return '回撤加仓单缺少同标的、同方向的活动父仓'

        lifecycle_id = str(getattr(position, 'lifecycle_id', None) or '')
        if not lifecycle_id:
            # 兼容改造前已在运行的持仓：首次看到加仓单时为父仓
            # 补齐身份，之后所有子单都使用同一生命周期标识。
            position.lifecycle_id = str(uuid4())
            lifecycle_id = position.lifecycle_id
        requested_parent = str(decision.get('parent_intent_id') or '')
        entry_intent_id = str(getattr(position, 'entry_intent_id', None) or '')
        if requested_parent and entry_intent_id and requested_parent != entry_intent_id:
            return '回撤加仓单的 parent_intent_id 与当前父仓不匹配'
        if inherited_parent_id and inherited_parent_id != lifecycle_id:
            return '替换单关联的父仓已失效'

        decision['parent_position_id'] = lifecycle_id
        plan = decision.get('trade_plan')
        if isinstance(plan, dict):
            plan['parent_position_id'] = lifecycle_id
        return None

    def _cancel_child_orders_for_position(
        self,
        position_id: Optional[str],
        timestamp: datetime,
        *,
        reason: str,
    ) -> int:
        """父仓完全结束时立即级联撤销所有未成交子单。"""
        if not position_id:
            return 0
        cancelled = 0
        for order_id, order in list(self.pending_orders.items()):
            if str(order.decision.get('parent_position_id') or '') != str(position_id):
                continue
            self.pending_orders.pop(order_id, None)
            order.status = 'cancelled'
            self._append_order_event(order, 'cancelled', timestamp, reason=reason)
            cancelled += 1
        return cancelled
    
    def _get_interval_seconds(self) -> int:
        """获取K线周期对应的秒数"""
        return INTERVAL_SECONDS.get(self.config.interval, 900)

    def _snapshot_history_bars(self) -> int:
        """快照中保留的历史 K 线根数（覆盖 7 天 lookback + 多周期 prompt 聚合）。"""
        return bars_for_lookback_days(self.config.interval, KLINE_CONTEXT_LOOKBACK_DAYS)
    
    async def run(self) -> BacktestResult:
        """
        执行回测
        
        Returns:
            BacktestResult: 回测结果
        """
        self.is_running = True
        self.is_cancelled = False
        result = BacktestResult()
        
        try:
            # 计算总步数
            interval_seconds = self._get_interval_seconds()
            total_duration = (self.config.end_time - self.config.start_time).total_seconds()
            # 起止时间均对应一个可执行 bar，因此总步数需包含两个端点。
            total_steps = int(total_duration / interval_seconds) + 1
            
            if total_steps <= 0:
                raise ValueError("回测时间范围太短")
            self._perf_log_every_steps = max(50, min(500, max(1, total_steps // 20)))
            
            # 获取每个时间点的数据
            current_step = 0
            current_time = self.config.start_time
            
            while current_time <= self.config.end_time and not self.is_cancelled:
                step_started_at = time.perf_counter()
                snapshot_ms = 0.0
                risk_ms = 0.0
                decision_ms = 0.0
                equity_ms = 0.0
                progress_ms = 0.0

                # 构建市场快照
                snapshot_started_at = time.perf_counter()
                snapshot = self._build_snapshot(current_time)
                snapshot_ms = (time.perf_counter() - snapshot_started_at) * 1000
                
                if snapshot and snapshot.prices:
                    current_bars = snapshot.current_bars or {}
                    close_prices = {symbol: bar.close for symbol, bar in current_bars.items()}
                    execution_prices = snapshot.execution_prices or snapshot.prices
                    self._last_mark_prices = dict(close_prices or execution_prices)
                    # 首次记录基准价格
                    if not self.benchmark_start_prices:
                        self.benchmark_start_prices = dict(execution_prices)

                    # 先处理上一时点已存在的委托；新限价单最早从下一根 bar 成交。
                    await self._process_pending_orders(snapshot)
                    
                    # 执行策略决策
                    if self.decision_callback:
                        decision_started_at = time.perf_counter()
                        await self._run_decision_with_timeout(snapshot)
                        decision_ms = (time.perf_counter() - decision_started_at) * 1000

                    # 订单在本根 open 成交后，再使用本根 high/low 做盘中风控。
                    risk_started_at = time.perf_counter()
                    await self._run_risk_checks_with_timeout(snapshot)
                    risk_ms = (time.perf_counter() - risk_started_at) * 1000

                    self._apply_funding_if_due(snapshot, close_prices)

                    # 收盘盯市；信号仍只看到上一根已闭合 K 线。
                    self.account.update_positions_pnl(close_prices)
                    
                    # 记录权益
                    equity_started_at = time.perf_counter()
                    benchmark_equity = self._calculate_benchmark_equity(close_prices)
                    self.account.record_equity(current_time, benchmark_equity)
                    equity_ms = (time.perf_counter() - equity_started_at) * 1000
                
                # 更新进度
                current_step += 1
                progress = int(current_step / total_steps * 100)
                if self.progress_callback:
                    progress_started_at = time.perf_counter()
                    detail = {
                        "currentStep": current_step,
                        "totalSteps": total_steps,
                        "intervalSeconds": interval_seconds,
                    }
                    try:
                        await asyncio.wait_for(
                            self.progress_callback(
                                progress,
                                current_time,
                                f"回测进行中... {current_time.strftime('%Y-%m-%d %H:%M')}",
                                detail,
                            ),
                            timeout=max(0.1, float(self.config.progress_timeout_seconds)),
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "进度回调超时，已跳过本次更新: "
                            f"timeout={self.config.progress_timeout_seconds}s, "
                            f"step={current_step}/{total_steps}, ts={current_time.isoformat()}"
                        )
                    except Exception as pe:
                        logger.warning(f"进度回调异常，已忽略: {pe}")
                    progress_ms = (time.perf_counter() - progress_started_at) * 1000
                
                step_ms = (time.perf_counter() - step_started_at) * 1000
                self._record_perf_sample(
                    snapshot_ms=snapshot_ms,
                    risk_ms=risk_ms,
                    decision_ms=decision_ms,
                    equity_ms=equity_ms,
                    progress_ms=progress_ms,
                    step_ms=step_ms,
                )
                if step_ms >= 1000:
                    logger.info(
                        "回测慢步骤: "
                        f"step={current_step}/{total_steps}, ts={current_time.isoformat()}, "
                        f"snapshot={snapshot_ms:.1f}ms, risk={risk_ms:.1f}ms, "
                        f"decision={decision_ms:.1f}ms, equity={equity_ms:.1f}ms, "
                        f"progress={progress_ms:.1f}ms, total={step_ms:.1f}ms"
                    )
                self._maybe_log_perf_summary(current_step, total_steps)
                
                # 移动到下一个时间点
                current_time += timedelta(seconds=interval_seconds)
                
                # 让出控制权
                await asyncio.sleep(0)
            
            # 构建回测结果
            result = self._build_result()
            
        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            raise
        finally:
            self.is_running = False
        
        return result
    
    def cancel(self):
        """取消回测"""
        self.is_cancelled = True

    def _record_perf_sample(self, **durations_ms: float):
        """累计各阶段耗时，用于定位回测热点。"""
        self._perf_samples += 1
        for key, value in durations_ms.items():
            self._perf_totals[key] = self._perf_totals.get(key, 0.0) + float(value)

    def _maybe_log_perf_summary(self, current_step: int, total_steps: int):
        """按固定步长输出阶段平均耗时，避免每步刷屏。"""
        if self._perf_samples <= 0:
            return
        if current_step % self._perf_log_every_steps != 0 and current_step != total_steps:
            return
        samples = float(self._perf_samples)
        logger.info(
            "回测性能统计: "
            f"step={current_step}/{total_steps}, "
            f"avg_snapshot={self._perf_totals['snapshot_ms'] / samples:.2f}ms, "
            f"avg_risk={self._perf_totals['risk_ms'] / samples:.2f}ms, "
            f"avg_decision={self._perf_totals['decision_ms'] / samples:.2f}ms, "
            f"avg_equity={self._perf_totals['equity_ms'] / samples:.2f}ms, "
            f"avg_progress={self._perf_totals['progress_ms'] / samples:.2f}ms, "
            f"avg_total={self._perf_totals['step_ms'] / samples:.2f}ms"
        )
    
    def _build_snapshot(self, timestamp: datetime) -> Optional[MarketSnapshot]:
        """构建无前视快照：历史截止上一根闭合 bar，当前 bar 仅供执行与撮合。"""
        prices = {}
        klines = {}
        execution_prices = {}
        current_bars = {}
        
        for symbol, kline_list in self.kline_data.items():
            if not kline_list:
                continue
            cursor = self._kline_cursor_indices.get(symbol, -1)
            if cursor >= len(kline_list):
                cursor = len(kline_list) - 1

            # 回测时间单调递增时只向前推进；若外部以更早时间调用则回退到正确位置。
            while cursor + 1 < len(kline_list) and kline_list[cursor + 1].timestamp <= timestamp:
                cursor += 1
            while cursor >= 0 and kline_list[cursor].timestamp > timestamp:
                cursor -= 1

            self._kline_cursor_indices[symbol] = cursor
            if cursor >= 1:
                execution_bar = kline_list[cursor]
                interval_seconds = self._get_interval_seconds()
                if (timestamp - execution_bar.timestamp).total_seconds() >= interval_seconds:
                    continue
                signal_cursor = cursor - 1
                history_bars = self._snapshot_history_bars()
                start_idx = max(0, signal_cursor - (history_bars - 1))
                klines[symbol] = kline_list[start_idx:signal_cursor + 1]
                prices[symbol] = kline_list[signal_cursor].close
                execution_prices[symbol] = execution_bar.open
                current_bars[symbol] = execution_bar
        
        if not prices:
            return None
        
        return MarketSnapshot(
            timestamp=timestamp,
            prices=prices,
            klines=klines,
            execution_prices=execution_prices,
            current_bars=current_bars,
        )
    
    async def _run_risk_checks(self, snapshot: MarketSnapshot):
        """执行风控检查"""
        risk_results = self.risk_manager.check_all_positions(
            self.account,
            {symbol: bar.close for symbol, bar in (snapshot.current_bars or {}).items()},
            bars=snapshot.current_bars or {},
        )
        
        for result in risk_results:
            if not result.passed:
                for action in result.actions:
                    if action['type'] == 'close_position':
                        symbol = action['symbol']
                        position = self.account.get_position(symbol)
                        if position:
                            current_price = action.get('trigger_price')
                            if current_price is None:
                                current_price = (snapshot.execution_prices or snapshot.prices).get(symbol)
                            if current_price:
                                reason = action.get('reason', '风控平仓')
                                parent_position_id = getattr(position, 'lifecycle_id', None)
                                if position.side == 'long':
                                    trade = self.account.close_long(
                                        symbol=symbol,
                                        quantity=None,
                                        current_price=current_price,
                                        timestamp=snapshot.timestamp,
                                        reasoning=reason,
                                        signals=['risk_control'],
                                        liquidity='taker',
                                        slippage_rate=self._effective_slippage_rate(
                                            snapshot, symbol, position.quantity, 'taker'
                                        ),
                                    )
                                    final_action = 'close_long'
                                else:
                                    trade = self.account.close_short(
                                        symbol=symbol,
                                        quantity=None,
                                        current_price=current_price,
                                        timestamp=snapshot.timestamp,
                                        reasoning=reason,
                                        signals=['risk_control'],
                                        liquidity='taker',
                                        slippage_rate=self._effective_slippage_rate(
                                            snapshot, symbol, position.quantity, 'taker'
                                        ),
                                    )
                                    final_action = 'close_short'
                                if trade:
                                    if self.account.get_position(symbol) is None:
                                        self._cancel_child_orders_for_position(
                                            parent_position_id,
                                            snapshot.timestamp,
                                            reason='parent_position_closed_by_risk_control',
                                        )
                                    self._record_automatic_trade_decision(
                                        trade=trade,
                                        action=final_action,
                                        snapshot=snapshot,
                                        reason=reason,
                                        execution_origin='risk_control',
                                    )

    def _record_automatic_trade_decision(
        self,
        *,
        trade,
        action: str,
        snapshot: MarketSnapshot,
        reason: str,
        execution_origin: str,
    ) -> None:
        """把风控/保护性平仓记为独立执行事件。

        这些成交不是当轮 LLM 的新委托，但必须在决策记录中与真实成交一一对应。
        """
        trade.action = action
        decision = {
            'decision_id': str(uuid4()),
            'action': action,
            'symbol': trade.symbol,
            'quantity': float(trade.quantity),
            'reason': reason,
            'signals': list(trade.signals or [execution_origin]),
            'execution_origin': execution_origin,
        }
        self._record_decision(decision, snapshot)
        execution_result = {
            'status': 'filled',
            'requestedAction': action,
            'finalAction': action,
            'executionOrigin': execution_origin,
            'tradeId': trade.id,
            'side': trade.side,
            'tradeType': trade.trade_type,
            'quantity': float(trade.quantity),
            'price': float(trade.price),
            'amount': float(trade.amount),
            'fee': float(trade.fee),
            'pnl': float(trade.pnl),
            'pnlPercent': float(trade.pnl_percent),
            'balanceAfter': float(trade.balance),
            'positionQuantityAfter': 0.0,
            'message': f'风控自动执行 {action}：数量 {trade.quantity}，价格 {trade.price}',
        }
        decision['execution_result'] = execution_result
        self.decision_log[-1]['execution_result'] = execution_result
    
    async def _run_decision(self, snapshot: MarketSnapshot):
        """执行策略决策"""
        try:
            decision = await self.decision_callback(
                snapshot, self.account, self.risk_manager
            )
            if decision:
                for cancel in decision.get('cancel_order_intents') or []:
                    if isinstance(cancel, dict):
                        self.cancel_pending_order(
                            str(cancel.get('order_id') or ''), snapshot.timestamp
                        )
                order_batch = decision.get('order_batch')
                if isinstance(order_batch, list):
                    for child in order_batch:
                        if not isinstance(child, dict):
                            continue
                        item = dict(child)
                        item.setdefault('decision_mode', decision.get('decision_mode'))
                        item.setdefault('outcome_type', decision.get('outcome_type'))
                        item.setdefault('proposal_id', decision.get('proposal_id'))
                        item.setdefault('decision_id', decision.get('decision_id'))
                        item.setdefault('signals', decision.get('signals') or [])
                        # 批量订单的每条子记录都必须保留完整 LLM 审计上下文。
                        # 否则单条详情只能看到已批准订单，无法还原原始限价与保护计划。
                        for audit_key in (
                            'decision_prompt', 'llm_raw_response', 'parsed_decision',
                            'llm_metadata', 'chain_of_thought', 'technical_analysis',
                        ):
                            item.setdefault(audit_key, decision.get(audit_key))
                        self._record_decision(item, snapshot)
                        await self._submit_or_execute_order(item, snapshot)
                    return True
                self._record_decision(decision, snapshot)
                action = str(decision.get('action') or 'hold').strip().lower()
                if action == 'system_error':
                    return None
                if action in {
                    'open_long', 'open_short', 'add_long', 'add_short',
                    'reduce_long', 'reduce_short', 'close_long', 'close_short'
                }:
                    await self._submit_or_execute_order(decision, snapshot)
            return True
        except Exception as e:
            logger.warning(f"决策执行失败: {e}")
            return False

    async def _submit_or_execute_order(self, decision: Dict, snapshot: MarketSnapshot):
        group = self._pending_order_group(decision)
        same_group = [
            order for order in self.pending_orders.values()
            if self._pending_order_group(order.decision) == group
        ]
        binding_error = self._bind_child_order_to_parent_position(decision, same_group)
        if binding_error:
            self._mark_execution_rejected(decision, binding_error)
            return
        if str(decision.get('order_type') or 'market').lower() != 'limit':
            await self._execute_decision(decision, snapshot)
            return
        limit_price = Decimal(str(decision.get('limit_price') or 0))
        quantity = Decimal(str(decision.get('quantity') or 0))
        if limit_price <= 0 or quantity <= 0:
            self._mark_execution_rejected(decision, '限价单缺少有效 limit_price 或 quantity')
            return
        plan_key = self._pending_order_plan_key(decision)
        same_plan = [
            order for order in same_group
            if plan_key is not None
            and self._pending_order_plan_key(order.decision) == plan_key
        ]
        if same_plan:
            kept = same_plan[0]
            decision['execution_result'] = {
                **self._execution_plan_snapshot(kept.decision),
                'status': 'kept',
                'orderId': kept.order_id,
                'requestedAction': decision.get('action'),
                'finalAction': 'hold',
                'remainingQuantity': float(kept.remaining_quantity),
                'message': '相同交易计划已有活动挂单，保留原单且不重复提交',
            }
            if self.decision_log:
                self.decision_log[-1]['execution_result'] = decision['execution_result']
            return
        # 同标的、同持仓方向的新计划替换旧计划，防止陈旧挂单叠加暴露。
        for existing in same_group:
            self.pending_orders.pop(existing.order_id, None)
            existing.status = 'replaced'
            self._append_order_event(existing, 'replaced', snapshot.timestamp)
        expires_at = self._normalize_pending_order_expiry(
            snapshot.timestamp, decision.get('expires_at')
        )
        decision['expires_at'] = expires_at.isoformat()
        order = PendingBacktestOrder(
            order_id=str(uuid4()),
            proposal_id=decision.get('proposal_id'),
            decision=dict(decision),
            remaining_quantity=quantity,
            created_at=snapshot.timestamp,
            expires_at=expires_at,
        )
        self.pending_orders[order.order_id] = order
        self._append_order_event(order, 'submitted', snapshot.timestamp, quantity=quantity)
        decision['execution_result'] = {
            **self._execution_plan_snapshot(decision),
            'status': 'submitted',
            'orderId': order.order_id,
            'requestedAction': decision.get('action'),
            'finalAction': decision.get('action'),
            'remainingQuantity': float(quantity),
            'expiresAt': expires_at.isoformat(),
            'message': (
                f'限价单已提交，等待价格 {limit_price}；最晚于 '
                f'{expires_at.isoformat()} 失效'
            ),
        }
        if self.decision_log:
            self.decision_log[-1]['execution_result'] = decision['execution_result']

    async def _process_pending_orders(self, snapshot: MarketSnapshot):
        for order_id, order in list(self.pending_orders.items()):
            if order.expires_at and self._time_reached(snapshot.timestamp, order.expires_at):
                order.status = 'expired'
                self._append_order_event(order, 'expired', snapshot.timestamp)
                self.pending_orders.pop(order_id, None)
                continue
            symbol = str(order.decision.get('symbol') or '')
            parent_position_id = str(order.decision.get('parent_position_id') or '')
            if parent_position_id:
                parent = self.account.get_position(symbol)
                parent_is_active = (
                    parent is not None
                    and str(getattr(parent, 'lifecycle_id', None) or '') == parent_position_id
                    and str(parent.side).lower()
                    == self._decision_position_side(order.decision)
                )
                if not parent_is_active:
                    order.status = 'cancelled'
                    self._append_order_event(
                        order,
                        'cancelled',
                        snapshot.timestamp,
                        reason='parent_position_missing_before_fill',
                    )
                    self.pending_orders.pop(order_id, None)
                    continue
            bar = (snapshot.current_bars or {}).get(symbol)
            if bar is None:
                continue
            price = Decimal(str(order.decision.get('limit_price') or 0))
            action = str(order.decision.get('action') or '')
            is_buy = action in {'open_long', 'add_long', 'reduce_short', 'close_short'}
            touched = Decimal(str(bar.low)) <= price if is_buy else Decimal(str(bar.high)) >= price
            if not touched:
                continue
            fill_qty = self._cap_quantity_by_participation(
                snapshot, symbol, order.remaining_quantity, price
            )
            if fill_qty <= 0:
                continue
            decision = dict(order.decision)
            # 挂单提交和实际成交是两个独立事件。不能沿用提交决策的主键，
            # 否则增量持久化会把成交事件当成重复记录跳过。
            source_decision_id = decision.get('decision_id')
            decision['decision_id'] = str(uuid4())
            decision['source_decision_id'] = source_decision_id
            decision['execution_origin'] = 'pending_order_fill'
            decision['quantity'] = float(fill_qty)
            decision['liquidity'] = 'maker'
            decision['signals'] = list(dict.fromkeys([
                *(decision.get('signals') or []), 'pending_order_fill'
            ]))
            fill_snapshot = MarketSnapshot(
                timestamp=snapshot.timestamp,
                prices={**snapshot.prices, symbol: price},
                klines=snapshot.klines,
                execution_prices={**(snapshot.execution_prices or snapshot.prices), symbol: price},
                current_bars=snapshot.current_bars,
            )
            self._record_decision(decision, fill_snapshot)
            before = len(self.account.trades)
            await self._execute_decision(decision, fill_snapshot)
            if len(self.account.trades) == before:
                order.status = 'rejected'
                self._append_order_event(order, 'rejected', snapshot.timestamp)
                self.pending_orders.pop(order_id, None)
                continue
            actual = Decimal(str(self.account.trades[-1].quantity))
            order.remaining_quantity = max(Decimal('0'), order.remaining_quantity - actual)
            status = 'filled' if order.remaining_quantity <= 0 else 'partially_filled'
            order.status = status
            self._append_order_event(order, status, snapshot.timestamp, quantity=actual, price=price)
            if status == 'filled':
                self.pending_orders.pop(order_id, None)

    def cancel_pending_order(self, order_id: str, timestamp: Optional[datetime] = None) -> bool:
        order = self.pending_orders.pop(order_id, None)
        if order is None:
            return False
        order.status = 'cancelled'
        self._append_order_event(order, 'cancelled', timestamp or order.created_at)
        return True

    def _append_order_event(
        self,
        order: PendingBacktestOrder,
        event_type: str,
        timestamp: datetime,
        *,
        quantity: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.order_events.append({
            'eventId': str(uuid4()),
            'orderId': order.order_id,
            'proposalId': order.proposal_id,
            'clientIntentId': order.decision.get('client_intent_id'),
            'parentIntentId': order.decision.get('parent_intent_id'),
            'parentPositionId': order.decision.get('parent_position_id'),
            'eventType': event_type,
            'timestamp': timestamp.isoformat(),
            'quantity': float(quantity) if quantity is not None else None,
            'price': float(price) if price is not None else None,
            'remainingQuantity': float(order.remaining_quantity),
            'reason': reason,
        })

    @staticmethod
    def _time_reached(current: datetime, target: datetime) -> bool:
        if current.tzinfo is None and target.tzinfo is not None:
            target = target.replace(tzinfo=None)
        elif current.tzinfo is not None and target.tzinfo is None:
            target = target.replace(tzinfo=current.tzinfo)
        return current >= target

    async def _run_risk_checks_with_timeout(self, snapshot: MarketSnapshot):
        """风控执行加超时，避免异常场景阻塞整条回测链路。"""
        timeout_s = max(0.1, float(self.config.risk_timeout_seconds))
        try:
            await asyncio.wait_for(self._run_risk_checks(snapshot), timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                "风控检查超时，跳过本轮风控: "
                f"timeout={timeout_s}s, ts={snapshot.timestamp.isoformat()}"
            )
        except Exception as e:
            logger.warning(f"风控检查异常，跳过本轮风控: {e}")

    async def _run_decision_with_timeout(self, snapshot: MarketSnapshot):
        """
        决策执行加超时与熔断，防止 LLM/外部依赖抖动导致回测卡死。
        """
        if self._decision_cooldown_remaining > 0:
            self._decision_cooldown_remaining -= 1
            self._record_decision(
                {
                    "action": "system_error",
                    "error_type": "decision_circuit_breaker",
                    "reason": (
                        f"决策熔断冷却中，剩余{self._decision_cooldown_remaining}步，"
                        "本轮跳过 LLM 决策"
                    ),
                    "signals": ["decision_circuit_breaker"],
                },
                snapshot,
            )
            return

        timeout_s = max(0.1, float(self.config.decision_timeout_seconds))
        try:
            ok = await asyncio.wait_for(self._run_decision(snapshot), timeout=timeout_s)
            if ok is True:
                self._decision_error_streak = 0
                return

            if ok is None:
                self._decision_error_streak += 1
                self._apply_decision_circuit_breaker_if_needed(snapshot)
                return

            self._decision_error_streak += 1
            self._record_decision(
                {
                    "action": "system_error",
                    "error_type": "decision_callback_error",
                    "reason": (
                        f"决策回调异常已被捕获；连续失败={self._decision_error_streak}"
                    ),
                    "signals": ["decision_callback_error"],
                },
                snapshot,
            )
            self._apply_decision_circuit_breaker_if_needed(snapshot)
        except asyncio.TimeoutError:
            self._decision_error_streak += 1
            reason = (
                f"LLM 决策超时({timeout_s}s)；"
                f"连续失败={self._decision_error_streak}"
            )
            logger.warning(
                "决策超时，已降级: "
                f"ts={snapshot.timestamp.isoformat()}, streak={self._decision_error_streak}"
            )
            self._record_decision(
                {
                    "action": "system_error",
                    "error_type": "decision_timeout",
                    "reason": reason,
                    "signals": ["decision_timeout"],
                },
                snapshot,
            )
            self._apply_decision_circuit_breaker_if_needed(snapshot)
        except Exception as e:
            self._decision_error_streak += 1
            logger.warning(
                "决策异常，已降级: "
                f"ts={snapshot.timestamp.isoformat()}, streak={self._decision_error_streak}, err={e}"
            )
            self._record_decision(
                {
                    "action": "system_error",
                    "error_type": "decision_exception",
                    "reason": f"决策异常({str(e)[:180]})",
                    "signals": ["decision_exception"],
                },
                snapshot,
            )
            self._apply_decision_circuit_breaker_if_needed(snapshot)

    def _apply_decision_circuit_breaker_if_needed(self, snapshot: MarketSnapshot):
        """
        连续异常触发短暂熔断，给外部 LLM/网络恢复窗口，避免每步持续阻塞。
        """
        threshold = max(1, int(self.config.max_consecutive_decision_errors))
        if self._decision_error_streak < threshold:
            return

        cooldown_steps = max(1, int(self.config.decision_cooldown_steps))
        self._decision_cooldown_remaining = cooldown_steps
        logger.warning(
            "触发决策熔断: "
            f"streak={self._decision_error_streak}, cooldown_steps={cooldown_steps}, "
            f"ts={snapshot.timestamp.isoformat()}"
        )
        self._decision_error_streak = 0
    
    def _decision_reference_price(self, decision: Dict, snapshot: MarketSnapshot) -> Optional[float]:
        """决策时点展示用参考价：优先决策中的交易对，否则按配置顺序取首个有价的标的。"""
        prices = snapshot.prices
        if not prices:
            return None
        sym = decision.get('symbol')
        if sym and sym in prices:
            return float(prices[sym])
        for s in self.config.symbols:
            if s in prices:
                return float(prices[s])
        first = next(iter(prices.values()), None)
        return float(first) if first is not None else None
    
    def _record_decision(self, decision: Dict, snapshot: MarketSnapshot):
        """记录单次决策（含 hold），供前端决策表格展示"""
        action = decision.get('action', 'hold')
        ref = self._decision_reference_price(decision, snapshot)
        decision_analysis = decision.get('decision_analysis') or decision.get('reason') or decision.get('reasoning', '')
        if action == 'hold':
            execution_result = {
                'status': 'no_action',
                'requestedAction': action,
                'finalAction': 'hold',
                'message': '本轮观望，未提交交易委托',
            }
        elif action == 'system_error':
            execution_result = {
                'status': 'error',
                'requestedAction': action,
                'finalAction': 'system_error',
                'message': decision_analysis or '决策系统错误，未提交交易委托',
            }
        else:
            execution_result = {
                'status': 'pending',
                'requestedAction': action,
                'finalAction': action,
                'message': '等待执行',
            }
        if decision.get('source_decision_id'):
            execution_result['sourceDecisionId'] = str(decision['source_decision_id'])
        if decision.get('execution_origin'):
            execution_result['executionOrigin'] = str(decision['execution_origin'])
        self.decision_log.append({
            'id': str(decision.get('decision_id') or uuid4()),
            'timestamp': snapshot.timestamp.isoformat(),
            'action': action,
            'symbol': decision.get('symbol'),
            'quantity': float(decision.get('quantity', 0)) if decision.get('quantity') is not None else None,
            'reasoning': decision_analysis,
            'decision_analysis': decision_analysis,
            'technical_analysis': decision.get('technical_analysis') or '',
            'chain_of_thought': decision.get('chain_of_thought', []),
            'current_price': ref,
            'decision_prompt': decision.get('decision_prompt') or '',
            'llm_raw_response': decision.get('llm_raw_response') or '',
            'parsed_decision': decision.get('parsed_decision') or '',
            'llm_metadata': decision.get('llm_metadata') or {},
            'error_type': decision.get('error_type'),
            'decision_mode': decision.get('decision_mode'),
            'outcome_type': decision.get('outcome_type'),
            'regime': decision.get('regime'),
            'rule_hits': decision.get('rule_hits') or [],
            'signals': decision.get('signals') or [],
            'indicators_snapshot': decision.get('indicators_snapshot') or {},
            'execution_result': execution_result,
        })
    
    async def _execute_decision(self, decision: Dict, snapshot: MarketSnapshot):
        """执行交易决策"""
        action = decision.get('action')
        symbol = decision.get('symbol')
        quantity = Decimal(str(decision.get('quantity', 0)))
        reasoning = decision.get('reason', '')
        chain_of_thought = decision.get('chain_of_thought', [])
        
        if not symbol or symbol not in snapshot.prices:
            self._mark_execution_rejected(decision, '交易对无效或缺少行情价格')
            return
        
        execution_prices = snapshot.execution_prices or snapshot.prices
        current_price = execution_prices.get(symbol)
        if current_price is None:
            self._mark_execution_rejected(decision, '下一根 K 线缺少可执行开盘价')
            return
        current_date = snapshot.timestamp.strftime('%Y-%m-%d')

        is_entry = action in ('open_long', 'open_short', 'add_long', 'add_short')
        if not is_entry and quantity <= 0:
            position = self.account.get_position(symbol)
            quantity = position.quantity if position else Decimal('0')

        # 按当前 bar 可成交量裁剪；平仓未显式给 quantity 时默认尝试全平。
        quantity = self._cap_quantity_by_participation(snapshot, symbol, quantity, current_price)
        if quantity <= 0:
            self._mark_execution_rejected(decision, '可成交数量为 0')
            return

        default_liquidity = self.config.strategy_config.get(
            'entryLiquidity' if is_entry else 'exitLiquidity', 'taker'
        )
        liquidity = str(decision.get('liquidity') or default_liquidity).lower()
        if liquidity not in {'maker', 'taker'}:
            liquidity = 'taker'
        slippage_rate = self._effective_slippage_rate(snapshot, symbol, quantity, liquidity)

        risk_price = (
            self._predicted_execution_price(action, current_price, slippage_rate)
            if is_entry else current_price
        )
        proposed = dict(decision)
        proposed['quantity'] = float(quantity)
        risk_evaluation = self.risk_kernel.evaluate(
            proposed,
            self.account,
            {**snapshot.prices, symbol: risk_price},
        )
        decision['risk_evaluation'] = risk_evaluation.to_dict()
        if not risk_evaluation.approved or not risk_evaluation.approved_decision:
            reason = (
                risk_evaluation.violations[0].message
                if risk_evaluation.violations else '硬风险内核拒绝该订单'
            )
            self._mark_execution_rejected(decision, reason)
            return
        quantity = Decimal(str(risk_evaluation.approved_decision.get('quantity') or quantity))
        decision['quantity'] = float(quantity)
        approved_leverage = Decimal(str(
            risk_evaluation.approved_decision.get('leverage')
            or decision.get('requested_leverage')
            or self.account.leverage
        ))
        decision['leverage'] = float(approved_leverage)
        if risk_evaluation.status == 'resized':
            decision.setdefault('signals', []).append('risk_kernel_resized')
        if self.decision_log:
            self.decision_log[-1]['quantity'] = float(quantity)
            self.decision_log[-1]['signals'] = list(decision.get('signals') or [])
            self.decision_log[-1]['risk_evaluation'] = risk_evaluation.to_dict()

        if is_entry:
            rejection = self._validate_open_at_execution(
                decision, action, current_price, slippage_rate, liquidity
            )
            if rejection:
                self._mark_execution_rejected(decision, rejection)
                logger.info(f"开仓在真实执行价复核时取消: {symbol}, reason={rejection}")
                return

            predicted_entry = risk_price
            order_amount = quantity * predicted_entry
            # Trader 的交易质量已经由模型负责，资金安全由 RiskKernel 负责。
            # 旧 RiskManager 的仓位/金额规则只服务 rule 模式，避免形成第二套
            # 隐含策略 veto；Trader 这里只保留配置型订单频率硬限制。
            if str(decision.get('decision_mode') or self.decision_mode) == 'trader':
                risk_check = self.risk_manager.check_daily_trades(current_date)
            else:
                risk_check = self.risk_manager.check_new_order(
                    self.account, order_amount, current_date
                )
            if not risk_check.passed:
                self._mark_execution_rejected(decision, risk_check.reason)
                logger.debug(f"风控拒绝: {risk_check.reason}")
                return

        # 执行交易
        trade = None
        position_before = self.account.get_position(symbol)
        parent_position_id = getattr(position_before, 'lifecycle_id', None)
        if action in {'open_long', 'add_long'}:
            trade = self.account.open_long(
                symbol=symbol,
                quantity=quantity,
                current_price=current_price,
                timestamp=snapshot.timestamp,
                reasoning=reasoning,
                signals=decision.get('signals'),
                chain_of_thought=chain_of_thought,
                liquidity=liquidity,
                slippage_rate=slippage_rate,
                leverage=approved_leverage,
            )
            if trade and decision.get('trade_plan'):
                pos = self.account.get_position(symbol)
                if pos:
                    pos.trade_plan = decision['trade_plan']
        elif action in {'open_short', 'add_short'}:
            trade = self.account.open_short(
                symbol=symbol,
                quantity=quantity,
                current_price=current_price,
                timestamp=snapshot.timestamp,
                reasoning=reasoning,
                signals=decision.get('signals'),
                chain_of_thought=chain_of_thought,
                liquidity=liquidity,
                slippage_rate=slippage_rate,
                leverage=approved_leverage,
            )
            if trade and decision.get('trade_plan'):
                pos = self.account.get_position(symbol)
                if pos:
                    pos.trade_plan = decision['trade_plan']
        elif action in {'reduce_long', 'close_long'}:
            trade = self.account.close_long(
                symbol=symbol,
                quantity=quantity if quantity > 0 else None,
                current_price=current_price,
                timestamp=snapshot.timestamp,
                reasoning=reasoning,
                signals=decision.get('signals'),
                chain_of_thought=chain_of_thought,
                liquidity=liquidity,
                slippage_rate=slippage_rate,
            )
        elif action in {'reduce_short', 'close_short'}:
            trade = self.account.close_short(
                symbol=symbol,
                quantity=quantity if quantity > 0 else None,
                current_price=current_price,
                timestamp=snapshot.timestamp,
                reasoning=reasoning,
                signals=decision.get('signals'),
                chain_of_thought=chain_of_thought,
                liquidity=liquidity,
                slippage_rate=slippage_rate,
            )
        
        if trade:
            # VirtualAccount 的 trade_type 只有 open/close；在这里保留决策的细粒度动作。
            trade.action = action
            decision['quantity'] = float(trade.quantity)
            position_after = self.account.get_position(symbol)
            if is_entry and position_after:
                if position_before is None:
                    position_after.lifecycle_id = str(
                        decision.get('position_lifecycle_id') or uuid4()
                    )
                    position_after.entry_intent_id = (
                        str(decision.get('client_intent_id'))
                        if decision.get('client_intent_id') else None
                    )
                decision['position_lifecycle_id'] = position_after.lifecycle_id
                if isinstance(position_after.trade_plan, dict):
                    position_after.trade_plan['position_lifecycle_id'] = (
                        position_after.lifecycle_id
                    )
                    position_after.trade_plan['entry_intent_id'] = (
                        position_after.entry_intent_id
                    )
            elif not is_entry and position_after is None:
                self._cancel_child_orders_for_position(
                    parent_position_id,
                    snapshot.timestamp,
                    reason='parent_position_closed_by_order',
                )
            execution_result = {
                **self._execution_plan_snapshot(decision),
                'status': 'filled',
                'requestedAction': action,
                'finalAction': action,
                'tradeId': trade.id,
                'side': trade.side,
                'tradeType': trade.trade_type,
                'quantity': float(trade.quantity),
                'price': float(trade.price),
                'amount': float(trade.amount),
                'requestedLeverage': decision.get('requested_leverage'),
                'approvedLeverage': float(trade.leverage),
                'marginUsed': float(trade.amount / trade.leverage),
                'fee': float(trade.fee),
                'pnl': float(trade.pnl),
                'pnlPercent': float(trade.pnl_percent),
                'balanceAfter': float(trade.balance),
                'positionQuantityAfter': (
                    float(position_after.quantity) if position_after else 0.0
                ),
                'message': (
                    f"{action} 已成交：数量 {trade.quantity}，"
                    f"价格 {trade.price}，金额 {trade.amount}"
                ),
            }
            if decision.get('source_decision_id'):
                execution_result['sourceDecisionId'] = str(decision['source_decision_id'])
            if decision.get('execution_origin'):
                execution_result['executionOrigin'] = str(decision['execution_origin'])
            decision['execution_result'] = execution_result
            if self.decision_log:
                self.decision_log[-1]['quantity'] = float(trade.quantity)
                self.decision_log[-1]['execution_result'] = execution_result
            self.risk_manager.increment_trade_count(current_date)
        else:
            self._mark_execution_rejected(decision, '账户未生成成交记录')

    @staticmethod
    def _predicted_execution_price(
        action: str, market_price: Decimal, slippage_rate: Decimal
    ) -> Decimal:
        multiplier = (
            Decimal('1') + slippage_rate
            if action in {'open_long', 'add_long', 'reduce_short', 'close_short'}
            else Decimal('1') - slippage_rate
        )
        return (market_price * multiplier).quantize(
            Decimal('0.00000001'), rounding=ROUND_DOWN
        )

    def _cap_entry_quantity_by_risk_limits(
        self,
        quantity: Decimal,
        predicted_entry: Decimal,
    ) -> Decimal:
        """按实际预计成交价裁剪数量，避免价格跳空使名义金额略超风控上限。"""
        if quantity <= 0 or predicted_entry <= 0:
            return Decimal('0')

        risk_config = self.risk_manager.config
        current_position_value = sum(
            pos.quantity * pos.entry_price for pos in self.account.get_all_positions()
        )
        max_position_value = (
            self.account.equity * risk_config.max_position_ratio / Decimal('100')
        )
        remaining_position_budget = max(
            Decimal('0'), max_position_value - current_position_value
        )
        max_notional = min(
            risk_config.max_order_amount,
            remaining_position_budget,
        )
        if max_notional <= 0:
            return Decimal('0')

        max_quantity = (max_notional / predicted_entry).quantize(
            Decimal('0.00000001'), rounding=ROUND_DOWN
        )
        return min(quantity, max_quantity)

    def _validate_open_at_execution(
        self,
        decision: Dict[str, Any],
        action: str,
        market_price: Decimal,
        slippage_rate: Decimal,
        liquidity: str,
    ) -> Optional[str]:
        """用下一根真实开盘价校验保护价方向，不评价交易质量。"""
        plan = decision.get('trade_plan') if isinstance(decision.get('trade_plan'), dict) else decision
        try:
            stop = Decimal(str(plan.get('stop_loss_price')))
        except (ArithmeticError, TypeError, ValueError):
            return "缺少有效的保护性止损价"
        take_raw = plan.get('take_profit_price')
        try:
            take = Decimal(str(take_raw)) if take_raw is not None else None
        except (ArithmeticError, TypeError, ValueError):
            return "止盈价格格式无效"

        entry = self._predicted_execution_price(action, market_price, slippage_rate)
        if entry <= 0 or stop <= 0:
            return "实际成交价或保护性止损价格无效"

        if action in {'open_long', 'add_long'}:
            if stop >= entry:
                return f"实际成交后多单止损方向失效: stop={stop}, entry={entry}"
            if take is not None and take <= entry:
                return f"实际成交后多单止盈方向失效: take={take}, entry={entry}"
        else:
            if stop <= entry:
                return f"实际成交后空单止损方向失效: stop={stop}, entry={entry}"
            if take is not None and take >= entry:
                return f"实际成交后空单止盈方向失效: take={take}, entry={entry}"
        return None

    def _mark_execution_rejected(self, decision: Dict[str, Any], reason: str) -> None:
        """保留模型原始输出，同时让决策日志准确反映未成交的 hold。"""
        signal = 'execution_revalidation_rejected'
        decision.setdefault('signals', []).append(signal)
        decision['execution_rejection_reason'] = reason
        requested_action = str(decision.get('action') or 'hold')
        execution_result = {
            **self._execution_plan_snapshot(decision),
            'status': 'rejected',
            'requestedAction': requested_action,
            'finalAction': 'hold',
            'message': reason,
        }
        decision['execution_result'] = execution_result
        if not self.decision_log:
            return
        row = self.decision_log[-1]
        row['action'] = 'hold'
        row['reasoning'] = f"执行前复核取消开仓：{reason}"
        row['decision_analysis'] = row['reasoning']
        row['signals'] = list(dict.fromkeys((row.get('signals') or []) + [signal]))
        row['execution_result'] = execution_result

    @staticmethod
    def _execution_plan_snapshot(decision: Dict[str, Any]) -> Dict[str, Any]:
        """把执行所依据的订单与保护价格固化进回执，供历史详情可靠展示。"""
        plan = decision.get('trade_plan') or {}
        return {
            'orderType': decision.get('order_type') or 'market',
            'limitPrice': decision.get('limit_price'),
            'stopLossPrice': (
                decision.get('stop_loss_price')
                if decision.get('stop_loss_price') is not None
                else plan.get('stop_loss_price')
            ),
            'takeProfitPrice': (
                decision.get('take_profit_price')
                if decision.get('take_profit_price') is not None
                else plan.get('take_profit_price')
            ),
            'requestedLeverage': decision.get('requested_leverage'),
            'executionRole': decision.get('execution_role') or 'standalone',
            'clientIntentId': decision.get('client_intent_id'),
            'parentIntentId': decision.get('parent_intent_id'),
        }

    def _cap_quantity_by_participation(
        self, snapshot: MarketSnapshot, symbol: str, quantity: Decimal, price: Decimal
    ) -> Decimal:
        bar = (snapshot.current_bars or {}).get(symbol)
        if not bar or quantity <= 0:
            return quantity
        quote_volume = bar.quote_volume or (bar.volume * bar.close)
        max_rate = self.config.max_participation_rate / Decimal('100')
        if quote_volume <= 0 or max_rate <= 0:
            return quantity
        max_quantity = (quote_volume * max_rate) / price
        return min(quantity, max_quantity)

    def _effective_slippage_rate(
        self, snapshot: MarketSnapshot, symbol: str, quantity: Decimal, liquidity: str
    ) -> Decimal:
        """基础滑点 + 成交参与率/波动率冲击，返回小数费率。"""
        bar = (snapshot.current_bars or {}).get(symbol)
        base = Decimal('0') if liquidity == 'maker' else self.config.slippage / Decimal('100')
        fixed_impact = self.config.market_impact_bps / Decimal('10000')
        if not bar or quantity <= 0 or bar.close <= 0:
            return base + fixed_impact
        quote_volume = bar.quote_volume or (bar.volume * bar.close)
        notional = quantity * bar.open
        participation = float(notional / quote_volume) if quote_volume > 0 else 1.0
        range_pct = float((bar.high - bar.low) / bar.close) if bar.close > 0 else 0.0
        dynamic = float(self.config.impact_volatility_weight) * range_pct * math.sqrt(max(0.0, participation))
        impact = fixed_impact + Decimal(str(dynamic))
        impact = min(impact, self.config.max_impact_pct / Decimal('100'))
        if liquidity == 'maker':
            impact *= Decimal('0.5')
        return base + impact

    def _apply_funding_if_due(
        self, snapshot: MarketSnapshot, close_prices: Dict[str, Decimal]
    ) -> None:
        rate = self.config.funding_rate_per_interval
        interval_hours = max(1, int(self.config.funding_interval_hours))
        slot_seconds = interval_hours * 3600
        epoch = int(snapshot.timestamp.timestamp())
        slot = epoch // slot_seconds
        if rate == 0 or slot in self._settled_funding_slots or epoch % slot_seconds >= self._get_interval_seconds():
            return
        self.account.apply_funding(close_prices, rate / Decimal('100'))
        self._settled_funding_slots.add(slot)
    
    def _calculate_benchmark_equity(self, prices: Dict[str, Decimal]) -> Decimal:
        """计算基准权益（买入持有策略）"""
        if not self.benchmark_start_prices:
            return self.config.initial_capital
        
        # 假设在开始时用全部资金均匀买入所有交易对
        total_return = Decimal('0')
        symbol_count = len(self.benchmark_start_prices)
        
        for symbol, start_price in self.benchmark_start_prices.items():
            if symbol in prices and start_price > 0:
                return_ratio = (prices[symbol] - start_price) / start_price
                total_return += return_ratio
        
        if symbol_count > 0:
            avg_return = total_return / symbol_count
            return self.config.initial_capital * (1 + avg_return)
        
        return self.config.initial_capital
    
    def _serialize_live_decision_log(self, max_rows: int = 200) -> Dict[str, Any]:
        """最近 N 条决策摘要；完整审计内容通过 /decisions 按需读取。"""
        total = len(self.decision_log)
        tail = self.decision_log[-max_rows:] if total > max_rows else self.decision_log
        out: List[Dict[str, Any]] = []
        for d in tail:
            ts = d.get("timestamp")
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
            row = {
                "id": d.get("id"),
                "timestamp": ts,
                "action": d.get("action", "hold"),
                "symbol": d.get("symbol"),
                "quantity": d.get("quantity"),
                "reasoning": d.get("reasoning") or "",
                "decisionAnalysis": d.get("decision_analysis") or d.get("reasoning") or "",
                "executionResult": d.get("execution_result") or {},
            }
            if d.get("error_type"):
                row["errorType"] = d["error_type"]
            if d.get("current_price") is not None:
                row["currentPrice"] = d["current_price"]
            if d.get("decision_mode"):
                row["decisionMode"] = d["decision_mode"]
            if d.get("outcome_type"):
                row["outcomeType"] = d["outcome_type"]
            if d.get("regime"):
                row["regime"] = d["regime"]
            if d.get("signals"):
                row["signals"] = d["signals"]
            out.append(row)
        return {
            "decisionLog": out,
            "decisionLogTotal": total,
            "decisionLogTruncated": total > max_rows,
        }
    
    def build_live_preview(self, max_points: int = 800) -> Dict[str, Any]:
        """
        运行中导出当前权益曲线与统计，写入 progress_snapshot.livePreview 供前端轮询。
        曲线过长时降采样以控制 JSON 体积。
        """
        full = self.account.equity_history
        if len(full) > max_points:
            step = max(1, len(full) // max_points)
            rows = list(full[::step])
            if full and rows[-1]["timestamp"] != full[-1]["timestamp"]:
                rows.append(full[-1])
        else:
            rows = list(full)

        equity_curve: List[Dict[str, Any]] = []
        drawdown_curve: List[Dict[str, Any]] = []
        benchmark_curve: List[Dict[str, Any]] = []
        for record in rows:
            ts = record["timestamp"].isoformat()
            equity_curve.append({
                "time": ts,
                "value": float(record["equity"]),
                "unrealizedPnl": float(record.get("unrealized_pnl", 0)),
                "unrealizedPnlRate": float(record.get("unrealized_pnl_rate", 0)),
            })
            drawdown_curve.append({"time": ts, "value": float(record["drawdown"])})
            if record.get("benchmark") is not None:
                benchmark_curve.append({"time": ts, "value": float(record["benchmark"])})

        s = self.account.get_statistics()
        closed_trades = sum(
            1 for t in self.account.trades
            if t.trade_type == "close" and t.round_trip_complete
        )
        win_rate_closed = round(
            (self.account.win_trades / closed_trades * 100) if closed_trades > 0 else 0.0,
            2,
        )

        open_positions = self._serialize_live_open_positions()
        unrealized_pnl_total = round(
            sum(float(p["unrealizedPnl"]) for p in open_positions), 4
        )
        mark_prices = {
            symbol: float(price) for symbol, price in self._last_mark_prices.items()
        }

        statistics: Dict[str, Any] = {
            "totalReturn": float(s["total_return"]),
            "annualizedReturn": float(self._calculate_annualized_return(s["total_return"])),
            "maxDrawdown": float(s["max_drawdown"]),
            "sharpeRatio": float(self._calculate_sharpe_ratio()),
            "sortinoRatio": None,
            "winRate": win_rate_closed,
            "profitFactor": float(s["profit_factor"]),
            "totalTrades": int(s["total_trades"]),
            "closedTrades": closed_trades,
            "winTrades": int(s["win_trades"]),
            "lossTrades": int(s["lose_trades"]),
            "avgProfit": float(s["avg_profit"]),
            "avgLoss": float(s["avg_loss"]),
            "avgHoldingTime": None,
            "maxConsecutiveWins": self._calculate_max_consecutive_wins(),
            "maxConsecutiveLosses": self._calculate_max_consecutive_losses(),
            "finalCapital": float(s["final_capital"]),
            "totalFees": float(s.get("total_fees", 0.0)),
            "totalSlippageCost": float(s.get("total_slippage_cost", 0.0)),
            "totalFunding": float(s.get("total_funding", 0.0)),
            "totalTradingCosts": float(
                s.get("total_fees", 0.0)
                + s.get("total_slippage_cost", 0.0)
                + s.get("total_funding", 0.0)
            ),
            "balanceAtEnd": float(self.account.balance),
            "unrealizedPnlTotal": unrealized_pnl_total,
            "openPositions": open_positions,
        }

        dl_meta = self._serialize_live_decision_log(200)
        preview: Dict[str, Any] = {
            "equityCurve": equity_curve,
            "drawdownCurve": drawdown_curve,
            "benchmarkCurve": benchmark_curve,
            "statistics": statistics,
            "decisionLog": dl_meta["decisionLog"],
            "decisionLogTotal": dl_meta["decisionLogTotal"],
            "decisionLogTruncated": dl_meta["decisionLogTruncated"],
            "trades": self._serialize_live_trades(),
            "openPositions": open_positions,
            "activeOrders": self._serialize_live_active_orders(
                full[-1]["timestamp"] if full else None,
            ),
            "markPrices": mark_prices,
            "balance": float(self.account.balance),
            "equity": float(self.account.equity),
            "lastAction": self._build_live_last_action(),
        }
        return preview

    def _serialize_live_open_positions(self) -> List[Dict[str, Any]]:
        """运行中当前未平持仓（含现价与浮盈）。"""
        out: List[Dict[str, Any]] = []
        for pos in self.account.get_all_positions():
            current_price = self._last_mark_prices.get(pos.symbol)
            if current_price is None and pos.quantity:
                if pos.side == "long":
                    current_price = pos.entry_price + (pos.unrealized_pnl / pos.quantity)
                else:
                    current_price = pos.entry_price - (pos.unrealized_pnl / pos.quantity)
            if current_price is None:
                current_price = pos.entry_price
            pnl_percent = float(pos.get_pnl_percent(current_price))
            margin_used = float(pos.margin_used)
            roi_percent = (
                float(pos.unrealized_pnl / pos.margin_used * Decimal("100"))
                if pos.margin_used > 0 else 0.0
            )
            raw_plan = pos.trade_plan if isinstance(pos.trade_plan, dict) else {}
            trade_plan = {
                "stopLossPrice": raw_plan.get("stop_loss_price"),
                "takeProfitPrice": raw_plan.get("take_profit_price"),
                "thesis": raw_plan.get("thesis") or "",
                "invalidation": raw_plan.get("invalidation") or "",
            }
            out.append({
                "symbol": pos.symbol,
                "side": pos.side,
                "quantity": float(pos.quantity),
                "entryPrice": float(pos.entry_price),
                "leverage": float(pos.leverage),
                "marginUsed": margin_used,
                "currentPrice": float(current_price),
                "endPrice": float(current_price),
                "unrealizedPnl": float(pos.unrealized_pnl),
                "unrealizedPnlPercent": pnl_percent,
                "roiPercent": roi_percent,
                "entryTime": pos.entry_time.isoformat() if pos.entry_time else None,
                "notional": float(pos.quantity * current_price),
                "tradePlan": trade_plan,
            })
        return out

    def _build_live_last_action(self) -> Optional[Dict[str, Any]]:
        """最近一次决策或成交摘要，供顶栏展示。"""
        last_decision = self.decision_log[-1] if self.decision_log else None
        last_trade = self.account.trades[-1] if self.account.trades else None

        def _ts(value: Any) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        decision_ts = _ts(last_decision.get("timestamp")) if last_decision else None
        trade_ts = last_trade.timestamp if last_trade else None

        use_trade = bool(last_trade and trade_ts and (not decision_ts or trade_ts >= decision_ts))

        if use_trade and last_trade:
            action = last_trade.action or f"{last_trade.side}_{last_trade.trade_type}"
            action_labels = {
                "open_long": "开多",
                "open_short": "开空",
                "add_long": "加多",
                "add_short": "加空",
                "reduce_long": "减多",
                "reduce_short": "减空",
                "close_long": "平多",
                "close_short": "平空",
            }
            summary = (
                f"{action_labels.get(action, action)} {last_trade.symbol} "
                f"{float(last_trade.quantity):.8g} @ {float(last_trade.price):.8g}"
            )
            return {
                "kind": "trade",
                "timestamp": trade_ts.isoformat() if trade_ts else None,
                "action": action,
                "side": last_trade.side,
                "type": last_trade.trade_type,
                "quantity": float(last_trade.quantity),
                "amount": float(last_trade.amount),
                "fee": float(last_trade.fee),
                "symbol": last_trade.symbol,
                "price": float(last_trade.price),
                "summary": summary,
            }

        if last_decision:
            action = str(last_decision.get("action") or "hold")
            symbol = last_decision.get("symbol") or ""
            price = last_decision.get("current_price")
            reason = (
                last_decision.get("decision_analysis")
                or last_decision.get("reasoning")
                or last_decision.get("reason")
                or ""
            )
            reason_short = str(reason).strip().replace("\n", " ")
            if len(reason_short) > 48:
                reason_short = reason_short[:48] + "…"
            action_labels = {
                "hold": "观望",
                "open_long": "开多",
                "open_short": "开空",
                "add_long": "加多",
                "add_short": "加空",
                "reduce_long": "减多",
                "reduce_short": "减空",
                "close_long": "平多",
                "close_short": "平空",
            }
            label = action_labels.get(action, action)
            summary = f"{label} {symbol}".strip()
            if reason_short:
                summary = f"{summary} · {reason_short}"
            return {
                "kind": "decision",
                "timestamp": decision_ts.isoformat() if decision_ts else None,
                "action": action,
                "symbol": symbol or None,
                "price": float(price) if price is not None else None,
                "summary": summary,
            }
        return None

    def _serialize_live_trades(self) -> List[Dict[str, Any]]:
        """全部成交记录，字段与完成后 API 的 trades 一致（camelCase）。"""
        out: List[Dict[str, Any]] = []
        for t in self.account.trades:
            out.append({
                "id": t.id,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                "symbol": t.symbol,
                "side": t.side,
                "type": t.trade_type,
                "action": t.action,
                "price": float(t.price),
                "quantity": float(t.quantity),
                "amount": float(t.amount),
                "fee": float(t.fee),
                "pnl": float(t.pnl),
                "pnlPercent": float(t.pnl_percent),
                "roundTripComplete": bool(t.round_trip_complete),
                "roundTripPnl": float(t.round_trip_pnl),
                "balance": float(t.balance),
                "reasoning": t.reasoning,
                "signals": t.signals,
                "chainOfThought": t.chain_of_thought or [],
            })
        return out
    
    def _force_close_open_positions(self, end_prices: Dict[str, Decimal], end_time: datetime) -> None:
        """
        回测结束时对所有未平持仓按结束价强制平仓，生成 close trade。

        之前 `_build_result` 只更新未实现盈亏计入 equity，没有生成 close trade，
        导致 closed_trades=0 且统计数据（胜率/盈亏比/平均盈亏）失真，无法反映
        LLM 持仓管理的真实表现。这里强制平仓并把浮盈/浮亏落账，reasoning 标注
        「回测结束强制平仓」便于前端区分。
        """
        if not self.account.positions:
            return

        for symbol in list(self.account.positions.keys()):
            position = self.account.positions.get(symbol)
            if not position:
                continue
            current_price = end_prices.get(symbol)
            if current_price is None:
                # 没有结束价兜底：用持仓最高/最低价或入场价兜底，避免遗漏平仓
                current_price = position.entry_price
            reasoning = "回测结束强制平仓"
            parent_position_id = getattr(position, 'lifecycle_id', None)
            liquidity = str((self.config.strategy_config or {}).get('exitLiquidity', 'taker')).lower()
            if liquidity not in {'maker', 'taker'}:
                liquidity = 'taker'
            bars = [
                bar for bar in self.kline_data.get(symbol, [])
                if bar.timestamp <= end_time
            ]
            current_bar = bars[-1] if bars else None
            force_snapshot = MarketSnapshot(
                timestamp=end_time,
                prices={symbol: current_price},
                klines={},
                execution_prices={symbol: current_price},
                current_bars={symbol: current_bar} if current_bar else {},
            )
            slippage_rate = self._effective_slippage_rate(
                force_snapshot, symbol, position.quantity, liquidity
            )
            if position.side == "long":
                self.account.close_long(
                    symbol=symbol,
                    quantity=None,
                    current_price=current_price,
                    timestamp=end_time,
                    reasoning=reasoning,
                    signals=["force_close_at_end"],
                    liquidity=liquidity,
                    slippage_rate=slippage_rate,
                )
            else:
                self.account.close_short(
                    symbol=symbol,
                    quantity=None,
                    current_price=current_price,
                    timestamp=end_time,
                    reasoning=reasoning,
                    signals=["force_close_at_end"],
                    liquidity=liquidity,
                    slippage_rate=slippage_rate,
                )
            if self.account.get_position(symbol) is None:
                self._cancel_child_orders_for_position(
                    parent_position_id,
                    end_time,
                    reason='parent_position_closed_at_backtest_end',
                )

    def _build_result(self) -> BacktestResult:
        """构建回测结果"""
        result = BacktestResult()
        
        # 各交易对开始/结束价格（用于前端展示）
        symbol_prices = {}
        end_prices_decimal = {}
        for symbol in self.config.symbols:
            klist = self.kline_data.get(symbol, [])
            if not klist:
                continue
            klist_sorted = sorted(klist, key=lambda k: k.timestamp)
            within_range = [k for k in klist_sorted if k.timestamp <= self.config.end_time]
            if not within_range:
                within_range = klist_sorted
            symbol_prices[symbol] = {
                'startPrice': float(klist_sorted[0].close),
                'endPrice': float(within_range[-1].close)
            }
            end_prices_decimal[symbol] = within_range[-1].close
        
        # 用结束价更新持仓未实现盈亏，确保最终权益一致
        self.account.update_positions_pnl(end_prices_decimal)

        # 回测结束强制平仓：把所有未平持仓按结束价落账为 close trade，
        # 避免 closed_trades=0 且统计数据失真
        self._force_close_open_positions(end_prices_decimal, self.config.end_time)

        # 最后一条权益必须反映强平手续费/冲击成本，否则曲线终点与 finalCapital 不一致。
        if self.account.equity_history:
            benchmark = self.account.equity_history[-1].get('benchmark')
            if self.account.equity_history[-1].get('timestamp') == self.config.end_time:
                self.account.equity_history.pop()
            self.account.record_equity(self.config.end_time, benchmark)

        # 未平仓持仓列表（强制平仓后通常为空；保留逻辑以兼容未来部分平仓场景）
        open_positions = []
        for pos in self.account.get_all_positions():
            ep = symbol_prices.get(pos.symbol, {}).get('endPrice')
            if ep is not None:
                open_positions.append({
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'quantity': float(pos.quantity),
                    'entryPrice': float(pos.entry_price),
                    'leverage': float(pos.leverage),
                    'marginUsed': float(pos.margin_used),
                    'endPrice': ep,
                    'unrealizedPnl': float(pos.unrealized_pnl)
                })
        balance_at_end = float(self.account.balance)
        unrealized_pnl_total = round(sum(p['unrealizedPnl'] for p in open_positions), 4)
        closed_trades = sum(
            1 for t in self.account.trades
            if t.trade_type == 'close' and t.round_trip_complete
        )
        win_rate_closed = round(
            (self.account.win_trades / closed_trades * 100) if closed_trades > 0 else 0.0, 2
        )
        
        # 获取账户统计
        stats = self.account.get_statistics()
        autonomy_metrics = {
            'noTradeCount': sum(1 for d in self.decision_log if d.get('outcome_type') == 'NO_TRADE'),
            'shadowProposalCount': sum(1 for d in self.decision_log if d.get('outcome_type') == 'SHADOW_PROPOSAL'),
            'riskRejectedCount': sum(1 for d in self.decision_log if d.get('outcome_type') == 'RISK_REJECTED'),
            'abandonedCount': sum(1 for d in self.decision_log if d.get('outcome_type') == 'ABANDONED'),
            'systemErrorCount': sum(1 for d in self.decision_log if d.get('outcome_type') == 'SYSTEM_ERROR'),
            'committedCount': sum(1 for d in self.decision_log if d.get('outcome_type') == 'COMMITTED'),
            'executionRejectedCount': sum(
                1 for d in self.decision_log
                if (d.get('execution_result') or {}).get('status') == 'rejected'
            ),
            # Phase 4 的结构性不变量：Trader 执行路径没有策略型否决器。
            'strategyVetoCount': 0 if self.decision_mode == 'trader' else None,
        }
        
        # 计算额外统计指标（胜率改为“已平仓胜率”）
        result.statistics = {
            'totalReturn': stats['total_return'],
            'annualizedReturn': self._calculate_annualized_return(stats['total_return']),
            'maxDrawdown': stats['max_drawdown'],
            'sharpeRatio': self._calculate_sharpe_ratio(),
            'sortinoRatio': None,  # TODO: 实现索提诺比率
            'winRate': win_rate_closed,
            'profitFactor': stats['profit_factor'],
            'totalTrades': stats['total_trades'],
            'closedTrades': closed_trades,
            'winTrades': stats['win_trades'],
            'lossTrades': stats['lose_trades'],
            'avgProfit': stats['avg_profit'],
            'avgLoss': stats['avg_loss'],
            'avgHoldingTime': None,  # TODO: 计算平均持仓时间
            'maxConsecutiveWins': self._calculate_max_consecutive_wins(),
            'maxConsecutiveLosses': self._calculate_max_consecutive_losses(),
            'finalCapital': stats['final_capital'],
            'symbolPrices': symbol_prices,
            'openPositions': open_positions,
            'balanceAtEnd': balance_at_end,
            'unrealizedPnlTotal': unrealized_pnl_total,
            'totalFees': stats.get('total_fees', 0.0),
            'totalSlippageCost': stats.get('total_slippage_cost', 0.0),
            'totalFunding': stats.get('total_funding', 0.0),
            'totalTradingCosts': (
                stats.get('total_fees', 0.0)
                + stats.get('total_slippage_cost', 0.0)
                + stats.get('total_funding', 0.0)
            ),
            'autonomyMetrics': autonomy_metrics,
        }
        
        # 交易记录
        result.trades = self.account.trades
        
        # 决策记录（每次决策的思考过程，含 hold）
        result.decision_log = list(self.decision_log)
        result.order_events = list(self.order_events)
        
        # 曲线数据
        for record in self.account.equity_history:
            time_str = record['timestamp'].isoformat()
            result.equity_curve.append({
                'time': time_str,
                'value': float(record['equity']),
                'unrealizedPnl': float(record.get('unrealized_pnl', 0)),
                'unrealizedPnlRate': float(record.get('unrealized_pnl_rate', 0)),
            })
            result.drawdown_curve.append({
                'time': time_str,
                'value': float(record['drawdown'])
            })
            if record['benchmark']:
                result.benchmark_curve.append({
                    'time': time_str,
                    'value': float(record['benchmark'])
                })
        
        return result
    
    def _calculate_annualized_return(self, total_return: float) -> float:
        """计算年化收益率"""
        days = (self.config.end_time - self.config.start_time).days
        if days <= 0:
            return total_return
        
        # 年化收益率 = (1 + 总收益率) ^ (365/天数) - 1
        return ((1 + total_return / 100) ** (365 / days) - 1) * 100
    
    def _calculate_sharpe_ratio(self) -> float:
        """计算夏普比率（简化版）"""
        if len(self.account.equity_history) < 2:
            return 0
        
        # 计算日收益率
        daily_returns = []
        for i in range(1, len(self.account.equity_history)):
            prev_equity = self.account.equity_history[i-1]['equity']
            curr_equity = self.account.equity_history[i]['equity']
            if prev_equity > 0:
                daily_return = float((curr_equity - prev_equity) / prev_equity)
                daily_returns.append(daily_return)
        
        if not daily_returns:
            return 0
        
        # 计算平均收益率和标准差
        import statistics
        avg_return = statistics.mean(daily_returns)
        if len(daily_returns) > 1:
            std_return = statistics.stdev(daily_returns)
        else:
            return 0
        
        if std_return == 0:
            return 0
        
        # 年化夏普比率（假设无风险利率为0）
        sharpe = (avg_return / std_return) * (252 ** 0.5)  # 252是交易日
        return round(sharpe, 2)
    
    def _calculate_max_consecutive_wins(self) -> int:
        """计算最大连续盈利次数"""
        max_wins = 0
        current_wins = 0
        
        for trade in self.account.trades:
            if trade.trade_type == 'close' and trade.round_trip_complete:
                if trade.round_trip_pnl > 0:
                    current_wins += 1
                    max_wins = max(max_wins, current_wins)
                else:
                    current_wins = 0
        
        return max_wins
    
    def _calculate_max_consecutive_losses(self) -> int:
        """计算最大连续亏损次数"""
        max_losses = 0
        current_losses = 0
        
        for trade in self.account.trades:
            if trade.trade_type == 'close' and trade.round_trip_complete:
                if trade.round_trip_pnl < 0:
                    current_losses += 1
                    max_losses = max(max_losses, current_losses)
                else:
                    current_losses = 0
        
        return max_losses
