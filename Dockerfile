# 阶段 0: 前端构建层
FROM node:20-alpine AS webui-builder
WORKDIR /webui
COPY webui/package.json webui/package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com
RUN npm ci --legacy-peer-deps
COPY webui/ ./
RUN npm run build

# 阶段 1: 基础系统层
FROM python:3.10-slim AS base
EXPOSE 6090 6379

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 换源 + 安装系统依赖 (这些很少变动)
# 源的选择有实测依据（2026-09-15 在部署服务器上测 trixie/main/binary-amd64/Packages.gz，13.3 MB）：
#   mirrors.ustc.edu.cn        13.4 MB/s（DNS 5ms，最慢一次 0.27s）
#   mirrors.huaweicloud.com    12.1 MB/s
#   mirrors.tuna.tsinghua.edu.cn 2.7 MB/s
#   mirrors.aliyun.com        327 KB/s（25s 都没下完，原先用的就是它，一次全量重建会拖到小时级）
#   deb.debian.org             21 KB/s（25s 只下了 0.5 MB）
# 换机器/换网络后请重测：bash scripts/mirror-speedtest.sh
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y \
        pkg-config \
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
    python -m playwright install chromium --with-deps && \
    rm -rf /root/.cache/pip /tmp/*

# 修复: 磁盘空间不足时 pip 可能留下 0 字节的 typing_extensions.py
# (dist-info 完好, pip 误判已安装而不会修复, 导致 pydantic_core ImportError)
RUN python -m pip install --force-reinstall --no-deps typing-extensions -i https://pypi.tuna.tsinghua.edu.cn/simple

# 阶段 4: 代码层
FROM deps AS final

# 复制应用代码 (这一层会频繁变动)
COPY . .

# 编译 C++ 插件（依赖代码，所以放在 COPY 之后）
# 产物放在 /app/libs/：该路径不在 docker-compose 的源码挂载范围内，
# 保证镜像里始终有一份与镜像 ABI 匹配的动态库，不会被宿主目录覆盖。
RUN mkdir -p libs && \
    g++ -fPIC -shared \
    src/plugins/sub_records/table_gen.cpp \
    -o libs/libtablegen.so \
    $(pkg-config --cflags --libs cairo pango pangocairo jsoncpp) \
    -O3

# 确保 entrypoint.sh 可执行
RUN chmod +x scripts/entrypoint.sh

# 从构建阶段复制前端产物
COPY --from=webui-builder /webui/dist ./webui/dist

CMD ["/bin/bash", "scripts/entrypoint.sh"]