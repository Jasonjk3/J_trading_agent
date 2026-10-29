#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标分析 Agent
输入交易对和日期，输出技术指标分析报告
"""
import json
import asyncio
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from loguru import logger

from core.agent_base.task_base_agent import TaskBaseAgent
from core.agent_mixin.task_agent_mixin import TaskAgentMixin
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_factory import LLMFactory
from backtest.indicators import macd as calc_consistent_macd
from lib.okx.symbol_utils import normalize_okx_symbol


class TechnicalAnalysisAgent(TaskAgentMixin, TaskBaseAgent):
    """
    技术指标分析 Agent
    
    功能：
    - 获取指定交易对在指定日期前的历史K线数据
    - 计算多种技术指标（MA、MACD、RSI、布林带、斐波那契等）
    - 使用 LLM 生成综合分析报告
    
    输入参数：
    - symbol: 交易对，如 BTC-USDT
    - analysis_date: 分析截止日期，如 2026-03-25
    - timeframe: K线周期，如 1H, 4H, 1D（默认 4H）
    - lookback_days: 回溯天数（默认 30）
    
    输出：
    - 结构化的技术分析报告
    """
    
    AGENT_TYPE = "technical_analysis"
    DEFAULT_CAPABILITIES = [
        "technical_analysis",
        "indicator_calculation",
        "trend_analysis",
    ]
    
    SYSTEM_PROMPT = """你是一位专业的加密货币技术分析师，精通各类技术指标的解读和市场分析。

你的任务是基于提供的技术指标数据，生成一份专业、全面的技术分析报告。

分析要求：
1. 趋势判断：基于均线系统判断当前趋势方向和强度
2. 动量分析：解读 RSI、MACD 等动量指标的信号
3. 波动分析：评估布林带位置和市场波动状态
4. 支撑阻力：识别关键的支撑和阻力价位
5. 信号汇总：列出主要的多空信号
6. 综合建议：给出操作建议和风险提示

输出格式要求（必须返回有效 JSON）：
{
    "summary": "一句话概括当前市场状态",
    "trend": {
        "direction": "bullish" | "bearish" | "neutral",
        "strength": "strong" | "moderate" | "weak",
        "description": "趋势详细描述"
    },
    "momentum": {
        "rsi_status": "overbought" | "oversold" | "neutral",
        "macd_status": "bullish" | "bearish" | "neutral",
        "description": "动量分析描述"
    },
    "volatility": {
        "status": "high" | "medium" | "low",
        "bollinger_position": "upper" | "middle" | "lower",
        "description": "波动性分析描述"
    },
    "support_resistance": {
        "key_support": [支撑位1, 支撑位2],
        "key_resistance": [阻力位1, 阻力位2],
        "fibonacci_levels": "斐波那契位置描述"
    },
    "signals": [
        {"type": "bullish" | "bearish", "indicator": "指标名", "description": "信号描述"}
    ],
    "recommendation": {
        "action": "buy" | "sell" | "hold" | "wait",
        "confidence": 0.0-1.0,
        "entry_zone": "建议入场区间",
        "stop_loss": "建议止损位",
        "take_profit": "建议止盈位",
        "risk_warning": "风险提示"
    }
}

注意事项：
- 分析必须基于数据，不要臆测
- 风险提示要明确、具体
- 如果数据不足，如实说明
- 不要给出过于激进的建议
"""
    
    # 支持的K线周期映射
    TIMEFRAME_MAP = {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1H", "2h": "2H", "4h": "4H", 
        "6h": "6H", "12h": "12H",
        "1d": "1D", "1w": "1W", "1M": "1M"
    }
    
    # 周期对应的分钟数
    TIMEFRAME_MINUTES = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1H": 60, "2H": 120, "4H": 240,
        "6H": 360, "12H": 720,
        "1D": 1440, "1W": 10080, "1M": 43200
    }
    
    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "技术指标分析Agent",
        llm: Optional[BaseLLM] = None,
        market_service=None,
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=self.AGENT_TYPE,
            capabilities=self.DEFAULT_CAPABILITIES,
            llm=llm,
            **kwargs
        )
        
        self._market_service = market_service

        if not self.llm:
            self._init_llm()
    
    def _init_llm(self):
        """初始化 LLM 客户端"""
        try:
            logger.info(
                f"[{self.agent_name}] 进入默认 LLM 初始化路径: "
                "model=deepseek-chat, api_key_env=DEEPSEEK_API_KEY, api_url=default"
            )
            self.llm = LLMFactory.create_llm(
                model_name="deepseek-chat",
                api_key_env="DEEPSEEK_API_KEY",
                temperature=0.3,
                max_tokens=2048
            )
            if self.llm:
                logger.info(
                    f"[{self.agent_name}] LLM 初始化成功: "
                    f"class={self.llm.__class__.__name__}, api_url={getattr(self.llm, 'api_url', None)}"
                )
            else:
                logger.warning(f"[{self.agent_name}] LLM 初始化失败")
        except Exception as e:
            logger.error(f"[{self.agent_name}] 初始化 LLM 失败: {e}")
    
    def _get_market_service(self):
        """获取市场服务（延迟初始化）"""
        if self._market_service is None:
            from lib.okx.okx_market_service import OkxMarketService
            import os
            
            api_key = os.getenv("OKX_API_KEY")
            secret_key = os.getenv("OKX_SECRET_KEY")
            passphrase = os.getenv("OKX_PASSPHRASE")
            is_sandbox = os.getenv("OKX_IS_SANDBOX", "false").lower() == "true"
            proxy = os.getenv("OKX_PROXY")
            
            if not all([api_key, secret_key, passphrase]):
                raise ValueError("OKX API配置不完整，请检查环境变量")
            
            self._market_service = OkxMarketService(
                api_key=api_key,
                secret_key=secret_key,
                passphrase=passphrase,
                is_sandbox=is_sandbox,
                proxy=proxy
            )
        return self._market_service
    
    def _validate_task(self, task: Dict[str, Any]) -> bool:
        """验证任务参数"""
        if not isinstance(task, dict):
            return False
        
        raw = task.get("symbol")
        if not isinstance(raw, str) or not raw.strip():
            logger.error("缺少有效的 symbol 参数")
            return False
        if not normalize_okx_symbol(raw.strip()):
            logger.error("交易对规范化后为空，请检查输入（与大盘走势一致：如 BTCUSDT 或 BTC-USDT）")
            return False
        
        analysis_date = task.get("analysis_date")
        if analysis_date:
            raw_analysis_date = str(analysis_date).strip()
            try:
                if "T" in raw_analysis_date or " " in raw_analysis_date:
                    parsed = datetime.fromisoformat(raw_analysis_date.replace("Z", "+00:00"))
                    if parsed.tzinfo is not None:
                        parsed = parsed.replace(tzinfo=None)
                else:
                    datetime.strptime(raw_analysis_date, "%Y-%m-%d")
            except ValueError:
                logger.error(
                    f"无效的日期格式: {analysis_date}，应为 YYYY-MM-DD 或 ISO 时间格式"
                )
                return False
        
        return True
    
    def _coerce_lookback_days(self, task: Dict[str, Any]) -> int:
        """兼容 lookback_days / lookbackDays，并限制在 7～365。"""
        raw = task.get("lookback_days")
        if raw is None:
            raw = task.get("lookbackDays")
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = 30
        return max(7, min(n, 365))
    
    def _extract_task_params(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """提取任务参数"""
        raw_symbol = task.get("symbol") or ""
        symbol = normalize_okx_symbol(str(raw_symbol).strip())
        
        analysis_date_str = task.get("analysis_date")
        if analysis_date_str:
            raw_analysis_date = str(analysis_date_str).strip()
            if "T" in raw_analysis_date or " " in raw_analysis_date:
                try:
                    analysis_date = datetime.fromisoformat(raw_analysis_date.replace("Z", "+00:00"))
                    if analysis_date.tzinfo is not None:
                        analysis_date = analysis_date.replace(tzinfo=None)
                except ValueError:
                    d = datetime.strptime(raw_analysis_date[:10], "%Y-%m-%d").date()
                    analysis_date = datetime.combine(d, time(23, 59, 59, 999999))
            else:
                # 兼容历史仅传日期的接口：按当日收盘理解
                d = datetime.strptime(raw_analysis_date, "%Y-%m-%d").date()
                analysis_date = datetime.combine(d, time(23, 59, 59, 999999))
        else:
            analysis_date = datetime.now()
        
        timeframe = task.get("timeframe", "4h").lower()
        okx_timeframe = self.TIMEFRAME_MAP.get(timeframe, "4H")
        
        lookback_days = self._coerce_lookback_days(task)

        return {
            "task_id": task.get("task_id", str(uuid4())),
            "symbol": symbol,
            "analysis_date": analysis_date,
            "timeframe": okx_timeframe,
            "lookback_days": lookback_days,
        }
    
    # OKX 单次最多 300 根；向历史翻页用 after（官方：after=早于 ts 的数据）
    _OKX_CANDLE_PAGE_MAX = 300
    _KLINE_FETCH_MAX_PAGES = 40
    
    @staticmethod
    def _coerce_candle_ts_ms(raw: Any) -> int:
        """OKX K 线开盘时间为毫秒；若误为秒级整数则放大到毫秒。"""
        v = int(float(str(raw).strip()))
        if 0 < v < 10**12:
            v *= 1000
        return v
    
    @staticmethod
    def _historical_rows_to_kline_dicts(rows: List[Any]) -> List[Dict]:
        """将 historical_klines ORM 行转为指标计算用的 K 线 dict（与 OKX 分页结果字段一致）。"""
        out: List[Dict] = []
        for k in rows:
            ts_ms = int(k.timestamp.timestamp() * 1000)
            out.append({
                "timestamp": ts_ms,
                "open": float(k.open_price),
                "high": float(k.high_price),
                "low": float(k.low_price),
                "close": float(k.close_price),
                "volume": float(k.volume),
            })
        return out

    async def _fetch_kline_data(
        self,
        symbol: str,
        timeframe: str,
        end_date: datetime,
        lookback_days: int,
        session: Optional[AsyncSession] = None,
        exchange: str = "okx",
    ) -> List[Dict]:
        """获取历史K线：有 DB 会话时先读/补 MySQL 缓存，否则直连交易所分页拉取。"""
        if session is not None:
            from backtest.kline_fetcher import ensure_and_get_klines, okx_timeframe_to_db_interval

            db_interval = okx_timeframe_to_db_interval(timeframe)
            start_date = end_date - timedelta(days=lookback_days)
            rows = await ensure_and_get_klines(
                session,
                exchange,
                symbol,
                db_interval,
                start_date,
                end_date,
            )
            result = self._historical_rows_to_kline_dicts(rows)
            minutes_per_bar = self.TIMEFRAME_MINUTES.get(timeframe, 240)
            if minutes_per_bar <= 0:
                minutes_per_bar = 240
            total_minutes = lookback_days * 24 * 60
            target_bars = max(1, total_minutes // minutes_per_bar)
            if len(result) > target_bars:
                result = result[-target_bars:]
            logger.info(
                f"K线(MySQL缓存): symbol={symbol} bar={timeframe} interval={db_interval} "
                f"lookback_days={lookback_days} got={len(result)}"
            )
            return result

        market_service = self._get_market_service()
        
        end_ts = int(end_date.timestamp() * 1000)
        minutes_per_bar = self.TIMEFRAME_MINUTES.get(timeframe, 240)
        if minutes_per_bar <= 0:
            minutes_per_bar = 240
        total_minutes = lookback_days * 24 * 60
        target_bars = max(1, total_minutes // minutes_per_bar)
        
        by_ts: Dict[int, Dict] = {}
        # OKX: after=早于请求 ts 的 K 线。首包：截止时刻之前的历史；翻页：after=本批最旧开盘时间
        cursor_after = end_ts
        pages = 0
        prev_oldest_ms: Optional[int] = None
        
        try:
            while len(by_ts) < target_bars and pages < self._KLINE_FETCH_MAX_PAGES:
                pages += 1
                batch_limit = min(self._OKX_CANDLE_PAGE_MAX, target_bars - len(by_ts))
                if batch_limit <= 0:
                    break
                kline_data = await market_service.get_candlesticks(
                    inst_id=symbol,
                    bar=timeframe,
                    after=str(cursor_after),
                    limit=batch_limit,
                )
                if not kline_data:
                    break
                batch_prev_count = len(by_ts)
                oldest_ts = min(self._coerce_candle_ts_ms(k[0]) for k in kline_data)
                for item in kline_data:
                    if len(item) >= 6:
                        ts = self._coerce_candle_ts_ms(item[0])
                        by_ts[ts] = {
                            "timestamp": ts,
                            "open": float(item[1]),
                            "high": float(item[2]),
                            "low": float(item[3]),
                            "close": float(item[4]),
                            "volume": float(item[5]),
                        }
                if len(by_ts) == batch_prev_count:
                    break
                if prev_oldest_ms is not None and oldest_ts >= prev_oldest_ms:
                    logger.warning(
                        f"K线分页 oldest 未向过去推进: oldest_ts={oldest_ts} prev_oldest_ms={prev_oldest_ms}，停止"
                    )
                    break
                prev_oldest_ms = oldest_ts
                cursor_after = oldest_ts
            
            result = [by_ts[k] for k in sorted(by_ts.keys())]
            if len(result) > target_bars:
                result = result[-target_bars:]
            logger.info(
                f"K线拉取(after): symbol={symbol} bar={timeframe} lookback_days={lookback_days} "
                f"target_bars={target_bars} pages={pages} got={len(result)} cutoff_ts_ms={end_ts}"
            )
            return result
            
        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            raise
    
    async def _fetch_ticker_data(self, symbol: str) -> Dict:
        """获取最新行情数据"""
        market_service = self._get_market_service()
        try:
            ticker = await market_service.get_ticker(symbol)
            return {
                "last_price": float(ticker.get("last", 0)),
                "open_24h": float(ticker.get("open24h", 0)),
                "high_24h": float(ticker.get("high24h", 0)),
                "low_24h": float(ticker.get("low24h", 0)),
                "volume_24h": float(ticker.get("volCcy24h", 0)),
                "change_24h": float(ticker.get("last", 0)) / float(ticker.get("open24h", 1)) - 1
                if float(ticker.get("open24h", 0)) > 0 else 0
            }
        except Exception as e:
            logger.error(f"获取行情数据失败: {e}")
            return {}

    def _build_ticker_from_klines(self, klines: List[Dict], timeframe: str) -> Dict[str, Any]:
        """基于分析所用 K 线构造同一时点行情摘要，避免与实时 ticker 不同步。"""
        if not klines:
            return {}
        minutes_per_bar = self.TIMEFRAME_MINUTES.get(timeframe, 240)
        bars_24h = max(1, int((24 * 60) / max(minutes_per_bar, 1)))
        window = klines[-bars_24h:] if len(klines) >= bars_24h else klines
        last_close = float(klines[-1]["close"])
        open_24h = float(window[0]["open"]) if window else last_close
        high_24h = max(float(k["high"]) for k in window) if window else last_close
        low_24h = min(float(k["low"]) for k in window) if window else last_close
        volume_24h = sum(float(k.get("volume") or 0.0) for k in window)
        change_24h = (last_close / open_24h - 1) if open_24h > 0 else 0.0
        return {
            "last_price": last_close,
            "open_24h": open_24h,
            "high_24h": high_24h,
            "low_24h": low_24h,
            "volume_24h": volume_24h,
            "change_24h": change_24h,
        }
    
    def _bars_for_days(self, timeframe: str, days: int) -> int:
        """将日数换算成当前 K 线周期对应的 bar 数。"""
        minutes_per_bar = self.TIMEFRAME_MINUTES.get(timeframe, 240)
        if minutes_per_bar <= 0:
            minutes_per_bar = 240
        total_minutes = max(1, days) * 24 * 60
        return max(1, total_minutes // minutes_per_bar)

    def _calculate_indicators(self, klines: List[Dict], timeframe: str) -> Dict[str, Any]:
        """计算技术指标"""
        if len(klines) < 5:
            return {"error": "K线数据不足"}
        
        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        volumes = [k["volume"] for k in klines]
        current_price = closes[-1]
        price_change_1d_bars = self._bars_for_days(timeframe, 1)
        price_change_7d_bars = self._bars_for_days(timeframe, 7)
        price_change_30d_bars = self._bars_for_days(timeframe, 30)
        
        indicators = {
            "current_price": current_price,
            "price_change_1d": self._calc_price_change(closes, price_change_1d_bars),
            "price_change_7d": self._calc_price_change(closes, price_change_7d_bars),
            "price_change_30d": self._calc_price_change(closes, price_change_30d_bars),
        }
        
        for period in [5, 10, 20, 60]:
            indicators[f"ma{period}"] = self._calc_ma(closes, period)
        
        for period in [5, 10, 20]:
            indicators[f"ema{period}"] = self._calc_ema(closes, period)
        
        indicators["rsi_14"] = self._calc_rsi(closes, 14)
        indicators["rsi_7"] = self._calc_rsi(closes, 7)
        
        macd_result = self._calc_macd(closes)
        if macd_result:
            indicators["macd"] = macd_result
        
        boll = self._calc_bollinger(closes)
        if boll:
            indicators["bollinger"] = boll
        
        fib = self._calc_fibonacci(highs, lows, current_price)
        if fib:
            indicators["fibonacci"] = fib
        
        indicators["atr_14"] = self._calc_atr(highs, lows, closes, 14)
        
        indicators["volatility"] = self._calc_volatility(closes)
        
        indicators["volume_ma20"] = self._calc_ma(volumes, 20)
        indicators["volume_ratio"] = (
            volumes[-1] / indicators["volume_ma20"]
            if indicators["volume_ma20"] and indicators["volume_ma20"] > 0
            else None
        )
        
        indicators["trend_strength"] = self._calc_trend_strength(closes)
        
        return indicators
    
    def _calc_price_change(self, closes: List[float], periods: int) -> Optional[float]:
        """计算价格变化百分比"""
        if len(closes) < periods + 1:
            return None
        return (closes[-1] - closes[-periods-1]) / closes[-periods-1] * 100
    
    def _calc_ma(self, data: List[float], period: int) -> Optional[float]:
        """计算简单移动平均"""
        if len(data) < period:
            return None
        return sum(data[-period:]) / period
    
    def _calc_ema(self, data: List[float], period: int) -> Optional[float]:
        """计算指数移动平均"""
        if len(data) < period:
            return None
        
        alpha = 2.0 / (period + 1)
        ema = sum(data[:period]) / period
        
        for price in data[period:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return ema
    
    def _calc_rsi(self, closes: List[float], period: int = 14) -> Optional[float]:
        """计算RSI"""
        if len(closes) < period + 1:
            return None
        
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(change if change > 0 else 0)
            losses.append(-change if change < 0 else 0)
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calc_macd(
        self,
        closes: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Optional[Dict[str, Any]]:
        """计算MACD"""
        macd_result = calc_consistent_macd(closes, fast=fast, slow=slow, signal=signal)
        if not macd_result:
            return None

        histogram = float(macd_result["histogram"])
        return {
            "dif": float(macd_result["dif"]),
            "dea": float(macd_result["dea"]),
            "histogram": histogram,
            "signal": "bullish" if histogram > 0 else "bearish"
        }
    
    def _calc_bollinger(
        self,
        closes: List[float],
        period: int = 20,
        num_std: float = 2.0
    ) -> Optional[Dict]:
        """计算布林带"""
        if len(closes) < period:
            return None
        
        window = closes[-period:]
        middle = sum(window) / period
        variance = sum((x - middle) ** 2 for x in window) / period
        std = variance ** 0.5 if variance > 0 else 0
        
        upper = middle + num_std * std
        lower = middle - num_std * std
        current = closes[-1]
        
        if upper > lower:
            position = (current - lower) / (upper - lower)
        else:
            position = 0.5
        
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": (upper - lower) / middle * 100 if middle > 0 else 0,
            "position": position,
            "position_desc": "上轨" if position > 0.8 else "下轨" if position < 0.2 else "中轨"
        }
    
    def _calc_fibonacci(
        self,
        highs: List[float],
        lows: List[float],
        current_price: float,
        lookback: int = 20
    ) -> Optional[Dict]:
        """计算斐波那契回撤"""
        if len(highs) < lookback or len(lows) < lookback:
            return None
        
        h = max(highs[-lookback:])
        l = min(lows[-lookback:])
        diff = h - l
        
        if diff == 0:
            return None
        
        levels = {
            "high": h,
            "low": l,
            "level_0": h,
            "level_236": h - 0.236 * diff,
            "level_382": h - 0.382 * diff,
            "level_500": h - 0.5 * diff,
            "level_618": h - 0.618 * diff,
            "level_100": l,
        }
        
        if current_price >= h * 0.999:
            position_desc = "接近区间高点"
        elif current_price <= l * 1.001:
            position_desc = "接近区间低点"
        elif current_price >= levels["level_382"]:
            position_desc = "在0.382之上（偏强）"
        elif current_price >= levels["level_500"]:
            position_desc = "在0.382-0.5之间"
        elif current_price >= levels["level_618"]:
            position_desc = "在0.5-0.618之间（常见支撑）"
        else:
            position_desc = "在0.618之下（偏弱）"
        
        levels["position_desc"] = position_desc
        return levels
    
    def _calc_atr(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> Optional[float]:
        """计算ATR（平均真实波幅）"""
        if len(closes) < period + 1:
            return None
        
        tr_list = []
        for i in range(1, len(closes)):
            h = highs[i]
            l = lows[i]
            pc = closes[i-1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_list.append(tr)
        
        return sum(tr_list[-period:]) / period
    
    def _calc_volatility(self, closes: List[float], period: int = 20) -> Optional[float]:
        """计算波动率"""
        if len(closes) < period:
            return None
        
        recent = closes[-period:]
        mean = sum(recent) / len(recent)
        
        if mean == 0:
            return None
        
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        std = variance ** 0.5
        
        return std / mean * 100
    
    def _calc_trend_strength(self, closes: List[float]) -> Dict:
        """计算趋势强度"""
        result = {
            "short_term": "neutral",
            "medium_term": "neutral",
            "long_term": "neutral"
        }
        
        ma5 = self._calc_ma(closes, 5)
        ma10 = self._calc_ma(closes, 10)
        ma20 = self._calc_ma(closes, 20)
        ma60 = self._calc_ma(closes, 60)
        current = closes[-1] if closes else 0
        
        if ma5 and ma10:
            if ma5 > ma10 and current > ma5:
                result["short_term"] = "bullish"
            elif ma5 < ma10 and current < ma5:
                result["short_term"] = "bearish"
        
        if ma10 and ma20:
            if ma10 > ma20:
                result["medium_term"] = "bullish"
            elif ma10 < ma20:
                result["medium_term"] = "bearish"
        
        if ma20 and ma60:
            if ma20 > ma60:
                result["long_term"] = "bullish"
            elif ma20 < ma60:
                result["long_term"] = "bearish"
        
        return result
    
    def _build_user_input_prompt(
        self,
        params: Dict[str, Any],
        context: Optional[Dict] = None
    ) -> str:
        """构建用户输入Prompt"""
        indicators = context.get("indicators", {}) if context else {}
        ticker = context.get("ticker", {}) if context else {}
        klines = context.get("klines", []) if context else []
        
        prompt = f"""
## 分析任务

交易对：{params['symbol']}
分析截止日期：{params['analysis_date'].strftime('%Y-%m-%d %H:%M')}
K线周期：{params['timeframe']}
回溯天数：{params['lookback_days']}

## 最新行情
"""
        if ticker:
            prompt += f"""
- 最新价格：{ticker.get('last_price', 'N/A')}
- 24小时最高：{ticker.get('high_24h', 'N/A')}
- 24小时最低：{ticker.get('low_24h', 'N/A')}
- 24小时涨跌：{ticker.get('change_24h', 0) * 100:.2f}%
- 24小时成交量：{ticker.get('volume_24h', 'N/A')}
"""
        
        prompt += "\n## 技术指标数据\n"
        
        if indicators.get("current_price"):
            prompt += f"\n### 价格变化\n"
            prompt += f"- 当前价格：{indicators['current_price']:.4f}\n"
            if indicators.get("price_change_1d"):
                prompt += f"- 1日涨跌：{indicators['price_change_1d']:.2f}%\n"
            if indicators.get("price_change_7d"):
                prompt += f"- 7日涨跌：{indicators['price_change_7d']:.2f}%\n"
            if indicators.get("price_change_30d"):
                prompt += f"- 30日涨跌：{indicators['price_change_30d']:.2f}%\n"
        
        prompt += f"\n### 均线系统\n"
        for period in [5, 10, 20, 60]:
            ma_val = indicators.get(f"ma{period}")
            if ma_val:
                prompt += f"- MA{period}：{ma_val:.4f}\n"
        
        trend = indicators.get("trend_strength", {})
        if trend:
            prompt += f"\n### 趋势判断\n"
            prompt += f"- 短期趋势：{trend.get('short_term', 'neutral')}\n"
            prompt += f"- 中期趋势：{trend.get('medium_term', 'neutral')}\n"
            prompt += f"- 长期趋势：{trend.get('long_term', 'neutral')}\n"
        
        prompt += f"\n### RSI 指标\n"
        if indicators.get("rsi_7"):
            prompt += f"- RSI(7)：{indicators['rsi_7']:.2f}\n"
        if indicators.get("rsi_14"):
            prompt += f"- RSI(14)：{indicators['rsi_14']:.2f}\n"
        
        macd = indicators.get("macd")
        if macd:
            prompt += f"\n### MACD 指标\n"
            prompt += f"- DIF：{macd['dif']:.6f}\n"
            prompt += f"- DEA：{macd['dea']:.6f}\n"
            prompt += f"- 柱状图：{macd['histogram']:.6f}\n"
            prompt += f"- 信号：{macd['signal']}\n"
        
        boll = indicators.get("bollinger")
        if boll:
            prompt += f"\n### 布林带\n"
            prompt += f"- 上轨：{boll['upper']:.4f}\n"
            prompt += f"- 中轨：{boll['middle']:.4f}\n"
            prompt += f"- 下轨：{boll['lower']:.4f}\n"
            prompt += f"- 带宽：{boll['bandwidth']:.2f}%\n"
            prompt += f"- 当前位置：{boll['position_desc']}\n"
        
        fib = indicators.get("fibonacci")
        if fib:
            prompt += f"\n### 斐波那契回撤（{params['lookback_days']}日）\n"
            prompt += f"- 区间高点：{fib['high']:.4f}\n"
            prompt += f"- 区间低点：{fib['low']:.4f}\n"
            prompt += f"- 0.382位：{fib['level_382']:.4f}\n"
            prompt += f"- 0.5位：{fib['level_500']:.4f}\n"
            prompt += f"- 0.618位：{fib['level_618']:.4f}\n"
            prompt += f"- 当前位置：{fib['position_desc']}\n"
        
        if indicators.get("atr_14"):
            prompt += f"\n### 波动指标\n"
            prompt += f"- ATR(14)：{indicators['atr_14']:.4f}\n"
        if indicators.get("volatility"):
            prompt += f"- 波动率(20日)：{indicators['volatility']:.2f}%\n"
        
        if indicators.get("volume_ratio"):
            prompt += f"\n### 成交量\n"
            prompt += f"- 成交量比率（vs MA20）：{indicators['volume_ratio']:.2f}\n"

        prompt += "\n\n请基于以上数据，生成完整的技术分析报告（JSON格式）。"
        
        return prompt

    @staticmethod
    def _fmt_num(value: Any, digits: int = 4) -> str:
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "N/A"

    @staticmethod
    def _fmt_pct(value: Any, digits: int = 2) -> str:
        try:
            return f"{float(value):.{digits}f}%"
        except (TypeError, ValueError):
            return "N/A"

    @staticmethod
    def _join_levels(values: Any, digits: int = 4) -> str:
        if not isinstance(values, list) or not values:
            return "N/A"
        out = []
        for item in values[:3]:
            try:
                out.append(f"{float(item):.{digits}f}")
            except (TypeError, ValueError):
                out.append(str(item))
        return ", ".join(out)

    @staticmethod
    def _safe_round(value: Any, digits: int = 4) -> Optional[float]:
        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _json_dumps(data: Any) -> str:
        try:
            return json.dumps(data or {}, ensure_ascii=False, indent=2)
        except TypeError:
            return "{}"

    @staticmethod
    def _normalize_timeframe_label(timeframe: Any) -> str:
        raw = str(timeframe or "").strip()
        if not raw:
            return "-"
        return raw.lower() if raw.endswith(("H", "D", "W", "M")) else raw

    @staticmethod
    def _normalize_strength_label(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"strong", "moderate", "weak"}:
            return text
        if text in {"medium", "mid"}:
            return "moderate"
        return "weak"

    @staticmethod
    def _normalize_boll_position(value: Any) -> str:
        text = str(value or "").strip().lower()
        mapping = {
            "upper": "upper",
            "upper_band": "upper",
            "上轨": "upper",
            "middle": "middle",
            "mid": "middle",
            "middle_band": "middle",
            "中轨": "middle",
            "lower": "lower",
            "lower_band": "lower",
            "下轨": "lower",
        }
        return mapping.get(text, "middle")

    def _llm_metadata(self) -> Dict[str, Any]:
        return {
            "model": getattr(self.llm, "model_name", None) or getattr(self.llm, "model", None),
            "temperature": getattr(self.llm, "temperature", None),
            "api_url": getattr(self.llm, "api_url", None),
        }

    def _derive_consensus(self, analysis: Dict[str, Any], indicators: Dict[str, Any]) -> str:
        trend = analysis.get("trend") if isinstance(analysis.get("trend"), dict) else {}
        direction = str(trend.get("direction") or "").strip().lower()
        strength = self._normalize_strength_label(trend.get("strength"))
        if direction == "bullish":
            return "strong_trend_bullish" if strength == "strong" else "bullish_bias"
        if direction == "bearish":
            return "strong_trend_bearish" if strength == "strong" else "bearish_bias"

        trend_strength = indicators.get("trend_strength") or {}
        short_term = str(trend_strength.get("short_term") or "neutral").strip().lower()
        medium_term = str(trend_strength.get("medium_term") or "neutral").strip().lower()
        long_term = str(trend_strength.get("long_term") or "neutral").strip().lower()
        directions = [short_term, medium_term, long_term]
        bullish_count = sum(1 for item in directions if item == "bullish")
        bearish_count = sum(1 for item in directions if item == "bearish")
        if bullish_count >= 2:
            return "bullish_bias"
        if bearish_count >= 2:
            return "bearish_bias"
        return "mixed"

    def _build_risk_flags(
        self,
        analysis: Dict[str, Any],
        indicators: Dict[str, Any],
        ticker: Dict[str, Any],
    ) -> List[str]:
        flags: List[str] = []
        current_price = indicators.get("current_price") or ticker.get("last_price")
        current_f = self._safe_round(current_price, 8)
        sr = analysis.get("support_resistance") if isinstance(analysis.get("support_resistance"), dict) else {}
        resistance_levels = sr.get("key_resistance") or []
        support_levels = sr.get("key_support") or []

        if current_f and resistance_levels:
            try:
                nearest_resistance = min(float(x) for x in resistance_levels[:2])
                if nearest_resistance > 0 and (nearest_resistance - current_f) / current_f <= 0.01:
                    flags.append("near_resistance")
            except (TypeError, ValueError):
                pass
        if current_f and support_levels:
            try:
                nearest_support = max(float(x) for x in support_levels[:2])
                if nearest_support > 0 and (current_f - nearest_support) / current_f <= 0.01:
                    flags.append("near_support")
            except (TypeError, ValueError):
                pass

        rsi_14 = self._safe_round(indicators.get("rsi_14"), 2)
        if rsi_14 is not None and rsi_14 >= 70:
            flags.append("overbought")
        elif rsi_14 is not None and rsi_14 <= 30:
            flags.append("oversold")

        atr_14 = self._safe_round(indicators.get("atr_14"), 6)
        if current_f and atr_14 is not None and current_f > 0:
            atr_pct = atr_14 / current_f * 100
            if atr_pct >= 2.5:
                flags.append("high_volatility")

        volume_ratio = self._safe_round(indicators.get("volume_ratio"), 2)
        if volume_ratio is not None and volume_ratio >= 1.8:
            flags.append("volume_spike")

        return flags

    def _build_technical_facts(
        self,
        params: Dict[str, Any],
        analysis: Dict[str, Any],
        indicators: Dict[str, Any],
        ticker: Dict[str, Any],
    ) -> Dict[str, Any]:
        trend = analysis.get("trend") if isinstance(analysis.get("trend"), dict) else {}
        sr = analysis.get("support_resistance") if isinstance(analysis.get("support_resistance"), dict) else {}
        macd = indicators.get("macd") or {}
        boll = indicators.get("bollinger") or {}
        current_price = indicators.get("current_price") or ticker.get("last_price")
        atr_14 = self._safe_round(indicators.get("atr_14"), 6)
        atr_pct = None
        try:
            if atr_14 is not None and current_price:
                atr_pct = round(float(atr_14) / float(current_price) * 100, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            atr_pct = None

        return {
            "symbol": params["symbol"],
            "as_of": params["analysis_date"].replace(microsecond=0).isoformat(),
            "timeframe": self._normalize_timeframe_label(params["timeframe"]),
            "summary": str(analysis.get("summary") or "").strip()[:160],
            "consensus": self._derive_consensus(analysis, indicators),
            "trend": str(trend.get("direction") or "neutral").strip().lower() or "neutral",
            "trend_strength": self._normalize_strength_label(trend.get("strength")),
            "rsi_14": self._safe_round(indicators.get("rsi_14"), 2),
            "rsi_7": self._safe_round(indicators.get("rsi_7"), 2),
            "macd_hist": self._safe_round(macd.get("histogram"), 4),
            "boll_pos": self._normalize_boll_position(boll.get("position_desc")),
            "atr_pct": atr_pct,
            "volume_ratio": self._safe_round(indicators.get("volume_ratio"), 2),
            "price_change_1d_pct": self._safe_round(indicators.get("price_change_1d"), 2),
            "supports": [self._safe_round(x, 4) for x in (sr.get("key_support") or [])[:3] if self._safe_round(x, 4) is not None],
            "resistances": [self._safe_round(x, 4) for x in (sr.get("key_resistance") or [])[:3] if self._safe_round(x, 4) is not None],
            "risk_flags": self._build_risk_flags(analysis, indicators, ticker),
        }

    def _build_decision_report(
        self,
        params: Dict[str, Any],
        analysis: Dict[str, Any],
        indicators: Dict[str, Any],
        ticker: Dict[str, Any],
    ) -> str:
        """构建给交易决策 Agent 使用的技术分析摘要文本。"""
        trend = analysis.get("trend") or {}
        momentum = analysis.get("momentum") or {}
        volatility = analysis.get("volatility") or {}
        sr = analysis.get("support_resistance") or {}
        summary = str(analysis.get("summary") or "").strip()
        risk_warning = str((analysis.get("recommendation") or {}).get("risk_warning") or "").strip()
        support_text = self._join_levels(sr.get("key_support"), digits=2)
        resistance_text = self._join_levels(sr.get("key_resistance"), digits=2)
        rsi_val = self._safe_round(indicators.get("rsi_14"), 1)
        macd_hist = self._safe_round((indicators.get("macd") or {}).get("histogram"), 3)

        core_line = (
            f"- {self._normalize_timeframe_label(params['timeframe'])}: "
            f"趋势={trend.get('direction', 'neutral')}/{self._normalize_strength_label(trend.get('strength'))}; "
            f"RSI14={rsi_val if rsi_val is not None else 'N/A'}; "
            f"MACD={momentum.get('macd_status', 'neutral')}"
            f"{f'({macd_hist})' if macd_hist is not None else ''}; "
            f"布林={self._normalize_boll_position(volatility.get('bollinger_position'))}"
        )
        lines = [f"{params['symbol']} 技术摘要", core_line]
        if summary:
            lines.append(f"- 摘要: {summary[:140]}")
        lines.append(f"- 关键位: 支撑={support_text} | 阻力={resistance_text}")
        if risk_warning:
            lines.append(f"- 风险: {risk_warning[:120]}")
        return "\n".join(lines)

    def _build_llm_audit(
        self,
        user_prompt: str,
        messages: List[Dict[str, str]],
        llm_response: str,
        parsed_payload: Any,
    ) -> Dict[str, Any]:
        safe_messages: List[Dict[str, str]] = []
        for msg in messages or []:
            if not isinstance(msg, dict):
                continue
            safe_messages.append(
                {
                    "role": str(msg.get("role") or ""),
                    "content": str(msg.get("content") or ""),
                }
            )
        return {
            "analysisPrompt": self._messages_to_text(safe_messages),
            "userPrompt": user_prompt,
            "messages": safe_messages,
            "llmRawResponse": llm_response,
            "parsedAnalysis": self._json_dumps(parsed_payload),
            "llmMetadata": self._llm_metadata(),
        }
    
    def _parse_llm_response(
        self,
        llm_response: str,
        params: Dict[str, Any],
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """解析LLM响应"""
        try:
            start = llm_response.find('{')
            end = llm_response.rfind('}') + 1
            
            if start >= 0 and end > start:
                json_str = llm_response[start:end]
                analysis = json.loads(json_str)
                
                return {
                    "success": True,
                    "symbol": params["symbol"],
                    "analysis_date": params["analysis_date"].isoformat(),
                    "timeframe": params["timeframe"],
                    "analysis": analysis,
                    "raw_indicators": context.get("indicators", {}) if context else {}
                }
        except json.JSONDecodeError as e:
            logger.warning(f"解析LLM响应失败: {e}")
        
        return {
            "success": False,
            "symbol": params["symbol"],
            "analysis_date": params["analysis_date"].isoformat(),
            "error": "LLM响应解析失败",
            "raw_response": llm_response[:500]
        }
    
    async def _execute_normal_mode(
        self,
        params: Dict[str, Any],
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """执行分析任务"""
        try:
            ctx = context or {}
            klines = await self._fetch_kline_data(
                symbol=params["symbol"],
                timeframe=params["timeframe"],
                end_date=params["analysis_date"],
                lookback_days=params["lookback_days"],
                session=ctx.get("db_session"),
                exchange=str(ctx.get("kline_exchange") or "okx"),
            )
            
            if len(klines) < 20:
                return {
                    "success": False,
                    "error": f"K线数据不足，只获取到 {len(klines)} 根",
                    "symbol": params["symbol"]
                }
            
            ticker = self._build_ticker_from_klines(klines, params["timeframe"])

            indicators = self._calculate_indicators(klines, params["timeframe"])

            analysis_context = {
                "klines": klines,
                "ticker": ticker,
                "indicators": indicators,
            }
            
            if self.llm:
                user_prompt = self._build_user_input_prompt(params, analysis_context)
                messages = self._build_messages(
                    user_message=user_prompt,
                    include_system_prompt=True
                )
                
                llm_response = await self._call_llm_with_messages(messages)
                result = self._parse_llm_response(llm_response, params, analysis_context)
                if isinstance(result, dict):
                    parsed_payload = (
                        result.get("analysis")
                        if result.get("success")
                        else {
                            "success": result.get("success", False),
                            "error": result.get("error"),
                            "symbol": result.get("symbol"),
                            "analysis_date": result.get("analysis_date"),
                        }
                    )
                    result["analysis_mode"] = "llm"
                    result["llm_audit"] = self._build_llm_audit(
                        user_prompt=user_prompt,
                        messages=messages,
                        llm_response=llm_response,
                        parsed_payload=parsed_payload,
                    )
            else:
                result = self._generate_rule_based_analysis(params, indicators, ticker)

            if result.get("success"):
                result["technical_facts"] = self._build_technical_facts(
                    params=params,
                    analysis=result.get("analysis") or {},
                    indicators=indicators,
                    ticker=ticker,
                )
                result["decision_report"] = self._build_decision_report(
                    params=params,
                    analysis=result.get("analysis") or {},
                    indicators=indicators,
                    ticker=ticker,
                )
            
            return result
            
        except Exception as e:
            logger.error(f"执行分析任务失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "symbol": params["symbol"]
            }
    
    def _generate_rule_based_analysis(
        self,
        params: Dict[str, Any],
        indicators: Dict,
        ticker: Dict
    ) -> Dict[str, Any]:
        """基于规则的分析（无LLM时使用）"""
        trend = indicators.get("trend_strength", {})
        rsi = indicators.get("rsi_14", 50)
        macd = indicators.get("macd", {})
        boll = indicators.get("bollinger", {})
        
        bullish_signals = 0
        bearish_signals = 0
        signals = []
        
        if trend.get("short_term") == "bullish":
            bullish_signals += 1
            signals.append({"type": "bullish", "indicator": "MA", "description": "短期均线多头排列"})
        elif trend.get("short_term") == "bearish":
            bearish_signals += 1
            signals.append({"type": "bearish", "indicator": "MA", "description": "短期均线空头排列"})
        
        if rsi < 30:
            bullish_signals += 1
            signals.append({"type": "bullish", "indicator": "RSI", "description": f"RSI超卖({rsi:.1f})"})
        elif rsi > 70:
            bearish_signals += 1
            signals.append({"type": "bearish", "indicator": "RSI", "description": f"RSI超买({rsi:.1f})"})
        
        if macd.get("signal") == "bullish":
            bullish_signals += 1
            signals.append({"type": "bullish", "indicator": "MACD", "description": "MACD柱状图为正"})
        elif macd.get("signal") == "bearish":
            bearish_signals += 1
            signals.append({"type": "bearish", "indicator": "MACD", "description": "MACD柱状图为负"})
        
        if bullish_signals > bearish_signals:
            direction = "bullish"
            recommendation = "buy"
        elif bearish_signals > bullish_signals:
            direction = "bearish"
            recommendation = "sell"
        else:
            direction = "neutral"
            recommendation = "hold"
        
        analysis = {
            "summary": f"{params['symbol']} 当前{direction}，多空信号比 {bullish_signals}:{bearish_signals}",
            "trend": {
                "direction": direction,
                "strength": "moderate",
                "description": f"短期{trend.get('short_term', 'neutral')}，中期{trend.get('medium_term', 'neutral')}"
            },
            "momentum": {
                "rsi_status": "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral",
                "macd_status": macd.get("signal", "neutral"),
                "description": f"RSI={rsi:.1f}，MACD信号={macd.get('signal', 'N/A')}"
            },
            "volatility": {
                "status": "high" if indicators.get("volatility", 0) > 5 else "low",
                "bollinger_position": boll.get("position_desc", "N/A"),
                "description": f"波动率={indicators.get('volatility', 0):.2f}%"
            },
            "signals": signals,
            "recommendation": {
                "action": recommendation,
                "confidence": 0.6,
                "risk_warning": "此为规则化分析，仅供参考"
            }
        }
        
        return {
            "success": True,
            "symbol": params["symbol"],
            "analysis_date": params["analysis_date"].isoformat(),
            "timeframe": params["timeframe"],
            "analysis": analysis,
            "raw_indicators": indicators,
            "analysis_mode": "rule_based"
        }
