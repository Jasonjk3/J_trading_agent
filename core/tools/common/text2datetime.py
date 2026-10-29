#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/11/21 14:40
# @Author : Jason
# @Email : Jasonforjob@qq.com
"""
文本转日期时间工具
使用LLM将自然语言时间描述转换为标准格式
"""
from datetime import datetime
from typing import Any, Dict, Optional
from loguru import logger

from core.tools.base.base_tool import BaseTool
from core.llm.base.base_llm import BaseLLM


class Text2DateTimeTool(BaseTool):
    """文本转日期时间工具"""
    
    def __init__(
        self,
        llm: BaseLLM,
        tool_name: str = "text2datetime",
        tool_description: str = "将自然语言时间描述转换为标准日期时间格式或毫秒时间戳",
        **kwargs
    ):
        """
        初始化文本转日期时间工具
        
        Args:
            llm: LLM实例，用于理解自然语言时间
            tool_name: 工具名称
            tool_description: 工具描述
            **kwargs: 其他参数
        """
        super().__init__(tool_name, tool_description, **kwargs)
        self.llm = llm
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """
        获取参数模式
        
        Returns:
            参数模式字典
        """
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "自然语言时间描述，例如：'今天下午6点'、'明天上午10点'、'下周一'、'2025年12月25日'等"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["datetime", "timestamp", "both"],
                    "default": "both",
                    "description": "输出格式：datetime（标准日期时间字符串）、timestamp（毫秒时间戳）、both（两者都返回）"
                },
                "reference_time": {
                    "type": "string",
                    "description": "参考时间（可选），用于理解相对时间，格式：YYYY-MM-DD HH:mm:ss，如果不提供则使用当前时间"
                }
            },
            "required": ["text"]
        }
    
    async def execute(
        self,
        text: str,
        output_format: str = "both",
        reference_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行文本转日期时间转换
        
        Args:
            text: 自然语言时间描述
            output_format: 输出格式（datetime/timestamp/both）
            reference_time: 参考时间（可选）
            
        Returns:
            转换结果，包含：
                - success: 是否成功
                - datetime: 标准日期时间字符串（格式：YYYY-MM-DD HH:mm:ss）
                - timestamp: 毫秒时间戳字符串
                - error: 错误信息（如果失败）
        """
        try:
            # 获取参考时间
            if reference_time:
                try:
                    ref_dt = datetime.strptime(reference_time, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    ref_dt = datetime.now()
                    logger.warning(f"参考时间格式错误，使用当前时间: {reference_time}")
            else:
                ref_dt = datetime.now()
            
            # 构建提示词
            prompt = self._build_prompt(text, ref_dt)
            
            # 调用LLM
            response = await self._call_llm(prompt)
            
            # 解析LLM响应
            result = self._parse_response(response, ref_dt)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "无法解析时间"),
                    "text": text
                }
            
            # 构建返回结果
            output = {
                "success": True,
                "text": text,
                "parsed_datetime": result.get("datetime_str")
            }
            
            if output_format in ["datetime", "both"]:
                output["datetime"] = result.get("datetime_str")
            
            if output_format in ["timestamp", "both"]:
                output["timestamp"] = result.get("timestamp")
            
            return output
            
        except Exception as e:
            logger.error(f"文本转日期时间失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "text": text
            }
    
    def _build_prompt(self, text: str, reference_time: datetime) -> str:
        """
        构建LLM提示词
        
        Args:
            text: 自然语言时间描述
            reference_time: 参考时间
            
        Returns:
            提示词
        """
        current_time_str = reference_time.strftime("%Y-%m-%d %H:%M:%S")
        current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][reference_time.weekday()]
        
        prompt = f"""你是一个时间解析专家。请将自然语言时间描述转换为标准的日期时间格式。

当前参考时间：{current_time_str} ({current_weekday})

用户输入的时间描述：{text}

请仔细分析用户的时间描述，理解其含义，并转换为标准的日期时间格式。

要求：
1. 如果用户说的是相对时间（如"今天"、"明天"、"下周"等），请基于参考时间计算
2. 如果用户没有指定具体时间，使用默认时间（如"今天"默认使用当前时间，"明天"默认使用上午9点）
3. 如果用户只说了日期没有说时间，默认使用上午9点
4. 输出格式必须严格遵循：YYYY-MM-DD HH:mm:ss（24小时制）

请以JSON格式返回结果，格式如下：
{{
    "datetime": "YYYY-MM-DD HH:mm:ss",
    "reasoning": "解析理由"
}}

只返回JSON，不要返回其他内容。"""
        
        return prompt
    
    def _parse_response(self, response: str, reference_time: datetime) -> Dict[str, Any]:
        """
        解析LLM响应
        
        Args:
            response: LLM响应
            reference_time: 参考时间
            
        Returns:
            解析结果
        """
        import json
        import re
        
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                data = json.loads(response)
            
            datetime_str = data.get("datetime", "").strip()
            
            if not datetime_str:
                return {
                    "success": False,
                    "error": "LLM未返回日期时间"
                }
            
            # 验证日期时间格式
            try:
                dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # 尝试其他格式
                formats = [
                    "%Y-%m-%d",
                    "%Y/%m/%d",
                    "%Y-%m-%d %H:%M",
                ]
                dt = None
                for fmt in formats:
                    try:
                        dt = datetime.strptime(datetime_str, fmt)
                        # 如果只有日期，补充默认时间
                        if fmt in ["%Y-%m-%d", "%Y/%m/%d"]:
                            dt = dt.replace(hour=9, minute=0, second=0)
                        break
                    except ValueError:
                        continue
                
                if not dt:
                    return {
                        "success": False,
                        "error": f"日期时间格式无效: {datetime_str}"
                    }
            
            # 转换为毫秒时间戳
            timestamp = str(int(dt.timestamp() * 1000))
            
            return {
                "success": True,
                "datetime_str": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": timestamp,
                "reasoning": data.get("reasoning", "")
            }
            
        except json.JSONDecodeError as e:
            logger.warning(f"解析LLM响应失败: {e}, 响应: {response[:200]}")
            return {
                "success": False,
                "error": f"无法解析LLM响应: {str(e)}"
            }
        except Exception as e:
            logger.error(f"解析响应异常: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _call_llm(self, prompt: str) -> str:
        """调用LLM"""
        if hasattr(self.llm, 'ainvoke'):
            return await self.llm.ainvoke(prompt)
        elif hasattr(self.llm, '_call'):
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.llm._call, prompt)
        else:
            return self.llm._call(prompt)
