# -*- ecoding: utf-8 -*-
# @ModuleName: api.py
# @Author: jason
# @Email: jasonforjob@qq.com
# @Time: 2025/3/7
# @Desc:
from typing import List, Dict

from lib.okx.okx_base import OkxBase


class ApiService(OkxBase):
    def __init__(self, API_KEY, SECRET_KEY, PASSPHRASE, IS_SANDBOX=False, proxy=None):
        super().__init__(API_KEY, SECRET_KEY, PASSPHRASE, IS_SANDBOX, proxy)

    async def get_kline_data(self, symbol: str, interval: str, limit: int = 100) -> List[Dict]:
        """获取K线数据

        Args:
            symbol: 交易对，如 "BTC-USDT"
            interval: K线间隔，如 "5m", "15m", "1H", "4H", "1D"
            limit: 获取数量，默认100条
        """
        path = "/market/candles"
        params = {
            "instId": symbol,
            "bar": interval,
            "limit": str(limit)  # OKX API需要字符串类型的参数
        }
        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取K线数据失败: {str(e)}")

    async def get_market_depth(self, symbol: str, depth: int = 20) -> Dict:
        """获取市场深度数据

        Args:
            symbol: 交易对，如 "BTC-USDT"
            depth: 深度档数，默认20档
        """
        path = "/market/books"
        params = {
            "instId": symbol,
            "sz": str(depth)  # OKX API需要字符串类型的参数
        }
        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"获取深度数据失败: {str(e)}")

    async def get_ticker(self, symbol: str) -> Dict:
        """获取单个产品行情信息

        Args:
            symbol: 产品ID，如 "BTC-USDT"

        Returns:
            Dict: 包含以下字段的字典
                instType: 产品类型
                instId: 产品ID
                last: 最新成交价
                lastSz: 最新成交的数量
                askPx: 卖一价
                askSz: 卖一价对应的数量
                bidPx: 买一价
                bidSz: 买一价对应的数量
                open24h: 24小时开盘价
                high24h: 24小时最高价
                low24h: 24小时最低价
                volCcy24h: 24小时成交量，以币为单位
                vol24h: 24小时成交量，以张为单位
                ts: 数据产生时间，Unix时间戳的毫秒数格式，如 1597026383085
        """
        path = "/market/ticker"
        params = {
            "instId": symbol
        }
        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"获取单个产品行情信息失败: {str(e)}")

    async def get_supported_symbols(self) -> List[Dict]:
        """获取支持的交易对列表"""
        path = "/market/tickers"
        params = {
            "instType": "SPOT"
        }
        try:
            response = await self._request("GET", path, params=params)
            data = response.get("data", [])
            return [
                {
                    "instId": item.get("instId", ""),
                    "baseCcy": item.get("instId", "").split("-")[0],
                    "quoteCcy": item.get("instId", "").split("-")[1] if "-" in item.get("instId", "") else "",
                    "last": item.get("last", ""),
                    "vol24h": item.get("vol24h", ""),
                    "volCcy24h": item.get("volCcy24h", "")
                }
                for item in data
                if "-" in item.get("instId", "")
            ]
        except Exception as e:
            raise Exception(f"获取交易对列表失败: {str(e)}")

    async def get_instruments(self, inst_type: str, uly: str = None, inst_family: str = None) -> List[Dict]:
        """获取产品基础信息列表

        Args:
            inst_type: 产品类型，如 SPOT / SWAP
            uly: 标的指数，仅适用于衍生品
            inst_family: 交易品种，仅适用于衍生品
        """
        path = "/public/instruments"
        params = {
            "instType": inst_type
        }
        if uly:
            params["uly"] = uly
        if inst_family:
            params["instFamily"] = inst_family

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取产品信息失败: {str(e)}")

    async def get_tickers(self, inst_type: str = None, uly: str = None) -> List[Dict]:
        """获取所有产品行情信息

        Args:
            inst_type: 产品类型
                SPOT：币币
                SWAP：永续合约
                FUTURES：交割合约
                OPTION：期权
            uly: 标的指数，仅适用于交割/永续/期权，如 BTC-USD

        Returns:
            List[Dict]: 产品行情信息列表
        """
        path = "/market/tickers"
        params = {}

        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取所有产品行情信息失败: {str(e)}")

    async def get_index_tickers(self, quote_ccy: str = None, inst_id: str = None) -> List[Dict]:
        """获取指数行情

        Args:
            quote_ccy: 指数计价单位，如 USD
            inst_id: 指数，如 BTC-USD

        Returns:
            List[Dict]: 指数行情信息列表
        """
        path = "/market/index-tickers"
        params = {}

        if quote_ccy:
            params["quoteCcy"] = quote_ccy
        if inst_id:
            params["instId"] = inst_id

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取指数行情失败: {str(e)}")

    async def get_order_books(self, inst_id: str, sz: int = 1) -> Dict:
        """获取产品深度

        Args:
            inst_id: 产品ID，如 BTC-USDT
            sz: 深度档位数量，最大值可传400，即买卖深度共800条
                1，5，10，20，50，100，200，400

        Returns:
            Dict: 产品深度信息
        """
        path = "/market/books"
        params = {
            "instId": inst_id,
            "sz": str(sz)
        }

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"获取产品深度失败: {str(e)}")

    async def get_order_books_lite(self, inst_id: str) -> Dict:
        """获取产品轻量深度

        Args:
            inst_id: 产品ID，如 BTC-USDT

        Returns:
            Dict: 产品轻量深度信息
        """
        path = "/market/books-lite"
        params = {
            "instId": inst_id
        }

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"获取产品轻量深度失败: {str(e)}")


    async def get_candlesticks(self, inst_id: str, bar: str = "1m", before: str = None,
                               after: str = None, limit: int = 100) -> List[List]:
        """获取K线数据（GET /api/v5/market/candles）

        与 OKX 官方文档一致（勿与旧注释混淆）：
            before: 返回开盘时间 **晚于** 请求 ts 的 K 线（更新的数据）；仅传 before 时返回最新行情
            after: 返回开盘时间 **早于** 请求 ts 的 K 线（更旧的数据），用于从某一时刻向历史翻页

        Args:
            inst_id: 产品ID，如 BTC-USDT
            bar: K线周期，如 1m/3m/5m/15m/30m/1H/2H/4H/6H/12H/1D/1W/1M/3M/6M/1Y
            before: 毫秒时间戳字符串
            after: 毫秒时间戳字符串
            limit: 分页返回的结果集数量，最大为300，不填默认返回100条

        Returns:
            List[List]: K线数据列表
        """
        path = "/market/candles"
        params = {
            "instId": inst_id,
            "bar": bar
        }

        if before:
            params["before"] = before
        if after:
            params["after"] = after
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取K线数据失败: {str(e)}")

    async def get_trades(self, inst_id: str, limit: int = 100) -> List[Dict]:
        """获取交易产品公共成交数据

        Args:
            inst_id: 产品ID，如 BTC-USDT
            limit: 返回的结果集数量，最大为500，默认100

        Returns:
            List[Dict]: 成交数据列表
        """
        path = "/market/trades"
        params = {
            "instId": inst_id
        }

        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取交易产品公共成交数据失败: {str(e)}")

    async def get_system_status(self, state: str = None) -> List[Dict]:
        """获取系统升级事件的状态

        系统状态包括：
        - scheduled：等待中
        - ongoing：进行中
        - pre_open：预开放
        - completed：已完成
        - canceled：已取消

        Args:
            state: 系统的状态，不填写此参数，默认返回等待中、进行中和预开放的数据

        Returns:
            List[Dict]: 系统状态信息列表，包含以下字段：
                title: 系统维护说明的标题
                state: 系统维护的状态
                begin: 系统维护的开始时间，Unix时间戳的毫秒数格式
                end: 交易全面开放的时间，Unix时间戳的毫秒数格式
                preOpenBegin: 预开放开始的时间
                href: 系统维护详情的超级链接
                serviceType: 服务类型
                system: 系统
                scheDesc: 改期进度说明
                maintType: 维护类型
                env: 环境
        """
        path = "/system/status"
        params = {}

        if state:
            params["state"] = state

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取系统状态失败: {str(e)}")

    async def get_platform_24h_volume(self) -> Dict:
        """获取平台24小时总成交量

        Returns:
            Dict: 平台24小时总成交量信息
        """
        path = "/market/platform-24-volume"

        try:
            response = await self._request("GET", path)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"获取平台24小时总成交量失败: {str(e)}")

    # ==================== 账户相关API ====================
    
    async def get_account_balance(self, ccy: str = None) -> List[Dict]:
        """获取账户余额

        Args:
            ccy: 币种，如 BTC，不填写此参数，默认返回所有币种的余额信息

        Returns:
            List[Dict]: 账户余额信息列表，包含以下字段：
                ccy: 币种，如 BTC
                frozenBal: 冻结余额
                availBal: 可用余额
                eq: 币种总权益
                eqUsd: 币种总权益（以美元价值计算的权益）
                uTime: 账户信息的更新时间，Unix时间戳的毫秒数格式
        """
        path = "/account/balance"
        params = {}
        
        if ccy:
            params["ccy"] = ccy

        try:
            response = await self._request("GET", path, params=params)
            print('请求成功')
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取账户余额失败: {str(e)}")

    async def get_account_positions(self, inst_type: str = None, inst_id: str = None, 
                                   pos_id: str = None) -> List[Dict]:
        """获取账户持仓信息

        Args:
            inst_type: 产品类型
                SPOT：币币
                MARGIN：币币杠杆
                SWAP：永续合约
                FUTURES：交割合约
                OPTION：期权
            inst_id: 产品ID，如 BTC-USDT-SWAP
            pos_id: 持仓ID，支持多个 posId 查询（半角逗号分隔）

        Returns:
            List[Dict]: 持仓信息列表，包含以下字段：
                instType: 产品类型
                instId: 产品ID
                posId: 持仓ID
                posSide: 持仓方向
                    long：多头
                    short：空头
                    net：净持仓
                pos: 持仓数量
                baseBal: 交易币余额
                quoteBal: 计价币余额
                posCcy: 持仓币种
                availPos: 可平仓数量
                avgPx: 开仓平均价
                upl: 未实现盈亏
                uplRatio: 未实现盈亏率
                lever: 杠杆倍数
                liqPx: 强平价格
                imr: 初始保证金
                margin: 保证金余额
                mgnRatio: 保证金率
                mmr: 维持保证金
                liab: 负债额
                liabCcy: 负债币种
                interest: 利息
                tradeId: 最新成交ID
                notionalUsd: 以美元价值计算的持仓数量
                optVal: 期权价值
                adl: 信号区
                cTime: 持仓创建时间
                uTime: 最近一次持仓更新时间
        """
        path = "/account/positions"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if inst_id:
            params["instId"] = inst_id
        if pos_id:
            params["posId"] = pos_id

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取账户持仓信息失败: {str(e)}")

    async def get_positions_history(self, inst_type: str = None, inst_id: str = None,
                                   mgn_mode: str = None, type_: str = None, 
                                   pos_id: str = None, after: str = None,
                                   before: str = None, limit: int = 100) -> List[Dict]:
        """获取历史持仓信息

        Args:
            inst_type: 产品类型
                SPOT：币币
                MARGIN：币币杠杆
                SWAP：永续合约
                FUTURES：交割合约
                OPTION：期权
            inst_id: 产品ID，如 BTC-USDT-SWAP
            mgn_mode: 保证金模式
                cross：全仓
                isolated：逐仓
            type_: 平仓类型
                liquidation：强平
                partial_liquidation：部分强平
                adl：ADL自动减仓
                delivery：交割
                manual：手动平仓
            pos_id: 持仓ID
            after: 请求此 ID 之后（更新的数据）的分页内容
            before: 请求此 ID 之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条

        Returns:
            List[Dict]: 历史持仓信息列表，包含以下字段：
                instType: 产品类型
                instId: 产品ID
                mgnMode: 保证金模式
                posId: 持仓ID
                posSide: 持仓方向
                pos: 持仓数量
                openAvgPx: 开仓平均价
                closeAvgPx: 平仓平均价
                pnl: 已实现盈亏
                pnlRatio: 已实现盈亏率
                lever: 杠杆倍数
                direction: 持仓方向
                closeTime: 平仓时间
                cTime: 持仓创建时间
                openMaxPos: 最大持仓数量
                closeMaxPos: 最大平仓数量
                uTime: 最近一次持仓更新时间
        """
        path = "/account/positions-history"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if inst_id:
            params["instId"] = inst_id
        if mgn_mode:
            params["mgnMode"] = mgn_mode
        if type_:
            params["type"] = type_
        if pos_id:
            params["posId"] = pos_id
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取历史持仓信息失败: {str(e)}")

    # ==================== 永续合约交易API ====================
    
    async def place_order(self, inst_id: str, td_mode: str, side: str, ord_type: str,
                         sz: str, px: str = None, ccy: str = None, cl_ord_id: str = None,
                         tag: str = None, pos_side: str = None, reduce_only: bool = None,
                         tgt_ccy: str = None, ban_amend: bool = None, tp_trigger_px: str = None,
                         tp_trigger_px_type: str = None, tp_ord_px: str = None,
                         sl_trigger_px: str = None, sl_trigger_px_type: str = None,
                         sl_ord_px: str = None, tp_trigger_px_sl_trigger_px: str = None,
                         tp_trigger_px_sl_trigger_px_type: str = None) -> Dict:
        """下单
        
        Args:
            inst_id: 产品ID，如 BTC-USDT-SWAP
            td_mode: 交易模式
                cash：现金模式
                cross：全仓模式
                isolated：逐仓模式
            side: 订单方向
                buy：买
                sell：卖
            ord_type: 订单类型
                market：市价单
                limit：限价单
                post_only：只做maker单
                fok：全部成交或立即取消
                ioc：立即成交并取消剩余
            sz: 委托数量
            px: 委托价格，当ord_type为limit时，此参数必填
            ccy: 保证金币种，仅适用于单币种保证金模式下的全仓杠杆订单
            cl_ord_id: 客户自定义订单ID
            tag: 订单标签
            pos_side: 持仓方向
                long：开多
                short：开空
                net：单向持仓
            reduce_only: 是否只减仓，默认false
            tgt_ccy: 市价单委托数量sz的单位
                base_ccy：交易货币
                quote_ccy：计价货币
            ban_amend: 是否禁止币种自动借币，默认false
            tp_trigger_px: 止盈触发价
            tp_trigger_px_type: 止盈触发价类型
                last：最新价格
                index：指数价格
                mark：标记价格
            tp_ord_px: 止盈委托价
            sl_trigger_px: 止损触发价
            sl_trigger_px_type: 止损触发价类型
                last：最新价格
                index：指数价格
                mark：标记价格
            sl_ord_px: 止损委托价
            tp_trigger_px_sl_trigger_px: 止盈止损触发价
            tp_trigger_px_sl_trigger_px_type: 止盈止损触发价类型
                last：最新价格
                index：指数价格
                mark：标记价格
                
        Returns:
            Dict: 下单结果，包含订单ID等信息
        """
        path = "/trade/order"
        data = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz
        }
        
        # 添加可选参数
        if px:
            data["px"] = px
        if ccy:
            data["ccy"] = ccy
        if cl_ord_id:
            data["clOrdId"] = cl_ord_id
        if tag:
            data["tag"] = tag
        if pos_side:
            data["posSide"] = pos_side
        if reduce_only is not None:
            data["reduceOnly"] = str(reduce_only).lower()
        if tgt_ccy:
            data["tgtCcy"] = tgt_ccy
        if ban_amend is not None:
            data["banAmend"] = str(ban_amend).lower()
        if tp_trigger_px:
            data["tpTriggerPx"] = tp_trigger_px
        if tp_trigger_px_type:
            data["tpTriggerPxType"] = tp_trigger_px_type
        if tp_ord_px:
            data["tpOrdPx"] = tp_ord_px
        if sl_trigger_px:
            data["slTriggerPx"] = sl_trigger_px
        if sl_trigger_px_type:
            data["slTriggerPxType"] = sl_trigger_px_type
        if sl_ord_px:
            data["slOrdPx"] = sl_ord_px
        if tp_trigger_px_sl_trigger_px:
            data["tpTriggerPxSlTriggerPx"] = tp_trigger_px_sl_trigger_px
        if tp_trigger_px_sl_trigger_px_type:
            data["tpTriggerPxSlTriggerPxType"] = tp_trigger_px_sl_trigger_px_type

        try:
            response = await self._request("POST", path, data=data)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"下单失败: {str(e)}")

    async def place_multiple_orders(self, orders: List[Dict]) -> List[Dict]:
        """批量下单
        
        Args:
            orders: 订单列表，每个订单包含place_order方法的所有参数
            
        Returns:
            List[Dict]: 批量下单结果列表
        """
        path = "/trade/batch-orders"
        data = {"orders": orders}

        try:
            response = await self._request("POST", path, data=data)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"批量下单失败: {str(e)}")

    async def cancel_order(self, inst_id: str, ord_id: str = None, cl_ord_id: str = None) -> Dict:
        """撤销订单
        
        Args:
            inst_id: 产品ID，如 BTC-USDT-SWAP
            ord_id: 订单ID，ord_id和cl_ord_id必须传一个
            cl_ord_id: 客户自定义订单ID，ord_id和cl_ord_id必须传一个
            
        Returns:
            Dict: 撤单结果
        """
        path = "/trade/cancel-order"
        data = {"instId": inst_id}
        
        if ord_id:
            data["ordId"] = ord_id
        elif cl_ord_id:
            data["clOrdId"] = cl_ord_id
        else:
            raise ValueError("ord_id和cl_ord_id必须传一个")

        try:
            response = await self._request("POST", path, data=data)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"撤销订单失败: {str(e)}")

    async def cancel_multiple_orders(self, orders: List[Dict]) -> List[Dict]:
        """批量撤销订单
        
        Args:
            orders: 订单列表，每个订单包含inst_id和ord_id或cl_ord_id
            
        Returns:
            List[Dict]: 批量撤单结果列表
        """
        path = "/trade/cancel-batch-orders"
        data = {"orders": orders}

        try:
            response = await self._request("POST", path, data=data)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"批量撤销订单失败: {str(e)}")

    async def get_order(self, inst_id: str, ord_id: str = None, cl_ord_id: str = None) -> Dict:
        """获取订单信息
        
        Args:
            inst_id: 产品ID，如 BTC-USDT-SWAP
            ord_id: 订单ID，ord_id和cl_ord_id必须传一个
            cl_ord_id: 客户自定义订单ID，ord_id和cl_ord_id必须传一个
            
        Returns:
            Dict: 订单信息
        """
        path = "/trade/order"
        params = {"instId": inst_id}
        
        if ord_id:
            params["ordId"] = ord_id
        elif cl_ord_id:
            params["clOrdId"] = cl_ord_id
        else:
            raise ValueError("ord_id和cl_ord_id必须传一个")

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"获取订单信息失败: {str(e)}")

    async def get_orders_pending(self, inst_type: str = None, uly: str = None, 
                                inst_id: str = None, ord_type: str = None,
                                state: str = None, after: str = None, before: str = None,
                                limit: int = 100) -> List[Dict]:
        """获取未成交订单列表
        
        Args:
            inst_type: 产品类型
                SPOT：币币
                MARGIN：币币杠杆
                SWAP：永续合约
                FUTURES：交割合约
                OPTION：期权
            uly: 标的指数，如 BTC-USD
            inst_id: 产品ID，如 BTC-USDT-SWAP
            ord_type: 订单类型
                market：市价单
                limit：限价单
                post_only：只做maker单
                fok：全部成交或立即取消
                ioc：立即成交并取消剩余
            state: 订单状态
                live：等待成交
                partially_filled：部分成交
            after: 请求此ID之后（更新的数据）的分页内容
            before: 请求此ID之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 未成交订单列表
        """
        path = "/trade/orders-pending"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly
        if inst_id:
            params["instId"] = inst_id
        if ord_type:
            params["ordType"] = ord_type
        if state:
            params["state"] = state
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取未成交订单列表失败: {str(e)}")

    async def get_orders_history(self, inst_type: str = None, uly: str = None,
                                inst_id: str = None, ord_type: str = None,
                                state: str = None, category: str = None,
                                after: str = None, before: str = None,
                                limit: int = 100) -> List[Dict]:
        """获取历史订单记录
        
        Args:
            inst_type: 产品类型
            uly: 标的指数
            inst_id: 产品ID
            ord_type: 订单类型
            state: 订单状态
                filled：完全成交
                canceled：已撤销
                partially_filled：部分成交
            category: 订单种类
                normal：普通委托
                twap：TWAP委托
                adl：ADL自动减仓
                full_liquidation：完全减仓
                partial_liquidation：部分减仓
                delivery：交割
                ddh：对冲
            after: 请求此ID之后（更新的数据）的分页内容
            before: 请求此ID之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 历史订单记录列表
        """
        path = "/trade/orders-history"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly
        if inst_id:
            params["instId"] = inst_id
        if ord_type:
            params["ordType"] = ord_type
        if state:
            params["state"] = state
        if category:
            params["category"] = category
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取历史订单记录失败: {str(e)}")

    async def get_orders_history_archive(self, inst_type: str = None, uly: str = None,
                                       inst_id: str = None, ord_type: str = None,
                                       state: str = None, category: str = None,
                                       after: str = None, before: str = None,
                                       limit: int = 100) -> List[Dict]:
        """获取历史订单记录（近3个月）
        
        Args:
            inst_type: 产品类型
            uly: 标的指数
            inst_id: 产品ID
            ord_type: 订单类型
            state: 订单状态
            category: 订单种类
            after: 请求此ID之后（更新的数据）的分页内容
            before: 请求此ID之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 历史订单记录列表（近3个月）
        """
        path = "/trade/orders-history-archive"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly
        if inst_id:
            params["instId"] = inst_id
        if ord_type:
            params["ordType"] = ord_type
        if state:
            params["state"] = state
        if category:
            params["category"] = category
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取历史订单记录（近3个月）失败: {str(e)}")

    async def get_fills(self, inst_type: str = None, uly: str = None, inst_id: str = None,
                       ord_id: str = None, after: str = None, before: str = None,
                       limit: int = 100) -> List[Dict]:
        """获取成交明细
        
        Args:
            inst_type: 产品类型
            uly: 标的指数
            inst_id: 产品ID
            ord_id: 订单ID
            after: 请求此ID之后（更新的数据）的分页内容
            before: 请求此ID之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 成交明细列表
        """
        path = "/trade/fills"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly
        if inst_id:
            params["instId"] = inst_id
        if ord_id:
            params["ordId"] = ord_id
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取成交明细失败: {str(e)}")

    async def get_fills_history(self, inst_type: str = None, uly: str = None, inst_id: str = None,
                               ord_id: str = None, after: str = None, before: str = None,
                               limit: int = 100) -> List[Dict]:
        """获取历史成交明细（近3个月）
        
        Args:
            inst_type: 产品类型
            uly: 标的指数
            inst_id: 产品ID
            ord_id: 订单ID
            after: 请求此ID之后（更新的数据）的分页内容
            before: 请求此ID之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 历史成交明细列表（近3个月）
        """
        path = "/trade/fills-history"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly
        if inst_id:
            params["instId"] = inst_id
        if ord_id:
            params["ordId"] = ord_id
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取历史成交明细失败: {str(e)}")

    # ==================== 杠杆设置API ====================
    
    async def set_leverage(self, inst_id: str, lever: str, mgn_mode: str, 
                          pos_side: str = None, ccy: str = None) -> Dict:
        """设置杠杆倍数
        
        Args:
            inst_id: 产品ID，如 BTC-USDT-SWAP
            lever: 杠杆倍数，如 "10"
            mgn_mode: 保证金模式
                cross：全仓
                isolated：逐仓
            pos_side: 持仓方向
                long：多头
                short：空头
                net：净持仓
            ccy: 保证金币种，仅适用于单币种保证金模式下的全仓杠杆订单
            
        Returns:
            Dict: 设置结果
        """
        path = "/account/set-leverage"
        data = {
            "instId": inst_id,
            "lever": lever,
            "mgnMode": mgn_mode
        }
        
        if pos_side:
            data["posSide"] = pos_side
        if ccy:
            data["ccy"] = ccy

        try:
            response = await self._request("POST", path, data=data)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"设置杠杆倍数失败: {str(e)}")

    async def get_leverage(self, inst_id: str, mgn_mode: str) -> Dict:
        """获取杠杆倍数
        
        Args:
            inst_id: 产品ID，如 BTC-USDT-SWAP
            mgn_mode: 保证金模式
                cross：全仓
                isolated：逐仓
                
        Returns:
            Dict: 杠杆倍数信息
        """
        path = "/account/leverage"
        params = {
            "instId": inst_id,
            "mgnMode": mgn_mode
        }

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"获取杠杆倍数失败: {str(e)}")

    # ==================== 止盈止损API ====================
    
    async def place_algo_order(self, inst_id: str, td_mode: str, side: str, ord_type: str,
                              sz: str, ccy: str = None, pos_side: str = None,
                              reduce_only: bool = None, tp_trigger_px: str = None,
                              tp_trigger_px_type: str = None, tp_ord_px: str = None,
                              sl_trigger_px: str = None, sl_trigger_px_type: str = None,
                              sl_ord_px: str = None, trigger_px: str = None,
                              trigger_px_type: str = None, order_px: str = None,
                              px_side: str = None, px_var: str = None, px_spread: str = None,
                              sz_limit: str = None, px_limit: str = None, time_interval: str = None,
                              tp_trigger_px_sl_trigger_px: str = None,
                              tp_trigger_px_sl_trigger_px_type: str = None) -> Dict:
        """下单（止盈止损、移动止盈、冰山委托、时间加权委托）
        
        Args:
            inst_id: 产品ID，如 BTC-USDT-SWAP
            td_mode: 交易模式
                cash：现金模式
                cross：全仓模式
                isolated：逐仓模式
            side: 订单方向
                buy：买
                sell：卖
            ord_type: 订单类型
                conditional：单向止盈止损
                oco：双向止盈止损
                trigger：移动止盈
                ice：冰山委托
                twap：时间加权委托
            sz: 委托数量
            ccy: 保证金币种
            pos_side: 持仓方向
                long：开多
                short：开空
                net：单向持仓
            reduce_only: 是否只减仓
            tp_trigger_px: 止盈触发价
            tp_trigger_px_type: 止盈触发价类型
            tp_ord_px: 止盈委托价
            sl_trigger_px: 止损触发价
            sl_trigger_px_type: 止损触发价类型
            sl_ord_px: 止损委托价
            trigger_px: 触发价
            trigger_px_type: 触发价类型
            order_px: 委托价格
            px_side: 价格方向
            px_var: 价格偏差
            px_spread: 价差
            sz_limit: 单笔数量上限
            px_limit: 价格上限
            time_interval: 时间间隔
            tp_trigger_px_sl_trigger_px: 止盈止损触发价
            tp_trigger_px_sl_trigger_px_type: 止盈止损触发价类型
            
        Returns:
            Dict: 下单结果
        """
        path = "/trade/order-algo"
        data = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz
        }
        
        # 添加可选参数
        if ccy:
            data["ccy"] = ccy
        if pos_side:
            data["posSide"] = pos_side
        if reduce_only is not None:
            data["reduceOnly"] = str(reduce_only).lower()
        if tp_trigger_px:
            data["tpTriggerPx"] = tp_trigger_px
        if tp_trigger_px_type:
            data["tpTriggerPxType"] = tp_trigger_px_type
        if tp_ord_px:
            data["tpOrdPx"] = tp_ord_px
        if sl_trigger_px:
            data["slTriggerPx"] = sl_trigger_px
        if sl_trigger_px_type:
            data["slTriggerPxType"] = sl_trigger_px_type
        if sl_ord_px:
            data["slOrdPx"] = sl_ord_px
        if trigger_px:
            data["triggerPx"] = trigger_px
        if trigger_px_type:
            data["triggerPxType"] = trigger_px_type
        if order_px:
            data["orderPx"] = order_px
        if px_side:
            data["pxSide"] = px_side
        if px_var:
            data["pxVar"] = px_var
        if px_spread:
            data["pxSpread"] = px_spread
        if sz_limit:
            data["szLimit"] = sz_limit
        if px_limit:
            data["pxLimit"] = px_limit
        if time_interval:
            data["timeInterval"] = time_interval
        if tp_trigger_px_sl_trigger_px:
            data["tpTriggerPxSlTriggerPx"] = tp_trigger_px_sl_trigger_px
        if tp_trigger_px_sl_trigger_px_type:
            data["tpTriggerPxSlTriggerPxType"] = tp_trigger_px_sl_trigger_px_type

        try:
            response = await self._request("POST", path, data=data)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"下止盈止损单失败: {str(e)}")

    async def cancel_algo_order(self, inst_id: str, algo_id: str = None, 
                               cl_ord_id: str = None) -> Dict:
        """撤销策略委托订单
        
        Args:
            inst_id: 产品ID，如 BTC-USDT-SWAP
            algo_id: 策略委托订单ID，algo_id和cl_ord_id必须传一个
            cl_ord_id: 客户自定义订单ID，algo_id和cl_ord_id必须传一个
            
        Returns:
            Dict: 撤单结果
        """
        path = "/trade/cancel-algos"
        data = {"instId": inst_id}
        
        if algo_id:
            data["algoId"] = algo_id
        elif cl_ord_id:
            data["clOrdId"] = cl_ord_id
        else:
            raise ValueError("algo_id和cl_ord_id必须传一个")

        try:
            response = await self._request("POST", path, data=data)
            return response.get("data", [{}])[0]
        except Exception as e:
            raise Exception(f"撤销策略委托订单失败: {str(e)}")

    async def get_algo_orders_pending(self, inst_type: str = None, uly: str = None,
                                     inst_id: str = None, ord_type: str = None,
                                     state: str = None, after: str = None, before: str = None,
                                     limit: int = 100) -> List[Dict]:
        """获取未成交策略委托单列表
        
        Args:
            inst_type: 产品类型
            uly: 标的指数
            inst_id: 产品ID
            ord_type: 订单类型
            state: 订单状态
                live：等待触发
                effective：已生效
                canceled：已撤销
                order_failed：委托失败
            after: 请求此ID之后（更新的数据）的分页内容
            before: 请求此ID之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 未成交策略委托单列表
        """
        path = "/trade/orders-algo-pending"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly
        if inst_id:
            params["instId"] = inst_id
        if ord_type:
            params["ordType"] = ord_type
        if state:
            params["state"] = state
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取未成交策略委托单列表失败: {str(e)}")

    async def get_algo_orders_history(self, inst_type: str = None, uly: str = None,
                                     inst_id: str = None, ord_type: str = None,
                                     state: str = None, after: str = None, before: str = None,
                                     limit: int = 100) -> List[Dict]:
        """获取历史策略委托单列表
        
        Args:
            inst_type: 产品类型
            uly: 标的指数
            inst_id: 产品ID
            ord_type: 订单类型
            state: 订单状态
            after: 请求此ID之后（更新的数据）的分页内容
            before: 请求此ID之前（更旧的数据）的分页内容
            limit: 分页返回的结果集数量，最大为100，默认100条
            
        Returns:
            List[Dict]: 历史策略委托单列表
        """
        path = "/trade/orders-algo-history"
        params = {}
        
        if inst_type:
            params["instType"] = inst_type
        if uly:
            params["uly"] = uly
        if inst_id:
            params["instId"] = inst_id
        if ord_type:
            params["ordType"] = ord_type
        if state:
            params["state"] = state
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if limit:
            params["limit"] = str(limit)

        try:
            response = await self._request("GET", path, params=params)
            return response.get("data", [])
        except Exception as e:
            raise Exception(f"获取历史策略委托单列表失败: {str(e)}")

