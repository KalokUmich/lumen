FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        fastapi 'uvicorn[standard]' sse-starlette \
        httpx pydantic pydantic-settings \
        asyncpg sqlalchemy aiosqlite \
        'anthropic[bedrock]' openai \
        pyjwt structlog tenacity \
        duckdb pyyaml redis \
        pytest pytest-asyncio

COPY backend /app/backend
COPY config /app/config
COPY local_test /app/local_test

ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1

EXPOSE 8001 8002 8004 8088

CMD ["python", "-m", "uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8088"]
