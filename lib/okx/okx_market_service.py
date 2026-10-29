# -*- coding: utf-8 -*-
# @ModuleName: market_service.py
# @Author: jason
# @Email: jasonforjob@qq.com
# @Time: 2025/3/7
# @Desc: OKX市场数据服务层
from typing import List, Dict, Optional, Union
import os
from decimal import Decimal, ROUND_DOWN
import asyncio
from datetime import datetime, timezone

from lib.okx.okx_api import ApiService


class OkxMarketService:
    """OKX市场数据服务类"""

    @staticmethod
    def rank_tickers(tickers, metric="gainers", limit=10):
        rows = []
        for source in tickers:
            if not source.get("instId", "").endswith("-USDT"):
                continue
            try:
                last, opened = Decimal(source["last"]), Decimal(source["open24h"])
                quote_volume = Decimal(source.get("volCcy24h") or "0")
                if not all(value.is_finite() for value in (last, opened, quote_volume)) or min(last, opened) <= 0:
                    continue
                rows.append({**source, "change_pct": str((last / opened - 1) * 100),
                             "quoteVolume24h": str(quote_volume), "quoteCurrency": "USDT"})
            except (ValueError, TypeError, ArithmeticError, KeyError):
                continue
        key = "quoteVolume24h" if metric == "volume" else "change_pct"
        return sorted(rows, key=lambda row: Decimal(row[key]), reverse=metric != "losers")[:limit]
    
    def __init__(self, api_key: str = None, secret_key: str = None, passphrase: str = None, 
                 is_sandbox: bool = True, proxy: str = None):
        """初始化OKX市场数据服务
        
        Args:
            api_key: OKX API密钥，如果为None则从环境变量获取
            secret_key: OKX Secret密钥，如果为None则从环境变量获取
            passphrase: OKX Passphrase，如果为None则从环境变量获取
            is_sandbox: 是否使用沙盒环境，默认True
            proxy: 代理设置，如果为None则从环境变量获取
        """
        # 从参数或环境变量获取API配置
        self.api_key = api_key or os.getenv("OKX_API_KEY", "")
        self.secret_key = secret_key or os.getenv("OKX_SECRET_KEY", "")
        self.passphrase = passphrase or os.getenv("OKX_PASSPHRASE", "")
        self.is_sandbox = is_sandbox if api_key else (os.getenv("OKX_IS_SANDBOX", "false").lower() == "true")
        self.proxy = proxy or os.getenv("OKX_PROXY", None)
        
        # 验证必要的配置
        if not all([self.api_key, self.secret_key, self.passphrase]):
            raise ValueError("API配置不完整，请提供api_key、secret_key和passphrase")
        
        # 初始化API服务
        self.api = ApiService(
            API_KEY=self.api_key,
            SECRET_KEY=self.secret_key,
            PASSPHRASE=self.passphrase,
            IS_SANDBOX=self.is_sandbox,
            proxy=self.proxy
        )

    # ==================== 市场数据相关 ====================
    
    async def get_kline_data(self, symbol: str, interval: str, limit: int = 100) -> List[Dict]:
        """获取K线数据
        
        Args:
            symbol: 交易对，如 "BTC-USDT"
            interval: K线间隔，如 "5m", "15m", "1H", "4H", "1D"
            limit: 获取数量，默认100条，最大300条
            
        Returns:
            List[Dict]: K线数据列表
        """
        try:
            # 参数验证
            if not symbol or not interval:
                raise ValueError("symbol和interval不能为空")
            
            if limit > 300:
                limit = 300
                print(f"警告: limit超过最大限制，已调整为300")
            
            data = await self.api.get_kline_data(symbol, interval, limit)
            print(f"获取K线数据成功: {symbol}, 间隔: {interval}, 数量: {len(data)}")
            return data
            
        except Exception as e:
            print(f"获取K线数据失败: {symbol}, {e}")
            raise

    async def get_market_depth(self, symbol: str, depth: int = 20) -> Dict:
        """获取市场深度数据
        
        Args:
            symbol: 交易对，如 "BTC-USDT"
            depth: 深度档数，默认20档，最大400档
            
        Returns:
            Dict: 市场深度数据
        """
        try:
            if not symbol:
                raise ValueError("symbol不能为空")
            
            if depth > 400:
                depth = 400
                print(f"警告: depth超过最大限制，已调整为400")
            
            data = await self.api.get_market_depth(symbol, depth)
            print(f"获取市场深度成功: {symbol}, 档数: {depth}")
            return data
            
        except Exception as e:
            print(f"获取市场深度失败: {symbol}, {e}")
            raise

    async def get_ticker(self, symbol: str) -> Dict:
        """获取单个产品行情信息
        
        Args:
            symbol: 产品ID，如 "BTC-USDT"
            
        Returns:
            Dict: 产品行情信息
        """
        try:
            if not symbol:
                raise ValueError("symbol不能为空")
            
            data = await self.api.get_ticker(symbol)
            print(f"获取行情信息成功: {symbol}")
            return data
            
        except Exception as e:
            print(f"获取行情信息失败: {symbol}, {e}")
            raise

    async def get_supported_symbols(self) -> List[Dict]:
        """获取支持的交易对列表
        
        Returns:
            List[Dict]: 交易对列表
        """
        try:
            data = await self.api.get_supported_symbols()
            print(f"获取交易对列表成功: 共{len(data)}个")
            return data
            
        except Exception as e:
            print(f"获取交易对列表失败: {e}")
            raise

    async def get_tickers(self, inst_type: str = None, uly: str = None) -> List[Dict]:
        """获取所有产品行情信息
        
        Args:
            inst_type: 产品类型 (SPOT, SWAP, FUTURES, OPTION)
            uly: 标的指数，如 BTC-USD
            
        Returns:
            List[Dict]: 产品行情信息列表
        """
        try:
            data = await self.api.get_tickers(inst_type, uly)
            print(f"获取产品行情成功: 类型={inst_type}, 数量={len(data)}")
            return data
            
        except Exception as e:
            print(f"获取产品行情失败: {e}")
            raise

    async def get_index_tickers(self, quote_ccy: str = None, inst_id: str = None) -> List[Dict]:
        """获取指数行情
        
        Args:
            quote_ccy: 指数计价单位，如 USD
            inst_id: 指数，如 BTC-USD
            
        Returns:
            List[Dict]: 指数行情信息列表
        """
        try:
            data = await self.api.get_index_tickers(quote_ccy, inst_id)
            print(f"获取指数行情成功: 计价单位={quote_ccy}, 数量={len(data)}")
            return data
            
        except Exception as e:
            print(f"获取指数行情失败: {e}")
            raise

    async def get_order_books(self, inst_id: str, sz: int = 1) -> Dict:
        """获取产品深度
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            sz: 深度档位数量，最大值可传400，即买卖深度共800条
            
        Returns:
            Dict: 产品深度信息
        """
        try:
            if not inst_id:
                raise ValueError("inst_id不能为空")
            
            if sz > 400:
                sz = 400
                print(f"警告: sz超过最大限制，已调整为400")
            
            data = await self.api.get_order_books(inst_id, sz)
            print(f"获取产品深度成功: {inst_id}, 档数={sz}")
            return data
            
        except Exception as e:
            print(f"获取产品深度失败: {inst_id}, {e}")
            raise

    async def get_order_books_lite(self, inst_id: str) -> Dict:
        """获取产品轻量深度
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            
        Returns:
            Dict: 产品轻量深度信息
        """
        try:
            if not inst_id:
                raise ValueError("inst_id不能为空")
            
            data = await self.api.get_order_books_lite(inst_id)
            print(f"获取轻量深度成功: {inst_id}")
            return data
            
        except Exception as e:
            print(f"获取轻量深度失败: {inst_id}, {e}")
            raise

    async def get_candlesticks(self, inst_id: str, bar: str = "1m", before: str = None,
                              after: str = None, limit: int = 100) -> List[List]:
        """获取K线数据（语义同 OKX 官方：before=较新，after=较旧）
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            bar: K线周期，如 1m/3m/5m/15m/30m/1H/2H/4H/6H/12H/1D/1W/1M/3M/6M/1Y
            before: 返回开盘时间晚于该 ts 的 K 线；仅传 before 时多为最新数据
            after: 返回开盘时间早于该 ts 的 K 线（向历史翻页）
            limit: 分页返回的结果集数量，最大为300，不填默认返回100条
            
        Returns:
            List[List]: K线数据列表
        """
        try:
            if not inst_id or not bar:
                raise ValueError("inst_id和bar不能为空")
            
            if limit > 300:
                limit = 300
                print(f"警告: limit超过最大限制，已调整为300")
            
            data = await self.api.get_candlesticks(inst_id, bar, before, after, limit)
            print(f"获取K线数据成功: {inst_id}, 周期: {bar}, 数量: {len(data)}")
            return data
            
        except Exception as e:
            print(f"获取K线数据失败: {inst_id}, {e}")
            raise

    async def get_trades(self, inst_id: str, limit: int = 100) -> List[Dict]:
        """获取交易产品公共成交数据
        
        Args:
            inst_id: 产品ID，如 BTC-USDT
            limit: 返回的结果集数量，最大为500，默认100
            
        Returns:
            List[Dict]: 成交数据列表
        """
        try:
            if not inst_id:
                raise ValueError("inst_id不能为空")
            
            if limit > 500:
                limit = 500
                print(f"警告: limit超过最大限制，已调整为500")
            
            data = await self.api.get_trades(inst_id, limit)
            print(f"获取成交数据成功: {inst_id}, 数量: {len(data)}")
            return data
            
        except Exception as e:
            print(f"获取成交数据失败: {inst_id}, {e}")
            raise

    async def get_system_status(self, state: str = None) -> List[Dict]:
        """获取系统升级事件的状态
        
        Args:
            state: 系统的状态，不填写此参数，默认返回等待中、进行中和预开放的数据
            
        Returns:
            List[Dict]: 系统状态信息列表
        """
        try:
            data = await self.api.get_system_status(state)
            print(f"获取系统状态成功: 状态={state}, 数量={len(data)}")
            return data
            
        except Exception as e:
            print(f"获取系统状态失败: {e}")
            raise

    async def get_platform_24h_volume(self) -> Dict:
        """获取平台24小时总成交量
        
        Returns:
            Dict: 平台24小时总成交量信息
        """
        try:
            data = await self.api.get_platform_24h_volume()
            print("获取平台24小时总成交量成功")
            return data
            
        except Exception as e:
            print(f"获取平台24小时总成交量失败: {e}")
            raise

    # ==================== 账户相关 ====================
    
    async def get_account_balance(self, ccy: str = None) -> List[Dict]:
        """获取账户余额
        
        Args:
            ccy: 币种，如 BTC，不填写此参数，默认返回所有币种的余额信息
            
        Returns:
            List[Dict]: 账户余额信息列表
        """
        try:
            data = await self.api.get_account_balance(ccy)
            print(f"获取账户余额成功: 币种={ccy or '全部'}, 数量={len(data)}")
            return data
            
        except Exception as e:
            print(f"获取账户余额失败: {e}")
            raise

    async def get_account_positions(self, inst_type: str = None, inst_id: str = None, 
                                   pos_id: str = None) -> List[Dict]:
        """获取账户持仓信息
        
        Args:
            inst_type: 产品类型 (SPOT, MARGIN, SWAP, FUTURES, OPTION)
            inst_id: 产品ID，如 BTC-USDT-SWAP
            pos_id: 持仓ID，支持多个 posId 查询（半角逗号分隔）
            
        Returns:
            List[Dict]: 持仓信息列表
        """
        try:
            data = await self.api.get_account_positions(inst_type, inst_id, pos_id)
            print(f"获取账户持仓成功: 类型={inst_type}, 产品={inst_id}, 数量={len(data)}")
            return data
            
        except Exception as e:
            print(f"获取账户持仓失败: {e}")
            raise

    async def get_positions_history(self, inst_type: str = None, inst_id: str = None,
                                   mgn_mode: str = None, type_: str = None, 
                                   pos_id: str = None, after: str = None,
                                   before: str = None, limit: int = 100) -> List[Dict]:
        """获取历史持仓信息
        
        Args:
            inst_type: 产品类型 (SPOT, MARGIN, SWAP, FUTURES, OPTION)
            inst_id: 产品ID，如 BTC-USDT-SWAP
            mgn_mode: 保证金模式 (cross, isolated)
            type_: 平仓类型 (liquidation, partial_liquidation, adl, delivery, manual)
            pos_id: 持仓ID
            after: 请求此 ID 之后（更新的数据）的分页内容
            before: 请求此 ID 之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 历史持仓信息列表
        """
        try:
            if limit > 100:
                limit = 100
                print(f"警告: limit超过最大限制，已调整为100")
            
            data = await self.api.get_positions_history(
                inst_type, inst_id, mgn_mode, type_, pos_id, after, before, limit
            )
            print(f"获取历史持仓成功: 类型={inst_type}, 数量={len(data)}")
            return data
            
        except Exception as e:
            print(f"获取历史持仓失败: {e}")
            raise



    # ==================== 市场数据便捷方法 ====================
    
    async def get_btc_price(self) -> float:
        """获取BTC当前价格"""
        try:
            ticker = await self.get_ticker("BTC-USDT")
            return float(ticker.get('last', 0))
        except Exception as e:
            print(f"获取BTC价格失败: {e}")
            return 0.0

    async def get_eth_price(self) -> float:
        """获取ETH当前价格"""
        try:
            ticker = await self.get_ticker("ETH-USDT")
            return float(ticker.get('last', 0))
        except Exception as e:
            print(f"获取ETH价格失败: {e}")
            return 0.0

    async def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        tickers = await self.get_tickers(inst_type="SPOT")
        if not tickers:
            raise ValueError("交易所未返回有效行情")
        return self.rank_tickers(tickers, "gainers", limit)

    async def get_top_losers(self, limit: int = 10) -> List[Dict]:
        tickers = await self.get_tickers(inst_type="SPOT")
        if not tickers:
            raise ValueError("交易所未返回有效行情")
        return self.rank_tickers(tickers, "losers", limit)

    async def get_volume_leaders(self, limit: int = 10) -> List[Dict]:
        tickers = await self.get_tickers(inst_type="SPOT")
        if not tickers:
            raise ValueError("交易所未返回有效行情")
        return self.rank_tickers(tickers, "volume", limit)

    async def get_market_summary(self) -> Dict:
        tickers = await self.get_tickers(inst_type="SPOT")
        if not tickers:
            raise ValueError("交易所未返回有效行情")
        index = {row.get("instId"): row for row in tickers}
        return {"btc_price": index.get("BTC-USDT", {}).get("last"),
                "eth_price": index.get("ETH-USDT", {}).get("last"),
                "top_gainers": self.rank_tickers(tickers, "gainers", 5),
                "top_losers": self.rank_tickers(tickers, "losers", 5),
                "volume_leaders": self.rank_tickers(tickers, "volume", 5),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scope": "OKX SPOT USDT", "quoteCurrency": "USDT"}

