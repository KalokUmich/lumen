"""End-to-end smoke test for the AI loop, backed by DuckDB.

Runs without docker, without AWS (with --mock), without Postgres. Uses
the consumer-lending fixture as the sole test vertical.

Usage:
    python local_test/run_local_test.py --mock
    python local_test/run_local_test.py            # uses configured provider
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# Make `backend/` importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


SMOKE_QUESTIONS: list[dict[str, Any]] = [
    {
        "question": "What's our total origination volume?",
        "expects": {"measures_subset": ["Loan.total_originated"], "must_succeed": True},
    },
    {
        "question": "Default rate by grade",
        "expects": {
            "measures_subset": ["Loan.default_rate"],
            "dimensions_subset": ["Loan.grade"],
            "must_succeed": True,
        },
    },
    {
        "question": "Approval rate by application product type",
        "expects": {
            "measures_subset": ["Application.approval_rate"],
            "dimensions_subset": ["Application.product_type"],
            "must_succeed": True,
        },
    },
    {
        "question": "Origination volume trend by month last year",
        "expects": {
            "measures_subset": ["Loan.total_originated"],
            "must_succeed": True,
        },
    },
    {
        "question": "Top 5 branches by origination volume",
        "expects": {
            "measures_subset": ["Loan.total_originated"],
            "dimensions_subset": ["Branch.name"],
            "must_succeed": True,
        },
    },
]


# ── Environment + data checks ─────────────────────────────────────────────────


def _set_dev_env(args: argparse.Namespace) -> None:
    os.environ.setdefault("JWT_SIGNING_KEY", "local-dev-only")
    os.environ.setdefault("ANTHROPIC_BEDROCK_REGION", "us-east-1")
    if args.mock:
        os.environ["USE_MOCK_LLM"] = "true"

    data_dir = Path(__file__).parent / "data"
    os.environ["LOCAL_SCHEMA_SUMMARY_PATH"] = str(data_dir / "lending_schema_summary.txt")
    os.environ["LOCAL_GLOSSARY_PATH"] = str(data_dir / "lending_glossary.md")


def _check_seed_data() -> None:
    db = Path(os.environ.get("LOCAL_LENDING_DUCKDB_PATH", Path(__file__).parent / "data" / "lending.duckdb"))
    if not db.exists():
        print("⚠ Lending seed data missing. Run:  make seed-lending")
        sys.exit(2)


# ── Single-question execution ─────────────────────────────────────────────────


async def run_one(question: str, expects: dict[str, Any]) -> dict[str, Any]:
    """Run the AI loop for one question, routing Cube execution to DuckDB."""
    from shared.auth import WorkspaceContext
    from shared.llm_providers import get_registry
    from services.ai_service import cube_runner
    from services.ai_service.stream import ChatContext, respond
    from local_test import duckdb_query_runner_lending as qr

    async def _local_run(query: dict[str, Any], ctx: WorkspaceContext) -> dict[str, Any]:
        return qr.run_query(query)

    cube_runner.run_cube_query = _local_run  # type: ignore[assignment]

    schema_summary = Path(os.environ["LOCAL_SCHEMA_SUMMARY_PATH"]).read_text()
    glossary = Path(os.environ["LOCAL_GLOSSARY_PATH"]).read_text()

    ctx = ChatContext(
        workspace_ctx=WorkspaceContext(
            user_id="user-local",
            workspace_id="ws-local-lending",
            role="admin",
            user_attrs={},
            workspace_preset="balanced",
        ),
        schema_summary=schema_summary,
        glossary=glossary,
    )

    registry = get_registry()
    await registry.startup()
    provider = registry.resolve_provider()

    final_payload: dict[str, Any] | None = None
    tool_inputs: list[dict[str, Any]] = []
    text_parts: list[str] = []
    error: str | None = None

    try:
        async for ev in respond(question, ctx, provider):
            if ev.event == "token":
                text_parts.append(ev.data.get("text", ""))
            elif ev.event == "tool_use":
                tool_inputs.append(ev.data)
            elif ev.event == "final":
                final_payload = ev.data
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    return {
        "question": question,
        "final": final_payload,
        "tool_inputs": tool_inputs,
        "text": "".join(text_parts),
        "error": error,
        "expects": expects,
    }


def evaluate(result: dict[str, Any]) -> tuple[bool, str]:
    expects = result["expects"]
    must_succeed = expects.get("must_succeed", False)

    if result["error"] and must_succeed:
        return False, f"errored: {result['error']}"

    latest_query: dict[str, Any] | None = None
    for ti in result["tool_inputs"]:
        if ti.get("tool") == "run_cube_query":
            latest_query = ti.get("input")
        elif ti.get("tool") == "final_answer":
            inp = ti.get("input") or {}
            if "cube_query" in inp:
                latest_query = inp["cube_query"]

    if must_succeed and latest_query is None:
        return False, "no cube_query was generated"

    if latest_query is not None:
        measures = set(latest_query.get("measures") or [])
        dims = set(latest_query.get("dimensions") or [])
        segs = set(latest_query.get("segments") or [])
        for required in expects.get("measures_subset", []):
            if required not in measures:
                return False, f"missing measure {required} (got {sorted(measures)})"
        for required in expects.get("dimensions_subset", []):
            if required not in dims:
                return False, f"missing dimension {required} (got {sorted(dims)})"
        for required in expects.get("segments_subset", []):
            if required not in segs:
                return False, f"missing segment {required} (got {sorted(segs)})"

    return True, "ok"


# ── Main ──────────────────────────────────────────────────────────────────────


async def main(args: argparse.Namespace) -> int:
    _set_dev_env(args)
    _check_seed_data()

    print(f"Mode:     {'MOCK LLM' if args.mock else 'REAL PROVIDER'}")
    print(f"Vertical: lending")
    print(f"Running {len(SMOKE_QUESTIONS)} smoke questions...\n")

    pass_count = 0
    fail_count = 0

    for i, case in enumerate(SMOKE_QUESTIONS, 1):
        print(f"[{i}/{len(SMOKE_QUESTIONS)}] {case['question']}")
        result = await run_one(case["question"], case["expects"])
        passed, reason = evaluate(result)
        if passed:
            pass_count += 1
            print(f"   ✓ pass — {reason}")
        else:
            fail_count += 1
            print(f"   ✗ FAIL — {reason}")
            if result["error"]:
                print(f"     error: {result['error']}")
            if result["tool_inputs"]:
                last = result["tool_inputs"][-1]
                print(f"     last tool: {last.get('tool')} input={last.get('input')}")
        print()

    print("=" * 60)
    print(f"Result: {pass_count} passed, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true", help="Use mock LLM (no AWS / no API keys)")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
