# Lumen

> A lightweight, AI-native data platform. Connect databases, model metrics in code, ask questions in natural language — get answers grounded in a governed semantic layer.
>
> See `PRODUCT_REPORT.md` for product strategy and `IMPLEMENTATION_PLAN.md` for engineering detail.

## Quick start (local dev)

Prereqs: Docker, Docker Compose, Node 20+, Python 3.12+, [`uv`](https://github.com/astral-sh/uv) optional. **No AWS credentials needed for the smoke test** (mock LLM mode).

```bash
# 1. Bring up backing services (Postgres, Redis, Cube, Temporal, LocalStack)
docker compose up -d

# 2. Install backend deps
cd backend && uv sync && cd ..

# 3. Install frontend deps
cd frontend && npm install && cd ..

# 4. Configure local secrets / settings (gitignored)
cp config/secrets.yaml config/secrets.local.yaml      # then fill in keys you have
cp config/settings.yaml config/settings.local.yaml    # optional overrides

# 5. Seed a local SQLite/DuckDB warehouse with realistic business data (TPC-H)
python local_test/seed_tpch.py

# 6. Start backend services (each in its own terminal, or use a process manager)
cd backend
uv run uvicorn services.api_gateway.main:app --reload --port 8000
uv run uvicorn services.ai_service.main:app   --reload --port 8001
uv run uvicorn services.query_service.main:app --reload --port 8002

# 7. Start frontend
cd frontend && npm run dev   # http://localhost:5173

# 8. Run the smoke test (no LLM provider keys needed)
python local_test/run_local_test.py --mock
```

## Repo layout

```
lumen/
├── PRODUCT_REPORT.md           # Strategy
├── IMPLEMENTATION_PLAN.md      # Engineering plan
├── config/
│   ├── settings.yaml           # Defaults (committed)
│   ├── secrets.yaml            # Schema for required secrets, with empty values (committed)
│   ├── settings.local.yaml     # Local overrides (gitignored)
│   └── secrets.local.yaml      # Local API keys (gitignored)
├── backend/                    # The platform — connect any frontend here
│   ├── shared/                 # Internal SDK (LLM client, auth, audit, observability)
│   ├── services/               # api_gateway, ai_service, query_service, ...
│   └── cube/                   # Cube semantic layer (config + schemas)
├── frontend/                   # Reference web app (React + Vite + Observable Plot)
├── local_test/                 # Local test scheme with TPC-H business dataset
└── docs/                       # Tutorials, API ref, runbooks
```

## Configuration

Lumen uses two YAML files in `config/`, each with an optional `.local.yaml` override:

- **`settings.yaml`** — non-secret config: LLM provider tier mapping, task routing, workspace presets, feature flags, observability.
- **`secrets.yaml`** — schema for required secrets (API keys, JWT signing key, etc.) with placeholder values. Real values go in `secrets.local.yaml` for development.

The `*.local.yaml` files are gitignored. The platform merges `local` over base on load.

## LLM providers

The platform supports multiple model providers, configurable in `settings.yaml`:

| Provider | Models we map |
|---|---|
| **AWS Bedrock** | Claude (Opus / Sonnet / Haiku) |
| **Anthropic API** | Claude (direct API) |
| **Alibaba DashScope** | Qwen (qwen-max / qwen-plus / qwen-turbo) |

At service startup, each configured provider is **health-checked** with a minimal call. Providers that fail authentication are marked unavailable and won't be routed to until restart.

## Architecture (one-liner)

User → React → API Gateway (Python/FastAPI) → AI Service (multi-provider LLM) → Cube semantic layer → MySQL/Postgres/MongoDB/DuckDB.

The backend is fully decoupled from the frontend — third-party UIs can connect to the API gateway directly.

For the long version see `IMPLEMENTATION_PLAN.md` §3.

## License

Proprietary.
