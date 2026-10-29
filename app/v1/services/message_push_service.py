"""消息推送配置与飞书发送服务。"""
import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.v1.crud.message_push_crud import (
    count_configs,
    create_config,
    delete_config,
    get_config,
    get_configs,
    update_config,
    update_test_result,
)
from configs.config import settings
from lib.feishu.bot.feishu_app_bot import FeishuAppBot
from lib.feishu.base.feishu_public import MsgType
from models.inner_models.message_push_model import (
    MessagePushConfigModel,
    PushBotType,
    PushReceiveType,
)


class MessagePushEncryptor:
    """基于应用 SECRET_KEY 的对称加密器。"""

    def __init__(self) -> None:
        raw_key = hashlib.sha256(settings.app_config.SECRET_KEY.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(raw_key))

    def encrypt(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: Optional[str]) -> str:
        if not value:
            return ""
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("消息推送凭据无法解密，请重新保存配置") from exc


class MessagePushService:
    def __init__(self) -> None:
        self.encryptor = MessagePushEncryptor()

    async def get_list(
        self,
        session: AsyncSession,
        user_id: str,
        bot_type: Optional[PushBotType] = None,
        enabled: Optional[bool] = None,
    ) -> Tuple[List[MessagePushConfigModel], int]:
        items = await get_configs(session, user_id, bot_type, enabled)
        total = await count_configs(session, user_id)
        return items, total

    async def create(
        self, session: AsyncSession, user_id: str, payload: Dict[str, Any]
    ) -> MessagePushConfigModel:
        bot_type = PushBotType(payload["botType"])
        data = self._build_create_data(bot_type, payload)
        return await create_config(session, user_id, data)

    async def update(
        self,
        session: AsyncSession,
        config_id: str,
        user_id: str,
        payload: Dict[str, Any],
    ) -> Optional[MessagePushConfigModel]:
        config = await get_config(session, config_id, user_id)
        if not config:
            return None

        target_type = PushBotType(payload.get("botType") or config.bot_type)
        changing_type = target_type != config.bot_type
        data: Dict[str, Any] = {}
        field_map = {"name": "name", "description": "description", "enabled": "enabled"}
        for request_key, model_key in field_map.items():
            if request_key in payload and payload[request_key] is not None:
                data[model_key] = payload[request_key]

        data["bot_type"] = target_type
        if target_type == PushBotType.WEBHOOK:
            webhook = payload.get("webhook")
            if changing_type and not webhook:
                raise ValueError("切换为自定义机器人时必须填写 Webhook 地址")
            if webhook:
                data["webhook"] = self.encryptor.encrypt(webhook)
            if payload.get("secret"):
                data["secret"] = self.encryptor.encrypt(payload["secret"])
            if changing_type:
                data.update(app_id=None, app_secret=None, receive_type=None, receive_id=None)
        else:
            app_id = payload.get("appId")
            app_secret = payload.get("appSecret")
            receive_id = payload.get("receiveId")
            if changing_type and (not app_id or not app_secret or not receive_id):
                raise ValueError("切换为应用机器人时必须填写 App ID、App Secret 和接收 ID")
            if app_id:
                data["app_id"] = self.encryptor.encrypt(app_id)
            if app_secret:
                data["app_secret"] = self.encryptor.encrypt(app_secret)
            if receive_id:
                data["receive_id"] = self.encryptor.encrypt(receive_id)
            if payload.get("receiveType"):
                data["receive_type"] = PushReceiveType(payload["receiveType"])
            if changing_type:
                data.update(webhook=None, secret=None)

        return await update_config(session, config, data)

    async def delete(self, session: AsyncSession, config_id: str, user_id: str) -> bool:
        config = await get_config(session, config_id, user_id)
        if not config:
            return False
        await delete_config(session, config)
        return True

    async def validate_credentials(self, payload: Dict[str, Any]) -> Tuple[bool, str]:
        bot_type = PushBotType(payload["botType"])
        try:
            if bot_type == PushBotType.WEBHOOK:
                return await asyncio.to_thread(
                    self._send_webhook,
                    payload["webhook"],
                    payload.get("secret") or "",
                    "text",
                    "",
                    "QuantTrader 连接验证成功。",
                )
            return await asyncio.to_thread(
                self._validate_app_credentials,
                payload["appId"],
                payload["appSecret"],
            )
        except Exception as exc:
            return False, str(exc)

    async def validate_saved(
        self, session: AsyncSession, config_id: str, user_id: str
    ) -> Tuple[bool, str]:
        config = await get_config(session, config_id, user_id)
        if not config:
            return False, "推送配置不存在"
        try:
            if config.bot_type == PushBotType.WEBHOOK:
                success, message = await asyncio.to_thread(
                    self._send_webhook,
                    self.encryptor.decrypt(config.webhook),
                    self.encryptor.decrypt(config.secret),
                    "text",
                    "",
                    "QuantTrader 连接验证成功。",
                )
            else:
                success, message = await asyncio.to_thread(
                    self._validate_app_credentials,
                    self.encryptor.decrypt(config.app_id),
                    self.encryptor.decrypt(config.app_secret),
                )
        except Exception as exc:
            success, message = False, str(exc)
        await update_test_result(session, config, success, None if success else message)
        return success, message

    async def send_test(
        self,
        session: AsyncSession,
        config_id: str,
        user_id: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, str]:
        config = await get_config(session, config_id, user_id)
        if not config:
            return False, "推送配置不存在"

        try:
            if config.bot_type == PushBotType.WEBHOOK:
                success, message = await asyncio.to_thread(
                    self._send_webhook,
                    self.encryptor.decrypt(config.webhook),
                    self.encryptor.decrypt(config.secret),
                    payload["messageType"],
                    payload.get("title") or "QuantTrader 通知",
                    payload["content"],
                )
            else:
                receive_type = payload.get("receiveType") or config.receive_type
                receive_id = payload.get("receiveId") or self.encryptor.decrypt(config.receive_id)
                if not receive_type or not receive_id:
                    raise ValueError("应用机器人缺少接收对象")
                success, message = await asyncio.to_thread(
                    self._send_app_message,
                    self.encryptor.decrypt(config.app_id),
                    self.encryptor.decrypt(config.app_secret),
                    str(receive_type.value if hasattr(receive_type, "value") else receive_type),
                    receive_id,
                    payload["messageType"],
                    payload.get("title") or "QuantTrader 通知",
                    payload["content"],
                )
        except Exception as exc:
            success, message = False, str(exc)

        await update_test_result(session, config, success, None if success else message)
        return success, message

    def model_to_response(self, config: MessagePushConfigModel) -> Dict[str, Any]:
        webhook = self.encryptor.decrypt(config.webhook)
        app_id = self.encryptor.decrypt(config.app_id)
        receive_id = self.encryptor.decrypt(config.receive_id)
        return {
            "id": config.id,
            "botType": config.bot_type.value,
            "name": config.name,
            "description": config.description or "",
            "enabled": config.enabled,
            "webhookMasked": self._mask(webhook, 34, 6),
            "hasSecret": bool(config.secret),
            "appIdMasked": self._mask(app_id, 7, 4),
            "hasAppSecret": bool(config.app_secret),
            "receiveType": config.receive_type.value if config.receive_type else None,
            "receiveIdMasked": self._mask(receive_id, 5, 4),
            "lastTestStatus": config.last_test_status.value,
            "lastTestAt": config.last_test_at.isoformat() if config.last_test_at else None,
            "lastError": config.last_error,
            "createdAt": config.created_at.isoformat(),
            "updatedAt": config.updated_at.isoformat() if config.updated_at else None,
        }

    def _build_create_data(self, bot_type: PushBotType, payload: Dict[str, Any]) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "bot_type": bot_type,
            "name": payload["name"],
            "description": payload.get("description"),
            "enabled": payload.get("enabled", True),
        }
        if bot_type == PushBotType.WEBHOOK:
            data["webhook"] = self.encryptor.encrypt(payload["webhook"])
            data["secret"] = self.encryptor.encrypt(payload.get("secret"))
        else:
            data["app_id"] = self.encryptor.encrypt(payload["appId"])
            data["app_secret"] = self.encryptor.encrypt(payload["appSecret"])
            data["receive_type"] = PushReceiveType(payload["receiveType"])
            data["receive_id"] = self.encryptor.encrypt(payload["receiveId"])
        return data

    @staticmethod
    def _mask(value: str, prefix: int, suffix: int) -> str:
        if not value:
            return ""
        if len(value) <= prefix + suffix:
            return f"****{value[-min(4, len(value)):]}"
        return f"{value[:prefix]}••••••{value[-suffix:]}"

    @staticmethod
    def _card(title: str, content: str) -> Dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "来自 QuantTrader 消息推送"}
                    ],
                },
            ],
        }

    def _send_webhook(
        self, webhook: str, secret: str, message_type: str, title: str, content: str
    ) -> Tuple[bool, str]:
        if not webhook.startswith("https://open.feishu.cn/open-apis/bot/v2/hook/"):
            return False, "Webhook 地址格式不正确"
        payload: Dict[str, Any]
        if message_type == "card":
            payload = {"msg_type": "interactive", "card": self._card(title, content)}
        else:
            payload = {"msg_type": "text", "content": {"text": content}}
        if secret:
            timestamp = str(int(time.time()))
            signing_key = f"{timestamp}\n{secret}".encode("utf-8")
            signature = base64.b64encode(
                hmac.new(signing_key, digestmod=hashlib.sha256).digest()
            ).decode("utf-8")
            payload.update(timestamp=timestamp, sign=signature)

        response = requests.post(webhook, json=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
        code = result.get("code", result.get("StatusCode", -1))
        if code != 0:
            return False, result.get("msg") or result.get("StatusMessage") or "飞书返回发送失败"
        return True, "飞书消息发送成功"

    @staticmethod
    def _validate_app_credentials(app_id: str, app_secret: str) -> Tuple[bool, str]:
        bot = FeishuAppBot(app_id=app_id, app_secret=app_secret, timeout=15)
        bot.get_tenant_access_token()
        return True, "应用凭据验证成功"

    def _send_app_message(
        self,
        app_id: str,
        app_secret: str,
        receive_type: str,
        receive_id: str,
        message_type: str,
        title: str,
        content: str,
    ) -> Tuple[bool, str]:
        bot = FeishuAppBot(app_id=app_id, app_secret=app_secret, timeout=15)
        token = bot.get_tenant_access_token()
        if message_type == "card":
            msg_type = MsgType.INTERACTIVE
            message_content = json.dumps(self._card(title, content), ensure_ascii=False)
        else:
            msg_type = MsgType.TEXT
            message_content = json.dumps({"text": content}, ensure_ascii=False)
        result = bot.send_messages(
            tenant_access_token=token,
            receive_id_type=receive_type,
            receive_id=receive_id,
            msg_type=msg_type,
            content=message_content,
        )
        if result.get("state") != "success":
            return False, result.get("msg") or "飞书应用消息发送失败"
        return True, "飞书消息发送成功"

