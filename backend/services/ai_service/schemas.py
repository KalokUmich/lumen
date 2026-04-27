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


# ---------- Tool definitions (sent to Claude) ----------


def tool_definitions() -> list[dict[str, Any]]:
    """Return Anthropic-style tool definitions."""
    return [
        {
            "name": "run_cube_query",
            "description": (
                "Execute a Cube query and return rows. Use this to fetch data needed "
                "to answer the user's question. You may call this multiple times if "
                "the question requires intermediate exploration."
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
