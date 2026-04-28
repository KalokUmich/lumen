---
name: data-transform
description: |
  Lumen's canonical data-fetch and data-transform routing rules. INVOKE THIS SKILL whenever you
  are about to (a) decide HOW to compute an answer from the warehouse, (b) author or revise an AI
  tool definition that returns rows, (c) design any "compute this metric" feature, or (d) review
  whether to add a new analytical capability as a Cube measure or a Pandas transform. This skill
  is the source of truth for the AI agent's tool-selection prompt and for the engineering
  decisions about where computation should live.
---

# Lumen Data Transform Standards

> The cost of a bad routing decision is high in both directions: doing too much in Pandas
> burns the governance/caching/RBAC story Cube provides; refusing to use Pandas leaves
> entire categories of analytical questions unanswerable. This skill is how we keep the
> line crisp.

This document is **prescriptive**: it tells the AI agent (and future contributors) when to
fetch raw data via the semantic layer (Cube) vs. when to escape into a Pandas transform.

---

## 1. The principle (read this first)

> **Cube is the default. Pandas is the escape hatch.**

Every analytical request walks through this gate:

1. **Can Cube express the answer as a query against the semantic model?**
   - YES → use `run_cube_query`. Stop.
2. Otherwise: **does the question require operations that are first-class in Pandas but
   awkward or impossible in SQL/Cube?** (See §3 for the closed list.)
   - YES → use `run_dataframe_transform`.
3. Otherwise: **decline and ask a clarifying question.** Don't invent a transform to
   stretch a vague request into something Pandas-shaped.

The bias is **strongly toward Cube**. Cube gives us caching, RBAC/RLS, schema governance,
provenance, prewarmed pre-aggregations, and a SQL trace the user can inspect. None of that
applies to ad-hoc Python. Every transform is a one-off snowflake until someone promotes it
to a Cube measure.

---

## 2. What Cube does well (use it, don't reinvent it)

These intents are Cube's home turf. Authoring these in Pandas is a code smell and will fail
review:

- **Aggregation**: SUM, COUNT, COUNT DISTINCT, AVG, MIN, MAX, MEDIAN
- **Group-by**: any combination of dimensions (`Orders.country`, `Customers.tier`, …)
- **Filtering**: WHERE/HAVING, including IN, NOT IN, LIKE, BETWEEN, multi-value OR
- **Joins**: declared in the Cube schema (`belongs_to`, `has_many`)
- **Time series**: `timeDimensions` with day/week/month/quarter/year granularity, with a
  `dateRange` (relative or absolute)
- **Top-N / Bottom-N**: `order` + `limit`
- **Ratios already declared as measures** (e.g. AOV = revenue / order_count if a measure exists)
- **Period-over-period delta** when achievable as two queries — let the visualizer subagent
  emit a `compare` hint instead of reaching for Pandas
- **Pre-aggregated rollups** — Cube's `pre_aggregations` slot

Even questions that "feel like" they need Pandas often don't. "Revenue trend by region for
the last 12 months" is one Cube query. "Top 5 products this quarter" is one Cube query.
"Median order value by country" is one Cube query. Reach for Pandas only after you've ruled
out a Cube formulation.

---

## 3. What Pandas does that Cube can't (the closed list)

`run_dataframe_transform` is the right tool **only** when the answer requires one of the
following. This list is closed by design — when something is added, the skill is updated
in the same PR.

### 3.1 Rolling / sliding windows
- 7-day moving average of daily revenue
- 30-day rolling stddev
- Cumulative sum across an ordered series (when `running_total` isn't a declared measure)
- Trailing 12-month KPI

> Why not Cube: window functions are SQL-expressible but Cube's measure model doesn't surface
> them ergonomically; expressing them as a measure requires a custom SQL block per measure
> and bypasses pre-aggregations. Pandas `rolling()` is the right shape for ad-hoc analysis.

### 3.2 Cohort and retention matrices
- Acquisition-cohort × tenure-period grid (the classic retention triangle)
- Churn cohort tables with conditional weighting
- LTV by cohort × month-active

> Why not Cube: requires self-joins on user-keyed slices the schema doesn't declare. Often
> only used once before being promoted to a Cube model.

### 3.3 Reshape — pivot / melt / stack / unstack
- Convert long-format ranking data to a wide table for a heatmap
- Pivot a `(year, quarter, value)` triple into a year-by-quarter matrix
- Unstack categorical breakdowns

> Why not Cube: Cube returns long-format rows by design. Reshape is a presentation step,
> not a semantic step.

### 3.4 Non-trivial statistics
- Percentile rank within a group, z-score within a group
- Pearson/Spearman correlation matrix across ≥3 measures
- Linear-regression slope or R² over a series
- Outlier detection (IQR / MAD)
- Distribution fits (skew, kurtosis)

> Why not Cube: most are not measures and not portable. If a stat becomes recurring it
> earns promotion to a Cube measure.

### 3.5 Multi-source DataFrame ops
- Joining two Cube query results with shapes the schema doesn't model
  (e.g. comparing snapshots from two date ranges side-by-side)
- Set operations (intersection / difference) across query results

> Why not Cube: Cube joins are schema-declared. Comparing arbitrary slices of the same
> dataset against itself is naturally a DataFrame op.

If the question doesn't fit one of §3.1–§3.5, **do not use the Pandas transform.** Either
fit it into Cube or ask the user to clarify.

---

## 4. The contract for `run_dataframe_transform`

The tool takes two inputs and returns rows in the same shape Cube returns:

```jsonc
{
  "cube_query": { /* a normal CubeQuery — must be the SOURCE the transform operates on */ },
  "pandas_code": "string — Python expression that mutates a DataFrame named `df`",
  "intent": "rolling_window | cohort_matrix | reshape | statistics | multi_source"
}
```

The runner:
1. Runs `cube_query` against query_service. The result becomes a DataFrame `df` with
   columns matching the Cube response keys (e.g. `LineItem__revenue`, `Orders__country`).
2. Executes `pandas_code` in a restricted Python sandbox with `df`, `pd`, `np` in scope —
   no `os`, `sys`, `subprocess`, `socket`, `open`, `__import__`, no network, no FS.
3. The final value of the `result` variable (DataFrame) is converted back to a list of
   row dicts, matching the schema/format that the visualizer expects.
4. Hard limits: 5s CPU, 256MB memory, 1M rows in the input, 100K rows in the output.

The agent **must** include `intent` so the audit trail can compare actual usage against the
allowed list in §3. The query_service logs `cube_query`, `pandas_code`, `intent`, runtime,
and output row count. Failed transforms (timeout, sandbox violation, unhandled exception)
go on the failed-query queue for triage.

---

## 5. Tool description (what the LLM actually reads)

When you author or revise the tool definition exposed to the LLM, use *these exact*
description strings. They have been tuned for routing accuracy on the golden set.

### 5.1 `run_cube_query` (the default)

> Run a query against the Cube semantic layer. **This is the default for any analytical
> question.** Use it for: aggregation (sum/count/avg/median), group-by, filtering, joins,
> time-series with day/week/month/quarter/year granularity, top-N / bottom-N, ratios that
> are already declared as measures, period-over-period (express via two queries with
> different `dateRange`s), and any question expressible in the Cube schema.
>
> **Do not** use Pandas transform when this tool can answer the question.

### 5.2 `run_dataframe_transform` (the escape hatch)

> Run a Pandas transform on top of a Cube query result. **Use ONLY when the question
> requires** one of the following operations that Cube cannot express:
>
> 1. Rolling / sliding window (e.g. 7-day moving average, trailing 12-month stat)
> 2. Cohort / retention matrix (acquisition × tenure)
> 3. Reshape: pivot / melt / stack / unstack
> 4. Non-trivial statistics: percentile rank, z-score, correlation matrix, regression,
>    outlier detection
> 5. Multi-source DataFrame ops the Cube schema doesn't model
>
> If the question is plain aggregation, group-by, filter, join, or top-N — use
> `run_cube_query` instead. **The bar to use this tool is high.** When in doubt, prefer
> `run_cube_query` and accept a slightly less polished answer over an unbounded Python
> escape hatch.
>
> Provide:
> - `cube_query`: the query that fetches the source data (must already include all
>   filters and dimensions you need; do not filter inside Pandas)
> - `pandas_code`: a self-contained Python snippet that mutates `df` and assigns
>   the final DataFrame to `result`. Available in scope: `df`, `pd`, `np`. Banned: any
>   import, any I/O, any network. CPU/memory/timeout limits are hard.
> - `intent`: which of the 5 categories above this transform falls under.

---

## 6. Few-shot examples (use in the system prompt)

These are the canonical good and bad routing decisions. Future-you should keep these in
the AI service's `prompts/few_shot.py` until the eval harness shows they're no longer
needed.

### 6.1 Use `run_cube_query` (positive examples)

| User asks | Tool | Why |
|---|---|---|
| "Total revenue last month" | `run_cube_query` | Aggregation + dateRange |
| "Top 5 countries by sales this quarter" | `run_cube_query` | order + limit |
| "Order count by month for the last year" | `run_cube_query` | Time series with granularity |
| "Average order value by customer tier" | `run_cube_query` | Group-by + aggregation |
| "Revenue trend last year vs this year" | `run_cube_query` (×2) | Two queries, visualizer compares |
| "Conversion rate by acquisition channel" | `run_cube_query` | Ratio measure already declared |

### 6.2 Use `run_dataframe_transform` (positive examples)

| User asks | Intent | Pandas code shape |
|---|---|---|
| "Show me 7-day rolling average of revenue" | `rolling_window` | `result = df.assign(rolling_revenue=df['LineItem__revenue'].rolling(7).mean())` |
| "Build me a cohort retention table by signup month" | `cohort_matrix` | `pivot_table` after computing `tenure_month = active_month - signup_month` |
| "Pivot revenue by region across quarters into a matrix" | `reshape` | `df.pivot(index='Region__name', columns='Orders__order_date_quarter', values='LineItem__revenue')` |
| "Z-score of monthly revenue, flag anomalies" | `statistics` | `df['z'] = (df['rev'] - df['rev'].mean()) / df['rev'].std()` |
| "Revenue Pearson correlation across categories" | `statistics` | `result = df[measures].corr()` |

### 6.3 DO NOT use `run_dataframe_transform` (negative examples)

| User asks | Wrong choice | Right choice | Why |
|---|---|---|---|
| "Top customers by revenue" | Pandas `.sort_values().head(10)` | `run_cube_query` with `order` + `limit` | Cube does this trivially |
| "Revenue per region" | Pandas `.groupby('region').sum()` | `run_cube_query` with `dimensions: [Orders.region]` | Pure aggregation |
| "Filter to orders above $100" | Pandas `df[df.amount > 100]` | `run_cube_query` with `filters` | Cube has filters |
| "Last year's revenue" | Pandas time math | `run_cube_query` with `dateRange: 'last year'` | Cube understands relative dates |

---

## 7. Promotion path (Pandas → Cube)

Every transform that runs is logged with its `intent` and `pandas_code`. If the same
transform recurs ≥3 times across users in a workspace, it earns a **promotion review**:

1. Engineering decides if it should become a Cube measure / pre-aggregation.
2. If yes: declare the measure with `description`, `synonyms`, `ai_hint`. Update the
   golden set so the AI prefers the Cube path on the next run. Decommission the transform
   intent if it was a one-off.
3. If no (truly ad-hoc): leave in Pandas, but add it to the workspace's allowed-pattern
   list so the audit log doesn't flag it.

This loop is what keeps the semantic layer growing in step with real usage instead of
calcifying around what was modeled at launch. Without it, Pandas becomes a permanent
shadow IT layer.

---

## 8. Security posture (must be enforced before turning the flag on)

This skill is read by humans designing the feature; the runtime enforces it. Before any
non-dev workspace gets `run_dataframe_transform`:

- [ ] AST-level whitelist of allowed nodes (`Import`, `ImportFrom`, `Exec`, `Eval` denied)
- [ ] Runtime sandbox: separate process, dropped capabilities, no network namespace
- [ ] Resource limits enforced via `setrlimit` (CPU, memory, file descriptors)
- [ ] DataFrame size guard at INPUT (refuse if `len(df) > 1_000_000`)
- [ ] DataFrame size guard at OUTPUT (truncate or error if `len(result) > 100_000`)
- [ ] Timeout enforced by parent watchdog (5s wall, 5s CPU)
- [ ] Per-workspace feature flag, default OFF
- [ ] Audit log row per call: workspace, user, intent, code hash, runtime, row counts
- [ ] No data egress: stdout/stderr captured, never returned to the LLM verbatim

If any of these checks aren't in place, the tool is not exposed to the LLM. The cost of
getting this wrong (LLM-driven RCE) outweighs the feature value of half-implementing it.

---

## 9. When this skill changes

Update conditions:
- New entry in §3 — needs a corresponding golden-set case + few-shot pair in §6.2
- Changed tool description in §5 — must re-run the routing-accuracy eval and document the
  before/after numbers in the PR
- New security check in §8 — bumps the v2 launch checklist

If a future contributor finds themselves wanting to use Pandas for something not in §3,
that's a signal to propose an addition here, not to silently widen the prompt.
