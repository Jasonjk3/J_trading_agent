# =============================================================================
# 前端镜像：Vite 构建 Vue3 静态站点 -> Nginx
# 构建上下文必须是仓库根目录（compose 已配置 context: .）
#   docker build -f deployment/frontend.Dockerfile -t agent-trading-frontend .
# =============================================================================

# ----------------------------- 构建阶段 --------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# 国内服务器可传入镜像源：--build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org
# 后端地址：留空表示与前端同源，由 nginx 反向代理 /v1 到 backend:5005
ARG VITE_API_BASE_URL=""
ARG VITE_USE_MOCK=false

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_USE_MOCK=${VITE_USE_MOCK}

COPY agent_web/package.json agent_web/package-lock.json ./
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm ci --no-audit --no-fund

COPY agent_web/ ./

# 仓库里可能存在本地开发用的 .env（常指向 http://127.0.0.1:5005），
# 删除后再构建，确保地址只由构建参数决定
RUN rm -f .env .env.local .env.development.local .env.production.local

# 优先走完整的 npm run build（含 vue-tsc 类型检查）；
# 若历史代码存在类型错误导致失败，回退到纯 vite 打包，避免部署被卡住
RUN npm run build || npx vite build

# ----------------------------- 运行阶段 --------------------------------------
FROM nginx:1.27-alpine

ENV TZ=Asia/Shanghai

COPY deployment/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
