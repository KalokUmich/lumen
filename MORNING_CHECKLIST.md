# Morning Checklist — switching from mock LLM to real Bedrock

> Goal: ask the AI a question through the running stack and get a real Claude answer grounded in TPC-H data.

## 1. Verify AWS access (~30 sec)

```bash
aws sts get-caller-identity
aws bedrock list-foundation-models --by-provider anthropic --region us-east-1 \
  --query 'modelSummaries[].modelId' --output table | head -20
```

You need `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` on the Anthropic foundation models in your region. If `list-foundation-models` returns rows, IAM is fine.

## 2. Drop credentials into the local config (~30 sec)

```bash
cd /home/kalok/omni
cp config/secrets.local.yaml.example config/secrets.local.yaml
```

Then **either**:

- **Use boto3 default chain** (preferred — IAM role / SSO / `~/.aws/credentials`): leave the bedrock keys empty in `secrets.local.yaml`. Just set `AWS_PROFILE` in your shell:
  ```bash
  export AWS_PROFILE=your-profile-name
  ```
- **Or hard-code** in `secrets.local.yaml`:
  ```yaml
  llm:
    bedrock:
      aws_access_key_id: AKIA...
      aws_secret_access_key: ...
  ```

## 3. Sanity-check model IDs (~30 sec)

The model IDs in `config/settings.yaml` are placeholders following the standard Anthropic-on-Bedrock naming. Confirm they match what your account can invoke:

```bash
grep model_id config/settings.yaml
```

Compare to the output of step 1's `list-foundation-models`. If different, override in `config/settings.local.yaml`:

```yaml
llm:
  providers:
    bedrock:
      tiers:
        strong: anthropic.claude-opus-<actual-version>
        medium: anthropic.claude-sonnet-<actual-version>
        weak:   anthropic.claude-haiku-<actual-version>
```

(No need to redeclare unchanged fields — local file deep-merges over the base.)

## 4. Disable the mock + start everything

```bash
unset USE_MOCK_LLM
make backend
sleep 3
curl -sf http://localhost:8001/providers | python3 -m json.tool
```

Expected: `bedrock` shows `"healthy": true` with a latency_ms value.

If it shows unhealthy, the `error` field tells you why. Common cases:
- `AccessDeniedException` → IAM doesn't have InvokeModel
- `ValidationException: model_id` → fix the model IDs in step 3
- `ResourceNotFoundException` → model not enabled in Bedrock console for your region

## 4.5 What got added overnight (informational)

While you slept, the platform got a substantial polish pass:

- **Data-viz standards skill** — `.claude/skills/data-viz-standards/SKILL.md`. 575 lines distilling Cleveland-McGill, Tufte, Mackinlay APT, Few, Tableau Show Me, Datawrapper. The visualizer subagent and frontend chart renderer follow these rules.
- **Visualizer subagent** — `backend/services/ai_service/visualizer.py`. Deterministically picks chart type from data shape; returns ChartSpec with `rationale` and `confidence`. Replaces whatever chart_spec the LLM emits with its own canonical pick. AI can override with `chart_type_override` when the user explicitly asks ("show as a line chart").
- **22 chart types** in `frontend/src/components/chart/PlotChart.tsx` — including donut, treemap, small-multiples, sparkline, bullet, KPI strip.
- **Number formatting** — `frontend/src/lib/format.ts`. K/M/B/T suffixes, currency, percent precision rules, tabular numerals.
- **30-question golden eval set** for TPC-H — `backend/services/ai_service/eval/golden_set.yaml`. Will be the primary measure of real-Bedrock accuracy.
- **PartSupp cube** — supplier-side economics; new measures: `total_inventory_value`, `late_rate`, `return_rate`, `collection_rate`.
- **Schema browser tooltips** — hover any measure/dim in the workbench Field Picker to see description, synonyms, AI hints, example questions, enum values.
- **Cross-filter on dashboards** — click a categorical value to filter all tiles.
- **Second vertical: `saas_finance`** — synthetic SaaS data (5K accounts, 4.2K subs, 49K invoices, $4.8M active MRR). Demonstrates workspace switching changes the entire context.

## 5. Run the smoke test against real Bedrock

```bash
PYTHONPATH=backend:. backend/.venv/bin/python local_test/run_local_test.py --vertical tpch
```

(Without `--mock`. Uses `default_provider: bedrock` from `settings.yaml`.)

This sends 6 NL questions through the full AI loop. Each question:
NL → Claude (Bedrock) → Cube query JSON → DuckDB on TPC-H SF=1 → answer evaluated.

Expected: 6/6 pass. If the AI generates a wrong query for any case, that's a real signal worth investigating.

To stress-test deeper, run the full 30-case golden set (manually for now — pytest harness with real Bedrock comes in Phase 1):

```bash
# Per-question sample (replace question with one from golden_set.yaml)
curl -sN -X POST http://localhost:8000/api/v1/chat/respond \
  -H 'content-type: application/json' \
  -H 'authorization: Bearer dev:user-1:ws-demo:admin:balanced' \
  -d '{"question":"Top 5 nations by revenue"}'
```

To try the second vertical (workspace switching demo):

```bash
# Seed it (once)
PYTHONPATH=. backend/.venv/bin/python -c "from local_test.seed_saas_finance import seed; seed(5000)"

# Create the workspace
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H 'authorization: Bearer dev:user-1:ws-demo:admin:balanced' \
  -H 'content-type: application/json' \
  -d '{"slug":"saas-demo","name":"SaaS Finance","vertical":"saas_finance"}'
```

Then in the UI, switch the workspace selector to "SaaS Finance" — every Cube measure/dimension in the Field Picker is different (MRR, ARR, collection rate, ...), and the AI's grounding context is now SaaS-specific.

## 6. Open the UI

```bash
make frontend
# http://localhost:5173
```

- Workspace selector top-left should show "Demo (TPC-H)".
- Top-right badge should show "1/3 providers" healthy (only Bedrock — Anthropic + Alibaba unconfigured).
- Click "AI Chat" in the left rail. Try:
  - "Top 5 nations by revenue"
  - "Revenue by customer segment"
  - "Show me orders trend by month last year"
- Watch the response: thinking → tool_use → tool_result → final → chart renders.

## 7. Stop everything

```bash
make stop-backend
pkill -f vite
```

---

## Troubleshooting

| Symptom | Look at |
|---|---|
| Service won't start | `tail -f /tmp/lumen-logs/*.log` |
| Provider unhealthy | `curl http://localhost:8001/providers` returns the error string |
| Wrong AI answers | Compare the generated `cube_query` to what TPC-H actually offers (see `backend/cube/schema/verticals/tpch/`) |
| Slow first query | Bedrock cold-start can be 1–2s. Warm queries are sub-500ms. |
| Out of Bedrock budget | Workspace preset → `cost_sensitive` (uses weak tier for main path) |

## Cost note

A single TPC-H smoke run with the recommended `balanced` preset:
- ~6 questions × ~3 hops each × ~5K cached input + 200 fresh + 100 output tokens
- With prompt caching: roughly **$0.05 total** for the whole 6-question run on Sonnet.
- Without caching (first run): ~$0.30.

Cache warms on the second invocation since the schema_summary block is identical.
