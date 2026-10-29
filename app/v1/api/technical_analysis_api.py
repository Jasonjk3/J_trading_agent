#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
技术指标分析 API（统一 ApiResponse 包装，与前端 request 拦截器一致）
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.public.dependencies.auth import get_current_user
from app.public.dependencies.database import get_db_session
from app.public.dependencies.response import ApiResponse, ResponseCode
from models.inner_models.user_model import UserModel

from app.v1.services.technical_analysis_service import technical_analysis_service
from app.v1.schemas.technical_analysis_schema import TechnicalAnalysisRequest

router = APIRouter(prefix="/technical-analysis", tags=["技术指标分析"])


@router.post(
    "/analyze",
    summary="执行技术指标分析",
    description="""
执行指定交易对的技术指标分析，生成综合分析报告。

### 功能说明
- 获取历史K线数据并计算多种技术指标
- 使用 LLM 生成专业的技术分析报告

### 支持的技术指标
- **趋势指标**: MA5, MA10, MA20, MA60, EMA
- **动量指标**: RSI(7/14), MACD (DIF, DEA, 柱状图)
- **波动指标**: 布林带, ATR, 波动率
- **支撑阻力**: 斐波那契回撤位

### K线周期
支持: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w
""",
)
async def analyze_symbol(
    request: TechnicalAnalysisRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """执行技术指标分析"""
    try:
        result = await technical_analysis_service.analyze(
            symbol=request.symbol,
            analysis_date=request.analysis_date,
            timeframe=request.timeframe,
            lookback_days=request.lookback_days,
            llm_model_id=request.llm_model_id,
            temperature=request.temperature,
            session=session,
            user_id=current_user.id,
        )

        if not result.get("success"):
            return ApiResponse.failed_response(
                msg=result.get("error", "分析失败"),
                code=ResponseCode.FAILED.value,
                data=result,
            )

        return ApiResponse.success_response(msg="分析成功", data=result)
    except Exception as e:
        logger.error(f"技术分析API异常: {e}")
        return ApiResponse.failed_response(
            msg=f"分析异常: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get(
    "/analyze",
    summary="执行技术指标分析 (GET)",
    description="GET 方式执行技术分析，参数通过 Query 传递",
)
async def analyze_symbol_get(
    symbol: str = Query(..., description="交易对，如 BTC-USDT"),
    analysis_date: Optional[str] = Query(None, description="分析日期 YYYY-MM-DD"),
    timeframe: str = Query("4h", description="K线周期"),
    lookback_days: int = Query(
        30,
        ge=7,
        le=365,
        alias="lookbackDays",
        description="回溯天数（与 lookback_days 等价）",
    ),
    llm_model_id: Optional[int] = Query(None, alias="llmModelId", description="模型管理模型 ID"),
    temperature: float = Query(0.3, ge=0, le=2, description="LLM 温度"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """GET 方式执行技术分析"""
    try:
        result = await technical_analysis_service.analyze(
            symbol=symbol,
            analysis_date=analysis_date,
            timeframe=timeframe,
            lookback_days=lookback_days,
            llm_model_id=llm_model_id,
            temperature=temperature,
            session=session,
            user_id=current_user.id,
        )

        if not result.get("success"):
            return ApiResponse.failed_response(
                msg=result.get("error", "分析失败"),
                code=ResponseCode.FAILED.value,
                data=result,
            )

        return ApiResponse.success_response(msg="分析成功", data=result)
    except Exception as e:
        logger.error(f"技术分析API异常: {e}")
        return ApiResponse.failed_response(
            msg=f"分析异常: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get(
    "/records",
    summary="技术指标分析生成记录列表",
    description="分页返回当前用户的分析生成历史",
)
async def list_technical_analysis_records(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="每页条数"),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        data = await technical_analysis_service.list_generation_records(
            session=session,
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
        return ApiResponse.success_response(msg="获取成功", data=data)
    except Exception as e:
        logger.error(f"技术分析记录列表异常: {e}")
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get(
    "/records/{record_id}",
    summary="技术指标分析生成记录详情",
    description="根据记录 ID 返回当时保存的完整结果快照",
)
async def get_technical_analysis_record_detail(
    record_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    try:
        data = await technical_analysis_service.get_generation_record(
            session=session,
            user_id=current_user.id,
            record_id=record_id,
        )
        if not data:
            return ApiResponse.failed_response(
                msg="记录不存在或无权访问",
                code=ResponseCode.FAILED.value,
            )
        return ApiResponse.success_response(msg="获取成功", data=data)
    except Exception as e:
        logger.error(f"技术分析记录详情异常: {e}")
        return ApiResponse.failed_response(
            msg=f"获取失败: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get(
    "/indicators",
    summary="获取技术指标数据",
    description="""
仅获取技术指标计算结果，不包含 LLM 分析。

### 返回的指标
- 价格变化 (1d/7d/30d)
- 均线 (MA5/10/20/60, EMA5/10/20)
- RSI (7/14)
- MACD (DIF/DEA/柱状图)
- 布林带 (上轨/中轨/下轨/带宽)
- 斐波那契回撤
- ATR(14)
- 波动率
- 成交量比率
- 趋势强度判断
""",
)
async def get_indicators(
    symbol: str = Query(..., description="交易对，如 BTC-USDT"),
    timeframe: str = Query("4h", description="K线周期"),
    lookback_days: int = Query(
        30,
        ge=7,
        le=365,
        alias="lookbackDays",
        description="回溯天数（与 lookback_days 等价）",
    ),
    session: AsyncSession = Depends(get_db_session),
    current_user: UserModel = Depends(get_current_user),
):
    """获取技术指标数据（使用库内 K 线缓存，不足时从交易所补全）"""
    try:
        result = await technical_analysis_service.get_indicators(
            symbol=symbol,
            timeframe=timeframe,
            lookback_days=lookback_days,
            session=session,
        )

        if not result.get("success"):
            return ApiResponse.failed_response(
                msg=result.get("error", "获取指标失败"),
                code=ResponseCode.FAILED.value,
                data=result,
            )

        return ApiResponse.success_response(msg="获取成功", data=result)
    except Exception as e:
        logger.error(f"获取指标API异常: {e}")
        return ApiResponse.failed_response(
            msg=f"获取异常: {str(e)}",
            code=ResponseCode.SYSTEM_ERROR.value,
        )


@router.get(
    "/supported-timeframes",
    summary="获取支持的K线周期",
    description="返回所有支持的K线周期列表",
)
async def get_supported_timeframes(
    current_user: UserModel = Depends(get_current_user),
):
    """获取支持的K线周期"""
    return ApiResponse.success_response(
        msg="获取成功",
        data={
            "timeframes": [
                {"value": "1m", "label": "1分钟", "okx": "1m"},
                {"value": "5m", "label": "5分钟", "okx": "5m"},
                {"value": "15m", "label": "15分钟", "okx": "15m"},
                {"value": "30m", "label": "30分钟", "okx": "30m"},
                {"value": "1h", "label": "1小时", "okx": "1H"},
                {"value": "2h", "label": "2小时", "okx": "2H"},
                {"value": "4h", "label": "4小时", "okx": "4H"},
                {"value": "6h", "label": "6小时", "okx": "6H"},
                {"value": "12h", "label": "12小时", "okx": "12H"},
                {"value": "1d", "label": "1天", "okx": "1D"},
                {"value": "1w", "label": "1周", "okx": "1W"},
            ]
        },
    )


@router.get(
    "/supported-indicators",
    summary="获取支持的技术指标",
    description="返回所有支持的技术指标说明",
)
async def get_supported_indicators(
    current_user: UserModel = Depends(get_current_user),
):
    """获取支持的技术指标"""
    return ApiResponse.success_response(
        msg="获取成功",
        data={
            "indicators": {
                "trend": {
                    "name": "趋势指标",
                    "items": [
                        {"key": "ma5", "name": "MA5", "description": "5周期简单移动平均"},
                        {"key": "ma10", "name": "MA10", "description": "10周期简单移动平均"},
                        {"key": "ma20", "name": "MA20", "description": "20周期简单移动平均"},
                        {"key": "ma60", "name": "MA60", "description": "60周期简单移动平均"},
                        {"key": "ema5", "name": "EMA5", "description": "5周期指数移动平均"},
                        {"key": "ema10", "name": "EMA10", "description": "10周期指数移动平均"},
                        {"key": "ema20", "name": "EMA20", "description": "20周期指数移动平均"},
                    ],
                },
                "momentum": {
                    "name": "动量指标",
                    "items": [
                        {"key": "rsi7", "name": "RSI(7)", "description": "7周期相对强弱指数"},
                        {"key": "rsi14", "name": "RSI(14)", "description": "14周期相对强弱指数"},
                        {"key": "macd", "name": "MACD", "description": "指数平滑异同移动平均线"},
                    ],
                },
                "volatility": {
                    "name": "波动指标",
                    "items": [
                        {"key": "bollinger", "name": "布林带", "description": "布林带(20,2)"},
                        {"key": "atr14", "name": "ATR(14)", "description": "14周期平均真实波幅"},
                        {"key": "volatility", "name": "波动率", "description": "20周期价格波动率"},
                    ],
                },
                "support_resistance": {
                    "name": "支撑阻力",
                    "items": [
                        {"key": "fibonacci", "name": "斐波那契回撤", "description": "基于区间高低点的回撤位"},
                    ],
                },
            }
        },
    )
