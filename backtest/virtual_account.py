#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
虚拟账户管理
用于回测和模拟盘的资金和持仓管理
"""
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: str  # 'long' or 'short'
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    margin_used: Decimal = Decimal('0')  # 占用保证金（杠杆时 = 名义价值/杠杆）
    leverage: Decimal = Decimal('1')
    unrealized_pnl: Decimal = Decimal('0')
    highest_price: Decimal = Decimal('0')
    lowest_price: Decimal = Decimal('0')
    trade_plan: Optional[Dict[str, Any]] = None  # 开仓时确定的目标位/止损位及交易逻辑
    # 一次从建仓到完全平仓的稳定标识。回撤加仓单使用该标识绑定
    # 父仓，避免父仓止盈/止损后子单变成无主挂单。
    lifecycle_id: Optional[str] = None
    entry_intent_id: Optional[str] = None
    open_fee_remaining: Decimal = Decimal('0')
    open_slippage_remaining: Decimal = Decimal('0')
    funding_accrued: Decimal = Decimal('0')
    realized_pnl_accumulated: Decimal = Decimal('0')
    round_trip_cost_accumulated: Decimal = Decimal('0')
    
    def update_unrealized_pnl(self, current_price: Decimal):
        """更新未实现盈亏"""
        if self.side == 'long':
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity
        
        # 更新最高/最低价（用于追踪止损）
        if current_price > self.highest_price:
            self.highest_price = current_price
        if self.lowest_price == 0 or current_price < self.lowest_price:
            self.lowest_price = current_price
    
    def get_pnl_percent(self, current_price: Decimal) -> Decimal:
        """获取盈亏百分比"""
        if self.entry_price == 0:
            return Decimal('0')
        
        if self.side == 'long':
            return ((current_price - self.entry_price) / self.entry_price * 100).quantize(Decimal('0.0001'))
        else:
            return ((self.entry_price - current_price) / self.entry_price * 100).quantize(Decimal('0.0001'))


@dataclass
class Order:
    """委托订单"""
    id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market' or 'limit'
    quantity: Decimal
    price: Optional[Decimal] = None
    status: str = 'pending'  # pending, filled, partially_filled, cancelled
    filled_quantity: Decimal = Decimal('0')
    filled_price: Decimal = Decimal('0')
    fee: Decimal = Decimal('0')
    created_at: datetime = None
    filled_at: datetime = None


@dataclass
class Trade:
    """成交记录"""
    id: str
    order_id: str
    symbol: str
    side: str
    trade_type: str  # 'open' or 'close'
    price: Decimal
    quantity: Decimal
    amount: Decimal
    fee: Decimal
    pnl: Decimal = Decimal('0')
    pnl_percent: Decimal = Decimal('0')
    balance: Decimal = Decimal('0')
    timestamp: datetime = None
    reasoning: Optional[str] = None
    signals: Optional[List[str]] = None
    chain_of_thought: Optional[List[Dict]] = None
    # 细粒度最终动作：open/add/reduce/close + long/short。
    # 旧数据可由 side + trade_type 推断，但无法区分 add/reduce。
    action: Optional[str] = None
    leverage: Decimal = Decimal('1')
    liquidity: str = 'taker'
    slippage_cost: Decimal = Decimal('0')
    round_trip_cost: Decimal = Decimal('0')
    round_trip_complete: bool = False
    round_trip_pnl: Decimal = Decimal('0')


class VirtualAccount:
    """虚拟账户"""
    
    def __init__(
        self,
        initial_capital: Decimal,
        maker_fee: Decimal = Decimal('0.001'),
        taker_fee: Decimal = Decimal('0.001'),
        slippage: Decimal = Decimal('0.0005'),
        leverage: Decimal = Decimal('1')
    ):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.maker_fee = maker_fee / 100  # 转换为小数
        self.taker_fee = taker_fee / 100
        self.slippage = slippage / 100
        self.leverage = max(Decimal('1'), leverage)  # 杠杆倍数，1=全仓无杠杆
        
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.trades: List[Trade] = []
        
        # 统计数据
        self.total_trades = 0
        self.win_trades = 0
        self.lose_trades = 0
        self.total_pnl = Decimal('0')
        self.total_fees = Decimal('0')
        self.total_slippage_cost = Decimal('0')
        self.total_funding = Decimal('0')
        self.max_drawdown = Decimal('0')
        self.peak_equity = initial_capital
        
        # 权益历史（用于绘制曲线）
        self.equity_history: List[Dict] = []
    
    @property
    def equity(self) -> Decimal:
        """账户权益（可用余额 + 占用保证金 + 未实现盈亏）"""
        total_margin = sum(pos.margin_used for pos in self.positions.values())
        unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())
        return self.balance + total_margin + unrealized_pnl
    
    @property
    def available_balance(self) -> Decimal:
        """可用余额"""
        return self.balance
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取指定交易对的持仓"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """获取所有持仓"""
        return list(self.positions.values())
    
    def update_positions_pnl(self, prices: Dict[str, Decimal]):
        """更新所有持仓的未实现盈亏"""
        for symbol, position in self.positions.items():
            if symbol in prices:
                position.update_unrealized_pnl(prices[symbol])
        
        # 更新最大回撤
        current_equity = self.equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        drawdown = (self.peak_equity - current_equity) / self.peak_equity * 100
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
    
    def record_equity(self, timestamp: datetime, benchmark: Optional[Decimal] = None):
        """记录权益快照"""
        current_equity = self.equity
        drawdown = Decimal('0')
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity * 100

        total_upl = sum(pos.unrealized_pnl for pos in self.positions.values())
        total_margin = sum(pos.margin_used for pos in self.positions.values())
        if total_margin > 0:
            upl_rate = (total_upl / total_margin * Decimal('100')).quantize(Decimal('0.01'))
        else:
            upl_rate = Decimal('0')
        
        self.equity_history.append({
            'timestamp': timestamp,
            'equity': current_equity,
            'drawdown': drawdown,
            'benchmark': benchmark,
            'unrealized_pnl': total_upl,
            'unrealized_pnl_rate': upl_rate,
        })
    
    def execute_market_order(
        self,
        symbol: str,
        side: str,  # 'buy' or 'sell'
        quantity: Decimal,
        current_price: Decimal,
        timestamp: datetime,
        trade_type: str = 'open',  # 'open' or 'close'
        reasoning: Optional[str] = None,
        signals: Optional[List[str]] = None,
        chain_of_thought: Optional[List[Dict]] = None,
        liquidity: str = 'taker',
        slippage_rate: Optional[Decimal] = None,
        leverage: Optional[Decimal] = None,
    ) -> Optional[Trade]:
        """
        执行市价单
        
        Args:
            symbol: 交易对
            side: 买卖方向 ('buy' or 'sell')
            quantity: 数量
            current_price: 当前市场价格
            timestamp: 时间戳
            trade_type: 交易类型 ('open' or 'close')
            reasoning: LLM 分析理由
            signals: 触发信号
            chain_of_thought: 思维链
            
        Returns:
            Trade: 成交记录，失败返回 None
        """
        liquidity = 'maker' if str(liquidity).lower() == 'maker' else 'taker'
        applied_slippage = self.slippage if slippage_rate is None else max(Decimal('0'), slippage_rate)
        position_before = self.positions.get(symbol)
        execution_leverage = (
            max(Decimal('1'), Decimal(str(leverage or self.leverage)))
            if trade_type == 'open'
            else max(
                Decimal('1'),
                Decimal(str(getattr(position_before, 'leverage', self.leverage))),
            )
        )

        # 计算滑点后的执行价格
        if side == 'buy':
            exec_price = current_price * (1 + applied_slippage)
        else:
            exec_price = current_price * (1 - applied_slippage)
        
        exec_price = exec_price.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        # 计算成交金额和手续费（手续费按名义价值计算）
        amount = exec_price * quantity
        fee_rate = self.maker_fee if liquidity == 'maker' else self.taker_fee
        fee = amount * fee_rate
        slippage_cost = abs(exec_price - current_price) * quantity
        margin_used = (amount / execution_leverage).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        # 检查余额
        if trade_type == 'open':
            if self.balance < margin_used + fee:
                return None
        else:
            position = self.positions.get(symbol)
            if not position:
                return None
        
        # 计算盈亏（平仓时，pnl 保持为扣除本次平仓手续费后的净盈亏）
        pnl = Decimal('0')
        pnl_percent = Decimal('0')
        release_margin = Decimal('0')
        open_fee_allocated = Decimal('0')
        open_slippage_allocated = Decimal('0')
        funding_allocated = Decimal('0')
        close_round_trip_cost = Decimal('0')
        round_trip_complete = False
        round_trip_pnl = Decimal('0')
        
        if trade_type == 'close':
            position = self.positions.get(symbol)
            if position and position.quantity > 0:
                quantity = min(quantity, position.quantity)
                amount = exec_price * quantity
                fee = amount * fee_rate
                slippage_cost = abs(exec_price - current_price) * quantity
                fraction = quantity / position.quantity
                open_fee_allocated = position.open_fee_remaining * fraction
                open_slippage_allocated = position.open_slippage_remaining * fraction
                funding_allocated = position.funding_accrued * fraction
                if position.side == 'long':
                    cash_pnl = (exec_price - position.entry_price) * quantity - fee
                else:
                    cash_pnl = (position.entry_price - exec_price) * quantity - fee
                pnl = cash_pnl - open_fee_allocated - funding_allocated
                entry_notional = position.entry_price * quantity
                pnl_percent = (
                    (pnl / entry_notional * 100).quantize(Decimal('0.0001'))
                    if entry_notional > 0 else Decimal('0')
                )
                release_margin = (position.margin_used * quantity / position.quantity).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
                close_round_trip_cost = (
                    fee + open_fee_allocated + slippage_cost
                    + open_slippage_allocated + funding_allocated
                )
                round_trip_complete = quantity >= position.quantity
                round_trip_pnl = position.realized_pnl_accumulated + pnl
                self.total_pnl += pnl
                if round_trip_complete:
                    if round_trip_pnl > 0:
                        self.win_trades += 1
                    else:
                        self.lose_trades += 1
                else:
                    position.realized_pnl_accumulated = round_trip_pnl
                    position.round_trip_cost_accumulated += close_round_trip_cost
        
        # 更新余额：开仓扣保证金+手续费，平仓返还保证金+净盈亏
        if trade_type == 'open':
            self.balance -= (margin_used + fee)
        else:
            # 开仓手续费和资金费率已在发生时从余额扣除，现金只落账价格盈亏与平仓费。
            self.balance += (release_margin + cash_pnl)

        self.total_fees += fee
        self.total_slippage_cost += slippage_cost
        
        # 更新持仓
        self._update_position(
            symbol, side, quantity, exec_price, timestamp, trade_type,
            margin_used=margin_used, release_margin=release_margin,
            open_fee=fee if trade_type == 'open' else Decimal('0'),
            open_slippage=slippage_cost if trade_type == 'open' else Decimal('0'),
            open_fee_allocated=open_fee_allocated,
            open_slippage_allocated=open_slippage_allocated,
            funding_allocated=funding_allocated,
            leverage=execution_leverage,
        )
        
        # 创建成交记录（全局主键，必须唯一，不可仅用模拟时间戳）
        if trade_type == 'open':
            direction = 'long' if side == 'buy' else 'short'
            final_action = f"{'add' if position_before else 'open'}_{direction}"
        else:
            direction = position_before.side if position_before else ('long' if side == 'sell' else 'short')
            final_action = f"{'close' if round_trip_complete else 'reduce'}_{direction}"
        trade = Trade(
            id=str(uuid.uuid4()),
            order_id="",
            symbol=symbol,
            side=side,
            trade_type=trade_type,
            price=exec_price,
            quantity=quantity,
            amount=amount,
            fee=fee,
            pnl=pnl,
            pnl_percent=pnl_percent,
            balance=self.balance,
            timestamp=timestamp,
            reasoning=reasoning,
            signals=signals,
            chain_of_thought=chain_of_thought,
            action=final_action,
            leverage=execution_leverage,
            liquidity=liquidity,
            slippage_cost=slippage_cost,
            round_trip_cost=(
                close_round_trip_cost
                + (position.round_trip_cost_accumulated if round_trip_complete else Decimal('0'))
            ) if trade_type == 'close' else (fee + slippage_cost),
            round_trip_complete=round_trip_complete,
            round_trip_pnl=round_trip_pnl if round_trip_complete else Decimal('0'),
        )
        
        self.trades.append(trade)
        # 统计口径是一笔完整的开仓—平仓，而不是成交腿数。
        if trade_type == 'close' and round_trip_complete:
            self.total_trades += 1
        
        return trade
    
    def _update_position(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        timestamp: datetime,
        trade_type: str,
        margin_used: Decimal = Decimal('0'),
        release_margin: Decimal = Decimal('0'),
        open_fee: Decimal = Decimal('0'),
        open_slippage: Decimal = Decimal('0'),
        open_fee_allocated: Decimal = Decimal('0'),
        open_slippage_allocated: Decimal = Decimal('0'),
        funding_allocated: Decimal = Decimal('0'),
        leverage: Decimal = Decimal('1'),
    ):
        """更新持仓"""
        if trade_type == 'open':
            position_side = 'long' if side == 'buy' else 'short'
            if symbol in self.positions:
                pos = self.positions[symbol]
                total_quantity = pos.quantity + quantity
                avg_price = (pos.entry_price * pos.quantity + price * quantity) / total_quantity
                pos.quantity = total_quantity
                pos.entry_price = avg_price
                pos.margin_used += margin_used
                if pos.margin_used > 0:
                    pos.leverage = (
                        pos.entry_price * pos.quantity / pos.margin_used
                    ).quantize(Decimal('0.0001'))
                pos.open_fee_remaining += open_fee
                pos.open_slippage_remaining += open_slippage
            else:
                self.positions[symbol] = Position(
                    symbol=symbol,
                    side=position_side,
                    quantity=quantity,
                    entry_price=price,
                    entry_time=timestamp,
                    margin_used=margin_used,
                    leverage=leverage,
                    highest_price=price,
                    lowest_price=price,
                    open_fee_remaining=open_fee,
                    open_slippage_remaining=open_slippage,
                )
        else:
            if symbol in self.positions:
                pos = self.positions[symbol]
                pos.quantity -= quantity
                pos.margin_used -= release_margin
                pos.open_fee_remaining -= open_fee_allocated
                pos.open_slippage_remaining -= open_slippage_allocated
                pos.funding_accrued -= funding_allocated
                if pos.quantity <= 0:
                    del self.positions[symbol]
    
    def open_long(
        self,
        symbol: str,
        quantity: Decimal,
        current_price: Decimal,
        timestamp: datetime,
        reasoning: Optional[str] = None,
        signals: Optional[List[str]] = None,
        chain_of_thought: Optional[List[Dict]] = None,
        liquidity: str = 'taker',
        slippage_rate: Optional[Decimal] = None,
        leverage: Optional[Decimal] = None,
    ) -> Optional[Trade]:
        """开多仓"""
        return self.execute_market_order(
            symbol=symbol,
            side='buy',
            quantity=quantity,
            current_price=current_price,
            timestamp=timestamp,
            trade_type='open',
            reasoning=reasoning,
            signals=signals,
            chain_of_thought=chain_of_thought,
            liquidity=liquidity,
            slippage_rate=slippage_rate,
            leverage=leverage,
        )
    
    def open_short(
        self,
        symbol: str,
        quantity: Decimal,
        current_price: Decimal,
        timestamp: datetime,
        reasoning: Optional[str] = None,
        signals: Optional[List[str]] = None,
        chain_of_thought: Optional[List[Dict]] = None,
        liquidity: str = 'taker',
        slippage_rate: Optional[Decimal] = None,
        leverage: Optional[Decimal] = None,
    ) -> Optional[Trade]:
        """开空仓"""
        return self.execute_market_order(
            symbol=symbol,
            side='sell',
            quantity=quantity,
            current_price=current_price,
            timestamp=timestamp,
            trade_type='open',
            reasoning=reasoning,
            signals=signals,
            chain_of_thought=chain_of_thought,
            liquidity=liquidity,
            slippage_rate=slippage_rate,
            leverage=leverage,
        )
    
    def close_long(
        self,
        symbol: str,
        quantity: Optional[Decimal],
        current_price: Decimal,
        timestamp: datetime,
        reasoning: Optional[str] = None,
        signals: Optional[List[str]] = None,
        chain_of_thought: Optional[List[Dict]] = None,
        liquidity: str = 'taker',
        slippage_rate: Optional[Decimal] = None,
    ) -> Optional[Trade]:
        """平多仓"""
        pos = self.positions.get(symbol)
        if not pos or pos.side != 'long':
            return None
        
        close_qty = quantity if quantity else pos.quantity
        return self.execute_market_order(
            symbol=symbol,
            side='sell',
            quantity=close_qty,
            current_price=current_price,
            timestamp=timestamp,
            trade_type='close',
            reasoning=reasoning,
            signals=signals,
            chain_of_thought=chain_of_thought,
            liquidity=liquidity,
            slippage_rate=slippage_rate,
        )
    
    def close_short(
        self,
        symbol: str,
        quantity: Optional[Decimal],
        current_price: Decimal,
        timestamp: datetime,
        reasoning: Optional[str] = None,
        signals: Optional[List[str]] = None,
        chain_of_thought: Optional[List[Dict]] = None,
        liquidity: str = 'taker',
        slippage_rate: Optional[Decimal] = None,
    ) -> Optional[Trade]:
        """平空仓"""
        pos = self.positions.get(symbol)
        if not pos or pos.side != 'short':
            return None
        
        close_qty = quantity if quantity else pos.quantity
        return self.execute_market_order(
            symbol=symbol,
            side='buy',
            quantity=close_qty,
            current_price=current_price,
            timestamp=timestamp,
            trade_type='close',
            reasoning=reasoning,
            signals=signals,
            chain_of_thought=chain_of_thought,
            liquidity=liquidity,
            slippage_rate=slippage_rate,
        )

    def apply_funding(self, prices: Dict[str, Decimal], rate: Decimal) -> Decimal:
        """结算一次资金费率；正费率时多头支付、空头收取。"""
        total = Decimal('0')
        if rate == 0:
            return total
        for symbol, position in self.positions.items():
            price = prices.get(symbol)
            if price is None:
                continue
            payment = position.quantity * price * rate
            signed_payment = payment if position.side == 'long' else -payment
            self.balance -= signed_payment
            position.funding_accrued += signed_payment
            total += signed_payment
        self.total_funding += total
        return total
    
    def get_statistics(self) -> Dict:
        """获取账户统计数据"""
        total_return = (self.equity - self.initial_capital) / self.initial_capital * 100
        win_rate = (self.win_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        # 计算平均盈利/亏损，以及标准盈利因子（毛利 / 毛损）
        completed_pnls = [
            t.round_trip_pnl for t in self.trades
            if t.trade_type == 'close' and t.round_trip_complete
        ]
        profits = [pnl for pnl in completed_pnls if pnl > 0]
        losses = [pnl for pnl in completed_pnls if pnl < 0]
        
        avg_profit = sum(profits) / len(profits) if profits else Decimal('0')
        avg_loss = abs(sum(losses) / len(losses)) if losses else Decimal('0')
        gross_profit = sum(profits) if profits else Decimal('0')
        gross_loss = abs(sum(losses)) if losses else Decimal('0')
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else Decimal('0')
        
        return {
            'initial_capital': float(self.initial_capital),
            'final_capital': float(self.equity),
            'total_return': float(total_return),
            'total_pnl': float(self.total_pnl),
            'max_drawdown': float(self.max_drawdown),
            'total_trades': self.total_trades,
            'win_trades': self.win_trades,
            'lose_trades': self.lose_trades,
            'win_rate': float(win_rate),
            'avg_profit': float(avg_profit),
            'avg_loss': float(avg_loss),
            'profit_factor': float(profit_factor),
            'total_fees': float(self.total_fees),
            'total_slippage_cost': float(self.total_slippage_cost),
            'total_funding': float(self.total_funding),
        }
