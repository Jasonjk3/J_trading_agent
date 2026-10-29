#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码审查 Agent
通过 AI 分析 GitLab MR 的代码变更并输出审查结果
"""
import json
import re
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4
from loguru import logger

from core.agent_base.task_base_agent import TaskBaseAgent
from core.models.agent_models import AgentStatus
from core.agent_mixin.task_agent_mixin import TaskAgentMixin
from core.llm.llm_models import LLMModels
from core.llm.llm_factory import LLMFactory
from core.llm.base.base_llm import BaseLLM
from core.tools.gitlab.git_tool import GitTool
from core.tools.gitlab.gitlab_comment_tool import GitLabCommentTool


class CodeReviewAgent(TaskAgentMixin, TaskBaseAgent):
    """
    代码审查 Agent - 审查 GitLab MR 的代码变更
    
    功能:
    - 获取 MR 的代码变更
    - AI 分析代码（语法、规范、潜在bug）
    - 将审查结果发送到 GitLab
    """

    AGENT_TYPE = "code_review"
    DEFAULT_CAPABILITIES = ["code_review", "static_analysis", "bug_detection"]
    
    # ==================== LLM 配置 ====================
    LLM_CONFIG = {
        "model_name": LLMModels.GPT_4O,
        "temperature": 0.2,
        "max_completion_tokens": 8192,
        "api_key_env": LLMModels.OPENAI_API_KEY_ENV
    }
    
    # ==================== 系统 Prompt ====================
    SYSTEM_PROMPT = """你是一个专业的代码审查专家，具有丰富的软件开发经验。你的任务是审查代码变更（diff），识别潜在问题并提供改进建议。

## 审查维度

请从以下维度进行代码审查：

### 1. 代码质量
- **语法错误**: 检查明显的语法问题
- **代码规范**: 检查命名规范、代码格式、注释规范
- **代码风格**: 检查代码可读性、一致性

### 2. 潜在 Bug
- **逻辑错误**: 条件判断、循环逻辑、边界条件
- **空指针/空值**: 未处理的 null/None/undefined
- **资源泄漏**: 未关闭的文件、连接、流
- **并发问题**: 线程安全、竞态条件
- **类型错误**: 类型不匹配、隐式转换

### 3. 安全问题
- **注入漏洞**: SQL注入、XSS、命令注入
- **敏感信息**: 硬编码密码、密钥、token
- **权限问题**: 不当的权限检查

### 4. 性能问题
- **效率问题**: 不必要的循环、重复计算
- **内存问题**: 内存泄漏、大对象处理
- **数据库问题**: N+1查询、缺少索引提示

### 5. 最佳实践
- **设计问题**: 违反SOLID原则、过度耦合
- **错误处理**: 异常处理不当、错误信息不明确
- **测试覆盖**: 缺少单元测试、边界测试

## 审查标准

- **critical（严重）**: 会导致程序崩溃、数据丢失、安全漏洞
- **high（高）**: 可能导致功能异常、性能严重下降
- **medium（中）**: 代码质量问题、可维护性问题
- **low（低）**: 代码风格问题、轻微的改进建议
- **info（信息）**: 建议性意见、最佳实践提示

## 输出格式

请以 JSON 格式返回审查结果：

```json
{
    "review_conclusion": "passed/rejected/manual_review",
    "summary": "整体审查总结（1-3句话概述代码质量和主要问题）",
    "overall_quality": "good/acceptable/needs_improvement/poor",
    "issues": [
        {
            "severity": "critical/high/medium/low/info",
            "category": "bug/security/performance/style/best_practice",
            "title": "问题标题",
            "file": "文件路径",
            "line": "行号或行范围（如有）",
            "description": "问题描述",
            "suggestion": "修复建议",
            "code_snippet": "相关代码片段（可选）"
        }
    ],
    "suggestions": [
        "整体改进建议1",
        "整体改进建议2"
    ],
    "stats": {
        "files_reviewed": 0,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0,
        "info_count": 0
    }
}
```

## 审核结论判定规则

请根据以下规则判定审核结论（review_conclusion）：

- **passed（通过）**: 没有 critical 或 high 级别问题，代码质量为 good 或 acceptable
- **rejected（不通过）**: 存在 critical 级别问题，或存在多个 high 级别问题，或存在明显的安全漏洞
- **manual_review（需要人工评判）**: 存在 1-2 个 high 级别问题，或代码逻辑复杂难以自动判断，或涉及业务逻辑需要人工确认

## 审查原则（重要）

1. **结合完整上下文理解代码**：
   - 会提供文件的完整内容或关键上下文代码
   - 充分理解变量声明、导入依赖、函数签名后再下结论
   - 理解代码的变更意图和业务场景
- 

2. **关注真正有影响的问题**：
   - **优先报告**: 逻辑错误、安全漏洞、性能问题、资源泄漏
   - **谨慎报告**: 代码风格、命名规范（仅在明显违背约定时报告）
   - **避免报告**: 纯格式化变更、无害的小改动、个人偏好问题

3. **避免误报和过度报告**：
   - 当代码上下文不足时，不要妄下结论
   - 不要对测试文件、配置文件过度苛刻
   - 不要将正常的代码实践标记为问题
   - 多个相似问题应合并为一个 issue

4. **严格控制 issue 数量和质量**：
   - 只报告确实需要修改的问题
   - 格式化/风格问题应该降级为 low 或完全忽略
   - 不确定的问题不要报告，或者降级为 info
   - 优先报告高价值的问题（bug、安全、性能）

5. **智能判断问题严重性**：
   - 纯风格问题最多为 low，不应该是 medium 或更高
   - 小的改进建议应该是 info，不要当作问题
   - medium 及以上级别必须是真正影响代码质量的问题

6. **提供具体建议**：
   - 每个问题都应有明确的修复建议和示例代码
   - 避免笼统的建议如"改进代码质量"
   - 保持客观，专注于代码质量

7. **特殊文件类型处理**：
   - **测试文件**: 降低审查严格度，允许更灵活的写法
   - **配置文件**: 只关注语法错误和敏感信息
   - **自动生成文件**: 跳过或快速审查
   - **文档文件**: 只检查明显错误

只返回 JSON，不要返回其他内容。"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_name: str = "代码审查Agent",
        gitlab_url: Optional[str] = None,
        gitlab_token: Optional[str] = None,
        max_diff_lines: int = 5000,
        context_lines: int = 15,
        include_full_file: bool = True,
        **kwargs
    ):
        """
        初始化代码审查 Agent
        
        Args:
            agent_id: Agent ID
            agent_name: Agent 名称
            gitlab_url: GitLab 服务器地址
            gitlab_token: GitLab 访问令牌
            max_diff_lines: 单次审查的最大 diff 行数
            context_lines: 每个 diff hunk 前后获取的上下文行数（默认 15 行）
            include_full_file: 是否包含完整文件内容（小文件 <500 行）
            **kwargs: 其他参数
        """
        agent_id = agent_id or str(uuid4())
        
        super().__init__(
            agent_id=agent_id,
            agent_name=agent_name,
            agent_type=self.AGENT_TYPE,
            capabilities=self.DEFAULT_CAPABILITIES,
            max_concurrent_tasks=kwargs.get("max_concurrent_tasks", 5),
            metadata=kwargs.get("metadata", {})
        )
        
        self.gitlab_url = gitlab_url
        self.gitlab_token = gitlab_token
        self.max_diff_lines = max_diff_lines
        self.context_lines = context_lines
        self.include_full_file = include_full_file
        
        self.git_tool: Optional[GitTool] = None
        self.comment_tool: Optional[GitLabCommentTool] = None
        
        self.system_prompt = self._build_system_prompt()
        
        # 需要跳过或降低审查的文件模式
        self.skip_patterns = [
            r'.*\.lock$',  # lock 文件
            r'.*\.min\.js$',  # 压缩的 js 文件
            r'.*\.min\.css$',  # 压缩的 css 文件
            r'.*\.bundle\..*$',  # 打包文件
            r'dist/.*',  # 构建目录
            r'build/.*',  # 构建目录
            r'node_modules/.*',  # 依赖目录
            r'vendor/.*',  # 依赖目录
        ]
        
        # 配置文件模式（降低审查严格度）
        self.config_patterns = [
            r'.*\.json$',
            r'.*\.yaml$',
            r'.*\.yml$',
            r'.*\.toml$',
            r'.*\.ini$',
            r'.*\.conf$',
        ]
        
        # 测试文件模式（降低审查严格度）
        self.test_patterns = [
            r'.*/test[s]?/.*',
            r'.*test_.*\.py$',
            r'.*_test\.py$',
            r'.*\.test\.js$',
            r'.*\.test\.ts$',
            r'.*\.spec\.js$',
            r'.*\.spec\.ts$',
        ]

    async def initialize(self) -> bool:
        """初始化 Agent"""
        try:
            if not self._get_llm():
                logger.error("代码审查Agent创建LLM实例失败")
                await self.update_status(AgentStatus.ERROR)
                return False
            
            self.system_prompt = self._build_system_prompt()
            
            logger.info(f"代码审查Agent初始化成功: {self.agent_id}")
            return True
        except Exception as e:
            logger.error(f"代码审查Agent初始化失败: {e}", exc_info=True)
            await self.update_status(AgentStatus.ERROR)
            return False

    async def cleanup(self) -> bool:
        """清理资源"""
        try:
            await self.update_status(AgentStatus.IDLE)
            return True
        except Exception as e:
            logger.error(f"代码审查Agent清理失败: {e}")
            return False

    def _init_tools(self, gitlab_url: str, gitlab_token: str) -> None:
        """
        初始化 GitLab 工具
        
        Args:
            gitlab_url: GitLab 服务器地址
            gitlab_token: GitLab 访问令牌
        """
        self.git_tool = GitTool(
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token
        )
        self.comment_tool = GitLabCommentTool(
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token
        )
    
    def _should_skip_file(self, file_path: str) -> bool:
        """
        判断是否应该跳过该文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否跳过
        """
        import re
        for pattern in self.skip_patterns:
            if re.match(pattern, file_path):
                return True
        return False
    
    def _is_config_file(self, file_path: str) -> bool:
        """
        判断是否为配置文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否为配置文件
        """
        import re
        for pattern in self.config_patterns:
            if re.match(pattern, file_path):
                return True
        return False
    
    def _is_test_file(self, file_path: str) -> bool:
        """
        判断是否为测试文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否为测试文件
        """
        import re
        for pattern in self.test_patterns:
            if re.match(pattern, file_path):
                return True
        return False
    
    def _get_file_type(self, file_path: str) -> str:
        """
        获取文件类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件类型: normal/config/test/skip
        """
        if self._should_skip_file(file_path):
            return "skip"
        if self._is_test_file(file_path):
            return "test"
        if self._is_config_file(file_path):
            return "config"
        return "normal"
    
    def _is_trivial_change(self, diff: str) -> bool:
        """
        判断是否为无意义的微小变更（纯格式化、空白字符等）
        
        Args:
            diff: diff 内容
            
        Returns:
            是否为微小变更
        """
        lines = diff.split('\n')
        meaningful_changes = 0
        
        for line in lines:
            if not line.startswith(('+', '-')):
                continue
            if line.startswith(('+++', '---')):
                continue
            
            content = line[1:].strip()
            
            # 跳过空行
            if not content:
                continue
            
            # 跳过纯注释行
            if content.startswith(('#', '//', '/*', '*', '*/')):
                continue
            
            meaningful_changes += 1
        
        # 少于 3 行有意义的变更视为微小变更
        return meaningful_changes < 3

    def _create_llm_from_config(self, llm_config: Dict[str, Any]) -> Optional[BaseLLM]:
        """
        根据配置创建 LLM 实例
        
        Args:
            llm_config: LLM 配置字典，包含：
                - model_name: 模型名称
                - api_key: API 密钥
                - api_type: API 类型 (openai/deepseek/generic)
                - api_url: API URL (可选)
                - temperature: 温度 (可选)
                - max_tokens: 最大 token 数 (可选)
                - use_max_completion_tokens: 是否使用 max_completion_tokens (可选)
                - extra_headers: 额外请求头 (可选)
                - extra_body: 额外请求体 (可选)
                
        Returns:
            LLM 实例，如果创建失败则返回 None
        """
        try:
            model_name = llm_config.get("model_name")
            api_key = llm_config.get("api_key")
            api_type = llm_config.get("api_type", "generic")
            
            if not model_name or not api_key:
                logger.warning("LLM 配置缺少必要参数: model_name 或 api_key")
                return None
            
            llm = LLMFactory.create_llm_direct(
                model_name=model_name,
                api_key=api_key,
                api_type=api_type,
                api_url=llm_config.get("api_url"),
                temperature=llm_config.get("temperature", self.LLM_CONFIG.get("temperature", 0.2)),
                max_tokens=llm_config.get("max_tokens", self.LLM_CONFIG.get("max_completion_tokens", 8192)),
                use_max_completion_tokens=llm_config.get("use_max_completion_tokens", False),
                extra_headers=llm_config.get("extra_headers"),
                extra_body=llm_config.get("extra_body"),
            )
            
            if llm:
                logger.info(f"成功创建指定模型 LLM 实例: {model_name}")
            else:
                logger.warning(f"创建指定模型 LLM 实例失败: {model_name}")
            
            return llm
            
        except Exception as e:
            logger.error(f"创建 LLM 实例失败: {e}", exc_info=True)
            return None

    # ==================== TaskBaseAgent 抽象方法实现 ====================
    
    def _validate_task(self, task: Dict[str, Any]) -> bool:
        """验证任务格式"""
        project_id = task.get("project_id")
        merge_request_iid = task.get("merge_request_iid")
        gitlab_url = task.get("gitlab_url") or self.gitlab_url
        gitlab_token = task.get("gitlab_token") or self.gitlab_token
        
        if not project_id:
            logger.warning("任务验证失败：缺少 project_id")
            return False
        
        if not merge_request_iid:
            logger.warning("任务验证失败：缺少 merge_request_iid")
            return False
        
        if not gitlab_url:
            logger.warning("任务验证失败：缺少 gitlab_url")
            return False
        
        if not gitlab_token:
            logger.warning("任务验证失败：缺少 gitlab_token")
            return False
        
        return True
    
    def _extract_task_params(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """提取任务参数"""
        return {
            "project_id": task.get("project_id"),
            "merge_request_iid": task.get("merge_request_iid"),
            "gitlab_url": task.get("gitlab_url") or self.gitlab_url,
            "gitlab_token": task.get("gitlab_token") or self.gitlab_token,
            "post_comment": task.get("post_comment", True),
            "task_id": task.get("task_id") or str(uuid4())
        }
    
    def _build_user_input_prompt(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建用户输入 Prompt"""
        changes = context.get("changes", []) if context else []
        mr_info = context.get("mr_info", {}) if context else {}
        file_contents = context.get("file_contents", {}) if context else {}
        
        prompt_parts = []
        
        prompt_parts.append(f"## MR 信息")
        prompt_parts.append(f"- 标题: {mr_info.get('title', '未知')}")
        prompt_parts.append(f"- 源分支: {mr_info.get('source_branch', '未知')}")
        prompt_parts.append(f"- 目标分支: {mr_info.get('target_branch', '未知')}")
        prompt_parts.append(f"- 变更文件数: {len(changes)}")
        prompt_parts.append("")
        
        prompt_parts.append("## 代码变更")
        prompt_parts.append("")
        
        total_lines = 0
        skipped_files = []
        reviewed_files = []
        
        for change in changes:
            file_path = change.get("new_path") or change.get("old_path", "未知文件")
            diff = change.get("diff", "")
            
            # 判断文件类型
            file_type = self._get_file_type(file_path)
            
            # 跳过不需要审查的文件
            if file_type == "skip":
                skipped_files.append(file_path)
                continue
            
            # 判断是否为微小变更
            if self._is_trivial_change(diff):
                logger.debug(f"跳过微小变更: {file_path}")
                skipped_files.append(file_path)
                continue
            
            # 检查行数限制
            diff_lines = diff.count('\n')
            if total_lines + diff_lines > self.max_diff_lines:
                prompt_parts.append(f"\n### ⚠️ 已达到最大审查行数限制 ({self.max_diff_lines} 行)")
                prompt_parts.append(f"剩余 {len(changes) - changes.index(change)} 个文件未审查")
                break
            
            total_lines += diff_lines
            
            change_type = "新增" if change.get("new_file") else \
                         "删除" if change.get("deleted_file") else \
                         "重命名" if change.get("renamed_file") else "修改"
            
            file_type_label = ""
            if file_type == "test":
                file_type_label = " [测试文件]"
            elif file_type == "config":
                file_type_label = " [配置文件]"
            
            prompt_parts.append(f"### 文件: `{file_path}` ({change_type}){file_type_label}")
            
            # 如果有完整文件内容，先展示
            if file_path in file_contents:
                full_content = file_contents[file_path]
                content_lines = full_content.split('\n')
                
                # 如果文件较小（<500行），显示完整内容
                if len(content_lines) <= 500:
                    prompt_parts.append("")
                    prompt_parts.append("**完整文件内容（用于上下文参考）：**")
                    prompt_parts.append("```")
                    prompt_parts.append(full_content)
                    prompt_parts.append("```")
                    prompt_parts.append("")
                else:
                    # 文件太大，只显示导入和关键定义
                    prompt_parts.append("")
                    prompt_parts.append("**文件头部（导入和关键定义）：**")
                    prompt_parts.append("```")
                    prompt_parts.append('\n'.join(content_lines[:50]))
                    prompt_parts.append("... (文件较大，已省略)")
                    prompt_parts.append("```")
                    prompt_parts.append("")
            elif change_type == "新增":
                # 新增文件没有原始内容是正常的
                prompt_parts.append("")
                prompt_parts.append("**ℹ️ 新增文件，无原始内容**")
                prompt_parts.append("")
            else:
                # 修改的文件但没获取到内容，可能是权限问题或文件太大
                prompt_parts.append("")
                prompt_parts.append("**⚠️ 未获取到完整文件内容，仅基于 diff 审查**")
                prompt_parts.append("")
            
            # 显示 diff
            prompt_parts.append("**代码变更（diff）：**")
            prompt_parts.append("```diff")
            prompt_parts.append(diff)
            prompt_parts.append("```")
            prompt_parts.append("")
            
            reviewed_files.append(file_path)
        
        if skipped_files:
            prompt_parts.append(f"\n### ℹ️ 已跳过 {len(skipped_files)} 个文件")
            prompt_parts.append("（自动生成文件、lock文件、或微小格式化变更）")
            prompt_parts.append("")
        
        prompt_parts.append("---")
        prompt_parts.append("")
        prompt_parts.append("## 审查要求")
        prompt_parts.append("")
        prompt_parts.append("请对以上代码变更进行审查，重点关注：")
        prompt_parts.append("1. **结合完整文件内容理解代码上下文**")
        prompt_parts.append("2. **只报告真正有影响的问题**（逻辑错误、安全问题、性能问题）")
        prompt_parts.append("3. **避免过度报告格式化和风格问题**")
        prompt_parts.append("4. **测试文件和配置文件降低审查严格度**")
        prompt_parts.append("5. **不确定的问题不要报告**")
        
        return "\n".join(prompt_parts)
    
    def _parse_llm_response(
        self,
        llm_response: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """解析 LLM 响应"""
        try:
            if not llm_response or not llm_response.strip():
                logger.warning("LLM响应为空")
                return self._default_review_result("LLM 响应为空")
            
            result = None
            
            try:
                result = json.loads(llm_response.strip())
            except json.JSONDecodeError:
                pass
            
            if result is None:
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
            
            if result is None:
                code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
                if code_block_match:
                    try:
                        result = json.loads(code_block_match.group(1))
                    except json.JSONDecodeError:
                        pass
            
            if result is None:
                logger.warning(f"无法解析 LLM 响应为 JSON: {llm_response[:500]}")
                return self._default_review_result(f"解析失败: {llm_response[:200]}")
            
            review_conclusion = result.get("review_conclusion")
            if not review_conclusion:
                review_conclusion = self._determine_review_conclusion(result)
            
            return {
                "success": True,
                "review_conclusion": review_conclusion,
                "summary": result.get("summary", "审查完成"),
                "overall_quality": result.get("overall_quality", "acceptable"),
                "issues": result.get("issues", []),
                "suggestions": result.get("suggestions", []),
                "stats": result.get("stats", {})
            }
            
        except Exception as e:
            logger.error(f"解析审查结果失败: {e}", exc_info=True)
            return self._default_review_result(str(e))
    
    def _default_review_result(self, error_msg: str) -> Dict[str, Any]:
        """返回默认审查结果"""
        return {
            "success": False,
            "review_conclusion": "manual_review",
            "summary": f"审查失败: {error_msg}",
            "overall_quality": "unknown",
            "issues": [],
            "suggestions": [],
            "stats": {}
        }
    
    def _determine_review_conclusion(self, result: Dict[str, Any]) -> str:
        """
        根据审查结果自动判定审核结论（后备逻辑）
        
        Args:
            result: LLM 返回的审查结果
            
        Returns:
            审核结论: passed/rejected/manual_review
        """
        issues = result.get("issues", [])
        stats = result.get("stats", {})
        overall_quality = result.get("overall_quality", "acceptable")
        
        critical_count = stats.get("critical_count", 0)
        high_count = stats.get("high_count", 0)
        
        if critical_count == 0 and high_count == 0:
            for issue in issues:
                severity = issue.get("severity", "").lower()
                if severity == "critical":
                    critical_count += 1
                elif severity == "high":
                    high_count += 1
        
        has_security_issue = any(
            issue.get("category", "").lower() == "security" and 
            issue.get("severity", "").lower() in ["critical", "high"]
            for issue in issues
        )
        
        if critical_count > 0 or has_security_issue:
            return "rejected"
        
        if high_count >= 3:
            return "rejected"
        
        if high_count > 0 or overall_quality in ["needs_improvement", "poor"]:
            return "manual_review"
        
        return "passed"

    # ==================== 核心执行逻辑 ====================
    
    async def _get_file_content(
        self,
        project_id: str,
        file_path: str,
        ref: str
    ) -> Optional[str]:
        """
        获取文件完整内容
        
        Args:
            project_id: 项目 ID
            file_path: 文件路径
            ref: 分支或提交 SHA
            
        Returns:
            文件内容，失败返回 None
        """
        try:
            result = await self.git_tool.get_file_content(
                project_id=project_id,
                file_path=file_path,
                ref=ref
            )
            
            if result.get("success"):
                return result.get("content", "")
            else:
                # 检查是否是新增文件导致的 404
                if result.get("is_new_file"):
                    logger.debug(f"跳过新增文件(源分支不存在): {file_path}")
                else:
                    logger.warning(f"获取文件内容失败: {file_path}, error={result.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"获取文件内容异常: {file_path}, error={e}")
            return None
    
    async def _execute_normal_mode(
        self,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行普通模式审查"""
        start_time = time.time()
        
        project_id = params.get("project_id")
        merge_request_iid = params.get("merge_request_iid")
        gitlab_url = params.get("gitlab_url")
        gitlab_token = params.get("gitlab_token")
        post_comment = params.get("post_comment", True)
        
        self._init_tools(gitlab_url, gitlab_token)
        
        original_llm = None
        custom_llm = None
        llm_config = context.get("llm_config") if context else None
        
        if llm_config:
            custom_llm = self._create_llm_from_config(llm_config)
            if custom_llm:
                original_llm = self.llm
                self.llm = custom_llm
                logger.info(f"使用指定模型进行审查: {llm_config.get('model_name')}")
            else:
                logger.warning("指定模型创建失败，使用默认模型")
        
        try:
            logger.info(f"开始审查 MR: project={project_id}, iid={merge_request_iid}")
            
            mr_result = await self.git_tool.get_merge_request_info(project_id, merge_request_iid)
            if not mr_result.get("success"):
                return {
                    "success": False,
                    "error": f"获取 MR 信息失败: {mr_result.get('error')}"
                }
            mr_info = mr_result.get("data", {})
            
            changes_result = await self.git_tool.get_merge_request_changes(project_id, merge_request_iid)
            if not changes_result.get("success"):
                return {
                    "success": False,
                    "error": f"获取 MR 变更失败: {changes_result.get('error')}"
                }
            
            changes_data = changes_result.get("data", {})
            changes = changes_data.get("changes", [])
            
            if not changes:
                return {
                    "success": True,
                    "summary": "没有代码变更需要审查",
                    "overall_quality": "good",
                    "issues": [],
                    "suggestions": [],
                    "stats": {"files_reviewed": 0}
                }
            
            # 获取文件完整内容（用于提供上下文）
            file_contents = {}
            source_branch = mr_info.get("source_branch", "")
            
            if self.include_full_file and source_branch:
                logger.info(f"开始获取变更文件的完整内容... (分支: {source_branch}, 共 {len(changes)} 个文件)")
                for change in changes:
                    file_path = change.get("new_path")
                    if not file_path:
                        logger.debug(f"跳过: 文件路径为空")
                        continue
                    
                    # 跳过不需要获取内容的文件
                    file_type = self._get_file_type(file_path)
                    if file_type == "skip":
                        logger.debug(f"跳过: {file_path} (类型: skip)")
                        continue
                    
                    # 跳过删除的文件
                    if change.get("deleted_file"):
                        logger.debug(f"跳过: {file_path} (已删除)")
                        continue
                    
                    # 获取文件内容
                    logger.debug(f"正在获取文件内容: {file_path}")
                    content = await self._get_file_content(
                        project_id=project_id,
                        file_path=file_path,
                        ref=source_branch
                    )
                    
                    if content:
                        file_contents[file_path] = content
                        logger.info(f"✓ 已获取文件内容: {file_path} ({len(content)} 字符)")
                    else:
                        logger.debug(f"✗ 未获取到文件内容: {file_path}")
                
                logger.info(f"完成获取文件内容: {len(file_contents)}/{len(changes)} 个文件")
            else:
                if not self.include_full_file:
                    logger.info("跳过获取文件内容 (include_full_file=False)")
                if not source_branch:
                    logger.warning("跳过获取文件内容 (source_branch 为空)")
            
            review_context = {
                "mr_info": mr_info,
                "changes": changes,
                "file_contents": file_contents
            }
            
            user_message = self._build_user_input_prompt(params, review_context)
            messages = self._build_messages(
                user_message=user_message,
                include_system_prompt=True
            )
            
            llm_response = await self._call_llm_with_messages(messages)
            
            review_result = self._parse_llm_response(llm_response, params, review_context)
            
            review_time = time.time() - start_time
            review_result["review_time"] = review_time
            review_result["reviewed_files"] = len(changes)
            review_result["mr_info"] = {
                "title": mr_info.get("title"),
                "source_branch": mr_info.get("source_branch"),
                "target_branch": mr_info.get("target_branch"),
                "web_url": mr_info.get("web_url")
            }
            
            if llm_config and custom_llm:
                review_result["model_used"] = llm_config.get("model_name")
            
            if post_comment and review_result.get("success"):
                await self._post_review_comment(
                    project_id=project_id,
                    merge_request_iid=merge_request_iid,
                    review_result=review_result
                )
            
            logger.info(
                f"MR 审查完成: project={project_id}, iid={merge_request_iid}, "
                f"files={len(changes)}, issues={len(review_result.get('issues', []))}, "
                f"time={review_time:.2f}s"
            )
            
            return review_result
            
        finally:
            if original_llm is not None:
                self.llm = original_llm
                logger.debug("已恢复默认 LLM 实例")
    
    async def _post_review_comment(
        self,
        project_id: str,
        merge_request_iid: int,
        review_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """发布审查评论到 GitLab"""
        try:
            comment_body = self.comment_tool.format_review_comment(
                summary=review_result.get("summary", "审查完成"),
                issues=review_result.get("issues", []),
                suggestions=review_result.get("suggestions", []),
                metadata={
                    "reviewed_files": review_result.get("reviewed_files", 0),
                    "total_issues": len(review_result.get("issues", [])),
                    "review_time": review_result.get("review_time", 0)
                },
                review_conclusion=review_result.get("review_conclusion")
            )
            
            result = await self.comment_tool.post_note(
                project_id=project_id,
                merge_request_iid=merge_request_iid,
                body=comment_body
            )
            
            if result.get("success"):
                logger.info(f"审查评论已发布: project={project_id}, iid={merge_request_iid}")
            else:
                logger.warning(f"发布审查评论失败: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"发布审查评论异常: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
