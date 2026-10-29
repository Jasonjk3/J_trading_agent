"""消息推送配置数据库模型。"""
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, String, Text

from models.inner_models.base import Base


class PushBotType(str, PyEnum):
    WEBHOOK = "webhook"
    APP = "app"


class PushReceiveType(str, PyEnum):
    CHAT_ID = "chat_id"
    OPEN_ID = "open_id"
    USER_ID = "user_id"
    EMAIL = "email"


class PushTestStatus(str, PyEnum):
    NEVER = "never"
    SUCCESS = "success"
    FAILED = "failed"


class MessagePushConfigModel(Base):
    __tablename__ = "message_push_configs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    bot_type = Column(
        SQLEnum(PushBotType, values_callable=lambda values: [item.value for item in values]),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)

    webhook = Column(Text, nullable=True, comment="加密后的 Webhook")
    secret = Column(Text, nullable=True, comment="加密后的 Webhook 签名密钥")
    app_id = Column(Text, nullable=True, comment="加密后的 App ID")
    app_secret = Column(Text, nullable=True, comment="加密后的 App Secret")
    receive_type = Column(
        SQLEnum(PushReceiveType, values_callable=lambda values: [item.value for item in values]),
        nullable=True,
    )
    receive_id = Column(Text, nullable=True, comment="加密后的默认接收 ID")

    enabled = Column(Boolean, nullable=False, default=True, index=True)
    last_test_status = Column(
        SQLEnum(PushTestStatus, values_callable=lambda values: [item.value for item in values]),
        nullable=False,
        default=PushTestStatus.NEVER,
    )
    last_test_at = Column(DateTime, nullable=True)
    last_error = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

