#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书应用机器人
提供应用机器人的消息发送和管理功能
"""
from typing import Optional, Dict, Any
from loguru import logger

from lib.feishu.base.feishu_public import (
    MsgType,
    ReceiveIdType,
    ValidateResponseException
)
from lib.feishu.feishu_sdk import FeishuSDK
from lib.feishu.base.http_client import FeishuHttpClient


class FeishuAppBot(FeishuSDK):
    """飞书应用机器人类"""

    def __init__(self, app_id: str, app_secret: str, timeout: int = 30):
        """
        初始化飞书应用机器人
        
        Args:
            app_id: 应用 ID
            app_secret: 应用密钥
            timeout: 请求超时时间（秒），默认 30 秒
        """
        super().__init__(app_id=app_id, app_secret=app_secret, timeout=timeout)

    def send_card_message_to_user_id(
        self,
        tenant_access_token: str,
        receive_id: str,
        content: str,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送卡片给指定 user_id
        
        Args:
            tenant_access_token: 租户访问令牌
            receive_id: 接收者 ID（user_id）
            content: 卡片内容（JSON 字符串）
            uuid: 消息唯一标识，可选
            
        Returns:
            发送结果响应数据
        """
        return self.send_messages(
            tenant_access_token=tenant_access_token,
            receive_id_type=ReceiveIdType.USER_ID,
            receive_id=receive_id,
            msg_type=MsgType.INTERACTIVE,
            content=content,
            uuid=uuid
        )

    def send_messages(
        self,
        tenant_access_token: str,
        receive_id_type: str,
        receive_id: str,
        msg_type: str,
        content: str,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        调用该接口向指定用户或者群聊发送消息。支持发送的消息类型包括文本、富文本、卡片、群名片、
        个人名片、图片、视频、音频、文件以及表情包等
        
        文档：https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/send-feishu-card
        
        Args:
            tenant_access_token: 租户访问令牌
            receive_id_type: 接收者 ID 类型（ReceiveIdType）
            receive_id: 接收者 ID
            msg_type: 消息类型（MsgType）
            content: 消息内容（JSON 字符串）
            uuid: 消息唯一标识，可选
            
        Returns:
            发送结果响应数据
        """
        url = f'{FeishuHttpClient.BASE_URL}/im/v1/messages'

        try:
            post_data = {
                'receive_id': receive_id,
                'msg_type': msg_type,
                'content': content
            }
            if uuid:
                post_data['uuid'] = uuid

            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data=post_data,
                params={'receive_id_type': receive_id_type}
            )

            result = data['data']
            return self.build_success_return_data(data=result)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'发送消息失败: {e}')
            return self.build_error_return_data(msg=f'发送消息失败: {str(e)}')

    def update_message(
        self,
        tenant_access_token: str,
        message_id: str,
        content: str
    ) -> Dict[str, Any]:
        """
        调用该接口，通过消息 ID（message_id）更新指定的消息卡片内容
        
        Args:
            tenant_access_token: 租户访问令牌
            message_id: 消息 ID
            content: 新的消息内容（JSON 字符串）
            
        Returns:
            更新结果响应数据
        """
        url = f'{FeishuHttpClient.BASE_URL}/im/v1/messages/{message_id}'

        try:
            data = self.http_client.patch(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data={'content': content}
            )

            result = data['data']
            return self.build_success_return_data(data=result)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'更新消息失败: {e}')
            return self.build_error_return_data(msg=f'更新消息失败: {str(e)}')

    def urgent_app_message(
        self,
        tenant_access_token: str,
        message_id: str,
        user_id_list: list,
        user_id_type: str = ReceiveIdType.USER_ID
    ) -> Dict[str, Any]:
        """
        发送应用内加急
        调用该接口把指定消息加急给目标用户，加急仅在飞书客户端内通知
        
        文档：https://open.feishu.cn/document/server-docs/im-v1/buzz-messages/urgent_app
        
        Args:
            tenant_access_token: 租户访问令牌
            message_id: 消息 ID
            user_id_list: 用户 ID 列表
            user_id_type: 用户 ID 类型，默认 ReceiveIdType.USER_ID
            
        Returns:
            加急结果响应数据
        """
        url = f'{FeishuHttpClient.BASE_URL}/im/v1/messages/{message_id}/urgent_app'

        try:
            data = self.http_client.patch(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data={'user_id_list': user_id_list},
                params={'user_id_type': user_id_type}
            )

            result = data['data']
            return self.build_success_return_data(data=result)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'发送应用内加急失败: {e}')
            return self.build_error_return_data(msg=f'发送应用内加急失败: {str(e)}')

    def urgent_phone_message(
        self,
        tenant_access_token: str,
        message_id: str,
        user_id_list: list,
        user_id_type: str = ReceiveIdType.USER_ID
    ) -> Dict[str, Any]:
        """
        发送电话加急
        调用该接口把指定消息加急给目标用户，加急将通过飞书客户端和电话进行通知
        
        文档：https://open.feishu.cn/document/server-docs/im-v1/buzz-messages/urgent_phone
        
        Args:
            tenant_access_token: 租户访问令牌
            message_id: 消息 ID
            user_id_list: 用户 ID 列表
            user_id_type: 用户 ID 类型，默认 ReceiveIdType.USER_ID
            
        Returns:
            加急结果响应数据
        """
        url = f'{FeishuHttpClient.BASE_URL}/im/v1/messages/{message_id}/urgent_phone'

        try:
            data = self.http_client.patch(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data={'user_id_list': user_id_list},
                params={'user_id_type': user_id_type}
            )

            result = data['data']
            return self.build_success_return_data(data=result)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'发送电话加急失败: {e}')
            return self.build_error_return_data(msg=f'发送电话加急失败: {str(e)}')

    def create_example_approval(
        self,
        tenant_access_token: str,
        post_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建审批实例
        
        Args:
            tenant_access_token: 租户访问令牌
            post_data: 审批实例数据（字典）
            
        Returns:
            创建结果响应数据
        """
        url = f'{FeishuHttpClient.BASE_URL}/approval/v4/instances'

        try:
            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data=post_data
            )

            result = data['data']
            return self.build_success_return_data(data=result)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'创建审批实例失败: {e}')
            return self.build_error_return_data(msg=f'创建审批实例失败: {str(e)}')

    def get_approval_instance(
        self,
        tenant_access_token: str,
        instance_id: str
    ) -> Dict[str, Any]:
        """
        查询审批实例结果
        
        Args:
            tenant_access_token: 租户访问令牌
            instance_id: 审批实例 ID
            
        Returns:
            审批实例详情响应数据
        """
        url = f'{FeishuHttpClient.BASE_URL}/approval/v4/instances/{instance_id}'

        try:
            data = self.http_client.get(
                url=url,
                tenant_access_token=tenant_access_token
            )

            result = data['data']
            return self.build_success_return_data(data=result)
        except ValidateResponseException as e:
            return self.build_error_return_data(msg=str(e))
        except Exception as e:
            logger.error(f'查询审批实例失败: {e}')
            return self.build_error_return_data(msg=f'查询审批实例失败: {str(e)}')
