# Local Test Scheme

A self-contained way to verify the platform end-to-end **without AWS, without Postgres, without OIDC**.

## What it does

1. Generates ~10K rows of synthetic order/customer data (`generate_data.py`)
2. Inserts into a local DuckDB file (`seed_duckdb.py`)
3. Builds a Cube schema summary + business glossary as text files the workspace_service serves
4. Runs an end-to-end smoke test (`run_local_test.py`):
   - Starts in-process versions of query_service + ai_service (mock LLM by default)
   - Sends a few canned natural-language questions
   - Validates AI generates plausible Cube queries
   - Optionally executes them against the DuckDB warehouse via Cube
5. Reports pass/fail with details

## Quick start

```bash
# 1. From repo root, install backend deps if not already
cd backend && uv sync && cd ..

# 2. Generate + seed data (creates local_test/data/warehouse.duckdb)
python local_test/seed_duckdb.py

# 3. Run the smoke test with the mock LLM (no AWS needed)
python local_test/run_local_test.py --mock

# 4. Or with real Bedrock (requires AWS_PROFILE + Bedrock access)
python local_test/run_local_test.py
```

## What's tested

| Component | Coverage |
|---|---|
| `shared.llm_config` | Tier resolution + workspace presets |
| `shared.bedrock_client` | Mock + real (if AWS available) |
| `ai_service.routing` | Complexity heuristic, tier escalation |
| `ai_service.stream` | Tool-use loop end-to-end |
| `ai_service.schemas` | CubeQuery validation (rejects bad queries) |
| `ai_service.eval` | Golden set self-consistency |
| `query_service.cube_client` | (real Cube only — needs `docker compose up cube`) |

The smoke test does NOT need real Cube to validate the AI loop — it falls back
to in-memory query execution against DuckDB directly.

## Files

```
local_test/
├── README.md             # this file
├── generate_data.py      # synthetic data generator
├── seed_duckdb.py        # creates warehouse.duckdb + schema_summary.txt + glossary.md
├── run_local_test.py     # the smoke test runner
└── data/                 # gitignored: generated CSVs + DuckDB file + schema files
```

## Why DuckDB (not SQLite)

DuckDB is columnar and built for analytics — exactly the BI workload we serve.
Aggregations on 10K-100K rows are sub-millisecond. SQLite would also work but
would be a poor proxy for production performance characteristics.

Cube has native DuckDB driver support, so production-style schema files work
unchanged when pointed at DuckDB.

## Adding test cases

Add a new entry to `run_local_test.py::SMOKE_QUESTIONS`. Each entry:

```python
{
    "question": "What was revenue last month?",
    "expects": {
        "measures_subset": ["Orders.revenue"],
        "must_succeed": True,
    },
}
```

The runner sends the question through the AI loop, then asserts the resulting
Cube query satisfies the expectations.
