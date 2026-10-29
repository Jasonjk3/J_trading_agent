# -*- coding: utf-8 -*-
# @ModuleName: trading_example.py
# @Author: jason
# @Email: jasonforjob@qq.com
# @Time: 2025/3/7
# @Desc: OKX永续合约交易示例

import asyncio
from lib.okx.okx_api import ApiService


class TradingExample:
    def __init__(self, api_key: str, secret_key: str, passphrase: str, is_sandbox: bool = True):
        """初始化交易示例
        
        Args:
            api_key: OKX API密钥
            secret_key: OKX Secret密钥
            passphrase: OKX Passphrase
            is_sandbox: 是否使用沙盒环境，默认True
        """
        self.api = ApiService(api_key, secret_key, passphrase, is_sandbox)
    
    async def get_market_info(self, symbol: str = "BTC-USDT-SWAP"):
        """获取市场信息"""
        try:
            # 获取行情信息
            ticker = await self.api.get_ticker(symbol)
            print(f"=== {symbol} 市场信息 ===")
            print(f"最新价格: {ticker.get('last', 'N/A')}")
            print(f"24小时最高价: {ticker.get('high24h', 'N/A')}")
            print(f"24小时最低价: {ticker.get('low24h', 'N/A')}")
            print(f"24小时成交量: {ticker.get('vol24h', 'N/A')}")

        except Exception as e:
            print(f"获取市场信息失败: {e}")
    
    async def set_leverage_example(self, symbol: str = "BTC-USDT-SWAP", leverage: str = "10"):
        """设置杠杆示例"""
        try:
            print(f"\n=== 设置杠杆倍数 ===")
            result = await self.api.set_leverage(
                inst_id=symbol,
                lever=leverage,
                mgn_mode="cross"  # 全仓模式
            )
            print(f"设置杠杆成功: {result}")
            
            # 查询当前杠杆设置
            leverage_info = await self.api.get_leverage(symbol, "cross")
            print(f"当前杠杆设置: {leverage_info}")
            
        except Exception as e:
            print(f"设置杠杆失败: {e}")
    
    async def place_long_order_example(self, symbol: str = "BTC-USDT-SWAP", 
                                     quantity: str = "0.001", price: str = None):
        """做多示例"""
        try:
            print(f"\n=== 做多交易示例 ===")
            
            if price:
                # 限价单
                order_result = await self.api.place_order(
                    inst_id=symbol,
                    td_mode="cross",  # 全仓模式
                    side="buy",       # 买入
                    ord_type="limit", # 限价单
                    sz=quantity,
                    px=price,
                    pos_side="long"   # 开多
                )
                print(f"限价多单下单成功: {order_result}")
            else:
                # 市价单
                order_result = await self.api.place_order(
                    inst_id=symbol,
                    td_mode="cross",  # 全仓模式
                    side="buy",       # 买入
                    ord_type="market", # 市价单
                    sz=quantity,
                    pos_side="long"   # 开多
                )
                print(f"市价多单下单成功: {order_result}")
                
        except Exception as e:
            print(f"做多下单失败: {e}")
    
    async def place_short_order_example(self, symbol: str = "BTC-USDT-SWAP", 
                                      quantity: str = "0.001", price: str = None):
        """做空示例"""
        try:
            print(f"\n=== 做空交易示例 ===")
            
            if price:
                # 限价单
                order_result = await self.api.place_order(
                    inst_id=symbol,
                    td_mode="cross",  # 全仓模式
                    side="sell",      # 卖出
                    ord_type="limit", # 限价单
                    sz=quantity,
                    px=price,
                    pos_side="short"  # 开空
                )
                print(f"限价空单下单成功: {order_result}")
            else:
                # 市价单
                order_result = await self.api.place_order(
                    inst_id=symbol,
                    td_mode="cross",  # 全仓模式
                    side="sell",      # 卖出
                    ord_type="market", # 市价单
                    sz=quantity,
                    pos_side="short"  # 开空
                )
                print(f"市价空单下单成功: {order_result}")
                
        except Exception as e:
            print(f"做空下单失败: {e}")
    
    async def place_tp_sl_order_example(self, symbol: str = "BTC-USDT-SWAP", 
                                       quantity: str = "0.001", 
                                       tp_price: str = None, sl_price: str = None):
        """止盈止损示例"""
        try:
            print(f"\n=== 止盈止损示例 ===")
            
            # 使用策略委托下单（止盈止损）
            algo_result = await self.api.place_algo_order(
                inst_id=symbol,
                td_mode="cross",
                side="buy",
                ord_type="conditional",  # 单向止盈止损
                sz=quantity,
                pos_side="long",
                tp_trigger_px=tp_price,  # 止盈触发价
                tp_trigger_px_type="last",  # 使用最新价格
                tp_ord_px=tp_price,      # 止盈委托价
                sl_trigger_px=sl_price,  # 止损触发价
                sl_trigger_px_type="last",  # 使用最新价格
                sl_ord_px=sl_price       # 止损委托价
            )
            print(f"止盈止损单下单成功: {algo_result}")
            
        except Exception as e:
            print(f"止盈止损下单失败: {e}")
    
    async def get_positions_example(self, symbol: str = "BTC-USDT-SWAP"):
        """获取持仓示例"""
        try:
            print(f"\n=== 当前持仓信息 ===")
            positions = await self.api.get_account_positions(
                inst_type="SWAP",
                inst_id=symbol
            )
            
            if positions:
                for pos in positions:
                    print(f"产品ID: {pos.get('instId')}")
                    print(f"持仓方向: {pos.get('posSide')}")
                    print(f"持仓数量: {pos.get('pos')}")
                    print(f"开仓均价: {pos.get('avgPx')}")
                    print(f"未实现盈亏: {pos.get('upl')}")
                    print(f"未实现盈亏率: {pos.get('uplRatio')}")
                    print(f"杠杆倍数: {pos.get('lever')}")
                    print(f"强平价格: {pos.get('liqPx')}")
                    print("---")
            else:
                print("当前无持仓")
                
        except Exception as e:
            print(f"获取持仓信息失败: {e}")
    
    async def get_orders_example(self, symbol: str = "BTC-USDT-SWAP"):
        """获取订单示例"""
        try:
            print(f"\n=== 当前订单信息 ===")
            
            # 获取未成交订单
            pending_orders = await self.api.get_orders_pending(
                inst_type="SWAP",
                inst_id=symbol
            )
            
            print(f"未成交订单数量: {len(pending_orders)}")
            for order in pending_orders[:5]:  # 只显示前5个
                print(f"订单ID: {order.get('ordId')}")
                print(f"订单类型: {order.get('ordType')}")
                print(f"订单方向: {order.get('side')}")
                print(f"持仓方向: {order.get('posSide')}")
                print(f"委托数量: {order.get('sz')}")
                print(f"委托价格: {order.get('px')}")
                print(f"订单状态: {order.get('state')}")
                print("---")
            
            # 获取历史订单
            history_orders = await self.api.get_orders_history(
                inst_type="SWAP",
                inst_id=symbol,
                limit=10
            )
            
            print(f"\n历史订单数量: {len(history_orders)}")
            for order in history_orders[:3]:  # 只显示前3个
                print(f"订单ID: {order.get('ordId')}")
                print(f"订单状态: {order.get('state')}")
                print(f"成交数量: {order.get('fillSz')}")
                print(f"成交价格: {order.get('fillPx')}")
                print("---")
                
        except Exception as e:
            print(f"获取订单信息失败: {e}")
    
    async def cancel_order_example(self, symbol: str, order_id: str):
        """撤销订单示例"""
        try:
            print(f"\n=== 撤销订单 ===")
            result = await self.api.cancel_order(
                inst_id=symbol,
                ord_id=order_id
            )
            print(f"撤销订单成功: {result}")
            
        except Exception as e:
            print(f"撤销订单失败: {e}")
    
    async def get_account_balance_example(self):
        """获取账户余额示例"""
        try:
            print(f"\n=== 账户余额信息 ===")
            balance = await self.api.get_account_balance()
            
            for item in balance:
                ccy = item.get('ccy')
                avail_bal = item.get('availBal', '0')
                frozen_bal = item.get('frozenBal', '0')
                eq_usd = item.get('eqUsd', '0')
                
                # 安全地转换为float，处理None值
                try:
                    avail_bal_float = float(avail_bal) if avail_bal is not None else 0.0
                    frozen_bal_float = float(frozen_bal) if frozen_bal is not None else 0.0
                except (ValueError, TypeError):
                    avail_bal_float = 0.0
                    frozen_bal_float = 0.0
                
                if avail_bal_float >= 0 or frozen_bal_float >= 0:
                    print(f"币种: {ccy}")
                    print(f"可用余额: {avail_bal}")
                    print(f"冻结余额: {frozen_bal}")
                    print(f"美元价值: {eq_usd}")
                    print("---")
                    
        except Exception as e:
            print(f"获取账户余额失败: {e}")
    
    async def run_complete_example(self):
        """运行完整示例"""
        symbol = "DOGE-USDT-SWAP"
        
        print("=== OKX永续合约交易完整示例 ===")
        
        # # 1. 获取市场信息
        await self.get_market_info(symbol)
        # #
        # # 2. 获取账户余额
        await self.get_account_balance_example()
        
        # # 3. 设置杠杆
        await self.set_leverage_example(symbol, "5")

        # 4. 获取当前持仓
        await self.get_positions_example(symbol)
        #
        # 5. 获取当前订单
        await self.get_orders_example(symbol)
        
        # 注意：以下为实际交易操作，请谨慎使用
        # print("\n=== 注意：以下为实际交易操作示例，请谨慎使用 ===")
        
        # 6. 做多示例（市价单）
        # await self.place_long_order_example(symbol, "0.001")
        
        # 7. 做空示例（限价单）
        await self.place_short_order_example(symbol, "1", "0.193")
        
        # 8. 止盈止损示例
        # await self.place_tp_sl_order_example(symbol, "0.001", "55000", "45000")


async def main():
    """主函数"""
    # 请替换为您的实际API密钥
    OKX_API_KEY = '944e7adf-0ff3-4cec-bc3c-3c09feeb3043'
    OKX_SECRET_KEY = '0AA8D8A67C8CEA9DA99474D3A7327617'
    OKX_PASSPHRASE = 'Jason2025.!'

    
    # 创建交易示例实例
    trading_example = TradingExample(OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE, is_sandbox=False)
    
    # 运行完整示例
    await trading_example.run_complete_example()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
