#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书 SDK 基础类
提供通用的工具方法和响应构建方法
"""
import json
import uuid
from typing import Optional, Dict, Any
from loguru import logger

from lib.feishu.base.feishu_public import (
    CardType,
    MsgType,
    ResponseType,
    ToastType
)


class FeishuBase:
    """飞书 SDK 基础类，提供通用工具方法"""
    
    @staticmethod
    def build_error_return_data(msg: str = '失败', data: Optional[Any] = None) -> Dict[str, Any]:
        """
        构建错误响应数据
        
        Args:
            msg: 错误消息
            data: 错误数据
            
        Returns:
            错误响应字典
        """
        return {
            'state': ResponseType.ERROR,
            'msg': msg,
            'data': data
        }

    @staticmethod
    def build_success_return_data(msg: str = '成功', data: Optional[Any] = None) -> Dict[str, Any]:
        """
        构建成功响应数据
        
        Args:
            msg: 成功消息
            data: 响应数据
            
        Returns:
            成功响应字典
        """
        return {
            'state': ResponseType.SUCCESS,
            'msg': msg,
            'data': data
        }

    @staticmethod
    def build_card_template_data(
        template_id: str,
        template_variable: Optional[Dict[str, Any]] = None,
        template_version_name: Optional[str] = None,
        json_format: bool = True
    ) -> Any:
        """
        构建飞书卡片模板数据
        
        Args:
            template_id: 模板 ID
            template_variable: 模板变量，格式：{"key": "value"}
            template_version_name: 模板版本名称
            json_format: 是否返回 JSON 字符串，默认 True
            
        Returns:
            卡片模板数据（字典或 JSON 字符串）
        """
        result = {
            'type': 'template',
            'data': {
                'template_id': template_id,
                'template_version_name': template_version_name
            }
        }
        
        if template_variable:
            result['data']['template_variable'] = template_variable

        if json_format:
            return json.dumps(result)
        else:
            return result

    @staticmethod
    def build_card_data(
        config: Optional[Dict[str, Any]] = None,
        card_link: Optional[str] = None,
        i18n_elements: Optional[Dict[str, Any]] = None,
        header: Optional[Dict[str, Any]] = None,
        elements: Optional[Any] = None,
        fallback: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建飞书卡片数据
        
        Args:
            config: 卡片配置
            card_link: 卡片链接
            i18n_elements: 国际化元素
            header: 卡片头部
            elements: 卡片元素
            fallback: 降级内容
            
        Returns:
            卡片数据字典
        """
        result = {}
        
        if config:
            result['config'] = config
        if card_link:
            result['card_link'] = card_link
        if i18n_elements:
            result['i18n_elements'] = i18n_elements
        if header:
            result['header'] = header
        if elements:
            result['elements'] = []
            result['elements'].append(elements)
        if fallback:
            result['fallback'] = fallback

        return result

    @staticmethod
    def generate_uuid() -> str:
        """
        生成一个 UUID 并返回其字符串表示形式
        
        Returns:
            生成的 UUID 字符串
        """
        return str(uuid.uuid4())

    @staticmethod
    def build_callback_response_toast(
        toast_type: str = ToastType.SUCCESS,
        content: str = '成功'
    ) -> Dict[str, str]:
        """
        构建响应回调的 Toast 结构体
        
        Args:
            toast_type: Toast 类型
            content: Toast 内容
            
        Returns:
            Toast 数据字典
        """
        return {
            'type': toast_type,
            'content': content,
        }

    @staticmethod
    def build_card_element_data(
        tag: str,
        text: Optional[str] = None,
        disabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        构建飞书卡片组件数据
        
        Args:
            tag: 组件标签
            text: 文本内容
            disabled: 是否禁用
            
        Returns:
            卡片组件数据字典
        """
        result = {'tag': tag}

        if text is not None:
            result['text'] = {'content': text}

        if disabled is not None:
            result['disabled'] = disabled

        return result

    @staticmethod
    def build_callback_response_card(
        card_type: str = 'template',
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构建飞书消息回调响应卡片组件
        
        Args:
            card_type: 卡片类型
            data: 卡片数据
            
        Returns:
            卡片响应数据字典
        """
        return {
            'type': card_type,
            'data': data
        }

    @staticmethod
    def build_return_card_callback_response(
        toast_type: Optional[str] = None,
        content: str = '卡片交互成功',
        card_type: Optional[str] = None,
        card_type_data: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
        template_variable: Optional[Dict[str, Any]] = None,
        template_version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        构建返回卡片回传交互结构
        
        Args:
            toast_type: Toast 类型
            content: Toast 内容
            card_type: 卡片类型
            card_type_data: 卡片数据
            template_id: 模板 ID
            template_variable: 模板变量
            template_version: 模板版本
            
        Returns:
            回调响应数据字典，失败时返回 None
        """
        try:
            post_data = {}

            if toast_type is not None:
                post_data['toast'] = {
                    'type': toast_type,
                    'content': content,
                    'i18n': {
                        'zh_cn': content
                    }
                }

            if card_type is not None:
                if card_type == CardType.TEMPLATE:
                    card_type_data = {
                        'template_id': template_id,
                        'template_variable': template_variable,
                        'template_version_name': template_version,
                    }
                post_data['card'] = {
                    'type': card_type,
                    'data': card_type_data
                }

            return post_data
        except Exception as e:
            logger.error(f'构建回调响应失败: {e}')
            return None

    @staticmethod
    def build_message_content(
        data: Any,
        msg_type: str,
        return_type: str = 'json'
    ) -> Any:
        """
        构建消息内容
        
        Args:
            data: 消息数据
            msg_type: 消息类型（MsgType.IMAGE、MsgType.FILE、MsgType.TEXT）
            return_type: 返回类型，'json' 或 'dict'，默认 'json'
            
        Returns:
            消息内容（JSON 字符串或字典）
            
        Raises:
            ValueError: 参数错误时抛出
        """
        if return_type not in ['json', 'dict']:
            raise ValueError('return_type must be "json" or "dict"')

        content = {}

        if msg_type == MsgType.IMAGE:
            content['image_key'] = data
        elif msg_type == MsgType.FILE:
            content['file_key'] = data
        elif msg_type == MsgType.TEXT:
            content['text'] = data
        else:
            raise ValueError(f'不支持的 msg_type: {msg_type}')

        if return_type == 'json':
            return json.dumps(content)
        else:
            return content
