# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Lumen is

Lightweight, AI-native data platform: connect a warehouse, model metrics in Cube, ask questions in natural language, get answers grounded in a governed semantic layer. Backend is a set of small Python/FastAPI services; frontend is a React/Vite reference app. Strategy/engineering deep-dives live in `PRODUCT_REPORT.md` and `IMPLEMENTATION_PLAN.md` — read these before architectural changes.

## Common commands

The `Makefile` is the source of truth for local dev. It uses a venv at `backend/.venv` (created by `make install`); the README mentions `uv` but the Makefile uses plain `pip`.

```bash
# Setup
make install                              # Create backend/.venv and install deps
make seed-lending                         # Seed local DuckDB with consumer-lending data (~1.9GB, 35M rows)
make seed-lending-small                   # 5% scale for fast iteration (~100MB)
make seed-orders                          # Seed the smaller orders fixture

# Run everything
make backend                              # Launches all 4 services in background; logs to /tmp/lumen-logs/
make frontend                             # Vite dev server on :5173
make dev                                  # Both
make stop-backend                         # pkill the uvicorns

# Smoke / mock-LLM end-to-end
make smoke                                # TPC-H, mock LLM (no API keys needed)
make smoke-orders                         # orders fixture, mock LLM

# Quality gates
make lint                                 # ruff check (backend)
make typecheck                            # pyright (backend, strict on shared/ + ai_service/)
make test                                 # pytest (backend)

# Frontend
cd frontend && npm test                   # vitest
cd frontend && npm run e2e                # Playwright
cd frontend && npm run typecheck          # tsc --noEmit
cd frontend && npm run lint               # eslint
```

Single-test invocations:

```bash
# One Python test file or test
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_critic.py
cd backend && PYTHONPATH=. .venv/bin/pytest tests/test_critic.py::test_specific_case -v

# One Vitest file
cd frontend && npm test -- src/lib/format.test.ts

# One Playwright spec
cd frontend && npx playwright test e2e/chat.spec.ts
```

`pytest` config (`backend/pyproject.toml`) sets `asyncio_mode=auto` and registers two markers: `eval` (golden-set AI regression, slow) and `integration` (real DB/Cube). Filter with `-m "not eval and not integration"` for fast runs.

## Service layout (the big picture)

Four FastAPI services + one Temporal worker, all in `backend/`. Each is launched by `make backend` on a fixed port. The frontend talks **only** to the API gateway; the gateway mints an internal JWT and fans out.

| Service | Port | Role |
|---|---|---|
| `services/api_gateway` | 8000 | BFF / auth boundary. Verifies external JWT, mints internal JWT, proxies SSE straight through to the browser, emits audit log. Zero business logic. |
| `services/ai_service` | 8001 | LLM tool-use loop. `/chat/respond` is SSE-streamed. Owns the system prompt, tool schemas, tool dispatcher, visualizer, critic. |
| `services/query_service` | 8002 | Executes Cube queries against the configured warehouse backend (DuckDB locally, Postgres/MySQL/Mongo in real deployments). Endpoint is `POST /internal/queries/run` and requires the internal JWT + `X-Internal-Token`. |
| `services/workspace_service` | 8004 | Workspace metadata, schema bundles, glossary, model definitions. |
| `services/auth_service` | — | OIDC integration (Phase 1 stub). |
| `services/etl_service/worker.py` | — | Temporal worker for ETL flows. |

Cross-service dependencies: gateway needs `AI_SERVICE_URL`/`QUERY_SERVICE_URL`; ai_service needs `WORKSPACE_SERVICE_URL`/`QUERY_SERVICE_URL`; query_service needs `WORKSPACE_SERVICE_URL`. All read `JWT_SIGNING_KEY` (default `local-dev-only` from the Makefile).

`backend/shared/` is the internal SDK every service imports — auth (`auth.py`), settings loader (`settings.py`), LLM provider registry (`llm_providers/`, `llm_config.py`), audit, observability, error types, schema-bundle helpers. Don't duplicate any of this in a service.

## The AI loop

`backend/services/ai_service/stream.py` runs a bounded tool-use loop (`MAX_HOPS = settings.ai.max_hops`, default 6) over `LLMProvider.stream`. The model sees:

1. The system prompt (`prompts/system.py`) + few-shot examples (`prompts/few_shot.py`).
2. Workspace schema summary + glossary, fetched via `workspace_service`.
3. Tool definitions from `schemas.py` (Pydantic → JSON schema). Tools include Cube query, text-to-query routing, visualizer, final-answer.
4. SSE events stream back to the browser via the gateway. Event protocol is `SSEEvent` in `stream.py`; the React frontend parses these in `frontend/src/lib/api.ts`.

Cube query execution goes through `cube_runner.py`, which calls the query_service. Locally, the query_service routes to one of the DuckDB runners in `local_test/duckdb_query_runner*.py` — these emulate Cube semantics (joins, time grain, dateRange like "last month") against the local DuckDB file. Selection is via `LUMEN_QUERY_BACKEND` (`duckdb_lending` is the default).

Two skills under `.claude/skills/` are **prescriptive** for AI-facing changes — read them before touching tool definitions, chart specs, or measure design:

- `data-transform/SKILL.md` — when to compute via Cube measure vs. Pandas transform tool. Source of truth for tool-routing prompts.
- `data-viz-standards/SKILL.md` — deterministic chart-type rules. Any chart_spec the visualizer emits must conform.

## Configuration

Two YAMLs in `config/`, each with a gitignored `*.local.yaml` override that's deep-merged on top:

- `settings.yaml` — non-secret: LLM provider/tier mapping, fallback chain, workspace presets, observability, feature flags. `llm.providers` defines `bedrock`, `anthropic`, `alibaba` (DashScope, OpenAI-compatible). At startup each enabled provider is health-checked with a 1-token call; failures mark it unavailable for the process lifetime.
- `secrets.yaml` — schema only (placeholder values). Real keys go in `secrets.local.yaml`.

Reading: `shared.settings.get("ai.max_hops", 6)` — dotted path, with default. Don't read YAML directly elsewhere.

## Cube semantic layer

`backend/cube/schema/` holds vertical-specific cube definitions:

- `verticals/lending/` — Consumer Lending (the primary fixture as of 2026-04-27). 8 cubes: Customer, Branch, LoanOfficer, Application, Loan, Payment, Collection, CreditInquiry. ~1.9 GB DuckDB, 35M rows.
- `shared/`, `examples/` — common pieces

Verticals are selected via `LUMEN_DEFAULT_VERTICAL` (default `lending`). The frontend's "model" pages in `frontend/src/components/model/` edit these. TPC-H + saas_finance were removed on 2026-04-27 in favor of the realistic lending dataset.

## Frontend notes

React 19 + Vite 6 + TanStack Router/Query + Zustand + Tailwind. Charts use `@observablehq/plot`. The chat panel renders SSE events from the AI service in `components/chat/`. Workbench (`components/workbench/`) is the manual query-builder; Dashboard (`components/dashboard/`) tiles results with `react-grid-layout`.

State store is `src/lib/store.ts` (Zustand). API client + SSE parsing is `src/lib/api.ts`. Schema/format/markdown helpers in `src/lib/` are all unit-tested with vitest — keep that pattern when adding new lib utilities.

Playwright e2e specs live in `frontend/e2e/`. The dev server must be running for `npm run e2e`.

## Gotchas

- `make backend` writes logs to `/tmp/lumen-logs/`. If queries fail with `IOException: database does not exist`, check `readlink /proc/<pid>/cwd` — uvicorn was likely started from a different working directory and is looking for the DuckDB file relative to that. Fix is to `pkill -f 'uvicorn services\.'` and re-run `make backend` from the repo root.
- The Makefile defaults `USE_MOCK_LLM=true` — set it to `false` (and have `secrets.local.yaml` filled in) to exercise the real provider.
- `pyright` is **strict** on `shared/` and `services/ai_service/` only; the rest is non-strict. Don't downgrade to non-strict to silence errors there.
- Two `pyproject.toml` `name`/`package.json` `name` entries still say `omni-*` — the project was renamed to Lumen. Don't "fix" these unless told to; they may be load-bearing for some scripts.
