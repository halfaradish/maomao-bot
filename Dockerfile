FROM library/python:3.10.18-slim
LABEL authors="UNDERLR"
EXPOSE 6090 6379

RUN python -m pip install --upgrade pip && \
    python -m pip install --user pipx && \
    python -m pipx ensurepath
ENV PATH="/root/.local/bin:${PATH}"

# 1. 先复制依赖文件
COPY requirements.txt /app/requirements.txt
WORKDIR /app

# 2. 安装依赖（只要 requirements.txt 没变，这一层就会缓存）
RUN python -m pip install -r requirements.txt && \
    python -m pipx install nb-cli

# 3. 最后复制代码（代码变动不会使上面层失效）
COPY . /app

CMD ["nb", "run"]