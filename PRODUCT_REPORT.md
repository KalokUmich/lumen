# Lumen — Product Report & 24-Month Plan

> **Lumen** is a lightweight, AI-native data platform. Connect your databases, model your metrics in code, and answer business questions in natural language — with answers grounded in a governed semantic layer rather than free-form SQL guesswork.
>
> **Document version**: v1.0 · 2026-04-26
> **Author**: Architect

---

## 0. Executive Summary

### 0.1 Mission
Build a lightweight, AI-native data platform with four pillars — Semantic Model, Workbook, Dashboard, and AI Chat — that gives mid-sized companies a trustworthy way to ask their data questions in plain language and get answers they can act on.

### 0.2 Strategic Bet
We are not building from scratch. **Our moat is the AI layer and the user experience.** The semantic engine is built on top of [Cube OSS](https://github.com/cube-js/cube), saving 2–3 years of LookML-class abstraction iteration. The AI layer uses Claude through AWS Bedrock for industry-leading natural language understanding and structured output.

### 0.3 Scope (24 months)

| Capability | v1 | v2 |
|---|---|---|
| Semantic model (code-as-source-of-truth) | ✅ (built on Cube) | ✅ |
| AI: natural language → query | ✅ (Claude + Bedrock) | ✅ + agentic |
| Dashboard | ✅ (core chart types) | ✅ (full) |
| Workbook (spreadsheet-like exploration) | ⚠️ (simplified, pivot-table focused) | ✅ |
| SQL workbench | ✅ (data-team day-1 dependency) | ✅ |
| Embedded analytics | ❌ | ⚠️ |
| Excel-grid formula engine | ❌ (explicitly out of scope) | ⚠️ evaluate |
| Full RBAC + RLS | ✅ (basic) | ✅ |
| Scheduled reports / alerts | ❌ | ✅ |
| Git-based model versioning | ✅ (from v1) | ✅ |

### 0.4 Explicit non-goals

- **No Excel-grade formula engine.** Building a full spreadsheet-style formula engine that compiles to SQL is a multi-year effort that distracts from our differentiation. Pivot tables cover the majority of use cases without it.
- **No in-house query engine / OLAP cache layer.** We rely on Cube pre-aggregations + Postgres / DuckDB. Reinventing this layer adds years of engineering for no user-visible benefit.
- **No mobile app.** Responsive web only.
- **No white-label or multi-region deployment** until v2.

### 0.5 Top-line numbers
- **Team**: 12 engineers + 3 design/PM = **15 FTE**
- **Timeline**: 24 months = Phase 0 (3mo) → Internal MVP (6mo) → Internal GA (6mo) → External Beta (6mo) → Commercial v1 (3mo)
- **AWS cost estimate**: ~$8K/mo internal phase, ~$25K/mo external beta
- **Confidence**: internal-usable — 75%; external beta with 5–10 paying customers — 50%; competitive in head-to-head enterprise BI deals — <15%

---

## 1. Product Vision

### 1.0 Concept summary

Lumen makes a single bet: **a workspace is a business vertical**. Each customer can run multiple workspaces (one per vertical they care about), and within each workspace the AI is tuned to that vertical's semantics. The same platform serves a wholesale-distribution workspace, a personal-lending workspace, and a B2B-finance workspace — all with grounded, governed AI answers — without code changes per vertical.

### 1.1 Positioning

> **A lightweight data platform with Claude-grade AI, deployable in your own AWS account.**

We do not aim to beat Tableau on visualization breadth or to match every enterprise BI feature checkbox. We aim to be best-in-class on two specific things: **the accuracy of natural-language data questions** and **the trustworthiness of the answers we return**.

### 1.2 Three personas
1. **Data engineer / analyst** — writes Cube models, defines metrics, validates with SQL
2. **Business user** (PM, Ops, Marketing) — uses AI chat and dashboards; does not write SQL
3. **Embedded developer** (v2) — embeds our dashboards into their own product

### 1.3 Workspaces are business verticals

A **workspace** in Lumen is the unit of business-vertical isolation. Every workspace has its own:

- **Cube semantic model** — the cubes, measures, dimensions, segments specific to that vertical
- **Data sources** — the databases the vertical reads from
- **AI grounding** — schema summary, business glossary, few-shot examples, eval set
- **Users + permissions + RLS policies**
- **LLM preset** (`cost_sensitive` / `balanced` / `quality_first`)

Switching workspace = switching the entire context the AI reasons about. A user can belong to multiple workspaces; switching is a single click.

This makes it natural to support **multiple verticals on one platform**:

| Vertical | Example data shape |
|---|---|
| Wholesale / distribution (TPC-H — shipped as the local test fixture) | Customer / Order / LineItem / Part / Supplier / Nation / Region |
| Personal lending | Borrower / Loan / Payment / Default |
| B2B SaaS finance | Customer / Subscription / Invoice / MRR / ChurnEvent |
| Retail e-commerce | Customer / Order / Product / Inventory / Promotion |
| Insurance | Policy / Claim / Premium / Renewal |

Each vertical is a workspace template the platform can ship pre-built (v2/v3): pre-defined cubes, glossary, example questions, eval set. Customers clone a template, point it at their own data sources, and adjust descriptions/synonyms to match their vocabulary.

This also unlocks **vertical-specific AI tuning**. Few-shot examples in the prompt are drawn from the workspace's own example pool, so the AI's behavior is shaped by the vertical's idioms (e.g., a lending workspace's "default rate" question routes to lending-specific measures).

### 1.4 North-star metrics
- **Time-to-first-trusted-answer**: from a new business user's onboarding to the first answer they're willing to act on. Target **< 10 minutes**.
- **AI accuracy on governed metrics**: for questions that map to modelled metrics, accuracy **> 95%**. (Pure text-to-SQL benchmarks at ~64.5%; routing through a structured semantic layer is how we close the gap.)

---

## 2. Frontend Design

### 2.1 Stack

| Layer | Choice | Rationale |
|---|---|---|
| Framework | React 19 + TypeScript | Largest talent pool; server components optional |
| Build / dev | Vite | Fast HMR, simple config |
| Routing | TanStack Router | Type-safe; superior to React Router for typed flows |
| Server state | TanStack Query | Caching + optimistic updates |
| Client state | Zustand | Lightweight; avoids Redux boilerplate |
| Forms | React Hook Form + Zod | Schema-driven; we share Zod schemas with backend |
| Charts | **Observable Plot** + D3 escape hatch | Declarative; faster to build than raw D3 |
| Tables / grid | TanStack Table; AG Grid Community for pivots | TanStack handles standard tables; AG Grid for pivots (free tier) |
| Code editor | Monaco | Syntax highlighting for SQL workbench and Cube model editor |
| Styling | Tailwind v4 + Radix UI | Token-based design; Radix handles a11y |
| Drag-drop | dnd-kit | Used in dashboard layout |

### 2.2 Information architecture (four primary surfaces)

```
┌─────────────────────────────────────────────────────────────┐
│  Top nav: Workspace · Search · AI · User                    │
├──────────┬──────────────────────────────────────────────────┤
│ Sidebar: │  Main canvas                                      │
│          │                                                   │
│ • Home   │  ┌─ Workbook ───────────────┐                     │
│ • Models │  │                          │                     │
│ • Dashes │  │  (one of 4 surfaces)     │                     │
│ • SQL    │  │                          │                     │
│ • AI Chat│  │                          │                     │
│ • Admin  │  └──────────────────────────┘                     │
└──────────┴──────────────────────────────────────────────────┘
```

#### Surface 1: Workbook — exploratory analysis

- **Left panel**: Cube schema explorer (cubes / measures / dimensions / segments) — drag fields into the query builder
- **Center panel**: Query builder
  - Click-to-add measures and dimensions (90% of use cases)
  - Filter pills with operator dropdowns
  - Time grain selector
  - Toggle to raw SQL for analysts (compiled by the Cube SQL API)
- **Right panel**: Visualization
  - Auto chart-type recommendation (driven by measure count + dimension cardinality)
  - Rendered via Observable Plot
  - "Pin to dashboard" action
- **Top bar**: Save / Fork / Share / AI Assist
- **AI Assist**: Floating chat that modifies the current query in place ("add a filter for last 30 days")

#### Surface 2: Dashboard

- Grid layout via `react-grid-layout`
- Each tile maps to a saved Workbook query
- **Cross-filter**: clicking a tile's dimension re-filters every other tile on the dashboard
- **Drill-down**: right-click / shift-click a data point opens the Workbook with the filter pre-applied
- **Dashboard-level filters**: top-of-page control panel applied to all tiles
- **Sharing**: URL encodes filter state; copy and send

#### Surface 3: Model Editor — IDE for the Cube schema

- Monaco editor with Cube YAML / JS syntax highlighting
- Left sidebar: file tree synced from a Git repo
- Right side: live preview — change a measure, query it instantly
- **Diff view** against `main` branch
- **Validate** button runs Cube schema validation
- **Lineage view** (v2): measure → column dependency graph

#### Surface 4: AI Chat — conversational analysis

- Full-screen mode (Claude.ai-style) and inline mode (within Workbook / Dashboard)
- **Each reply contains**:
  1. A natural-language answer
  2. The generated Cube query (collapsible)
  3. A rendered chart or table
  4. "Continue in Workbook" CTA — opens the AI's query in Workbook for further editing
- **Conversation memory**: session-level context; follow-up questions can reference prior answers
- **Trust indicators**: each reply shows which cube and measures were used; users can click through to the model definition

### 2.3 Observable Plot integration pattern

Plot's idiom (imperative DOM construction) doesn't match React's. Our wrapper:

```tsx
function PlotChart({ spec, data }: { spec: ChartSpec; data: Row[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = Plot.plot(buildPlotOptions(spec, data));
    ref.current?.replaceChildren(el);
    return () => el.remove();
  }, [spec, data]);
  return <div ref={ref} />;
}
```

Internal `ChartSpec` (not raw Plot options):

```ts
type ChartSpec = {
  type: 'line' | 'bar' | 'area' | 'scatter' | 'heatmap' | 'pie' | 'big-number';
  x?: { field: string; type: 'time' | 'ordinal' | 'quantitative' };
  y?: { field: string; agg?: 'sum' | 'avg' | 'count' };
  color?: { field: string };
  facet?: { row?: string; column?: string };
  marks?: PlotMarkOverride[];  // escape hatch
};
```

**Why a middle layer?**
1. Field names map directly to Cube query results
2. AI can emit it as a Zod-validated structure
3. Swapping the chart engine later (if Plot doesn't scale) doesn't require rewriting dashboards

**Cross-filter wiring**: every chart container subscribes to a Zustand store; click events emit filters; the dashboard re-fetches affected tiles (debounced).

### 2.4 Performance budget
- **Initial JS bundle**: < 350 KB gzipped (route-level code splitting)
- **AI chat first token**: < 2s (Bedrock streaming)
- **Dashboard cold load**: < 3s for 6 tiles (with Cube pre-agg cache hit)
- **Workbook query**: P50 < 1.5s, P95 < 5s (pre-aggs in place)

### 2.5 Design system
- Token-based (spacing, color, typography)
- Dark mode from day 1
- Density toggle (comfortable / dense) — analysts prefer dense
- Keyboard-first: ⌘K command palette; shortcuts aligned with Linear / Notion conventions

---

## 3. Backend Design

### 3.1 Language choice

**Conclusion: every in-house service is Python.** The exceptions are Cube (Node.js, but it's OSS we deploy rather than write) and the frontend (TypeScript).

| Service | Language | Notes |
|---|---|---|
| API Gateway / BFF | **Python** (FastAPI) | I/O-bound; Python handles it well |
| AI Orchestration | **Python** (FastAPI) | Bedrock SDK / prompt tooling / eval frameworks are Python-first; this is **the most important, non-negotiable service** |
| Query Service | **Python** (FastAPI) | Cube / Redis / Postgres clients are mature in Python |
| Auth / Workspace Service | **Python** (FastAPI) | CRUD + permissions; Python is more than adequate |
| ETL Workers | **Python** (Temporal SDK) | Meltano + Singer taps (Apache 2.0) + motor + asyncpg; permissive license stack with the richest connector ecosystem |
| Semantic Layer | **Node.js** (Cube OSS) | Cube itself is Node.js; we deploy it, we don't write code in it |
| Frontend | **TypeScript** | Already decided |

**Why a single backend language**:
1. **The AI service mandates Python** (Bedrock / Claude SDK / prompt tooling / ML eval framework are all Python-first). Since we must have Python, using it for everything saves us a second toolchain.
2. **Operational simplicity**: one CI / linter / dependency manager (uv) / package layout / observability lib / internal SDK. The cognitive load saved across 12 engineers is enormous.
3. **Hiring**: only need Python engineers; no need to split a Go/Python pool.
4. **On-call**: an on-call engineer doesn't have to be fluent in two languages to debug a cross-service issue.
5. **Internal libraries**: auth helpers, metrics emitters, audit log writers — written once.

**Honest trade-offs**:
- Per-request latency is 10–30 ms slower than Go — but our bottleneck is Cube + warehouse query latency (hundreds of ms to seconds), so this delta is negligible.
- Memory per worker is larger (~150 MB vs ~30 MB for Go) — handled by EKS pod limits; the dollar impact is trivial at our scale.
- True parallelism is GIL-limited — but our services are entirely I/O-bound (waiting on DB or Bedrock); asyncio is sufficient. CPU-bound workloads use multiple worker processes.

**Why not Go**:
- The ops cost of running Go + Python is greater than the perf cost of running pure Python.
- Go's strengths (concurrency, single-binary deployment) aren't bottlenecks in our workload.
- The AI service must be Python; mixing forces us to maintain two ecosystems.

**Why not Rust**:
- We're not writing a query engine (Cube + Postgres handle the hot path).
- Smaller hiring pool, 30–50% slower iteration speed.
- AI orchestration in Rust is a productivity disaster.

**Why not Java**:
- Slow iteration; JVM tuning overhead.
- Its main perceived advantage (enterprise trust) is something we don't need to prove via language choice.

**Standard tooling for the Python stack**:

| Concern | Choice |
|---|---|
| Web framework | FastAPI (async, OpenAPI auto-generation) |
| ASGI server | Uvicorn (production: behind nginx / ALB) |
| Async DB drivers | asyncpg (Postgres), motor (Mongo), aiomysql (MySQL) |
| HTTP client | httpx |
| Validation | Pydantic v2 |
| Package management | uv (Astral) |
| Linter / formatter | Ruff |
| Type checker | Pyright (strict) |
| Testing | pytest + pytest-asyncio |
| Workflow | Temporal Python SDK |
| Observability | OpenTelemetry Python SDK |

### 3.2 Service architecture

```
                ┌──────────────────────────────────┐
                │        Web Frontend (React)      │
                └────────────┬─────────────────────┘
                             │ HTTPS
                ┌────────────▼─────────────────────┐
                │   API Gateway / BFF (Python)     │
                │   • Auth (JWT validate)          │
                │   • Request routing              │
                │   • Rate limiting                │
                │   • Audit log emit               │
                └─┬────────┬────────┬───────┬──────┘
                  │        │        │       │
        ┌─────────▼──┐ ┌───▼────┐ ┌─▼──┐ ┌──▼──────┐
        │ AI Service │ │ Query  │ │Auth │ │Workspace│
        │ (Python)   │ │ Service│ │ Svc │ │ Service │
        │            │ │(Python)│ │(Py) │ │ (Py)    │
        └──────┬─────┘ └────┬───┘ └─────┘ └─────────┘
               │ Cube query JSON
               ▼
        ┌────────────────────────────┐
        │   Cube Semantic Layer       │
        │   (Node.js, OSS Cube core)  │
        └────────┬───────────────────┘
                 │ SQL
        ┌────────┴────────────────────────────┐
        ▼                                     ▼
  ┌──────────┐    ┌──────────┐    ┌──────────────┐
  │ Postgres │    │  MySQL   │    │ Postgres     │
  │ (warehs) │    │ (client) │    │ (Mongo→ETL)  │
  └──────────┘    └──────────┘    └──────────────┘

  ┌─────────────────────────────────┐
  │  Job Queue: Temporal            │
  │  • ETL workflows                │
  │  • Scheduled queries            │
  │  • Pre-agg refresh              │
  └─────────────────────────────────┘
```

### 3.3 Service breakdown

#### A. API Gateway / BFF (Python, FastAPI, ~3K LoC)
- REST + SSE endpoints (query results + AI streaming); no GraphQL in v1
- JWT verification (public key from Auth Service, cached)
- **Per-request audit log**: who, when, which query / AI prompt → Kafka (aiokafka) → S3
- Rate limiting (per workspace + user, Redis token bucket)
- Async middleware stack: auth → rate limit → audit → route

#### B. AI Service (Python, FastAPI)
**This is the moat service. Detailed below.**

Responsibilities:
1. NL question → Cube query JSON
2. Query results → NL summary
3. Conversation memory management
4. Tool calling (Claude) for multi-step reasoning

**Core prompt structure**:

```
[System]
You are a data analyst with access to the following Cube semantic model:
<schema>
{compiled Cube schema, summarized to ~5K tokens}
</schema>

When answering, you must:
1. Output ONLY a structured Cube query (JSON tool call)
2. Reference only measures/dimensions defined in the schema
3. If the question is ambiguous, ask a clarifying question

[Tools]
- run_cube_query(query: CubeQuery) → results
- ask_clarification(question: str) → user input
- final_answer(text: str, query: CubeQuery, viz: ChartSpec)

[Few-shot examples]
{20–30 curated NL → CubeQuery pairs, swapped per workspace}
```

**Schema grounding strategy**:
- Schemas are typically small (< 50 cubes ≈ 3–8K tokens); we embed the entire schema in the prompt rather than retrieve via RAG.
- Prompt caching (Bedrock Claude prompt caching): the schema portion is cached, with target hit rate > 90%, dramatically reducing cost.
- For very large schemas (> 100 cubes): fall back to RAG, selecting top-K cubes by question keyword embedding.

**Quality loop**:
- Every AI query is logged: (NL question, generated CubeQuery, success/failure, user-edited?).
- Weekly batch eval: re-run regressions across logged cases.
- Failure cases reviewed by data team and added to the few-shot pool.

**Streaming design**:
- Bedrock streaming → server-sent events → frontend.
- When a tool call (e.g., `run_cube_query`) appears, the stream pauses, the query runs, then resumes.
- Orchestrated by a minimal in-house state machine (LangGraph evaluated and rejected as too heavy for our needs).

#### C. Query Service (Python, FastAPI)
- Receives Cube query JSON, forwards to Cube, processes results.
- **Result cache**: Redis, key = hash(query + schema version + user RLS context).
- **Permission enforcement**: injects RLS filters (based on user attributes) into the Cube query before execution.
- **Long query handling**: queries exceeding 30s become async jobs (Temporal workflow), returning a job ID; the frontend polls or streams via SSE.
- Talks to Cube via httpx async client with a connection pool.

#### D. Cube Semantic Layer (Node.js, OSS)
- Deploy Cube core directly; no fork.
- In-house code is limited to schema deployment tooling (pull from Git, validate, push to Cube).
- Pre-aggregations stored in Cube Store (built-in).

#### E. Auth Service (Python, FastAPI)
- OIDC support (Okta, Google Workspace, Azure AD) via authlib.
- Workspace + role + group management.
- RLS policy storage (policies are part of the Cube schema; user→group→policy mapping lives here).

#### F. Workspace Service (Python, FastAPI)
- Workspace CRUD, user invites, billing (v2; Stripe Python SDK), settings.
- Saved workbook / dashboard storage (Postgres, asyncpg + SQLAlchemy 2.0).

#### G. ETL Service (Python, Temporal worker)
- Mongo → Postgres pipeline.
- Schema flattening (config-driven).
- Incremental sync (using Mongo `_id` or `updatedAt`).
- Temporal handles workflow orchestration (retries, versioning are free).

### 3.4 Storage layer

| Store | Purpose |
|---|---|
| **Postgres (app DB)** | Workspaces, users, dashboards, saved queries, audit metadata |
| **Postgres (warehouse)** | Mongo ETL landing zone; hosted-warehouse customer data |
| **Redis** | Query result cache, sessions, rate-limit counters |
| **S3** | Audit log archive, exports (CSV / Parquet), AI training data dumps |
| **Cube Store** (Parquet on disk) | Pre-aggregation cache |
| **OpenSearch** | Full-text search across dashboards / workbooks / Cube schemas |

### 3.5 Auth & permissions

**Three-tier model**:
1. **Workspace level** — does the user belong to this workspace
2. **Resource level** — does the user have view / edit / admin on this dashboard / workbook (ACL)
3. **Row level (RLS)** — even if the user can see the dashboard, the underlying data is filtered (e.g., "only your region")

RLS implementation: Cube's `securityContext` plus our policy engine. Example policy:

```yaml
# policies/sales.yml
policy: sales_region_isolation
applies_to: [Sales, Orders]
when: user.role != 'admin'
filter: |
  Sales.region = '${user.attributes.region}'
```

Policies are injected into the Cube query at compile time.

### 3.6 AWS deployment topology

```
VPC
├── Public subnets
│   └── ALB → Cloudfront (frontend static)
├── Private subnets (app)
│   ├── EKS cluster
│   │   ├── api-gateway (3 replicas)
│   │   ├── ai-service (autoscale 2–20)
│   │   ├── query-service (3 replicas)
│   │   ├── cube (4 replicas + cube-store)
│   │   └── temporal worker (autoscale)
│   └── ElastiCache Redis
├── Private subnets (data)
│   ├── RDS Postgres (app DB, multi-AZ)
│   ├── RDS Postgres (warehouse, larger)
│   └── MSK Kafka (audit log)
└── External
    ├── Bedrock (Claude)
    ├── S3
    └── OpenSearch
```

**Notes**:
- AI service has a wide autoscale band (2–20). Bedrock is per-request billed, so pod resource is mainly memory (streaming buffers) + CPU (JSON parsing).
- Cube runs at least 4 replicas. Pre-agg refresh and query serving are on separate deployments so refresh doesn't slow live queries.

### 3.7 Observability
- **Metrics**: Prometheus + Grafana (self-hosted)
- **Logs**: structured JSON → CloudWatch + indexed to OpenSearch
- **Traces**: OpenTelemetry → Tempo / Jaeger
- **AI quality dashboard** (in-house): daily query accuracy, top failed prompts, token cost breakdown
- **Error tracking**: Sentry

### 3.8 Security
- Encryption at rest (RDS, S3) and in transit (mTLS between services)
- Secret management: AWS Secrets Manager
- SOC 2 readiness: preparation begins in v2; external audit in Phase 4
- Customer data isolation: v1 single-tenant per workspace (schema-per-workspace in the warehouse); v2 evaluates row-level multi-tenancy
- AI safety: every LLM output is schema-validated; references to columns or functions outside the schema are rejected

### 3.9 LLM model strategy

> The AI service is not a single LLM call — it's many sub-tasks. Each uses the cheapest tier that's fit for purpose: medium for the main path (quality), weak for sub-tasks (cost), strong for hard cases.

#### 3.9.1 Selection principles

| Principle | Why |
|---|---|
| **Don't use weak tier for the main path** | Multi-cube joins, ambiguity resolution, and tool-chain stability all degrade 5–10% with the weak tier — fatal for our accuracy target |
| **Don't use strong tier for the main path** | 5x the cost and ~50% higher latency; medium tier is already correct on 90% of queries |
| **Medium is the default** | Strong structured output, stable schema grounding, best price/perf |
| **Weak handles sub-tasks** | Summary, autocomplete, chart-spec recommendation — simple tasks where weak saves ~10x |
| **Strong handles hard cases** | Multi-step reasoning, failed-query retry, complex cross-cube queries |

#### 3.9.2 Model tier abstraction (v1 fixed at 3 tiers)

Application code **never references a model_id directly** (e.g., `"claude-sonnet-4-6"`). It calls `tier="medium"` instead. Tier → model_id mapping lives in a single YAML config.

##### Config schema (`config/llm_models.yaml`)

```yaml
# Single source of truth for model selection across the platform.
tiers:
  strong:
    provider: anthropic
    model_id: claude-opus-4-7
    max_context: 200_000
    supports_streaming: true
    supports_tools: true
    notes: "Hard cases, failed query retry, deep analysis"

  medium:
    provider: anthropic
    model_id: claude-sonnet-4-6
    max_context: 200_000
    supports_streaming: true
    supports_tools: true
    notes: "Default for NL → Cube query main path"

  weak:
    provider: anthropic
    model_id: claude-haiku-4-5-20251001
    max_context: 200_000
    supports_streaming: true
    supports_tools: true
    notes: "Sub-tasks: summary, autocomplete, chart spec"

# Task → tier defaults
task_defaults:
  text_to_query: medium
  query_summary: weak
  chart_recommendation: weak
  autocomplete: weak
  schema_description_gen: medium
  failed_query_analysis: strong
  complexity_estimator: weak

# Escalation rules (referenced by routing logic)
escalation:
  text_to_query:
    on_previous_failure: strong
    on_complex_multi_cube: strong

# Per-workspace presets (selected by admin; override task_defaults)
workspace_presets:
  cost_sensitive:
    text_to_query: weak           # cheaper but accuracy drops
    failed_query_analysis: medium

  balanced: {}                    # use task_defaults

  quality_first:
    text_to_query: strong         # always strong; expensive but most accurate
    query_summary: medium
```

##### Why we lock at 3 tiers

- **No fourth tier** (e.g., "premium-strong"). More tiers means more complex routing logic and a UX that's harder for admins to reason about.
- **3 tiers cover** the speed/cost/quality extremes; anything beyond is over-engineering.
- If v2 truly needs another tier, it's a YAML change — call sites stay unchanged.

##### Only allowed hard-coded model IDs

Only this YAML file may contain `claude-*` strings. **CI lint enforces this**:

```bash
git diff --name-only | grep -v "config/llm_models.yaml" | xargs grep -l "claude-opus\|claude-sonnet\|claude-haiku" && exit 1
```

##### Python loader

```python
# llm_config.py — single platform-wide entrypoint
from pathlib import Path
import yaml
from pydantic import BaseModel

class TierConfig(BaseModel):
    provider: str
    model_id: str
    max_context: int
    supports_streaming: bool
    supports_tools: bool

class LLMConfig(BaseModel):
    tiers: dict[Literal["strong", "medium", "weak"], TierConfig]
    task_defaults: dict[str, Literal["strong", "medium", "weak"]]
    escalation: dict[str, dict[str, Literal["strong", "medium", "weak"]]]
    workspace_presets: dict[str, dict[str, Literal["strong", "medium", "weak"]]]

CONFIG = LLMConfig(**yaml.safe_load(Path("config/llm_models.yaml").read_text()))

def resolve_model(task: str, workspace_preset: str | None = None) -> TierConfig:
    tier = CONFIG.task_defaults[task]
    if workspace_preset and task in CONFIG.workspace_presets.get(workspace_preset, {}):
        tier = CONFIG.workspace_presets[workspace_preset][task]
    return CONFIG.tiers[tier]
```

#### 3.9.3 Task → tier routing

| Task | Default tier | Escalation |
|---|---|---|
| **NL → Cube query** (main path) | **medium** | failed_once / complex_multi_cube → strong |
| NL summary (results → text) | **weak** | — |
| Chart-spec recommendation | **weak** | — |
| AI autocomplete | **weak** | — (latency-critical, < 300 ms) |
| Complexity estimator (pre-routing) | **weak** | — |
| Schema-importer description gen | **medium** | — |
| Failed-query root-cause analysis (background) | **strong** | — |
| Eval regression run | **medium** | (also runs strong for comparison) |

#### 3.9.4 Routing logic

```python
async def route_text_to_query(question: str, ctx: ChatContext) -> TierConfig:
    workspace_preset = ctx.workspace.llm_preset  # cost_sensitive / balanced / quality_first

    # Start with default for this task (respects workspace preset)
    tier = (
        CONFIG.workspace_presets.get(workspace_preset, {}).get("text_to_query")
        or CONFIG.task_defaults["text_to_query"]
    )

    # Escalation
    rules = CONFIG.escalation.get("text_to_query", {})
    if ctx.previous_failures >= 1 and "on_previous_failure" in rules:
        tier = rules["on_previous_failure"]
    elif await is_complex_multi_cube(question) and "on_complex_multi_cube" in rules:
        tier = rules["on_complex_multi_cube"]

    return CONFIG.tiers[tier]
```

Call sites always receive a `TierConfig`; they never see model_ids. The Bedrock client wrapper takes a `TierConfig` and pulls the `model_id` for the API call.

Sub-tasks (summary, autocomplete, chart spec) call `resolve_model("query_summary", workspace.llm_preset)` directly — no escalation.

#### 3.9.5 Cost estimate

Assuming a workspace with 100 active users × 30 queries/day:

| Workspace preset | Main path tier | Sub-task tier | Monthly cost (with prompt cache 90% hit) | Quality |
|---|---|---|---|---|
| `cost_sensitive` | weak | weak | ~$130 | ❌ accuracy drops 5–10%, customer churn |
| **`balanced` (recommended)** | **medium** | **weak** | **~$650** | ✅ balanced |
| `quality_first` | strong | medium | ~$3,200 | ✅ most accurate, expensive |
| All-strong (not offered) | strong | strong | ~$5,800 | ❌ unnecessary overkill |

Recommended config ≈ 45% the cost of medium-only: weak sub-tasks save dollars without affecting core quality.

Current tier mapping (from §3.9.2 YAML):
- strong → claude-opus-4-7
- medium → claude-sonnet-4-6
- weak → claude-haiku-4-5

#### 3.9.6 Prompt caching strategy

**This is the cost-control linchpin.** Cache misses cause 5–10x cost spikes.

| Cache layer | Contents | TTL | Target hit rate |
|---|---|---|---|
| **Schema cache** | Cube schema summary (5–15K tokens) | 1 hour | > 95% |
| **Few-shot cache** | Per-cube example pool | 1 hour | > 90% |
| **Glossary cache** | Business glossary | 1 hour | > 95% |
| **System prompt cache** | Static instructions | 1 hour | > 99% |

Cache invalidation triggers:
- Cube schema deploy (via Model Editor push)
- Glossary update
- Few-shot pool update

#### 3.9.7 1M context (strong-tier 1M Opus): use it?

**Not in v1.**
- Schemas are typically 5–15K tokens — 1M context is overkill.
- Only Opus offers 1M, so cost and latency surge.
- Stuffing too much cold context degrades model attention.

**v2 evaluate**: long conversation memory + workspace-wide query history + entire dashboard library in the prompt may justify 1M, but it's an advanced feature, not day-1 work.

#### 3.9.8 Required companion product features

1. **Per-workspace preset selector** — admin UI to choose `cost_sensitive` / `balanced` / `quality_first`. Backed by `workspace.llm_preset` in app DB; the YAML's `workspace_presets` apply immediately.
2. **Token budget monitoring** — monthly token quota per workspace; throttle or alert admin on overage.
3. **Model A/B framework** — no code changes required; add `experimental_tier_override` to YAML to split traffic.
4. **Cost attribution** — per-user / per-dashboard token consumption visible in the admin panel; broken down by tier (strong/medium/weak shown separately).
5. **Cache hit-rate dashboard** — visible in observability; alert on drop.
6. **Tier override audit log** — record which admin changed which workspace preset / YAML; cost-affecting changes must be traceable.

#### 3.9.9 Model upgrade strategy

This is the **biggest payoff of the §3.9.2 abstraction** — upgrading a new Claude model is a one-line YAML change.

- **Anthropic ships a new model** (e.g., a future Sonnet 4.7 / Haiku 5.0):
  1. Run the eval suite against the candidate model_id.
  2. On pass: update `config/llm_models.yaml`, e.g., `medium.model_id: claude-sonnet-4-7`.
  3. Canary deploy: 1% of workspaces → 10% → 50% → 100%.
  4. At each stage, monitor accuracy + cost + p95 latency.
- **New model fails eval**: don't update YAML; log failure cases; wait for the next version.
- **Old model deprecated**: try the YAML change in staging first, then roll out.
- **Emergency rollback**: revert one YAML line; full-platform recovery in ~1 minute.

This flow **requires no code changes and no app deploy** — a major operational simplification.

---

## 4. Data Layer

### 4.1 Connector matrix (v1)

| Source | Mode | Tooling |
|---|---|---|
| **Postgres** | Direct query via Cube | Cube native driver |
| **MySQL** | Direct query via Cube | Cube native driver |
| **MongoDB** | ETL → Postgres warehouse | Meltano + `tap-mongodb` (Singer) on Temporal |

### 4.2 MongoDB ETL detail

**Goal**: turn Mongo collections into Postgres tables that Cube can treat as normal SQL sources.

**Pipeline**:
```
Mongo (source)
   │ Change Streams (or polling fallback)
   ▼
Meltano + tap-mongodb (Singer)        ← Apache 2.0 / MIT
   │
   ▼
Transformation layer (dbt-style, but in Python)
   • Flatten nested fields (config-driven)
   • Array explode (config-driven)
   • Type coercion (Mongo BSON → Postgres types)
   ▼
Postgres warehouse (raw schema → modeled schema)
   ▼
Cube (semantic model on top of modeled schema)
```

**Why Meltano not Airbyte?** Airbyte changed to Elastic License v2 in 2022. ELv2 prohibits offering the software as a hosted/managed service — incompatible with our commercial path. Meltano + Singer is the permissive-license alternative with the same connector breadth. See Appendix A for the license audit.

**Schema flattening config** (in-house DSL):
```yaml
source: orders
target_schema: warehouse_modeled
mappings:
  - mongo_path: $._id
    column: order_id
    type: text
    primary_key: true
  - mongo_path: $.customer.email
    column: customer_email
    type: text
  - mongo_path: $.items
    explode_to_table: order_items
    parent_fk: order_id
incremental_field: updatedAt
sync_mode: incremental
schedule: every 10 minutes
```

**Bottleneck warning**: Mongo collections > 100M docs may take a full day for the initial backfill. Mitigations:
- Initial: parallel by `_id` range
- Ongoing: change stream (lag < 1 min)

### 4.3 Cube schema organization

```
/cube-schemas
  /shared/                   # cross-workspace shared dimensions
    date_dim.yml
    geography_dim.yml
  /workspaces/
    /acme-corp/
      orders.yml
      customers.yml
      _metrics.yml           # shared measure macros
      _segments.yml
```

**Conventions**:
- One cube per file
- Measure naming: `count_*`, `sum_*`, `avg_*`, `pct_*`
- Pre-aggregations live at the bottom of the cube file, not scattered
- Everything goes through CI (`cubejs-cli validate`)

### 4.4 Pre-aggregation strategy
- Every cube ships with at least one daily rollup (most-used dimensions × main measures).
- The AI service emits queries; Cube auto-routes to the best pre-agg; we monitor miss rate.
- High-frequency dashboard queries get dedicated pre-aggs.
- Refresh schedule: daily for most cubes; high-freshness cubes use partition + incremental.

### 4.5 Multi-source join limits
v1 **does not support cross-source joins** (e.g., Mongo→Postgres data joining customer-side MySQL). Customers wishing to join must ETL to a common warehouse. v2 evaluates Trino / DuckDB for federated query.

### 4.6 Data team onboarding & AI grounding workflow

> **A common question**: what does the data team need to do for the AI to understand their model?
>
> **Short answer**: adding column comments to MySQL helps, but isn't the main course. The AI **does not look at raw tables**. AI grounding lives in the **Cube semantic model**.

#### 4.6.1 Five layers of AI grounding

```
┌─────────────────────────────────────────┐
│  5. Eval set (golden questions)         │ ← QA layer
├─────────────────────────────────────────┤
│  4. Few-shot examples                   │ ← prompt examples
├─────────────────────────────────────────┤
│  3. Cube AI annotations                 │ ← description / synonyms / examples
├─────────────────────────────────────────┤
│  2. Cube semantic model                 │ ← what the AI actually sees
├─────────────────────────────────────────┤
│  1. Raw schema + comments (MySQL/PG)    │ ← reference material for writing Cube
└─────────────────────────────────────────┘
```

The AI sees only layers 2–4 in its prompt. Layer 1 is **raw material the data team uses to write layer 2**; the AI never reads it directly.

#### 4.6.2 Why raw table comments aren't enough

The business question "How many active customers did we have last month?" cannot be answered from raw schema alone — what counts as "active"? Is `user_id` the same as `customers.id`? Is `created_at` server time or user time? Does "customer" mean only paying customers, or include sign-ups?

These are **business semantics** — not schema — and they belong in the Cube model.

#### 4.6.3 Five-step data-team workflow

##### Step 1 — Tidy up raw schema (helpful but not the goal)

Add column comments to MySQL / Postgres / Mongo (post-ETL):
```sql
ALTER TABLE orders MODIFY COLUMN status VARCHAR(20)
  COMMENT 'paid|refunded|cancelled — only "paid" counts as revenue';
```
**Purpose**: reference material for the data engineer authoring the Cube model; can also be fed to an LLM to scaffold a Cube YAML draft for human review. **No need to do every table** — only the ones that will enter the semantic model.

##### Step 2 — Write the Cube schema (core work, 90% of effort)

An AI-friendly cube example:

```yaml
cubes:
  - name: Orders
    sql_table: warehouse.orders
    description: |
      One row per customer order. Used for revenue, order volume,
      and customer purchase behavior analysis.
      Only orders with status='paid' count as revenue.

    joins:
      - name: Customers
        sql: "{CUBE}.customer_id = {Customers}.id"
        relationship: many_to_one

    dimensions:
      - name: status
        sql: status
        type: string
        description: "Order lifecycle status"
        meta:
          enum_values: [paid, refunded, cancelled, pending]
          ai_hint: "Filter to status='paid' for revenue queries"

      - name: created_at
        sql: created_at
        type: time
        description: "When the order was placed (UTC)"

      - name: country
        sql: shipping_country
        type: string
        description: "Country shipped to (ISO 2-letter)"

    measures:
      - name: revenue
        sql: amount_usd
        type: sum
        filters:
          - sql: "{CUBE}.status = 'paid'"
        format: currency
        description: |
          Total paid order amount in USD.
          Excludes refunded and cancelled orders.
        meta:
          synonyms: [sales, gmv, top-line, turnover]
          example_questions:
            - "What was revenue last month?"
            - "Top 10 countries by sales this quarter"

      - name: order_count
        sql: id
        type: count_distinct
        description: "Number of unique orders (any status)"
        meta:
          synonyms: [orders, transactions, purchase count]

      - name: aov
        sql: "{revenue} / {order_count}"
        type: number
        format: currency
        description: "Average Order Value — paid revenue per order"
        meta:
          synonyms: [average order value, avg ticket]

    segments:
      - name: high_value
        sql: "{CUBE}.amount_usd > 1000"
        description: "Orders over $1000"
```

**AI-friendly key fields**:

| Field | Why it matters |
|---|---|
| `description` (cube/dimension/measure) | The AI's primary source of meaning |
| `meta.synonyms` | Users say "sales" when they mean "revenue" |
| `meta.example_questions` | Few-shot raw material; tells AI which questions this measure answers |
| `meta.ai_hint` | Encodes subtle invariants ("revenue must always filter status='paid'") |
| `meta.enum_values` | Tells AI the legal filter values, prevents hallucination |
| `format` | Auto-applies `$` / `%` in chart rendering |
| `segments` | Pre-defined common filters; "high value customer" is callable by name |

##### Step 3 — Business glossary

For things the Cube schema can't express on its own (fiscal year, custom region groupings, etc.), maintain a markdown glossary that's **fed into the AI prompt as system context**:

```markdown
# Business Glossary

## Active Customer
A customer who placed at least one paid order in the last 90 days.
Use Customers.is_active_90d segment.

## Fiscal Year
Our fiscal year starts April 1. Use TimeDim.fiscal_year, not calendar year,
unless the user explicitly says "calendar year".

## Region Mapping
- APAC = JP, KR, SG, HK, TW, AU, NZ
- EMEA = all European countries + ME + Africa
- AMER = US, CA, MX, BR + LATAM
```

##### Step 4 — Curate few-shot examples

Maintain `examples.yml` with 5–15 NL → Cube query JSON pairs per cube:

```yaml
- question: "Top 5 countries by revenue last quarter"
  cube_query:
    measures: [Orders.revenue]
    dimensions: [Orders.country]
    timeDimensions:
      - dimension: Orders.created_at
        dateRange: "last quarter"
    order: { "Orders.revenue": "desc" }
    limit: 5

- question: "What's our AOV trend this year?"
  cube_query:
    measures: [Orders.aov]
    timeDimensions:
      - dimension: Orders.created_at
        granularity: month
        dateRange: "this year"
```

The prompt builder selects top-K matched examples by question keywords (so the prompt context stays tight).

##### Step 5 — Eval set (QA layer)

Maintain a 100–500-question dataset of "golden question + expected query result". Every prompt or model change auto-runs a regression:

```yaml
- id: q_revenue_by_country_q1
  question: "Top 5 countries by sales in Q1 2026"
  expected:
    measures_used: [Orders.revenue]
    must_filter: ["status = 'paid'", "created_at in Q1 2026"]
    expected_row_count: 5
  tolerance: row_order_strict
```

Without an eval, you never know whether a prompt change made things better or worse.

#### 4.6.4 Effort estimate (typical customer)

For a typical mid-sized customer (30 core tables, 10 business domains), first-time onboarding:

| Work | Estimate |
|---|---|
| Raw table comments (only those entering the semantic model) | 1–2 weeks |
| Cube schema v1 (10 cubes, ~50 measures) | 4–6 weeks |
| Descriptions / synonyms / example_questions filled in | 2–3 weeks (overlapping above) |
| Business glossary | 1 week |
| Few-shot examples (~50) | 1–2 weeks |
| Eval set v1 (~100 cases) | 2 weeks |
| **Total** | **~10–14 weeks (1 data engineer + 0.5 analyst)** |

This is **front-loaded investment**; AI quality ROI depends on it.

#### 4.6.5 Onboarding tooling we must ship (v1)

1. **Schema Importer** — connect to MySQL/PG → pull schema + comments → generate a Cube YAML draft (Claude auto-fills descriptions, guesses measure types, suggests likely joins).
2. **AI Annotation Panel** — UI for editing description / synonym / example_question / ai_hint per cube/measure without touching YAML directly.
3. **Eval Runner** — UI showing per-cube AI accuracy (green/yellow/red) so the data team knows where to add descriptions or examples.
4. **Failed Query Review Queue** — when a user's AI answer is wrong, one-click sends it to the data team queue; after the team fixes the model, the original question is auto-retested.

These four are **v1 must-ship**. If the data team won't maintain the schema, AI quality is a toy. Without these tools, schema maintenance means editing YAML and running eval scripts — no one will do it.

#### 4.6.6 Ongoing data team work

After onboarding, the data team's weekly cadence:
- Review failed query queue (~30 min / week)
- Add new measures / dimensions as business needs evolve
- Run eval regression (CI automated; data team responds to alerts)
- Monthly review of the AI accuracy dashboard; focus on the worst-performing cubes

This is **ongoing work, not one-time onboarding**. The product must make this workflow effortless. If it's painful, the data team stops doing it, AI quality drops, business users churn, the product dies.

---

## 5. 24-Month Project Plan

### 5.1 Team composition

| Role | Headcount | Joining |
|---|---|---|
| Tech Lead / Architect | 1 | M0 |
| Backend Eng (Python, services) | 3 | M0×2, M3×1 |
| Backend Eng (Python, AI focus) | 2 | M0, M2 |
| Frontend Eng (React) | 3 | M0×2, M4×1 |
| Data Eng (Cube + ETL, Python) | 2 | M0, M3 |
| ML Eng (eval, prompt tuning, Python) | 1 | M3 |
| **Engineering total** | **12** | All Python (except frontend) |
| Product Manager | 1 | M0 |
| Designer (UX + visual) | 1 | M0 |
| Data Analyst (dogfooding + content) | 1 | M2 |

**15 FTE total.**

### 5.2 Phases & milestones

#### Phase 0 — Foundation (M0–M3)
- Stand up infrastructure: EKS, CI/CD, Cube deployment, Postgres, Bedrock IAM.
- First end-to-end skeleton: log in → hardcoded Cube schema → workbook field picker → render a chart.
- AI service hello-world: NL → Cube query JSON (single cube, no RLS).
- Mongo ETL POC (one collection round-trips).

**Exit criteria**: internal demo lets users "pick a measure → render a chart" and "ask a question → AI returns a chart". 3 internal users can log in.

#### Phase 1 — Internal MVP (M4–M9)
- All four primary surfaces functional:
  - Workbook: 8 chart types, filters, save
  - Dashboard: grid layout, cross-filter, drill-down
  - Model editor: Git-based, validate, deploy
  - AI chat: streaming, conversation memory, ≥80% accuracy on the modelled cubes
- RBAC + RLS v1
- Mongo ETL: 3 schema-flattening patterns working
- Pre-aggregation auto-refresh
- Internal dogfood: data team + at least 2 business teams

**Exit criteria**: 30 internal users, 50% weekly active rate, AI accuracy on internal cubes > 85%.

#### Phase 2 — Internal GA (M10–M15)
- SQL workbench
- Dashboard scheduling + email export (basic)
- Full audit log + admin panel
- Performance hardening: dashboard < 3s, AI < 2s first token
- AI quality lift: > 95% on common patterns
- First security review (internal red team)
- Recruit design partners (3–5 friendly external companies)

**Exit criteria**: 200 internal users, 5 design-partner workspaces live and active.

#### Phase 3 — External Beta (M16–M21)
- Multi-tenant hardening: data isolation review; per-workspace pre-agg quotas
- Onboarding flow: UI-driven Cube schema creation
- Billing integration (Stripe)
- SOC 2 audit kick-off
- Documentation site
- Beta: open to 20–30 paying-intent customers

**Exit criteria**: 10 paying customers signed; monthly retention > 80%.

#### Phase 4 — Commercial v1 (M22–M24)
- Public pricing
- Self-serve signup
- Marketing site
- Initial outbound sales (3 AEs)
- Push for first 25 customers / $1M ARR

### 5.3 Critical risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AI accuracy fails to reach 95% | High | Critical | Weekly eval from M3; ML eng full-time; "AI declines to answer when uncertain" fallback |
| Mongo ETL schema drift causes user complaints | Medium | High | Schema change detection + auto-alert + UI repair flow |
| Cube OSS lacks needed features / upstream slow on PRs | Medium | Medium | Plan for fork + maintenance budget; evaluate fork in Phase 2 |
| Can't hire enough senior frontend | High | Medium | Make offers in M0; consider contractors as backfill |
| Bedrock cost gets out of hand | Medium | Medium | Prompt caching + result cache + per-workspace token budget |
| Competitive pricing pressure from established BI tools | Medium | High | Lean into self-host + best-in-class AI accuracy |
| Excel-grid feature gap becomes a deal-breaker | Medium | Medium | Track lost-deal reasons; if blocking, re-evaluate post-Phase 4 |

### 5.4 Cost estimate (rough)

| Item | Internal phase (M0–M15) | External phase (M16–M24) |
|---|---|---|
| AWS infra | $5K/mo → $10K/mo | $25K/mo |
| Bedrock (Claude) | $2K/mo | $15K/mo |
| Personnel (15 FTE × 2 yr, blended $250K) | — | $7.5M total |
| Third-party (Sentry, Stripe, etc.) | $1K/mo | $5K/mo |
| SOC 2 audit | — | $80K one-off |

**Total burn**: ~$8.5M over 24 months (mostly personnel).

### 5.5 Team practice
- **Weekly AI quality review** (mandatory): case study of the prior week's failed queries.
- **2-week sprints**, but the AI service ships daily (it's experiment-heavy).
- **Internal dogfood mandate**: all PM / leadership metric reviews must happen on our own platform.
- **Decision logs (ADR)**: every major schema / API decision is recorded; avoids rewriter syndrome.

---

## 6. Tech decision summary (one-page)

| Question | Answer | Why |
|---|---|---|
| Use OSS semantic layer? | ✅ Cube | Saves 2 years of in-house engineering |
| Which AI model? | Claude (via Bedrock) | Strongest structured output + tool use; deployable in customer's AWS |
| Backend primary language? | **Python (single language)** | The AI service must be Python; the ops cost of mixing exceeds Go's perf advantage |
| Frontend chart library? | Observable Plot + D3 escape | Declarative; faster iteration |
| MongoDB strategy? | ETL → Postgres | Semantic layers are relational-first |
| MySQL/Postgres direct? | ✅ via Cube | No data movement required |
| Pre-aggregation? | Cube Store | OSS; no Snowflake needed |
| Multi-tenant? | v1 schema-per-workspace; v2 evaluate row-level | Risk-controlled |
| Embedded analytics? | After v2 | Scope discipline |
| Excel grid? | No | Cost/value ratio doesn't justify it |

---

## 7. Closing thesis

Lumen's bet is that there's a real segment of customers — mid-sized companies, AWS-resident, data-conscious, AI-curious, security-aware — who want a lightweight, AI-native data platform they can deploy in their own infrastructure, with metrics defined in code and answers grounded in a governed semantic model.

Established BI vendors serve adjacent segments well, but this particular intersection — **lightweight + self-hostable + AI-native + semantic-first** — is underserved. Not because no one can build it, but because the market hasn't yet routed engineering effort here.

Our wedge: **build on Cube** to compress 2+ years of semantic-layer iteration; **route through Claude** for industry-leading natural-language accuracy; **discipline scope** by saying no to Excel-grid formula engines, embedded analytics, mobile, and other features that would dilute focus; and **invest deeply** in the data-team workflow — the schema-importer, annotation panel, eval runner, and failed-query queue — because that's the loop that determines whether AI quality compounds or stagnates.

If the thesis is right, Lumen ships a product mid-sized companies will pay for in 24 months. If it's wrong (e.g., customers don't actually care about self-host), we still have a high-quality internal data platform — not a failed product.

---

## Appendix A: Core OSS dependencies

| Project | License | Purpose |
|---|---|---|
| [Cube](https://github.com/cube-js/cube) | Apache 2.0 | Semantic layer |
| [Observable Plot](https://github.com/observablehq/plot) | ISC | Charts |
| [TanStack Query / Table / Router](https://tanstack.com/) | MIT | Frontend |
| [Meltano](https://github.com/meltano/meltano) + [Singer SDK](https://github.com/meltano/sdk) | MIT + Apache 2.0 | Mongo→PG ETL (orchestration + connector framework) |
| [tap-mongodb (MeltanoLabs)](https://github.com/MeltanoLabs/tap-mongodb) | Apache 2.0 | Mongo source connector (Singer tap) |
| [Temporal](https://github.com/temporalio/temporal) | MIT | Workflow |
| [Vanna AI](https://github.com/vanna-ai/vanna) | MIT | Text-to-SQL fallback (evaluate Phase 1) |
| [Monaco Editor](https://github.com/microsoft/monaco-editor) | MIT | Code editor |
| [AG Grid Community](https://github.com/ag-grid/ag-grid) | MIT | Pivot table |
| [Radix UI](https://github.com/radix-ui/primitives) | MIT | Headless components |

## Appendix B: Pitfalls avoided (vs. naive first instinct)

1. **Don't build dashboards on raw D3** — use Observable Plot + a D3 escape hatch (saves ~6 months).
2. **Don't use raw text-to-SQL** — use text-to-Cube-query (lifts accuracy from ~65% → ~95%).
3. **Don't build a semantic layer from scratch** — use Cube (saves ~2 years).
4. **Don't try to make MongoDB work natively in the semantic layer** — ETL it (avoids unsolved abstraction problems).
5. **Don't build an Excel formula engine** — explicit non-goal (avoids competing with mature spreadsheet UX).
6. **Don't use Rust or mix backend languages** — single-language Python preserves iteration speed and ops simplicity.
7. **Don't write a workflow engine** — use Temporal.

---

*End of report.*
