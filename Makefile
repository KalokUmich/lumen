.PHONY: help install install-backend install-frontend seed seed-lending seed-lending-small \
        smoke backend frontend dev clean lint typecheck test stop-backend \
        docker-build docker-up docker-down docker-logs docker-clean docker-ps docker-infra-up

PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@echo "Lumen — common dev commands"
	@echo
	@echo "  make install        Set up Python venv + install backend & frontend deps"
	@echo "  make install-backend   Backend deps only (Python venv)"
	@echo "  make install-frontend  Frontend deps only (npm ci)"
	@echo "  make seed-lending       Seed local DuckDB with consumer-lending data (~1.9GB, 35M rows)"
	@echo "  make seed-lending-small Same data at 5% scale (~100MB, fast iteration)"
	@echo "  make smoke              Run the AI smoke test (mock LLM, lending fixture)"
	@echo "  make backend        Launch all 4 backend services in the background"
	@echo "  make frontend       Launch the Vite dev server"
	@echo "  make dev            Backend + frontend together"
	@echo "  make lint           ruff check"
	@echo "  make typecheck      pyright on backend/"
	@echo "  make test           pytest backend/"
	@echo "  make clean          Remove .venv, .duckdb files, app.db"
	@echo
	@echo "  ── Docker ──"
	@echo "  make docker-build   Build backend + frontend images"
	@echo "  make docker-up      Start full stack (backend services + frontend) in background"
	@echo "  make docker-down    Stop the stack"
	@echo "  make docker-logs    Tail logs from all containers"
	@echo "  make docker-ps      Show container status"
	@echo "  make docker-clean   Stop + remove volumes (frontend_node_modules, pg_data)"
	@echo "  make docker-infra-up   Start optional infra (postgres, cube, redis, temporal, localstack)"

install: install-backend install-frontend

install-backend:
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

install-frontend:
	@command -v npm >/dev/null || { echo "✗ npm not found — install Node.js (>=18) first"; exit 1; }
	@if [ -f frontend/package-lock.json ]; then \
		cd frontend && npm ci; \
	else \
		cd frontend && npm install; \
	fi
	@echo "✓ frontend deps installed"

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
	 PYTHONPATH=backend $(PY) -m uvicorn services.api_gateway.main:app --port 8088 --log-level warning >/tmp/lumen-logs/gateway.log 2>&1 &
	@sleep 2
	@echo "✓ services up: gateway:8088  ai:8001  query:8002  workspace:8004"
	@echo "  logs: tail -f /tmp/lumen-logs/*.log"
	@echo "  stop: pkill -f 'lumen|uvicorn services'"

frontend:
	@test -d frontend/node_modules || $(MAKE) install-frontend
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

# ── Docker ──────────────────────────────────────────────────────────────

docker-build:
	docker compose build

docker-up:
	@test -f local_test/data/lending.duckdb || { echo "✗ local_test/data/lending.duckdb not found — run 'make seed-lending' first (the file is bind-mounted into the containers)"; exit 1; }
	docker compose up -d
	@echo
	@echo "✓ stack up"
	@echo "  frontend:  http://localhost:5173"
	@echo "  gateway:   http://localhost:8088"
	@echo "  ai:        http://localhost:8001"
	@echo "  query:     http://localhost:8002"
	@echo "  workspace: http://localhost:8004"
	@echo
	@echo "  logs: make docker-logs"
	@echo "  stop: make docker-down"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps

docker-clean:
	docker compose down -v
	@echo "✓ stack + volumes removed"

docker-infra-up:
	docker compose --profile infra up -d
	@echo "✓ infra up: postgres:5432  redis:6379  cube:4000  temporal:7233  localstack:4566"
