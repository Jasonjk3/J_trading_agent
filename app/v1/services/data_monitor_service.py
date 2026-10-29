"""Persist monitoring configuration and evaluate due market conditions."""
import asyncio
import math
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import delete, func, or_, select, update

from app.v1.crud.message_push_crud import get_config
from app.v1.services.market_service import MarketService
from app.v1.services.message_push_service import MessagePushService
from models.inner_models.data_monitor_model import (
    MonitorEventModel, MonitorRuleModel, MonitorSampleModel, MonitorTaskModel, MonitorTemplateModel,
)
from models.inner_models.message_push_model import MessagePushConfigModel


PRESET_RULES = [
    {"id": "preset-price-high", "name": "价格突破", "description": "最新价格高于目标价", "metric": "price", "operator": ">", "threshold": 70000},
    {"id": "preset-price-low", "name": "价格跌破", "description": "最新价格低于目标价", "metric": "price", "operator": "<", "threshold": 60000},
    {"id": "preset-change", "name": "涨跌幅异动", "description": "24 小时涨跌幅超过阈值", "metric": "change", "operator": ">", "threshold": 5},
    {"id": "preset-volume", "name": "成交量异常", "description": "24 小时成交额超过阈值（USDT）", "metric": "volume", "operator": ">", "threshold": 1000000},
    {"id": "preset-rsi", "name": "RSI 超买", "description": "15 分钟 K 线 RSI(14) 超过阈值", "metric": "rsi", "operator": ">", "threshold": 75},
    {"id": "preset-daily-report", "name": "每日定时汇报", "description": "每天指定时段内按间隔汇报最新价格", "ruleType": "scheduled", "metric": "price", "operator": ">", "threshold": 0, "startTime": "09:00", "endTime": "18:00", "reportIntervalMinutes": 60},
    {"id": "preset-movement-percent", "name": "短时涨跌提醒", "description": "1 小时内价格涨跌达到 3%", "ruleType": "movement", "metric": "price", "operator": ">", "threshold": 3, "windowMinutes": 60, "movementUnit": "percent", "movementDirection": "either"},
    {"id": "preset-movement-amount", "name": "价格金额浮动", "description": "1 小时内价格涨跌达到 100 USDT", "ruleType": "movement", "metric": "price", "operator": ">", "threshold": 100, "windowMinutes": 60, "movementUnit": "amount", "movementDirection": "either"},
]
PRESET_TEMPLATES = [
    {"id": "preset-standard", "name": "监控提醒", "messageType": "card", "title": "{{symbol}} 监控提醒", "content": "{{symbol}} 的 {{metric}} 当前值 {{current_value}}，已触发阈值 {{threshold}}。\n时间：{{triggered_at}}"},
    {"id": "preset-simple", "name": "简洁通知", "messageType": "text", "title": "{{symbol}} 监控提醒", "content": "{{symbol}} {{metric}}={{current_value}}，阈值 {{threshold}}（{{event_type}}）"},
    {"id": "preset-report", "name": "定时行情汇报", "messageType": "text", "title": "{{symbol}} 行情汇报", "content": "{{symbol}} 最新价格 {{current_value}} USDT\n时间：{{triggered_at}}"},
    {"id": "preset-movement", "name": "价格浮动提醒", "messageType": "text", "title": "{{symbol}} 价格浮动", "content": "{{symbol}} 在 {{window_minutes}} 分钟内由 {{baseline_value}} 变为 {{current_value}} USDT，浮动 {{movement_amount}} USDT（{{movement_percent}}%）。\n时间：{{triggered_at}}"},
]
FIELD_MAP = {
    "frequencySeconds": "frequency_seconds", "ruleId": "rule_id", "pushConfigId": "push_config_id",
    "templateId": "template_id", "cooldownSeconds": "cooldown_seconds", "recoveryNotice": "recovery_notice",
    "ruleType": "rule_type", "windowMinutes": "window_minutes", "movementUnit": "movement_unit",
    "movementDirection": "movement_direction", "startTime": "start_time", "endTime": "end_time",
    "reportIntervalMinutes": "report_interval_minutes",
}
RULE_FIELDS = ("ruleType", "windowMinutes", "movementUnit", "movementDirection", "startTime", "endTime", "reportIntervalMinutes")


def extra_fields(obj):
    if isinstance(obj, dict):
        return {key: obj.get(key, "threshold" if key == "ruleType" else None) for key in RULE_FIELDS}
    return {key: getattr(obj, FIELD_MAP[key]) for key in RULE_FIELDS}


def serialize_rule(rule):
    if isinstance(rule, dict):
        return {**rule, **extra_fields(rule), "system": True, "usage": 0}
    return {"id": rule.id, "name": rule.name, "description": rule.description, "metric": rule.metric,
            "operator": rule.operator, "threshold": rule.threshold, **extra_fields(rule), "system": False, "usage": 0}


def serialize_template(template):
    if isinstance(template, dict):
        return {**template, "system": True, "usage": 0}
    return {"id": template.id, "name": template.name, "messageType": template.message_type,
            "title": template.title, "content": template.content, "system": False, "usage": 0}


def serialize_task(task, rule_name="", channel_name="", template_name=""):
    return {"id": task.id, "name": task.name, "exchange": task.exchange, "symbol": task.symbol,
            "frequencySeconds": task.frequency_seconds, "ruleId": task.rule_id, "ruleName": rule_name,
            "metric": task.metric, "operator": task.operator, "threshold": task.threshold,
            **extra_fields(task),
            "pushConfigId": task.push_config_id, "channelName": channel_name,
            "templateId": task.template_id, "templateName": template_name,
            "cooldownSeconds": task.cooldown_seconds, "recoveryNotice": task.recovery_notice,
            "enabled": task.enabled, "lastValue": task.last_value,
            "lastCheckedAt": task.last_checked_at.isoformat() if task.last_checked_at else None,
            "lastTriggeredAt": task.last_triggered_at.isoformat() if task.last_triggered_at else None,
            "lastError": task.last_error}


class DataMonitorService:
    async def list_rules(self, session, user_id):
        rows = (await session.execute(select(MonitorRuleModel).where(MonitorRuleModel.user_id == user_id).order_by(MonitorRuleModel.created_at.desc()))).scalars().all()
        result = [serialize_rule(item) for item in PRESET_RULES] + [serialize_rule(row) for row in rows]
        counts = (await session.execute(select(MonitorTaskModel.rule_id, func.count()).where(MonitorTaskModel.user_id == user_id).group_by(MonitorTaskModel.rule_id))).all()
        usage = dict(counts)
        for item in result:
            item["usage"] = usage.get(item["id"], 0)
        return result

    async def list_templates(self, session, user_id):
        rows = (await session.execute(select(MonitorTemplateModel).where(MonitorTemplateModel.user_id == user_id).order_by(MonitorTemplateModel.created_at.desc()))).scalars().all()
        result = [serialize_template(item) for item in PRESET_TEMPLATES] + [serialize_template(row) for row in rows]
        counts = (await session.execute(select(MonitorTaskModel.template_id, func.count()).where(MonitorTaskModel.user_id == user_id).group_by(MonitorTaskModel.template_id))).all()
        usage = dict(counts)
        for item in result:
            item["usage"] = usage.get(item["id"], 0)
        return result

    async def list_tasks(self, session, user_id):
        tasks = (await session.execute(select(MonitorTaskModel).where(MonitorTaskModel.user_id == user_id).order_by(MonitorTaskModel.created_at.desc()))).scalars().all()
        rules = {item["id"]: item["name"] for item in await self.list_rules(session, user_id)}
        templates = {item["id"]: item["name"] for item in await self.list_templates(session, user_id)}
        configs = (await session.execute(select(MessagePushConfigModel).where(MessagePushConfigModel.user_id == user_id))).scalars().all()
        channels = {item.id: item.name for item in configs}
        return [serialize_task(item, rules.get(item.rule_id, "自定义条件"), channels.get(item.push_config_id, "已删除渠道"), templates.get(item.template_id, "已删除模板")) for item in tasks]

    async def get_task(self, session, user_id, task_id):
        return (await session.execute(select(MonitorTaskModel).where(MonitorTaskModel.id == task_id, MonitorTaskModel.user_id == user_id))).scalar_one_or_none()

    async def validate_references(self, session, user_id, data):
        config = await get_config(session, data["pushConfigId"], user_id)
        if not config or not config.enabled:
            raise ValueError("请选择已启用的推送渠道")
        if data["templateId"] not in {item["id"] for item in await self.list_templates(session, user_id)}:
            raise ValueError("消息模板不存在")
        if data.get("ruleId") and data["ruleId"] not in {item["id"] for item in await self.list_rules(session, user_id)}:
            raise ValueError("监控规则不存在")

    async def save_task(self, session, user_id, data, task=None):
        await self.validate_references(session, user_id, data)
        if task is None:
            task = MonitorTaskModel(id=str(uuid.uuid4()), user_id=user_id)
            session.add(task)
        for key, value in data.items():
            setattr(task, FIELD_MAP.get(key, key), value)
        task.updated_at = datetime.now()
        task.next_check_at = datetime.now() if task.enabled else None
        task.condition_active = False
        task.last_value = None
        task.last_triggered_at = None
        await session.execute(delete(MonitorSampleModel).where(MonitorSampleModel.task_id == task.id))
        await session.flush()
        return task

    async def save_rule(self, session, user_id, data):
        rule = MonitorRuleModel(id=str(uuid.uuid4()), user_id=user_id,
                                **{FIELD_MAP.get(key, key): value for key, value in data.items()})
        session.add(rule)
        await session.flush()
        return serialize_rule(rule)

    async def save_template(self, session, user_id, data):
        template = MonitorTemplateModel(id=str(uuid.uuid4()), user_id=user_id, name=data["name"], message_type=data["messageType"], title=data["title"], content=data["content"])
        session.add(template)
        await session.flush()
        return serialize_template(template)

    async def remove_rule(self, session, user_id, rule_id):
        rule = (await session.execute(select(MonitorRuleModel).where(MonitorRuleModel.id == rule_id, MonitorRuleModel.user_id == user_id))).scalar_one_or_none()
        if not rule:
            raise ValueError("自定义规则不存在")
        count = (await session.execute(select(func.count()).select_from(MonitorTaskModel).where(MonitorTaskModel.user_id == user_id, MonitorTaskModel.rule_id == rule_id))).scalar() or 0
        if count:
            raise ValueError("规则已被监控任务使用")
        await session.delete(rule)

    async def remove_template(self, session, user_id, template_id):
        template = (await session.execute(select(MonitorTemplateModel).where(MonitorTemplateModel.id == template_id, MonitorTemplateModel.user_id == user_id))).scalar_one_or_none()
        if not template:
            raise ValueError("自定义模板不存在")
        count = (await session.execute(select(func.count()).select_from(MonitorTaskModel).where(MonitorTaskModel.user_id == user_id, MonitorTaskModel.template_id == template_id))).scalar() or 0
        if count:
            raise ValueError("模板已被监控任务使用")
        await session.delete(template)

    async def get_events(self, session, user_id, task_id=None):
        query = select(MonitorEventModel).where(MonitorEventModel.user_id == user_id)
        if task_id:
            query = query.where(MonitorEventModel.task_id == task_id)
        rows = (await session.execute(query.order_by(MonitorEventModel.created_at.desc()).limit(100))).scalars().all()
        return [{"id": row.id, "taskId": row.task_id, "eventType": row.event_type, "value": row.value,
                 "success": row.success, "error": row.error, "createdAt": row.created_at.isoformat()} for row in rows]

    async def get_summary(self, session, user_id):
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_triggers = (await session.execute(
            select(func.count()).select_from(MonitorEventModel).where(
                MonitorEventModel.user_id == user_id,
                MonitorEventModel.event_type.in_(("trigger", "report")),
                MonitorEventModel.created_at >= today,
            )
        )).scalar() or 0
        results = (await session.execute(
            select(MonitorEventModel.success).where(MonitorEventModel.user_id == user_id)
            .order_by(MonitorEventModel.created_at.desc()).limit(100)
        )).scalars().all()
        return {"todayTriggers": today_triggers,
                "pushSuccessRate": round(sum(bool(result) for result in results) / len(results) * 100) if results else None}


def condition_matches(value: float, threshold: float, operator: str, previous: float | None) -> bool:
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == "cross_up":
        return previous is not None and previous <= threshold < value
    if operator == "cross_down":
        return previous is not None and previous >= threshold > value
    return False


def trigger_due(value: float, threshold: float, operator: str, previous: float | None,
                active: bool, last_triggered_at: datetime | None, cooldown_seconds: int,
                now: datetime) -> bool:
    if operator in ("cross_up", "cross_down"):
        return condition_matches(value, threshold, operator, previous)
    matched = condition_matches(value, threshold, operator, previous)
    return matched and (last_triggered_at is None or
                        (now - last_triggered_at).total_seconds() >= cooldown_seconds)


def render_template(value: str, context: dict[str, str]) -> str:
    return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", lambda match: context.get(match.group(1), ""), value)


def scheduled_slot(now: datetime, start_time: str, end_time: str, interval_minutes: int) -> datetime | None:
    """Return the active report slot, anchored to each daily window's start."""
    start_hour, start_minute = map(int, start_time.split(":"))
    end_hour, end_minute = map(int, end_time.split(":"))
    for day in (now.date(), (now - timedelta(days=1)).date()):
        start = datetime.combine(day, datetime.min.time()).replace(hour=start_hour, minute=start_minute)
        end = datetime.combine(day, datetime.min.time()).replace(hour=end_hour, minute=end_minute)
        if end <= start:
            end += timedelta(days=1)
        if start <= now < end:
            elapsed = int((now - start).total_seconds() // 60)
            return start + timedelta(minutes=(elapsed // interval_minutes) * interval_minutes)
    return None


def movement_values(current: float, baseline: float, direction: str, unit: str, threshold: float):
    amount = current - baseline
    percent = amount / baseline * 100 if baseline > 0 else 0.0
    comparison = percent if unit == "percent" else amount
    matched = (comparison >= threshold if direction == "up" else
               comparison <= -threshold if direction == "down" else
               abs(comparison) >= threshold)
    return matched, amount, percent


async def evaluate_task(db, task_id: str):
    service = DataMonitorService()
    push_service = MessagePushService()
    market = MarketService()
    async with db.get_session() as session:
        task = (await session.execute(select(MonitorTaskModel).where(MonitorTaskModel.id == task_id))).scalar_one_or_none()
        if not task or not task.enabled:
            return
        now = datetime.now()
        claim = await session.execute(update(MonitorTaskModel).where(MonitorTaskModel.id == task_id, MonitorTaskModel.enabled.is_(True), or_(MonitorTaskModel.next_check_at.is_(None), MonitorTaskModel.next_check_at <= now)).values(next_check_at=now + timedelta(seconds=task.frequency_seconds)))
        if not claim.rowcount:
            return
        await session.commit()

    try:
        if task.rule_type == "scheduled":
            slot = scheduled_slot(datetime.now(), task.start_time, task.end_time, task.report_interval_minutes)
            if slot is None or (task.last_triggered_at and task.last_triggered_at >= slot):
                return
        if task.metric == "rsi" and task.rule_type == "threshold":
            data = await market.get_indicators(task.symbol, "15m")
            value = float(data["rsi14"])
        else:
            ticker = await market._get_market_service().get_ticker(task.symbol)
            if task.rule_type != "threshold" or task.metric == "price":
                value = float(ticker["last"])
            elif task.metric == "change":
                opening = float(ticker["open24h"])
                if opening <= 0:
                    raise ValueError("行情缺少有效的 24 小时开盘价")
                value = (float(ticker["last"]) - opening) / opening * 100
            else:
                value = float(ticker["volCcy24h"])
        if not math.isfinite(value):
            raise ValueError("行情值无效")
        now = datetime.now()
        async with db.get_session() as session:
            task = (await session.execute(select(MonitorTaskModel).where(MonitorTaskModel.id == task_id))).scalar_one_or_none()
            if not task or not task.enabled:
                return
            previous = task.last_value
            baseline = None
            amount = percent = 0.0
            if task.rule_type == "movement":
                cutoff = now - timedelta(minutes=task.window_minutes)
                tolerance = timedelta(seconds=max(task.frequency_seconds * 2, 60))
                baseline_sample = (await session.execute(
                    select(MonitorSampleModel).where(MonitorSampleModel.task_id == task.id,
                        MonitorSampleModel.observed_at <= cutoff,
                        MonitorSampleModel.observed_at >= cutoff - tolerance)
                    .order_by(MonitorSampleModel.observed_at.desc()).limit(1)
                )).scalar_one_or_none()
                session.add(MonitorSampleModel(id=str(uuid.uuid4()), task_id=task.id, observed_at=now, price=value))
                await session.execute(delete(MonitorSampleModel).where(
                    MonitorSampleModel.task_id == task.id,
                    MonitorSampleModel.observed_at < cutoff - tolerance))
                baseline = baseline_sample.price if baseline_sample else None
                if baseline is None:
                    task.last_value = value
                    task.last_checked_at = now
                    task.last_error = None
                    return
                matched, amount, percent = movement_values(value, baseline, task.movement_direction,
                    task.movement_unit, task.threshold)
            elif task.rule_type == "scheduled":
                slot = scheduled_slot(now, task.start_time, task.end_time, task.report_interval_minutes)
                matched = slot is not None and (task.last_triggered_at is None or task.last_triggered_at < slot)
            else:
                matched = (value > task.threshold if task.operator == "cross_up" else
                           value < task.threshold if task.operator == "cross_down" else
                           condition_matches(value, task.threshold, task.operator, previous))
            event_type = None
            if task.rule_type == "scheduled" and matched:
                event_type = "report"
            elif task.rule_type == "movement" and matched and (
                task.last_triggered_at is None or (now - task.last_triggered_at).total_seconds() >= task.cooldown_seconds):
                event_type = "trigger"
            elif task.rule_type == "threshold" and trigger_due(value, task.threshold, task.operator, previous,
                           task.condition_active, task.last_triggered_at, task.cooldown_seconds, now):
                event_type = "trigger"
            elif task.rule_type != "scheduled" and not matched and task.condition_active and task.recovery_notice:
                event_type = "recovery"
            task.condition_active = matched
            task.last_value = value
            task.last_checked_at = now
            task.last_error = None
            if not event_type:
                return
            template = next((item for item in await service.list_templates(session, task.user_id) if item["id"] == task.template_id), None)
            config = await get_config(session, task.push_config_id, task.user_id)
            if not template or not config or not config.enabled:
                task.last_error = "消息模板或推送渠道不可用"
                session.add(MonitorEventModel(id=str(uuid.uuid4()), task_id=task.id, user_id=task.user_id,
                                              event_type=event_type, value=value, success=False,
                                              error=task.last_error))
                if event_type in ("trigger", "report"):
                    task.last_triggered_at = now
                return
            context = {"symbol": task.symbol, "exchange": task.exchange, "metric": task.metric,
                       "current_value": f"{value:.4f}", "threshold": str(task.threshold),
                       "rule_name": task.name, "triggered_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                       "event_type": "恢复正常" if event_type == "recovery" else "定时汇报" if event_type == "report" else "触发",
                       "baseline_value": f"{baseline:.4f}" if baseline is not None else "",
                       "movement_amount": f"{amount:+.4f}", "movement_percent": f"{percent:+.2f}",
                       "window_minutes": str(task.window_minutes or "")}
            title = render_template(template["title"], context)
            content = render_template(template["content"], context)
            if event_type == "recovery":
                title = f"[恢复] {title}"
            success, message = await push_service.send_test(session, config.id, task.user_id, {"messageType": template["messageType"], "title": title, "content": content})
            session.add(MonitorEventModel(id=str(uuid.uuid4()), task_id=task.id, user_id=task.user_id, event_type=event_type, value=value, success=success, error=None if success else message[:500]))
            if event_type in ("trigger", "report"):
                task.last_triggered_at = now
            if not success:
                task.last_error = message[:500]
    except Exception as exc:
        logger.exception("数据监控任务 {} 执行失败: {}", task_id, exc)
        async with db.get_session() as session:
            task = (await session.execute(select(MonitorTaskModel).where(MonitorTaskModel.id == task_id))).scalar_one_or_none()
            if task:
                task.last_error = str(exc)[:500]
                task.last_checked_at = datetime.now()


async def data_monitor_worker_loop(db, poll_seconds: float = 5):
    semaphore = asyncio.Semaphore(8)

    async def run_one(task_id: str):
        async with semaphore:
            await evaluate_task(db, task_id)

    while True:
        try:
            async with db.get_session() as session:
                now = datetime.now()
                ids = (await session.execute(select(MonitorTaskModel.id).where(MonitorTaskModel.enabled.is_(True), or_(MonitorTaskModel.next_check_at.is_(None), MonitorTaskModel.next_check_at <= now)).limit(100))).scalars().all()
            if ids:
                await asyncio.gather(*(run_one(task_id) for task_id in ids))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("数据监控后台轮询失败: {}", exc)
        await asyncio.sleep(poll_seconds)
