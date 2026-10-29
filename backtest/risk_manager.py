#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
风控规则引擎
用于回测和实盘的风险控制
"""
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime, timedelta

from backtest.virtual_account import VirtualAccount, Position
from decision.types import resolve_decision_mode
from trader.risk_kernel import HardRiskPolicy


@dataclass
class RiskConfig:
    """风控配置"""
    # 仓位控制
    max_position_ratio: Decimal = Decimal('30')  # 最大持仓比例(%)
    
    # 止盈止损（None 表示由 AI 判断，不强制）
    take_profit_ratio: Optional[Decimal] = None  # 止盈比例(%)，仅作兜底
    stop_loss_ratio: Optional[Decimal] = None    # 止损比例(%)，仅作兜底

    # 追踪止损
    trailing_stop_enabled: bool = False
    trailing_stop_ratio: Decimal = Decimal('2')  # 追踪止损回撤比例(%)
    
    # 交易限制
    max_daily_trades: int = 50                   # 单日最大交易次数
    min_order_amount: Decimal = Decimal('10')    # 单笔最小金额(USDT)
    max_order_amount: Decimal = Decimal('1000')  # 单笔最大金额(USDT)
    
    # 价格偏离
    price_deviation_upper: Decimal = Decimal('1')  # 挂单价格偏离上限(%)
    price_deviation_lower: Decimal = Decimal('1')  # 挂单价格偏离下限(%)


class RiskCheckResult:
    """风控检查结果"""
    
    def __init__(self, passed: bool, reason: str = ""):
        self.passed = passed
        self.reason = reason
        self.actions: List[Dict] = []  # 需要执行的风控动作
    
    def add_action(self, action_type: str, **kwargs):
        """添加风控动作"""
        self.actions.append({
            'type': action_type,
            **kwargs
        })


class RiskManager:
    """风控管理器"""
    
    def __init__(self, config: RiskConfig):
        self.config = config
        self.daily_trade_count: Dict[str, int] = {}  # 日期 -> 交易次数
    
    def reset_daily_count(self, date: str):
        """重置每日交易计数"""
        if date not in self.daily_trade_count:
            self.daily_trade_count[date] = 0
    
    def increment_trade_count(self, date: str):
        """增加交易计数"""
        if date not in self.daily_trade_count:
            self.daily_trade_count[date] = 0
        self.daily_trade_count[date] += 1
    
    def check_position_ratio(
        self,
        account: VirtualAccount,
        order_amount: Decimal
    ) -> RiskCheckResult:
        """检查持仓比例"""
        current_equity = account.equity
        position_value = sum(
            pos.quantity * pos.entry_price 
            for pos in account.get_all_positions()
        )
        
        # 计算新增后的持仓比例
        new_position_value = position_value + order_amount
        new_ratio = new_position_value / current_equity * 100
        
        if new_ratio > self.config.max_position_ratio:
            return RiskCheckResult(
                passed=False,
                reason=f"持仓比例将超过限制: {new_ratio:.2f}% > {self.config.max_position_ratio}%"
            )
        
        return RiskCheckResult(passed=True)
    
    def check_order_amount(self, amount: Decimal) -> RiskCheckResult:
        """检查委托金额"""
        if amount < self.config.min_order_amount:
            return RiskCheckResult(
                passed=False,
                reason=f"委托金额低于最小限制: {amount} < {self.config.min_order_amount}"
            )
        
        if amount > self.config.max_order_amount:
            return RiskCheckResult(
                passed=False,
                reason=f"委托金额超过最大限制: {amount} > {self.config.max_order_amount}"
            )
        
        return RiskCheckResult(passed=True)
    
    def check_daily_trades(self, date: str) -> RiskCheckResult:
        """检查每日交易次数"""
        count = self.daily_trade_count.get(date, 0)
        if count >= self.config.max_daily_trades:
            return RiskCheckResult(
                passed=False,
                reason=f"当日交易次数已达上限: {count} >= {self.config.max_daily_trades}"
            )
        
        return RiskCheckResult(passed=True)
    
    def check_stop_loss(
        self,
        position: Position,
        current_price: Decimal
    ) -> RiskCheckResult:
        """检查止损（未配置时由 AI 判断，不强制）"""
        if self.config.stop_loss_ratio is None:
            return RiskCheckResult(passed=True)
        pnl_percent = position.get_pnl_percent(current_price)
        if pnl_percent <= -self.config.stop_loss_ratio:
            result = RiskCheckResult(
                passed=False,
                reason=f"触发止损: 亏损 {pnl_percent:.2f}% <= -{self.config.stop_loss_ratio}%"
            )
            result.add_action(
                'close_position',
                symbol=position.symbol,
                side=position.side,
                reason='止损平仓'
            )
            return result
        return RiskCheckResult(passed=True)

    def check_take_profit(
        self,
        position: Position,
        current_price: Decimal
    ) -> RiskCheckResult:
        """检查止盈（未配置时由 AI 判断，不强制）"""
        if self.config.take_profit_ratio is None:
            return RiskCheckResult(passed=True)
        pnl_percent = position.get_pnl_percent(current_price)
        if pnl_percent >= self.config.take_profit_ratio:
            result = RiskCheckResult(
                passed=False,
                reason=f"触发止盈: 盈利 {pnl_percent:.2f}% >= {self.config.take_profit_ratio}%"
            )
            result.add_action(
                'close_position',
                symbol=position.symbol,
                side=position.side,
                reason='止盈平仓'
            )
            return result
        
        return RiskCheckResult(passed=True)
    
    def check_trade_plan_stop(
        self,
        position: Position,
        current_price: Decimal
    ) -> RiskCheckResult:
        """
        根据开仓时声明的 trade_plan 强制止损止盈。

        与 check_stop_loss/check_take_profit 不同：本方法读取 Position 上保存的
        LLM 声明 stop_loss_price / take_profit_price，按价格绝对值触发，确保 LLM
        自己声明的风险位被强制执行，避免亏损无限放大、盈利回吐。
        """
        plan = getattr(position, "trade_plan", None)
        if not isinstance(plan, dict):
            return RiskCheckResult(passed=True)

        stop_loss_raw = plan.get("stop_loss_price")
        take_profit_raw = plan.get("take_profit_price")
        if not stop_loss_raw and not take_profit_raw:
            return RiskCheckResult(passed=True)

        try:
            stop_loss = Decimal(str(stop_loss_raw)) if stop_loss_raw is not None else None
        except (ArithmeticError, ValueError):
            stop_loss = None
        try:
            take_profit = Decimal(str(take_profit_raw)) if take_profit_raw is not None else None
        except (ArithmeticError, ValueError):
            take_profit = None

        side = (position.side or "").lower()

        # 强制止损
        if stop_loss is not None and stop_loss > 0:
            if side == "long" and current_price <= stop_loss:
                result = RiskCheckResult(
                    passed=False,
                    reason=f"硬止损触发：价格 {current_price} <= 声明止损 {stop_loss}"
                )
                result.add_action(
                    "close_position",
                    symbol=position.symbol,
                    side=position.side,
                    reason="硬止损平仓（trade_plan）"
                )
                return result
            if side == "short" and current_price >= stop_loss:
                result = RiskCheckResult(
                    passed=False,
                    reason=f"硬止损触发：价格 {current_price} >= 声明止损 {stop_loss}"
                )
                result.add_action(
                    "close_position",
                    symbol=position.symbol,
                    side=position.side,
                    reason="硬止损平仓（trade_plan）"
                )
                return result

        # 强制止盈
        if take_profit is not None and take_profit > 0:
            if side == "long" and current_price >= take_profit:
                result = RiskCheckResult(
                    passed=False,
                    reason=f"硬止盈触发：价格 {current_price} >= 声明止盈 {take_profit}"
                )
                result.add_action(
                    "close_position",
                    symbol=position.symbol,
                    side=position.side,
                    reason="硬止盈平仓（trade_plan）"
                )
                return result
            if side == "short" and current_price <= take_profit:
                result = RiskCheckResult(
                    passed=False,
                    reason=f"硬止盈触发：价格 {current_price} <= 声明止盈 {take_profit}"
                )
                result.add_action(
                    "close_position",
                    symbol=position.symbol,
                    side=position.side,
                    reason="硬止盈平仓（trade_plan）"
                )
                return result

        return RiskCheckResult(passed=True)

    @staticmethod
    def _conservative_trigger_price(
        position: Position,
        bar: Any,
        trigger_price: Decimal,
        is_stop: bool,
    ) -> Decimal:
        """Gap 时按更差的开盘价成交；普通触发按声明价成交。"""
        bar_open = Decimal(str(bar.open))
        if not is_stop:
            return trigger_price
        if position.side == 'long' and bar_open < trigger_price:
            return bar_open
        if position.side == 'short' and bar_open > trigger_price:
            return bar_open
        return trigger_price

    def check_intrabar_exit(self, position: Position, bar: Any) -> RiskCheckResult:
        """
        使用执行 K 线 high/low 检查止盈止损。

        同一根 K 线同时触发止损和止盈时无法知道真实先后，统一采用保守的
        stop-first 规则，避免回测获得不可实现的乐观收益。
        """
        high = Decimal(str(bar.high))
        low = Decimal(str(bar.low))
        plan = position.trade_plan if isinstance(position.trade_plan, dict) else {}

        stop_price: Optional[Decimal] = None
        take_price: Optional[Decimal] = None
        try:
            if plan.get('stop_loss_price') is not None:
                stop_price = Decimal(str(plan['stop_loss_price']))
        except (ArithmeticError, ValueError):
            stop_price = None
        try:
            if plan.get('take_profit_price') is not None:
                take_price = Decimal(str(plan['take_profit_price']))
        except (ArithmeticError, ValueError):
            take_price = None

        if stop_price is None and self.config.stop_loss_ratio is not None:
            ratio = self.config.stop_loss_ratio / Decimal('100')
            stop_price = position.entry_price * (
                Decimal('1') - ratio if position.side == 'long' else Decimal('1') + ratio
            )
        if take_price is None and self.config.take_profit_ratio is not None:
            ratio = self.config.take_profit_ratio / Decimal('100')
            take_price = position.entry_price * (
                Decimal('1') + ratio if position.side == 'long' else Decimal('1') - ratio
            )

        stop_hit = bool(
            stop_price is not None
            and ((position.side == 'long' and low <= stop_price) or (position.side == 'short' and high >= stop_price))
        )
        take_hit = bool(
            take_price is not None
            and ((position.side == 'long' and high >= take_price) or (position.side == 'short' and low <= take_price))
        )

        if stop_hit:
            fill = self._conservative_trigger_price(position, bar, stop_price, is_stop=True)
            result = RiskCheckResult(False, 'K线内止损触发（同 bar 冲突按止损优先）')
            result.add_action(
                'close_position', symbol=position.symbol, side=position.side,
                reason='K线内止损平仓', trigger_price=fill, trigger_kind='stop_loss',
                same_bar_conflict=take_hit,
            )
            return result
        if take_hit:
            fill = self._conservative_trigger_price(position, bar, take_price, is_stop=False)
            result = RiskCheckResult(False, 'K线内止盈触发')
            result.add_action(
                'close_position', symbol=position.symbol, side=position.side,
                reason='K线内止盈平仓', trigger_price=fill, trigger_kind='take_profit',
                same_bar_conflict=False,
            )
            return result
        return RiskCheckResult(passed=True)

    def check_trailing_stop(
        self,
        position: Position,
        current_price: Decimal
    ) -> RiskCheckResult:
        """检查追踪止损"""
        if not self.config.trailing_stop_enabled:
            return RiskCheckResult(passed=True)
        
        # 计算从最高点的回撤
        if position.side == 'long':
            if position.highest_price > 0:
                drawdown = (position.highest_price - current_price) / position.highest_price * 100
                if drawdown >= self.config.trailing_stop_ratio:
                    result = RiskCheckResult(
                        passed=False,
                        reason=f"触发追踪止损: 从最高点回撤 {drawdown:.2f}% >= {self.config.trailing_stop_ratio}%"
                    )
                    result.add_action(
                        'close_position',
                        symbol=position.symbol,
                        side=position.side,
                        reason='追踪止损平仓'
                    )
                    return result
        else:  # short
            if position.lowest_price > 0:
                drawdown = (current_price - position.lowest_price) / position.lowest_price * 100
                if drawdown >= self.config.trailing_stop_ratio:
                    result = RiskCheckResult(
                        passed=False,
                        reason=f"触发追踪止损: 从最低点反弹 {drawdown:.2f}% >= {self.config.trailing_stop_ratio}%"
                    )
                    result.add_action(
                        'close_position',
                        symbol=position.symbol,
                        side=position.side,
                        reason='追踪止损平仓'
                    )
                    return result
        
        return RiskCheckResult(passed=True)
    
    def check_all_positions(
        self,
        account: VirtualAccount,
        prices: Dict[str, Decimal],
        bars: Optional[Dict[str, Any]] = None,
    ) -> List[RiskCheckResult]:
        """检查所有持仓的风控规则"""
        results = []
        
        for symbol, position in account.positions.items():
            if symbol not in prices:
                continue

            current_price = prices[symbol]

            if bars and symbol in bars:
                intrabar_result = self.check_intrabar_exit(position, bars[symbol])
                if not intrabar_result.passed:
                    results.append(intrabar_result)
                    continue

            # 优先级：trade_plan 硬止损/止盈 > 配置止损 > 配置止盈 > 追踪止损
            # trade_plan 来自开仓时 LLM 声明的 stop_loss_price/take_profit_price，
            # 必须先于其它兜底规则触发，确保 LLM 自己声明的风险位被强制执行。
            plan_stop_result = self.check_trade_plan_stop(position, current_price)
            if not plan_stop_result.passed:
                results.append(plan_stop_result)
                continue
            
            stop_loss_result = self.check_stop_loss(position, current_price)
            if not stop_loss_result.passed:
                results.append(stop_loss_result)
                continue
            
            take_profit_result = self.check_take_profit(position, current_price)
            if not take_profit_result.passed:
                results.append(take_profit_result)
                continue
            
            trailing_stop_result = self.check_trailing_stop(position, current_price)
            if not trailing_stop_result.passed:
                results.append(trailing_stop_result)
        
        return results
    
    def check_new_order(
        self,
        account: VirtualAccount,
        order_amount: Decimal,
        current_date: str
    ) -> RiskCheckResult:
        """检查新订单是否符合风控规则"""
        # 检查交易次数
        daily_check = self.check_daily_trades(current_date)
        if not daily_check.passed:
            return daily_check
        
        # 检查委托金额
        amount_check = self.check_order_amount(order_amount)
        if not amount_check.passed:
            return amount_check
        
        # 检查持仓比例
        position_check = self.check_position_ratio(account, order_amount)
        if not position_check.passed:
            return position_check
        
        return RiskCheckResult(passed=True)
    
    @classmethod
    def from_strategy_config(cls, config: Dict) -> 'RiskManager':
        """创建执行期风控；Trader 不继承交易风格产生的策略型退出。"""
        mode = resolve_decision_mode(config)
        style = str(config.get('tradingStyle') or 'balanced').strip().lower()
        style_position_ratios = {
            'conservative': Decimal('20'),
            'balanced': Decimal('30'),
            'aggressive': Decimal('50'),
        }
        hard_policy = HardRiskPolicy.from_strategy_config(config)
        # 保留 rule/旧配置的展示与兼容值；Trader 执行不会再用该字段二次否决，
        # 其真实总敞口上限只由 HardRiskPolicy 决定。
        max_position_ratio_raw = config.get('maxPositionRatio')
        max_position_ratio = (
            Decimal(str(max_position_ratio_raw))
            if max_position_ratio_raw is not None
            else style_position_ratios.get(style, Decimal('30'))
        )
        risk_config = RiskConfig(
            max_position_ratio=max_position_ratio,
            take_profit_ratio=None,  # 由 AI 判断
            stop_loss_ratio=None,    # 由 AI 判断
            # 固定追踪止盈/止损属于交易判断，只允许 rule 模式启用。
            trailing_stop_enabled=(
                bool(config.get('trailingStopEnabled', False)) if mode == 'rule' else False
            ),
            trailing_stop_ratio=Decimal(str(config.get('trailingStopRatio', 2))),
            max_daily_trades=config.get('maxDailyTrades', 50),
            min_order_amount=(
                hard_policy.min_order_notional
                if mode == 'trader'
                else Decimal(str(config.get('minOrderAmount', 10)))
            ),
            max_order_amount=(
                hard_policy.max_order_notional
                if mode == 'trader'
                else Decimal(str(config.get('maxOrderAmount', 1000)))
            ),
            price_deviation_upper=Decimal(str(config.get('priceDeviationUpper', 1))),
            price_deviation_lower=Decimal(str(config.get('priceDeviationLower', 1)))
        )
        return cls(risk_config)
