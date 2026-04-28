"""Query-shape critic — runs *before* a Cube query is executed.

Catches cases where the LLM produced a syntactically valid Cube query that
nevertheless mismatches the user's intent in ways the warehouse can't catch.
The check returns a corrective message; the stream loop forwards it to the
model as a tool error so the next hop self-corrects.

Bug B1 from IMPLEMENTATION_PLAN.md §0.5: relative-time phrases ("last 3
months", "MTD", "this year") must be expressed as `timeDimensions[].dateRange`,
not as a free-text filter. We catch the omission here.
"""

from __future__ import annotations

import re
from typing import Any

# Phrases that obligate a `timeDimensions[].dateRange` in the query.
# Matched case-insensitive, word-boundaried. Order doesn't matter.
_RELATIVE_TIME_PATTERNS = [
    re.compile(r"\blast\s+\d+\s+(day|week|month|quarter|year)s?\b", re.IGNORECASE),
    re.compile(r"\b(last|past|previous)\s+(day|week|month|quarter|year)\b", re.IGNORECASE),
    re.compile(r"\b(this|current)\s+(day|week|month|quarter|year)\b", re.IGNORECASE),
    re.compile(r"\b(MTD|YTD|QTD|WTD)\b", re.IGNORECASE),
    re.compile(r"\byear[\s-]over[\s-]year\b|\bYoY\b", re.IGNORECASE),
    re.compile(r"\bmonth[\s-]over[\s-]month\b|\bMoM\b", re.IGNORECASE),
    re.compile(r"\bsince\s+(yesterday|last\s+\w+|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE),
    re.compile(r"\bover\s+the\s+(last|past)\s+(few|several|\d+)\s+(day|week|month|quarter|year)s?\b", re.IGNORECASE),
]


def _question_implies_relative_time(question: str) -> bool:
    return any(p.search(question) for p in _RELATIVE_TIME_PATTERNS)


def _query_has_date_range(cube_query: dict[str, Any]) -> bool:
    tds = cube_query.get("timeDimensions") or []
    return any((td or {}).get("dateRange") for td in tds)


def check_relative_time_filter(question: str, cube_query: dict[str, Any]) -> str | None:
    """If the user asked for a relative time window but the query has no
    `dateRange`, return a corrective message. Otherwise None.
    """
    if not _question_implies_relative_time(question):
        return None
    if _query_has_date_range(cube_query):
        return None
    return (
        "Your query is missing a time filter, but the user's question implies a "
        "relative time window (e.g. 'last 3 months', 'this year', 'YTD'). Re-emit "
        "the run_cube_query tool call with a `timeDimensions` entry whose "
        "`dateRange` matches the phrase verbatim, e.g.:\n"
        '  "timeDimensions": [{"dimension": "<TimeDimension>", '
        '"dateRange": "last 3 months", "granularity": "month"}]\n'
        "Use the time dimension that fits the measure (e.g. Orders.order_date for "
        "order counts, LineItem.ship_date for shipped revenue). Pick a granularity "
        "consistent with the requested window: day for ≤14d, week for ≤90d, month "
        "for ≤2y, quarter or year beyond that."
    )


# All checks run in order. Each returns Optional[str] — first non-None wins.
_CHECKS = [
    check_relative_time_filter,
]


def critique_query(question: str, cube_query: dict[str, Any]) -> str | None:
    """Run pre-execution critics. Returns the first violation message, or None."""
    for check in _CHECKS:
        msg = check(question, cube_query)
        if msg:
            return msg
    return None
