# -*- coding: utf-8 -*-
# @ModuleName: trading_service.py
# @Author: jason
# @Email: jasonforjob@qq.com
# @Time: 2025/3/7
# @Desc: OKX永续合约交易服务类

import asyncio
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN

from lib.okx.okx_api import ApiService


class OkxTradingService:
    """OKX永续合约交易服务类"""
    
    def __init__(self, api_key: str, secret_key: str, passphrase: str, is_sandbox: bool = True):
        """初始化交易服务
        
        Args:
            api_key: OKX API密钥
            secret_key: OKX Secret密钥
            passphrase: OKX Passphrase
            is_sandbox: 是否使用沙盒环境，默认True
        """
        self.api = ApiService(api_key, secret_key, passphrase, is_sandbox)
    
    async def initialize_trading(self, symbol: str = "BTC-USDT-SWAP", 
                               leverage: str = "10", mgn_mode: str = "cross"):
        """初始化交易设置
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
            leverage: 杠杆倍数
            mgn_mode: 保证金模式，cross=全仓，isolated=逐仓
        """
        try:
            # 设置杠杆
            await self.api.set_leverage(
                inst_id=symbol,
                lever=leverage,
                mgn_mode=mgn_mode
            )
            print(f"交易设置初始化成功: {symbol}, 杠杆: {leverage}x, 模式: {mgn_mode}")
        except Exception as e:
            print(f"交易设置初始化失败: {e}")
            raise
    
    async def get_market_price(self, symbol: str) -> float:
        """获取当前市场价格
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
        """
        try:
            ticker = await self.api.get_ticker(symbol)
            return float(ticker.get('last', 0))
        except Exception as e:
            print(f"获取市场价格失败: {e}")
            return 0.0
    
    async def calculate_position_size(self, symbol: str, usd_amount: float, price: float = None) -> str:
        """计算持仓数量
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
            usd_amount: 美元金额
            price: 价格，如果为None则使用当前市价
            
        Returns:
            str: 计算后的持仓数量
        """
        if price is None:
            price = await self.get_market_price(symbol)
        
        if price <= 0:
            raise ValueError("价格无效")
        
        # 计算持仓数量（张数）
        # 对于永续合约，1张 = 0.01 BTC
        btc_amount = usd_amount / price
        position_size = btc_amount / 0.01  # 转换为张数
        
        # 保留2位小数
        return str(Decimal(str(position_size)).quantize(Decimal('0.01'), rounding=ROUND_DOWN))
    
    async def open_long_position(self, symbol: str, usd_amount: float, price: float = None, 
                                order_type: str = "market", mgn_mode: str = "cross") -> Dict:
        """开多仓
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
            usd_amount: 美元金额
            price: 价格，市价单时忽略
            order_type: 订单类型，market=市价单，limit=限价单
            mgn_mode: 保证金模式，cross=全仓，isolated=逐仓
            
        Returns:
            Dict: 下单结果
        """
        try:
            # 计算持仓数量
            sz = await self.calculate_position_size(symbol, usd_amount, price)
            
            order_data = {
                "instId": symbol,
                "tdMode": mgn_mode,
                "side": "buy",
                "ordType": order_type,
                "sz": sz,
                "posSide": "long"
            }
            
            if order_type == "limit" and price:
                order_data["px"] = str(price)
            
            result = await self.api.place_order(**order_data)
            print(f"开多仓成功: 数量={sz}, 价格={price if order_type == 'limit' else '市价'}")
            return result
            
        except Exception as e:
            print(f"开多仓失败: {e}")
            raise
    
    async def open_short_position(self, symbol: str, usd_amount: float, price: float = None, 
                                 order_type: str = "market", mgn_mode: str = "cross") -> Dict:
        """开空仓
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
            usd_amount: 美元金额
            price: 价格，市价单时忽略
            order_type: 订单类型，market=市价单，limit=限价单
            mgn_mode: 保证金模式，cross=全仓，isolated=逐仓
            
        Returns:
            Dict: 下单结果
        """
        try:
            # 计算持仓数量
            sz = await self.calculate_position_size(symbol, usd_amount, price)
            
            order_data = {
                "instId": symbol,
                "tdMode": mgn_mode,
                "side": "sell",
                "ordType": order_type,
                "sz": sz,
                "posSide": "short"
            }
            
            if order_type == "limit" and price:
                order_data["px"] = str(price)
            
            result = await self.api.place_order(**order_data)
            print(f"开空仓成功: 数量={sz}, 价格={price if order_type == 'limit' else '市价'}")
            return result
            
        except Exception as e:
            print(f"开空仓失败: {e}")
            raise
    
    async def close_position(self, symbol: str, pos_side: str, price: float = None,
                           order_type: str = "market", mgn_mode: str = "cross",
                           quantity: float = None) -> Dict:
        """平仓
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
            pos_side: 持仓方向，long=多头，short=空头
            price: 价格，市价单时忽略
            order_type: 订单类型，market=市价单，limit=限价单
            mgn_mode: 保证金模式，cross=全仓，isolated=逐仓
            quantity: 需要平掉的张数；为空时全平，传入时最多不超过当前持仓
            
        Returns:
            Dict: 下单结果
        """
        try:
            # 获取当前持仓
            positions = await self.api.get_account_positions(
                inst_type="SWAP",
                inst_id=symbol
            )
            
            # 找到对应方向的持仓
            target_position = None
            for pos in positions:
                if pos.get('posSide') == pos_side and float(pos.get('pos', 0)) > 0:
                    target_position = pos
                    break
            
            if not target_position:
                raise ValueError(f"未找到{pos_side}方向持仓")
            
            # 平仓数量。减仓必须显式传张数；全平保持原有 quantity=None 语义。
            available = Decimal(str(target_position.get('pos') or 0))
            requested = Decimal(str(quantity)) if quantity is not None else available
            if requested <= 0:
                raise ValueError("平仓数量必须大于0")
            sz_decimal = min(requested, available)
            sz = format(sz_decimal.normalize(), 'f')
            
            # 确定平仓方向
            side = "sell" if pos_side == "long" else "buy"
            
            order_data = {
                "instId": symbol,
                "tdMode": mgn_mode,
                "side": side,
                "ordType": order_type,
                "sz": sz,
                "posSide": pos_side,
                "reduceOnly": True  # 只减仓
            }
            
            if order_type == "limit" and price:
                order_data["px"] = str(price)
            
            result = await self.api.place_order(**order_data)
            print(f"平仓成功: 方向={pos_side}, 数量={sz}, 价格={price if order_type == 'limit' else '市价'}")
            return result
            
        except Exception as e:
            print(f"平仓失败: {e}")
            raise
    
    async def set_take_profit_stop_loss(self, symbol: str, pos_side: str, tp_price: float, 
                                      sl_price: float, mgn_mode: str = "cross") -> Dict:
        """设置止盈止损
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
            pos_side: 持仓方向，long=多头，short=空头
            tp_price: 止盈价格
            sl_price: 止损价格
            mgn_mode: 保证金模式，cross=全仓，isolated=逐仓
            
        Returns:
            Dict: 下单结果
        """
        try:
            # 获取当前持仓
            positions = await self.api.get_account_positions(
                inst_type="SWAP",
                inst_id=symbol
            )
            
            # 找到对应方向的持仓
            target_position = None
            for pos in positions:
                if pos.get('posSide') == pos_side and float(pos.get('pos', 0)) > 0:
                    target_position = pos
                    break
            
            if not target_position:
                raise ValueError(f"未找到{pos_side}方向持仓")
            
            # 平仓数量
            sz = target_position.get('pos')
            
            # 确定平仓方向
            side = "sell" if pos_side == "long" else "buy"
            
            result = await self.api.place_algo_order(
                inst_id=symbol,
                td_mode=mgn_mode,
                side=side,
                ord_type="conditional",
                sz=sz,
                pos_side=pos_side,
                reduce_only=True,
                tp_trigger_px=str(tp_price),
                tp_trigger_px_type="last",
                tp_ord_px=str(tp_price),
                sl_trigger_px=str(sl_price),
                sl_trigger_px_type="last",
                sl_ord_px=str(sl_price)
            )
            
            print(f"止盈止损设置成功: 方向={pos_side}, 止盈={tp_price}, 止损={sl_price}")
            return result
            
        except Exception as e:
            print(f"设置止盈止损失败: {e}")
            raise
    
    async def get_position_info(self, symbol: str) -> List[Dict]:
        """获取持仓信息
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
        """
        try:
            positions = await self.api.get_account_positions(
                inst_type="SWAP",
                inst_id=symbol
            )
            
            active_positions = []
            for pos in positions:
                if float(pos.get('pos', 0)) > 0:
                    active_positions.append({
                        'instId': pos.get('instId'),
                        'posSide': pos.get('posSide'),
                        'pos': pos.get('pos'),
                        'avgPx': pos.get('avgPx'),
                        'upl': pos.get('upl'),
                        'uplRatio': pos.get('uplRatio'),
                        'lever': pos.get('lever'),
                        'liqPx': pos.get('liqPx'),
                        'margin': pos.get('margin'),
                        'mgnRatio': pos.get('mgnRatio')
                    })
            
            return active_positions
            
        except Exception as e:
            print(f"获取持仓信息失败: {e}")
            return []
    
    async def get_pending_orders(self, symbol: str) -> List[Dict]:
        """获取未成交订单
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
        """
        try:
            orders = await self.api.get_orders_pending(
                inst_type="SWAP",
                inst_id=symbol
            )
            return orders
        except Exception as e:
            print(f"获取未成交订单失败: {e}")
            return []
    
    async def cancel_all_orders(self, symbol: str) -> List[Dict]:
        """撤销所有未成交订单
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"
        """
        try:
            pending_orders = await self.get_pending_orders(symbol)
            
            if not pending_orders:
                print("没有未成交订单")
                return []
            
            # 构建批量撤单数据
            cancel_orders = []
            for order in pending_orders:
                cancel_orders.append({
                    "instId": symbol,
                    "ordId": order.get('ordId')
                })
            
            result = await self.api.cancel_multiple_orders(cancel_orders)
            print(f"批量撤销订单成功: 撤销了{len(cancel_orders)}个订单")
            return result
            
        except Exception as e:
            print(f"批量撤销订单失败: {e}")
            raise
    
    async def get_account_summary(self, symbol: str = None) -> Dict:
        """获取账户摘要信息
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"，如果为None则获取所有持仓
        """
        try:
            # 获取账户余额
            balance = await self.api.get_account_balance()
            
            # 获取持仓信息
            if symbol:
                positions = await self.get_position_info(symbol)
            else:
                # 获取所有永续合约持仓
                all_positions = await self.api.get_account_positions(inst_type="SWAP")
                positions = []
                for pos in all_positions:
                    if float(pos.get('pos', 0)) > 0:
                        positions.append({
                            'instId': pos.get('instId'),
                            'posSide': pos.get('posSide'),
                            'pos': pos.get('pos'),
                            'avgPx': pos.get('avgPx'),
                            'upl': pos.get('upl'),
                            'uplRatio': pos.get('uplRatio'),
                            'lever': pos.get('lever'),
                            'liqPx': pos.get('liqPx'),
                            'margin': pos.get('margin'),
                            'mgnRatio': pos.get('mgnRatio')
                        })
            
            # 获取未成交订单
            if symbol:
                pending_orders = await self.get_pending_orders(symbol)
            else:
                pending_orders = await self.api.get_orders_pending(inst_type="SWAP")
            
            # 计算总权益
            total_equity = 0
            for item in balance:
                eq_usd = float(item.get('eqUsd', 0))
                total_equity += eq_usd
            
            # 计算未实现盈亏
            total_upl = 0
            for pos in positions:
                upl = float(pos.get('upl', 0))
                total_upl += upl
            
            return {
                'total_equity': total_equity,
                'total_upl': total_upl,
                'balance': balance,
                'positions': positions,
                'pending_orders_count': len(pending_orders)
            }
            
        except Exception as e:
            print(f"获取账户摘要失败: {e}")
            return {}
    
    async def risk_management_check(self, symbol: str = None) -> Dict:
        """风险检查
        
        Args:
            symbol: 交易对，如 "BTC-USDT-SWAP"，如果为None则检查所有持仓
        """
        try:
            if symbol:
                positions = await self.get_position_info(symbol)
            else:
                # 获取所有永续合约持仓
                all_positions = await self.api.get_account_positions(inst_type="SWAP")
                positions = []
                for pos in all_positions:
                    if float(pos.get('pos', 0)) > 0:
                        positions.append({
                            'instId': pos.get('instId'),
                            'posSide': pos.get('posSide'),
                            'pos': pos.get('pos'),
                            'avgPx': pos.get('avgPx'),
                            'upl': pos.get('upl'),
                            'uplRatio': pos.get('uplRatio'),
                            'lever': pos.get('lever'),
                            'liqPx': pos.get('liqPx'),
                            'margin': pos.get('margin'),
                            'mgnRatio': pos.get('mgnRatio')
                        })
            
            balance = await self.api.get_account_balance()
            
            # 计算总权益
            total_equity = sum(float(item.get('eqUsd', 0)) for item in balance)
            
            # 计算总未实现盈亏
            total_upl = sum(float(pos.get('upl', 0)) for pos in positions)
            
            # 计算风险指标
            risk_ratio = abs(total_upl) / total_equity if total_equity > 0 else 0
            
            # 检查强平风险
            liquidation_risk = []
            for pos in positions:
                liq_px = float(pos.get('liqPx', 0))
                current_price = await self.get_market_price(pos.get('instId', symbol))
                
                if liq_px > 0:
                    if pos.get('posSide') == 'long' and current_price <= liq_px * 1.1:
                        liquidation_risk.append({
                            'instId': pos.get('instId'),
                            'posSide': pos.get('posSide'),
                            'liqPx': liq_px,
                            'currentPx': current_price,
                            'risk': 'HIGH'
                        })
                    elif pos.get('posSide') == 'short' and current_price >= liq_px * 0.9:
                        liquidation_risk.append({
                            'instId': pos.get('instId'),
                            'posSide': pos.get('posSide'),
                            'liqPx': liq_px,
                            'currentPx': current_price,
                            'risk': 'HIGH'
                        })
            
            return {
                'total_equity': total_equity,
                'total_upl': total_upl,
                'risk_ratio': risk_ratio,
                'liquidation_risk': liquidation_risk,
                'recommendation': 'HIGH_RISK' if risk_ratio > 0.5 or liquidation_risk else 'NORMAL'
            }
            
        except Exception as e:
            print(f"风险检查失败: {e}")
            return {}
