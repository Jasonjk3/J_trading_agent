"""Validation for data-monitor configuration."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Metric = Literal["price", "change", "volume", "rsi"]
Operator = Literal[">", "<", "cross_up", "cross_down"]
RuleType = Literal["threshold", "scheduled", "movement"]


class RulePayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    ruleType: RuleType = "threshold"
    metric: Metric = "price"
    operator: Operator = ">"
    threshold: float = Field(default=0, allow_inf_nan=False)
    windowMinutes: Optional[int] = Field(default=None, ge=1, le=1440)
    movementUnit: Optional[Literal["amount", "percent"]] = None
    movementDirection: Optional[Literal["either", "up", "down"]] = None
    startTime: Optional[str] = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    endTime: Optional[str] = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reportIntervalMinutes: Optional[int] = Field(default=None, ge=1, le=1440)

    @model_validator(mode="after")
    def validate_condition(self):
        if self.ruleType == "scheduled":
            if not self.startTime or not self.endTime or not self.reportIntervalMinutes or self.startTime == self.endTime:
                raise ValueError("定时汇报需要不同的起止时间和汇报间隔")
            if self.metric != "price":
                raise ValueError("定时汇报当前仅支持最新价格")
            return self
        if self.ruleType == "movement":
            if not self.windowMinutes or not self.movementUnit or not self.movementDirection or self.threshold <= 0:
                raise ValueError("价格浮动规则需要时间窗口、方向、单位和正数阈值")
            if self.metric != "price":
                raise ValueError("区间浮动当前仅支持最新价格")
            return self
        if self.metric in ("price", "volume") and self.threshold <= 0:
            raise ValueError("价格和成交额阈值必须大于零")
        if self.metric == "rsi" and not 0 <= self.threshold <= 100:
            raise ValueError("RSI 阈值必须在 0 到 100 之间")
        return self


class TemplatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    messageType: Literal["text", "card"] = "text"
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=3000)

    @field_validator("title", "content")
    @classmethod
    def safe_variables(cls, value: str) -> str:
        import re

        allowed = {"symbol", "exchange", "metric", "current_value", "threshold", "rule_name", "triggered_at", "event_type", "baseline_value", "movement_amount", "movement_percent", "window_minutes"}
        found = re.findall(r"\{\{\s*([^{}]+?)\s*\}\}", value)
        if any(item not in allowed for item in found) or "{{" in re.sub(r"\{\{\s*[^{}]+?\s*\}\}", "", value):
            raise ValueError("模板包含不支持的变量")
        return value


class TaskPayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    exchange: Literal["OKX"] = "OKX"
    symbol: str = Field(min_length=3, max_length=40, pattern=r"^[A-Z0-9]+-[A-Z0-9]+$")
    frequencySeconds: Literal[10, 60, 300] = 60
    ruleId: Optional[str] = None
    ruleType: RuleType = "threshold"
    metric: Metric = "price"
    operator: Operator = ">"
    threshold: float = Field(default=0, allow_inf_nan=False)
    windowMinutes: Optional[int] = Field(default=None, ge=1, le=1440)
    movementUnit: Optional[Literal["amount", "percent"]] = None
    movementDirection: Optional[Literal["either", "up", "down"]] = None
    startTime: Optional[str] = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    endTime: Optional[str] = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reportIntervalMinutes: Optional[int] = Field(default=None, ge=1, le=1440)
    pushConfigId: str
    templateId: str
    cooldownSeconds: Literal[300, 900, 3600] = 900
    recoveryNotice: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def validate_condition(self):
        RulePayload(name=self.name, ruleType=self.ruleType, metric=self.metric, operator=self.operator,
                    threshold=self.threshold, windowMinutes=self.windowMinutes,
                    movementUnit=self.movementUnit, movementDirection=self.movementDirection,
                    startTime=self.startTime, endTime=self.endTime,
                    reportIntervalMinutes=self.reportIntervalMinutes)
        if self.ruleType == "scheduled" and self.reportIntervalMinutes * 60 < self.frequencySeconds:
            raise ValueError("检测频率不能低于定时汇报间隔")
        if self.ruleType == "movement" and self.windowMinutes * 60 < self.frequencySeconds:
            raise ValueError("检测频率不能低于价格浮动时间窗口")
        return self


class TaskEnabledPayload(BaseModel):
    enabled: bool
