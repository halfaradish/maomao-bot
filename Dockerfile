# 阶段 1: 基础系统层
FROM python:3.10-slim AS base
EXPOSE 6090 6379

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 换源 + 安装系统依赖 (这些很少变动)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y \
        pkg-config \
        default-libmysqlclient-dev \
        build-essential \
        libpangocairo-1.0-0 \
        libcairo2-dev \
        libpango1.0-dev \
        libgomp1 \
        libjsoncpp-dev \
        fonts-wqy-microhei \
        fonts-wqy-zenhei \
        fonts-arphic-ukai \
        fonts-arphic-uming \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 阶段 2: Python 环境层
FROM base AS python-env

# 安装 pipx (Python 工具管理)
RUN python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    python -m pip install --user pipx -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    python -m pipx ensurepath

ENV PATH="/root/.local/bin:${PATH}"

# 阶段 3: 依赖安装层
FROM python-env AS deps

WORKDIR /app

# 单独复制依赖文件，充分利用缓存
COPY requirements.txt .

# 安装 Python 依赖 + Playwright (这是最耗时的步骤，要保护好缓存)
RUN python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    python -m pip install nb-cli -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    python -m playwright install chromium --with-deps && \
    rm -rf /root/.cache/pip /tmp/*

# 阶段 4: 代码层
FROM deps AS final

ENV DJANGO_SETTINGS_MODULE="django_project.settings"

# 复制应用代码 (这一层会频繁变动)
COPY . .

# 编译 C++ 插件 (依赖代码，所以放在 COPY 之后)
RUN g++ -fPIC -shared \
    src/plugins/sub_records/table_gen.cpp \
    -o src/plugins/sub_records/table_gen.so \
    $(pkg-config --cflags --libs cairo pango pangocairo jsoncpp) \
    -O3

CMD ["nb", "run"]