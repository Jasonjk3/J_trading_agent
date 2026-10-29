#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
飞书 SDK 工具使用示例
展示如何将飞书 SDK 工具接入到智能助手 Agent 中
"""
import asyncio
from agent_applications.conversation_agents.intelligent_assistant_agent import IntelligentAssistantAgent
from core.tools.feishu import (
    FeishuContactTool,
    FeishuApprovalTool,
    FeishuBitableTool,
    FeishuImTool,
)
from core.llm.deepseek_llm import DeepSeekLLM  # 根据实际情况调整导入


async def main():
    """示例：使用飞书 SDK 工具的智能助手"""
    
    # 1. 创建 LLM 实例
    llm = DeepSeekLLM()  # 或其他 LLM 实现
    
    # 2. 创建飞书工具（需要配置 app_id 和 app_secret）
    app_id = "your_app_id"
    app_secret = "your_app_secret"
    
    # 创建各种飞书工具
    contact_tool = FeishuContactTool(app_id=app_id, app_secret=app_secret)
    approval_tool = FeishuApprovalTool(app_id=app_id, app_secret=app_secret)
    bitable_tool = FeishuBitableTool(app_id=app_id, app_secret=app_secret)
    im_tool = FeishuImTool(app_id=app_id, app_secret=app_secret)
    
    # 3. 创建智能助手 Agent，并注册工具
    agent = IntelligentAssistantAgent(
        agent_name="智能助手（带飞书功能）",
        llm=llm,
        tools=[contact_tool, approval_tool, bitable_tool, im_tool],  # 传入工具列表
        enable_tool_calling=True  # 启用工具调用
    )
    
    # 4. 初始化 Agent
    success = await agent.initialize()
    if not success:
        print("Agent 初始化失败")
        return
    
    try:
        # 5. 执行任务（用户提问）
        task = {
            "message": "帮我查询手机号为13800138000的用户信息",
            "session_id": "test_session_001"
        }
        
        result = await agent.execute(task)
        
        if result.get("success"):
            print("=" * 50)
            print("用户问题：", task["message"])
            print("=" * 50)
            print("助手回复：")
            print(result.get("response", ""))
            print("=" * 50)
        else:
            print("执行失败：", result.get("error"))
        
        # 6. 继续对话
        task2 = {
            "message": "查询审批实例ID为xxx的详情",
            "session_id": "test_session_001"
        }
        
        result2 = await agent.execute(task2)
        if result2.get("success"):
            print("\n" + "=" * 50)
            print("用户问题：", task2["message"])
            print("=" * 50)
            print("助手回复：")
            print(result2.get("response", ""))
            print("=" * 50)
        
    finally:
        # 7. 清理资源
        await agent.cleanup()


async def example_single_tool():
    """示例：只使用一个工具"""
    
    llm = DeepSeekLLM()
    
    # 只使用通讯录工具
    contact_tool = FeishuContactTool(
        app_id="your_app_id",
        app_secret="your_app_secret"
    )
    
    agent = IntelligentAssistantAgent(
        agent_name="飞书通讯录助手",
        llm=llm,
        tools=[contact_tool],
        enable_tool_calling=True
    )
    
    await agent.initialize()
    
    try:
        task = {
            "message": "查询部门列表",
            "session_id": "test_session_002"
        }
        
        result = await agent.execute(task)
        print("回复：", result.get("response", ""))
    finally:
        await agent.cleanup()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
    
    # 其他示例
    # asyncio.run(example_single_tool())

