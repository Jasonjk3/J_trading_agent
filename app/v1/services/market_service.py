#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/03/10
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
市场数据服务层
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import os
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from lib.okx.okx_market_service import OkxMarketService
from lib.okx.symbol_utils import normalize_okx_symbol
from app.v1.crud import favorite_symbol_crud


class MarketService:
    """市场数据服务类"""

    def __init__(self):
        self._market_service: Optional[OkxMarketService] = None

    def _get_market_service(self) -> OkxMarketService:
        """获取市场服务实例（延迟初始化）"""
        if self._market_service is None:
            api_key = os.getenv("OKX_API_KEY")
            secret_key = os.getenv("OKX_SECRET_KEY")
            passphrase = os.getenv("OKX_PASSPHRASE")
            is_sandbox = os.getenv("OKX_IS_SANDBOX", "false").lower() == "true"
            proxy = os.getenv("OKX_PROXY")
            
            self._market_service = OkxMarketService(
                api_key=api_key,
                secret_key=secret_key,
                passphrase=passphrase,
                is_sandbox=is_sandbox,
                proxy=proxy
            )
        return self._market_service

    async def search_symbols(self, keyword: Optional[str] = None) -> List[Dict]:
        """搜索交易对
        
        Args:
            keyword: 搜索关键词，如 BTC
            
        Returns:
            List[Dict]: 交易对列表
        """
        try:
            market_service = self._get_market_service()
            symbols = await market_service.get_supported_symbols()
            
            result = []
            for item in symbols:
                inst_id = item.get("instId", "")
                base_ccy = item.get("baseCcy", "")
                quote_ccy = item.get("quoteCcy", "")
                
                if keyword:
                    keyword_upper = keyword.upper()
                    if keyword_upper not in inst_id.upper():
                        continue
                
                result.append({
                    "symbol": inst_id,
                    "baseAsset": base_ccy,
                    "quoteAsset": quote_ccy
                })
            
            return result
        except Exception as e:
            logger.error(f"搜索交易对失败: {e}")
            raise

    async def get_kline(
        self, 
        symbol: str, 
        interval: str, 
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> List[Dict]:
        """获取K线数据
        
        Args:
            symbol: 交易对，如 BTC-USDT (OKX格式) 或 BTCUSDT (前端格式)
            interval: 时间周期，如 15m, 1h, 4h, 1d
            limit: 获取数量
            session: 数据库会话；传入时优先读 MySQL 缓存，不足再补拉
            
        Returns:
            List[Dict]: K线数据列表
        """
        try:
            okx_symbol = self._convert_symbol_to_okx(symbol)
            db_interval = interval.lower()

            if session is not None:
                cached = await self._get_kline_from_cache(
                    session, okx_symbol, db_interval, limit
                )
                if cached:
                    logger.debug(
                        f"K线大盘缓存命中: {okx_symbol} {db_interval} bars={len(cached)}"
                    )
                    return cached

            okx_interval = self._convert_interval_to_okx(interval)
            market_service = self._get_market_service()
            kline_data = await market_service.get_candlesticks(
                inst_id=okx_symbol,
                bar=okx_interval,
                limit=limit
            )
            
            result = []
            for item in kline_data:
                if len(item) >= 6:
                    result.append({
                        "time": item[0],
                        "open": item[1],
                        "high": item[2],
                        "low": item[3],
                        "close": item[4],
                        "volume": item[5]
                    })
            
            result.reverse()
            return result
        except Exception as e:
            logger.error(f"获取K线数据失败: {symbol}, {e}")
            raise

    async def _get_kline_from_cache(
        self,
        session: AsyncSession,
        symbol: str,
        db_interval: str,
        limit: int,
    ) -> List[Dict]:
        """从 historical_klines 读取 K 线，不足时增量补拉。"""
        from backtest.kline_fetcher import KlineFetcher, ensure_and_get_klines

        interval_seconds = KlineFetcher.INTERVAL_SECONDS.get(db_interval, 900)
        end_time = datetime.now()
        start_time = end_time - timedelta(seconds=interval_seconds * max(limit, 1))

        rows = await ensure_and_get_klines(
            session,
            exchange="okx",
            symbol=symbol,
            interval=db_interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        if len(rows) < min(limit, 5):
            return []

        result = []
        for row in rows[-limit:]:
            ts_ms = str(int(row.timestamp.timestamp() * 1000))
            result.append({
                "time": ts_ms,
                "open": str(row.open_price),
                "high": str(row.high_price),
                "low": str(row.low_price),
                "close": str(row.close_price),
                "volume": str(row.volume),
            })
        return result

    async def get_indicators(
        self,
        symbol: str,
        interval: str,
        session: Optional[AsyncSession] = None,
    ) -> Dict:
        """获取市场指标数据
        
        Args:
            symbol: 交易对
            interval: 时间周期
            session: 数据库会话；传入时 K 线优先读 MySQL 缓存（ticker 仍走交易所）
            
        Returns:
            Dict: 市场指标数据
        """
        try:
            okx_symbol = self._convert_symbol_to_okx(symbol)
            okx_interval = self._convert_interval_to_okx(interval)
            market_service = self._get_market_service()

            ticker = await market_service.get_ticker(okx_symbol)

            closes: List[Decimal] = []
            bars_through = None
            if session is not None:
                cached_klines = await self._get_kline_from_cache(
                    session, okx_symbol, interval.lower(), limit=50
                )
                if cached_klines:
                    bars_through = cached_klines[-1].get("time")
                for item in cached_klines:
                    try:
                        closes.append(Decimal(item["close"]))
                    except Exception:
                        pass

            if not closes:
                kline_data = await market_service.get_candlesticks(
                    inst_id=okx_symbol,
                    bar=okx_interval,
                    limit=50,
                )
                if kline_data:
                    bars_through = kline_data[0][0]
                for item in kline_data:
                    if len(item) >= 5:
                        try:
                            closes.append(Decimal(item[4]))
                        except Exception:
                            pass
                closes.reverse()

            latest_price = ticker.get("last", "0")
            open_24h = ticker.get("open24h", "0")
            high_24h = ticker.get("high24h", "0")
            low_24h = ticker.get("low24h", "0")
            vol_24h = ticker.get("volCcy24h", "0")
            
            try:
                last_val = Decimal(latest_price)
                open_val = Decimal(open_24h) if open_24h and open_24h != "0" else Decimal("1")
                change_24h = ((last_val - open_val) / open_val * 100).quantize(Decimal("0.01"))
            except Exception:
                change_24h = Decimal("0")
            
            ma5 = self._calculate_ma(closes, 5)
            ma10 = self._calculate_ma(closes, 10)
            ma20 = self._calculate_ma(closes, 20)
            rsi14 = self._calculate_rsi(closes, 14)
            macd, signal, histogram = self._calculate_macd(closes)
            volatility = self._calculate_volatility(closes)
            recommendation = self._get_recommendation(
                latest_price=Decimal(latest_price) if latest_price else Decimal("0"),
                ma5=ma5,
                ma20=ma20,
                rsi14=rsi14
            )
            
            return {
                "symbol": symbol,
                "interval": interval,
                "latestPrice": latest_price,
                "marketTime": ticker.get("ts"),
                "indicatorBarCount": len(closes),
                "indicatorBarsThrough": bars_through,
                "complete": len(closes) >= 26 and bool(ticker.get("ts")),
                "warnings": [] if len(closes) >= 26 else ["K线不足26根，部分指标不可可靠计算"],
                "change24h": str(change_24h),
                "high24h": high_24h,
                "low24h": low_24h,
                "volume24h": vol_24h,
                "ma5": str(ma5),
                "ma10": str(ma10),
                "ma20": str(ma20),
                "rsi14": str(rsi14),
                "macd": str(macd),
                "signal": str(signal),
                "histogram": str(histogram),
                "volatility": str(volatility),
                "recommendation": recommendation
            }
        except Exception as e:
            logger.error(f"获取市场指标失败: {symbol}, {e}")
            raise

    def _convert_symbol_to_okx(self, symbol: str) -> str:
        """转换交易对格式为OKX格式（与 ``lib.okx.symbol_utils.normalize_okx_symbol`` 一致）"""
        return normalize_okx_symbol(symbol)

    def _convert_interval_to_okx(self, interval: str) -> str:
        """转换时间周期格式为OKX格式
        
        前端格式: 15m, 1h, 4h, 1d
        OKX格式: 15m, 1H, 4H, 1D
        """
        interval_map = {
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D"
        }
        return interval_map.get(interval.lower(), interval)

    def _calculate_ma(self, closes: List[Decimal], period: int) -> Decimal:
        """计算移动平均线"""
        if len(closes) < period:
            return Decimal("0")
        
        recent = closes[-period:]
        return (sum(recent) / period).quantize(Decimal("0.01"))

    def _calculate_rsi(self, closes: List[Decimal], period: int = 14) -> Decimal:
        """计算RSI指标"""
        if len(closes) < period + 1:
            return Decimal("50")
        
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(Decimal("0"))
            else:
                gains.append(Decimal("0"))
                losses.append(abs(change))
        
        if len(gains) < period:
            return Decimal("50")
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return Decimal("100")
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return Decimal(str(rsi)).quantize(Decimal("0.01"))

    def _calculate_macd(
        self, 
        closes: List[Decimal], 
        fast: int = 12, 
        slow: int = 26, 
        signal_period: int = 9
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """计算MACD指标"""
        if len(closes) < slow:
            return Decimal("0"), Decimal("0"), Decimal("0")
        
        ema_fast = self._calculate_ema(closes, fast)
        ema_slow = self._calculate_ema(closes, slow)
        
        macd = ema_fast - ema_slow
        
        signal = macd * Decimal("0.2")
        histogram = macd - signal
        
        return (
            macd.quantize(Decimal("0.01")),
            signal.quantize(Decimal("0.01")),
            histogram.quantize(Decimal("0.01"))
        )

    def _calculate_ema(self, closes: List[Decimal], period: int) -> Decimal:
        """计算指数移动平均线"""
        if len(closes) < period:
            return Decimal("0")
        
        multiplier = Decimal(2) / (period + 1)
        ema = sum(closes[:period]) / period
        
        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema

    def _calculate_volatility(self, closes: List[Decimal], period: int = 20) -> Decimal:
        """计算波动率"""
        if len(closes) < period:
            return Decimal("0")
        
        recent = closes[-period:]
        mean = sum(recent) / len(recent)
        
        if mean == 0:
            return Decimal("0")
        
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std_dev = variance.sqrt() if hasattr(variance, 'sqrt') else Decimal(str(float(variance) ** 0.5))
        
        volatility = (std_dev / mean * 100)
        
        return volatility.quantize(Decimal("0.01"))

    def _get_recommendation(
        self,
        latest_price: Decimal,
        ma5: Decimal,
        ma20: Decimal,
        rsi14: Decimal
    ) -> str:
        """获取交易建议
        
        基于简单的技术指标分析
        """
        bullish_signals = 0
        bearish_signals = 0
        
        if latest_price > ma5 > 0:
            bullish_signals += 1
        elif latest_price < ma5 > 0:
            bearish_signals += 1
        
        if ma5 > ma20 > 0:
            bullish_signals += 1
        elif ma5 < ma20 > 0:
            bearish_signals += 1
        
        if rsi14 < 30:
            bullish_signals += 1
        elif rsi14 > 70:
            bearish_signals += 1
        
        if bullish_signals > bearish_signals:
            return "bullish"
        elif bearish_signals > bullish_signals:
            return "bearish"
        else:
            return "neutral"

    # ==================== 自选交易对相关 ====================

    async def get_favorite_symbols(
        self,
        session: AsyncSession,
        user_id: str
    ) -> List[Dict]:
        """获取用户自选交易对列表"""
        try:
            favorites = await favorite_symbol_crud.get_user_favorites(session, user_id)
            return [item.to_dict() for item in favorites]
        except Exception as e:
            logger.error(f"获取自选列表失败: {e}")
            raise

    async def add_favorite_symbol(
        self,
        session: AsyncSession,
        user_id: str,
        symbol: str,
        name: Optional[str] = None
    ) -> Dict:
        """添加自选交易对"""
        try:
            # 检查是否已存在
            exists = await favorite_symbol_crud.is_favorite(session, user_id, symbol)
            if exists:
                raise ValueError(f"交易对 {symbol} 已在自选列表中")
            
            # 检查数量限制（最多20个）
            count = await favorite_symbol_crud.get_favorites_count(session, user_id)
            if count >= 20:
                raise ValueError("自选数量已达上限（20个）")
            
            favorite = await favorite_symbol_crud.add_favorite(
                session, user_id, symbol, name
            )
            return favorite.to_dict()
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"添加自选失败: {e}")
            raise

    async def remove_favorite_symbol(
        self,
        session: AsyncSession,
        user_id: str,
        symbol: str
    ) -> bool:
        """移除自选交易对"""
        try:
            result = await favorite_symbol_crud.remove_favorite(session, user_id, symbol)
            if not result:
                raise ValueError(f"交易对 {symbol} 不在自选列表中")
            return True
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"移除自选失败: {e}")
            raise

    async def is_symbol_favorite(
        self,
        session: AsyncSession,
        user_id: str,
        symbol: str
    ) -> bool:
        """判断交易对是否已自选"""
        try:
            return await favorite_symbol_crud.is_favorite(session, user_id, symbol)
        except Exception as e:
            logger.error(f"判断自选状态失败: {e}")
            return False

    async def update_favorite_sort(
        self,
        session: AsyncSession,
        user_id: str,
        items: List[dict]
    ) -> bool:
        """更新自选排序"""
        try:
            return await favorite_symbol_crud.update_sort_order(session, user_id, items)
        except Exception as e:
            logger.error(f"更新自选排序失败: {e}")
            raise
