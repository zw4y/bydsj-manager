FROM python:3.12-slim

WORKDIR /app

COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r /app/requirements.txt

COPY server /app/server

ENV CARD_DB_PATH=/data/cards.db
VOLUME ["/data"]
EXPOSE 8000

CMD ["python", "-m", "server.main"]
