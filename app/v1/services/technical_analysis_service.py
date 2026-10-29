#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标分析服务层
"""
import copy
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from loguru import logger
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_applications.task_agents.technical_analysis_agent import TechnicalAnalysisAgent
from lib.okx.symbol_utils import normalize_okx_symbol
from app.v1.crud.model_management_crud import get_api_config_by_id, get_model_by_id
from app.v1.crud.technical_analysis_record_crud import (
    create_technical_analysis_record,
    get_technical_analysis_record,
    list_technical_analysis_records,
)
from core.llm.base.base_llm import BaseLLM
from core.llm.llm_factory import ApiType, LLMFactory


def _is_lost_mysql_connection(exc: Exception) -> bool:
    """判断是否为 MySQL 连接断开类错误（长耗时任务后常见）。"""
    if isinstance(exc, OperationalError):
        orig = getattr(exc, "orig", None)
        if orig and getattr(orig, "args", None):
            code = orig.args[0]
            if code in (2006, 2013):
                return True
    msg = str(exc).lower()
    return "lost connection" in msg or "server has gone away" in msg


def _map_api_type(api_type_raw: Optional[str]) -> str:
    if not api_type_raw:
        return ApiType.GENERIC
    x = str(api_type_raw).strip().lower()
    if x in ("openai", "open_ai"):
        return ApiType.OPENAI
    if x == "deepseek":
        return ApiType.DEEPSEEK
    return ApiType.GENERIC


async def _build_llm_from_managed_model(
    session: AsyncSession,
    llm_model_id: int,
    temperature: float,
) -> Tuple[Optional[BaseLLM], Optional[str], Optional[str]]:
    """
    根据模型管理记录构造 LLM。

    Returns:
        (llm, error_message, model_display_name)
    """
    model = await get_model_by_id(session, llm_model_id)
    if not model:
        return None, f"未找到模型 id={llm_model_id}", None
    if not model.api_config_id:
        return None, "模型未绑定 API 配置", None
    cfg = await get_api_config_by_id(session, model.api_config_id)
    if not cfg or not (cfg.api_key or "").strip():
        return None, "API 配置缺失或 Key 为空", None

    api_type = _map_api_type(cfg.api_type)
    extra_headers = dict(cfg.extra_headers) if cfg.extra_headers else None
    extra_body: Dict[str, Any] = {}
    if cfg.extra_params:
        extra_body.update(dict(cfg.extra_params))
    if model.custom_params:
        extra_body.update(dict(model.custom_params))
    if extra_body and api_type in (ApiType.OPENAI, ApiType.DEEPSEEK):
        logger.debug("模型含 extra 参数，技术分析改用 generic 客户端")
        api_type = ApiType.GENERIC

    display_name = (model.name or "").strip() or model.model_id
    output_tokens = getattr(model, "max_output_tokens", None) or model.max_tokens or 4096
    logger.info(
        "技术分析 LLM 追踪: "
        f"llm_model_id={llm_model_id}, model={model.model_id}, "
        f"display_name={display_name}, api_type={api_type}, api_url={cfg.api_url or 'default'}"
    )

    llm = LLMFactory.create_llm_direct(
        model_name=model.model_id,
        api_key=cfg.api_key.strip(),
        api_type=api_type,
        api_url=cfg.api_url,
        temperature=float(temperature),
        max_tokens=output_tokens,
        use_max_completion_tokens=bool(model.use_max_completion_tokens),
        extra_headers=extra_headers,
        extra_body=extra_body if extra_body else None,
    )
    if not llm:
        return None, "LLMFactory 创建失败", None
    return llm, None, display_name


class TechnicalAnalysisService:
    """技术指标分析服务"""

    def __init__(self):
        self._indicator_agent: Optional[TechnicalAnalysisAgent] = None

    def _get_indicator_agent(self) -> TechnicalAnalysisAgent:
        """无 LLM 路径的指标计算复用单例，避免重复初始化默认 LLM。"""
        if self._indicator_agent is None:
            self._indicator_agent = TechnicalAnalysisAgent()
        return self._indicator_agent

    @staticmethod
    def _snapshot_for_storage(payload: Dict[str, Any]) -> Dict[str, Any]:
        """深拷贝可 JSON 序列化的分析结果，避免 ORM 持有可变引用。"""
        return copy.deepcopy(payload)

    async def analyze(
        self,
        symbol: str,
        analysis_date: Optional[str] = None,
        timeframe: str = "4h",
        lookback_days: int = 30,
        llm_model_id: Optional[int] = None,
        temperature: float = 0.3,
        session: Optional[AsyncSession] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        执行技术指标分析

        Args:
            llm_model_id: 模型管理主键；为 None 时使用环境变量默认 DeepSeek
            temperature: LLM 温度
            session: 选择模型时必填，用于读取模型与 API 配置
        """
        try:
            llm: Optional[BaseLLM] = None
            model_display_name: Optional[str] = None

            logger.info(
                "技术分析入口追踪: "
                f"symbol={symbol}, analysis_date={analysis_date}, timeframe={timeframe}, "
                f"lookback_days={lookback_days}, llm_model_id={llm_model_id}, temperature={temperature}"
            )

            if llm_model_id is not None:
                if session is None:
                    return {
                        "success": False,
                        "symbol": symbol,
                        "error": "缺少数据库会话，无法加载所选模型",
                    }
                llm, err, model_display_name = await _build_llm_from_managed_model(
                    session, llm_model_id, temperature
                )
                if err:
                    out = {"success": False, "symbol": symbol, "error": err}
                    await self._persist_generation_record(
                        session=session,
                        user_id=user_id,
                        analysis_date=analysis_date,
                        timeframe=timeframe,
                        lookback_days=lookback_days,
                        temperature=temperature,
                        llm_model_id=llm_model_id,
                        llm_model_name=None,
                        formatted=out,
                    )
                    return out

            agent = TechnicalAnalysisAgent(llm=llm) if llm is not None else TechnicalAnalysisAgent()
            logger.info(
                "技术分析 Agent 追踪: "
                f"llm_injected={llm is not None}, "
                f"llm_class={llm.__class__.__name__ if llm else None}, "
                f"llm_api_url={getattr(llm, 'api_url', None) if llm else None}"
            )

            task = {
                "symbol": symbol,
                "analysis_date": analysis_date,
                "timeframe": timeframe,
                "lookback_days": lookback_days,
            }

            exec_ctx = {"db_session": session} if session is not None else None
            result = await agent.execute(task, context=exec_ctx)
            formatted = self._format_response(result)

            if formatted.get("success") and llm_model_id is not None:
                formatted["llmModelId"] = llm_model_id
                if model_display_name:
                    formatted["llmModelName"] = model_display_name

            await self._persist_generation_record(
                session=session,
                user_id=user_id,
                analysis_date=analysis_date,
                timeframe=timeframe,
                lookback_days=lookback_days,
                temperature=temperature,
                llm_model_id=llm_model_id,
                llm_model_name=formatted.get("llmModelName") if isinstance(formatted, dict) else None,
                formatted=formatted,
            )

            return formatted

        except Exception as e:
            logger.error(f"技术分析失败: {e}")
            err_payload = {"success": False, "symbol": symbol, "error": str(e)}
            await self._persist_generation_record(
                session=session,
                user_id=user_id,
                analysis_date=analysis_date,
                timeframe=timeframe,
                lookback_days=lookback_days,
                temperature=temperature,
                llm_model_id=llm_model_id,
                llm_model_name=None,
                formatted=err_payload,
            )
            return err_payload

    async def _persist_generation_record(
        self,
        session: Optional[AsyncSession],
        user_id: Optional[str],
        analysis_date: Optional[str],
        timeframe: str,
        lookback_days: int,
        temperature: float,
        llm_model_id: Optional[int],
        llm_model_name: Optional[str],
        formatted: Dict[str, Any],
    ) -> None:
        if not user_id or session is None:
            return
        ok = bool(formatted.get("success"))
        sym = str(formatted.get("symbol") or "")
        err = formatted.get("error") if not ok else None
        summary_preview = None
        if ok:
            analysis = formatted.get("analysis") or {}
            s = analysis.get("summary")
            if isinstance(s, str) and s.strip():
                summary_preview = s.strip()[:500]
        payload = self._snapshot_for_storage(formatted)
        insert_kwargs = dict(
            user_id=user_id,
            symbol=sym,
            analysis_date=analysis_date,
            timeframe=timeframe,
            lookback_days=lookback_days,
            temperature=float(temperature),
            llm_model_id=llm_model_id,
            llm_model_name=llm_model_name,
            success=ok,
            error_message=str(err) if err else None,
            summary_preview=summary_preview,
            result_payload=payload,
        )

        async def _insert(sess: AsyncSession):
            return await create_technical_analysis_record(session=sess, **insert_kwargs)

        rec = None
        try:
            # LLM 分析期间连接可能长时间空闲，写入前先释放旧事务/连接。
            try:
                await session.rollback()
            except Exception as rb_err:
                logger.debug(f"技术分析记录保存前 session.rollback 异常，改为 invalidate: {rb_err}")
                try:
                    await session.invalidate()
                except Exception as inv_err:
                    logger.debug(f"技术分析记录保存前 session.invalidate 跳过: {inv_err}")
            rec = await _insert(session)
        except Exception as e:
            if not _is_lost_mysql_connection(e):
                logger.warning(f"保存技术分析生成记录失败: {e}")
                try:
                    await session.rollback()
                except Exception as rb_err:
                    logger.warning(f"技术分析记录保存失败后 session.rollback 异常: {rb_err}")
                return
            logger.warning(f"保存技术分析生成记录连接失效，使用独立会话重试: {e}")
            try:
                await session.rollback()
            except Exception as rb_err:
                logger.debug(f"技术分析记录重试前 session.rollback 异常: {rb_err}")
            maker = async_sessionmaker(
                bind=session.bind,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
            try:
                async with maker() as isolated_session:
                    rec = await _insert(isolated_session)
                    await isolated_session.commit()
                try:
                    await session.rollback()
                except Exception as rb_err:
                    logger.debug(f"技术分析记录独立会话提交后 rollback 异常: {rb_err}")
            except Exception as retry_err:
                logger.warning(f"保存技术分析生成记录重试仍失败: {retry_err}")
                return

        if rec is not None:
            formatted["recordId"] = rec.id

    async def list_generation_records(
        self,
        session: AsyncSession,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        page = max(1, page)
        page_size = min(100, max(1, page_size))
        skip = (page - 1) * page_size
        rows, total = await list_technical_analysis_records(session, user_id, skip, page_size)
        items = []
        for r in rows:
            items.append(
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "analysisDate": r.analysis_date,
                    "timeframe": r.timeframe,
                    "lookbackDays": r.lookback_days,
                    "temperature": r.temperature,
                    "llmModelId": r.llm_model_id,
                    "llmModelName": r.llm_model_name,
                    "success": r.success,
                    "errorMessage": r.error_message,
                    "summaryPreview": r.summary_preview,
                    "createdAt": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    async def get_generation_record(
        self,
        session: AsyncSession,
        user_id: str,
        record_id: str,
    ) -> Optional[Dict[str, Any]]:
        r = await get_technical_analysis_record(session, record_id, user_id)
        if not r:
            return None
        payload = r.result_payload if isinstance(r.result_payload, dict) else {}
        return {
            "id": r.id,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
            "snapshot": payload,
        }

    async def get_indicators(
        self,
        symbol: str,
        timeframe: str = "4h",
        lookback_days: int = 30,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """仅获取技术指标数据（不含 LLM 分析）。传入 session 时走 MySQL K 线缓存（有则读、缺则拉取写入）。"""
        try:
            agent = self._get_indicator_agent()

            symbol_fmt = normalize_okx_symbol(symbol)

            okx_timeframe = agent.TIMEFRAME_MAP.get(timeframe.lower(), "4H")

            klines = await agent._fetch_kline_data(
                symbol=symbol_fmt,
                timeframe=okx_timeframe,
                end_date=datetime.now(),
                lookback_days=lookback_days,
                session=session,
                exchange="okx",
            )

            if len(klines) < 5:
                return {
                    "success": False,
                    "symbol": symbol_fmt,
                    "timeframe": okx_timeframe,
                    "error": f"K线数据不足，只获取到 {len(klines)} 根",
                }

            indicators = agent._calculate_indicators(klines, okx_timeframe)

            return {
                "success": True,
                "symbol": symbol_fmt,
                "timeframe": okx_timeframe,
                "indicators": self._format_indicators(indicators),
                "kline_count": len(klines),
            }

        except Exception as e:
            logger.error(f"获取指标失败: {e}")
            return {
                "success": False,
                "symbol": symbol,
                "timeframe": timeframe,
                "error": str(e),
            }

    def _format_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """格式化响应数据"""
        if not result.get("success"):
            return result

        analysis = result.get("analysis", {})

        formatted = {
            "success": True,
            "symbol": result.get("symbol"),
            "analysisDate": result.get("analysis_date"),
            "timeframe": result.get("timeframe"),
            "analysisMode": result.get("analysis_mode", "llm"),
            "decisionReport": result.get("decision_report") or "",
            "technicalFacts": result.get("technical_facts") or {},
            "analysis": {
                "summary": analysis.get("summary", ""),
                "trend": analysis.get("trend"),
                "momentum": analysis.get("momentum"),
                "volatility": analysis.get("volatility"),
                "supportResistance": analysis.get("support_resistance"),
                "signals": analysis.get("signals", []),
                "recommendation": analysis.get("recommendation"),
            },
            "rawIndicators": self._format_indicators(result.get("raw_indicators", {})),
        }

        llm_audit = result.get("llm_audit")
        if isinstance(llm_audit, dict) and llm_audit:
            formatted["llmAudit"] = self._snapshot_for_storage(llm_audit)

        return formatted

    def _format_indicators(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """格式化指标数据（转换为 camelCase）"""
        if not indicators:
            return {}

        formatted: Dict[str, Any] = {}

        for key, value in indicators.items():
            camel_key = self._to_camel_case(key)

            if isinstance(value, dict):
                formatted[camel_key] = self._format_indicators(value)
            elif isinstance(value, float):
                formatted[camel_key] = round(value, 6)
            else:
                formatted[camel_key] = value

        return formatted

    def _to_camel_case(self, snake_str: str) -> str:
        """snake_case 转 camelCase"""
        components = snake_str.split("_")
        return components[0] + "".join(x.title() for x in components[1:])


technical_analysis_service = TechnicalAnalysisService()
