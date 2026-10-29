FROM python:3.11.11

# 设置上海时区
ENV TZ=Asia/Shanghai

# 切换工作目录
WORKDIR /home/project/sjy-multi-agent

COPY pip.conf ./pip.conf

# 更换 apt 源并移除 buster-backports 源
RUN echo "deb http://mirrors.aliyun.com/debian/ buster main non-free contrib" > /etc/apt/sources.list \
    && echo "deb http://mirrors.aliyun.com/debian/ buster-updates main non-free contrib" >> /etc/apt/sources.list \
    && echo "deb http://mirrors.aliyun.com/debian-security/ buster/updates main non-free contrib" >> /etc/apt/sources.list \
    && echo "deb-src http://mirrors.aliyun.com/debian/ buster main non-free contrib" >> /etc/apt/sources.list \
    && echo "deb-src http://mirrors.aliyun.com/debian/ buster-updates main non-free contrib" >> /etc/apt/sources.list \
    && echo "deb-src http://mirrors.aliyun.com/debian-security/ buster/updates main non-free contrib" >> /etc/apt/sources.list

# 更新 apt 并安装软件包
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 更换 pip 源
RUN mkdir ~/.pip && \
    echo "[global]\nindex-url = https://mirrors.aliyun.com/pypi/simple/\ntrusted-host = mirrors.aliyun.com" > ~/.pip/pip.conf

# 拷贝项目文件到容器
COPY . .

# 安装 Poetry
RUN pip install poetry==1.6.0

# 将 Poetry 添加到 PATH
ENV PATH="/root/.local/bin:$PATH"

# 安装 Python 库
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes
RUN pip install --no-cache-dir --upgrade -r requirements.txt --trusted-host pypi.tuna.tsinghua.edu.cn

# 挂载主机目录到容器
VOLUME /home/project/sjy-multi-agent:/home/project/sjy-multi-agent


# 添加权限
RUN chmod +x /home/project/sjy-multi-agent/main.py

EXPOSE 8005
