FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY app/ ./app/

RUN mkdir -p /app/screenshots

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
