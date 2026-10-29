#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书即时消息工具
封装飞书 SDK 的即时消息相关功能（发送消息、上传图片、文件）
"""
from typing import Any, Dict, Optional, Union
from loguru import logger
import os

from core.tools.base.base_tool import BaseTool
from lib.feishu import FeishuSDK
from lib.feishu.base.feishu_public import MsgType, ReceiveIdType


class FeishuImTool(BaseTool):
    """飞书即时消息工具，用于发送消息、上传图片和文件"""
    
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        timeout: int = 30
    ):
        """
        初始化飞书即时消息工具
        
        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            timeout: 请求超时时间（秒）
        """
        super().__init__(
            tool_name="feishu_im",
            tool_description="飞书即时消息工具，支持发送消息（文本、图片、文件、卡片等）、上传图片和文件",
            tool_type="feishu_im"
        )
        
        self.sdk = FeishuSDK(app_id=app_id, app_secret=app_secret, timeout=timeout)
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数模式
        
        Returns:
            参数模式字典
        """
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "send_message",
                        "send_text",
                        "send_image",
                        "send_file",
                        "send_interactive",
                        "upload_image",
                        "upload_file"
                    ],
                    "description": "操作类型：send_message-发送消息，send_text-发送文本，send_image-发送图片，send_file-发送文件，send_interactive-发送卡片，upload_image-上传图片，upload_file-上传文件"
                },
                "receive_id": {
                    "type": "string",
                    "description": "消息接收者的ID（发送消息时必填）"
                },
                "receive_id_type": {
                    "type": "string",
                    "enum": ["open_id", "union_id", "user_id", "email", "chat_id"],
                    "description": "接收者ID类型：open_id-用户在应用中的身份，union_id-用户在开发商下的身份，user_id-用户在租户内的身份，email-邮箱，chat_id-群ID。默认user_id"
                },
                "msg_type": {
                    "type": "string",
                    "enum": ["text", "post", "image", "file", "audio", "media", "sticker", "interactive", "share_chat", "share_user", "system"],
                    "description": "消息类型（send_message时需要）"
                },
                "content": {
                    "type": ["string", "object"],
                    "description": "消息内容，可以是JSON字符串或对象。文本消息示例：{\"text\": \"内容\"}，图片消息示例：{\"image_key\": \"img_xxx\"}"
                },
                "text": {
                    "type": "string",
                    "description": "文本内容（send_text时使用）"
                },
                "image_key": {
                    "type": "string",
                    "description": "图片key（send_image时使用，可通过upload_image获取）"
                },
                "file_key": {
                    "type": "string",
                    "description": "文件key（send_file时使用，可通过upload_file获取）"
                },
                "card": {
                    "type": "object",
                    "description": "卡片内容（send_interactive时使用）"
                },
                "uuid": {
                    "type": "string",
                    "description": "请求去重标识，相同uuid在1小时内至多发送一条消息，最大50字符"
                },
                "file_path": {
                    "type": "string",
                    "description": "文件路径（upload_image/upload_file时必填）"
                },
                "file_name": {
                    "type": "string",
                    "description": "文件名（upload_file时必填）"
                },
                "duration": {
                    "type": "integer",
                    "description": "文件时长（秒），音频/视频文件需要"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        action: str,
        receive_id: Optional[str] = None,
        receive_id_type: str = ReceiveIdType.OPEN_ID,
        msg_type: Optional[str] = None,
        content: Optional[Union[str, Dict[str, Any]]] = None,
        text: Optional[str] = None,
        image_key: Optional[str] = None,
        file_key: Optional[str] = None,
        card: Optional[Dict[str, Any]] = None,
        uuid: Optional[str] = None,
        file_path: Optional[str] = None,
        file_name: Optional[str] = None,
        duration: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        执行工具：发送飞书消息或上传图片/文件
        
        Args:
            action: 操作类型
            receive_id: 消息接收者的ID
            receive_id_type: 接收者ID类型，默认open_id
            msg_type: 消息类型（send_message时使用）
            content: 消息内容，JSON字符串或字典
            text: 文本内容（send_text时使用）
            image_key: 图片key（send_image时使用）
            file_key: 文件key（send_file时使用）
            card: 卡片内容（send_interactive时使用）
            uuid: 请求去重标识
            file_path: 文件路径（upload_image/upload_file时使用）
            file_name: 文件名（upload_file时使用）
            duration: 文件时长（秒）
            
        Returns:
            执行结果
        """
        try:
            # ========== 发送消息相关操作 ==========
            if action == "send_message":
                # 通用发送消息
                if not receive_id:
                    return {"success": False, "error": "receive_id 不能为空"}
                if not msg_type:
                    return {"success": False, "error": "msg_type 不能为空"}
                if not content:
                    return {"success": False, "error": "content 不能为空"}
                
                result = self.sdk.im.send_message(
                    receive_id=receive_id,
                    msg_type=msg_type,
                    content=content,
                    receive_id_type=receive_id_type,
                    uuid=uuid
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "send_text":
                # 发送文本消息
                if not receive_id:
                    return {"success": False, "error": "receive_id 不能为空"}
                if not text:
                    return {"success": False, "error": "text 不能为空"}
                
                result = self.sdk.im.send_text_message(
                    receive_id=receive_id,
                    text=text,
                    receive_id_type=receive_id_type,
                    uuid=uuid
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "send_image":
                # 发送图片消息
                if not receive_id:
                    return {"success": False, "error": "receive_id 不能为空"}
                if not image_key:
                    return {"success": False, "error": "image_key 不能为空，请先使用 upload_image 上传图片"}
                
                result = self.sdk.im.send_image_message(
                    receive_id=receive_id,
                    image_key=image_key,
                    receive_id_type=receive_id_type,
                    uuid=uuid
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "send_file":
                # 发送文件消息
                if not receive_id:
                    return {"success": False, "error": "receive_id 不能为空"}
                if not file_key:
                    return {"success": False, "error": "file_key 不能为空，请先使用 upload_file 上传文件"}
                
                result = self.sdk.im.send_file_message(
                    receive_id=receive_id,
                    file_key=file_key,
                    receive_id_type=receive_id_type,
                    uuid=uuid
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            elif action == "send_interactive":
                # 发送卡片消息
                if not receive_id:
                    return {"success": False, "error": "receive_id 不能为空"}
                if not card:
                    return {"success": False, "error": "card 不能为空"}
                
                result = self.sdk.im.send_interactive_message(
                    receive_id=receive_id,
                    card=card,
                    receive_id_type=receive_id_type,
                    uuid=uuid
                )
                return {
                    "success": True,
                    "action": action,
                    "data": result
                }
            
            # ========== 上传文件相关操作 ==========
            elif action == "upload_image":
                if not file_path:
                    return {"success": False, "error": "file_path 不能为空"}
                if not os.path.exists(file_path):
                    return {"success": False, "error": f"文件不存在: {file_path}"}
                
                with open(file_path, 'rb') as f:
                    uploaded_image_key = self.sdk.im.upload_image(image=f)
                return {
                    "success": True,
                    "action": action,
                    "data": {
                        "image_key": uploaded_image_key,
                        "file_path": file_path
                    }
                }
            
            elif action == "upload_file":
                if not file_path:
                    return {"success": False, "error": "file_path 不能为空"}
                if not os.path.exists(file_path):
                    return {"success": False, "error": f"文件不存在: {file_path}"}
                
                if not file_name:
                    file_name = os.path.basename(file_path)
                
                with open(file_path, 'rb') as f:
                    uploaded_file_key = self.sdk.im.upload_file(
                        file=f,
                        file_name=file_name,
                        duration=duration
                    )
                return {
                    "success": True,
                    "action": action,
                    "data": {
                        "file_key": uploaded_file_key,
                        "file_name": file_name,
                        "file_path": file_path
                    }
                }
            
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作类型: {action}"
                }
                
        except Exception as e:
            logger.error(f'飞书即时消息工具执行失败: {e}')
            return {
                "success": False,
                "error": str(e),
                "action": action
            }

