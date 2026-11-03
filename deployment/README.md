# Linux 服务器 Docker Compose 部署指南

本文档面向把本项目（FastAPI 后端 + Vue3 前端）部署到一台 Linux 服务器，
使用仓库根目录的 `docker-compose.yml` 一次性拉起 MySQL、后端、前端（Nginx）。

---

## 1. 交付文件清单

| 文件 | 作用 |
| --- | --- |
| `deploy.sh` | **一键部署脚本**：生成配置 / 构建 / 启动 / 等健康检查 / 建管理员 / 备份 |
| `deployment/pack.ps1` | 本地（Windows）一键打包成 tar.gz，供无法访问 GitHub 时上传服务器 |
| `docker-compose.yml` | 编排：mysql / redis / backend / frontend |
| `deployment/backend.Dockerfile` | 后端镜像（Python 3.11 + Uvicorn） |
| `deployment/frontend.Dockerfile` | 前端镜像（Node 构建 → Nginx 托管） |
| `deployment/nginx.conf` | 前端站点配置：SPA 回退、静态缓存、`/v1` 反向代理、SSE 支持 |
| `deployment/entrypoint.sh` | 后端启动脚本：等数据库 → 可选建表 → 启动 uvicorn |
| `deployment/init_db.py` | 幂等建表 + 写入种子数据（模型价格、标签等） |
| `deployment/.env.production.example` | 生产环境变量模板（复制为 `.env.production`） |
| `.dockerignore` | 排除 `.env`、`node_modules`、`__pycache__` 等，避免密钥进镜像 |

> 旧的 `deployment/Dockerfile`、`deployment/.env` 是历史配置（引用了不存在的
> `pip.conf` / Poetry 配置，端口也不一致），**不要使用**，保留仅作参考。
> 另外 `deployment/.env` 里存在历史项目的真实数据库口令与 API Key，
> 若这份代码进过仓库或共享过，请立即轮换这些密钥。

---

## 1.1 最快路径（3 条命令）

**情况 A：服务器能访问 GitHub**

```bash
git clone <仓库地址> /opt/agent_trading && cd /opt/agent_trading
bash deploy.sh init     # 自动生成 .env.production 并填充随机密钥，提示还需填哪些
vi deployment/.env.production   # 只填 LLM / 飞书 / OKX 的 key（约 1 分钟）
bash deploy.sh          # 构建 + 启动 + 等健康 + 建管理员，一条命令到底
```

**情况 B：服务器连不上 GitHub（就像你推送时的情况）——不用 git，直接传包**

```powershell
# 本地 Windows，一条命令打包（自动排除 .git / node_modules / dist / .env 等）
.\deployment\pack.ps1
# 按屏幕提示执行 scp，例如：
scp "...\agent-trading-20261102-1541.tar.gz" user@服务器IP:/opt/
```

```bash
# 服务器上，两条命令
mkdir -p /opt/agent_trading && tar -xzf /opt/agent-trading-*.tar.gz -C /opt/agent_trading
cd /opt/agent_trading && bash deploy.sh init && vi deployment/.env.production && bash deploy.sh
```

`deploy.sh` 支持：`init | up(默认) | update | admin | ps | logs | backup | down | config`，
没有参数时等价于 `up`（完整构建+启动）。

**提速提示**：国内服务器先在 `.env.production` 里把 `PIP_INDEX_URL` 改成
`https://mirrors.aliyun.com/pypi/simple/`、`NPM_REGISTRY` 改成 `https://registry.npmmirror.com`，
后端镜像构建时间通常能从 10 分钟级降到 2-4 分钟。

---

## 2. 部署架构

```
                 Internet
                    │  :80（建议再套一层 HTTPS）
        ┌───────────▼────────────┐
        │ frontend (nginx:80)    │  静态站点 + /v1 反向代理
        └───────────┬────────────┘
                    │ http://backend:5005
        ┌───────────▼────────────┐
        │ backend  (uvicorn)     │  单进程：API + 后台任务
        └───────┬────────┬───────┘
                │        │
     ┌──────────▼──┐  ┌──▼─────────┐
     │ mysql:3306  │  │ redis:6379 │  （redis 仅消息管道用，可选）
     └─────────────┘  └────────────┘
```

要点：

- 前端与后端**同源**：浏览器只访问 `http://服务器IP/`，所有接口走 `/v1/**` 由 Nginx 转发，
  因此不存在跨域问题（后端 CORS 当前是 `allow_origins=["*"]`，与 `credentials=true` 组合
  在浏览器里其实是不合法的，同源部署可以完全绕开这个坑）。
- 后端必须是**单进程**（`WEB_CONCURRENCY=1`）：消息面采集、数据监控、交易调度等
  后台任务都在进程内启动，多 worker 会重复执行、重复下单。
- MySQL 数据保存在命名卷 `agent-trading-mysql-data` 中，`docker compose down` 不会丢数据，
  **只有 `down -v` 才会删除数据卷**。

---

## 3. 服务器前置要求

| 项目 | 要求 |
| --- | --- |
| 系统 | 任意主流发行版（Ubuntu 20.04+ / Debian 11+ / CentOS Stream 8+） |
| Docker | 24+，含 Compose v2（`docker compose version` 可用） |
| 配置 | 2 核 4G 起步；`requirements.txt` 含 xgboost / prophet / matplotlib / scikit-learn，镜像构建内存峰值约 1.5G |
| 磁盘 | 建议 ≥ 20G（后端镜像约 1.5–2.5G） |
| 网络 | 能访问 PyPI / npm（或使用镜像源），运行期需要访问大模型 API 与 OKX |

安装 Docker（以官方脚本为例，国内可用镜像站）：

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
docker compose version
```

防火墙只放行需要的端口（示例，按实际调整）：

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 4. 上传代码

方式一（推荐，服务器有 Git 权限）：

```bash
cd /opt
sudo mkdir -p agent_trading && sudo chown "$USER":"$USER" agent_trading
git clone <你的仓库地址> agent_trading
cd agent_trading
```

方式二（本地打包上传）：

```bash
# 本地 PowerShell
scp -r D:\project\agent_trading user@服务器IP:/opt/agent_trading
```

> 上传时不要带 `agent_web/node_modules`、`.venv`、`__pycache__`（`.dockerignore` 已做排除，
> 但仍会影响上传速度）。

---

## 5. 准备环境配置文件

```bash
cd /opt/agent_trading
cp deployment/.env.production.example deployment/.env.production
chmod 600 deployment/.env.production
vi deployment/.env.production
```

必须修改的项：

| 变量 | 说明 |
| --- | --- |
| `SECRET_KEY` | JWT 签名 + 交易所密钥加密都用它。**生成一次就固定下来**，后期修改会导致所有 Token 失效、已加密的交易所 API Key 无法解密 |
| `MYSQL_USERNAME` / `MYSQL_PASSWORD` / `MYSQL_DB` | 应用连接 MySQL 的账号；容器初始化时会用这三个值创建库和用户 |
| `MYSQL_ROOT_PASSWORD` | MySQL root 密码（仅容器初始化使用） |
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | 启动时会实例化智能助手 Agent，key 不可用可能导致应用启动失败 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 启动流程会注册飞书助手 Agent，注册失败会直接抛出异常中断启动 |
| `OKX_*` | 行情与交易功能需要；不配置则相关接口报错 |
| `ENABLE_LIVE_TRADING_SCHEDULER` | 首次部署务必保持 `false` |
| `TRADING_SANDBOX_MODE` | 首次部署保持 `true` |
| `WEB_PORT` | 若服务器 80 端口已被占用，改成 `8080` 等 |
| `PIP_INDEX_URL` / `NPM_REGISTRY` | 国内服务器建议改成阿里云 PyPI 与 npmmirror，否则构建可能很慢或失败 |

生成随机密钥的两种方式：

```bash
openssl rand -base64 48
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

关键注意事项：

1. **`MYSQL_HOST` 必须写成 `mysql`**（compose 服务名）。应用用 `python-dotenv` 以
   `override=True` 加载容器内 `/app/.env`，该文件会覆盖 compose `environment` 里设置的同名变量，
   所以数据库地址只能在这份文件里改，写在 compose 里无效。
2. 该文件同时被 compose 用于 `${...}` 变量替换，因此 `WEB_PORT`、`BACKEND_PORT`、
   `PIP_INDEX_URL`、`NPM_REGISTRY`、`VITE_API_BASE_URL` 也写在这里。
3. 文件里**不要写行内注释**（`KEY=value  # 说明`），compose 的 env_file 解析器会把注释当成值的一部分。
4. `MYSQL_PASSWORD` 会被直接拼进 SQLAlchemy 连接串（`mysql+aiomysql://user:pass@host`），
   请避开 `@ : / ? # %` 等字符，否则需要 URL 编码。

可选：先做一次语法与变量校验（不会启动容器）：

```bash
docker compose --env-file deployment/.env.production config >/dev/null && echo OK
```

---

## 6. 构建并启动

```bash
cd /opt/agent_trading
docker compose --env-file deployment/.env.production up -d --build
```

由于每次都要带 `--env-file`，建议加个别名：

```bash
echo "alias dc='docker compose --env-file deployment/.env.production'" >> ~/.bashrc
source ~/.bashrc
# 之后可直接：dc up -d --build / dc ps / dc logs -f backend
```

首次启动流程：

1. 构建后端镜像（安装 Python 依赖，5–15 分钟，视网速而定）；
2. 构建前端镜像（`npm ci` + `vite build`）；
3. 启动 MySQL 并等待健康检查通过；
4. 后端 `/app/deployment/entrypoint.sh` 等待 3306 端口 → 执行 `init_db.py` 建表与种子数据；
5. 启动 uvicorn（0.0.0.0:5005）；
6. 前端 Nginx 启动，监听宿主机 `${WEB_PORT}`。

查看进度：

```bash
dc ps
dc logs -f backend
```

> 如果前端构建阶段因历史代码的类型错误失败，Dockerfile 已内置回退：
> `npm run build || npx vite build`（跳过 `vue-tsc` 类型检查，仅做打包）。

---

## 7. 初始化管理员账号

应用不会自动创建管理员，需要在后端容器里执行一次脚本（脚本是幂等的，已存在会提示）：

```bash
cd /opt/agent_trading
docker compose --env-file deployment/.env.production exec backend \
  python scripts/init_admin_user.py
```

脚本读取 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 环境变量，未设置时交互式输入，默认 `admin / admin123`。
非交互式创建示例：

```bash
docker compose --env-file deployment/.env.production exec \
  -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD='一个强密码' \
  backend python scripts/init_admin_user.py
```

也可以给 `entrypoint.sh` 传任意命令（entrypoint 会原样 `exec`）：

```bash
docker compose --env-file deployment/.env.production run --rm backend python deployment/init_db.py
```

---

## 8. 验证

```bash
# 1) 容器状态：backend 应为 healthy
dc ps

# 2) 后端直连（仅在服务器本机可用，端口绑定 127.0.0.1）
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5005/openapi.json   # 期望 200

# 3) 前端站点
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/                    # 期望 200
curl -s http://127.0.0.1/healthz                                              # 期望 ok

# 4) 经 Nginx 访问后端接口（未登录应返回业务错误而非 502）
curl -s http://127.0.0.1/v1/auth/me

# 5) 浏览器验证
#    打开 http://服务器IP/ → 登录页 → 用第 7 步的账号登录
#    → 智能助手页面发一条消息，确认流式输出正常（验证 SSE 未被缓冲）
```

检查清单：

- [ ] `dc ps` 四个容器均为 `running`，`backend`/`mysql` 为 `healthy`
- [ ] `dc logs backend | grep 服务初始化完成`
- [ ] 页面能打开、能登录、列表页有数据（说明 `/v1` 反代正常）
- [ ] 智能助手可以流式输出（说明 Nginx SSE 配置生效）
- [ ] 服务器时间正确：`docker compose exec backend date` 显示东八区

---

## 9. 只部署后端（不用 Docker / 或只跑 API）

### 9.1 直接用 Docker 只跑后端

```bash
docker build -f deployment/backend.Dockerfile -t agent-trading-backend .
docker run -d --name agent-backend --restart unless-stopped \
  --env-file deployment/.env.production \
  -v "$PWD/deployment/.env.production:/app/.env:ro" \
  -p 127.0.0.1:5005:5005 \
  agent-trading-backend
```

### 9.2 裸机 Python 方式（本机 systemd 守护）

```bash
cd /opt/agent_trading
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 首次建表
python deployment/init_db.py
# 创建管理员
ADMIN_USERNAME=admin ADMIN_PASSWORD='强密码' python scripts/init_admin_user.py

# 前台试跑
python -m uvicorn app:create_app --factory --host 0.0.0.0 --port 5005 --workers 1
```

`main.py` 里端口是写死的 `5005`，用 uvicorn 命令则可以自行指定。
生产建议用 systemd 托管：

```ini
# /etc/systemd/system/agent-backend.service
[Unit]
Description=agent_trading backend
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/agent_trading
EnvironmentFile=/opt/agent_trading/deployment/.env.production
ExecStart=/opt/agent_trading/.venv/bin/python -m uvicorn app:create_app --factory \
    --host 0.0.0.0 --port 5005 --workers 1 --proxy-headers --forwarded-allow-ips='*'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agent-backend
sudo journalctl -u agent-backend -f
```

> 注意：`ENVIRONMENT=pro` 时日志是 JSON 到 stderr，systemd/journald 会原样收集。

---

## 10. 只部署前端（静态站点）

前端是纯静态产物，服务器**不需要 Node**，可以在任意机器构建后上传，也可以让 Docker 构建。

### 10.1 用 Docker（推荐，和全栈部署一致）

```bash
docker build -f deployment/frontend.Dockerfile -t agent-trading-frontend .
docker run -d --name agent-frontend --restart unless-stopped \
  -p 80:80 agent-trading-frontend
```

### 10.2 本地构建后上传 dist

```bash
cd agent_web
npm ci
# 同源部署（Nginx 反代 /v1）：留空
VITE_API_BASE_URL= npm run build
# 前后端分离部署：填后端地址
# VITE_API_BASE_URL=https://api.example.com npm run build

scp -r dist/* user@服务器IP:/var/www/agent_trading/
```

服务器上的 Nginx 站点配置可直接照抄 `deployment/nginx.conf`，
把 `set $backend "http://backend:5005";` 改成实际后端地址，例如
`set $backend "http://127.0.0.1:5005";`，并删除 `resolver 127.0.0.11` 这一行
（那是 Docker 内置 DNS）。如果后端在其他服务器，改成
`set $backend "https://api.example.com";`。

**分离部署的额外要求**：

1. 浏览器会跨域访问后端，需确认后端 CORS 策略。当前代码是
   `allow_origins=["*"] + allow_credentials=True`，不符合 CORS 规范，
   部分浏览器会拦截。稳妥做法是把前端与后端放在同一域名下（推荐），
   或修改 `app/public/factory.py` 中的 CORS 配置，显式列出前端域名并去掉
   `allow_credentials`（本项目用 `Authorization: Bearer`，不依赖 Cookie）。
2. 后端也要能对外访问（不能只绑 `127.0.0.1`），并建议上 HTTPS，
   否则浏览器对混合内容（HTTPS 页面调 HTTP 接口）会直接拦截。

---

## 11. 日常运维

```bash
cd /opt/agent_trading

# 状态 / 资源占用
dc ps
docker stats --no-stream

# 日志（后端日志走 stderr，被 docker 收集并轮转：50MB × 5）
dc logs -f --tail=200 backend
dc logs -f --tail=100 frontend

# 重启单个服务（改完 .env.production 后必须重建/重启才生效）
dc restart backend
dc up -d --force-recreate backend

# 发版更新
git pull
dc up -d --build            # 只改了某个服务的代码时也可：dc up -d --build backend
dc image prune -f           # 清理旧镜像

# 进容器排查
dc exec backend bash
dc exec backend python -c "import app, sys; print('import ok')"
dc exec mysql mysql -u"$MYSQL_USERNAME" -p"$MYSQL_PASSWORD" "$MYSQL_DB" -e 'show tables;'
```

数据库备份与恢复（建议加进 crontab 每日执行）：

```bash
# 备份
docker compose --env-file deployment/.env.production exec -T mysql \
  sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines \
  --databases "$MYSQL_DATABASE"' | gzip > backup_$(date +%F).sql.gz

# 恢复
gunzip -c backup_2026-01-01.sql.gz | docker compose --env-file deployment/.env.production \
  exec -T mysql sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD"'
```

彻底清理（**会删除数据库数据**）：

```bash
dc down            # 停止并删除容器，数据卷保留
dc down -v         # 连数据卷一起删除，谨慎
```

---

## 12. 常见问题排查

| 现象 | 排查与处理 |
| --- | --- |
| `required variable MYSQL_ROOT_PASSWORD is missing` | 启动命令漏了 `--env-file deployment/.env.production`，或文件里没写该项 |
| 后端容器反复重启（`Restarting`） | `dc logs --tail=200 backend`。最常见原因：`SECRET_KEY` 未设置、`OPENAI_API_KEY` 不可用、飞书 App 凭据缺失导致 Agent 注册失败、数据库连接失败 |
| `Access denied for user` | `.env.production` 里的 `MYSQL_USERNAME/MYSQL_PASSWORD/MYSQL_DB` 与卷里已初始化的账号不一致。MySQL 只在**空数据目录**首次启动时创建账号；改配置后需 `dc down -v` 重建（会清空数据）或进库手动授权 |
| 页面 502 / `host not found in upstream` | backend 未启动或崩溃；`dc ps`、`dc logs backend`。nginx 用变量 + 内置 DNS 解析，不会因后端重建而卡死，但后端彻底挂掉时返回 502 |
| 页面能开但接口 404 | 确认访问的是 `/v1/...`；确认前端构建时 `VITE_API_BASE_URL` 为空（同源），否则会绕过 Nginx 直连后端地址 |
| 智能助手回复不流式、一次性出现 | Nginx 缓冲未关闭。`deployment/nginx.conf` 中 `/v1/` 已设 `proxy_buffering off`，若自行改过配置请确认；同时确认前置 CDN/负载均衡也未开缓冲 |
| 时间不对（差 8 小时） | 容器已设 `TZ=Asia/Shanghai`，MySQL 用 `--default-time-zone=+08:00`；若宿主机时间本身错误，先 `timedatectl set-timezone Asia/Shanghai` |
| 构建卡在 `pip install` / `npm ci` | 网络问题。改 `.env.production` 里的 `PIP_INDEX_URL`、`NPM_REGISTRY` 为国内镜像后重新 `up -d --build` |
| 构建时 OOM（`Killed`） | 依赖较重，加 swap 或换更大内存机器：`fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
| 前端构建报类型错误 | Dockerfile 已回退到 `npx vite build`；也可在本地先 `npm run build` 修好类型再部署 |
| 管理员登录 401/登录后立刻退出 | 确认 `SECRET_KEY` 在多次发版间没有变化；确认浏览器时间正常 |
| 需要 Swagger 调试 | 默认不对外暴露。`dc exec backend curl -s localhost:5005/docs` 或在 `nginx.conf` 里解开注释的 `/docs`、`/openapi.json` 段落 |
| 某些 Agent 工具报 `npx: not found` | 飞书 MCP 文档检索工具依赖 Node 的 `npx`，默认未装（按需才用）。如确需使用，在 `deployment/backend.Dockerfile` 中追加 `nodejs npm` 安装 |

---

## 13. 上线前的安全与风控建议

1. **密钥**：`deployment/.env.production` 权限 `600`；`deployment/.env` 里的历史密钥（阿里云 RDS、
   OpenAI/DeepSeek、Redis 口令）应视为已泄露并轮换。
2. **HTTPS**：在宿主机用 Nginx/Caddy/Cloudflare 终止 TLS 后转发到 80 端口，或直接在前面挂
   反向代理；交易类系统强烈建议全程 HTTPS。
3. **端口暴露**：只暴露 80/443。后端 5005 只绑 `127.0.0.1`，MySQL 3306 不映射到公网。
4. **交易开关**：`ENABLE_LIVE_TRADING_SCHEDULER=false`、`TRADING_SANDBOX_MODE=true` 起步，
   先用模拟盘/回测验证策略，再逐个打开；打开实盘前确认 OKX 账户、权限与风控配置。
5. **CORS**：当前是全放开，同源部署时影响有限；一旦前后端分域名，请先收紧
   `app/public/factory.py` 的 CORS 白名单。
6. **备份**：数据库与 `.env.production` 一起备份；`SECRET_KEY` 丢失等于交易所密钥需要重新录入。
7. **监控**：`docker compose` 的健康检查只是基础存活探测，建议再接入日志/告警（如飞书机器人）。
