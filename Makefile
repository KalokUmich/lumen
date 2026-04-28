.PHONY: help install seed seed-tpch seed-orders smoke smoke-tpch smoke-orders \
        backend frontend dev clean lint typecheck test

PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@echo "Lumen — common dev commands"
	@echo
	@echo "  make install        Set up Python venv + install backend deps"
	@echo "  make seed-tpch      Seed local DuckDB with TPC-H scale=0.1 (~100MB)"
	@echo "  make seed-orders    Seed local DuckDB with the synthetic orders fixture"
	@echo "  make smoke          Run the AI smoke test (mock LLM, TPC-H)"
	@echo "  make smoke-orders   Run the AI smoke test (mock LLM, orders fixture)"
	@echo "  make backend        Launch all 4 backend services in the background"
	@echo "  make frontend       Launch the Vite dev server"
	@echo "  make dev            Backend + frontend together"
	@echo "  make lint           ruff check"
	@echo "  make typecheck      pyright on backend/"
	@echo "  make test           pytest backend/"
	@echo "  make clean          Remove .venv, .duckdb files, app.db"

install:
	@test -d backend/.venv || python3 -m venv backend/.venv
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet \
		fastapi 'uvicorn[standard]' sse-starlette \
		httpx pydantic pydantic-settings \
		asyncpg sqlalchemy aiosqlite \
		'anthropic[bedrock]' openai \
		pyjwt structlog tenacity \
		duckdb pyyaml redis \
		pytest pytest-asyncio
	@echo "✓ backend env ready"
	@echo "  python: $$($(PY) --version)"
	@echo "  packages: $$($(PIP) list --format=freeze | wc -l)"

seed: seed-lending

seed-lending:
	PYTHONPATH=. $(PY) local_test/seed_lending.py --scale 1.0

seed-lending-small:
	PYTHONPATH=. $(PY) local_test/seed_lending.py --scale 0.05

smoke:
	PYTHONPATH=backend:. $(PY) local_test/run_local_test.py --mock --vertical lending

# Launch all 4 backend services in the background. Logs to /tmp/lumen-*.log.
backend:
	@mkdir -p /tmp/lumen-logs
	@LUMEN_QUERY_BACKEND=duckdb_lending \
	 LUMEN_DEFAULT_VERTICAL=lending \
	 JWT_SIGNING_KEY=local-dev-only \
	 PYTHONPATH=backend $(PY) -m uvicorn services.workspace_service.main:app --port 8004 --log-level warning >/tmp/lumen-logs/workspace.log 2>&1 &
	@LUMEN_QUERY_BACKEND=duckdb_lending \
	 JWT_SIGNING_KEY=local-dev-only \
	 WORKSPACE_SERVICE_URL=http://localhost:8004 \
	 PYTHONPATH=backend $(PY) -m uvicorn services.query_service.main:app --port 8002 --log-level warning >/tmp/lumen-logs/query.log 2>&1 &
	@JWT_SIGNING_KEY=local-dev-only \
	 LUMEN_DEFAULT_VERTICAL=lending \
	 USE_MOCK_LLM=$${USE_MOCK_LLM:-true} \
	 WORKSPACE_SERVICE_URL=http://localhost:8004 \
	 QUERY_SERVICE_URL=http://localhost:8002 \
	 PYTHONPATH=backend $(PY) -m uvicorn services.ai_service.main:app --port 8001 --log-level warning >/tmp/lumen-logs/ai.log 2>&1 &
	@JWT_SIGNING_KEY=local-dev-only \
	 AI_SERVICE_URL=http://localhost:8001 \
	 QUERY_SERVICE_URL=http://localhost:8002 \
	 PYTHONPATH=backend $(PY) -m uvicorn services.api_gateway.main:app --port 8000 --log-level warning >/tmp/lumen-logs/gateway.log 2>&1 &
	@sleep 2
	@echo "✓ services up: gateway:8000  ai:8001  query:8002  workspace:8004"
	@echo "  logs: tail -f /tmp/lumen-logs/*.log"
	@echo "  stop: pkill -f 'lumen|uvicorn services'"

frontend:
	cd frontend && npm run dev

dev: backend frontend

stop-backend:
	@pkill -f 'uvicorn services\.' || true
	@echo "✓ stopped"

lint:
	cd backend && .venv/bin/ruff check . || true

typecheck:
	cd backend && .venv/bin/pyright . || true

test:
	cd backend && PYTHONPATH=. .venv/bin/pytest

clean:
	rm -rf backend/.venv
	rm -f local_test/data/*.duckdb local_test/data/app.db
	rm -rf /tmp/lumen-logs
	@echo "✓ clean"
