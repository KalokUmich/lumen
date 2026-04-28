"""Aesthetic critic — v0.

Runs after the deterministic visualizer. Applies a battery of rules to detect
chart-quality problems the rule-based picker can't catch on its own (label
overlap risk, low-contrast palette choices, suspiciously dense layouts,
missing captions for abbreviated values, etc.). Each rule produces an *issue*
with optional auto-fix instructions.

Architecture per the v2/v3 roadmap (IMPLEMENTATION_PLAN §16.6):
- v0 (this file): rule-based, deterministic, runs synchronously, ~free
- v1: weak-tier LLM critic for ambiguous cases not covered by rules
- v2: LangGraph multi-agent (visualizer ↔ critic patch loop, with retries)

The critic emits structured `CriticReport` so:
- Patch-able issues are auto-applied (e.g. switch bar→horizontal-bar when
  label overlap risk is high)
- Other issues are logged for offline review (training data for new rules)
- The frontend can surface a "Why this chart?" tooltip with the critic's
  rationale alongside the visualizer's
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .data_profile import DataSummary
from .visualizer import ChartSpec, ColorRef, FieldRef


Severity = Literal["info", "warn", "error"]
Action = Literal["fix", "warn", "log"]


@dataclass
class CriticIssue:
    rule_id: str
    severity: Severity
    message: str
    action: Action
    fix_summary: str = ""


@dataclass
class CriticReport:
    issues: list[CriticIssue] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)

    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def has_warnings(self) -> bool:
        return any(i.severity == "warn" for i in self.issues)


# ── Rules ─────────────────────────────────────────────────────────────────────


def _rule_dense_categorical_axis(
    spec: ChartSpec, summary: DataSummary, schema_metadata: dict[str, Any]
) -> tuple[list[CriticIssue], ChartSpec]:
    """Detect bar charts with too many categories → either too many bars or
    label-overlap risk. Auto-fix by switching to horizontal-bar."""
    issues: list[CriticIssue] = []
    if spec.type != "bar":
        return issues, spec
    if not summary.dimensions:
        return issues, spec
    dim = summary.dimensions[0]
    avg_label_len = (
        sum(len(str(v)) for v in dim.sample_values) / max(1, len(dim.sample_values))
    )
    if dim.distinct_count > 8 or avg_label_len > 10:
        new_spec = ChartSpec(**{**spec.__dict__})
        new_spec.type = "horizontal-bar"
        issues.append(
            CriticIssue(
                rule_id="dense_categorical_axis",
                severity="warn",
                message=f"Vertical bar with {dim.distinct_count} categories "
                f"and avg label length {avg_label_len:.0f} chars would overlap.",
                action="fix",
                fix_summary="Switched to horizontal-bar (labels read more clearly when long).",
            )
        )
        return issues, new_spec
    return issues, spec


def _rule_pie_too_many_slices(
    spec: ChartSpec, summary: DataSummary, _schema_metadata: dict[str, Any]
) -> tuple[list[CriticIssue], ChartSpec]:
    """Donut/pie with more than 6 slices is unreadable per skill §4.13.
    Auto-fix: switch to bar (or treemap if >12)."""
    issues: list[CriticIssue] = []
    if spec.type != "donut":
        return issues, spec
    if summary.n_rows <= 6:
        return issues, spec
    new_spec = ChartSpec(**{**spec.__dict__})
    new_spec.type = "treemap" if summary.n_rows > 12 else "bar"
    issues.append(
        CriticIssue(
            rule_id="pie_too_many_slices",
            severity="warn",
            message=f"Donut with {summary.n_rows} slices is unreadable; angles are indistinguishable past 6.",
            action="fix",
            fix_summary=f"Switched to {new_spec.type} per skill §4.13.",
        )
    )
    return issues, new_spec


def _rule_missing_caption_for_codes(
    spec: ChartSpec, summary: DataSummary, schema_metadata: dict[str, Any]
) -> tuple[list[CriticIssue], ChartSpec]:
    """X-axis with abbreviated codes (R/A/N) but no caption explaining them."""
    issues: list[CriticIssue] = []
    if not spec.x or not spec.x.field or spec.caption:
        return issues, spec
    dim = next((d for d in summary.dimensions if d.name == spec.x.field), None)
    if not dim:
        return issues, spec
    avg_len = (
        sum(len(str(v)) for v in dim.sample_values) / max(1, len(dim.sample_values))
    )
    if avg_len < 4 and dim.sample_values:
        # Try to populate caption from schema metadata
        info = schema_metadata.get(dim.member, {})
        ai_hint = info.get("ai_hint")
        enum_values = info.get("enum_values")
        if ai_hint:
            new_spec = ChartSpec(**{**spec.__dict__})
            new_spec.caption = ai_hint
            issues.append(
                CriticIssue(
                    rule_id="missing_caption_for_codes",
                    severity="info",
                    message=f"X-axis '{dim.member}' has abbreviated codes; added caption from schema ai_hint.",
                    action="fix",
                    fix_summary=f"Caption: {ai_hint}",
                )
            )
            return issues, new_spec
        elif enum_values:
            issues.append(
                CriticIssue(
                    rule_id="missing_caption_for_codes",
                    severity="warn",
                    message=f"X-axis '{dim.member}' has abbreviated codes but schema has no ai_hint to explain them.",
                    action="warn",
                )
            )
    return issues, spec


def _rule_zero_baseline_for_bars(
    spec: ChartSpec, _summary: DataSummary, _schema_metadata: dict[str, Any]
) -> tuple[list[CriticIssue], ChartSpec]:
    """Bar charts must zero-base. The Plot config does this, but if anything
    sets a manual y domain we should flag it."""
    if spec.type not in ("bar", "horizontal-bar", "stacked-bar", "stacked-bar-100"):
        return [], spec
    # No way for the spec to override y domain in our current shape, but we
    # log that the rule was checked (audit trail).
    return [], spec


def _rule_caption_dot_plot_zoom(
    spec: ChartSpec, summary: DataSummary, _schema_metadata: dict[str, Any]
) -> tuple[list[CriticIssue], ChartSpec]:
    """Add a caption to dot-plots explaining the non-zero baseline so users
    don't misread the zoomed scale."""
    if spec.type != "dot-plot":
        return [], spec
    if spec.caption:
        return [], spec
    new_spec = ChartSpec(**{**spec.__dict__})
    new_spec.caption = (
        "Note: y-axis is zoomed (non-zero baseline) because values are tightly clustered. "
        "Position encodes value, not bar length."
    )
    return [
        CriticIssue(
            rule_id="dot_plot_zoom_caption",
            severity="info",
            message="Dot-plot uses non-zero baseline; added explanatory caption.",
            action="fix",
            fix_summary=new_spec.caption,
        )
    ], new_spec


def _rule_redundant_color(
    spec: ChartSpec, _summary: DataSummary, _schema_metadata: dict[str, Any]
) -> tuple[list[CriticIssue], ChartSpec]:
    """If color encodes the same field as x (purely cosmetic), warn but allow
    — this is the §4.2.2 categorical-color allowance for low-cardinality bars."""
    if not spec.color or not spec.x:
        return [], spec
    if spec.color.field == spec.x.field:
        return [
            CriticIssue(
                rule_id="redundant_color",
                severity="info",
                message=f"Color encodes the same field as x ({spec.x.field}). "
                f"Allowed by skill §4.2.2 for low-cardinality bars; logged for review.",
                action="log",
            )
        ], spec
    return [], spec


_ALL_RULES = [
    _rule_dense_categorical_axis,
    _rule_pie_too_many_slices,
    _rule_missing_caption_for_codes,
    _rule_caption_dot_plot_zoom,
    _rule_zero_baseline_for_bars,
    _rule_redundant_color,
]


def critique(
    spec: ChartSpec,
    summary: DataSummary,
    schema_metadata: dict[str, Any] | None = None,
) -> tuple[ChartSpec, CriticReport]:
    """Run all critic rules against a candidate spec.

    Returns (possibly-patched spec, report). Auto-fixes are applied in order;
    report.fixes_applied lists rule_ids that mutated the spec.
    """
    schema_metadata = schema_metadata or {}
    report = CriticReport()

    for rule in _ALL_RULES:
        rule_issues, new_spec = rule(spec, summary, schema_metadata)
        for issue in rule_issues:
            report.issues.append(issue)
            if issue.action == "fix" and new_spec is not spec:
                report.fixes_applied.append(issue.rule_id)
                spec = new_spec

    return spec, report
