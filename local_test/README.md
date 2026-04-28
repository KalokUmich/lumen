# Local Test Scheme

A self-contained way to verify the platform end-to-end **without AWS, without
Postgres, without OIDC**.

## What it does

1. Seeds a local DuckDB file with consumer-lending fixture data
   (`seed_lending.py` — 8 cubes: Customer, Branch, LoanOfficer, Application,
   Loan, Payment, Collection, CreditInquiry).
2. Builds a Cube schema summary + business glossary as text files the
   workspace_service serves (`data/lending_schema_summary.txt`,
   `data/lending_glossary.md`).
3. Runs an end-to-end smoke test (`run_local_test.py`):
   - Starts in-process versions of query_service + ai_service (mock LLM by default)
   - Sends a few canned natural-language questions
   - Validates AI generates plausible Cube queries
   - Executes them against the DuckDB warehouse via the lending runner
4. Reports pass/fail with details.

## Quick start

```bash
# 1. From repo root, install backend deps if not already
make install-backend

# 2. Seed lending data (creates local_test/data/lending.duckdb, ~1.9 GB)
make seed-lending           # or: make seed-lending-small (5%, ~100 MB)

# 3. Run the smoke test with the mock LLM (no AWS needed)
make smoke

# 4. Or with real Bedrock / Anthropic / Alibaba (requires creds in
#    config/secrets.local.yaml)
PYTHONPATH=backend:. backend/.venv/bin/python local_test/run_local_test.py
```

## What's tested

| Component | Coverage |
|---|---|
| `shared.llm_config` | Tier resolution + workspace presets |
| `shared.llm_providers` | Mock + real (if AWS / API keys available) |
| `ai_service.routing` | Complexity heuristic, tier escalation |
| `ai_service.stream` | Tool-use loop end-to-end |
| `ai_service.schemas` | CubeQuery validation (rejects bad queries) |
| `ai_service.eval` | Golden set self-consistency |
| `query_service.cube_client` | (real Cube only — needs `docker compose --profile infra up cube`) |

The smoke test does NOT need real Cube to validate the AI loop — it falls back
to in-process query execution against DuckDB directly.

## Files

```
local_test/
├── README.md                       # this file
├── seed_lending.py                 # creates lending.duckdb + schema/glossary text
├── duckdb_query_runner_lending.py  # Cube query → DuckDB SQL (lending vertical)
├── run_local_test.py               # the smoke test runner
├── run_eval.py                     # golden-set eval runner
└── data/                           # gitignored: DuckDB file + schema/glossary
```

## Why DuckDB (not SQLite)

DuckDB is columnar and built for analytics — exactly the BI workload we serve.
Aggregations on the lending fixture (~35M rows at full scale) are sub-second.

Cube has native DuckDB driver support, so production-style schema files work
unchanged when pointed at DuckDB.

## Adding test cases

Add a new entry to `run_local_test.py::SMOKE_QUESTIONS`. Each entry:

```python
{
    "question": "What's our total origination volume?",
    "expects": {
        "measures_subset": ["Loan.total_originated"],
        "must_succeed": True,
    },
}
```

The runner sends the question through the AI loop, then asserts the resulting
Cube query satisfies the expectations.
