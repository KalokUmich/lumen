FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy lockfiles + project files first for better layer caching
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY shared/ ./shared/
COPY services/ai_service/ ./services/ai_service/

ENV PYTHONPATH=/app
EXPOSE 8001

CMD ["uv", "run", "uvicorn", "services.ai_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
