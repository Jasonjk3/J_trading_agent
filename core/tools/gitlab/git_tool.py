#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Git 工具
通过 GitLab API 获取 MR 的 diff 信息
"""
import aiohttp
from typing import Any, Dict, List, Optional
from loguru import logger

from core.tools.base.base_tool import BaseTool


class GitTool(BaseTool):
    """
    Git 工具 - 通过 GitLab API 获取 MR 变更信息
    
    功能:
    - get_merge_request_info(): 获取 MR 基本信息
    - get_merge_request_changes(): 获取 MR 文件变更列表
    - get_merge_request_diffs(): 获取 MR 的详细 diff
    """
    
    def __init__(
        self,
        gitlab_url: str,
        gitlab_token: str,
        timeout: int = 30,
        **kwargs
    ):
        """
        初始化 Git 工具
        
        Args:
            gitlab_url: GitLab 服务器地址（如 https://gitlab.com）
            gitlab_token: GitLab 访问令牌
            timeout: 请求超时时间（秒）
            **kwargs: 其他参数
        """
        super().__init__(
            tool_name="git_tool",
            tool_description="通过 GitLab API 获取 Merge Request 的代码变更信息",
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
            action: 操作类型（get_info/get_changes/get_diffs）
            project_id: 项目 ID 或路径（需要 URL 编码）
            merge_request_iid: MR 的 IID
            
        Returns:
            执行结果
        """
        action = kwargs.get("action", "get_changes")
        project_id = kwargs.get("project_id")
        merge_request_iid = kwargs.get("merge_request_iid")
        
        if not project_id or not merge_request_iid:
            return {
                "success": False,
                "error": "缺少必需参数: project_id 或 merge_request_iid"
            }
        
        try:
            if action == "get_info":
                return await self.get_merge_request_info(project_id, merge_request_iid)
            elif action == "get_changes":
                return await self.get_merge_request_changes(project_id, merge_request_iid)
            elif action == "get_diffs":
                return await self.get_merge_request_diffs(project_id, merge_request_iid)
            else:
                return {
                    "success": False,
                    "error": f"不支持的操作类型: {action}"
                }
        except Exception as e:
            logger.error(f"GitTool 执行失败: {e}", exc_info=True)
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
                    "description": "操作类型：get_info（获取MR信息）、get_changes（获取文件变更列表）、get_diffs（获取详细diff）",
                    "enum": ["get_info", "get_changes", "get_diffs"]
                },
                "project_id": {
                    "type": "string",
                    "description": "GitLab 项目 ID 或 URL 编码的路径"
                },
                "merge_request_iid": {
                    "type": "integer",
                    "description": "Merge Request 的 IID"
                }
            },
            "required": ["project_id", "merge_request_iid"]
        }
    
    async def get_merge_request_info(
        self,
        project_id: str,
        merge_request_iid: int
    ) -> Dict[str, Any]:
        """
        获取 MR 基本信息
        
        Args:
            project_id: 项目 ID 或 URL 编码的路径
            merge_request_iid: MR 的 IID
            
        Returns:
            MR 信息字典
        """
        url = f"{self.api_base}/projects/{project_id}/merge_requests/{merge_request_iid}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "data": {
                                "iid": data.get("iid"),
                                "title": data.get("title"),
                                "description": data.get("description"),
                                "state": data.get("state"),
                                "source_branch": data.get("source_branch"),
                                "target_branch": data.get("target_branch"),
                                "author": data.get("author", {}).get("username"),
                                "created_at": data.get("created_at"),
                                "updated_at": data.get("updated_at"),
                                "web_url": data.get("web_url"),
                                "changes_count": data.get("changes_count"),
                                "diff_refs": data.get("diff_refs")
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
            logger.error(f"获取 MR 信息失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
    
    async def get_merge_request_changes(
        self,
        project_id: str,
        merge_request_iid: int
    ) -> Dict[str, Any]:
        """
        获取 MR 文件变更列表
        
        Args:
            project_id: 项目 ID 或 URL 编码的路径
            merge_request_iid: MR 的 IID
            
        Returns:
            包含变更文件列表的字典
        """
        url = f"{self.api_base}/projects/{project_id}/merge_requests/{merge_request_iid}/changes"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        changes = data.get("changes", [])
                        
                        parsed_changes = []
                        for change in changes:
                            parsed_change = {
                                "old_path": change.get("old_path"),
                                "new_path": change.get("new_path"),
                                "new_file": change.get("new_file", False),
                                "renamed_file": change.get("renamed_file", False),
                                "deleted_file": change.get("deleted_file", False),
                                "diff": change.get("diff", ""),
                            }
                            parsed_changes.append(parsed_change)
                        
                        return {
                            "success": True,
                            "data": {
                                "title": data.get("title"),
                                "source_branch": data.get("source_branch"),
                                "target_branch": data.get("target_branch"),
                                "changes_count": len(parsed_changes),
                                "changes": parsed_changes
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
            logger.error(f"获取 MR 变更失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
    
    async def get_merge_request_diffs(
        self,
        project_id: str,
        merge_request_iid: int,
        unidiff_format: bool = True
    ) -> Dict[str, Any]:
        """
        获取 MR 的详细 diff 信息
        
        Args:
            project_id: 项目 ID 或 URL 编码的路径
            merge_request_iid: MR 的 IID
            unidiff_format: 是否使用统一 diff 格式
            
        Returns:
            包含详细 diff 的字典
        """
        url = f"{self.api_base}/projects/{project_id}/merge_requests/{merge_request_iid}/diffs"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        diffs = await response.json()
                        
                        parsed_diffs = []
                        for diff in diffs:
                            parsed_diff = {
                                "old_path": diff.get("old_path"),
                                "new_path": diff.get("new_path"),
                                "a_mode": diff.get("a_mode"),
                                "b_mode": diff.get("b_mode"),
                                "new_file": diff.get("new_file", False),
                                "renamed_file": diff.get("renamed_file", False),
                                "deleted_file": diff.get("deleted_file", False),
                                "diff": diff.get("diff", ""),
                            }
                            parsed_diffs.append(parsed_diff)
                        
                        return {
                            "success": True,
                            "data": {
                                "diffs_count": len(parsed_diffs),
                                "diffs": parsed_diffs
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
            logger.error(f"获取 MR diff 失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
    
    async def get_file_content(
        self,
        project_id: str,
        file_path: str,
        ref: str
    ) -> Dict[str, Any]:
        """
        获取指定文件的完整内容
        
        Args:
            project_id: 项目 ID 或 URL 编码的路径
            file_path: 文件路径
            ref: 分支名或提交 SHA
            
        Returns:
            包含文件内容的字典
        """
        import urllib.parse
        
        # URL 编码文件路径 - 斜杠也需要编码
        encoded_file_path = urllib.parse.quote(file_path, safe='')
        url = f"{self.api_base}/projects/{project_id}/repository/files/{encoded_file_path}/raw"
        
        params = {"ref": ref}
        
        logger.debug(f"获取文件内容 API 请求: URL={url}, ref={ref}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    logger.debug(f"API 响应状态: {response.status} for {file_path}")
                    
                    if response.status == 200:
                        content = await response.text()
                        logger.debug(f"成功获取文件内容: {file_path} ({len(content)} 字符)")
                        return {
                            "success": True,
                            "content": content,
                            "file_path": file_path,
                            "ref": ref
                        }
                    elif response.status == 401:
                        logger.warning(f"获取文件内容认证失败: {file_path}")
                        return {
                            "success": False,
                            "error": "认证失败，请检查 GitLab Token"
                        }
                    elif response.status == 404:
                        # 404 是正常情况：可能是新增文件,在源分支还不存在
                        logger.debug(f"文件不存在(可能是新增文件): {file_path} (ref: {ref})")
                        return {
                            "success": False,
                            "error": f"未找到文件: {file_path} (ref: {ref})",
                            "is_new_file": True
                        }
                    else:
                        error_text = await response.text()
                        logger.warning(f"获取文件内容失败 ({response.status}): {file_path}, {error_text[:200]}")
                        return {
                            "success": False,
                            "error": f"GitLab API 错误 ({response.status}): {error_text[:200]}"
                        }
        except aiohttp.ClientError as e:
            logger.error(f"获取文件内容网络异常: {file_path}, {e}", exc_info=True)
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
    
    def parse_diff(self, diff_content: str) -> Dict[str, Any]:
        """
        解析 diff 内容为结构化数据
        
        Args:
            diff_content: diff 字符串
            
        Returns:
            解析后的结构化数据
        """
        lines = diff_content.split('\n')
        hunks = []
        current_hunk = None
        
        for line in lines:
            if line.startswith('@@'):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {
                    "header": line,
                    "added_lines": [],
                    "removed_lines": [],
                    "context_lines": []
                }
            elif current_hunk:
                if line.startswith('+') and not line.startswith('+++'):
                    current_hunk["added_lines"].append(line[1:])
                elif line.startswith('-') and not line.startswith('---'):
                    current_hunk["removed_lines"].append(line[1:])
                else:
                    current_hunk["context_lines"].append(line)
        
        if current_hunk:
            hunks.append(current_hunk)
        
        total_added = sum(len(h["added_lines"]) for h in hunks)
        total_removed = sum(len(h["removed_lines"]) for h in hunks)
        
        return {
            "hunks_count": len(hunks),
            "total_added_lines": total_added,
            "total_removed_lines": total_removed,
            "hunks": hunks
        }
