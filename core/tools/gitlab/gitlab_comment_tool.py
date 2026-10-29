#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GitLab 评论工具
将代码审查结果发送到 GitLab MR
"""
import aiohttp
from typing import Any, Dict, List, Optional
from loguru import logger

from core.tools.base.base_tool import BaseTool


class GitLabCommentTool(BaseTool):
    """
    GitLab 评论工具 - 将审查结果发送到 GitLab MR
    
    功能:
    - post_note(): 发布 MR 整体评论（Note）
    - post_discussion(): 发布讨论评论（Discussion）
    - post_inline_comment(): 发布行级评论（未来阶段实现）
    """
    
    def __init__(
        self,
        gitlab_url: str,
        gitlab_token: str,
        timeout: int = 30,
        **kwargs
    ):
        """
        初始化 GitLab 评论工具
        
        Args:
            gitlab_url: GitLab 服务器地址
            gitlab_token: GitLab 访问令牌
            timeout: 请求超时时间（秒）
            **kwargs: 其他参数
        """
        super().__init__(
            tool_name="gitlab_comment_tool",
            tool_description="将代码审查结果发送到 GitLab Merge Request",
            tool_type="function",
            **kwargs
        )
        
        self.gitlab_url = gitlab_url.rstrip('/')
        self.gitlab_token = gitlab_token
        self.timeout = timeout
        self.api_base = f"{self.gitlab_url}/api/v4"
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "PRIVATE-TOKEN": self.gitlab_token,
            "Content-Type": "application/json"
        }
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具（统一入口）
        
        Args:
            action: 操作类型（post_note/post_discussion）
            project_id: 项目 ID 或路径
            merge_request_iid: MR 的 IID
            body: 评论内容
            
        Returns:
            执行结果
        """
        action = kwargs.get("action", "post_note")
        project_id = kwargs.get("project_id")
        merge_request_iid = kwargs.get("merge_request_iid")
        body = kwargs.get("body")
        
        if not project_id or not merge_request_iid or not body:
            return {
                "success": False,
                "error": "缺少必需参数: project_id, merge_request_iid 或 body"
            }
        
        try:
            if action == "post_note":
                return await self.post_note(project_id, merge_request_iid, body)
            elif action == "post_discussion":
                return await self.post_discussion(project_id, merge_request_iid, body)
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作类型: {action}"
                }
        except Exception as e:
            logger.error(f"GitLabCommentTool 执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：post_note（发布评论）、post_discussion（发布讨论）",
                    "enum": ["post_note", "post_discussion"]
                },
                "project_id": {
                    "type": "string",
                    "description": "GitLab 项目 ID 或 URL 编码的路径"
                },
                "merge_request_iid": {
                    "type": "integer",
                    "description": "Merge Request 的 IID"
                },
                "body": {
                    "type": "string",
                    "description": "评论内容（支持 Markdown 格式）"
                }
            },
            "required": ["project_id", "merge_request_iid", "body"]
        }
    
    async def post_note(
        self,
        project_id: str,
        merge_request_iid: int,
        body: str
    ) -> Dict[str, Any]:
        """
        发布 MR 整体评论（Note）
        
        Args:
            project_id: 项目 ID 或 URL 编码的路径
            merge_request_iid: MR 的 IID
            body: 评论内容（支持 Markdown）
            
        Returns:
            发布结果
        """
        url = f"{self.api_base}/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._get_headers(),
                    json={"body": body},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return {
                            "success": True,
                            "data": {
                                "note_id": data.get("id"),
                                "body": data.get("body"),
                                "author": data.get("author", {}).get("username"),
                                "created_at": data.get("created_at"),
                                "web_url": data.get("noteable_url")
                            }
                        }
                    elif response.status == 401:
                        return {
                            "success": False,
                            "error": "认证失败，请检查 GitLab Token"
                        }
                    elif response.status == 404:
                        return {
                            "success": False,
                            "error": f"未找到 MR: project={project_id}, iid={merge_request_iid}"
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"GitLab API 错误 ({response.status}): {error_text}"
                        }
        except aiohttp.ClientError as e:
            logger.error(f"发布评论失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
    
    async def post_discussion(
        self,
        project_id: str,
        merge_request_iid: int,
        body: str
    ) -> Dict[str, Any]:
        """
        发布 MR 讨论评论（Discussion）
        
        Discussion 会创建一个可回复的讨论线程
        
        Args:
            project_id: 项目 ID 或 URL 编码的路径
            merge_request_iid: MR 的 IID
            body: 评论内容（支持 Markdown）
            
        Returns:
            发布结果
        """
        url = f"{self.api_base}/projects/{project_id}/merge_requests/{merge_request_iid}/discussions"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._get_headers(),
                    json={"body": body},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return {
                            "success": True,
                            "data": {
                                "discussion_id": data.get("id"),
                                "notes": [
                                    {
                                        "note_id": note.get("id"),
                                        "body": note.get("body"),
                                        "author": note.get("author", {}).get("username"),
                                        "created_at": note.get("created_at")
                                    }
                                    for note in data.get("notes", [])
                                ]
                            }
                        }
                    elif response.status == 401:
                        return {
                            "success": False,
                            "error": "认证失败，请检查 GitLab Token"
                        }
                    elif response.status == 404:
                        return {
                            "success": False,
                            "error": f"未找到 MR: project={project_id}, iid={merge_request_iid}"
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"GitLab API 错误 ({response.status}): {error_text}"
                        }
        except aiohttp.ClientError as e:
            logger.error(f"发布讨论失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
    
    async def post_inline_comment(
        self,
        project_id: str,
        merge_request_iid: int,
        body: str,
        file_path: str,
        line_number: int,
        line_type: str = "new",
        base_sha: Optional[str] = None,
        head_sha: Optional[str] = None,
        start_sha: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发布行级评论（阶段二实现）
        
        Args:
            project_id: 项目 ID
            merge_request_iid: MR 的 IID
            body: 评论内容
            file_path: 文件路径
            line_number: 行号
            line_type: 行类型（new/old）
            base_sha: base commit SHA
            head_sha: head commit SHA
            start_sha: start commit SHA
            
        Returns:
            发布结果
        """
        url = f"{self.api_base}/projects/{project_id}/merge_requests/{merge_request_iid}/discussions"
        
        position = {
            "position_type": "text",
            "new_path": file_path,
            "old_path": file_path,
        }
        
        if line_type == "new":
            position["new_line"] = line_number
        else:
            position["old_line"] = line_number
        
        if base_sha:
            position["base_sha"] = base_sha
        if head_sha:
            position["head_sha"] = head_sha
        if start_sha:
            position["start_sha"] = start_sha
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._get_headers(),
                    json={
                        "body": body,
                        "position": position
                    },
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        return {
                            "success": True,
                            "data": {
                                "discussion_id": data.get("id"),
                                "file_path": file_path,
                                "line_number": line_number,
                                "body": body
                            }
                        }
                    elif response.status == 401:
                        return {
                            "success": False,
                            "error": "认证失败，请检查 GitLab Token"
                        }
                    elif response.status == 404:
                        return {
                            "success": False,
                            "error": f"未找到 MR: project={project_id}, iid={merge_request_iid}"
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"GitLab API 错误 ({response.status}): {error_text}"
                        }
        except aiohttp.ClientError as e:
            logger.error(f"发布行级评论失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
    
    def format_review_comment(
        self,
        summary: str,
        issues: List[Dict[str, Any]],
        suggestions: List[str] = None,
        metadata: Dict[str, Any] = None,
        review_conclusion: str = None
    ) -> str:
        """
        格式化代码审查评论（Markdown 格式）
        
        Args:
            summary: 审查总结
            issues: 发现的问题列表
            suggestions: 改进建议
            metadata: 元数据（如审查耗时、文件数等）
            review_conclusion: 审核结论（passed/rejected/manual_review）
            
        Returns:
            格式化后的 Markdown 评论
        """
        lines = []
        
        lines.append("## 🤖 AI 代码审查报告")
        lines.append("")
        
        if review_conclusion:
            conclusion_map = {
                "passed": ("✅", "通过", "代码审查通过，可以合并"),
                "rejected": ("❌", "不通过", "存在严重问题，需要修复后再合并"),
                "manual_review": ("⚠️", "需要人工评判", "存在需要人工确认的问题")
            }
            icon, text, desc = conclusion_map.get(
                review_conclusion, 
                ("❓", "未知", "无法判定审核结果")
            )
            lines.append(f"### {icon} 审核结论：{text}")
            lines.append("")
            lines.append(f"> {desc}")
            lines.append("")
        
        if metadata:
            lines.append("### 📊 审查概览")
            lines.append("")
            lines.append("| 指标 | 值 |")
            lines.append("|------|-----|")
            if "reviewed_files" in metadata:
                lines.append(f"| 审查文件数 | {metadata['reviewed_files']} |")
            if "total_issues" in metadata:
                lines.append(f"| 发现问题数 | {metadata['total_issues']} |")
            if "review_time" in metadata:
                lines.append(f"| 审查耗时 | {metadata['review_time']:.2f}s |")
            lines.append("")
        
        lines.append("### 📝 审查总结")
        lines.append("")
        lines.append(summary)
        lines.append("")
        
        if issues:
            lines.append("### ⚠️ 发现的问题")
            lines.append("")
            
            severity_icons = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
                "info": "ℹ️"
            }
            
            for i, issue in enumerate(issues, 1):
                severity = issue.get("severity", "info")
                icon = severity_icons.get(severity, "ℹ️")
                file_path = issue.get("file", "")
                line = issue.get("line", "")
                description = issue.get("description", "")
                suggestion = issue.get("suggestion", "")
                
                lines.append(f"#### {icon} 问题 {i}: {issue.get('title', '未命名问题')}")
                lines.append("")
                if file_path:
                    location = f"`{file_path}`"
                    if line:
                        location += f" (行 {line})"
                    lines.append(f"**位置**: {location}")
                    lines.append("")
                lines.append(f"**描述**: {description}")
                if suggestion:
                    lines.append("")
                    lines.append(f"**建议**: {suggestion}")
                lines.append("")
        
        if suggestions:
            lines.append("### 💡 改进建议")
            lines.append("")
            for suggestion in suggestions:
                lines.append(f"- {suggestion}")
            lines.append("")
        
        lines.append("---")
        lines.append("*此报告由 AI 代码审查助手自动生成*")
        
        return "\n".join(lines)
