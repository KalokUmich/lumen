"""Schema bundle loader.

Reads a workspace's vertical-specific Cube schema files from
backend/cube/schema/verticals/<vertical>/ and produces:
  - schema_summary: a markdown text the AI uses for prompt grounding
  - glossary: business glossary markdown (from local_test/data/<vertical>_glossary.md
              if present, else empty)

This is the bridge between the Cube YAML files and the AI prompt. Production
will read the same YAML through Cube's own schema API; this module is the
fallback path used by the Phase 0 in-process workspace_service.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CUBE_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "cube" / "schema"
DATA_DIR = Path(__file__).resolve().parents[2] / "local_test" / "data"


def _load_cube_files(vertical_dir: Path) -> list[dict[str, Any]]:
    cubes: list[dict[str, Any]] = []
    for path in sorted(vertical_dir.glob("*.yml")):
        data = yaml.safe_load(path.read_text())
        if not data:
            continue
        for cube in data.get("cubes", []):
            cubes.append(cube)
    return cubes


def _format_meta(meta: dict[str, Any]) -> str:
    parts = []
    if meta.get("synonyms"):
        parts.append(f"synonyms: {meta['synonyms']}")
    if meta.get("enum_values"):
        parts.append(f"enum_values: {meta['enum_values']}")
    if meta.get("ai_hint"):
        parts.append(f"ai_hint: \"{meta['ai_hint']}\"")
    if meta.get("example_questions"):
        parts.append(f"examples: {meta['example_questions']}")
    return "; ".join(parts)


def _render_summary(cubes: list[dict[str, Any]], vertical: str) -> str:
    lines: list[str] = [f"# Cube Semantic Model — {vertical} vertical", ""]
    for cube in cubes:
        name = cube["name"]
        lines.append(f"## Cube: {name}")
        if cube.get("description"):
            lines.append(f"Description: {cube['description'].strip()}")

        if cube.get("dimensions"):
            lines.append("### Dimensions")
            for d in cube["dimensions"]:
                base = f"- {name}.{d['name']} ({d.get('type','string')})"
                if d.get("description"):
                    base += f" — {d['description']}"
                meta = _format_meta(d.get("meta", {}))
                if meta:
                    base += f"  [{meta}]"
                lines.append(base)

        if cube.get("measures"):
            lines.append("### Measures")
            for m in cube["measures"]:
                base = f"- {name}.{m['name']} ({m.get('type','number')}"
                if m.get("format"):
                    base += f", {m['format']}"
                base += ")"
                if m.get("description"):
                    base += f" — {m['description'].strip()}"
                meta = _format_meta(m.get("meta", {}))
                if meta:
                    base += f"  [{meta}]"
                lines.append(base)

        if cube.get("segments"):
            lines.append("### Segments")
            for s in cube["segments"]:
                base = f"- {name}.{s['name']}"
                if s.get("description"):
                    base += f" — {s['description']}"
                lines.append(base)

        if cube.get("joins"):
            lines.append("### Joins")
            for j in cube["joins"]:
                lines.append(f"- → {j['name']} ({j.get('relationship','many_to_one')})")

        lines.append("")
    return "\n".join(lines)


def _read_glossary(vertical: str) -> str:
    """Look for a vertical-specific glossary in local_test/data/<vertical>_glossary.md."""
    p = DATA_DIR / f"{vertical}_glossary.md"
    if p.exists():
        return p.read_text()
    return ""


@lru_cache(maxsize=8)
def get_bundle(vertical: str) -> dict[str, Any]:
    """Return {schema_summary, glossary, metadata} for the named vertical.

    `metadata` is a dict keyed by Cube member name (e.g. "Orders.revenue") with:
        format: "currency"|"percent"|"number"|None
        label:  human-readable label
        kind:   "measure"|"dimension"|"segment"|"time_dimension"
        synonyms: list[str]
        ai_hint: str | None
        enum_values: list[str] | None
        description: str | None
    """
    vertical_dir = CUBE_SCHEMA_ROOT / "verticals" / vertical
    if not vertical_dir.exists():
        return {
            "schema_summary": f"# Unknown vertical: {vertical}",
            "glossary": "",
            "metadata": {},
        }
    cubes = _load_cube_files(vertical_dir)
    return {
        "schema_summary": _render_summary(cubes, vertical),
        "glossary": _read_glossary(vertical),
        "metadata": _extract_metadata(cubes),
    }


def _extract_metadata(cubes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-member metadata for downstream consumers (visualizer, frontend)."""
    out: dict[str, dict[str, Any]] = {}
    for cube in cubes:
        cube_name = cube["name"]

        for d in cube.get("dimensions", []) or []:
            full = f"{cube_name}.{d['name']}"
            meta = d.get("meta", {}) or {}
            out[full] = {
                "kind": "time_dimension" if d.get("type") == "time" else "dimension",
                "type": d.get("type", "string"),
                "label": meta.get("label") or _humanize(d["name"]),
                "description": d.get("description"),
                "synonyms": meta.get("synonyms", []),
                "ai_hint": meta.get("ai_hint"),
                "enum_values": meta.get("enum_values"),
                "format": meta.get("format"),
            }

        for m in cube.get("measures", []) or []:
            full = f"{cube_name}.{m['name']}"
            meta = m.get("meta", {}) or {}
            out[full] = {
                "kind": "measure",
                "type": m.get("type", "number"),
                "label": meta.get("label") or _humanize(m["name"]),
                "description": m.get("description"),
                "synonyms": meta.get("synonyms", []),
                "ai_hint": meta.get("ai_hint"),
                "format": m.get("format"),
                "example_questions": meta.get("example_questions", []),
            }

        for s in cube.get("segments", []) or []:
            full = f"{cube_name}.{s['name']}"
            out[full] = {
                "kind": "segment",
                "label": _humanize(s["name"]),
                "description": s.get("description"),
            }
    return out


def _humanize(name: str) -> str:
    """customer_count → Customer Count, aov → AOV"""
    parts = name.split("_")
    return " ".join(p.upper() if len(p) <= 3 else p.capitalize() for p in parts)


def list_verticals() -> list[str]:
    root = CUBE_SCHEMA_ROOT / "verticals"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def reload_cache() -> None:
    get_bundle.cache_clear()
