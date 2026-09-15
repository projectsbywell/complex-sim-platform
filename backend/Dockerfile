# complex-sim-platform backend image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY export_openapi.py .

# Runtime configuration defaults (override with -e on `docker run`)
ENV SECRET_KEY=please-change-me \
    DATA_DIR=/app/data \
    SIM_CORE_PATH=/app/simulation-core \
    RATE_LIMIT_PER_MINUTE=100 \
    CACHE_TTL_SECONDS=60

# Durable JSON data lives here
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]