# =============================================================================
# 后端镜像：Python 3.11 + FastAPI / Uvicorn
# 构建上下文必须是仓库根目录（compose 已配置 context: .）
#   docker build -f deployment/backend.Dockerfile -t agent-trading-backend .
# =============================================================================
FROM python:3.11-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8

WORKDIR /app

# build-essential：asyncmy / prophet 等包在没有预编译 wheel 时需要编译器
# libgomp1：xgboost、scikit-learn 的 OpenMP 运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libgomp1 \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo "$TZ" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 国内服务器可传入镜像源：
#   --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
#   --build-arg PIP_TRUSTED_HOST=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

# 先只拷贝依赖清单，最大化利用构建缓存
COPY requirements.txt ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r requirements.txt

# 再拷贝源码（.dockerignore 已排除 .env、node_modules、__pycache__ 等）
COPY . .

# Windows 上检出的脚本可能是 CRLF，sed 兜底避免 "#!/bin/sh: not found"
RUN sed -i 's/\r$//' deployment/entrypoint.sh \
    && chmod +x deployment/entrypoint.sh

EXPOSE 5005

ENTRYPOINT ["/bin/sh", "/app/deployment/entrypoint.sh"]
