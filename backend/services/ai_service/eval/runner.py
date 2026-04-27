"""Eval harness — runs the golden set against the AI service.

Usage:
    pytest backend/services/ai_service/eval/runner.py -m eval --tb=short
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml


GOLDEN_PATH = Path(__file__).parent / "golden_set.yaml"


def load_cases() -> list[dict[str, Any]]:
    return yaml.safe_load(GOLDEN_PATH.read_text())["examples"]


def evaluate_query(generated: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, str]:
    """Return (passed, reason)."""
    measures = set(generated.get("measures", []))
    dimensions = set(generated.get("dimensions", []))
    segments = set(generated.get("segments", []))

    for required in expected.get("measures_used", []):
        if required not in measures:
            return False, f"missing measure {required}"
    for required in expected.get("dimensions_used", []):
        if required not in dimensions:
            return False, f"missing dimension {required}"
    for required in expected.get("segments_used", []):
        if required not in segments:
            return False, f"missing segment {required}"

    if "expected_row_count_max" in expected:
        limit = generated.get("limit") or 0
        if limit and limit > expected["expected_row_count_max"]:
            return False, f"limit {limit} > expected max {expected['expected_row_count_max']}"

    return True, "ok"


@pytest.mark.eval
@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_golden_case(case: dict[str, Any]) -> None:
    """For now, just validates that golden cases are well-formed.

    Once the AI service is end-to-end runnable in CI, this calls out to it
    and compares the AI-generated query against the expected fields.
    """
    assert "question" in case
    assert "cube_query" in case
    # Self-check: the example's own cube_query should pass the eval.
    passed, reason = evaluate_query(case["cube_query"], case.get("expected", {}))
    assert passed, f"{case['id']}: {reason} | query={json.dumps(case['cube_query'])}"
