#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
K线数据获取器
用于从交易所获取历史K线数据并存储到数据库
"""
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from models.inner_models.backtest_model import HistoricalKlineModel
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession

from lib.okx.symbol_utils import normalize_okx_symbol
from app.v1.crud.backtest_crud import (
    get_klines,
    batch_create_klines,
    count_klines,
    get_latest_kline,
    get_earliest_kline,
)


def okx_timeframe_to_db_interval(okx_bar: str) -> str:
    """
    OKX bar（如 4H、1m、1M）转为库表 historical_klines.interval 使用的键。
    与回测 KlineInterval（1h、4h）一致；月线保留 1M，避免与 1 分钟 1m 混淆。
    """
    if okx_bar == "1M":
        return "1M"
    return okx_bar.lower()


def _normalize_db_symbol(symbol: str) -> str:
    """统一库内 symbol 键，避免 BTCUSDT / BTC-USDT 缓存穿透。"""
    return normalize_okx_symbol(symbol)


class KlineFetcher:
    """K线数据获取器"""
    
    # DB interval -> OKX bar（与技术分析 TIMEFRAME 对齐）
    INTERVAL_MAP = {
        '1m': '1m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1h': '1H',
        '2h': '2H',
        '4h': '4H',
        '6h': '6H',
        '12h': '12H',
        '1d': '1D',
        '1w': '1W',
        '1M': '1M',
    }
    
    # 每根K线的秒数（1M 按 30 天近似，仅用于覆盖率估算）
    INTERVAL_SECONDS = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '30m': 1800,
        '1h': 3600,
        '2h': 7200,
        '4h': 14400,
        '6h': 21600,
        '12h': 43200,
        '1d': 86400,
        '1w': 604800,
        '1M': 2592000,
    }

    CACHE_COVERAGE_RATIO = 0.95
    
    def __init__(self, exchange: str = 'okx'):
        self.exchange = exchange
        self._market_service = None
    
    async def _get_market_service(self):
        """获取交易所市场服务（懒加载）"""
        if self._market_service is None:
            try:
                from lib.okx.okx_market_service import OkxMarketService
                self._market_service = OkxMarketService()
            except Exception as e:
                logger.warning(f"无法初始化 OKX 市场服务: {e}")
                return None
        return self._market_service

    def _interval_seconds(self, interval: str) -> int:
        return self.INTERVAL_SECONDS.get(interval, 900)

    def _is_cache_sufficient(
        self,
        existing_count: int,
        expected_count: int,
        latest_ts: Optional[datetime],
        end_time: datetime,
        interval_seconds: int,
    ) -> bool:
        if expected_count <= 0:
            return existing_count > 0
        if existing_count < int(expected_count * self.CACHE_COVERAGE_RATIO):
            return False
        if latest_ts is None:
            return False
        freshness_cutoff = end_time - timedelta(seconds=interval_seconds)
        return latest_ts >= freshness_cutoff

    def _plan_fetch_segments(
        self,
        start_time: datetime,
        end_time: datetime,
        interval_seconds: int,
        existing_count: int,
        expected_count: int,
        latest: Optional["HistoricalKlineModel"],
        earliest: Optional["HistoricalKlineModel"],
    ) -> List[Tuple[datetime, datetime]]:
        """规划需从交易所补拉的区间（尾部增量 + 头部回填）。"""
        if self._is_cache_sufficient(
            existing_count, expected_count,
            latest.timestamp if latest else None,
            end_time, interval_seconds,
        ):
            return []

        segments: List[Tuple[datetime, datetime]] = []
        bar_delta = timedelta(seconds=interval_seconds)

        if latest and latest.timestamp >= start_time:
            tail_start = latest.timestamp
            if tail_start < end_time - bar_delta:
                segments.append((tail_start, end_time))
        else:
            segments.append((start_time, end_time))
            return segments

        if earliest and earliest.timestamp > start_time + bar_delta:
            head_end = earliest.timestamp
            if head_end > start_time:
                segments.insert(0, (start_time, head_end))

        if not segments:
            segments.append((start_time, end_time))
        return segments
    
    async def fetch_and_store_klines(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> int:
        """
        获取并存储K线数据（有缓存时跳过 API；不足时按缺口增量补拉）。
        
        Args:
            session: 数据库会话
            symbol: 交易对，如 "BTCUSDT" 或 "BTC-USDT"
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            int: 新增的K线数量
        """
        symbol = _normalize_db_symbol(symbol)
        interval_seconds = self._interval_seconds(interval)
        expected_count = max(1, int((end_time - start_time).total_seconds() / interval_seconds))

        existing_count = await count_klines(
            session, self.exchange, symbol, interval, start_time, end_time
        )
        latest = await get_latest_kline(session, self.exchange, symbol, interval)
        earliest = await get_earliest_kline(
            session, self.exchange, symbol, interval, start_time, end_time
        )

        segments = self._plan_fetch_segments(
            start_time, end_time, interval_seconds,
            existing_count, expected_count, latest, earliest,
        )
        if not segments:
            logger.info(
                f"K线缓存命中: {symbol} {interval} "
                f"{existing_count}/{expected_count}, latest={getattr(latest, 'timestamp', None)}"
            )
            return 0

        market_service = await self._get_market_service()
        if not market_service:
            logger.warning("无法获取交易所服务，跳过数据获取")
            return 0

        okx_symbol = symbol
        okx_interval = self.INTERVAL_MAP.get(interval, '15m')
        total_saved = 0

        for seg_start, seg_end in segments:
            logger.info(
                f"K线增量补拉: {okx_symbol} {okx_interval} "
                f"[{seg_start.isoformat()} ~ {seg_end.isoformat()}]"
            )
            saved = await self._fetch_segment_from_exchange(
                session, market_service, symbol, okx_symbol, okx_interval,
                interval, seg_start, seg_end,
            )
            total_saved += saved

        return total_saved

    async def _fetch_segment_from_exchange(
        self,
        session: AsyncSession,
        market_service,
        db_symbol: str,
        okx_symbol: str,
        okx_interval: str,
        db_interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """从交易所分页拉取一个时间区间并写入库。"""
        all_klines: List[Dict] = []
        current_end = end_time

        try:
            while current_end > start_time:
                after_ts = str(int(current_end.timestamp() * 1000))

                klines = await market_service.get_candlesticks(
                    inst_id=okx_symbol,
                    bar=okx_interval,
                    after=after_ts,
                    limit=300,
                )

                if not klines:
                    break

                batch_oldest_ts = min(int(k[0]) for k in klines)
                for kline in klines:
                    ts = datetime.fromtimestamp(int(kline[0]) / 1000)
                    if ts < start_time:
                        continue
                    all_klines.append({
                        'exchange': self.exchange,
                        'symbol': db_symbol,
                        'interval': db_interval,
                        'timestamp': ts,
                        'open_price': Decimal(kline[1]),
                        'high_price': Decimal(kline[2]),
                        'low_price': Decimal(kline[3]),
                        'close_price': Decimal(kline[4]),
                        'volume': Decimal(kline[5]),
                        'quote_volume': Decimal(kline[6]) if len(kline) > 6 else None,
                    })

                if batch_oldest_ts <= int(start_time.timestamp() * 1000):
                    break

                current_end = datetime.fromtimestamp(batch_oldest_ts / 1000)
                await asyncio.sleep(0.2)

            if all_klines:
                count = await batch_create_klines(session, all_klines)
                await session.commit()
                logger.info(f"保存 {db_symbol} K线数据: {count} 条")
                return count
            return 0

        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            return 0


async def ensure_and_get_klines(
    session: AsyncSession,
    exchange: str,
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
    limit: int = 10000,
) -> List["HistoricalKlineModel"]:
    """
    缓存旁路：先按区间补全库内数据（不足则从交易所增量拉取并 INSERT IGNORE），再返回查询结果。
    """
    symbol = _normalize_db_symbol(symbol)
    fetcher = KlineFetcher(exchange)
    await fetcher.fetch_and_store_klines(
        session, symbol, interval, start_time, end_time
    )
    return await get_klines(
        session,
        exchange,
        symbol,
        interval,
        start_time,
        end_time,
        limit=limit,
    )


async def ensure_kline_data(
    session: AsyncSession,
    exchange: str,
    symbols: List[str],
    interval: str,
    start_time: datetime,
    end_time: datetime
) -> Dict[str, int]:
    """
    确保K线数据存在，如果不存在则从交易所获取
    
    Args:
        session: 数据库会话
        exchange: 交易所
        symbols: 交易对列表
        interval: K线周期
        start_time: 开始时间
        end_time: 结束时间
        
    Returns:
        Dict[str, int]: 每个交易对获取的数据数量
    """
    fetcher = KlineFetcher(exchange)
    result = {}
    
    for symbol in symbols:
        norm_symbol = _normalize_db_symbol(symbol)
        count = await fetcher.fetch_and_store_klines(
            session, norm_symbol, interval, start_time, end_time
        )
        result[symbol] = count
    
    return result
