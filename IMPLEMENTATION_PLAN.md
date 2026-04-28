# Lumen — Implementation Plan

> Companion to `PRODUCT_REPORT.md`. This document is the engineering bible: it converts product decisions into concrete API contracts, database schemas, build orders, and a working repo layout.
>
> **Mission**: Ship a lightweight, AI-native data platform on AWS in 24 months. Internal use first, external paying customers by Phase 4. Multi-provider LLM (Bedrock, Anthropic, Alibaba) with provider-agnostic tier abstraction.
>
> **Scope of this doc**: Phase 0 + Phase 1 (months 0–9). Later phases are sketched at the end.

---

## 0. Status snapshot (last audited 2026-04-27)

**Legend**: ✅ done · 🟡 partial / wired-but-not-integrated · ❌ not started · ❓ unclear

> **Primary fixture as of 2026-04-27**: `consumer_lending` (1.9 GB DuckDB, 35M rows, 8 cubes — Customer, Branch, LoanOfficer, Application, Loan, Payment, Collection, CreditInquiry). 8-year horizon (2018-01-01 → 2026-04-27). Replaces TPC-H + saas_finance; old verticals are scheduled for removal once §22 is underway.

### Phase 0 — Foundation (M0–M3) — ✅ **complete**
All four backend services run, Cube + DuckDB stack works locally, AI tool-use loop is wired, golden set runs (30 questions, target 50). The `make backend` flow gets a new dev to a working chart in under 10 min.

### Phase 1 — Internal MVP (M4–M9) — 🟢 **largely complete**
| Milestone | Status | Gap |
|---|---|---|
| M4 Workbook + Dashboard MVP | ✅ | — |
| M5 Cross-filter + drill | ✅ | Cross-filter ✅; drill-down via right-click context menu ✅ (2026-04-28) |
| M5 Dashboard scheduling | ✅ stub | DB table + CRUD endpoints ✅; cron worker = Sprint G |
| M6 Model editor + git deploy | 🟡 | YAML editor + validation ✅; CI-based git deploy ❌ (needs `.github/workflows/`) |
| M7 AI escalation + prompt caching | ✅ | Cache hit-rate metric on `/providers` (2026-04-28) |
| M8 RBAC/RLS + audit | ✅ | RLS injector + middleware-based audit emit (2026-04-28) |
| M8 OIDC | ❌ | `auth_service` stub. Phase 2 — out-of-scope for an internal MVP |
| M9 Mongo→PG ETL | ❌ | Temporal worker scaffold only. Needs Mongo source + flat-doc transform |

### Phase 2 — Advanced features — see §22 deep parity matrix
**Started**: Markdown viz primitive ✅, Skills v0 (YAML + chat surfacing) ✅, per-tile inspect (SQL + ms + cache) ✅, sample_values prompt grounding 🟡 (a few cubes), aesthetic critic wired ✅.

**Not started** (top priorities — see §22 for the full sprint structure): RAG over Q→Query→Answer triples, learn-from-conversation + auto-learn, right-rail viz settings panel, calculations DSL (PIVOT/XLOOKUP/IFS/AI_*), modeling DSL parity (`value_format`, `links`, `drill_fields`, topics, content validator, branch mode), embed events protocol, MCP server, action hub, telemetry self-model.

### Cross-cutting gaps
- **CI/CD** ❌ no `.github/workflows/` — quick win available: copy a basic pytest+vitest+playwright matrix
- **Migrations** ❌ no `backend/migrations/` (Alembic dep installed but unused) — Phase 0 uses `Base.metadata.create_all`
- **Docs** ✅ `docs/SETUP.md` covers data-source / cube authoring / feedback loop (added 2026-04-27)
- **Coverage targets** ❌ not measured — add `pytest --cov=services --cov=shared` to CI
- **Observability** 🟡 `observability.py` 38 lines; structured audit middleware emits per-request log (2026-04-28); cache hit-rate on `/providers` (2026-04-28); Prom/Grafana/Sentry still not wired
- **Test counts (2026-04-28)** Backend pytest **62/62**; Frontend vitest **108/108**; Playwright e2e **21/21**; tsc clean

### What shipped 2026-04-27 → 2026-04-28 (one tracker session)
- ✅ Replaced TPC-H + saas_finance with **`consumer_lending`** (1.9 GB, 35M rows, 8 cubes, realistic FICO/grade/default-rate gradients) — Phase 0 fixture
- ✅ Demo workspace seeded with 5 starter workbooks + 1 dashboard ("Lending Overview")
- ✅ Bug B1 (relative-time → `dateRange`), B2 (low-N grouped bar), B3 (single-period grouped-bar blank chart) — all fixed with regression tests
- ✅ Markdown viz primitive (Mustache + Sparkline + ChangeArrow + sanitization)
- ✅ Skills v0 (YAML + bundle + chat EmptyState cards)
- ✅ Per-tile inspect (Time / Rows / Cache / Backend stat panel)
- ✅ Audit log middleware (every authenticated request → structured JSON)
- ✅ Cache hit-rate metric on `/providers`
- ✅ Schedules CRUD endpoints (M5 stub)
- ✅ Tufte breathing-room pass — Plot margins 32/24/56/40, BigNumber 32px tabular-nums, panel borders not shadows, dashboard gutters 24px, redundant legend suppression (R5), chat EmptyState reflowed, left-rail icons up-sized, ChartActions footer polished
- ✅ Roadmap §22 deep parity matrix (sprints A–G) authored from 1067-line Omni docs crawl + 765-line Looker survey
- ✅ §23 Tufte breathing-room rule set authored as always-on stance

---

## 0.5 Known P0 bugs (must fix before declaring Phase 1 done)

These are the bugs that make the AI loop visibly wrong to a user. Both have repros.

### B1 — AI omits `timeDimensions` for relative time phrases — ✅ fixed 2026-04-27
**Repro**: ask "number of orders by region over last 3 months over time" → SQL has no `WHERE o_orderdate ≥ ...` clause; all-time data is returned.

**Diagnosis**: `local_test/duckdb_query_runner_tpch.py` correctly emits a `BETWEEN` when `timeDimensions[].dateRange` is present; the LLM never set the field. The system prompt at `backend/services/ai_service/prompts/system.py` does not state explicitly that **relative-time phrases ("last N months", "MTD", "YTD") must use `timeDimensions[].dateRange`, not a `filters` clause**.

**Fix**:
1. Add a section to `prompts/system.py` titled "Time filtering" with three positive and two negative examples.
2. Add a few-shot to `prompts/few_shot.py` whose query is exactly this user prompt and whose tool input includes `timeDimensions: [{dimension: "Orders.order_date", dateRange: "last 3 months", granularity: "month"}]`.
3. Add a critic check in `critic.py` that, when the user prompt matches `/last\s+\d+\s+(day|week|month|quarter|year)s?/i` and the generated query has no `timeDimensions` with a `dateRange`, the loop retries with a corrective system message before answering.
4. Add a regression entry in `eval/golden_set.yaml` with the exact prompt.

### B2 — Visualizer picks multi-line over grouped-bar for low-N time × low-N category — ✅ fixed 2026-04-27

### B3 — Top-N within a single period renders a blank chart — ✅ fixed 2026-04-27

**Repro**: ask "Top 5 countries by sales this quarter" → chart panel is blank.

**Diagnosis**: R11 grouped-bar branch fired for `n_periods=1 × n_categories=5`. The visualizer emitted `chart_spec.type = "grouped-bar"` but `_build_chart_spec` only attaches `color` when there are 2 *categorical* dimensions, so it returned `{x: Nation__name, y: revenue}` with no color encoding. The frontend's grouped-bar Plot branch requires `colorField` and silently skipped the marks → empty SVG.

**Fix**:
1. `visualizer.py::_decide_chart_type` — R11 now requires `2 ≤ n_periods ≤ 4` (single-period grouped-bar degenerates to plain bar; route to `bar` instead).
2. `visualizer.py::_build_chart_spec` — when grouped-bar fires from R11 (time × dim), put time on X and the dim on color. Two-dim case unchanged.
3. `frontend/src/components/chart/PlotChart.tsx` — defence in depth: grouped-bar without `color` falls back to plain bar instead of emitting empty marks.
4. Tests: `test_single_period_top_n_uses_plain_bar_not_blank_grouped_bar`, `test_grouped_bar_when_picked_always_has_color_encoding`, plus `e2e/chat-time-range.spec.ts::Top 5 countries this quarter renders a non-blank chart` (asserts SVG has marks + non-trivial bbox).
**Repro**: same query as B1 (3 months × 5 regions). Result rendered as a 5-line trend chart; user expected grouped bar (X=month, group=region, color=region).

**Diagnosis**: `backend/services/ai_service/visualizer.py:277-280` matches `M=1 AND D=1 AND T=true AND card<=5` and unconditionally returns `multi-line`. The skill at `.claude/skills/data-viz-standards/SKILL.md` does not yet codify the line-vs-grouped-bar resolution for the **few-periods × few-categories** case.

**Fix**:
1. Insert a new rule into `data-viz-standards/SKILL.md` (the canonical chart guide): "**N_periods ≤ 4 AND N_categories ≤ 5 → grouped bar.** Periods become the X axis, categories become color groups within each period." See the rule set in §16.4 below; details in the skill itself.
2. Add a branch in `_decide_chart_type` *before* the `multi-line` case that returns `grouped-bar` when the time dimension yields ≤ 4 distinct buckets and the categorical dim has ≤ 5 distinct values.
3. Add `test_visualizer_grouped_bar_short_period.py` covering the (3 months × 5 regions) case.

---

## 0.7 How to read this doc

- §1–§14 are the original engineering spec (architecture / contracts / files). Status badges in §0 above tell you what's actually built.
- §15 is the original Phase 0+1 sprint plan, now annotated with badges.
- §16 holds risks + the visualizer/workspace deep-dive.
- §19 (new) is the **Omni parity backlog** — features we still owe to be a credible Omni alternative.
- §20 (new) is **Quality loops** — RAG, user accounts, feedback DB, eval workflow.
- §21 (new) is **Tutorials we owe** — what users currently can't figure out.

---

## 1. Repository Layout

Single monorepo. Polyglot is constrained to: Python (all backend services), TypeScript (frontend), YAML/JS (Cube schemas and config). No Go.

```
lumen/
├── PRODUCT_REPORT.md              # Strategic doc
├── IMPLEMENTATION_PLAN.md         # This file
├── README.md                      # Getting started
├── docker-compose.yml             # Local dev — every service runs here
├── .gitignore
├── .env.example                   # Required env vars
│
├── config/
│   ├── settings.yaml              # Defaults (committed)
│   ├── secrets.yaml               # Required-secret schema with placeholders (committed)
│   ├── settings.local.yaml        # Local overrides (gitignored)
│   └── secrets.local.yaml         # Local API keys (gitignored)
│
├── backend/                       # The platform — connect any frontend here
│   ├── pyproject.toml             # uv-managed monorepo for Python services
│   ├── shared/                    # Internal SDK shared by all services
│   │   ├── __init__.py
│   │   ├── settings.py            # Loads settings.yaml + settings.local.yaml + secrets.*
│   │   ├── llm_config.py          # Tier resolver (strong/medium/weak) + provider routing
│   │   ├── llm_providers/         # Multi-provider LLM clients
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # LLMProvider abstract interface
│   │   │   ├── bedrock.py         # AWS Bedrock (Claude)
│   │   │   ├── anthropic.py       # Anthropic API direct
│   │   │   ├── alibaba.py         # Alibaba DashScope (Qwen)
│   │   │   ├── mock.py            # Mock provider for local tests
│   │   │   └── registry.py        # Provider lifecycle + health checks
│   │   ├── auth.py                # JWT verify, workspace context
│   │   ├── audit.py               # Structured audit emit
│   │   ├── observability.py       # OTel setup
│   │   └── errors.py              # Domain error taxonomy
│   ├── services/
│   │   ├── api_gateway/           # Thin BFF: auth, routing, rate limit, audit
│   │   ├── ai_service/            # LLM orchestration — the moat
│   │   ├── query_service/         # Cube proxy + result cache + RLS injection
│   │   ├── auth_service/          # OIDC, workspace, role, group
│   │   ├── workspace_service/     # Workspace CRUD, saved workbooks/dashboards
│   │   └── etl_service/           # Temporal worker, Mongo→Postgres
│   ├── cube/                      # Cube semantic layer (config + per-workspace schemas)
│   │   ├── cube.js
│   │   └── schema/
│   │       ├── shared/            # Cross-workspace shared dimensions
│   │       └── verticals/         # Pre-built schemas per business vertical
│   │           └── tpch/          # TPC-H — used by local_test
│   └── tests/
│       ├── unit/
│       └── integration/
│
├── frontend/                      # Reference web app — fully decoupled
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/                # TanStack Router file-based
│       ├── components/
│       │   ├── chart/             # PlotChart wrapper, ChartSpec
│       │   ├── chat/              # ChatPanel
│       │   ├── workbench/         # Query builder
│       │   └── layout/
│       ├── lib/                   # api.ts, store.ts
│       └── styles.css
│
└── docs/
    ├── getting-started.md
    ├── architecture.md
    ├── data-team-onboarding.md    # The 5-step workflow
    ├── api-reference.md
    └── deployment.md
```

---

## 2. Database Layer

### 2.1 Three logical databases

| DB | Purpose | Tech |
|---|---|---|
| `app_db` | Workspaces, users, dashboards, audit metadata | Postgres 16 (RDS) |
| `warehouse_db` | Mongo-ETL landing + customer data | Postgres 16 (RDS, larger instance) |
| `cube_store` | Pre-aggregation cache (managed by Cube) | Cube Store (built-in) |

### 2.2 `app_db` schema (v0)

```sql
-- Workspaces
CREATE TABLE workspaces (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            TEXT UNIQUE NOT NULL,
  name            TEXT NOT NULL,
  llm_preset      TEXT NOT NULL DEFAULT 'balanced'
                  CHECK (llm_preset IN ('cost_sensitive','balanced','quality_first')),
  cube_schema_ref TEXT,           -- git ref of Cube schema currently deployed
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Users (federated identity, mapped to workspaces via memberships)
CREATE TABLE users (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email        TEXT UNIQUE NOT NULL,
  display_name TEXT,
  oidc_subject TEXT UNIQUE,
  attributes   JSONB NOT NULL DEFAULT '{}',  -- region, dept, etc., used for RLS
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workspace_memberships (
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role         TEXT NOT NULL CHECK (role IN ('admin','editor','viewer')),
  groups       TEXT[] NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, user_id)
);

-- Workbook = saved query + viz spec
CREATE TABLE workbooks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  cube_query   JSONB NOT NULL,   -- The Cube query JSON
  chart_spec   JSONB NOT NULL,   -- Our internal ChartSpec
  created_by   UUID NOT NULL REFERENCES users(id),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dashboard = grid of tile refs
CREATE TABLE dashboards (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  layout       JSONB NOT NULL,   -- [{tile_id, x, y, w, h}]
  filters      JSONB NOT NULL DEFAULT '[]',
  created_by   UUID NOT NULL REFERENCES users(id),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dashboard_tiles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dashboard_id UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
  workbook_id  UUID NOT NULL REFERENCES workbooks(id) ON DELETE CASCADE,
  title        TEXT
);

-- AI conversations (for memory + audit)
CREATE TABLE chat_sessions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id      UUID NOT NULL REFERENCES users(id),
  title        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant','tool')),
  content         JSONB NOT NULL,    -- text + tool calls + results
  tier_used       TEXT,              -- strong/medium/weak (NULL for user/tool)
  tokens_input    INT,
  tokens_output   INT,
  tokens_cached   INT,
  cost_usd_micros BIGINT,            -- store as integer micros for precision
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Failed query queue (data team review)
CREATE TABLE failed_query_reviews (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  question     TEXT NOT NULL,
  ai_query     JSONB,
  error        TEXT,
  status       TEXT NOT NULL DEFAULT 'open'
               CHECK (status IN ('open','triaged','fixed','wont_fix')),
  triaged_by   UUID REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_workbooks_workspace ON workbooks(workspace_id);
CREATE INDEX idx_dashboards_workspace ON dashboards(workspace_id);
CREATE INDEX idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX idx_failed_queries_status ON failed_query_reviews(workspace_id, status);
```

### 2.3 Connection management

- All Python services use **`asyncpg`** with a per-process connection pool (min=2, max=10).
- Connection strings via env: `APP_DB_URL`, `WAREHOUSE_DB_URL`.
- Migrations: **Alembic**. One migration head per service, versioned in `backend/migrations/`.
- Read replicas (Phase 2): `*_DB_URL_REPLICA` for read-heavy services (query_service).

### 2.4 Customer data sources (Cube-managed)

Cube is responsible for connecting to `MySQL`, `Postgres`, and (post-ETL) `warehouse_db`. Connection strings stored encrypted in `app_db.workspace_data_sources` (Phase 1 schema, omitted here for brevity).

Data source definition (per workspace, in app_db):
```yaml
type: mysql | postgres | postgres_warehouse
host: ...
port: ...
database: ...
username: ...
password_secret_id: arn:aws:secretsmanager:...   # Never store raw
ssh_tunnel: optional
```

---

## 3. Backend API Specifications

### 3.1 Conventions

- **REST + SSE.** No GraphQL in v1 (over-budget for our scope).
- All requests carry `Authorization: Bearer <jwt>`. Verified at API gateway, propagated downstream as `X-Workspace-Id` + `X-User-Id` + `X-User-Attrs` (signed internal token).
- All responses: JSON, `application/json; charset=utf-8`.
- Errors: RFC 7807 `application/problem+json`.
- Pagination: cursor-based, `?cursor=...&limit=...`.

### 3.2 API Gateway endpoints (`/api/v1/...`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Initiate OIDC flow |
| `GET` | `/auth/callback` | OIDC callback |
| `POST` | `/auth/refresh` | Refresh JWT |
| `GET` | `/me` | Current user + workspace memberships |
| `GET` | `/workspaces/:id` | Workspace metadata |
| `PATCH` | `/workspaces/:id` | Update name, llm_preset |
| `GET` | `/workspaces/:id/cube-schema` | Compiled schema summary (for AI grounding) |
| `POST` | `/workspaces/:id/cube-schema/deploy` | Deploy schema from git ref |
| `GET` | `/workbooks` / `/workbooks/:id` | List / fetch |
| `POST` | `/workbooks` | Create |
| `PATCH` | `/workbooks/:id` | Update query/spec |
| `POST` | `/queries/run` | Run an arbitrary cube_query |
| `POST` | `/queries/run-async` | Long-running, returns job_id |
| `GET` | `/queries/jobs/:id` | Poll long query |
| `POST` | `/chat/sessions` | New chat session |
| `POST` | `/chat/sessions/:id/messages` | Send message — **SSE stream response** |
| `GET` | `/chat/sessions/:id/messages` | Replay history |
| `GET` | `/dashboards` / `/dashboards/:id` | List / fetch |
| `POST` | `/dashboards` | Create |
| `PATCH` | `/dashboards/:id` | Update layout/filters |
| `GET` | `/admin/failed-queries` | Data team queue |
| `POST` | `/admin/failed-queries/:id/triage` | Mark triaged |

### 3.3 AI Service: SSE event protocol

`POST /chat/sessions/:id/messages` returns Server-Sent Events:

```
event: thinking
data: {"tier":"medium","message":"Analyzing your question..."}

event: tool_use
data: {"tool":"run_cube_query","input":{"measures":["Orders.revenue"],...}}

event: tool_result
data: {"rows":42,"sample":[{"Orders.revenue":12345}]}

event: token
data: {"text":"Last quarter revenue was "}

event: token
data: {"text":"$1.2M, up 8% from Q4."}

event: viz_spec
data: {"type":"big-number","value":1234567,"format":"currency"}

event: final
data: {"message_id":"...","cube_query":{...},"chart_spec":{...},"tokens":{"input":3200,"output":180,"cached":2900}}

event: error
data: {"code":"CUBE_QUERY_FAILED","detail":"..."}
```

### 3.4 Cube query JSON contract

This is the **canonical structured query** the AI emits and the query service consumes. Aligned with Cube's REST API but extended.

```json
{
  "measures": ["Orders.revenue", "Orders.aov"],
  "dimensions": ["Orders.country"],
  "timeDimensions": [
    {
      "dimension": "Orders.created_at",
      "granularity": "month",
      "dateRange": "last 12 months"
    }
  ],
  "filters": [
    { "member": "Orders.status", "operator": "equals", "values": ["paid"] }
  ],
  "segments": ["Orders.high_value"],
  "order": { "Orders.revenue": "desc" },
  "limit": 100
}
```

Validated server-side against compiled Cube schema before execution. Any reference to a non-existent measure/dimension → 422 with field-level errors (and routed to AI for self-correction).

### 3.5 Internal service-to-service auth

Internal calls use signed JWTs minted by the gateway (`HS512` with rotating shared key from Secrets Manager). 5-minute TTL. Services validate via shared `auth.verify_internal_token()`.

---

## 4. AI Service — Detailed Design

### 4.0 Subagent architecture (the visualizer)

The AI service is **not a single LLM call**. It runs a small, hand-rolled state graph in `services/ai_service/stream.py` with these nodes:

```
                       ┌────────────────────────────────────┐
                       │   Main loop (provider.stream)      │
                       │   - tier-routed Claude call        │
                       │   - tool-use orchestration         │
                       └──────────┬─────────────────────────┘
                                  │ tool_use=run_cube_query
                                  ▼
                       ┌────────────────────────┐
                       │  cube_runner           │   (HTTP → query_service)
                       │  + result row coercion │
                       └──────────┬─────────────┘
                                  │ rows
                                  ▼
                       ┌────────────────────────────────────┐
                       │  visualizer subagent               │   (deterministic + optional weak-tier LLM tiebreak)
                       │  - data_profile() → DataSummary    │
                       │  - select_chart() → ChartType      │
                       │  - build_chart_spec() → ChartSpec  │
                       │  rules from .claude/skills/        │
                       │    data-viz-standards/SKILL.md     │
                       └──────────┬─────────────────────────┘
                                  │ ChartSpec (authoritative)
                                  ▼
                       ┌────────────────────────────────────┐
                       │  Main loop continues, eventually   │
                       │  emits final_answer with chart_spec│
                       │  REPLACED by visualizer's pick     │
                       └────────────────────────────────────┘
```

**Why split visualization out of the main LLM:**

1. **Determinism**: most queries hit a deterministic rule branch in `select_chart()`. The frontend renders the same chart for the same data shape every time.
2. **Cost**: no extra LLM tokens for chart selection in the common case. The weak-tier tiebreak fires only when `decide_chart_type` returns confidence < 0.7.
3. **Quality**: the rules encode best practices from Cleveland-McGill, Tufte, Few, Mackinlay, Datawrapper, Tableau "Show Me". Codified once in `.claude/skills/data-viz-standards/SKILL.md`; applied uniformly.
4. **Auditability**: each chart_spec carries `rationale` and `confidence`. The chat surface shows "Why this chart?" on hover.

**Why NOT LangGraph**: For this 3-node graph (LLM → tool → visualizer → LLM continue), 50 lines of plain async Python in `stream.py` does the job. LangGraph adds a 10MB dep + a learning curve without enabling features we need. We'll revisit if we add parallel branches or human-in-the-loop pauses later.

### 4.1 Files

### 4.1 Component layout

```
ai_service/
├── main.py                  # FastAPI app + /providers health endpoint
├── routing.py               # Tier routing (uses llm_config)
├── prompts/
│   ├── system.py            # System prompt builder
│   └── few_shot.py          # Few-shot example selector
├── schemas.py               # Pydantic CubeQuery / FinalAnswer + tool definitions
├── stream.py                # Tool-use loop + SSE event protocol
├── cube_runner.py           # Calls query_service over HTTP
├── data_profile.py          # Profiles result rows: cardinalities, types, skew
├── visualizer.py            # The viz subagent — implements SKILL.md §3
└── eval/
    ├── runner.py            # Eval harness (pytest -m eval)
    └── golden_set.yaml      # Curated NL → CubeQuery + expected fields
```

`.claude/skills/data-viz-standards/SKILL.md` is the **authoritative document** for chart selection. The visualizer's code is a faithful encoding of that skill — when the skill changes, the visualizer changes.

### 4.2 Prompt structure

```
[System]
You are a data analyst with access to the following Cube semantic model:

<schema cache_control="ephemeral">
{cube_schema_summary, ~5K tokens, marked for prompt caching}
</schema>

<glossary cache_control="ephemeral">
{business glossary, ~1K tokens}
</glossary>

When answering, you MUST:
1. Output ONLY a Cube query via the `run_cube_query` tool, OR ask a clarifying question via `ask_clarification`, OR finalize with `final_answer`.
2. Reference only measures/dimensions defined in the schema.
3. If filtering on `status` or other enum dimensions, only use values listed in `meta.enum_values`.
4. Always end with `final_answer` containing a concise text summary, the final cube_query, and a chart_spec.

[Few-shot examples — top 5 matched by question keywords]
{NL → CubeQuery JSON pairs}

[User]
{conversation history}
{current question}
```

### 4.3 Tool definitions (Anthropic tools schema)

```python
TOOLS = [
    {
        "name": "run_cube_query",
        "description": "Execute a Cube query. Returns rows.",
        "input_schema": CubeQuerySchema.model_json_schema(),
    },
    {
        "name": "ask_clarification",
        "description": "Ask the user a clarifying question when the request is ambiguous.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "final_answer",
        "description": "Provide the final answer to the user.",
        "input_schema": FinalAnswerSchema.model_json_schema(),
    },
]
```

### 4.4 Tool-use loop

```python
async def respond(question: str, ctx: ChatContext) -> AsyncIterator[SSEEvent]:
    tier = await route_text_to_query(question, ctx)
    yield SSEEvent("thinking", {"tier": tier.name})

    messages = build_messages(ctx)
    for hop in range(MAX_HOPS := 6):
        async with bedrock.stream(model=tier.model_id, messages=messages, tools=TOOLS) as stream:
            async for chunk in stream:
                if chunk.type == "content_block_delta" and chunk.delta.type == "text_delta":
                    yield SSEEvent("token", {"text": chunk.delta.text})

        response = stream.get_final_message()
        if response.stop_reason != "tool_use":
            break

        tool_use = next(b for b in response.content if b.type == "tool_use")
        if tool_use.name == "run_cube_query":
            yield SSEEvent("tool_use", {"tool": "run_cube_query", "input": tool_use.input})
            result = await run_cube_query(tool_use.input, ctx)
            yield SSEEvent("tool_result", {"rows": len(result.rows)})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result.summary())}]})
        elif tool_use.name == "ask_clarification":
            yield SSEEvent("clarification", {"question": tool_use.input["question"]})
            return
        elif tool_use.name == "final_answer":
            yield SSEEvent("final", tool_use.input)
            return
    raise MaxHopsExceeded()
```

### 4.5 Eval harness

- Golden set: `backend/services/ai_service/eval/golden_set.yaml` — start with 50 questions, grow to 500.
- `pytest -m eval` runs the full set; CI runs nightly + on every prompt change.
- Quality gate: regression must be ≤ 1 case worse than baseline.
- Output: HTML report uploaded to S3 (history visible to data team).

---

## 5. Frontend — Detailed Design

### 5.1 Stack lock-in

| Concern | Choice |
|---|---|
| Build | Vite |
| Framework | React 19 |
| Lang | TypeScript strict |
| Routing | TanStack Router (file-based) |
| Server state | TanStack Query |
| Client state | Zustand |
| Forms | React Hook Form + Zod |
| Charts | Observable Plot (+ D3 escape) |
| Tables | TanStack Table; AG Grid Community for pivot |
| Editor | Monaco |
| Styling | Tailwind v4 + Radix UI |
| Drag/drop | dnd-kit |
| Icons | Lucide |
| Test | Vitest + Testing Library + Playwright |

### 5.2 Visual design system

**Aesthetic principles**: data-first, dense, calm. Inspiration: Linear, Vercel dashboard, Hex notebooks. Avoid the "consumer SaaS pastel" trap — we serve analysts, not Instagram.

**Tokens** (`tailwind.config.js`):

```js
colors: {
  // Surface
  bg:        { DEFAULT: '#0B0D10', subtle: '#13161B', elevated: '#1A1E25' },
  border:    { DEFAULT: '#272B33', strong: '#3A3F49' },
  // Text
  fg:        { DEFAULT: '#E6E8EB', muted: '#9BA1A8', subtle: '#6B7177' },
  // Accent (deliberately limited; data viz palette is separate)
  accent:    { DEFAULT: '#7C5CFF', hover: '#6B4DEB' },
  // Semantic
  success:   '#3DD68C',
  warning:   '#F0A04B',
  danger:    '#FF5C5C',
}
```

**Light mode** mirrors with inverted surface tokens; both ship day-1.

**Data viz palette** (separate from UI accent — color-blind-safe, intentionally muted):
```js
viz: {
  categorical: ['#5B8FF9','#5AD8A6','#5D7092','#F6BD16','#E8684A','#6DC8EC','#9270CA','#FF9D4D','#269A99','#FF99C3'],
  sequential:  ['#EAF1FF','#C5D9FF','#8BB1FF','#5B8FF9','#2E5CD8','#1A3A9C'],
  diverging:   ['#D63E3E','#F09494','#F2F2F2','#9DBFE3','#1F5BB5'],
}
```

**Typography**:
- UI: Inter Variable
- Numerals: Inter `tabular-nums` for all numeric cells
- Code/SQL: JetBrains Mono Variable

**Density**: comfortable (default) and dense (toggle in user prefs). Dense reduces row height 32→24px.

### 5.3 Information architecture

```
┌─ Top bar ──────────────────────────────────────────────────┐
│ Logo · Workspace ▾  ⌘K Search   AI ●   Notifications  User │
├──────┬─────────────────────────────────────────────────────┤
│ Left │  Main canvas                                         │
│ rail │  ┌──────────────────────────────────────────────┐   │
│      │  │ Surface-specific header (Save · Share · ...) │   │
│ 📊   │  ├──────────────────────────────────────────────┤   │
│ 📈   │  │                                              │   │
│ 🧬   │  │   [Workbook | Dashboard | Model | AI]        │   │
│ 💬   │  │                                              │   │
│ ⚙️   │  └──────────────────────────────────────────────┘   │
└──────┴─────────────────────────────────────────────────────┘
```

### 5.4 Surface specs

#### 5.4.1 Workbook
- 3-column layout: Field picker | Query area | Visualization
- Field picker: tree of `Cube > Measure / Dimension`, drag to query
- Query area:
  - Pills row: `+ measure`, `+ dimension`, `+ filter`, `+ time`, `+ segment`
  - Order/limit inputs
  - Toggle: visual builder ↔ JSON ↔ generated SQL
- Visualization: auto-pick chart, manual override, "Pin to dashboard" button
- Right sidebar (collapsed by default): AI assist (modify current query)

#### 5.4.2 Dashboard
- `react-grid-layout` 12-col grid, tile min size 4×3
- Tile types: chart, big-number, table, markdown
- Header: dashboard filters (apply to all tiles), date range, refresh
- Right-click on data point → drill-down menu (open Workbook with filter applied)
- Cross-filter: clicking a categorical mark in one tile filters all others
- Auto-refresh: configurable per dashboard (off / 5min / 1hr)

#### 5.4.3 Model Editor
- File tree: read from git repo via API
- Monaco editor: YAML mode with Cube schema syntax
- Bottom panel: validation errors + lineage preview
- "Run validation" + "Deploy to workspace" buttons
- Diff vs `main` (split view)

#### 5.4.4 AI Chat
- Full-screen mode (route `/chat`) and inline panel mode (in Workbook/Dashboard)
- Message bubbles with rich content: text + Cube query (collapsible) + chart preview
- "Continue in Workbook" CTA at bottom of each AI message
- Citations: each measure used → click → jump to model definition
- Conversation list left rail (truncated to 20 most recent; search ⌘F)

### 5.5 PlotChart wrapper contract

```ts
export type ChartSpec = {
  type: 'line' | 'bar' | 'area' | 'scatter' | 'heatmap' | 'pie' | 'big-number' | 'table';
  x?:  { field: string; type: 'time' | 'ordinal' | 'quantitative'; label?: string };
  y?:  { field: string; agg?: 'sum' | 'avg' | 'count'; format?: 'number' | 'currency' | 'percent'; label?: string };
  color?:  { field: string; palette?: 'categorical' | 'sequential' | 'diverging' };
  facet?:  { row?: string; column?: string };
  marks?:  PlotMarkOverride[];   // escape hatch — raw Plot mark options
};
```

`PlotChart` consumes `ChartSpec + rows[]` and renders deterministically. Pure wrapper, no fetching.

### 5.6 State management rules

- Server data → TanStack Query keyed on `(workspace_id, resource, params)`
- Cross-component UI state (e.g. dashboard cross-filter) → Zustand slice
- Form state → React Hook Form
- Never lift state into parents that don't render it

---

## 6. Bedrock Integration

### 6.1 Why Anthropic SDK (not raw boto3)

We use the official `anthropic` Python SDK with the `AnthropicBedrock` client:
- Same surface as the Anthropic API client (easy to switch to direct API for unreleased models)
- First-class tool use, streaming, prompt caching support
- Pydantic-friendly response types

### 6.2 IAM minimum

The AI service IAM role:
```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": [
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-opus-4-7*",
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6*",
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5*"
  ]
}
```

### 6.3 Prompt caching

Use `cache_control: {"type": "ephemeral"}` on:
- Schema summary block
- Glossary block
- Few-shot block (only the static prefix)

Target ≥90% cache hit. Monitor via `usage.cache_read_input_tokens` per response.

### 6.4 Failure modes

| Failure | Handling |
|---|---|
| Bedrock 429 | Exponential backoff, retry up to 3× |
| Bedrock 5xx | Same, then escalate tier (medium → strong as last resort) |
| Tool call validation fails | Re-prompt with error message inline (single retry) |
| Max hops exceeded | Final message: "I couldn't answer this. Sending to data team for review." Insert into `failed_query_reviews`. |
| Schema reference invalid | Validate server-side, return error to AI inside tool_result, let it self-correct (1 hop budget) |

---

## 7. Cube Layer

### 7.1 Deployment

Cube core in Docker, mounted volume for `schema/` directory. `docker-compose.cube.yml` runs Cube + cube-store + Postgres for storage.

### 7.2 Schema annotation rules (enforced by linter)

Every cube/measure/dimension MUST have:
- `description` — non-empty, ≥ 10 chars
- For measures: `meta.synonyms` — array of ≥ 1 alternative term
- For enum-like dimensions: `meta.enum_values` — exhaustive list
- For revenue/financial measures: `meta.ai_hint` — explicit semantics

CI fails the schema deploy if any of these are missing on cubes marked `meta.ai_facing: true` (most cubes).

### 7.3 Schema deploy flow

```
git push (PR merged)
    ↓
GitHub Action: lint schema → cubejs-cli validate
    ↓
Container build with new schema
    ↓
Cube rolling deploy on EKS
    ↓
Schema version bumped in app_db.workspaces.cube_schema_ref
    ↓
AI service invalidates schema cache for affected workspaces
```

### 7.4 Pre-aggregations

Every cube ships with at least one pre-agg (`originalSql + measures + dimensions(top-3) + timeDimension(daily)`). Refresh schedule per cube. Cube auto-routes queries to pre-aggs when possible.

---

## 8. Mongo→Postgres ETL

### 8.1 Stack

- **Temporal** (Python SDK, MIT) for orchestration
- **Meltano + tap-mongodb** (MIT + Apache 2.0) — Singer-based extractor with native CDC + bookmark support; chosen over Airbyte specifically because Airbyte is Elastic License v2 which restricts our commercial path
- **`motor`** (Apache 2.0, async MongoDB driver) for cases where we want a hand-rolled connector instead of Meltano
- **`asyncpg`** (Apache 2.0) for sink writes
- **DDL idempotent**: target tables managed by Alembic migrations

License audit: every dep above is permissive (MIT or Apache 2.0). Safe for commercial / hosted-SaaS use. See `LICENSES.md` for the full project audit.

### 8.2 Workflow

```python
@workflow.defn
class MongoToPostgresWorkflow:
    @workflow.run
    async def run(self, config: SyncConfig) -> SyncReport:
        last_cursor = await workflow.execute_activity(
            load_cursor, config.target_table, start_to_close_timeout=timedelta(seconds=10),
        )
        batch_no = 0
        while True:
            batch = await workflow.execute_activity(
                read_mongo_batch,
                args=[config, last_cursor],
                start_to_close_timeout=timedelta(minutes=5),
            )
            if not batch.docs:
                break
            transformed = await workflow.execute_activity(transform_batch, batch, config.mapping)
            await workflow.execute_activity(write_postgres_batch, transformed, config.target_table)
            last_cursor = batch.next_cursor
            batch_no += 1
        return SyncReport(batches=batch_no, ...)
```

### 8.3 Mapping config (per workspace)

Versioned in app_db, edited via UI in Phase 2. Sample mapping shown in §4.2 of PRODUCT_REPORT.

---

## 9. Authentication & Authorization

### 9.1 Auth flow (OIDC, Authlib)

1. User clicks "Login" → `/auth/login` redirects to OIDC provider (Okta/Google/Azure AD)
2. Callback to `/auth/callback` exchanges code for tokens
3. Backend mints internal JWT (`sub=user_id`, `wid=workspace_id`, `attrs=...`, 1h TTL)
4. Stored in `httpOnly` secure cookie + `Authorization: Bearer` header for API
5. Refresh via `/auth/refresh`

### 9.2 RLS policy injection

```python
def inject_rls(query: CubeQuery, user: User, workspace: Workspace) -> CubeQuery:
    policies = load_policies(workspace.id)
    for policy in policies:
        if policy.applies(query, user):
            query.filters.extend(policy.to_filters(user))
    return query
```

Policies stored in Cube schema as `accessPolicy` blocks; loader compiles into our `Policy` objects.

---

## 10. Observability

| Layer | Tool |
|---|---|
| Metrics | Prometheus (managed via AMP) + Grafana |
| Logs | Structured JSON → CloudWatch + indexed to OpenSearch |
| Traces | OTel SDK (Python) → AWS X-Ray |
| Errors | Sentry |
| AI quality | Custom dashboard reading from `chat_messages` (per-tier accuracy, token spend, cache hit) |

Standard tags on every metric/log: `service`, `workspace_id`, `tier` (for AI), `env`.

---

## 11. Local Development

### 11.1 docker-compose

`docker-compose up` starts:
- Postgres (app_db + warehouse_db)
- MongoDB (test source)
- Redis
- Cube core + cube-store
- Temporal
- LocalStack (S3 mock)
- All Python services (with hot reload via uvicorn `--reload`)

`make dev-frontend` runs Vite separately for fast HMR.

### 11.2 Required env

```
ANTHROPIC_BEDROCK_REGION=us-east-1
AWS_PROFILE=lumen-dev
APP_DB_URL=postgresql+asyncpg://lumen:lumen@localhost:5432/app
WAREHOUSE_DB_URL=postgresql+asyncpg://lumen:lumen@localhost:5432/warehouse
REDIS_URL=redis://localhost:6379
CUBE_API_URL=http://localhost:4000
CUBE_API_SECRET=...
JWT_SIGNING_KEY=...        # local dev only
LOG_LEVEL=DEBUG
```

### 11.3 Seeding

`make seed` runs:
1. Migrations (`alembic upgrade head`)
2. Inserts demo workspace + admin user
3. Loads sample warehouse data (orders, customers fixtures)
4. Deploys example Cube schema (`cube/schema/examples/`)

After seeding, `http://localhost:5173` shows a working app with dummy data.

---

## 12. Testing Strategy

| Level | Tool | Scope | When run |
|---|---|---|---|
| Unit | pytest | Pure functions, validators, prompt builders | Every commit |
| Integration | pytest + testcontainers | Service ↔ DB, service ↔ Cube | PR |
| AI eval | pytest -m eval | Golden NL→Cube set | Nightly + on AI changes |
| E2E | Playwright | Critical user flows (login, run query, AI chat) | Nightly |
| Load | k6 | Cube + AI service under burst | Weekly + before major release |

Coverage targets: 70% backend lines, 60% frontend (we don't chase 100%, focus on core flows).

---

## 13. CI/CD

**GitHub Actions** pipelines:

1. **PR pipeline** (every push):
   - Backend: ruff + pyright + pytest unit/integration
   - Frontend: eslint + tsc --noEmit + vitest
   - Cube schema validate
   - **AI eval (delta)**: only re-runs cases whose tagged areas changed
   - Build all Docker images (no push)

2. **Main pipeline** (on merge):
   - Full AI eval
   - Push images to ECR
   - Deploy to staging EKS via ArgoCD
   - Smoke tests
   - Manual approval → prod

3. **Nightly**:
   - Full AI eval
   - E2E suite
   - Dependency vulnerability scan

---

## 14. Tutorial / Documentation Plan

`docs/` shipped with the repo, also published to a `docs.lumen.example` site (later public).

| Doc | Audience | Outline |
|---|---|---|
| `getting-started.md` | New eng | Local setup in 15 min, `make seed`, click through demo |
| `architecture.md` | Eng + arch reviewers | High-level diagram, request flow, decision log |
| `data-team-onboarding.md` | Customer data team | The 5-step workflow from PRODUCT_REPORT §4.6 |
| `cube-schema-style.md` | Customer data team | Naming, description rules, `meta.*` fields |
| `ai-chat-tips.md` | Business users | How to ask good questions, what AI can/can't do |
| `embedding-guide.md` | Customer dev (Phase 4) | iframe + JWT signing |
| `api-reference.md` | API consumers | OpenAPI rendered via Redoc |
| `deployment.md` | SRE | EKS, RDS, secrets, scaling, observability |
| `runbook.md` | On-call | Top 20 incident playbooks |

In-app help: contextual `?` icons link to relevant doc sections.

---

## 15. Phase 0 + 1 Sprint Plan (months 0–9)

### Phase 0 — Foundation (M0–M3) — ✅ complete

**Sprint 0–1 (weeks 1–2)**: Infra
- ❌ AWS accounts (dev/staging/prod), Terraform skeleton — local-only so far
- ❌ EKS cluster, ArgoCD, RDS, Bedrock IAM — local-only
- 🟡 Repo skeleton, CI baseline — repo ✅, CI workflows ❌
- ✅ `docker-compose` local dev works end-to-end (`make seed` → app loads)

**Sprint 2–3**: First end-to-end
- ✅ API gateway with mock auth (real JWT, no OIDC yet)
- ✅ Query service forwards Cube queries, returns rows
- ✅ Cube schemas in `backend/cube/schema/` (incl. `examples/orders.yml`)
- ✅ Frontend workbook surface; drag a measure → chart

**Sprint 4–5**: AI hello-world
- ✅ AI service with Bedrock (and Anthropic, Alibaba, mock providers)
- ✅ Schema cache loader (`shared/schema_bundle.py`)
- ✅ SSE streaming wired end-to-end
- ✅ Manual eval harness

**Sprint 6**: Tool use + golden set
- ✅ Tool-use loop (`run_cube_query`, `ask_clarification`, `final_answer`)
- 🟡 Golden set has 30 questions — target 50 not yet hit
- 🟡 `failed_query_reviews` table + admin endpoint — table ✅, admin endpoint stubbed

**Phase 0 exit criteria**: ✅ a developer can log in, build a workbook, ask the AI a question, get a chart back.

---

### Phase 1 — Internal MVP (M4–M9) — 🟡 mostly complete

| Milestone | Item | Status |
|---|---|---|
| **M4** | Workbook (filters, save, 22 chart types) | ✅ |
| **M4** | Dashboard MVP (grid, tile) | ✅ |
| **M5** | Cross-filter | 🟡 logic in `Dashboard.tsx`, UX rough |
| **M5** | Drill-down workbook → field detail | ❌ |
| **M5** | Dashboard scheduling stub | ❌ |
| **M6** | Model editor (read+write YAML) | ✅ |
| **M6** | Git-based deploy with CI validation | ❌ no `.github/workflows/` |
| **M6** | Schema validation | ✅ (Cube `meta.compile`) |
| **M7** | `ask_clarification` tool | ✅ |
| **M7** | Conversation memory (chat_messages) | ✅ |
| **M7** | Tier escalation rules | ✅ |
| **M7** | Prompt caching ≥90% hit | 🟡 cache_control set; hit rate not measured |
| **M8** | RBAC roles in DB | ✅ |
| **M8** | RLS injection in query path | ✅ `query_service.inject_rls()` |
| **M8** | Audit log emit | 🟡 `audit.py` skeleton |
| **M8** | OIDC (Okta) | ❌ `auth_service/main.py` only `/health` |
| **M9** | Mongo→PG ETL | ❌ Temporal worker stub only |
| **M9** | 3 internal teams onboarded | ❌ |

**Phase 1 exit criteria**: ❌ not yet — OIDC, ETL, drill-down, and golden-set ≥85% remain.

---

## 16. Risks Carried Forward

(Detailed in PRODUCT_REPORT §5.3.) The two that change implementation order:

1. **AI accuracy plateau** — if at M5 we're below 75% on the golden set, freeze feature work and reallocate two weeks to prompt + few-shot tuning.
2. **Cube OSS gap** — if a needed feature is missing (e.g., a join type), file upstream first; if no movement in 4 weeks, fork and patch (we own the maintenance burden).

---

## 16.4 Visualization architecture (subagent + skill)

The visualizer subagent at `backend/services/ai_service/visualizer.py` is the canonical chart-picker. It reads:

- `cube_query` — the query that was executed
- result rows — for cardinality / type / skew profiling
- `schema_metadata` — per-cube-member info (format, label, kind) extracted from the YAML by `shared/schema_bundle.py::_extract_metadata`

It returns a `ChartSpec` with these fields:

```python
ChartSpec(
    type: ChartType,            # enum: big-number, bar, line, ..., empty (22 types)
    x, y, color, size: FieldRef | None,
    facet: FacetRef | None,
    title: str | None,           # auto-generated, declarative
    subtitle: str | None,        # period / filter context
    annotations: list[dict],     # threshold lines, event markers
    rationale: str,              # WHY this chart was picked
    confidence: float,           # 0–1; <0.7 may trigger LLM tiebreak
    alt_text: str | None,        # accessibility
)
```

**The Skill** (`.claude/skills/data-viz-standards/SKILL.md`) defines the rules. Every section maps to a specific code path:

| Skill section | Code |
|---|---|
| §1 The compass question (intent) | `select_visualization(intent_hint=...)` parameter |
| §2 Perceptual hierarchy (Cleveland-McGill) | Drives the bias toward bar over pie, position over color |
| §3 Decision tree | `_decide_chart_type(summary, intent_hint)` |
| §4 Per-chart rules (axis, sort, etc.) | `_build_chart_spec()` |
| §5 Color palettes | `frontend/src/components/chart/ChartSpec.ts::PALETTES` + `tailwind.config.js` |
| §6 Number formatting | `frontend/src/lib/format.ts::formatValue/formatExact/formatDate` |
| §7 Axis rules (zero-baseline) | `frontend/src/components/chart/PlotChart.tsx` per-chart-type Y-axis config |
| §9 Anti-patterns | `_decide_chart_type` rejects (e.g. donut → bar when slices > 6) |
| §11 Subagent contract | This module |

**Updates flow downhill**: change the skill → update the visualizer code → no frontend changes needed for the rules themselves (frontend just renders the ChartSpec).

---

## 16.5 Workspaces and Business Verticals

A workspace is the **unit of business-vertical isolation**. Every workspace owns its own Cube schema, data sources, AI grounding (schema summary, glossary, few-shot, eval set), users, permissions, and LLM preset. Switching workspace = switching the entire vertical context.

Implementation implications already wired into the codebase:
- `app_db.workspaces.cube_schema_ref` — git ref of the schema deployed to this workspace
- `chat_messages.workspace_id` — chat history is per-workspace
- `WorkspaceContext` propagated by the gateway carries `workspace_id` through every internal call
- `cube/cube.js` `driverFactory` (Phase 1+) selects the data source by `securityContext.workspace_id`
- Few-shot example selector (`ai_service/prompts/few_shot.py`) loads from the workspace's example pool
- `workspace_service` returns the schema bundle (summary + glossary) for AI grounding per workspace

Pre-built vertical templates ship under `backend/cube/schema/verticals/`:
- `tpch/` — wholesale / distribution (used by the local test fixture)
- (v2) `personal_lending/`, `b2b_saas_finance/`, `retail_ecommerce/`, `insurance/`, ...

A customer onboarding flow (Phase 1 sprint M9 onwards) lets an admin clone a vertical template into a new workspace, point it at their data sources, and refine the schema annotations to match their vocabulary.

---

## 16.6 v2 / v3 Roadmap — Multi-agent visualization (where LangGraph earns its keep)

The Phase 0/1 platform uses a **single-agent** loop:

```
NL → Claude (with tools) → run_cube_query → result rows → final_answer → visualizer (deterministic) → ChartSpec
```

The deterministic visualizer applies SKILL §3 rules and produces good charts for ~90% of queries. The remaining ~10% are quality issues a deterministic algorithm can't catch:

- **Aesthetic problems**: bars too dense for the chart width, labels overlap, color clashes with the workspace theme, dot-plot's zoom is too tight to read precisely
- **Encoding mistakes**: AI emits a query that maps poorly to its picked chart type (e.g. one row from a heatmap query → meaningless 1×1 cell)
- **Localization**: number formats (en-US `$1.2M` vs zh `120万` vs de `1,2 Mio. €`) the deterministic rule can't pick without user context
- **Insight gaps**: the chart shows the data but misses the obvious annotation ("Black Friday spike", "outlier worth flagging")

These are the cases where a **critic agent** in a multi-agent flow earns its complexity cost.

### v2 — The aesthetic critic agent (Phase 2/3)

```
                ┌─────────────────────────────────────────┐
                │  Stage 1: visualizer (deterministic)    │  v1, exists today
                │  rows + schema → ChartSpec              │
                └──────────────────┬──────────────────────┘
                                   │  candidate spec
                                   ▼
                ┌─────────────────────────────────────────┐
                │  Stage 2: critic (weak-tier LLM)        │  v2 NEW
                │  inputs:                                │
                │    - candidate ChartSpec                │
                │    - data shape summary                 │
                │    - rendered SVG snapshot (optional)   │
                │    - SKILL.md rules in system prompt    │
                │  outputs: pass | (issues, fix_plan)     │
                └──────────────────┬──────────────────────┘
                                   │
                  pass ─────────────┼───── fail
                       ▼            │      ▼
                  emit final        │   patch_spec(fix_plan)
                                    │      ▼
                                    └──────┘ (1 retry max)
```

**The critic checks**:
- Density / overlap risk (compute label-bbox-vs-bar-width ratio from data)
- Color contrast against the dark theme palette (skill §5)
- Zero-baseline rule conformance (skill §7.1) — bar charts must zero-base
- Caption necessity (abbreviated values without explanation)
- Title/subtitle readability
- Anti-pattern violations (skill §9)
- Period subtitle correctness when timeDim filter was applied

**Why this is the right LangGraph use case**:
- Multi-actor: visualizer + critic are different agents with different prompts and different system contexts
- Conditional edges: pass-or-retry routes the graph differently
- Checkpointable: critic decisions logged for offline review (training data for future deterministic rules)
- Output guarantees: a "broken" chart never reaches the user — critic gates the emission

### v2 — Adding the LangGraph dep (when, not if)

Trigger to add `langgraph`:
- Adding the critic agent (this section)
- AND adding agentic dashboard authoring (below)
- AND adding cross-session memory (Phase 3)

If only ONE of these lands, build it without LangGraph (50 LoC each).
If 2+ land in the same release, take the LangGraph dep — the abstractions start paying back.

### v3 — Agentic dashboard authoring (Phase 3/4)

> "Build me a dashboard about supplier health"

```
                ┌──────────────────────────────────────────┐
                │  Planner agent (strong-tier LLM)         │
                │  Decomposes intent into sub-questions:   │
                │    - top suppliers by inventory value    │
                │    - late shipment rate by supplier       │
                │    - supply cost trend                   │
                │    - supplier nation distribution        │
                └──────────────────┬───────────────────────┘
                                   │ N sub-questions
                                   ▼ (parallel branches)
                ┌──────────────────────────────────────────┐
                │  Executor agents (medium-tier, parallel) │
                │  Each runs the v1 NL→Cube loop           │
                └──────────────────┬───────────────────────┘
                                   │ N (cube_query, rows, ChartSpec)
                                   ▼
                ┌──────────────────────────────────────────┐
                │  Composer agent (medium-tier)            │
                │  - Picks 4-6 best for the dashboard      │
                │  - Decides grid layout (which is hero?)  │
                │  - Writes dashboard title + description  │
                │  - Suggests cross-filter relationships   │
                └──────────────────┬───────────────────────┘
                                   ▼
                            Dashboard saved
```

This is **textbook LangGraph territory** — 3 agents with different roles, parallel branches, conditional dispatch. Building this without LangGraph is possible but unwieldy.

### v3 — Cross-session memory (Phase 3+)

Move chat history from in-memory to persistent storage with semantic search:
- chat_messages already in app_db
- Add embedding column (use small embedding model)
- "What did we figure out about supplier X last week?" → vector search prior chat sessions for relevant context, prepend to system prompt

LangGraph's checkpointer abstraction is one path here, but a custom Redis-backed memory store works too. Decide based on whether the LangGraph adoption decision (above) has already been made.

### v2 — Pandas transform tool (Phase 2)

> **Source of truth**: the routing rule, tool description, and security checklist are
> formalized in `.claude/skills/data-transform/SKILL.md`. This section is the
> sprint-planning view; the skill is the operational view that the AI agent and the
> implementing engineer both read.

Cube is excellent at declarative aggregation/joins but weak at: rolling windows, cohort matrices, forecasting, custom statistical formulas, DataFrame-level reshape (pivot/melt). Today the AI can express anything Cube supports; everything else gets a "I can't do that" answer.

**Shape:**
- New `pandas_runner` service — isolated process, restricted execution environment
- AI gains a new tool: `run_dataframe_transform(cube_query, pandas_code)` — runner first executes the cube_query to get raw rows as a DataFrame, then applies the AI-authored transform code
- White-listed imports only: `pandas`, `numpy`, a small set of stat libs. Block `os`, `subprocess`, `socket`, `open`, `__import__`, file I/O
- Hard limits: CPU seconds, memory MB, timeout — kill on breach
- Default: feature-flagged off; admin opt-in per workspace

**Routing rule (must be in the prompt):**
> Default to Cube. Only use `run_dataframe_transform` when the question requires: rolling window, cohort/retention matrix, custom metric formula not expressible as Cube measure, reshape (pivot/melt), or non-trivial statistics. Never use it for plain aggregation Cube can already do.

**Why it matters for Omni parity:** Omni's "calculations" feature lets analysts write column expressions on top of query results. Pandas transform is the same idea, just AI-authored — it widens the answerable-question surface by a full tier without touching the Cube schema.

**Why we're deferring:** the security envelope (sandbox, resource limits, prompt-engineering the routing rule, golden-set additions) is a sprint of careful work, not a feature you slip into a 2-hour push. Owners should plan it as its own sprint with a security review gate before turning the flag on for any non-dev workspace.

### Decision rule (single source of truth)

| State | LangGraph adopted? |
|---|---|
| Phase 0–1 (current — single-agent NL→Cube) | ❌ No |
| Phase 2 with critic agent only | ⚠️ Build without; reassess |
| Phase 2 with critic + agentic features | ✅ Yes |
| Phase 3+ with multi-agent dashboard authoring | ✅ Yes |

Whoever picks up this work in Phase 2: read SKILL.md §11 + this section together, decide based on what's in flight that quarter.

---

## 17. Local Test Scheme (DuckDB-backed)

The repo ships with a self-contained local test scheme at `local_test/` that runs
the AI loop end-to-end **without AWS, without docker, without Postgres**.

### 17.1 Why DuckDB

DuckDB is an embedded columnar OLAP engine — exactly the workload we serve.
Its in-process Python binding makes it trivial to seed and query a synthetic
warehouse with one script. SQLite would also work but its row-oriented engine
poorly mirrors production analytics performance, defeating the purpose of a
realistic smoke test. Cube has native DuckDB driver support too, so the same
schema files work unchanged when later pointed at production.

### 17.2 Layout

```
local_test/
├── README.md                          # Quickstart for new engineers
├── generate_data.py                   # Synthetic orders/customers fixture
├── seed_duckdb.py                     # Builds warehouse.duckdb (orders vertical)
├── seed_tpch.py                       # Builds tpch.duckdb via DuckDB tpch extension
├── duckdb_query_runner.py             # Cube → DuckDB SQL for orders fixture
├── duckdb_query_runner_tpch.py        # Cube → DuckDB SQL for TPC-H (handles join graph)
├── run_local_test.py                  # The smoke test driver (--vertical tpch | orders)
└── data/                              # Gitignored: CSVs + .duckdb + schema/glossary text files
```

**Two verticals supported**:
- `--vertical tpch` (default) — TPC-H decision-support dataset, 8 cubes (Region, Nation, Customer, Orders, LineItem, Supplier, Part, partsupp). Generated locally via DuckDB's `tpch` extension. SF=0.1 ≈ 100MB; SF=1 ≈ 1GB.
- `--vertical orders` — the original synthetic orders/customers fixture (10K orders, 1K customers).

### 17.3 What gets exercised

1. **Tier abstraction** — `shared.llm_config` resolves `text_to_query` → medium, etc.
2. **Bedrock client** — real or mock (set via `--mock` flag / `USE_MOCK_LLM=true`).
3. **Tool-use loop** — `services.ai_service.stream.respond` runs the full loop.
4. **Cube query schema validation** — invalid AI-generated queries are rejected and the loop self-corrects.
5. **Cube query execution** — for the smoke test, `cube_runner.run_cube_query` is monkey-patched to call `duckdb_query_runner` directly. This skips Cube and the query_service HTTP hop, but still validates the query JSON contract works.
6. **Pass/fail evaluation** — each question carries an `expects` dict (required measures, dimensions). The runner checks the AI-generated query satisfies them.

### 17.4 Running it

```bash
# Once: install deps + seed
cd backend && uv sync && cd ..
python local_test/seed_duckdb.py     # creates data/warehouse.duckdb (~1MB)

# Smoke test (no AWS)
python local_test/run_local_test.py --mock

# Smoke test (real Bedrock)
AWS_PROFILE=lumen-dev python local_test/run_local_test.py
```

### 17.5 Mock LLM behavior

`shared.bedrock_client.BedrockClient` honors `USE_MOCK_LLM=true`. The mock
inspects the user message and returns a plausible `run_cube_query` tool call:

| Keyword in question | Mock returns measures |
|---|---|
| "revenue" / "sales" | `Orders.revenue` |
| "order" | `Orders.order_count` |
| (else) | `Orders.revenue` (default) |
| "country" | adds `Orders.country` dimension |
| "month" / "trend" | adds `created_at` time dimension with month granularity |

This is enough to validate the loop wiring without burning Bedrock tokens.

### 17.6 Promoting a smoke question to the golden set

If a smoke question reveals a real AI quality bug, copy it into
`backend/services/ai_service/eval/golden_set.yaml` with full expected fields,
so it becomes a permanent regression test.

---

## 18. What This Plan Does NOT Cover (yet)

- Phase 2/3/4 detailed sprints (will write at end of Phase 1)
- Embedding SDK design
- Mobile/responsive breakpoints (covered by Tailwind defaults; design pass in Phase 2)
- Pricing/billing implementation
- Customer support tooling
- SOC 2 control mapping (Phase 3 work)

---

## 19. Omni Parity Backlog (Phase 2) — **superseded by §22**

> This section is retained for historical context. The authoritative
> parity matrix is **§22** (656-page Omni docs crawl + Looker open-source
> survey, organised into 7 sprints A–G). When in doubt, follow §22.

Goal: a Lumen workbook + dashboard should let an analyst do everything they can do in Omni, with the AI layer as our differentiator. Audit done 2026-04-27 against `docs.omni.co/showcase` and adjacent docs.

### 19.1 The 10 highest-leverage parity items (ranked by impact / effort)

| # | Capability | Status | Why it matters | Where it lands |
|---|---|---|---|---|
| 1 | **Markdown viz primitive** with `{{result.path}}` bindings, Mustache iterators, `<Sparkline>` / `<ChangeArrow>` components | ✅ v0 (2026-04-27) | Almost every Omni showcase pattern (KPI tile, metric tree, repeating waffle, calendar heatmap, cohort table, etc.) is built on this one primitive. Cheapest single feature with the biggest "looks like a real BI tool" payoff. | `frontend/src/components/chart/MarkdownTile.tsx` + `markdown` ChartType + `template` field on ChartSpec. Components support: `{{path}}` (escaped), `{{= path}}` (raw), `{{path\|format}}`, `{{#each rows}}`, `{{#if path}}`, `<Sparkline data="rows.field"/>`, `<ChangeArrow value="..." goodWhen="up\|down"/>`. v0.5 will add: `<Bar value width/>`, color theming, light/dark palette tokens. |
| 2 | **Right-rail viz settings panel** — chart selector, mark per-series override, stacking modes (stack/group/overlay/100%), labels tab, tooltip tab (per-field), analytics tab (moving avg, trend line), point interpolation, line styling | 🟡 chart selector exists in workbench; rest ❌ | Everyone evaluating the tool clicks here within 30 seconds of opening a chart. | `frontend/src/components/workbench/VizSettingsPanel.tsx` (new); extend `ChartSpec.ts` with `series[i].mark`, `tooltip.fields`, `analytics.{movingAverage,trendline}`, `interpolation` |
| 3 | **Small multiples / faceting as first-class** | 🟡 visualizer can return `small-multiples-line`; UI control to opt-in ❌ | Tufte's "at the heart of visual reasoning is the comparison" — and Omni notably *doesn't* do this well, so we get a real differentiator. | Add `multiples` field to `ChartSpec`; render via Plot's `fx`/`fy` channels; right-rail toggle |
| 4 | **Cross-tile cross-filter with selected/dimmed feedback** | 🟡 cross-filter logic in `Dashboard.tsx`; visual feedback ❌ | Distinguishes a real dashboard from a wall of static images. | Extend `Dashboard.tsx` filter context; emit `selection` events from `PlotChart` |
| 5 | **Drill paths from data point** (click a bar/cell → opens workbook scoped to that filter) | ❌ | Standard expectation; without it the dashboard is a dead-end. | New route `/workbook/new?from_dashboard=...&filter=...`; click handler in `PlotChart` |
| 6 | **Per-tile inspect** (SQL, cache status, query timing) + **dashboard performance profiler** | ❌ | First thing every data engineer asks for. | Add `/internal/queries/run` to also return `meta.{sql, cache_hit, ms}`; UI panel `InspectChart.tsx` |
| 7 | **Topics layer** over the semantic model — per-topic field whitelisting, RLS scope, AI-tool restriction (`ai_chat_topics`) | ❌ | Lets us ship one workspace serving multiple internal teams without leaking each other's fields. | Add `topics:` block to Cube schema YAML; wire `topic_id` into ai_service tool definition |
| 8 | **Field switchers + multi-field pickers** as a dashboard filter type | ❌ | Quick way to turn one dashboard into N — much higher leverage than building N dashboards. | Extend filter schema with `kind: field_switcher`, `targets: [...]` |
| 9 | **AI Summary tile** — per-tile auto-narrated description | 🟡 `critic.py` exists; not wired | Once the visualizer + critic are integrated, this is mostly free. | Wire `critic.py` into stream loop; surface as a tile mode `narrate-result` |
| 10 | **MCP server** — expose `getData`, `selectModel`, `searchDocs` as MCP tools so external Claude/Cursor/ChatGPT clients can query Lumen | ❌ | Cheap, big external-developer signal. | New `services/mcp_server/main.py` thin wrapper over query_service + workspace_service |

### 19.2 Right-rail viz settings — full target spec

Match Omni's right-rail layout but layered on Plot. Settings cascade: **overall → axis → per-series**.

**Overall tab**:
- Mark family selector: bar, line, area, scatter, heatmap, big-number, table
- Stacking mode: none / group / stack / stack-100% / overlay
- Color palette: select from `PALETTES`
- Sort: auto / by measure asc/desc / by dimension order

**Axis tab** (per X / per Y):
- Title, format (number/percent/currency/date), grid lines on/off
- Zero baseline lock (forced on for bar; toggle for line)
- Tick density
- Dual-Y opt-in (with a warning per skill rule R13)

**Series tab** (per measure):
- Mark override (a series in a bar chart can be a line)
- Color override
- Line style: solid / dashed / dotted; thickness; opacity; points on/off
- Interpolation: linear / monotone / step / step-before / step-after

**Labels tab**:
- Show all labels / on hover / off
- Position: above / below / left / right / middle
- Decimals, prefix, suffix

**Tooltip tab**:
- Per-field show/hide checkbox list
- Cross-series mode (single hover shows all series at X) — on by default for multi-line

**Analytics tab**:
- Moving average (window N)
- Trend line (linear / poly)
- Threshold lines (with label)

### 19.3 Showcase-pattern parity (built on the Markdown primitive)

Implementing item #1 above unlocks ~25 patterns from Omni's showcase essentially for free, because they're all CSS+HTML over a result set. Track which we've built:

| Pattern | Built? | Skill rule |
|---|---|---|
| KPI with sparkline + change arrow | ❌ | Tufte sparkline rules (R8) |
| Metric tree | ❌ | Layout via CSS grid |
| Cohort table (12-month, lookback offsets) | ❌ | `PIVOTOFFSET`-style calc support needed first |
| Repeating pie / waffle (small multiples) | ❌ | Use our small-multiples instead — better than HTML iterator |
| Calendar heatmap | ❌ | Plot supports this natively → don't markdown-fake it |
| Card grid / criteria checklist | ❌ | — |
| Colored progress bars | ❌ | Few's color rule (R10) |
| KPI table with conditional colors | ❌ | — |
| Dumbbell plot | ❌ | Plot has `link` mark — use it natively |
| Gauge / thermometer / honeycomb | ❌ Skill discourages these (chartjunk per R6) |
| Symmetric funnel | ❌ | Use our small-multiples |
| Table with in-cell tiny bars | ❌ | Worth doing — useful, low chartjunk |

Decision: implement the **Markdown viz primitive** for layout patterns (KPI tile, metric tree, card grid, in-cell bars, prose readout) and use **native Plot** for any pattern that's actually a chart (heatmap, dumbbell, small multiples, sparkline). Don't build the Omni anti-patterns (gauge, thermometer, honeycomb).

### 19.4 Modeling-layer parity

| Item | Status | Notes |
|---|---|---|
| YAML semantic model (views/measures/dims/joins) | ✅ | via Cube |
| Topics (UI curation layer) | ❌ | see 19.1 #7 |
| `ai_context` annotations on fields (synonyms, hints) | 🟡 | examples/orders.yml has `meta.ai_hint`; not propagated into prompt yet |
| Promote workbook calculation → model | ❌ | Big lift — needs a calc DSL |
| Content Validator (pre-deploy ref check) | ❌ | Cube can do schema-compile; surface in UI |
| Local model dev (CLI) | ❌ | Editor is in-app only |

### 19.5 AI feature parity

| Item | Status | Notes |
|---|---|---|
| Standalone chat agent | ✅ | `ChatPanel.tsx` |
| Workbook-scoped agent | 🟡 | chat is workspace-scoped, not workbook-scoped |
| Dashboard-tile-scoped agent (click a tile → conversation about that tile) | ❌ | High value, low effort once context plumbing exists |
| Modeling agent (proposes YAML edits) | ❌ | Phase 2.5 |
| Learn-from-conversation (one-click promote a clarification → permanent `ai_context`) | ❌ | Closes the agent-improvement loop |
| AI forecasting (NL → forecast on time series) | ❌ | Use `prophet` or `statsforecast` Python lib in pandas_runner |
| AI visualizations (NL → ChartSpec on result) | ✅ | this is the visualizer subagent |
| AI Summary tile (auto-narrated chart) | 🟡 | critic exists; wire it |
| Image-paste in chat | ❌ | Anthropic Claude supports this natively |

---

## 20. Quality Loops — RAG, accounts, feedback DB

The user request: stop the AI from regressing, give us a way to learn from what works, store user accounts and customizations.

### 20.1 RAG over successful Q→Query→Answer triples

**Why**: every successful AI run is training data we're throwing away. Cube schemas are stable, but the *mapping from English to query shape* is the hard part — and we have a stream of correct examples flowing through the system.

**Storage**: new Postgres table `query_examples`:

```sql
CREATE TABLE query_examples (
  id              UUID PRIMARY KEY,
  workspace_id    UUID NOT NULL REFERENCES workspaces(id),
  question_raw    TEXT NOT NULL,                  -- the user's original phrasing
  question_norm   TEXT NOT NULL,                  -- LLM-rewritten "canonical" form for retrieval
  question_embed  VECTOR(1536),                   -- pgvector
  cube_query      JSONB NOT NULL,                 -- the tool input that worked
  generated_sql   TEXT,                           -- snapshot
  chart_spec      JSONB,                          -- final visualizer output
  rationale       TEXT,                           -- LLM's own explanation, post-hoc
  comments        TEXT,                           -- human-curated note (optional)
  source          TEXT NOT NULL CHECK (source IN ('user_accepted','golden_set','operator_curated')),
  vertical        TEXT NOT NULL,                  -- tpch, saas_finance, ...
  created_at      TIMESTAMPTZ DEFAULT now(),
  upvotes         INT NOT NULL DEFAULT 0,
  downvotes       INT NOT NULL DEFAULT 0
);
CREATE INDEX query_examples_embed_idx ON query_examples USING hnsw (question_embed vector_cosine_ops);
CREATE INDEX query_examples_workspace_idx ON query_examples (workspace_id, vertical);
```

**Capture path**:
- After a chat exchange where the user clicks "thumbs up" or accepts the chart without complaint within N seconds, write a row with `source='user_accepted'`.
- A weekly cron promotes high-upvote, never-downvoted examples to `source='operator_curated'`.
- Golden-set entries are mirrored as `source='golden_set'`.

**Retrieval at query time**:
1. Embed the incoming question using the medium-tier provider (or a small local model — TBD).
2. Cosine-search top 5 from the same workspace + vertical, filtered to `downvotes < 2`.
3. Inject those 5 into the system prompt as **inline few-shot**, replacing the static few-shot when scores are above a threshold.
4. Cache by `(workspace_id, hash(question_norm))` so repeat questions skip retrieval.

**Why this beats blindly more few-shot**: static few-shot is a frozen 5–10 examples; RAG few-shot scales with usage and adapts to the workspace's actual question distribution.

**Implementation order**:
1. Add `pgvector` to docker-compose.
2. Add the migration + repository in `shared/`.
3. Capture path: modify `stream.py` to emit a `query_examples` row on `final_answer` if no clarifications were needed.
4. Embedding provider: add `EmbedProvider` to `shared/llm_providers/` (Bedrock Cohere or Anthropic does not embed → use Voyage or a local model).
5. Retrieval path: in `prompts/system.py` builder, swap `few_shot.select(...)` for `rag.select(question, workspace_id, vertical, k=5)`.

**Eval gate**: golden-set accuracy must improve, not regress, when RAG is enabled. Run twice, RAG-on vs RAG-off, in CI nightly.

### 20.2 User accounts table (with credentials)

We currently auth via mock JWT. To support real signup before OIDC ships, add a credentials table:

```sql
ALTER TABLE users
  ADD COLUMN password_hash TEXT,                  -- argon2id, NULL if SSO-only
  ADD COLUMN password_set_at TIMESTAMPTZ,
  ADD COLUMN last_login_at TIMESTAMPTZ,
  ADD COLUMN totp_secret_encrypted BYTEA;         -- NULL = no MFA

CREATE TABLE user_sessions (
  id              UUID PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id),
  refresh_token_hash TEXT NOT NULL,
  user_agent      TEXT,
  ip              INET,
  expires_at      TIMESTAMPTZ NOT NULL,
  revoked_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX user_sessions_user_active_idx ON user_sessions (user_id) WHERE revoked_at IS NULL;
```

**Endpoints** (extend `services/auth_service`):
- `POST /auth/signup` — email + password (argon2id)
- `POST /auth/login` — sets refresh-token cookie, returns access JWT
- `POST /auth/refresh`
- `POST /auth/logout` (revokes session)
- `POST /auth/totp/enroll`, `POST /auth/totp/verify`

Use `argon2-cffi`. Block passwords < 12 chars. Don't roll a new auth model — copy FastAPI-Users patterns.

When OIDC eventually lands, password auth stays as the local-dev/early-adopter path; SSO becomes the default for paying customers.

### 20.3 User-customizable persistence

**Tables** (new):

```sql
CREATE TABLE saved_charts (
  id              UUID PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id),
  name            TEXT NOT NULL,
  cube_query      JSONB NOT NULL,
  chart_spec      JSONB NOT NULL,
  is_pinned       BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE user_settings (
  user_id         UUID PRIMARY KEY REFERENCES users(id),
  theme           TEXT DEFAULT 'light',           -- light/dark/system
  default_workspace_id UUID REFERENCES workspaces(id),
  number_format   TEXT DEFAULT 'en-US',           -- locale tag
  timezone        TEXT DEFAULT 'UTC',
  ai_provider_pref TEXT,                          -- override workspace LLM preset
  preferences     JSONB DEFAULT '{}'::jsonb       -- the catch-all bag
);
```

The existing `workbooks` and `dashboards` tables already cover "user-saved analysis" — `saved_charts` is for the lighter "I just want to bookmark this one chart" workflow that doesn't justify a full workbook.

### 20.4 Feedback database (closing the eval loop)

**Storage** — extend the existing `failed_query_reviews` table:

```sql
ALTER TABLE failed_query_reviews
  ADD COLUMN kind TEXT NOT NULL DEFAULT 'execution_error'
    CHECK (kind IN ('execution_error', 'wrong_answer', 'wrong_chart', 'slow', 'unclear', 'other')),
  ADD COLUMN user_comment TEXT,
  ADD COLUMN reported_by UUID REFERENCES users(id),
  ADD COLUMN expected_chart_type TEXT,            -- e.g. user said "should be a bar chart"
  ADD COLUMN cube_query_at_failure JSONB,
  ADD COLUMN chart_spec_at_failure JSONB,
  ADD COLUMN screenshot_url TEXT;                 -- S3 key
```

**Capture flow**:
1. Every chart in the chat panel gets a small "👎 Not what I wanted" affordance + free-text comment box.
2. Submitting writes a row with `kind='wrong_chart'` (or whichever the user picks).
3. The chat session ID + message ID are stored, so we can reconstruct the full conversation.

**Review workflow** (weekly):
1. `/admin/failed-queries` (need to actually build this) lists the past week's reports grouped by kind.
2. Operators triage each: `wont_fix` (user error), `triaged` (acknowledged), `fixed` (a follow-up commit references this row's ID).
3. When marking `fixed`, the operator MUST attach a golden-set entry that would have caught this case. This is the gate that turns one-off fixes into permanent regression coverage.

**Metric**: track `fix_rate` and `recurrence_rate` per workspace per week. If a workspace's `wrong_chart` rate stays above 5% for two weeks, freeze feature work and dedicate a sprint to that vertical.

### 20.5 New `pgvector` + tooling deps

Add to `backend/pyproject.toml`:

```toml
"pgvector>=0.3.0",
"argon2-cffi>=23.1.0",
"voyageai>=0.2.0",        # or sentence-transformers for local
"prophet>=1.1.5",         # AI forecasting (Phase 2)
```

Add to docker-compose: replace `postgres:16` with `pgvector/pgvector:pg16`.

---

## 21. Tutorials We Owe

The user just told us they don't know how to: (a) configure a data source, (b) build a Cube per table, (c) participate in the eval/feedback loop. These are the docs we're missing. Each gets its own file under `docs/tutorials/`.

### 21.1 `docs/tutorials/01-add-a-data-source.md`
**Audience**: data team adding a new database to a workspace.
**Cover**:
- Where data sources are configured today: `config/secrets.local.yaml` → `data_sources:` keyed by ID; the workspace's Cube schema YAML references that ID via `dataSource:`. **There is no UI yet** — explicitly say so, and link the §19 backlog item that tracks adding one.
- The three supported flavors right now: Postgres, MongoDB (Mongo→PG ETL), DuckDB (local).
- Connection string format and the `health_check:` block.
- Verification: `make backend && curl :8000/api/v1/workspaces/<id>/schema-bundle` should return non-empty schema.
- Common mistakes: wrong workspace.cube_schema_ref, RLS policy that blocks all rows, host firewall.

### 21.2 `docs/tutorials/02-author-a-cube.md`
**Audience**: data analyst modeling a table.
**Cover**:
- File layout: one YAML per cube under `backend/cube/schema/verticals/<vertical>/<cube>.yml`.
- Anatomy: `name`, `sql_table`, `joins`, `dimensions`, `measures`, `meta` (synonyms, ai_hint, enum_values, viz_override).
- The minimum a measure needs to be AI-friendly: a `description`, a `meta.ai_hint` ("revenue net of discount"), and `meta.synonyms` for common phrasings ("sales", "GMV").
- Time dimensions: must have a `granularities` block listing supported `[day, week, month, quarter, year]`.
- Walk through one example end-to-end: take `customers.csv`, build `Customer.yml`, register it, ask the AI a question, verify it routes to the new cube.

### 21.3 `docs/tutorials/03-feedback-and-eval-loop.md`
**Audience**: anyone using Lumen who hits a wrong answer.
**Cover**:
- The 👎 button on every chart: what data goes in, where it ends up (`failed_query_reviews` row).
- The weekly review meeting: who attends, the queue link, the rule that every "fixed" needs a golden-set entry.
- How to add a golden-set entry yourself: `eval/golden_set.yaml`, run `make smoke` to verify it loads, the `expects` schema.
- How to read the eval dashboard (when we build it).

### 21.4 `docs/tutorials/04-customizing-charts.md`
**Audience**: end user who wants to change a chart's appearance.
**Cover**:
- The right-rail viz settings panel (once §19.2 ships).
- How chart picker decisions are made (link to data-viz-standards skill).
- "I want a grouped bar instead of multi-line" — the answer is the right-rail mark selector; until that ships, `chart_spec.type` can be edited in the JSON view.

### 21.5 `docs/tutorials/05-running-locally.md`
**Audience**: a new developer.
**Cover**:
- Already mostly in `README.md`; promote and expand.
- Specifically the **gotcha** documented in `CLAUDE.md`: services started from a different cwd will fail to find the DuckDB file. Show the `readlink /proc/<pid>/cwd` trick.

---

## 22. Omni + Looker deep parity matrix (Phase 2 master backlog)

**Source**: `/tmp/omni-deep-report.md` (1,067-line crawl of docs.omni.co covering 656 sub-pages) + `/tmp/looker-report.md` (765-line survey of looker-open-source repos and the LookML DSL). Crawled 2026-04-27.

This section supersedes §19 — it contains the full inventory, sorted into seven sprints. Each item carries:
- the vendor name verbatim
- our current implementation status (✅ / 🟡 / ❌)
- which sprint it lands in
- a one-line "what to build" so future-Claude can pick it up cold

**Sprint sizing**: each sprint is ~2 weeks of focused work. Larger items split across sprints.

### 22.1 Sprint A — AI grounding (the agent moat)

| Item | Vendor name | Status | What to build |
|---|---|---|---|
| `ai_context` field on cube/dim/measure | Omni | 🟡 | We have `meta.ai_hint`; rename or alias to `ai_context` to match Omni's verbatim term and use it as **primary** over our `description` |
| `synonyms` on every dim/measure | Omni | 🟡 | Already in `meta.synonyms`; ensure schema_summary serializer surfaces these |
| `sample_values` + `all_values` per dim | Omni | ❌ | New fields; render at most 8 values into the AI prompt next to the dim. For lending: `Customer.state` → US state codes |
| `sample_queries` per cube | Omni | 🟡 | Already in `meta.example_questions`; rename to match Omni; persist with `prompt`, `query`, `ai_context`, `exclude_from_ai_context` |
| **Skills** (named multi-step recipes) | Omni Agent Skills | ✅ v0 (2026-04-28) | `skills.yml` per vertical, parsed by `schema_bundle.py::_load_skills`, surfaced via `/api/v1/workspaces/{id}/schema-bundle` and rendered as quick-action cards in chat EmptyState. 6 skills shipped for the lending vertical. Next: skill click → `prompt + " " + user_input` form, and `input` flag for prompted skills |
| **Learn-from-conversation** | Omni | ❌ | Brain-icon affordance on each AI response → modal with proposed YAML diff (description / synonyms / new sample_query). Writes to git (Phase 1 sprint 6 did the table; this is the UI + writer). The single biggest agent-improvement loop |
| **Auto-learn** | Omni | ❌ | Background trigger: after N user clarifications on the same field, surface a "want to teach me?" toast |
| Prompt cache hit-rate ≥ 90% | — | 🟡 | Cache_control set; per-provider counters in `ProviderRegistry.record_usage()` aggregated through `stream.py`; surfaced on `/providers` as `stats.cache_hit_rate` (2026-04-28). 90% target requires real Bedrock traffic to confirm |
| RAG over successful Q→Query→Answer | §20.1 | ❌ | pgvector + `query_examples` table. See §20.1 for full schema |

**Sprint A exit criteria**: golden-set accuracy +5% vs baseline; one cube authored end-to-end with skills + sample_queries + ai_context.

### 22.2 Sprint B — Visualization & layout (the "polish" sprint)

The Markdown viz primitive is ✅ done (v0). What's missing is the **right-rail config panel** and the showcase patterns built on top.

| Item | Vendor name | Status | What to build |
|---|---|---|---|
| Right-rail viz settings panel | Omni | ❌ | Tabs: Overall / X-axis / Y-axis / Color / Series / Labels / Tooltips / Analytics. See §19.2 for full spec |
| Per-series mark override (line+bar combo) | Omni | ❌ | Extend `ChartSpec` with `series[i].mark` |
| Stacking modes: stack / group / overlay / 100% | Omni | 🟡 | `stacked-bar` and `stacked-bar-100` exist; need UI selector |
| Dual axes (with R13 warning per skill) | Omni | ❌ | Per-series `axis: 'left' \| 'right'` |
| Per-field tooltip toggle | Omni | ❌ | `tooltip: { fields: [...], hidden: [...], crossSeries: bool }` |
| Moving-average / trend line | Omni Analytics tab | ❌ | `analytics: { movingAverage: {window: N}, trendline: {kind: 'linear'\|'poly'} }` |
| Point interpolation (linear / monotone / step / step-before / step-after) | Omni | ❌ | `interpolation: 'linear'\|'monotone'\|...` field |
| Line styling (dashed / dotted / thickness / opacity) | Omni | ❌ | `seriesStyle: {dash, thickness, opacity, points}` |
| Reference lines on X / Y | Omni | ❌ | `axes.x.referenceLines: [{value, label, color}]` |
| **Small multiples / faceting as first-class** | (Lumen edge — Omni fakes it) | 🟡 | `small-multiples-line` exists; expose `multiples` field on ChartSpec; add right-rail toggle |
| Custom palette picker + paste-bulk-hex | Omni | ❌ | Admin UI; per-tile override |
| Application + document themes (CSS-in-themes) | Omni | ❌ | New `themes/*.json` + dark-mode tokens in Tailwind config |
| Showcase patterns from Markdown viz: 12 starters | Omni showcase | ❌ | Calendar heatmap, KPI w/ sparkline, metric tree, card grid, cohort table, dumbbell, table-with-tiny-bars, gauge, KPI conditional colors, KPI table, data readout, record lookup |
| AI summary tile | Omni | 🟡 | `critic.py` exists; surface as a dashboard tile mode `narrate-result` |
| AI subtitle/description on chart | Omni | ❌ | Star icon on chart → "Let AI write subtitle" |
| Custom error / empty-results message | Omni | 🟡 | `EmptyState` exists; add per-spec override |

### 22.3 Sprint C — Modeling DSL parity

Cube's YAML is leaner than LookML. These are the gaps to close so power-users feel at home.

| Item | Vendor name | Status | What to build |
|---|---|---|---|
| `value_format` / `value_format_name` (Excel-style format strings) | LookML / Omni | ❌ | Replace our 3-value enum (`number/currency/percent`) with full Excel-style strings: `#,##0.00`, `[$$-409]#,##0`, `0.0%;(0.0%)` |
| `link` / `links` (templated drill URLs) | LookML / Omni | ❌ | Per-dim `links: [{label, url, icon}]` with Mustache. Click → opens in new tab |
| `drill_fields` / `default_drill_fields` / `drill_queries` | LookML / Omni | ❌ | Author-specified drill targets per dim/measure |
| `group_label` / `group_item_label` / `view_label` | LookML / Omni | ❌ | Hierarchical grouping in field picker |
| Named `set` (reusable field group) | LookML | ❌ | `sets:` block on view/topic |
| `parameter` (true user-input, not a filter) | LookML | ❌ | First-class typed input bound to `${parameter.foo}` in SQL templates |
| `access_grants` / `access_filters` | LookML / Omni | 🟡 | RLS injector exists (`query_service.inject_rls()`); add YAML-level grants/filters and policy compilation |
| `html` template per dimension | LookML | ❌ | Per-dim `markdown:` (Mustache HTML) — already partly covered by our Markdown viz primitive; surface at field level too |
| **Liquid subset** (`{{ user.* }}`, `{{ value }}`, `{{ _filters['x'] }}`) | LookML | ❌ | Mustache + a small set of macros |
| `extends` (view inheritance) | LookML / Omni | ❌ | `extends: [BaseView]` keyword, deep-merge dims/measures |
| `materialized_query` (aggregate awareness) | Omni | ❌ | Cube auto-routes to a pre-aggregated table when query shape matches |
| `dynamic_top_n` (auto-generate top-N filtered dims) | Omni | ❌ | Compute top-N at query time and synthesize a dim for display |
| `level_of_detail` (LOD) | Omni | ❌ | Tableau-style fixed-grain calc |
| `bin_boundaries` / `groups` (CASE-like bucketing) | Omni | ❌ | YAML-declared bucketing |
| `convert_tz` / `timeframes` per dim | Omni | ❌ | Already partly via our `granularities`; add explicit TZ control |
| **Symmetric aggregates** | Omni | ❌ | Critical for join fan-out safety. SUM(x) over a fan-out join must use DISTINCT-aware logic |
| Topics layer | Omni | ❌ | Curated slice of cubes/dims with own `ai_context`, `ai_fields`, `access_filters`, `default_filters`, `cache_policy` |
| Three-layer model (schema / shared / workbook) | Omni | ❌ | Today we have one layer. Add per-workbook overrides that diff against shared |
| **Content Validator** | Omni | ❌ | Pre-deploy: find every workbook/dashboard referencing a renamed/deleted field. Bulk-fix |
| **Workbook Inspector** (SQL / structure / vis YAML) | Omni | 🟡 | "View SQL" exists; add structure tree + vis YAML copy-paste |
| **Branch Mode** (model + content branches) | Omni | ❌ | Git-like branches that include both YAML model and content drafts |
| Promotion (workbook → shared model) | Omni | ❌ | Visual diff + selective promotion of new dims/measures |

### 22.4 Sprint D — Calculations DSL (Excel-style)

Today users have no calc layer. Omni and Looker both ship rich ones. **Tier-1 priority**.

| Item | Vendor name | Status | What to build |
|---|---|---|---|
| Math functions (~50) | Omni | ❌ | ABS, AVG, AVERAGEIFS, CEIL, COUNT, COUNTIF, COUNTIFS, MAX/MAXIFS, MEDIAN, MIN/MINIFS, MOD, ROUND, SUM/SUMIF/SUMIFS, STDEV, VAR, CORREL, COVAR, RANK, OMNI_RANK, ... |
| Date/time (~16) | Omni | ❌ | DATE, DATEDIF, DAY, DAYS, EOMONTH, MONTH, NETWORKDAYS, NOW, TODAY, WEEKDAY, WEEKNUM, YEAR ... |
| Text (~18) | Omni | ❌ | CONCAT, EXACT, FIND, LEFT, LEN, LOWER, MID, REPLACE, RIGHT, SUBSTITUTE, TRIM, TEXT, UPPER ... |
| Logic (~13) | Omni | ❌ | AND, BITAND, BITOR, BITXOR, IF, IFERROR, IFNA, IFS, ISBLANK, ISNUMBER, NOT, OR |
| Position functions | Omni — D | ❌ | INDEX, MATCH, **PIVOT**, **PIVOTINDEX**, **PIVOTOFFSET**, **PIVOTROW**, SWITCH, ROW, VLOOKUP, **XLOOKUP** |
| AI functions in formulas | Omni — D | ❌ | AI_CLASSIFY, AI_COMPLETE, AI_EXTRACT, AI_SENTIMENT, AI_SUMMARIZE — call LLM per row |
| Quick calculations | Omni | ❌ | One-click % of row/col, running total, period-over-period |
| AI-generated calculations | Omni — D | ❌ | Plain-English → formula via LLM |
| Promote calc → model | Omni — D | ❌ | One-click write back to YAML measure |
| Filtered measure inline | Omni | 🟡 | Cube measures support `filters:`; add UI to author from result panel |
| Bin/group inline | Omni | ❌ | Click-bucket numeric to named bands |

### 22.5 Sprint E — Dashboard layout & filters

| Item | Vendor name | Status | What to build |
|---|---|---|---|
| **Advanced layout containers** (Grid + Stack with direction/gap/padding/wrap/align) | Omni | 🟡 | `react-grid-layout` covers Grid; add Stack + nested containers |
| **Pages** (up to 15 per dashboard, with auto-nav, slug `Key`) | Omni | ❌ | New `dashboard.pages: [{key, title, layout}]` |
| Filter as button toggles (single-select string) | Omni | ❌ | UI variant for ≤6 values |
| **Field control** (swap dim/measure across tiles) | Omni | ❌ | New filter kind `field_switcher` |
| Multi-field pickers | Omni | ❌ | One filter → different fields per tile |
| **Time control** (timeframe + granularity switcher) | Omni | 🟡 | Time-range select exists; add granularity |
| Parent control (cascading) | Omni | ❌ | A → B → C dependent dropdowns |
| **Cross-filter highlight + dim mode** | Omni | 🟡 | Filtering exists; visual selected/dimmed feedback ❌ |
| **Calculated-field filter** | Omni | ❌ | Filter expressed as a calc, not just `dim = value` |
| Drill paths from data point → workbook | Omni | ❌ | Click bar/cell → opens workbook scoped to that filter |
| **Per-tile inspect** (SQL + cache + timing) | Omni | ✅ (2026-04-28) | `query_service` stamps `meta.{ms, rows, cache_hit, backend, vertical}`; `runQuery` typed; ResultView → ChartActions surfaces an "Inspect" button → 4-stat panel (Time / Rows / Cache / Backend). View SQL still available |
| **Performance Profiler** | Omni | ❌ | Per-tile load times across whole dashboard |
| Hidden tiles + XLOOKUP | Omni — D | ❌ | Tile renderable but hidden; referenceable from formulas |
| Snapshots with parameters | Omni — D | ❌ | Named saved view of parameterized state |
| AI subtitle / description assist | Omni — D | ❌ | Star icon → AI fills tile copy |
| Custom error / empty message per tile | Omni | ❌ | `chart_spec.fallback: { message, suggested_filters }` |
| Multi-page navigation tabs | Omni | ❌ | Auto-emitted when ≥2 pages |

### 22.6 Sprint F — Embed & MCP

| Item | Vendor name | Status | What to build |
|---|---|---|---|
| **Embed events JS protocol** (the 12 emit + 3 receive list verbatim) | Omni | ❌ | Implement under EXACT names: `size`, `status`, `error`, `page-changed`, `dashboard:filters`, `dashboard:filter-changed`, `dashboard:download`, `dashboard:tile-download`, `dashboard:tile-drill`, `ai:chat-start`, `sidebar:open`, `navigation:home` (host-bound: `navigate`, `dashboard:filter-change-by-url-parameter`, `appearance:mode`). Customers can swap providers later |
| Standard SSO (signed iframe URL) | Omni | ❌ | HMAC URL signing |
| 2-step SSO (POST → URL) | Omni — D | ❌ | For sensitive `userAttributes` |
| Embed URL parameter set (full ~22) | Omni | ❌ | `accessBoost`, `connectionRoles`, `customTheme`, `entity`, etc. |
| **Visualization-emitted events** (table cell, Markdown `<omni-message>`) | Omni — D | ❌ | Per-field config `Display: Link → URL: Embed event` |
| Vanity domains | Omni | ❌ | Wildcard cert + session validation |
| Create Mode (analytics-as-a-product) | Omni — D | ❌ | Multi-tenant content authoring inside embed |
| Embedded agent | Omni | ❌ | `<omni-chat>` web component |
| Branding | Omni | ❌ | Agent name, image, intro headline, prompt placeholder |
| **MCP server** (`pickModel`, `pickTopic`, `getData`, `searchOmniDocs`) | Omni | ❌ | New `services/mcp_server/main.py` |
| OAuth 2.1 + PAT auth on MCP | Omni | ❌ | Spec at `docs.omni.co/ai/mcp/authentication` |

### 22.7 Sprint G — Telemetry, deliveries, ops

| Item | Vendor name | Status | What to build |
|---|---|---|---|
| **Self-model over usage** (`query_history`, `field_usage`, `ai_call_history`, `scheduled_plan`) | Looker `system_activity` / Omni audit logs | ❌ | A workspace named "Lumen Activity" exposing usage as cubes. Mine for few-shot examples |
| Audit logs (S3 / GCS) | Omni | ❌ | Structured emitter from `audit.py` to S3 |
| **Action hub** (3-endpoint contract: `/actions`, `/actions/{name}/execute`, `/actions/{name}/form`) | Looker | ❌ | Mirroring Looker spec gives free compatibility with their ecosystem |
| Schedules / deliveries (Email / Slack / Sheets / Webhook / S3 / SFTP) | Omni | ❌ | Cron + Mustache-templated payloads |
| Alerts (threshold breach) | Omni | ❌ | Same plumbing as schedules + condition |
| Cancel running queries | Omni | ❌ | `DELETE /api/v1/queries/{id}` |
| Cache policies + warming + requeryable cache | Omni | ❌ | `cache_policies:` model param; cron-driven warmer |
| Symmetric aggregates fan-out fix | Omni | ❌ | Critical for join correctness when joining to a "many" cube |
| Dynamic schemas / connection environments (dev/staging/prod) | Omni | ❌ | Pick warehouse per branch / user-attr |
| dbt deeper integration (exposures push, semantic-layer, environments) | Omni | ❌ | Tier-2 |
| Localization | Omni | ❌ | Tier-2 |

### 22.8 What we're explicitly NOT building (kill list)

Based on the deep crawl, these Omni features hit our "not worth it" bar:

- **Gauge / thermometer / speedometer** — chartjunk per skill R6. Reject in visualizer.
- **3D pies / 3D bars** — chartjunk per R6.
- **Snowflake semantic-views push / Databricks Unity push** — couples us to specific warehouses.
- **Slack Agent slash commands** — Tier-3.
- **Emoji mode for tabs** — cosmetic; punt.
- **Honeycomb categorical maps** — niche; revisit if a customer requests.

### 22.9 Tier-1 borrowables from Looker open-source

From `/tmp/looker-report.md`:

| Repo | What to borrow | Where it lands |
|---|---|---|
| `looker-open-source/components` | Density primitive, semantic color tokens, `LkFieldTree` field-picker pattern, viz adapters, filter expression mini-language | Sprint B (right-rail panel) + Sprint H (UI tokens) |
| `looker-open-source/looker-explore-assistant` | Multi-section prompt assembly: `# Documentation`, `# Format`, `# Metadata`, `# Examples`, `# Task` | `prompts/system.py` rewrite into named sections |
| `looker-open-source/extension-gen-ai` | Enum-keyed `PromptTemplateService` for distinct modes (`EXPLORE_QUERY`, `DASH_SUMMARIZE`, `EXPLORATION_OUTPUT`, `EXPLORE_VALIDATE_MERGED`) | Restructure our prompts/ as one module per mode |
| `looker-open-source/actions` | 3-endpoint action contract → free compatibility with Slack/Sheets/Salesforce/Jira plugins | Sprint G action hub |
| `looker-open-source/sdk-codegen` | Endpoint inventory we're missing: `/scheduled_plans`, `/render_tasks`, `/looks`, `/integrations`, format-negotiated `/queries/run/{format}`, `/system_activity` | API surface in Sprint G |

### 22.10 Sprint sequencing (recommended)

1. **Sprint H (NOW — UI/UX polish)**: §23 Tufte breathing-room pass on existing surfaces. Cheap, dramatic visual upgrade. *Always-on background work.*
2. **Sprint A (next 2 weeks)**: AI grounding — synonyms, sample_values, skills, learn-from-conversation, RAG. Highest agent-quality leverage.
3. **Sprint B (~2 weeks after)**: Right-rail viz settings panel + 12 Markdown showcase patterns.
4. **Sprint D (parallel with B)**: Calculations DSL — math/date/text/logic/position + AI functions.
5. **Sprint E**: Dashboard layout + filters + drill paths + per-tile inspect.
6. **Sprint C**: Modeling DSL parity — symmetric aggregates first, then `value_format`, `links`, `drill_fields`, topics, content validator.
7. **Sprint F**: Embed events + MCP server.
8. **Sprint G**: Telemetry self-model, action hub, deliveries, alerts.

---

## 23. UI/UX — Tufte breathing room (always-on)

> "The best designs are not designs at all. The best designs are simply data, with a thin layer of human judgment about how to spotlight what matters." — Tufte, paraphrased.

This isn't a sprint with an end date; it's a stance applied to every PR. The rules:

### 23.1 The compounding rules

1. **Whitespace is data**. Generous margins, never crowded. Plot's default 40 px margins are a floor, not a ceiling — for KPI tiles use 56 px, for chat-embedded charts use 48 px.
2. **Type scale = strict 1.25 ratio**. 12 / 14 / 16 / 20 / 24 / 32. No off-scale sizes. Never use sub-12 px text.
3. **Line height ≥ 1.5** for body, **≥ 1.3** for chart labels. Tighter is sloppy.
4. **One accent color per surface**. The neutral palette is 90% of the canvas; the accent (`#5B8FF9` per our palette) is reserved for the focal data point only.
5. **Erase tick marks the user doesn't need**. Plot's default tick density is fine for desktop; reduce by 30% on tile-mode renders.
6. **No drop shadows**. They're decorative ink.
7. **Numerals are tabular**. Use `font-variant-numeric: tabular-nums` everywhere a number is shown — KPIs, table cells, axis labels.
8. **Spacing rhythm**: 4 / 8 / 16 / 24 / 32 / 48 / 64. Tailwind's default scale is fine; just stick to those rungs.
9. **Borders before fills**. A 1 px border-bottom is enough to separate sections in 90% of cases.
10. **Empty states have personality**. Never an empty `<div>` — always a sentence and an action.

### 23.2 Concrete first pass (Sprint H — already underway)

- Chart titles: 16 px / weight 500 / 1.4 line-height; subtitle 13 px / weight 400 / muted; 16 px gap below
- BigNumber tile: value 32 px tabular-nums; label 12 px uppercase tracking-wide; padding 24 px
- Dashboard tile gutters: 16 px (current is sometimes 8 px)
- Chat bubble padding: 16 px sides, 12 px top/bottom; max-width 65ch for prose
- Workbench pill row: 8 px gaps; pill padding 6 px x 10 px
- Chart context menu: 4 px gaps between groups; 32 px row height
- Plot config defaults: marginTop 32, marginRight 24, marginBottom 32, marginLeft 48 (currently uneven)
- Dark-mode tokens: every accent has a `--accent-hover` and `--accent-muted` 6%/12% mix variant
- Table cells: 8 px vertical, 12 px horizontal padding; 1 px row borders only

### 23.3 Anti-patterns to grep-and-destroy

- `text-xs` (10 px) — replace with `text-[11px]` only when absolutely necessary, otherwise upsize
- `shadow-sm`, `shadow-md` etc. — review every usage; default to `border` instead
- `gap-1` (4 px) inside flex containers showing data — usually too tight
- Truncated bar y-axes (already enforced by R3 in skill, but spot-check chart_spec authoring code)
- `rounded-lg` on dashboard tiles — Tufte says no rounded corners on data surfaces; use `rounded-md` (4px) max

---

*End of plan. Update on every architectural decision; reference ADRs in `docs/adr/`.*
