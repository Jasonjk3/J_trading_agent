#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
LLM 监控业务服务
封装业务逻辑层
"""
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.crud import llm_monitor_crud as crud
from app.v1.schemas.llm_monitor_schema import (
    UsageHistoryRequest,
    UsageHistoryResponse,
    UsageLogItem,
    RealtimeUsageResponse,
    RealtimeUsageData,
    TopAgentItem,
    DailyStatsRequest,
    DailyStatsResponse,
    DailyStatsItem,
    DailyStatsSummary,
    OverviewStatsResponse,
    ModelStatsResponse,
    ModelStatsItem,
    AgentStatsResponse,
    AgentStatsItem,
    CostSummaryRequest,
    CostSummaryResponse,
    CostBreakdownItem,
    CostPeriodSummary,
    CostModelItem,
    CostAgentItem,
    CostTrendRequest,
    CostTrendResponse,
    CostTrendItem,
    ModelCostConfigItem,
    ModelCostConfigListResponse,
    ModelCostConfigCreateRequest,
    ModelCostConfigUpdateRequest,
    PaginationInfo
)
from core.llm.base.cost_calculator import get_cost_calculator

logger = logging.getLogger(__name__)


class LLMMonitorService:
    """LLM 监控服务"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化服务
        
        Args:
            session: 数据库会话
        """
        self.session = session
    
    # ========================================================================
    # 使用量相关
    # ========================================================================
    
    async def get_usage_history(
        self,
        request: UsageHistoryRequest
    ) -> UsageHistoryResponse:
        """
        获取历史调用记录
        
        Args:
            request: 请求参数
            
        Returns:
            历史记录响应
        """
        items, total = await crud.get_usage_logs(
            session=self.session,
            start_time=request.start_time,
            end_time=request.end_time,
            model_name=request.llm_model,
            agent_name=request.agent_name,
            status=request.status,
            user_id=request.user_id,
            page=request.page,
            page_size=request.page_size
        )
        
        # 转换为响应模型
        log_items = [
            UsageLogItem(
                id=item.id,
                request_id=item.request_id,
                llm_model=item.model_name,
                llm_provider=item.model_provider,
                agent_name=item.agent_name,
                task_type=item.task_type,
                prompt_tokens=item.prompt_tokens,
                completion_tokens=item.completion_tokens,
                total_tokens=item.total_tokens,
                cost_usd=float(item.cost_usd or 0),
                cost_cny=float(item.cost_cny or 0),
                response_time_ms=item.response_time_ms,
                status=item.status,
                error_message=item.error_message,
                user_id=item.user_id,
                session_id=item.session_id,
                created_at=item.created_at,
                extra_data=item.extra_data
            )
            for item in items
        ]
        
        total_pages = (total + request.page_size - 1) // request.page_size
        
        return UsageHistoryResponse(
            items=log_items,
            pagination=PaginationInfo(
                page=request.page,
                page_size=request.page_size,
                total=total,
                total_pages=total_pages
            )
        )
    
    async def get_realtime_usage(self) -> RealtimeUsageResponse:
        """
        获取实时使用情况
        
        Returns:
            实时使用数据
        """
        now = datetime.now()
        today_start = datetime.combine(now.date(), datetime.min.time())
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        
        # 今日数据
        today_stats = await crud.get_realtime_usage_stats(
            self.session, today_start, now
        )
        
        # 当前小时数据
        hour_stats = await crud.get_realtime_usage_stats(
            self.session, hour_start, now
        )
        
        # 活跃模型
        active_models = await crud.get_active_models(
            self.session, today_start
        )
        
        # Top Agents
        top_agents_data = await crud.get_top_agents(
            self.session, today_start, limit=5
        )
        
        return RealtimeUsageResponse(
            today=RealtimeUsageData(**today_stats),
            current_hour=RealtimeUsageData(**hour_stats),
            active_models=active_models,
            top_agents=[
                TopAgentItem(name=a["name"], requests=a["requests"])
                for a in top_agents_data
            ]
        )
    
    # ========================================================================
    # 统计相关
    # ========================================================================
    
    async def get_daily_stats(
        self,
        request: DailyStatsRequest
    ) -> DailyStatsResponse:
        """
        获取每日统计
        
        Args:
            request: 请求参数
            
        Returns:
            每日统计响应
        """
        items = await crud.get_daily_stats(
            session=self.session,
            start_date=request.start_date,
            end_date=request.end_date,
            model_name=request.llm_model,
            agent_name=request.agent_name,
            group_by=request.group_by
        )
        
        # 计算汇总
        total_requests = sum(item.get("total_requests", 0) for item in items)
        total_tokens = sum(item.get("total_tokens", 0) for item in items)
        total_cost_usd = sum(item.get("cost_usd", 0) for item in items)
        total_cost_cny = sum(item.get("cost_cny", 0) for item in items)
        
        # 转换为响应模型
        stats_items = [
            DailyStatsItem(
                stat_date=item["date"],
                llm_model=item.get("model_name"),
                agent_name=item.get("agent_name"),
                total_requests=item.get("total_requests", 0),
                success_requests=item.get("success_requests", 0),
                failed_requests=item.get("failed_requests", 0),
                total_tokens=item.get("total_tokens", 0),
                prompt_tokens=item.get("prompt_tokens", 0),
                completion_tokens=item.get("completion_tokens", 0),
                cost_usd=item.get("cost_usd", 0),
                cost_cny=item.get("cost_cny", 0),
                avg_response_time_ms=item.get("avg_response_time_ms", 0)
            )
            for item in items
        ]
        
        return DailyStatsResponse(
            items=stats_items,
            summary=DailyStatsSummary(
                total_requests=total_requests,
                total_tokens=total_tokens,
                total_cost_usd=total_cost_usd,
                total_cost_cny=total_cost_cny
            )
        )
    
    async def get_overview_stats(self) -> OverviewStatsResponse:
        """
        获取总览统计
        
        Returns:
            总览统计响应
        """
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        
        # 今日统计
        today_items = await crud.get_daily_stats(
            self.session, today, today
        )
        today_summary = self._calculate_summary(today_items)
        
        # 本周统计
        week_items = await crud.get_daily_stats(
            self.session, week_start, today
        )
        week_summary = self._calculate_summary(week_items)
        
        # 本月统计
        month_items = await crud.get_daily_stats(
            self.session, month_start, today
        )
        month_summary = self._calculate_summary(month_items)
        
        # 计算总体成功率和平均响应时间
        total_requests = sum(item.get("total_requests", 0) for item in month_items)
        total_success = sum(item.get("success_requests", 0) for item in month_items)
        success_rate = total_success / total_requests if total_requests > 0 else 1.0
        
        avg_response_times = [item.get("avg_response_time_ms", 0) for item in month_items if item.get("avg_response_time_ms")]
        avg_response_time = int(sum(avg_response_times) / len(avg_response_times)) if avg_response_times else 0
        
        return OverviewStatsResponse(
            today=DailyStatsSummary(**today_summary),
            this_week=DailyStatsSummary(**week_summary),
            this_month=DailyStatsSummary(**month_summary),
            success_rate=round(success_rate, 4),
            avg_response_time_ms=avg_response_time
        )
    
    def _calculate_summary(self, items: List[Dict]) -> Dict:
        """计算汇总数据"""
        return {
            "total_requests": sum(item.get("total_requests", 0) for item in items),
            "total_tokens": sum(item.get("total_tokens", 0) for item in items),
            "total_cost_usd": sum(item.get("cost_usd", 0) for item in items),
            "total_cost_cny": sum(item.get("cost_cny", 0) for item in items)
        }
    
    async def get_stats_by_model(
        self,
        start_date: date,
        end_date: date
    ) -> ModelStatsResponse:
        """
        按模型获取统计
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            模型统计响应
        """
        items = await crud.get_stats_by_model(
            self.session, start_date, end_date
        )
        
        # 获取模型提供商信息
        cost_calculator = get_cost_calculator()
        
        stats_items = []
        for item in items:
            pricing = cost_calculator.get_pricing(item["model_name"])
            provider = pricing.provider if pricing else "unknown"
            
            stats_items.append(ModelStatsItem(
                llm_model=item["model_name"],
                llm_provider=provider,
                total_requests=item["total_requests"],
                total_tokens=item["total_tokens"],
                cost_cny=item["cost_cny"],
                avg_response_time_ms=item["avg_response_time_ms"],
                success_rate=item["success_rate"]
            ))
        
        return ModelStatsResponse(
            items=stats_items,
            total_models=len(stats_items)
        )
    
    async def get_stats_by_agent(
        self,
        start_date: date,
        end_date: date
    ) -> AgentStatsResponse:
        """
        按Agent获取统计
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            Agent统计响应
        """
        items = await crud.get_stats_by_agent(
            self.session, start_date, end_date
        )
        
        stats_items = [
            AgentStatsItem(
                agent_name=item["agent_name"],
                total_requests=item["total_requests"],
                total_tokens=item["total_tokens"],
                cost_cny=item["cost_cny"],
                avg_response_time_ms=item["avg_response_time_ms"],
                success_rate=item["success_rate"],
                primary_model=item["primary_model"]
            )
            for item in items
        ]
        
        return AgentStatsResponse(
            items=stats_items,
            total_agents=len(stats_items)
        )
    
    # ========================================================================
    # 费用相关
    # ========================================================================
    
    async def get_cost_summary(
        self,
        request: CostSummaryRequest
    ) -> CostSummaryResponse:
        """
        获取费用汇总
        
        Args:
            request: 请求参数
            
        Returns:
            费用汇总响应（包含今日/本周/本月费用以及按模型/Agent分组）
        """
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        
        # 并发获取三个时间段的费用以及按模型、Agent分组的数据
        today_data = await crud.get_cost_summary(
            session=self.session,
            start_date=today,
            end_date=today,
            group_by=None
        )
        
        week_data = await crud.get_cost_summary(
            session=self.session,
            start_date=week_start,
            end_date=today,
            group_by=None
        )
        
        month_data = await crud.get_cost_summary(
            session=self.session,
            start_date=month_start,
            end_date=today,
            group_by=None
        )
        
        # 获取按模型分组的数据
        model_data = await crud.get_cost_summary(
            session=self.session,
            start_date=month_start,
            end_date=today,
            group_by="model"
        )
        
        # 获取按Agent分组的数据
        agent_data = await crud.get_cost_summary(
            session=self.session,
            start_date=month_start,
            end_date=today,
            group_by="agent"
        )
        
        # 计算today tokens（需要从日志表获取）
        today_tokens = await crud.get_tokens_for_period(self.session, today, today)
        week_tokens = await crud.get_tokens_for_period(self.session, week_start, today)
        month_tokens = await crud.get_tokens_for_period(self.session, month_start, today)
        
        # 构建按模型分组的列表
        by_model = [
            CostModelItem(
                llm_model=item["name"],
                cost_cny=item["cost_cny"],
                percentage=item["percentage"]
            )
            for item in model_data.get("breakdown", [])
        ]
        
        # 构建按Agent分组的列表
        by_agent = [
            CostAgentItem(
                agent_name=item["name"],
                cost_cny=item["cost_cny"],
                percentage=item["percentage"]
            )
            for item in agent_data.get("breakdown", [])
        ]
        
        # 保留原有的breakdown以向后兼容
        breakdown_items = [
            CostBreakdownItem(
                name=item["name"],
                cost_usd=item["cost_usd"],
                cost_cny=item["cost_cny"],
                percentage=item["percentage"]
            )
            for item in model_data.get("breakdown", [])
        ]
        
        return CostSummaryResponse(
            today=CostPeriodSummary(
                cost_cny=today_data["total_cost_cny"],
                cost_usd=today_data["total_cost_usd"],
                tokens=today_tokens
            ),
            this_week=CostPeriodSummary(
                cost_cny=week_data["total_cost_cny"],
                cost_usd=week_data["total_cost_usd"],
                tokens=week_tokens
            ),
            this_month=CostPeriodSummary(
                cost_cny=month_data["total_cost_cny"],
                cost_usd=month_data["total_cost_usd"],
                tokens=month_tokens
            ),
            by_model=by_model,
            by_agent=by_agent,
            total_cost_usd=month_data["total_cost_usd"],
            total_cost_cny=month_data["total_cost_cny"],
            breakdown=breakdown_items
        )
    
    async def get_cost_trend(
        self,
        request: CostTrendRequest
    ) -> CostTrendResponse:
        """
        获取费用趋势
        
        Args:
            request: 请求参数
            
        Returns:
            费用趋势响应
        """
        items = await crud.get_cost_trend(
            session=self.session,
            start_date=request.start_date,
            end_date=request.end_date,
            granularity=request.granularity
        )
        
        trend_items = [
            CostTrendItem(
                period=item["period"],
                cost_usd=item["cost_usd"],
                cost_cny=item["cost_cny"],
                tokens=item["tokens"],
                requests=item["requests"]
            )
            for item in items
        ]
        
        total_cost_cny = sum(item["cost_cny"] for item in items)
        
        return CostTrendResponse(
            items=trend_items,
            total_cost_cny=total_cost_cny
        )
    
    # ========================================================================
    # 配置管理（已迁移到公共模块模型管理，此处保留兼容性接口）
    # ========================================================================
    
    async def get_model_configs(
        self,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> ModelCostConfigListResponse:
        """
        获取模型费用配置列表
        
        注意：费用配置已统一到公共模块模型管理（model_compare_model 表）
        此接口从模型管理表读取费用信息，保持兼容性
        
        Args:
            model_name: 模型名称（模糊匹配）
            provider: 提供商（模糊匹配）
            is_active: 是否生效
            
        Returns:
            配置列表响应
        """
        from sqlalchemy import select, and_
        from models.inner_models.model_compare_model import ModelCompareModel
        from datetime import date
        
        # 从模型管理表读取
        query = select(ModelCompareModel)
        conditions = []
        
        if model_name:
            conditions.append(ModelCompareModel.model_id.like(f"%{model_name}%"))
        if provider:
            conditions.append(ModelCompareModel.provider.like(f"%{provider}%"))
        if is_active is not None:
            conditions.append(ModelCompareModel.is_active == (1 if is_active else 0))
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(ModelCompareModel.provider, ModelCompareModel.model_id)
        
        result = await self.session.execute(query)
        models = result.scalars().all()
        
        # 转换为费用配置响应格式
        config_items = [
            ModelCostConfigItem(
                id=model.id,
                llm_model=model.model_id,
                provider=model.provider,
                input_price_per_1m=float(model.input_price_per_1m or 0),
                output_price_per_1m=float(model.output_price_per_1m or 0),
                currency="USD",
                exchange_rate=7.25,  # 默认汇率
                effective_date=date.today(),  # 使用当前日期
                is_active=bool(model.is_active),
                created_at=model.created_at,
                updated_at=model.updated_at
            )
            for model in models
        ]
        
        return ModelCostConfigListResponse(
            items=config_items,
            total=len(config_items)
        )
    
    async def create_model_config(
        self,
        request: ModelCostConfigCreateRequest
    ) -> ModelCostConfigItem:
        """
        创建模型费用配置
        
        注意：费用配置已统一到公共模块模型管理
        此接口会在模型管理表中创建或更新模型记录
        
        Args:
            request: 创建请求
            
        Returns:
            创建的配置
        """
        from sqlalchemy import select
        from models.inner_models.model_compare_model import ModelCompareModel
        
        # 检查模型是否已存在
        query = select(ModelCompareModel).where(
            ModelCompareModel.model_id == request.llm_model
        )
        result = await self.session.execute(query)
        existing_model = result.scalar_one_or_none()
        
        if existing_model:
            # 更新现有模型的费用配置
            existing_model.input_price_per_1m = request.input_price_per_1m
            existing_model.output_price_per_1m = request.output_price_per_1m
            existing_model.provider = request.provider
            existing_model.is_active = 1 if request.is_active else 0
            await self.session.commit()
            await self.session.refresh(existing_model)
            model = existing_model
        else:
            # 创建新模型
            model = ModelCompareModel(
                model_id=request.llm_model,
                name=request.llm_model,
                provider=request.provider,
                input_price_per_1m=request.input_price_per_1m,
                output_price_per_1m=request.output_price_per_1m,
                is_active=1 if request.is_active else 0,
            )
            self.session.add(model)
            await self.session.commit()
            await self.session.refresh(model)
        
        # 更新内存中的费用计算器配置
        if model.is_active:
            cost_calculator = get_cost_calculator()
            cost_calculator.update_pricing_from_db(
                model_name=model.model_id,
                provider=model.provider,
                input_price_per_1m=float(model.input_price_per_1m),
                output_price_per_1m=float(model.output_price_per_1m),
                exchange_rate=7.25,
            )
        
        return ModelCostConfigItem(
            id=model.id,
            llm_model=model.model_id,
            provider=model.provider,
            input_price_per_1m=float(model.input_price_per_1m or 0),
            output_price_per_1m=float(model.output_price_per_1m or 0),
            currency="USD",
            exchange_rate=7.25,
            effective_date=request.effective_date,
            is_active=bool(model.is_active),
            created_at=model.created_at,
            updated_at=model.updated_at
        )
    
    async def update_model_config(
        self,
        config_id: int,
        request: ModelCostConfigUpdateRequest
    ) -> Optional[ModelCostConfigItem]:
        """
        更新模型费用配置
        
        注意：费用配置已统一到公共模块模型管理
        此接口会更新模型管理表中的费用信息
        
        Args:
            config_id: 配置ID（对应 model_compare_model.id）
            request: 更新请求
            
        Returns:
            更新后的配置，如果不存在则返回None
        """
        from sqlalchemy import select
        from models.inner_models.model_compare_model import ModelCompareModel
        from datetime import date
        
        # 查找模型
        query = select(ModelCompareModel).where(ModelCompareModel.id == config_id)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        
        if not model:
            return None
        
        # 更新费用字段
        if request.input_price_per_1m is not None:
            model.input_price_per_1m = request.input_price_per_1m
        if request.output_price_per_1m is not None:
            model.output_price_per_1m = request.output_price_per_1m
        if request.is_active is not None:
            model.is_active = 1 if request.is_active else 0
        
        await self.session.commit()
        await self.session.refresh(model)
        
        # 更新内存中的费用计算器配置
        if model.is_active:
            cost_calculator = get_cost_calculator()
            cost_calculator.update_pricing_from_db(
                model_name=model.model_id,
                provider=model.provider,
                input_price_per_1m=float(model.input_price_per_1m),
                output_price_per_1m=float(model.output_price_per_1m),
                exchange_rate=7.25,
            )
        
        return ModelCostConfigItem(
            id=model.id,
            llm_model=model.model_id,
            provider=model.provider,
            input_price_per_1m=float(model.input_price_per_1m or 0),
            output_price_per_1m=float(model.output_price_per_1m or 0),
            currency="USD",
            exchange_rate=7.25,
            effective_date=date.today(),
            is_active=bool(model.is_active),
            created_at=model.created_at,
            updated_at=model.updated_at
        )
    
    async def delete_model_config(self, config_id: int) -> bool:
        """
        删除模型费用配置
        
        注意：费用配置已统一到公共模块模型管理
        此接口不会真正删除模型，而是将模型的费用设为0并禁用
        如需删除模型，请使用模型管理接口
        
        Args:
            config_id: 配置ID（对应 model_compare_model.id）
            
        Returns:
            是否操作成功
        """
        from sqlalchemy import select
        from models.inner_models.model_compare_model import ModelCompareModel
        
        # 查找模型
        query = select(ModelCompareModel).where(ModelCompareModel.id == config_id)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        
        if not model:
            return False
        
        # 清空费用信息（而非删除模型）
        model.input_price_per_1m = 0
        model.output_price_per_1m = 0
        
        await self.session.commit()
        
        # 从费用计算器缓存中移除
        cost_calculator = get_cost_calculator()
        cost_calculator.remove_pricing(model.model_id)
        
        return True
