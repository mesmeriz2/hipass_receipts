FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/archives/*

COPY app/ ./app/

RUN mkdir -p /app/screenshots

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
