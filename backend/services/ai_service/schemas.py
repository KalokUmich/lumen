"""Pydantic schemas for the AI service.

These define the *contract* between Claude (via tool use) and our backend.
Claude returns these as JSON; we validate before executing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------- Cube query (the canonical structured query) ----------


class TimeDimension(BaseModel):
    dimension: str
    granularity: Literal["second", "minute", "hour", "day", "week", "month", "quarter", "year"] | None = None
    dateRange: str | list[str] | None = None  # noqa: N815 — Cube uses camelCase


class Filter(BaseModel):
    member: str
    operator: Literal[
        "equals", "notEquals", "contains", "notContains",
        "gt", "gte", "lt", "lte", "set", "notSet",
        "inDateRange", "notInDateRange",
    ]
    values: list[str | int | float] | None = None


class CubeQuery(BaseModel):
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    timeDimensions: list[TimeDimension] = Field(default_factory=list)  # noqa: N815
    filters: list[Filter] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    order: dict[str, Literal["asc", "desc"]] | None = None
    limit: int | None = Field(default=None, ge=1, le=10_000)


# ---------- Chart spec (what the frontend renders) ----------


class FieldRef(BaseModel):
    field: str
    type: Literal["time", "ordinal", "quantitative"] | None = None
    agg: Literal["sum", "avg", "count"] | None = None
    format: Literal["number", "currency", "percent"] | None = None
    label: str | None = None


class ColorRef(BaseModel):
    field: str
    palette: Literal["categorical", "sequential", "diverging"] = "categorical"


class ChartSpec(BaseModel):
    type: Literal["line", "bar", "area", "scatter", "heatmap", "pie", "big-number", "table"]
    x: FieldRef | None = None
    y: FieldRef | None = None
    color: ColorRef | None = None
    facet: dict[str, str] | None = None
    title: str | None = None


# ---------- Tool inputs ----------


class FinalAnswerInput(BaseModel):
    text: str = Field(..., description="Natural language summary for the user")
    cube_query: CubeQuery
    chart_spec: ChartSpec
    chart_type_override: str | None = Field(
        default=None,
        description=(
            "Optional override of the visualizer's chart type. ONLY set when the "
            "user explicitly asked for a specific chart (e.g. 'show as a line chart', "
            "'as a donut'). The visualizer normally picks the best chart based on "
            "data shape; respect that default unless the user requests otherwise. "
            "Allowed values: bar, line, area, scatter, donut, treemap, table, "
            "big-number, heatmap, stacked-bar, multi-line."
        ),
    )


class AskClarificationInput(BaseModel):
    question: str = Field(..., description="A targeted question to disambiguate the user's request")


class DataframeTransformInput(BaseModel):
    """Input schema for the v2 Pandas transform escape hatch.

    See `.claude/skills/data-transform/SKILL.md` for the full routing rule.
    The runtime that consumes this input is the `pandas_runner` service (not yet
    implemented); this schema is shipped early so the LLM-facing contract is
    stable and reviewable in PRs.
    """

    cube_query: CubeQuery = Field(
        ..., description="The source query — fetches the DataFrame the transform operates on. Must include all filters/dimensions; do not filter inside the Pandas code."
    )
    pandas_code: str = Field(
        ...,
        description=(
            "Python snippet that mutates `df` and assigns the final DataFrame to `result`. "
            "Available in scope: df, pd, np. Banned: any import, any I/O, any network."
        ),
    )
    intent: Literal[
        "rolling_window",
        "cohort_matrix",
        "reshape",
        "statistics",
        "multi_source",
    ] = Field(
        ...,
        description=(
            "Which of the five allowed transform categories this code falls under. "
            "Required for audit and routing-accuracy evaluation."
        ),
    )


# ---------- Tool definitions (sent to Claude) ----------


def tool_definitions(*, enable_dataframe_transform: bool = False) -> list[dict[str, Any]]:
    """Return Anthropic-style tool definitions.

    `enable_dataframe_transform` is a feature flag — keep this off until the
    sandbox + resource limits described in `.claude/skills/data-transform/SKILL.md`
    §8 are implemented and reviewed. The tool description is already tuned for
    routing accuracy; do not exclude it lightly even when behind the flag.
    """
    tools: list[dict[str, Any]] = [
        {
            "name": "run_cube_query",
            "description": (
                "Run a query against the Cube semantic layer. THIS IS THE DEFAULT for any "
                "analytical question. Use it for: aggregation (sum/count/avg/median), group-by, "
                "filtering, joins, time-series with day/week/month/quarter/year granularity, "
                "top-N / bottom-N, ratios that are already declared as measures, period-over-period "
                "(express via two queries with different dateRanges), and any question expressible "
                "in the Cube schema. You may call this multiple times for intermediate exploration. "
                "Do NOT use the Pandas transform tool when this tool can answer the question."
            ),
            "input_schema": CubeQuery.model_json_schema(),
        },
        {
            "name": "ask_clarification",
            "description": (
                "Ask the user a single targeted clarifying question. Use only when the "
                "request is genuinely ambiguous and you cannot make a reasonable assumption."
            ),
            "input_schema": AskClarificationInput.model_json_schema(),
        },
        {
            "name": "final_answer",
            "description": (
                "Provide the final answer to the user. Always call this once you have "
                "the data you need. Includes a text summary, the final cube_query used, "
                "and a chart_spec describing how to visualize the result."
            ),
            "input_schema": FinalAnswerInput.model_json_schema(),
        },
    ]

    if enable_dataframe_transform:
        tools.append(
            {
                "name": "run_dataframe_transform",
                "description": (
                    "Run a Pandas transform on top of a Cube query result. USE ONLY when the "
                    "question requires one of the following operations that Cube cannot express:\n"
                    "  1. Rolling / sliding window (e.g. 7-day moving average, trailing 12-month stat)\n"
                    "  2. Cohort / retention matrix (acquisition × tenure)\n"
                    "  3. Reshape: pivot / melt / stack / unstack\n"
                    "  4. Non-trivial statistics: percentile rank, z-score, correlation matrix, "
                    "regression, outlier detection\n"
                    "  5. Multi-source DataFrame ops the Cube schema doesn't model\n\n"
                    "If the question is plain aggregation, group-by, filter, join, or top-N — use "
                    "run_cube_query instead. The bar to use this tool is HIGH. When in doubt, prefer "
                    "run_cube_query.\n\n"
                    "Provide:\n"
                    "  - cube_query: the query that fetches the source data (must already include "
                    "all filters/dimensions you need; do not filter inside Pandas).\n"
                    "  - pandas_code: a self-contained Python snippet that mutates `df` and assigns "
                    "the final DataFrame to `result`. Available in scope: df, pd, np. Banned: any "
                    "import, any I/O, any network. CPU/memory/timeout limits are hard.\n"
                    "  - intent: which of the 5 categories above this transform falls under."
                ),
                "input_schema": DataframeTransformInput.model_json_schema(),
            }
        )

    return tools
