"""消息推送管理 API Schema。"""
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from models.inner_models.message_push_model import PushBotType, PushReceiveType


class CreateMessagePushConfigRequest(BaseModel):
    botType: PushBotType
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    webhook: Optional[str] = None
    secret: Optional[str] = None
    appId: Optional[str] = None
    appSecret: Optional[str] = None
    receiveType: Optional[PushReceiveType] = None
    receiveId: Optional[str] = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_credentials(self):
        if self.botType == PushBotType.WEBHOOK and not self.webhook:
            raise ValueError("自定义机器人必须填写 Webhook 地址")
        if self.botType == PushBotType.APP:
            if not self.appId or not self.appSecret:
                raise ValueError("应用机器人必须填写 App ID 和 App Secret")
            if not self.receiveType or not self.receiveId:
                raise ValueError("应用机器人必须填写默认接收对象")
        return self


class UpdateMessagePushConfigRequest(BaseModel):
    botType: Optional[PushBotType] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    webhook: Optional[str] = None
    secret: Optional[str] = None
    appId: Optional[str] = None
    appSecret: Optional[str] = None
    receiveType: Optional[PushReceiveType] = None
    receiveId: Optional[str] = None
    enabled: Optional[bool] = None


class ValidateMessagePushConfigRequest(BaseModel):
    botType: PushBotType
    webhook: Optional[str] = None
    secret: Optional[str] = None
    appId: Optional[str] = None
    appSecret: Optional[str] = None

    @model_validator(mode="after")
    def validate_credentials(self):
        if self.botType == PushBotType.WEBHOOK and not self.webhook:
            raise ValueError("请填写 Webhook 地址")
        if self.botType == PushBotType.APP and (not self.appId or not self.appSecret):
            raise ValueError("请填写 App ID 和 App Secret")
        return self


class TestMessagePushRequest(BaseModel):
    messageType: str = Field(default="text", pattern="^(text|card)$")
    title: Optional[str] = Field(default=None, max_length=100)
    content: str = Field(min_length=1, max_length=2000)
    receiveType: Optional[PushReceiveType] = None
    receiveId: Optional[str] = None

