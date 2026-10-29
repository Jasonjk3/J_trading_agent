# 飞书 SDK 工具使用说明

## 概述

飞书 SDK 工具将 `/lib/feishu` 封装好的 SDK 封装为 Agent 可用的工具，无需通过 MCP，直接调用飞书 API。

## 工具列表

### 1. FeishuContactTool - 通讯录工具

**功能**：查询用户和部门信息

**支持的操作**：
- `get_user_by_mobiles` - 通过手机号查询用户
- `get_user_by_emails` - 通过邮箱查询用户
- `get_departments` - 获取部门列表
- `get_user_by_department` - 根据部门获取用户列表

**使用示例**：
```python
from core.tools.feishu import FeishuContactTool

tool = FeishuContactTool(app_id="your_app_id", app_secret="your_app_secret")

# 通过手机号查询用户
result = await tool.execute(
    action="get_user_by_mobiles",
    mobiles=["13800138000"]
)

# 获取部门列表
result = await tool.execute(
    action="get_departments",
    department_id="0",  # 根部门
    fetch_child=True
)
```

### 2. FeishuApprovalTool - 审批工具

**功能**：查询审批实例信息

**支持的操作**：
- `get_instance_detail` - 获取审批实例详情
- `get_instance_list` - 获取审批实例列表

**使用示例**：
```python
from core.tools.feishu import FeishuApprovalTool

tool = FeishuApprovalTool(app_id="your_app_id", app_secret="your_app_secret")

# 获取审批实例详情
result = await tool.execute(
    action="get_instance_detail",
    instance_id="instance_123"
)

# 获取审批实例列表
result = await tool.execute(
    action="get_instance_list",
    approval_code="approval_123",
    start_time="2024-01-01 00:00:00",
    end_time="2024-12-31 23:59:59"
)
```

### 3. FeishuBitableTool - 多维表格工具

**功能**：操作多维表格数据

**支持的操作**：
- `create_record` - 创建单条记录
- `batch_create_records` - 批量创建记录
- `search_records` - 搜索记录（支持分页、过滤、排序）
- `update_record` - 更新记录
- `delete_record` - 删除记录

**使用示例**：
```python
from core.tools.feishu import FeishuBitableTool

tool = FeishuBitableTool(app_id="your_app_id", app_secret="your_app_secret")

# 创建记录
result = await tool.execute(
    action="create_record",
    app_token="app_token_123",
    table_id="table_123",
    fields={"姓名": "张三", "年龄": 25}
)

# 搜索记录
result = await tool.execute(
    action="search_records",
    app_token="app_token_123",
    table_id="table_123",
    page_size=100
)
```

### 4. FeishuImTool - 即时消息工具

**功能**：上传图片和文件

**支持的操作**：
- `upload_image` - 上传图片
- `upload_file` - 上传文件

**使用示例**：
```python
from core.tools.feishu import FeishuImTool

tool = FeishuImTool(app_id="your_app_id", app_secret="your_app_secret")

# 上传图片
result = await tool.execute(
    action="upload_image",
    file_path="/path/to/image.jpg"
)

# 上传文件
result = await tool.execute(
    action="upload_file",
    file_path="/path/to/file.pdf",
    file_name="document.pdf"
)
```

## 接入到 Agent

### 基本使用

```python
from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
from core.tools.feishu import FeishuContactTool, FeishuApprovalTool

# 创建工具
contact_tool = FeishuContactTool(app_id="your_app_id", app_secret="your_app_secret")
approval_tool = FeishuApprovalTool(app_id="your_app_id", app_secret="your_app_secret")

# 创建 Agent 并注册工具
agent = IntelligentAssistantAgent(
    llm=llm,
    tools=[contact_tool, approval_tool],
    enable_tool_calling=True
)

# 初始化并使用
await agent.initialize()
result = await agent.execute({
    "message": "查询手机号为13800138000的用户",
    "session_id": "session_001"
})
```

### 使用所有工具

```python
from core.tools.feishu import (
    FeishuContactTool,
    FeishuApprovalTool,
    FeishuBitableTool,
    FeishuImTool,
)

app_id = "your_app_id"
app_secret = "your_app_secret"

tools = [
    FeishuContactTool(app_id=app_id, app_secret=app_secret),
    FeishuApprovalTool(app_id=app_id, app_secret=app_secret),
    FeishuBitableTool(app_id=app_id, app_secret=app_secret),
    FeishuImTool(app_id=app_id, app_secret=app_secret),
]

agent = IntelligentAssistantAgent(
    llm=llm,
    tools=tools,
    enable_tool_calling=True
)
```

## 与 MCP 工具的区别

| 特性 | SDK 工具 | MCP 工具 |
|------|---------|---------|
| **实现方式** | 直接调用 Python SDK | 通过 MCP 协议调用 Node.js 服务 |
| **依赖** | 仅需 Python SDK | 需要 Node.js 和 npm |
| **启动速度** | 快速（无需启动进程） | 较慢（需要启动 MCP 服务端） |
| **功能范围** | SDK 支持的所有功能 | 仅限 MCP 服务端提供的功能 |
| **资源占用** | 较低 | 较高（需要运行 Node.js 进程） |
| **适用场景** | 常规飞书 API 调用 | 文档搜索等特定功能 |

## 工具调用格式

Agent 会在回复中使用以下格式调用工具：

```markdown
```tool_call
{
  "tool": "feishu_contact",
  "parameters": {
    "action": "get_user_by_mobiles",
    "mobiles": ["13800138000"]
  }
}
```
```

## 错误处理

所有工具都会返回统一的格式：

```python
{
    "success": True/False,
    "action": "操作类型",
    "data": {...},  # 成功时返回数据
    "error": "错误信息"  # 失败时返回错误
}
```

## 注意事项

1. **认证信息**：所有工具都需要 `app_id` 和 `app_secret`
2. **Token 管理**：SDK 会自动管理 token 的获取和缓存
3. **异步执行**：所有工具方法都是异步的
4. **错误处理**：工具执行失败不会导致 Agent 崩溃，错误信息会返回给 LLM

## 完整示例

完整示例请参考：`core/tools/feishu/example.py`

