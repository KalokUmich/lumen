"""Data profiling utilities.

Given Cube query results, compute the structural properties the visualizer
subagent needs to make a chart-pick decision: cardinalities, time presence,
distribution skew, magnitude buckets, etc.

Pure functions — no I/O. Easy to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class ColumnProfile:
    """Describes one column in a result set."""

    name: str            # raw key in the row dict, e.g. "Orders__country"
    member: str          # canonical Cube member, e.g. "Orders.country"
    role: str            # "measure" | "dimension" | "time"
    inferred_type: str   # "string" | "number" | "time" | "boolean" | "null"
    distinct_count: int = 0
    null_count: int = 0
    min: Any = None
    max: Any = None
    sample_values: list[Any] = field(default_factory=list)
    skew: str = "even"   # "even" | "long_tail" | "concentrated"


@dataclass
class DataSummary:
    """Top-level structural summary of a result set."""

    n_rows: int
    n_measures: int
    n_dimensions: int
    has_time: bool
    time_granularity: str | None
    measures: list[ColumnProfile]
    dimensions: list[ColumnProfile]
    time_dimensions: list[ColumnProfile]


def _row_key_to_member(key: str) -> str:
    """Cube column aliases use double-underscore: Orders__country → Orders.country."""
    return key.replace("__", ".") if "__" in key else key


def _classify(values: list[Any]) -> str:
    """Best-effort type inference from a sample."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "null"
    if all(isinstance(v, bool) for v in non_null):
        return "boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return "number"
    if all(isinstance(v, (date, datetime)) for v in non_null):
        return "time"
    if all(isinstance(v, str) for v in non_null):
        # Try ISO date
        try:
            datetime.fromisoformat(non_null[0])
            if all(_looks_like_iso_date(v) for v in non_null):
                return "time"
        except (ValueError, TypeError):
            pass
        return "string"
    return "mixed"


def _looks_like_iso_date(s: Any) -> bool:
    if not isinstance(s, str) or len(s) < 10:
        return False
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _skew(distinct: int, total: int, sample_value_counts: dict[Any, int]) -> str:
    """Heuristic distribution skew classification."""
    if total == 0 or distinct == 0:
        return "even"
    if not sample_value_counts:
        return "even"
    counts = sorted(sample_value_counts.values(), reverse=True)
    top = counts[0]
    if top >= total * 0.7:
        return "concentrated"
    # Long tail if top-3 hold > 60% across many distinct values
    top_3 = sum(counts[:3])
    if distinct > 10 and top_3 >= total * 0.6:
        return "long_tail"
    return "even"


def profile_column(
    rows: list[dict[str, Any]],
    column_key: str,
    role: str,
) -> ColumnProfile:
    raw_values = [r.get(column_key) for r in rows]
    non_null = [v for v in raw_values if v is not None]
    distinct = list({(v if not isinstance(v, list) else tuple(v)) for v in non_null})

    counts: dict[Any, int] = {}
    for v in non_null:
        key = v if not isinstance(v, list) else tuple(v)
        counts[key] = counts.get(key, 0) + 1

    inferred = _classify(non_null)

    min_v: Any = None
    max_v: Any = None
    if inferred in ("number", "time") and non_null:
        try:
            min_v = min(non_null)
            max_v = max(non_null)
        except TypeError:
            min_v = max_v = None

    return ColumnProfile(
        name=column_key,
        member=_row_key_to_member(column_key),
        role=role,
        inferred_type=inferred,
        distinct_count=len(distinct),
        null_count=len(raw_values) - len(non_null),
        min=min_v,
        max=max_v,
        sample_values=non_null[:5],
        skew=_skew(len(distinct), len(non_null), counts),
    )


def profile(
    rows: list[dict[str, Any]],
    cube_query: dict[str, Any],
) -> DataSummary:
    """Build a DataSummary from Cube result rows + the originating query."""
    measures_q = list(cube_query.get("measures") or [])
    dimensions_q = list(cube_query.get("dimensions") or [])
    time_dims_q = list(cube_query.get("timeDimensions") or [])

    def key(member: str) -> str:
        return member.replace(".", "__")

    measure_profiles = [profile_column(rows, key(m), "measure") for m in measures_q]
    dim_profiles = [profile_column(rows, key(d), "dimension") for d in dimensions_q]

    # Only treat a timeDimension as a time AXIS when it has a granularity.
    # A timeDimension without granularity is a date-range FILTER and shouldn't
    # cause us to render a line chart against a non-existent time column.
    axis_time_dims = [td for td in time_dims_q if td.get("granularity")]
    td_profiles = [profile_column(rows, key(td["dimension"]), "time") for td in axis_time_dims]

    granularity = axis_time_dims[0].get("granularity") if axis_time_dims else None

    return DataSummary(
        n_rows=len(rows),
        n_measures=len(measure_profiles),
        n_dimensions=len(dim_profiles),
        has_time=bool(td_profiles),
        time_granularity=granularity,
        measures=measure_profiles,
        dimensions=dim_profiles,
        time_dimensions=td_profiles,
    )
