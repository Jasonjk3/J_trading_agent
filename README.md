# SJY Multi-Agent

基于 **FastAPI + Python** 的多智能体应用后端，提供对话助手、任务执行、模型管理和工具调用能力，并围绕数字资产交易实现资讯采集、技术分析、策略决策、历史回测及交易执行接口。

项目适合用于开发多 Agent 业务应用、研究规则与大模型交易策略。仓库同时包含后端代码和 `agent_web/` 前端工程；前端安装与运行方式见 `agent_web/README.md`。

> 本文根据当前工作区代码编写，包含尚未提交的功能实现。代码中存在交易执行能力，但本文未验证交易所联调或实盘运行结果。

## 主要功能

- **多智能体框架**：任务式、对话式、服务型 Agent；注册中心、执行器、任务队列、会话与记忆管理；普通推理、CoT、ReAct 和协调 Agent。
- **业务助手与工具**：智能助手、飞书助手、竞品分析、代码审查、技术分析等 Agent，以及飞书、Text2SQL 等工具封装。
- **模型与提示词管理**：OpenAI、DeepSeek 及 OpenAI 兼容协议适配，模型配置、模型对比、提示词模板、调用量与费用监控。
- **行情与分析**：OKX 行情接入、历史 K 线缓存和补数、技术指标计算、分析报告持久化、消息面采集与查询。
- **策略决策**：支持持续状态的 AI 交易员和规则策略；AI 交易员维护市场观点、交易计划、订单意图与下一复核条件。
- **历史回测**：虚拟账户、仓位与风控、模拟交易、决策记录、净值曲线、任务进度和结果持久化。
- **交易管理**：交易所账户绑定、持仓、手工交易、交易 Agent 配置及启停、后台交易调度与执行。
- **账户权限**：用户登录、JWT 认证、管理员与普通用户管理。

## 核心工作流程

### 通用 Agent 应用

请求进入 FastAPI 后，由业务服务调用注册中心和执行器，将任务交给对应 Agent。Agent 按需使用模型、工具、会话历史及记忆，再将结果返回并持久化。

核心抽象位于 `core/agent_base/`，具体业务 Agent 位于 `agent_applications/`。API、业务编排和数据访问分别位于 `app/v1/api/`、`services/`、`crud/`。

### 交易研究与回测

```text
创建回测任务
  → BacktestRunner 准备配置与历史 K 线
  → BacktestEngine 按时间推进市场快照
  → 按 decisionMode 构造决策输入
      trader：行情事实 + 可选资讯 + 账户、持仓与硬风险策略
      rule：K 线指标 + 市场状态 + 规则配置
  → TraderOrchestrator 恢复上一轮 TraderState
  → TraderAgent 输出 TraderTurn（观点、计划、订单意图、下一复核）
  → 持久化工作记忆与只追加审计事件
  → RiskKernel 只校验账户安全与订单合法性
  → 回测引擎模拟执行并更新虚拟账户
  → 保存决策、交易记录、净值与统计结果
```

交易员模式由 `trading_analysis_context_service` 提供结构化事实与可选资讯，`TraderAgent` 自主形成观点和交易计划；技术评分、RR、信号冲突和冷却期不再作为代码二次否决。所有订单在回测和实盘执行前都必须经过确定性的 `RiskKernel`。规则模式由 `decision/` 中的上下文构建器和规则引擎处理，不依赖模型生成交易决策。

`traderConfig.executionMode` 默认是 `shadow`：观点、计划和订单意图会被记录，但不会提交订单。只有显式改成 `live` 后，首个订单意图才会进入当前执行链路；其余意图在阶段 3 的多订单生命周期接入前只做审计记录。实盘工作记忆保存在 `trader_states`，结构化回合与事件分别保存在 `trader_turns`、`trader_events`。

策略字段 `decisionMode` 仅支持 `trader`、`rule`，默认是 `trader`。旧 `llm` 模式与 `useLLM` 字段已经废弃；显式提交 `decisionMode=llm` 会被拒绝，以避免旧策略静默运行。

规则引擎包含市场状态识别、突破、趋势跟随、布林带区间、RSI、成交量确认、移动止损和固定比例止损；预设包括 `balanced_auto`、`trend_rider`、`range_scalper`、`conservative`。

### 后台交易执行

`live_trading_scheduler.py` 为运行中的交易 Agent 周期性构造行情和分析上下文，调用决策 Agent，再交给 `live_trading_executor.py` 执行。应用启动时通过环境变量控制是否启用，默认关闭。手工交易有单独的 `/v1/manual-trading` 接口。

历史文档中“尚未接入实盘调度”和“只有 LLM 决策”的描述已不完全适用于当前代码，应结合当前实现阅读。

## 目录结构

```text
sjy-multi-agent/
├── main.py                  # Uvicorn 启动入口
├── app/                     # FastAPI 应用
│   ├── public/              # 应用工厂、初始化、依赖与中间件
│   └── v1/                  # API、Schema、Service、CRUD
├── agent_applications/      # 任务式、对话式、服务型业务 Agent
├── core/                    # Agent 基类、执行器、模型、工具与基础设施
├── decision/                # 规则决策引擎、参数及上下文构建
├── backtest/                # 回测调度、模拟引擎、账户、风控与 K 线缓存
├── models/inner_models/     # SQLAlchemy 数据模型
├── lib/                     # OKX、Dify 等外部服务封装
├── consumers/               # 消息消费与处理管道
├── schedules/               # 定时任务相关代码
├── configs/                 # 环境配置
├── migrations/              # 数据库初始化与增量 SQL
├── scripts/                 # 管理员初始化、验证脚本和补充 SQL
├── deployment/              # 历史 Docker/Compose 配置
├── doc/                     # 架构、开发与业务设计文档
└── requirements.txt         # Python 依赖版本
```

## 本地运行

### 1. 准备环境

建议使用 Python 3.11（仓库 Dockerfile 使用 3.11.11），并准备支持 JSON 字段的 MySQL 实例。后端使用 SQLAlchemy 异步会话和 `aiomysql` 驱动。

以下命令在项目根目录、PowerShell 中执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

模型调用需要对应服务的凭据与网络连接；行情与交易功能需要访问 OKX。Redis、Kafka 相关能力按所启用的管道或集成配置，不是默认 HTTP 服务的统一前置条件。

### 2. 配置环境变量

在项目根目录创建或编辑 `.env`。以下仅为配置示例，请替换占位值，并保留已有环境中需要的配置：

```dotenv
ENVIRONMENT=dev
SECRET_KEY=replace-with-a-long-random-secret
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USERNAME=sjy_app
MYSQL_PASSWORD=replace-with-your-database-password
MYSQL_DB=sjy_multi_agent

# 按 Agent 所用模型配置
OPENAI_API_KEY=replace-with-your-api-key
# DEEPSEEK_API_KEY=replace-with-your-api-key
# LLM_PROXY=http://127.0.0.1:7890

# 当前启动流程会注册飞书助手
FEISHU_APP_ID=replace-with-your-feishu-app-id
FEISHU_APP_SECRET=replace-with-your-feishu-app-secret
# DB_URL_XITING_USER_DATA=your-business-database-url

ENABLE_PIPELINE=false
ENABLE_NEWS_INTELLIGENCE_WORKER=false
ENABLE_LIVE_TRADING_SCHEDULER=false
TRADING_SANDBOX_MODE=true
```

`SECRET_KEY` 是必填配置。当前 `.env` 加载使用 `override=True`，同名配置可能覆盖进程中已设置的环境变量。

默认启动流程会注册飞书助手和智能助手，不能仅通过关闭交易功能来跳过这些 Agent 的初始化。请为使用的模型与工具提供配置；注册失败时查看启动日志。

可选配置：

- 消息面采集：`ENABLE_NEWS_INTELLIGENCE_WORKER` 代码默认值为 `true`；上面的本地示例显式关闭。`NEWS_INTELLIGENCE_WORKER_INTERVAL` 默认为 60 秒，仅处理运行中的采集任务。
- 后台交易：`ENABLE_LIVE_TRADING_SCHEDULER` 默认 `false`，`TRADING_SANDBOX_MODE` 默认 `true`。
- OKX 行情服务：支持 `OKX_API_KEY`、`OKX_SECRET_KEY`、`OKX_PASSPHRASE`、`OKX_PROXY`、`OKX_IS_SANDBOX`。其中 `OKX_IS_SANDBOX` 默认 `false`，与后台调度器的沙盒开关是不同配置；交易账户还需通过账户管理接口配置。

### 3. 初始化数据库

先在 MySQL 中创建数据库，并为应用用户授予对应权限：

```sql
CREATE DATABASE sjy_multi_agent
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

应用启动不会自动建表。对于全新的空库，可以将下面代码保存为本地临时脚本 `init_db_local.py`，在项目根目录运行 `python init_db_local.py`，按当前 ORM 模型创建表：

```python
import asyncio
import importlib
import pkgutil

import models.inner_models as model_package
from models.inner_models.base import Base
from configs.config import app_config
from core.infrastructure.database.async_database import AsyncDatabase


async def main():
    for module in pkgutil.iter_modules(model_package.__path__):
        importlib.import_module(f"models.inner_models.{module.name}")
    db = AsyncDatabase(app_config)
    try:
        async with db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await db.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

该方式只创建缺失表，不升级已有字段，也不填充模型价格等业务配置。已有数据库需核对 `migrations/`、`scripts/` 及 `scripts/sql/` 中的 SQL，按实际缺失项执行。交易员模式至少需要依次执行 `013_migrate_llm_mode_to_trader.sql` 与 `014_create_trader_state_tables.sql`。部分早期迁移包含 `DROP TABLE`，不能当作可重复运行的升级命令直接应用到有数据的数据库。

### 4. 创建管理员

```powershell
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "replace-with-a-strong-password"
python scripts/init_admin_user.py
```

若 `.env` 中也设置了 `ADMIN_USERNAME` 或 `ADMIN_PASSWORD`，应同步调整。脚本检测到同名用户时会进入交互式密码更新流程。

### 5. 启动 API

```powershell
python main.py
```

当前入口固定监听 `0.0.0.0:5005`：

- Swagger UI：<http://127.0.0.1:5005/docs>
- ReDoc：<http://127.0.0.1:5005/redoc>
- OpenAPI：<http://127.0.0.1:5005/openapi.json>

`SERVER_HOST`、`SERVER_PORT` 虽然存在于配置类中，但 `main.py` 未使用它们。需要指定地址和端口时可运行：

```powershell
python -m uvicorn app:create_app --factory --host 127.0.0.1 --port 5005
```

后台采集和交易调度在应用进程内启动，初次运行建议保持单 worker，避免多个进程重复执行后台任务。

## API 使用入口

实际业务路由前缀为 **`/v1`**。

- 用户与认证：`/v1/auth`、`/v1/users`。
- 对话与 Agent：`/v1/chat`、`/v1/agents`、`/v1/service-monitor`。
- 模型与提示词：`/v1/llm`、`/v1/model-management`、`/v1/model-compare`、`/v1/monitor`、`/v1/prompt-templates`。
- 行情与交易：`/v1/market`、`/v1/exchange-accounts`、`/v1/positions`、`/v1/manual-trading`、`/v1/analytics`。
- 策略研究：`/v1/trading-agents`、`/v1/backtest`、`/v1/technical-analysis`、`/v1/news-intelligence-agents`。

以上为模块前缀，具体方法、子路径与请求字段以 Swagger 为准。先通过 `POST /v1/auth/login` 登录，需认证的接口使用 `Authorization: Bearer <token>`。

建议首次使用顺序：登录 → 配置模型 → 查询行情或执行技术分析 → 创建交易 Agent 策略 → 创建短时间范围回测 → 查看决策、交易与净值结果。规则决策可先通过下面的冒烟脚本单独验证。

## 验证与开发

在项目根目录运行现有规则决策冒烟脚本：

```powershell
python -m scripts.smoke_rule_decision
```

该脚本构造合成 K 线，验证模式解析及规则引擎、决策 Agent 的基本行为。它不能替代完整回测、数据库或交易所联调。

`scripts/test_technical_analysis.py` 和 `scripts/test_news_intelligence_collect.py` 用于相关功能集成验证；运行前检查脚本参数和所需服务，可能涉及网络请求、模型费用或数据库写入。

扩展功能时：新增 Agent 继承 `core/agent_base/` 对应基类，并接入注册流程；新增工具通过 `core/tools/tool_factory.py` 接入；新增接口按 API → Service → CRUD/Model 分层；新增规则在 `decision/` 中实现并接入规则配置。

## 当前运行注意事项

- `deployment/` 是需整理的历史配置：Compose 引用 `docker/Dockerfile`，实际文件位于 `deployment/Dockerfile`；构建还引用当前仓库未提供的 `pip.conf` 和 Poetry 项目配置，端口也与 `main.py` 不一致。目前优先按上面的本地方式运行。
- 部分源码存在集成服务默认凭据，部署前应替换为自己的环境配置；不要依赖代码中的默认值。
- 当前 CORS 允许所有来源。对外部署需按实际前端域名调整，并检查各路由的认证依赖。
- 回测属于历史数据模拟；启用真实交易前需要独立验证账户环境、执行逻辑与风控。

## 相关文档

- [Agent 开发指南](doc/agent_development_guide.md)
- [项目结构概览（部分目录为历史描述）](doc/project_structure_overview.md)
- [交易链路说明（需结合当前规则与调度代码）](doc/current_trading_chain.md)
- [规则决策模式设计](doc/rule_based_decision_mode_design.md)
- [消息面采集 Agent 设计](doc/financial_news_intelligence_service_agent_design.md)
- [回测优化计划](doc/BACKTEST_OPTIMIZATION_PLAN.md)
- [OKX 封装说明](lib/okx/README.md)
