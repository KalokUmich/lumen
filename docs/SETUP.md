# Lumen Setup & Operating Tutorial

> A practical, end-to-end walk-through for the three things our docs don't cover yet:
> (1) where data sources live, (2) how to author a Cube per table, (3) how the AI
> feedback loop works. If you hit anything that contradicts the code, the code wins —
> file a docs bug.

This is **§19/§21 of `IMPLEMENTATION_PLAN.md`** in tutorial form.

## Table of contents
1. [Where data sources are configured](#1-where-data-sources-are-configured)
2. [Authoring a Cube per table](#2-authoring-a-cube-per-table)
3. [The feedback / eval loop](#3-the-feedback--eval-loop)
4. [Common gotchas](#4-common-gotchas)

---

## 1. Where data sources are configured

**Today: YAML, not UI.** A "data source UI" is on the Phase 2 backlog
(`IMPLEMENTATION_PLAN.md` §19.1 #1 / §19.4) — until it ships, every connection lives in
two files:

```
config/settings.yaml          # committed defaults (provider availability, tier maps)
config/secrets.local.yaml     # gitignored credentials (DSN, API keys)
```

A workspace's data source is named in the **Cube schema YAML** itself, via the
`data_source:` key on a cube. The settings/secrets files supply the connection details
that name resolves to.

### 1.1 The three flavors we currently support

| Flavor | Where | Used for |
|---|---|---|
| **DuckDB (file)** | `local_test/data/*.duckdb` | local dev, smoke tests, CI |
| **Postgres** | env or `secrets.local.yaml` | production warehouses, app metadata |
| **MongoDB** | via the Mongo→Postgres ETL (Temporal) | source-of-truth services that don't expose SQL |

MySQL has driver wiring (`aiomysql` in `pyproject.toml`) but no production path; treat
it as experimental for now.

### 1.2 Adding a new Postgres source — worked example

Step 1. Add the DSN to `config/secrets.local.yaml`:

```yaml
data_sources:
  acme_finance:
    kind: postgres
    dsn: postgresql+asyncpg://lumen_ro:${ACME_PASSWORD}@db.acme.local:5432/finance
    health_check:
      query: "SELECT 1"
      timeout_ms: 1500
```

Step 2. Reference it from a Cube:

```yaml
# backend/cube/schema/verticals/acme/Invoice.yml
cubes:
  - name: Invoice
    data_source: acme_finance        # <— this name, not the DSN
    sql_table: public.invoices
    ...
```

Step 3. Verify the bundle loads:

```bash
make backend
TOK=$(backend/.venv/bin/python -c "import jwt; print(jwt.encode({'sub':'me','workspace_id':'acme'},'local-dev-only'))")
curl -s -H "Authorization: Bearer $TOK" http://localhost:8000/api/v1/workspaces/acme/schema-bundle | jq '.cubes | length'
```

If this returns `0`, look at `/tmp/lumen-logs/workspace.log` — almost always a YAML
parse error or a wrong `data_source:` name.

### 1.3 Where the actual binding happens (so you can debug)

- **Loader**: `backend/shared/settings.py` reads `config/settings.yaml` then
  deep-merges `config/settings.local.yaml`. Same for `secrets.yaml` →
  `secrets.local.yaml`.
- **Resolution**: `backend/services/query_service/main.py` looks up the cube's
  `data_source` name in the merged secrets, opens a connection, and runs the
  Cube-compiled SQL.
- **Health check at startup**: each enabled provider AND data source is pinged once.
  A failed source is marked unavailable for the lifetime of the process — restart to
  re-check.

### 1.4 What the future UI will expose

Tracked in `IMPLEMENTATION_PLAN.md` §19.4. The shortlist:
- A "Data sources" page under Admin where you paste a DSN, click "Test", and save.
- The save writes back to `secrets.local.yaml` (in dev) or to a secret store (in prod).
- A **Topics** layer that maps a source's tables to the AI tool's allowed list.

---

## 2. Authoring a Cube per table

The semantic layer is the contract between the warehouse and the AI. A well-written
cube measurably improves AI accuracy; a sloppy cube guarantees the AI invents nonsense.

### 2.1 File layout

One YAML per cube under `backend/cube/schema/verticals/<vertical>/<Cube>.yml`. The
filename is conventional; what matters is the `name:` field inside.

```
backend/cube/schema/
├── examples/orders.yml          # canonical reference — read this first
├── shared/                       # cross-vertical macros and joins
└── verticals/
    ├── tpch/                     # 8 cubes
    │   ├── region.yml
    │   ├── nation.yml
    │   ├── customer.yml
    │   ├── orders.yml
    │   └── ...
    └── saas_finance/             # 3 cubes
```

### 2.2 Anatomy of a cube (minimum AI-friendly version)

```yaml
cubes:
  - name: Region                       # PascalCase; this is what the AI references
    data_source: acme_finance          # see §1
    sql_table: main.region             # qualified table name
    description: |
      One-line plain-English description. Used in the schema bundle the AI sees.
      Mention any non-obvious business rules.
    meta:
      ai_facing: true                  # if false, AI can't query it
      vertical: acme
      domain: geography                # optional but improves few-shot match

    dimensions:
      - name: key
        sql: r_regionkey
        type: number
        primary_key: true              # required exactly once per cube

      - name: name
        sql: r_name
        type: string
        description: "Region name (AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST)"
        meta:
          enum_values: [AFRICA, AMERICA, ASIA, EUROPE, "MIDDLE EAST"]
          synonyms: [region, continent]      # ← critical for AI

    measures:
      - name: count
        sql: r_regionkey
        type: count_distinct
        description: "Number of regions"
```

### 2.3 The four AI-grounding fields you must not skip

These are what differentiate a cube the AI can use from a cube the AI guesses at:

1. **`description`** on the cube — what is this table?
2. **`description`** on every measure and dimension — what does this column mean
   in business terms?
3. **`meta.synonyms`** on dimensions and measures — list every phrasing a user
   might use ("revenue" → also "sales", "GMV", "top-line"). Covers the AI's
   text-to-query gap when the column name is jargony.
4. **`meta.ai_hint`** on measures with non-obvious semantics — e.g.
   `"revenue net of discount, before tax"` for a measure that's
   `SUM(extended_price * (1 - discount))`. Without this hint, the AI will produce
   plausible-but-wrong measures.

### 2.4 Time dimensions

Any column you want to filter by date needs a `granularities` block:

```yaml
- name: order_date
  sql: o_orderdate
  type: time
  granularities:
    - name: day
      interval: 1 day
    - name: week
      interval: 1 week
    - name: month
      interval: 1 month
    - name: quarter
      interval: 1 quarter
    - name: year
      interval: 1 year
```

The AI uses these granularities when it emits `timeDimensions[].granularity`. **If
you skip this block, queries like "orders by month" will fail to compile** — which
is one of the bugs called out in §0.5 of the plan.

### 2.5 Joins

Joins are declared *on the cube doing the joining*, not in some central place:

```yaml
joins:
  - name: Customer
    relationship: many_to_one
    sql: "{CUBE}.o_custkey = {Customer}.c_custkey"
```

Use `{CUBE}` and `{OtherCube}` interpolation — never hardcode table aliases.

### 2.6 Writing for the AI: a checklist

Before promoting a cube from `examples/` to a vertical, verify:

- [ ] Every dimension has a `description`
- [ ] Every measure has a `description` and (if non-obvious) `meta.ai_hint`
- [ ] Every dimension users might filter on has `meta.synonyms` (at least 2 variants)
- [ ] Every time column has full `granularities`
- [ ] Enums have `meta.enum_values`
- [ ] At least one entry in `eval/golden_set.yaml` exercises this cube
- [ ] `make smoke-orders` (or the appropriate vertical) passes

### 2.7 Where to add custom calculations

Two places, **and the choice matters**:

| Goal | Where |
|---|---|
| Will be reused across questions, governed, cached, RBAC-scoped | **Cube measure** — it lives in the YAML and the AI can pick it directly |
| One-off transform a user asks for, requires Pandas-shaped logic (rolling windows, percentile, t-test) | **Pandas transform tool** — see `.claude/skills/data-transform/SKILL.md` for routing rules |

**Do not** add an analytical capability as a Pandas transform when it could be a
measure — you lose governance, caching, and RLS. The data-transform skill is the
source of truth for this decision.

---

## 3. The feedback / eval loop

This is how a wrong AI answer becomes a permanent regression test.

### 3.1 Today (what's wired)

- **Failed query queue**: every execution error or `MaxAIHopsExceeded` writes a row
  to the `failed_query_reviews` table. The columns are in `IMPLEMENTATION_PLAN.md`
  §2.2 / §20.4.
- **Golden-set harness**: `backend/services/ai_service/eval/runner.py` runs
  `golden_set.yaml` (30 questions today, 50 target) and asserts each generated
  Cube query has the expected measures and dimensions.
- **Smoke test**: `make smoke` runs 5–10 representative questions against the
  mock LLM end-to-end so we catch wiring breaks before AI quality regressions.

### 3.2 What's missing (and tracked in §19/§20 of the plan)

- 👎 button on every chart in the chat panel — captures `wrong_chart`,
  `wrong_answer`, `unclear`, with a free-text comment
- `/admin/failed-queries` UI to triage the queue
- Weekly review meeting checklist
- Auto-promotion of upvoted Q→Query→Answer triples into RAG store (see
  `IMPLEMENTATION_PLAN.md` §20.1)

### 3.3 Manually promoting a question to the golden set

When you hit a wrong answer worth catching forever:

1. Reproduce the question against `make smoke` to confirm it's reproducible.
2. Capture the *correct* tool input by running the right query manually, e.g.:
   ```bash
   PYTHONPATH=. backend/.venv/bin/python -c "
   from local_test.duckdb_query_runner_tpch import run_query
   q = {'measures':['Orders.count'],
        'dimensions':['Region.name'],
        'timeDimensions':[{'dimension':'Orders.order_date',
                           'dateRange':'last 3 months',
                           'granularity':'month'}]}
   print(run_query(q)['sql'])
   "
   ```
3. Add an entry to `backend/services/ai_service/eval/golden_set.yaml`:
   ```yaml
   - id: orders_by_region_last_3_months
     question: "number of orders by region over last 3 months over time"
     vertical: tpch
     expects:
       measures_subset: ["Orders.count"]
       dimensions_subset: ["Region.name"]
       time_dimension: "Orders.order_date"
       date_range: "last 3 months"
       granularity: "month"
       must_succeed: true
       expected_chart_type: "grouped-bar"     # see §13a R11
   ```
4. Run `make smoke` to verify the entry parses.
5. Commit with a message tying back to the bug ID in `IMPLEMENTATION_PLAN.md`
   §0.5 if applicable.

### 3.4 Adding a system-prompt or few-shot fix

Some bugs are best fixed not in code but in the prompt. The two files are:

- **`backend/services/ai_service/prompts/system.py`** — the always-on instructions.
  Add a new section here when the bug is a class of question (e.g., "relative time
  phrases must use `timeDimensions`, not `filters`" — bug B1).
- **`backend/services/ai_service/prompts/few_shot.py`** — adds canned input/output
  examples retrieved by similarity. Add an entry here when the bug is one specific
  phrasing.

When you're tempted to add a third fix to the same bug, that's the signal to add
a critic check in `critic.py` instead — see `IMPLEMENTATION_PLAN.md` §0.5.

---

## 4. Common gotchas

- **`uvicorn` started from the wrong cwd**: services look up `local_test/data/*.duckdb`
  *relative to their working directory*. If the DB "doesn't exist" but you can `ls`
  it, run `readlink /proc/<pid>/cwd` on each uvicorn — it's almost certainly running
  from a stale path. Fix: `pkill -f 'uvicorn services\.' && make backend` from
  the repo root.
- **`USE_MOCK_LLM=true` is the default in `make backend`**. Set it to `false` (and
  fill in `secrets.local.yaml`) to exercise the real provider.
- **Two ports for the frontend**: VS Code's port forwarding sometimes shadows
  Vite's `:5173`. If chat 502s, confirm the frontend is hitting `localhost:8000`
  (the gateway), not the Vite dev server's `/api` proxy.
- **Pyright is strict on `shared/` and `services/ai_service/` only**. New files in
  those paths must type-check at strict; the rest of the tree is intentionally
  non-strict.
- **The repo says `omni-*` in two places** (`pyproject.toml` `name`,
  `package.json` `name`). The project was renamed to Lumen. Don't fix these
  unless told to — some scripts may depend on the old names.
