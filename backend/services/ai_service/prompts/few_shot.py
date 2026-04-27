"""Few-shot example selection.

v1: hand-curated YAML, top-K by simple keyword overlap.
v2: embeddings-based retrieval.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "eval"


def load_examples() -> list[dict[str, Any]]:
    """Load all example questions from golden_set.yaml (re-used as few-shot pool)."""
    path = EXAMPLES_DIR / "golden_set.yaml"
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text()).get("examples", [])


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in text.replace(",", " ").replace(".", " ").split() if len(w) > 2}


def select_top_k(question: str, k: int = 5) -> list[dict[str, Any]]:
    examples = load_examples()
    if not examples:
        return []

    q_tokens = _tokens(question)
    scored: list[tuple[int, dict[str, Any]]] = []
    for ex in examples:
        ex_tokens = _tokens(ex["question"])
        overlap = len(q_tokens & ex_tokens)
        scored.append((overlap, ex))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for _, ex in scored[:k]]


def render_examples(examples: list[dict[str, Any]]) -> str:
    """Render examples as a string suitable for embedding in the prompt."""
    if not examples:
        return ""
    lines = []
    for i, ex in enumerate(examples, 1):
        lines.append(f"Example {i}:")
        lines.append(f"Question: {ex['question']}")
        lines.append(f"Cube query: {json.dumps(ex['cube_query'], indent=2)}")
        lines.append("")
    return "\n".join(lines)


def example_distribution() -> Counter[str]:
    """Diagnostic: count how many examples reference each cube/measure."""
    counter: Counter[str] = Counter()
    for ex in load_examples():
        for m in ex.get("cube_query", {}).get("measures", []):
            counter[m] += 1
    return counter
