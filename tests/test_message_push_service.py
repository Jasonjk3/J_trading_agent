import base64
import hashlib
import hmac
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.v1.schemas.message_push_schema import CreateMessagePushConfigRequest
from app.v1.services.message_push_service import MessagePushEncryptor, MessagePushService
from lib.feishu.apis.base import FeishuBaseApi
from lib.feishu.feishu_sdk import FeishuSDK


class MessagePushServiceTests(unittest.TestCase):
    def test_encryptor_round_trip_and_ciphertext_does_not_expose_secret(self):
        encryptor = MessagePushEncryptor()
        ciphertext = encryptor.encrypt("SEC-sensitive-value")
        self.assertNotIn("sensitive-value", ciphertext)
        self.assertEqual(encryptor.decrypt(ciphertext), "SEC-sensitive-value")

    def test_create_schema_requires_type_specific_credentials(self):
        with self.assertRaises(ValidationError):
            CreateMessagePushConfigRequest(botType="webhook", name="test")
        with self.assertRaises(ValidationError):
            CreateMessagePushConfigRequest(
                botType="app", name="test", appId="cli_demo", appSecret="secret"
            )

    @patch("app.v1.services.message_push_service.time.time", return_value=1599360473)
    @patch("app.v1.services.message_push_service.requests.post")
    def test_webhook_sender_adds_feishu_signature(self, post: Mock, _time: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "msg": "success"}
        post.return_value = response

        success, _ = MessagePushService()._send_webhook(
            "https://open.feishu.cn/open-apis/bot/v2/hook/demo",
            "demo",
            "text",
            "",
            "hello",
        )

        payload = post.call_args.kwargs["json"]
        signing_key = b"1599360473\ndemo"
        expected = base64.b64encode(
            hmac.new(signing_key, digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        self.assertTrue(success)
        self.assertEqual(payload["timestamp"], "1599360473")
        self.assertEqual(payload["sign"], expected)
        self.assertEqual(payload["content"]["text"], "hello")

    @patch.object(FeishuBaseApi, "get_app_access_token")
    def test_sdk_tenant_token_uses_unwrapped_parent_result(self, get_token: Mock):
        get_token.return_value = {
            "tenant_access_token": "tenant-token",
            "app_access_token": "app-token",
            "expire": 7200,
        }
        sdk = FeishuSDK("cli_demo", "secret")

        self.assertEqual(sdk.get_tenant_access_token(), "tenant-token")
        get_token.assert_called_once_with(sdk)


if __name__ == "__main__":
    unittest.main()
