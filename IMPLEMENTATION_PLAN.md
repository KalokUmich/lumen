# Lumen — Implementation Plan

> Companion to `PRODUCT_REPORT.md`. This document is the engineering bible: it converts product decisions into concrete API contracts, database schemas, build orders, and a working repo layout.
>
> **Mission**: Ship a lightweight, AI-native data platform on AWS in 24 months. Internal use first, external paying customers by Phase 4. Multi-provider LLM (Bedrock, Anthropic, Alibaba) with provider-agnostic tier abstraction.
>
> **Scope of this doc**: Phase 0 + Phase 1 (months 0–9). Later phases are sketched at the end.

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

### Phase 0 — Foundation (M0–M3)

**Sprint 0–1 (weeks 1–2)**: Infra
- AWS accounts (dev/staging/prod), Terraform skeleton
- EKS cluster, ArgoCD, RDS, Bedrock IAM
- Repo skeleton, CI baseline (this plan's structure)
- `docker-compose` local dev works end-to-end (`make seed` → app loads)

**Sprint 2–3**: First end-to-end
- API gateway with mock auth (real JWT, no OIDC yet)
- Query service: forwards a hardcoded Cube query, returns rows
- Cube deployed with `examples/orders.yml`
- Frontend: workbook surface, drag a measure → render a chart

**Sprint 4–5**: AI hello-world
- AI service: single Bedrock call (no tool use), tier=medium
- Schema cache loader
- SSE streaming wired end-to-end
- 5-question manual eval (no harness yet)

**Sprint 6**: Tool use + golden set
- Tool-use loop (`run_cube_query` + `final_answer`)
- 50-question golden set + pytest eval harness
- Failed query queue table + admin endpoint stub

**Phase 0 exit**: 3 internal users can log in, build a workbook by dragging fields, ask the AI a question and get a chart back.

---

### Phase 1 — Internal MVP (M4–M9)

**M4**: Workbook complete (8 chart types, filters, save), Dashboard MVP (grid, tile, no cross-filter)
**M5**: Cross-filter, drill-down, dashboard scheduling stub
**M6**: Model editor (read-only), git-based deploy, schema validation
**M7**: AI: ask_clarification, conversation memory, tier escalation, prompt caching tuned to >90% hit
**M8**: RBAC + RLS v1, audit log, OIDC integration (Okta sandbox)
**M9**: Mongo→PG ETL for one canonical pattern (flat docs), 3 internal teams onboarded

**Phase 1 exit**: 30 internal users, 50% WAU, AI accuracy ≥85% on golden set.

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

*End of plan. Update on every architectural decision; reference ADRs in `docs/adr/`.*
