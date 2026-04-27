"""Tier routing for the AI service.

Wraps shared.llm_config with a complexity heuristic, returning a tier name
the caller passes through to the resolved provider.
"""

from __future__ import annotations

from shared.llm_config import (
    GenerationParams,
    get_generation_params,
    resolve_tier,
    resolve_tier_with_escalation,
)
from shared.llm_providers.base import TierName


def estimate_complexity(question: str) -> str:
    """Cheap heuristic for whether a question needs strong tier on first attempt.

    v2: ask the weak tier to classify (still cheap, more accurate).
    """
    lower = question.lower()
    multi_cube_signals = [
        "compare", "vs", "versus", "across", "join", "ratio between",
        "correlation", "by both", "broken down by",
    ]
    if any(s in lower for s in multi_cube_signals):
        return "complex_multi_cube"
    if len(question.split()) > 35:
        return "complex_multi_cube"
    return "simple"


def route_text_to_query(
    question: str,
    *,
    workspace_preset: str = "balanced",
    previous_failures: int = 0,
) -> tuple[TierName, GenerationParams]:
    is_complex = estimate_complexity(question) == "complex_multi_cube"
    tier_name = resolve_tier_with_escalation(
        "text_to_query",
        workspace_preset,
        previous_failures=previous_failures,
        is_complex_multi_cube=is_complex,
    )
    return tier_name, get_generation_params("text_to_query")


def route_summary(workspace_preset: str = "balanced") -> tuple[TierName, GenerationParams]:
    return resolve_tier("query_summary", workspace_preset), get_generation_params("query_summary")
