#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2026/01/30
# @Author : AI Assistant
"""
预算预警服务
实现费用阈值检测和通知功能
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.inner_models.llm_monitor_model import (
    LLMUsageLog,
    LLMDailyStats,
    LLMBudgetAlertRule,
    LLMBudgetAlertHistory
)
from app.v1.schemas.llm_monitor_schema import (
    AlertRuleItem,
    AlertRuleListResponse,
    AlertRuleCreateRequest,
    AlertRuleUpdateRequest,
    AlertHistoryItem,
    AlertHistoryRequest,
    AlertHistoryResponse,
    PaginationInfo
)

logger = logging.getLogger(__name__)


class BudgetAlertService:
    """预算预警服务"""
    
    def __init__(self, session: AsyncSession):
        """
        初始化服务
        
        Args:
            session: 数据库会话
        """
        self.session = session
    
    # ========================================================================
    # 预警规则管理
    # ========================================================================
    
    async def get_alert_rules(
        self,
        is_active: Optional[bool] = None
    ) -> AlertRuleListResponse:
        """
        获取预警规则列表
        
        Args:
            is_active: 是否只返回启用的规则
            
        Returns:
            规则列表响应
        """
        query = select(LLMBudgetAlertRule)
        if is_active is not None:
            query = query.where(LLMBudgetAlertRule.is_active == is_active)
        query = query.order_by(desc(LLMBudgetAlertRule.created_at))
        
        result = await self.session.execute(query)
        items = result.scalars().all()
        
        rule_items = [
            AlertRuleItem(
                id=item.id,
                rule_name=item.rule_name,
                alert_type=item.alert_type,
                threshold_value=float(item.threshold_value or 0),
                llm_model=item.model_name,
                agent_name=item.agent_name,
                notify_channels=item.notify_channels or {},
                is_active=bool(item.is_active),
                cooldown_minutes=item.cooldown_minutes,
                created_at=item.created_at,
                updated_at=item.updated_at
            )
            for item in items
        ]
        
        return AlertRuleListResponse(
            items=rule_items,
            total=len(rule_items)
        )
    
    async def get_alert_rule_by_id(
        self,
        rule_id: int
    ) -> Optional[AlertRuleItem]:
        """根据ID获取预警规则"""
        query = select(LLMBudgetAlertRule).where(LLMBudgetAlertRule.id == rule_id)
        result = await self.session.execute(query)
        item = result.scalar_one_or_none()
        
        if not item:
            return None
        
        return AlertRuleItem(
            id=item.id,
            rule_name=item.rule_name,
            alert_type=item.alert_type,
            threshold_value=float(item.threshold_value or 0),
            llm_model=item.model_name,
            agent_name=item.agent_name,
            notify_channels=item.notify_channels or {},
            is_active=bool(item.is_active),
            cooldown_minutes=item.cooldown_minutes,
            created_at=item.created_at,
            updated_at=item.updated_at
        )
    
    async def create_alert_rule(
        self,
        request: AlertRuleCreateRequest
    ) -> AlertRuleItem:
        """
        创建预警规则
        
        Args:
            request: 创建请求
            
        Returns:
            创建的规则
        """
        rule = LLMBudgetAlertRule(
            rule_name=request.rule_name,
            alert_type=request.alert_type,
            threshold_value=Decimal(str(request.threshold_value)),
            model_name=request.llm_model,
            agent_name=request.agent_name,
            notify_channels=request.notify_channels,
            is_active=request.is_active,
            cooldown_minutes=request.cooldown_minutes
        )
        
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        
        return AlertRuleItem(
            id=rule.id,
            rule_name=rule.rule_name,
            alert_type=rule.alert_type,
            threshold_value=float(rule.threshold_value or 0),
            llm_model=rule.model_name,
            agent_name=rule.agent_name,
            notify_channels=rule.notify_channels or {},
            is_active=bool(rule.is_active),
            cooldown_minutes=rule.cooldown_minutes,
            created_at=rule.created_at,
            updated_at=rule.updated_at
        )
    
    async def update_alert_rule(
        self,
        rule_id: int,
        request: AlertRuleUpdateRequest
    ) -> Optional[AlertRuleItem]:
        """
        更新预警规则
        
        Args:
            rule_id: 规则ID
            request: 更新请求
            
        Returns:
            更新后的规则，如果不存在则返回None
        """
        query = select(LLMBudgetAlertRule).where(LLMBudgetAlertRule.id == rule_id)
        result = await self.session.execute(query)
        rule = result.scalar_one_or_none()
        
        if not rule:
            return None
        
        # 更新字段
        if request.rule_name is not None:
            rule.rule_name = request.rule_name
        if request.threshold_value is not None:
            rule.threshold_value = Decimal(str(request.threshold_value))
        if request.notify_channels is not None:
            rule.notify_channels = request.notify_channels
        if request.is_active is not None:
            rule.is_active = request.is_active
        if request.cooldown_minutes is not None:
            rule.cooldown_minutes = request.cooldown_minutes
        
        await self.session.flush()
        await self.session.refresh(rule)
        
        return AlertRuleItem(
            id=rule.id,
            rule_name=rule.rule_name,
            alert_type=rule.alert_type,
            threshold_value=float(rule.threshold_value or 0),
            llm_model=rule.model_name,
            agent_name=rule.agent_name,
            notify_channels=rule.notify_channels or {},
            is_active=bool(rule.is_active),
            cooldown_minutes=rule.cooldown_minutes,
            created_at=rule.created_at,
            updated_at=rule.updated_at
        )
    
    async def delete_alert_rule(
        self,
        rule_id: int
    ) -> bool:
        """
        删除预警规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            是否删除成功
        """
        stmt = delete(LLMBudgetAlertRule).where(LLMBudgetAlertRule.id == rule_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0
    
    # ========================================================================
    # 预警历史
    # ========================================================================
    
    async def get_alert_history(
        self,
        request: AlertHistoryRequest
    ) -> AlertHistoryResponse:
        """
        获取预警历史记录
        
        Args:
            request: 请求参数
            
        Returns:
            历史记录响应
        """
        # 构建查询条件
        conditions = []
        if request.start_time:
            conditions.append(LLMBudgetAlertHistory.created_at >= request.start_time)
        if request.end_time:
            conditions.append(LLMBudgetAlertHistory.created_at <= request.end_time)
        if request.rule_id:
            conditions.append(LLMBudgetAlertHistory.rule_id == request.rule_id)
        if request.alert_type:
            conditions.append(LLMBudgetAlertHistory.alert_type == request.alert_type)
        if request.notify_status:
            conditions.append(LLMBudgetAlertHistory.notify_status == request.notify_status)
        
        # 查询总数
        count_query = select(func.count(LLMBudgetAlertHistory.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # 查询数据（联合查询规则名称）
        query = select(
            LLMBudgetAlertHistory,
            LLMBudgetAlertRule.rule_name
        ).outerjoin(
            LLMBudgetAlertRule,
            LLMBudgetAlertHistory.rule_id == LLMBudgetAlertRule.id
        )
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(desc(LLMBudgetAlertHistory.created_at))
        query = query.offset((request.page - 1) * request.page_size).limit(request.page_size)
        
        result = await self.session.execute(query)
        rows = result.fetchall()
        
        history_items = [
            AlertHistoryItem(
                id=row[0].id,
                rule_id=row[0].rule_id,
                rule_name=row[1],
                alert_type=row[0].alert_type,
                current_value=float(row[0].current_value or 0),
                threshold_value=float(row[0].threshold_value or 0),
                alert_message=row[0].alert_message,
                notify_status=row[0].notify_status,
                notify_result=row[0].notify_result,
                created_at=row[0].created_at
            )
            for row in rows
        ]
        
        total_pages = (total + request.page_size - 1) // request.page_size
        
        return AlertHistoryResponse(
            items=history_items,
            pagination=PaginationInfo(
                page=request.page,
                page_size=request.page_size,
                total=total,
                total_pages=total_pages
            )
        )
    
    # ========================================================================
    # 预警检测
    # ========================================================================
    
    async def check_alerts(self) -> List[Dict[str, Any]]:
        """
        检测所有启用的预警规则
        
        Returns:
            触发的预警列表
        """
        # 获取所有启用的规则
        query = select(LLMBudgetAlertRule).where(LLMBudgetAlertRule.is_active == 1)
        result = await self.session.execute(query)
        rules = result.scalars().all()
        
        triggered_alerts = []
        
        for rule in rules:
            # 检查冷却时间
            if rule.last_triggered_at:
                cooldown_end = rule.last_triggered_at + timedelta(minutes=rule.cooldown_minutes)
                if datetime.now() < cooldown_end:
                    logger.debug(f"规则 {rule.rule_name} 在冷却期内，跳过检测")
                    continue
            
            # 根据预警类型获取当前值
            current_value = await self._get_current_value(rule)
            
            if current_value is None:
                continue
            
            # 检查是否超过阈值
            threshold = float(rule.threshold_value)
            if current_value >= threshold:
                # 触发预警
                alert_info = await self._trigger_alert(rule, current_value)
                triggered_alerts.append(alert_info)
        
        return triggered_alerts
    
    async def _get_current_value(
        self,
        rule: LLMBudgetAlertRule
    ) -> Optional[float]:
        """
        根据规则类型获取当前值
        
        Args:
            rule: 预警规则
            
        Returns:
            当前值
        """
        today = date.today()
        
        if rule.alert_type == "daily_cost":
            # 今日费用
            return await self._get_daily_cost(today, rule.model_name, rule.agent_name)
        
        elif rule.alert_type == "monthly_cost":
            # 本月费用
            month_start = today.replace(day=1)
            return await self._get_period_cost(month_start, today, rule.model_name, rule.agent_name)
        
        elif rule.alert_type == "single_request":
            # 单次请求费用 - 检查最近的请求
            return await self._get_max_single_request_cost(rule.model_name, rule.agent_name)
        
        return None
    
    async def _get_daily_cost(
        self,
        target_date: date,
        model_name: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> float:
        """获取指定日期的费用"""
        conditions = [LLMDailyStats.stat_date == target_date]
        if model_name:
            conditions.append(LLMDailyStats.model_name == model_name)
        if agent_name:
            conditions.append(LLMDailyStats.agent_name == agent_name)
        
        query = select(func.sum(LLMDailyStats.total_cost_cny)).where(and_(*conditions))
        result = await self.session.execute(query)
        cost = result.scalar()
        
        return float(cost or 0)
    
    async def _get_period_cost(
        self,
        start_date: date,
        end_date: date,
        model_name: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> float:
        """获取指定时间段的费用"""
        conditions = [
            LLMDailyStats.stat_date >= start_date,
            LLMDailyStats.stat_date <= end_date
        ]
        if model_name:
            conditions.append(LLMDailyStats.model_name == model_name)
        if agent_name:
            conditions.append(LLMDailyStats.agent_name == agent_name)
        
        query = select(func.sum(LLMDailyStats.total_cost_cny)).where(and_(*conditions))
        result = await self.session.execute(query)
        cost = result.scalar()
        
        return float(cost or 0)
    
    async def _get_max_single_request_cost(
        self,
        model_name: Optional[str] = None,
        agent_name: Optional[str] = None,
        hours: int = 1
    ) -> float:
        """获取最近一段时间内单次请求的最大费用"""
        start_time = datetime.now() - timedelta(hours=hours)
        
        conditions = [LLMUsageLog.created_at >= start_time]
        if model_name:
            conditions.append(LLMUsageLog.model_name == model_name)
        if agent_name:
            conditions.append(LLMUsageLog.agent_name == agent_name)
        
        query = select(func.max(LLMUsageLog.cost_cny)).where(and_(*conditions))
        result = await self.session.execute(query)
        cost = result.scalar()
        
        return float(cost or 0)
    
    async def _trigger_alert(
        self,
        rule: LLMBudgetAlertRule,
        current_value: float
    ) -> Dict[str, Any]:
        """
        触发预警
        
        Args:
            rule: 预警规则
            current_value: 当前值
            
        Returns:
            预警信息
        """
        # 生成预警消息
        alert_message = self._generate_alert_message(rule, current_value)
        
        # 记录预警历史
        history = LLMBudgetAlertHistory(
            rule_id=rule.id,
            alert_type=rule.alert_type,
            current_value=Decimal(str(current_value)),
            threshold_value=rule.threshold_value,
            alert_message=alert_message,
            notify_status="pending"
        )
        self.session.add(history)
        
        # 更新规则的上次触发时间
        rule.last_triggered_at = datetime.now()
        
        await self.session.flush()
        await self.session.refresh(history)
        
        # 发送通知
        notify_result = await self._send_notifications(rule, alert_message)
        
        # 更新通知状态
        history.notify_status = "success" if notify_result.get("success") else "failed"
        history.notify_result = notify_result
        
        logger.info(f"触发预警: {rule.rule_name}, 当前值: {current_value}, 阈值: {rule.threshold_value}")
        
        return {
            "rule_id": rule.id,
            "rule_name": rule.rule_name,
            "alert_type": rule.alert_type,
            "current_value": current_value,
            "threshold_value": float(rule.threshold_value),
            "alert_message": alert_message,
            "notify_result": notify_result
        }
    
    def _generate_alert_message(
        self,
        rule: LLMBudgetAlertRule,
        current_value: float
    ) -> str:
        """生成预警消息"""
        threshold = float(rule.threshold_value)
        
        type_names = {
            "daily_cost": "日费用",
            "monthly_cost": "月费用",
            "single_request": "单次请求费用"
        }
        type_name = type_names.get(rule.alert_type, rule.alert_type)
        
        message = f"【LLM 费用预警】{rule.rule_name}\n"
        message += f"预警类型: {type_name}\n"
        message += f"当前值: ¥{current_value:.4f}\n"
        message += f"阈值: ¥{threshold:.4f}\n"
        message += f"超出: ¥{(current_value - threshold):.4f}\n"
        
        if rule.model_name:
            message += f"模型: {rule.model_name}\n"
        if rule.agent_name:
            message += f"Agent: {rule.agent_name}\n"
        
        message += f"触发时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message
    
    async def _send_notifications(
        self,
        rule: LLMBudgetAlertRule,
        message: str
    ) -> Dict[str, Any]:
        """
        发送通知
        
        Args:
            rule: 预警规则
            message: 预警消息
            
        Returns:
            通知结果
        """
        result = {
            "success": False,
            "channels": {}
        }
        
        channels = rule.notify_channels or {}
        
        # 飞书 Webhook
        if "feishu_webhook" in channels:
            webhook_url = channels["feishu_webhook"]
            feishu_result = await self._send_feishu_notification(webhook_url, message)
            result["channels"]["feishu"] = feishu_result
            if feishu_result.get("success"):
                result["success"] = True
        
        # 邮件通知（如果配置了）
        if "email" in channels:
            emails = channels["email"]
            if isinstance(emails, list) and emails:
                email_result = await self._send_email_notification(emails, rule.rule_name, message)
                result["channels"]["email"] = email_result
                if email_result.get("success"):
                    result["success"] = True
        
        # 如果没有配置任何通知渠道，也标记为成功（只记录）
        if not channels:
            result["success"] = True
            result["channels"]["log"] = {"success": True, "message": "仅记录日志"}
        
        return result
    
    async def _send_feishu_notification(
        self,
        webhook_url: str,
        message: str
    ) -> Dict[str, Any]:
        """发送飞书通知"""
        try:
            import httpx
            
            payload = {
                "msg_type": "text",
                "content": {
                    "text": message
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") == 0 or data.get("StatusCode") == 0:
                    return {"success": True}
                else:
                    return {"success": False, "error": str(data)}
                    
        except Exception as e:
            logger.error(f"发送飞书通知失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_email_notification(
        self,
        emails: List[str],
        subject: str,
        message: str
    ) -> Dict[str, Any]:
        """发送邮件通知（需要配置 SMTP）"""
        # 邮件发送功能需要根据实际配置实现
        # 这里只是一个占位实现
        logger.info(f"邮件通知: {emails}, 主题: {subject}")
        return {"success": False, "error": "邮件发送功能未配置"}
    
    async def trigger_manual_check(
        self,
        rule_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        手动触发指定规则的检测
        
        Args:
            rule_id: 规则ID
            
        Returns:
            检测结果
        """
        query = select(LLMBudgetAlertRule).where(LLMBudgetAlertRule.id == rule_id)
        result = await self.session.execute(query)
        rule = result.scalar_one_or_none()
        
        if not rule:
            return None
        
        current_value = await self._get_current_value(rule)
        if current_value is None:
            return {"error": "无法获取当前值"}
        
        threshold = float(rule.threshold_value)
        
        if current_value >= threshold:
            # 触发预警
            alert_info = await self._trigger_alert(rule, current_value)
            return {
                "triggered": True,
                **alert_info
            }
        else:
            return {
                "triggered": False,
                "rule_id": rule.id,
                "rule_name": rule.rule_name,
                "current_value": current_value,
                "threshold_value": threshold,
                "message": f"当前值 ({current_value:.4f}) 未达到阈值 ({threshold:.4f})"
            }
