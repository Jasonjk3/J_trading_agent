#!/usr/bin/env bash
# =============================================================================
# 一键部署脚本（MySQL + 后端 + 前端 一起）
#
#   bash deploy.sh init       # 1) 生成 deployment/.env.production 并自动填充随机密钥
#   bash deploy.sh            # 2) 构建镜像 + 启动全部服务 + 等健康检查 + 建管理员
#
#   bash deploy.sh update     # 更新代码后重新构建部署（并清理旧镜像）
#   bash deploy.sh admin      # 只创建/更新管理员账号
#   bash deploy.sh ps         # 查看容器状态
#   bash deploy.sh logs       # 跟踪后端日志
#   bash deploy.sh backup     # 备份数据库到 ./backups/
#   bash deploy.sh down       # 停止服务（保留数据卷）
#   bash deploy.sh config     # 只校验配置，不启动
#
# 依赖：docker + docker compose v2
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE="${ENV_FILE:-deployment/.env.production}"
ENV_TEMPLATE="deployment/.env.production.example"
BACKEND_CONTAINER="agent-trading-backend"

info()  { printf '\033[36m[deploy]\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[deploy]\033[0m %s\n' "$*"; }
fail()  { printf '\033[31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 环境检查 ---
if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
        DC=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        DC=(docker-compose)
    else
        fail "未找到 docker compose，请先安装 Docker Compose v2"
    fi
else
    fail "未找到 docker，请先安装：curl -fsSL https://get.docker.com | sh"
fi

compose() { "${DC[@]}" --env-file "$ENV_FILE" "$@"; }

read_env() {
    # 读取 .env.production 中某个键的值（同键取最后一条）
    local key="$1" default="${2:-}" value
    value="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d '\r' || true)"
    printf '%s' "${value:-$default}"
}

set_env() {
    # 写入或替换某个键（值由调用方保证不含 | 和换行）
    local key="$1" value="$2"
    if grep -qE "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
    fi
}

rand_str() {
    # 纯十六进制随机串：不含 @ : / ? # % 等会破坏连接串/URL 的字符
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 24
    else
        head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'
    fi
}

require_env() {
    if [ ! -f "$ENV_FILE" ]; then
        warn "未找到 $ENV_FILE"
        if [ -f "deployment/.env" ]; then
            warn "但检测到历史文件 deployment/.env：它是旧项目的配置（含真实密钥），不能用于本次部署"
        fi
        warn "请先执行：bash deploy.sh init   （自动生成并填充随机密钥）"
        exit 1
    fi
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    if grep -q '请替换' "$ENV_FILE"; then
        fail "$ENV_FILE 中还有未替换的占位值（搜索“请替换”），或先执行：bash deploy.sh init"
    fi
}

# --------------------------------------------------------------- 子命令 ------
cmd_init() {
    if [ ! -f "$ENV_FILE" ]; then
        [ -f "$ENV_TEMPLATE" ] || fail "缺少模板 $ENV_TEMPLATE"
        cp "$ENV_TEMPLATE" "$ENV_FILE"
        info "已从模板生成 $ENV_FILE"
    else
        info "复用已存在的 $ENV_FILE（只补空值/占位值）"
    fi
    chmod 600 "$ENV_FILE" 2>/dev/null || true

    local key current
    for key in SECRET_KEY MYSQL_PASSWORD MYSQL_ROOT_PASSWORD; do
        current="$(read_env "$key")"
        case "$current" in
            "" | *请替换*)
                set_env "$key" "$(rand_str)"
                info "已生成 $key"
                ;;
            *)
                info "$key 已存在，保持不变"
                ;;
        esac
    done

    # 数据库地址必须是 compose 服务名
    if [ "$(read_env MYSQL_HOST)" != "mysql" ]; then
        set_env MYSQL_HOST mysql
        info "MYSQL_HOST 已设为 mysql（容器内通过服务名连库）"
    fi

    echo
    info "配置就绪：$ENV_FILE"
    local missing=""
    for key in OPENAI_API_KEY DEEPSEEK_API_KEY FEISHU_APP_ID FEISHU_APP_SECRET; do
        if [ -z "$(read_env "$key")" ]; then
            missing="$missing $key"
        fi
    done
    if [ -n "$missing" ]; then
        warn "以下值为空，建议部署前填写（为空可能导致启动失败）："
        warn "  $missing"
        warn "  编辑：vi $ENV_FILE"
    fi
    warn "想自动创建管理员，可在该文件中补充 ADMIN_USERNAME 和 ADMIN_PASSWORD"
    echo
    info "下一步：bash deploy.sh"
}

cmd_config() {
    require_env
    info "校验 compose 配置与变量 ..."
    compose config >/dev/null
    info "配置正确"
}

cmd_up() {
    local prune="${1:-no}"
    require_env
    cmd_config

    info "配置文件：$ENV_FILE"
    info "pip 源：$(read_env PIP_INDEX_URL 默认)；npm 源：$(read_env NPM_REGISTRY 默认)"
    info "开始构建镜像并启动（后端依赖较重，首次约 5-15 分钟）..."
    compose up -d --build

    if [ "$prune" = "update" ]; then
        info "清理无用镜像 ..."
        docker image prune -f >/dev/null 2>&1 || true
    fi

    info "等待后端就绪（最多 180 秒）..."
    local i status
    for i in $(seq 1 36); do
        status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
            "$BACKEND_CONTAINER" 2>/dev/null || echo missing)"
        if [ "$status" = "healthy" ]; then
            info "后端就绪（healthy）"
            break
        fi
        if [ "$i" -eq 36 ]; then
            warn "后端 180 秒内未变 healthy（当前：$status）"
            warn "排查：bash deploy.sh logs"
        fi
        sleep 5
    done

    local admin_user admin_pass
    admin_user="$(read_env ADMIN_USERNAME)"
    admin_pass="$(read_env ADMIN_PASSWORD)"
    if [ -n "$admin_user" ] && [ -n "$admin_pass" ]; then
        info "初始化管理员：$admin_user"
        compose exec -T backend python scripts/init_admin_user.py </dev/null \
            || warn "管理员初始化未成功（可能已存在），可手动：bash deploy.sh admin"
    else
        warn "未配置 ADMIN_USERNAME / ADMIN_PASSWORD，跳过管理员创建"
        warn "配置后执行：bash deploy.sh admin"
    fi

    echo
    compose ps
    echo
    local web_port host_ip
    web_port="$(read_env WEB_PORT 80)"
    host_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
    info "部署完成"
    info "前端访问： http://${host_ip:-服务器IP}:${web_port}/"
    info "后端调试： http://127.0.0.1:$(read_env BACKEND_PORT 5005)/openapi.json （仅服务器本机）"
    info "查看日志： bash deploy.sh logs"
}

cmd_admin() {
    require_env
    local user pass
    user="$(read_env ADMIN_USERNAME)"
    pass="$(read_env ADMIN_PASSWORD)"
    if [ -z "$user" ] || [ -z "$pass" ]; then
        fail "请先在 $ENV_FILE 中设置 ADMIN_USERNAME 和 ADMIN_PASSWORD"
    fi
    info "创建/更新管理员：$user"
    compose exec -T backend python scripts/init_admin_user.py </dev/null
}

cmd_backup() {
    require_env
    mkdir -p backups
    local file="backups/mysql-$(date +%Y%m%d-%H%M%S).sql.gz"
    info "备份数据库 -> $file"
    compose exec -T mysql sh -c \
        'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --databases "$MYSQL_DATABASE"' \
        | gzip >"$file"
    info "完成：$(du -h "$file" | cut -f1)"
}

# --------------------------------------------------------------- 分派 --------
case "${1:-up}" in
    init)    cmd_init ;;
    up)      cmd_up ;;
    update)  cmd_up update ;;
    admin)   cmd_admin ;;
    ps)      require_env; compose ps ;;
    logs)    require_env; compose logs -f --tail=200 backend ;;
    down)    require_env; compose down ;;
    backup)  cmd_backup ;;
    config)  cmd_config ;;
    *)       sed -n '2,20p' "$0"; exit 1 ;;
esac
