"""Run all golden eval cases through the real LLM provider.

Loads `backend/services/ai_service/eval/golden_set.yaml` and sends each
question through the AI loop, capturing the AI's emitted Cube query and
comparing it against the expected measures / dimensions / segments.

Reports aggregate accuracy + per-case detail. Useful for measuring real-LLM
quality (Qwen / Bedrock / Anthropic) against the curated golden set, not
just the loop's mechanical correctness.

Usage:
  PYTHONPATH=backend:. backend/.venv/bin/python local_test/run_eval.py
  PYTHONPATH=backend:. backend/.venv/bin/python local_test/run_eval.py --provider alibaba
  PYTHONPATH=backend:. backend/.venv/bin/python local_test/run_eval.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

GOLDEN_PATH = ROOT / "backend" / "services" / "ai_service" / "eval" / "golden_set.yaml"


def load_cases(limit: int | None = None) -> list[dict[str, Any]]:
    cases = yaml.safe_load(GOLDEN_PATH.read_text())["examples"]
    return cases[:limit] if limit else cases


def evaluate(
    generated: dict[str, Any] | None,
    expected: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Return (passed, list_of_reasons). Empty reasons means full pass."""
    if generated is None:
        return False, ["no cube_query was generated"]

    measures = set(generated.get("measures", []) or [])
    dims = set(generated.get("dimensions", []) or [])
    segs = set(generated.get("segments", []) or [])

    issues: list[str] = []
    for required in expected.get("measures_used", []):
        if required not in measures:
            issues.append(f"missing measure {required}; got {sorted(measures)}")
    for required in expected.get("dimensions_used", []):
        if required not in dims:
            issues.append(f"missing dimension {required}; got {sorted(dims)}")
    for required in expected.get("segments_used", []):
        if required not in segs:
            issues.append(f"missing segment {required}; got {sorted(segs)}")
    if "expected_row_count_max" in expected:
        limit = generated.get("limit") or 0
        if limit and limit > expected["expected_row_count_max"]:
            issues.append(f"limit {limit} > expected max {expected['expected_row_count_max']}")

    return len(issues) == 0, issues


async def run_one_case(case: dict[str, Any], schema_summary: str, glossary: str, vertical: str) -> dict[str, Any]:
    """Send the case's question through the AI loop, return result dict."""
    from shared.auth import WorkspaceContext
    from shared.llm_providers import get_registry
    from services.ai_service import cube_runner
    from services.ai_service.stream import ChatContext, respond

    if vertical == "tpch":
        from local_test import duckdb_query_runner_tpch as qr
    else:
        from local_test import duckdb_query_runner as qr

    async def _local_run(query: dict[str, Any], _ctx: WorkspaceContext) -> dict[str, Any]:
        try:
            return qr.run_query(query)
        except Exception as e:
            return {"data": [], "error": str(e)}

    cube_runner.run_cube_query = _local_run  # type: ignore[assignment]

    ctx = ChatContext(
        workspace_ctx=WorkspaceContext(
            user_id="eval", workspace_id=f"ws-eval-{vertical}", role="admin",
            user_attrs={}, workspace_preset="balanced",
        ),
        schema_summary=schema_summary,
        glossary=glossary,
    )

    registry = get_registry()
    if not registry.started:
        await registry.startup()
    provider = registry.resolve_provider()

    final_query: dict[str, Any] | None = None
    last_run_query: dict[str, Any] | None = None
    error: str | None = None
    text_parts: list[str] = []
    tokens_in = 0
    tokens_out = 0
    hops = 0
    t0 = time.monotonic()

    try:
        async for ev in respond(case["question"], ctx, provider):
            if ev.event == "token":
                text_parts.append(ev.data.get("text", ""))
            elif ev.event == "tool_use":
                if ev.data.get("tool") == "run_cube_query":
                    last_run_query = ev.data.get("input")
                elif ev.data.get("tool") == "final_answer":
                    inp = ev.data.get("input") or {}
                    if "cube_query" in inp:
                        final_query = inp["cube_query"]
            elif ev.event == "usage":
                tokens_in += ev.data.get("input_tokens", 0)
                tokens_out += ev.data.get("output_tokens", 0)
                hops = max(hops, ev.data.get("hop", 0) + 1)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    elapsed = time.monotonic() - t0

    return {
        "id": case["id"],
        "question": case["question"],
        "expected": case.get("expected", {}),
        "generated_query": final_query or last_run_query,
        "answer_text": "".join(text_parts),
        "error": error,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "hops": hops,
        "elapsed_seconds": elapsed,
        "provider": provider.name,
    }


async def main(args: argparse.Namespace) -> int:
    os.environ.setdefault("USE_MOCK_LLM", "false")
    os.environ.setdefault("JWT_SIGNING_KEY", "local-dev-only")

    # Always use TPC-H for the golden set (the schema_bundle the eval was written against)
    from shared.schema_bundle import get_bundle
    bundle = get_bundle("tpch")
    schema_summary = bundle["schema_summary"]
    glossary = bundle["glossary"]

    cases = load_cases(args.limit)
    print(f"Running {len(cases)} eval cases against vertical=tpch\n")

    results: list[dict[str, Any]] = []
    pass_count = 0
    issue_count = 0

    for i, case in enumerate(cases, 1):
        print(f"[{i:>2}/{len(cases)}] {case['id']:<35} ", end="", flush=True)
        result = await run_one_case(case, schema_summary, glossary, "tpch")
        passed, reasons = evaluate(result["generated_query"], case.get("expected", {}))
        result["passed"] = passed
        result["reasons"] = reasons
        results.append(result)

        if passed:
            pass_count += 1
            print(f"✓  ({result['elapsed_seconds']:.1f}s, {result['tokens_in']}in/{result['tokens_out']}out, {result['hops']} hops)")
        else:
            issue_count += 1
            print(f"✗  ({result['elapsed_seconds']:.1f}s)")
            for r in reasons:
                print(f"      {r}")
            if result["generated_query"]:
                m = result["generated_query"].get("measures") or []
                d = result["generated_query"].get("dimensions") or []
                s = result["generated_query"].get("segments") or []
                print(f"      generated → measures={m} dims={d} segs={s}")
            if result["error"]:
                print(f"      error: {result['error']}")

    # ── Aggregate ───────────────────────────────────────────────────────────
    total = len(results)
    accuracy = pass_count / total * 100 if total else 0
    total_in = sum(r["tokens_in"] for r in results)
    total_out = sum(r["tokens_out"] for r in results)
    total_time = sum(r["elapsed_seconds"] for r in results)
    avg_hops = sum(r["hops"] for r in results) / total if total else 0
    provider = results[0]["provider"] if results else "unknown"

    print("\n" + "=" * 70)
    print(f"Provider:              {provider}")
    print(f"Result:                {pass_count}/{total} passed  ({accuracy:.1f}%)")
    print(f"Total wall time:       {total_time:.1f}s  (avg {total_time/total:.1f}s per case)")
    print(f"Total tokens:          {total_in:,} in / {total_out:,} out")
    print(f"Avg tokens per case:   {total_in//total:,} in / {total_out//total:,} out")
    print(f"Avg hops per case:     {avg_hops:.2f}")
    print("=" * 70)

    # Per-issue summary
    if issue_count > 0:
        print(f"\nFailing cases ({issue_count}):")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['id']}: {'; '.join(r['reasons'])}")

    return 0 if issue_count == 0 else 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="Run only the first N cases")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
