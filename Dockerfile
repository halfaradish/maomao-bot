FROM library/python:3.10.18-slim
LABEL authors="UNDERLR"
EXPOSE 6090 6379

COPY . .

RUN python -m pip install --upgrade pip
RUN python -m pip install --user pipx
RUN python -m pipx ensurepath
ENV PATH="/root/.local/bin:${PATH}"

RUN pipx install nb-cli
RUN pip install -r requirements.txt

CMD nb run