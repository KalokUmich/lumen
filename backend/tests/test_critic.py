"""Tests for the aesthetic critic.

Verifies each rule fires correctly + produces the right auto-fix or warning.
"""

from __future__ import annotations

import pytest

from services.ai_service.critic import critique
from services.ai_service.data_profile import ColumnProfile, DataSummary
from services.ai_service.visualizer import ChartSpec, FieldRef


def _summary(
    n_rows: int = 5,
    measures: list[ColumnProfile] | None = None,
    dimensions: list[ColumnProfile] | None = None,
    has_time: bool = False,
) -> DataSummary:
    return DataSummary(
        n_rows=n_rows,
        n_measures=len(measures) if measures else 0,
        n_dimensions=len(dimensions) if dimensions else 0,
        has_time=has_time,
        time_granularity=None,
        measures=measures or [],
        dimensions=dimensions or [],
        time_dimensions=[],
    )


def _dim(name: str, values: list, distinct_count: int | None = None) -> ColumnProfile:
    return ColumnProfile(
        name=name,
        member=name.replace("__", "."),
        role="dimension",
        inferred_type="string",
        distinct_count=distinct_count if distinct_count is not None else len(values),
        sample_values=values[:5],
    )


def test_dense_categorical_axis_fix():
    """Bar with >8 categories or long labels → switch to horizontal-bar."""
    spec = ChartSpec(
        type="bar",
        x=FieldRef(field="Nation__name", type="ordinal", label="Nation"),
        y=FieldRef(field="LineItem__revenue", format="currency", label="Revenue"),
    )
    dim = _dim("Nation__name", ["MOZAMBIQUE", "INDONESIA", "ETHIOPIA"], distinct_count=10)
    summary = _summary(n_rows=10, dimensions=[dim])

    new_spec, report = critique(spec, summary, {})

    assert new_spec.type == "horizontal-bar"
    assert "dense_categorical_axis" in report.fixes_applied
    assert any(i.rule_id == "dense_categorical_axis" for i in report.issues)


def test_dense_categorical_axis_no_fix_for_short_few():
    """Bar with ≤8 short labels → leave as bar."""
    spec = ChartSpec(
        type="bar",
        x=FieldRef(field="Region__name", type="ordinal"),
        y=FieldRef(field="LineItem__revenue"),
    )
    dim = _dim("Region__name", ["ASIA", "EUROPE", "AMERICA"], distinct_count=5)
    summary = _summary(n_rows=5, dimensions=[dim])

    new_spec, report = critique(spec, summary, {})

    assert new_spec.type == "bar"  # unchanged
    assert "dense_categorical_axis" not in report.fixes_applied


def test_pie_too_many_slices_to_treemap():
    """Donut with >12 slices → treemap."""
    spec = ChartSpec(type="donut", y=FieldRef(field="value"))
    summary = _summary(n_rows=15)

    new_spec, report = critique(spec, summary, {})

    assert new_spec.type == "treemap"
    assert "pie_too_many_slices" in report.fixes_applied


def test_pie_too_many_slices_to_bar():
    """Donut with 7-12 slices → bar (treemap reserved for >12)."""
    spec = ChartSpec(type="donut", y=FieldRef(field="value"))
    summary = _summary(n_rows=8)

    new_spec, report = critique(spec, summary, {})

    assert new_spec.type == "bar"
    assert "pie_too_many_slices" in report.fixes_applied


def test_pie_six_slices_unchanged():
    spec = ChartSpec(type="donut", y=FieldRef(field="value"))
    summary = _summary(n_rows=6)

    new_spec, report = critique(spec, summary, {})

    assert new_spec.type == "donut"
    assert "pie_too_many_slices" not in report.fixes_applied


def test_missing_caption_for_codes_filled_from_ai_hint():
    """X-axis has abbreviated codes (R/A/N) AND schema has ai_hint → fix."""
    spec = ChartSpec(
        type="bar",
        x=FieldRef(field="LineItem__return_flag", type="ordinal"),
        y=FieldRef(field="LineItem__count"),
    )
    dim = _dim("LineItem__return_flag", ["R", "A", "N"])
    summary = _summary(n_rows=3, dimensions=[dim])
    metadata = {
        "LineItem.return_flag": {
            "ai_hint": "R = returned, A = accepted, N = not yet returned",
            "enum_values": ["R", "A", "N"],
        }
    }

    new_spec, report = critique(spec, summary, metadata)

    assert new_spec.caption == "R = returned, A = accepted, N = not yet returned"
    assert "missing_caption_for_codes" in report.fixes_applied


def test_missing_caption_warns_when_no_ai_hint():
    """Abbreviated codes but no ai_hint → warning (no fix)."""
    spec = ChartSpec(
        type="bar",
        x=FieldRef(field="X__code"),
        y=FieldRef(field="Y__count"),
    )
    dim = _dim("X__code", ["A", "B", "C"])
    summary = _summary(n_rows=3, dimensions=[dim])
    metadata = {"X.code": {"enum_values": ["A", "B", "C"]}}

    _new_spec, report = critique(spec, summary, metadata)

    issue = next(i for i in report.issues if i.rule_id == "missing_caption_for_codes")
    assert issue.severity == "warn"
    assert issue.action == "warn"


def test_dot_plot_zoom_caption_added():
    """Dot-plot without caption → critic adds explanatory caption."""
    spec = ChartSpec(
        type="dot-plot",
        x=FieldRef(field="Region__name"),
        y=FieldRef(field="value", format="currency"),
    )
    dim = _dim("Region__name", ["ASIA", "EUROPE", "AMERICA"])
    summary = _summary(n_rows=3, dimensions=[dim])

    new_spec, report = critique(spec, summary, {})

    assert new_spec.caption is not None
    assert "non-zero baseline" in new_spec.caption.lower()
    assert "dot_plot_zoom_caption" in report.fixes_applied


def test_redundant_color_logged_not_fixed():
    """Color same as x is allowed (skill §4.2.2) but logged for audit."""
    spec = ChartSpec(
        type="bar",
        x=FieldRef(field="Region__name"),
        y=FieldRef(field="value"),
        color=__import__("services.ai_service.visualizer", fromlist=["ColorRef"]).ColorRef(
            field="Region__name", palette="categorical"
        ),
    )
    summary = _summary(n_rows=5)

    new_spec, report = critique(spec, summary, {})

    assert new_spec.color is not None  # not removed
    issue = next(i for i in report.issues if i.rule_id == "redundant_color")
    assert issue.action == "log"


def test_critic_idempotent():
    """Running the critic twice should produce the same result (no double-fixes)."""
    spec = ChartSpec(type="donut", y=FieldRef(field="value"))
    summary = _summary(n_rows=15)

    once, _ = critique(spec, summary, {})
    twice, report = critique(once, summary, {})

    assert twice.type == once.type == "treemap"
    # No further fixes needed
    assert "pie_too_many_slices" not in report.fixes_applied
