"""Tests for the pre-execution query critic.

Covers IMPLEMENTATION_PLAN.md §0.5 bug B1: the AI omits `timeDimensions[].dateRange`
when the user's question implies a relative time window.
"""

from __future__ import annotations

import pytest

from services.ai_service.query_critic import critique_query


# ── Should fire (relative phrase + missing dateRange) ────────────────────────

@pytest.mark.parametrize("question", [
    "number of orders by region over last 3 months over time",
    "Show revenue for the last 7 days",
    "What's our MTD revenue?",
    "YTD orders per region",
    "Revenue this quarter by region",
    "Orders this year by month",
    "Revenue year-over-year by category",
    "Orders YoY",
    "Show me orders since 2026-01-01",
    "Trend over the past few weeks",
    "Order count over the last 6 months",
])
def test_relative_phrase_without_date_range_is_caught(question: str):
    msg = critique_query(question, {"measures": ["Orders.count"]})
    assert msg is not None
    assert "dateRange" in msg


def test_relative_phrase_with_dim_but_no_date_range_is_caught():
    """Time dimension is set but dateRange is missing — still wrong."""
    msg = critique_query(
        "orders by region last 3 months",
        {
            "measures": ["Orders.count"],
            "dimensions": ["Region.name"],
            "timeDimensions": [
                {"dimension": "Orders.order_date", "granularity": "month"}
            ],
        },
    )
    assert msg is not None


# ── Should NOT fire ──────────────────────────────────────────────────────────

def test_relative_phrase_with_date_range_is_fine():
    msg = critique_query(
        "number of orders by region over last 3 months over time",
        {
            "measures": ["Orders.count"],
            "dimensions": ["Region.name"],
            "timeDimensions": [
                {
                    "dimension": "Orders.order_date",
                    "dateRange": "last 3 months",
                    "granularity": "month",
                }
            ],
        },
    )
    assert msg is None


def test_no_time_phrase_is_fine():
    msg = critique_query(
        "What's our total revenue?",
        {"measures": ["LineItem.revenue"]},
    )
    assert msg is None


def test_absolute_date_range_is_fine():
    """User asks with an explicit date range; not 'relative' so we don't fire."""
    msg = critique_query(
        "Revenue from 2025-01-01 to 2025-12-31",
        {"measures": ["LineItem.revenue"]},
    )
    assert msg is None


def test_phrase_in_middle_of_sentence_is_caught():
    msg = critique_query(
        "What was the revenue trend in our top region last month and now?",
        {"measures": ["LineItem.revenue"]},
    )
    assert msg is not None
