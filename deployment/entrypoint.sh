#!/bin/sh
# =============================================================================
# 后端容器入口脚本
#   1) 等待 MySQL 端口可用
#   2) INIT_DB=true 时幂等建表 + 写入种子数据
#   3) 带参数时执行参数命令（可用于 docker compose run --rm backend python ...）
#      否则以单进程 uvicorn 启动应用
# =============================================================================
set -e

cd /app

DB_HOST="${MYSQL_HOST:-mysql}"
DB_PORT="${MYSQL_PORT:-3306}"

wait_for_db() {
    python - "$DB_HOST" "$DB_PORT" "${DB_WAIT_TIMEOUT:-120}" <<'PY'
import socket
import sys
import time

host, port, timeout = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
deadline = time.time() + timeout
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"[entrypoint] MySQL 已可连接：{host}:{port}", flush=True)
            raise SystemExit(0)
    except OSError:
        print(f"[entrypoint] 等待 MySQL {host}:{port} ...", flush=True)
        time.sleep(3)
print(f"[entrypoint] 等待 MySQL 超时（{timeout}s）：{host}:{port}", flush=True)
raise SystemExit(1)
PY
}

if [ "${WAIT_FOR_DB:-true}" = "true" ]; then
    wait_for_db
fi

if [ "${INIT_DB:-false}" = "true" ]; then
    echo "[entrypoint] 检查 / 创建数据库表结构 ..."
    python deployment/init_db.py
fi

# 传入自定义命令时优先执行（例如初始化管理员账号）
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "[entrypoint] 启动 uvicorn：port=${SERVER_PORT:-5005} workers=${WEB_CONCURRENCY:-1}"
exec uvicorn app:create_app --factory \
    --host 0.0.0.0 \
    --port "${SERVER_PORT:-5005}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --timeout-keep-alive 75
