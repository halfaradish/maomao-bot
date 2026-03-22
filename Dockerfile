FROM library/python:3.10.18-slim
LABEL authors="UNDERLR"
EXPOSE 6090 6379

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/root/.local/bin:${PATH}"

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y \
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

RUN python -m pip install --upgrade pip && \
    python -m pip install --user pipx && \
    python -m pipx ensurepath
ENV PATH="/root/.local/bin:${PATH}"

ENV DJANGO_SETTINGS_MODULE="django_project.settings"

# 1. 先复制依赖文件
COPY requirements.txt /app/requirements.txt
WORKDIR /app

# 2. 安装依赖（只要 requirements.txt 没变，这一层就会缓存）
RUN python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    python -m pip install nb-cli -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    python -m playwright install chromium --with-deps && \
    rm -rf /root/.cache/pip /tmp/*  # 显式清理缓存

# 3. 最后复制代码（代码变动不会使上面层失效）
COPY . /app

# 3. 编译 C++ 插件二进制文件
RUN g++ -fPIC -shared \
    /app/src/plugins/sub_records/table_gen.cpp \
    -o /app/src/plugins/sub_records/table_gen.so \
    $(pkg-config --cflags --libs cairo pango pangocairo jsoncpp) \
    -O3

CMD ["nb", "run"]
