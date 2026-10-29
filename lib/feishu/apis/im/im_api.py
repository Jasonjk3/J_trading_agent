#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书即时消息 API
提供即时消息相关的 API 接口（发送消息、上传图片、文件等）
"""
import json
from typing import Optional, Dict, Any, Union
from loguru import logger
from requests_toolbelt import MultipartEncoder

from lib.feishu.base.feishu_public import (
    ValidateResponseException, 
    FileType, 
    ImageType,
    MsgType,
    ReceiveIdType
)
from lib.feishu.base.http_client import FeishuHttpClient
from ..base import FeishuBaseApi


class FeishuImApi(FeishuBaseApi):
    """飞书即时消息 API 类"""

    def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: Union[str, Dict[str, Any]],
        receive_id_type: str = ReceiveIdType.OPEN_ID,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送消息
        调用该接口向指定用户或者群聊发送消息。支持发送的消息类型包括文本、富文本、卡片、
        群名片、个人名片、图片、视频、音频、文件以及表情包等。
        
        文档：https://open.feishu.cn/document/server-docs/im-v1/message/create
        
        使用限制：
        - 向同一用户发送消息的限频为 5 QPS
        - 向同一群组发送消息的限频为群内机器人共享 5 QPS
        
        Args:
            receive_id: 消息接收者的 ID，ID 类型与 receive_id_type 的取值一致
                - 给用户发送消息时，用户需要在机器人的可用范围内
                - 给群组发送消息时，机器人需要在该群组中，且在群组内拥有发言权限
                - 如果消息接收者为用户，推荐使用用户的 open_id
            msg_type: 消息类型，可选值：
                - text：文本
                - post：富文本
                - image：图片
                - file：文件
                - audio：语音
                - media：视频
                - sticker：表情包
                - interactive：卡片
                - share_chat：分享群名片
                - share_user：分享个人名片
                - system：系统消息（仅支持在机器人单聊内推送）
            content: 消息内容，可以是 JSON 字符串或字典
                - 如果是字典，会自动转换为 JSON 字符串
                - 文本消息示例：{"text": "test content"}
                - 图片消息示例：{"image_key": "img_xxx"}
                - 文件消息示例：{"file_key": "file_xxx"}
            receive_id_type: 消息接收者 ID 类型，默认 open_id，可选值：
                - open_id：标识一个用户在某个应用中的身份
                - union_id：标识一个用户在某个应用开发商下的身份
                - user_id：标识一个用户在某个租户内的身份
                - email：以用户的真实邮箱来标识用户
                - chat_id：以群 ID 来标识群聊
            uuid: 自定义设置的唯一字符串序列，用于请求去重
                - 持有相同 uuid 的请求，在 1 小时内至多成功发送一条消息
                - 最大长度 50 字符
            
        Returns:
            发送消息的响应数据，包含：
            - message_id: 消息 ID
            - root_id: 根消息 ID（仅在回复消息场景返回）
            - parent_id: 父消息 ID（仅在回复消息场景返回）
            - thread_id: 话题 ID（仅在话题场景返回）
            - msg_type: 消息类型
            - create_time: 消息生成的时间戳（毫秒）
            - update_time: 消息更新的时间戳（毫秒）
            - deleted: 消息是否被撤回
            - updated: 消息是否被更新
            - chat_id: 消息所属的群 ID
            - sender: 发送者信息
            - body: 消息内容
            - mentions: 被 @ 的用户列表
            
        Raises:
            ValidateResponseException: 发送消息失败时抛出
            
        Example:
            >>> # 发送文本消息
            >>> api.send_message(
            ...     receive_id="ou_xxx",
            ...     msg_type="text",
            ...     content={"text": "Hello, World!"},
            ...     receive_id_type="open_id"
            ... )
            
            >>> # 发送卡片消息
            >>> api.send_message(
            ...     receive_id="oc_xxx",
            ...     msg_type="interactive",
            ...     content={"elements": [{"tag": "markdown", "content": "**标题**"}]},
            ...     receive_id_type="chat_id"
            ... )
        """
        url = f'{FeishuHttpClient.BASE_URL}/im/v1/messages'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            # 如果 content 是字典，转换为 JSON 字符串
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            
            # 构建请求体
            request_body: Dict[str, Any] = {
                'receive_id': receive_id,
                'msg_type': msg_type,
                'content': content
            }
            
            # 添加可选参数
            if uuid is not None:
                request_body['uuid'] = uuid
            
            # 构建查询参数
            params = {
                'receive_id_type': receive_id_type
            }
            
            data = self.http_client.post(
                url=url,
                tenant_access_token=tenant_access_token,
                json_data=request_body,
                params=params
            )

            return data.get('data', {})
        except ValidateResponseException as e:
            logger.error(f'发送消息失败: {e}')
            raise
        except Exception as e:
            logger.error(f'发送消息失败: {e}')
            raise ValidateResponseException(f'发送消息失败: {str(e)}')

    def send_text_message(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = ReceiveIdType.OPEN_ID,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送文本消息（便捷方法）
        
        Args:
            receive_id: 消息接收者的 ID
            text: 文本内容
            receive_id_type: 消息接收者 ID 类型，默认 open_id
            uuid: 请求去重标识
            
        Returns:
            发送消息的响应数据
            
        Example:
            >>> api.send_text_message("ou_xxx", "Hello, World!")
        """
        return self.send_message(
            receive_id=receive_id,
            msg_type=MsgType.TEXT,
            content={'text': text},
            receive_id_type=receive_id_type,
            uuid=uuid
        )

    def send_image_message(
        self,
        receive_id: str,
        image_key: str,
        receive_id_type: str = ReceiveIdType.OPEN_ID,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送图片消息（便捷方法）
        
        Args:
            receive_id: 消息接收者的 ID
            image_key: 图片的 key，可通过 upload_image 方法获取
            receive_id_type: 消息接收者 ID 类型，默认 open_id
            uuid: 请求去重标识
            
        Returns:
            发送消息的响应数据
            
        Example:
            >>> image_key = api.upload_image(image_file)
            >>> api.send_image_message("ou_xxx", image_key)
        """
        return self.send_message(
            receive_id=receive_id,
            msg_type=MsgType.IMAGE,
            content={'image_key': image_key},
            receive_id_type=receive_id_type,
            uuid=uuid
        )

    def send_file_message(
        self,
        receive_id: str,
        file_key: str,
        receive_id_type: str = ReceiveIdType.OPEN_ID,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送文件消息（便捷方法）
        
        Args:
            receive_id: 消息接收者的 ID
            file_key: 文件的 key，可通过 upload_file 方法获取
            receive_id_type: 消息接收者 ID 类型，默认 open_id
            uuid: 请求去重标识
            
        Returns:
            发送消息的响应数据
            
        Example:
            >>> file_key = api.upload_file(file, "report.pdf")
            >>> api.send_file_message("ou_xxx", file_key)
        """
        return self.send_message(
            receive_id=receive_id,
            msg_type=MsgType.FILE,
            content={'file_key': file_key},
            receive_id_type=receive_id_type,
            uuid=uuid
        )

    def send_interactive_message(
        self,
        receive_id: str,
        card: Dict[str, Any],
        receive_id_type: str = ReceiveIdType.OPEN_ID,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送卡片消息（便捷方法）
        
        Args:
            receive_id: 消息接收者的 ID
            card: 卡片内容，JSON 结构的字典
            receive_id_type: 消息接收者 ID 类型，默认 open_id
            uuid: 请求去重标识
            
        Returns:
            发送消息的响应数据
            
        Example:
            >>> card = {
            ...     "elements": [
            ...         {"tag": "markdown", "content": "**Hello**"}
            ...     ]
            ... }
            >>> api.send_interactive_message("ou_xxx", card)
        """
        return self.send_message(
            receive_id=receive_id,
            msg_type=MsgType.INTERACTIVE,
            content=card,
            receive_id_type=receive_id_type,
            uuid=uuid
        )

    def upload_image(
        self,
        image: Any,
        image_type: str = ImageType.MESSAGE
    ) -> str:
        """
        上传图片
        调用本接口将图片上传至飞书开放平台，支持上传 JPG、JPEG、PNG、WEBP、GIF、BMP、ICO、
        TIFF、HEIC 格式的图片，但需要注意 TIFF、HEIC 上传后会被转为 JPG 格式。
        
        文档：https://open.feishu.cn/document/server-docs/im-v1/image/create
        
        Args:
            image: 图片文件对象或文件路径
            image_type: 图片类型，默认 ImageType.MESSAGE
            
        Returns:
            图片的 image_key
        """
        url = f'{FeishuHttpClient.BASE_URL}/im/v1/images'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            form = {
                'image_type': image_type,
                'image': image
            }
            multi_form = MultipartEncoder(form)

            data = self.http_client.post_multipart(
                url=url,
                tenant_access_token=tenant_access_token,
                form_data=multi_form
            )

            return data['data']['image_key']
        except ValidateResponseException as e:
            logger.error(f'上传图片失败: {e}')
            raise
        except Exception as e:
            logger.error(f'上传图片失败: {e}')
            raise ValidateResponseException(f'上传图片失败: {str(e)}')

    def upload_file(
        self,
        file: Any,
        file_name: str,
        duration: Optional[int] = None,
        file_type: str = FileType.STREAM
    ) -> str:
        """
        上传文件
        调用该接口将本地文件上传至开放平台，支持上传音频、视频、文档等文件类型。
        上传后接口会返回文件的 Key，使用该 Key 值可以调用其他接口。
        
        文档：https://open.feishu.cn/document/server-docs/im-v1/file/create
        
        Args:
            file: 文件对象或文件路径
            file_name: 文件名
            duration: 文件时长（秒），音频/视频文件需要
            file_type: 文件类型，默认 FileType.STREAM
            
        Returns:
            文件的 file_key
        """
        url = f'{FeishuHttpClient.BASE_URL}/im/v1/files'

        try:
            tenant_access_token = self.get_tenant_access_token()
            
            form = {
                'file_type': file_type,
                'file': (file_name, file, 'agent_applications/octet-stream'),
                'file_name': file_name
            }
            if duration is not None:
                form['duration'] = str(duration)
            
            multi_form = MultipartEncoder(form)

            data = self.http_client.post_multipart(
                url=url,
                tenant_access_token=tenant_access_token,
                form_data=multi_form
            )

            return data['data']['file_key']
        except ValidateResponseException as e:
            logger.error(f'上传文件失败: {e}')
            raise
        except Exception as e:
            logger.error(f'上传文件失败: {e}')
            raise ValidateResponseException(f'上传文件失败: {str(e)}')

