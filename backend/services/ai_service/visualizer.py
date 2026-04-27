"""The Visualizer subagent.

Implements the canonical chart-pick algorithm from
`.claude/skills/data-viz-standards/SKILL.md` §3.

The visualizer is called between query execution and final_answer:

    cube_query → run_cube_query → data_profile → visualizer → ChartSpec → final_answer

Most queries are decided deterministically by rules. Genuine ambiguity (e.g. two
candidate chart types with similar fitness) escalates to a small LLM call using
the weak tier — the LLM has the rules in its system prompt and just picks
between the candidates with a one-line rationale.

Outputs include a `rationale` field that the chat surface can show as
"Why this chart?".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .data_profile import ColumnProfile, DataSummary, profile

# Chart types match what the frontend PlotChart can render.
ChartType = Literal[
    "big-number",
    "kpi-strip",
    "bar",
    "horizontal-bar",
    "grouped-bar",
    "stacked-bar",
    "stacked-bar-100",
    "line",
    "multi-line",
    "small-multiples-line",
    "area",
    "stacked-area",
    "sparkline",
    "bullet",
    "dot-plot",
    "scatter",
    "bubble",
    "heatmap",
    "donut",
    "treemap",
    "table",
    "empty",
]


@dataclass
class FieldRef:
    field: str
    type: str | None = None              # "time" | "ordinal" | "quantitative"
    format: str | None = None             # "number" | "currency" | "percent"
    label: str | None = None
    agg: str | None = None


@dataclass
class ColorRef:
    field: str
    palette: Literal["categorical", "sequential", "diverging"] = "categorical"


@dataclass
class FacetRef:
    row: str | None = None
    column: str | None = None


@dataclass
class ChartSpec:
    type: ChartType
    x: FieldRef | None = None
    y: FieldRef | None = None
    color: ColorRef | None = None
    size: FieldRef | None = None
    facet: FacetRef | None = None
    title: str | None = None
    subtitle: str | None = None
    annotations: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 1.0
    alt_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        # Strip empty/None to keep the wire payload small
        return {k: v for k, v in out.items() if v not in (None, [], {})}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _short_member(member: str) -> str:
    return member.split(".")[-1].replace("_", " ")


def _format_for(member: str, schema_metadata: dict[str, Any]) -> str:
    """Try to read 'format' (currency / percent / number) from schema metadata."""
    info = schema_metadata.get(member, {})
    return info.get("format") or "number"


def _label_for(member: str, schema_metadata: dict[str, Any]) -> str:
    info = schema_metadata.get(member, {})
    return info.get("label") or _short_member(member).title()


# ── Title generators ──────────────────────────────────────────────────────────


def _title_for(
    summary: DataSummary,
    schema_metadata: dict[str, Any],
) -> str:
    if summary.n_measures == 1 and summary.n_dimensions == 0 and not summary.has_time:
        return _label_for(summary.measures[0].member, schema_metadata)
    if summary.n_measures >= 1 and summary.has_time:
        m = _label_for(summary.measures[0].member, schema_metadata)
        return f"{m} over time"
    if summary.n_measures >= 1 and summary.n_dimensions >= 1:
        m = _label_for(summary.measures[0].member, schema_metadata)
        d = _label_for(summary.dimensions[0].member, schema_metadata)
        return f"{m} by {d}"
    return "Result"


def _alt_text_for(spec: ChartSpec, summary: DataSummary) -> str:
    if spec.type == "big-number":
        return f"Single value: {spec.title or 'measure'}"
    if spec.type in ("line", "multi-line", "small-multiples-line", "sparkline", "area", "stacked-area"):
        return f"{spec.type.replace('-', ' ').title()} with {summary.n_rows} time points"
    if spec.type in ("bar", "horizontal-bar", "grouped-bar", "stacked-bar", "stacked-bar-100", "dot-plot"):
        return f"{spec.type.replace('-', ' ').title()} comparing {summary.n_rows} categories"
    if spec.type == "scatter" or spec.type == "bubble":
        return f"{spec.type.title()} of {summary.n_rows} points"
    if spec.type == "heatmap":
        return f"Heatmap with {summary.n_rows} cells"
    if spec.type == "donut":
        return f"Donut chart with {summary.n_rows} slices"
    if spec.type == "treemap":
        return f"Treemap with {summary.n_rows} categories"
    return f"{spec.type.replace('-', ' ').title()} with {summary.n_rows} rows"


# ── The decision tree (§3 of the skill) ───────────────────────────────────────


def _decide_chart_type(
    summary: DataSummary,
    intent_hint: str | None,
) -> tuple[ChartType, str, float]:
    """Return (chart_type, rationale, confidence). Confidence < 0.7 means the
    main loop may want to consult the LLM tiebreak."""

    if summary.n_rows == 0:
        return "empty", "Query returned 0 rows; nothing to render.", 1.0

    M = summary.n_measures
    D = summary.n_dimensions
    T = summary.has_time

    # ── Single value ──────────────────────────────────────────────────────
    if M == 1 and D == 0 and not T and summary.n_rows == 1:
        return "big-number", "One measure, one row → big number (intent=magnitude).", 1.0

    # ── KPI strip: multiple measures, single row ─────────────────────────
    if M > 1 and D == 0 and not T and summary.n_rows == 1:
        return "kpi-strip", f"{M} measures, single row → KPI strip.", 1.0

    # ── Time series ──────────────────────────────────────────────────────
    if T:
        if M == 1 and D == 0:
            if summary.n_rows < 5:
                return "bar", "Time series with very few points; bar reads more clearly than a sparse line.", 0.9
            return "line", "One measure over time → line (intent=change).", 1.0

        if M == 1 and D == 1:
            card = summary.dimensions[0].distinct_count
            if card <= 5:
                return "multi-line", f"One measure × time × dim (card={card}); ≤5 series fit on one chart.", 1.0
            if card <= 12:
                return "small-multiples-line", f"One measure × time × dim (card={card}); >5 series → small multiples to avoid spaghetti.", 0.95
            return "small-multiples-line", f"One measure × time × dim (card={card}); too many series — top 12 + Other.", 0.8

        if M >= 2 and D == 0:
            # Multiple measures over time. Same units → multi-line; otherwise small multiples (no dual axis).
            return "small-multiples-line", f"{M} measures over time → small multiples (we never use dual y-axis; see §9 of the skill).", 0.9

        if M >= 2 and D >= 1:
            return "small-multiples-line", "Multiple measures + time + dim → small multiples; complex shape best decomposed.", 0.7

    # ── Comparison / composition (no time) ───────────────────────────────
    if M == 1 and D == 1 and not T:
        card = summary.dimensions[0].distinct_count
        if intent_hint == "composition":
            if card <= 6:
                return "donut", f"composition intent + {card} slices ≤ 6 → donut acceptable.", 0.9
            if card <= 20:
                return "stacked-bar-100", f"composition intent + {card} parts → 100% stacked bar.", 0.85
            return "treemap", f"composition intent + {card} parts → treemap.", 0.8

        if card == 1:
            return "big-number", "Single category — equivalent to a single value.", 1.0
        if card <= 30:
            return "bar", f"One measure × one dim (card={card}) → bar chart, sorted descending.", 1.0
        return "bar", f"One measure × one dim (card={card}) → bar with top-N + Other.", 0.85

    if M == 1 and D == 2 and not T:
        c0 = summary.dimensions[0].distinct_count
        c1 = summary.dimensions[1].distinct_count
        if max(c0, c1) <= 12 and min(c0, c1) <= 12:
            return "heatmap", f"One measure × two dims ({c0}×{c1}) → heatmap.", 0.95
        if min(c0, c1) <= 5:
            return "grouped-bar", f"One measure × two dims, inner cardinality {min(c0,c1)} ≤ 5 → grouped bar.", 0.85
        return "table", "One measure × two high-cardinality dims → table; chart would overplot.", 0.8

    # ── Composition with multiple measures (e.g. revenue + cost stacked) ──
    if M >= 2 and D == 1 and not T and intent_hint == "composition":
        return "stacked-bar", f"{M} measures × one dim, composition intent → stacked bar.", 0.9

    # ── Relationship ─────────────────────────────────────────────────────
    if M == 2 and D == 0 and not T:
        return "scatter", "Two measures, no dim → scatter (intent=relationship).", 1.0
    if M == 2 and D == 1 and not T:
        return "scatter", "Two measures + categorical dim → scatter colored by dim.", 0.95
    if M == 3 and D <= 1 and not T:
        return "bubble", "Three measures → bubble (x, y, size).", 0.9

    # ── Fallback ─────────────────────────────────────────────────────────
    return "table", f"No clean chart for {M}m × {D}d (time={T}); falling back to table.", 0.6


# ── Public API ────────────────────────────────────────────────────────────────


def select_visualization(
    cube_query: dict[str, Any],
    rows: list[dict[str, Any]],
    schema_metadata: dict[str, Any] | None = None,
    intent_hint: str | None = None,
    *,
    period_subtitle: str | None = None,
) -> ChartSpec:
    """Run the deterministic chart-pick. Returns a fully-specified ChartSpec."""
    schema_metadata = schema_metadata or {}
    summary = profile(rows, cube_query)
    chart_type, rationale, confidence = _decide_chart_type(summary, intent_hint)

    spec = _build_chart_spec(chart_type, summary, schema_metadata, rationale, confidence)
    spec.title = _title_for(summary, schema_metadata)
    spec.subtitle = period_subtitle
    spec.alt_text = _alt_text_for(spec, summary)
    return spec


def _build_chart_spec(
    chart_type: ChartType,
    summary: DataSummary,
    schema_metadata: dict[str, Any],
    rationale: str,
    confidence: float,
) -> ChartSpec:
    spec = ChartSpec(type=chart_type, rationale=rationale, confidence=confidence)

    # Single measure / dim setup
    primary_measure = summary.measures[0] if summary.measures else None
    primary_dim = summary.dimensions[0] if summary.dimensions else None
    primary_time = summary.time_dimensions[0] if summary.time_dimensions else None

    if primary_measure:
        spec.y = FieldRef(
            field=primary_measure.name,
            format=_format_for(primary_measure.member, schema_metadata),
            label=_label_for(primary_measure.member, schema_metadata),
        )

    if chart_type == "big-number":
        return spec

    if chart_type == "kpi-strip":
        # x repurposed as the "measure list" anchor; frontend renders one tile per measure
        return spec

    if chart_type in ("line", "multi-line", "small-multiples-line", "sparkline", "area", "stacked-area"):
        if primary_time:
            spec.x = FieldRef(field=primary_time.name, type="time", label=_label_for(primary_time.member, schema_metadata))
        if chart_type in ("multi-line", "small-multiples-line") and primary_dim:
            if chart_type == "small-multiples-line":
                spec.facet = FacetRef(column=primary_dim.name)
            else:
                spec.color = ColorRef(field=primary_dim.name, palette="categorical")
        return spec

    if chart_type in ("bar", "horizontal-bar", "dot-plot"):
        if primary_dim:
            spec.x = FieldRef(field=primary_dim.name, type="ordinal", label=_label_for(primary_dim.member, schema_metadata))
        if primary_dim and primary_dim.distinct_count > 8:
            spec.type = "horizontal-bar"
        return spec

    if chart_type == "grouped-bar":
        if primary_dim:
            spec.x = FieldRef(field=primary_dim.name, type="ordinal", label=_label_for(primary_dim.member, schema_metadata))
        if len(summary.dimensions) >= 2:
            spec.color = ColorRef(field=summary.dimensions[1].name, palette="categorical")
        return spec

    if chart_type in ("stacked-bar", "stacked-bar-100"):
        if primary_dim:
            spec.x = FieldRef(field=primary_dim.name, type="ordinal", label=_label_for(primary_dim.member, schema_metadata))
        if len(summary.dimensions) >= 2:
            spec.color = ColorRef(field=summary.dimensions[1].name, palette="categorical")
        elif len(summary.measures) >= 2:
            # Multiple measures stacked — color by measure (frontend handles)
            spec.color = ColorRef(field="__measure__", palette="categorical")
        return spec

    if chart_type == "heatmap":
        if len(summary.dimensions) >= 2:
            spec.x = FieldRef(field=summary.dimensions[0].name, type="ordinal")
            spec.y = FieldRef(field=summary.dimensions[1].name, type="ordinal")
            if primary_measure:
                spec.color = ColorRef(field=primary_measure.name, palette="sequential")
        return spec

    if chart_type == "donut":
        # Donut needs a color (the categorical) and a measure (the angle/size)
        if primary_dim:
            spec.color = ColorRef(field=primary_dim.name, palette="categorical")
        return spec

    if chart_type == "treemap":
        if primary_dim:
            spec.color = ColorRef(field=primary_dim.name, palette="categorical")
        return spec

    if chart_type in ("scatter", "bubble"):
        if len(summary.measures) >= 2:
            spec.x = FieldRef(
                field=summary.measures[0].name,
                format=_format_for(summary.measures[0].member, schema_metadata),
                label=_label_for(summary.measures[0].member, schema_metadata),
            )
            spec.y = FieldRef(
                field=summary.measures[1].name,
                format=_format_for(summary.measures[1].member, schema_metadata),
                label=_label_for(summary.measures[1].member, schema_metadata),
            )
        if chart_type == "bubble" and len(summary.measures) >= 3:
            spec.size = FieldRef(field=summary.measures[2].name, label=_label_for(summary.measures[2].member, schema_metadata))
        if primary_dim:
            spec.color = ColorRef(field=primary_dim.name, palette="categorical")
        return spec

    if chart_type == "bullet":
        # Single measure with target reference; frontend reads from y.field
        return spec

    # Table, empty: no encodings needed
    return spec


# ── Optional LLM tiebreak (used when confidence < 0.7) ────────────────────────


async def llm_tiebreak(
    candidates: list[ChartSpec],
    summary: DataSummary,
    user_question: str,
    provider,
    tier: str = "weak",
) -> ChartSpec:
    """For ambiguous cases. Asks the weak tier to pick between candidate specs.

    Currently we don't actually *generate* multiple candidates — we just enrich
    the existing pick with a small explanation. This function is wired up
    for the future when the decision tree returns a tied set.
    """
    # v1: the deterministic algorithm always returns one. This is a stub for
    # future expansion when decide_chart_type returns multiple candidates.
    return candidates[0] if candidates else ChartSpec(type="table", rationale="fallback")
