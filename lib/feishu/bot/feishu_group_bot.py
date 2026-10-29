#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书群聊机器人
提供群聊机器人的消息发送功能
"""
import json
import time
from typing import Any, Dict, Optional
import certifi
from loguru import logger
import requests

from lib.feishu.base.feishu_base import FeishuBase


class FeishuGroupBot(FeishuBase):
    """飞书群聊机器人类"""

    def __init__(
        self,
        webhook: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ):
        """
        初始化飞书群聊机器人
        
        Args:
            webhook: 群聊机器人 Webhook URL
            headers: 自定义请求头，默认使用 JSON 格式
            timeout: 请求超时时间（秒），默认 30 秒
        """
        if headers is None:
            headers = {'Content-Type': 'application/json; charset=utf-8'}

        self.headers = headers
        self.webhook = webhook
        self.timeout = timeout

    def send_message(self, message: str) -> Dict[str, Any]:
        """
        发送文本消息
        
        Args:
            message: 文本消息内容
            
        Returns:
            发送结果响应数据
        """
        message_data = {'msg_type': 'text', 'content': {'text': message}}
        return self._send_post_request(message_data)
    
    def send_post(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送富文本消息
        
        Args:
            content: 富文本内容（字典格式）
            
        Returns:
            发送结果响应数据
        """
        message_data = {'msg_type': 'post', 'content': {'post': content}}
        return self._send_post_request(message_data)
    
    def send_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送卡片消息
        
        Args:
            card: 卡片内容（字典格式）
            
        Returns:
            发送结果响应数据
        """
        message_data = {'msg_type': 'interactive', 'card': card}
        return self._send_post_request(message_data)

    def _send_post_request(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        发送 POST 请求到 Webhook
        
        Args:
            message_data: 消息数据字典
            
        Returns:
            发送结果响应数据
        """
        return_response = self.build_success_return_data()
        try:
            post_data = json.dumps(message_data)
            response = requests.post(
                url=self.webhook,
                headers=self.headers,
                data=post_data,
                verify=certifi.where(),
                timeout=self.timeout
            )
            response.raise_for_status()
            return_response = self._process_response(response)
        except requests.exceptions.HTTPError as e:
            return_response = self._handle_exception(
                f'消息发送失败，HTTP error: {e.response.status_code}, reason: {e.response.reason}'
            )
        except requests.exceptions.ConnectionError as e:
            return_response = self._handle_exception(f'消息发送失败，HTTP connection error: {e}')
        except requests.exceptions.Timeout as e:
            return_response = self._handle_exception(f'消息发送失败，Timeout error: {e}')
        except requests.exceptions.RequestException as e:
            return_response = self._handle_exception(f'消息发送失败，Request Exception: {e}')
        except Exception as e:
            return_response = self._handle_exception(f'消息发送失败，Exception: {e}')

        return return_response

    def _process_response(self, response: requests.Response) -> Dict[str, Any]:
        """
        处理响应结果
        
        Args:
            response: requests 响应对象
            
        Returns:
            处理后的响应数据
        """
        try:
            result = response.json()
            logger.debug(f'发送结果：{result}')
            return self.build_success_return_data(data=result)
        except json.JSONDecodeError:
            error_msg = f'服务器响应异常，状态码：{response.status_code}，响应内容：{response.text}'
            logger.error(error_msg)
            return self.build_error_return_data(msg='服务器响应异常')

    def _send_error_notification(self, result: Dict[str, Any]) -> None:
        """
        发送错误通知消息
        
        Args:
            result: 错误结果字典
        """
        time_now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        error_msg = result.get('errmsg', '未知异常')
        error_data = {
            'msg_type': 'text',
            'content': {
                'text': f'[注意-自动通知]飞书机器人消息发送失败，时间：{time_now}，原因：{error_msg}，请及时跟进，谢谢!'
            },
            'at': {'isAtAll': False},
        }
        logger.error(f'消息发送失败，自动通知：{error_data}')
        self._send_post_request(error_data)

    def _handle_exception(self, message: str) -> Dict[str, Any]:
        """
        处理异常并返回错误响应
        
        Args:
            message: 错误消息
            
        Returns:
            错误响应数据
        """
        logger.error(message)
        return self.build_error_return_data(msg=message)
