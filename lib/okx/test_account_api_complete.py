# -*- ecoding: utf-8 -*-
# @ModuleName: test_account_api_complete.py
# @Author: jason
# @Email: jasonforjob@qq.com
# @Time: 2025/3/7
# @Desc: 测试完整的OKX账户API功能
import asyncio
import os
from lib.okx.okx_api import ApiService

OKX_API_KEY = '944e7adf-0ff3-4cec-bc3c-3c09feeb3043'
OKX_SECRET_KEY = '0AA8D8A67C8CEA9DA99474D3A7327617'
OKX_PASSPHRASE = 'Jason2025.!'
OKX_IS_SANDBOX = False

# 初始化API服务
api_service = ApiService(
    API_KEY=OKX_API_KEY,
    SECRET_KEY=OKX_SECRET_KEY,
    PASSPHRASE=OKX_PASSPHRASE,
    IS_SANDBOX=OKX_IS_SANDBOX
)

async def account_apis():
    """测试账户相关API"""


    print("=" * 60)
    print("开始测试OKX账户相关API")
    print("=" * 60)

    try:
        # 测试获取账户余额
        print("\n1. 测试获取账户余额...")
        balance_data = await api_service.get_account_balance()
        print(f"账户余额数据: {len(balance_data)} 条记录")
        if balance_data:
            print("前3个币种余额:")
            for i, item in enumerate(balance_data[:3]):
                print(f"  {i+1}. {item.get('ccy', 'N/A')}: 可用={item.get('availBal', 0)}, 冻结={item.get('frozenBal', 0)}, 总权益={item.get('eqUsd', 0)} USD")

        # 测试获取特定币种余额
        print("\n2. 测试获取USDT余额...")
        usdt_balance = await api_service.get_account_balance("USDT")
        if usdt_balance:
            print(f"USDT余额: {usdt_balance[0]}")

        # 测试获取账户持仓
        print("\n3. 测试获取账户持仓...")
        positions_data = await api_service.get_account_positions()
        print(f"账户持仓数据: {len(positions_data)} 条记录")
        if positions_data:
            print("前3个持仓:")
            for i, item in enumerate(positions_data[:3]):
                print(f"  {i+1}. {item.get('instId', 'N/A')}: 持仓={item.get('pos', 0)}, 方向={item.get('posSide', 'N/A')}, 未实现盈亏={item.get('upl', 0)}")

        # 测试获取现货持仓
        print("\n4. 测试获取现货持仓...")
        spot_positions = await api_service.get_account_positions(inst_type="SPOT")
        print(f"现货持仓数据: {len(spot_positions)} 条记录")

        # 测试获取永续合约持仓
        print("\n5. 测试获取永续合约持仓...")
        swap_positions = await api_service.get_account_positions(inst_type="SWAP")
        print(f"永续合约持仓数据: {len(swap_positions)} 条记录")

        # 测试获取交割合约持仓
        print("\n6. 测试获取交割合约持仓...")
        futures_positions = await api_service.get_account_positions(inst_type="FUTURES")
        print(f"交割合约持仓数据: {len(futures_positions)} 条记录")

        # 测试获取历史持仓
        print("\n7. 测试获取历史持仓...")
        history_data = await api_service.get_positions_history(limit=10)
        print(f"历史持仓数据: {len(history_data)} 条记录")
        if history_data:
            print("前3个历史持仓:")
            for i, item in enumerate(history_data[:3]):
                print(f"  {i+1}. {item.get('instId', 'N/A')}: 已实现盈亏={item.get('pnl', 0)}, 平仓时间={item.get('closeTime', 'N/A')}")

        # 测试获取现货历史持仓
        print("\n8. 测试获取现货历史持仓...")
        spot_history = await api_service.get_positions_history(inst_type="SPOT", limit=5)
        print(f"现货历史持仓数据: {len(spot_history)} 条记录")

        # 测试获取永续合约历史持仓
        print("\n9. 测试获取永续合约历史持仓...")
        swap_history = await api_service.get_positions_history(inst_type="SWAP", limit=5)
        print(f"永续合约历史持仓数据: {len(swap_history)} 条记录")

        # 测试获取交割合约历史持仓
        print("\n10. 测试获取交割合约历史持仓...")
        futures_history = await api_service.get_positions_history(inst_type="FUTURES", limit=5)
        print(f"交割合约历史持仓数据: {len(futures_history)} 条记录")

        print("\n" + "=" * 60)
        print("所有测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"测试过程中出现错误: {str(e)}")
        print("请检查API配置是否正确")


async def specific_functions():
    """测试特定功能"""
    # 从环境变量获取API配置


    print("\n" + "=" * 60)
    print("测试特定功能")
    print("=" * 60)

    try:
        # 测试获取特定产品持仓
        print("\n1. 测试获取BTC-USDT-SWAP持仓...")
        btc_positions = await api_service.get_account_positions(inst_id="BTC-USDT-SWAP")
        print(f"BTC-USDT-SWAP持仓: {len(btc_positions)} 条记录")
        if btc_positions:
            print(f"持仓详情: {btc_positions[0]}")

        # 测试获取特定币种余额
        print("\n2. 测试获取BTC余额...")
        btc_balance = await api_service.get_account_balance("BTC")
        if btc_balance:
            print(f"BTC余额: {btc_balance[0]}")

        # 测试获取特定产品的历史持仓
        print("\n3. 测试获取ETH-USDT-SWAP历史持仓...")
        eth_history = await api_service.get_positions_history(inst_id="ETH-USDT-SWAP", limit=5)
        print(f"ETH-USDT-SWAP历史持仓: {len(eth_history)} 条记录")

        # 测试获取特定平仓类型的历史持仓
        print("\n4. 测试获取手动平仓的历史持仓...")
        manual_history = await api_service.get_positions_history(type_="manual", limit=5)
        print(f"手动平仓历史持仓: {len(manual_history)} 条记录")

    except Exception as e:
        print(f"特定功能测试中出现错误: {str(e)}")


async def test_error_handling():
    """测试错误处理"""

    
    print("\n" + "=" * 60)
    print("测试错误处理")
    print("=" * 60)
    
    try:
        # 测试无效的币种
        print("\n1. 测试无效的币种...")
        try:
            invalid_balance = await api_service.get_account_balance("INVALID")
            print(f"无效币种余额: {invalid_balance}")
        except Exception as e:
            print(f"预期的错误: {str(e)}")
        
        # 测试无效的产品类型
        print("\n2. 测试无效的产品类型...")
        try:
            invalid_positions = await api_service.get_account_positions(inst_type="INVALID")
            print(f"无效产品类型持仓: {invalid_positions}")
        except Exception as e:
            print(f"预期的错误: {str(e)}")
        
        # 测试无效的历史持仓参数
        print("\n3. 测试无效的历史持仓参数...")
        try:
            invalid_history = await api_service.get_positions_history(inst_type="INVALID", limit=5)
            print(f"无效历史持仓: {invalid_history}")
        except Exception as e:
            print(f"预期的错误: {str(e)}")
        
    except Exception as e:
        print(f"错误处理测试中出现错误: {str(e)}")


if __name__ == "__main__":

    
    # 运行测试
    asyncio.run(account_apis())
    # asyncio.run(specific_functions())
    # asyncio.run(test_error_handling())
