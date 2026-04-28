"""Skill §13a R11 / §4.3.1: low-N time × low-N category → grouped bar, not multi-line.

Repro for IMPLEMENTATION_PLAN.md §0.5 bug B2.
"""

from __future__ import annotations

from services.ai_service.visualizer import select_visualization


def _short_period_rows() -> list[dict]:
    """3 months × 5 regions = 15 rows (the canonical bug-B2 shape)."""
    months = ["2026-02-01", "2026-03-01", "2026-04-01"]
    regions = ["AFRICA", "AMERICA", "ASIA", "EUROPE", "MIDDLE EAST"]
    rows: list[dict] = []
    for i, m in enumerate(months):
        for j, r in enumerate(regions):
            rows.append({
                "Orders__order_date": m,
                "Region__name": r,
                "Orders__count": 100 + i * 5 + j,
            })
    return rows


def test_three_periods_five_categories_returns_grouped_bar():
    cube_query = {
        "measures": ["Orders.count"],
        "dimensions": ["Region.name"],
        "timeDimensions": [
            {
                "dimension": "Orders.order_date",
                "dateRange": "last 3 months",
                "granularity": "month",
            }
        ],
    }
    spec = select_visualization(cube_query, _short_period_rows(), schema_metadata={})
    assert spec.type == "grouped-bar", (
        f"Expected grouped-bar for 3 months × 5 regions, got {spec.type!r}. "
        f"Rationale: {spec.rationale}"
    )


def test_many_periods_low_categories_still_multiline():
    """12 months × 5 regions: trend dominates → multi-line stays correct."""
    rows: list[dict] = []
    regions = ["AFRICA", "AMERICA", "ASIA", "EUROPE", "MIDDLE EAST"]
    for i in range(12):
        for j, r in enumerate(regions):
            rows.append({
                "Orders__order_date": f"2025-{i+1:02d}-01",
                "Region__name": r,
                "Orders__count": 100 + i + j,
            })
    cube_query = {
        "measures": ["Orders.count"],
        "dimensions": ["Region.name"],
        "timeDimensions": [
            {
                "dimension": "Orders.order_date",
                "dateRange": "last 12 months",
                "granularity": "month",
            }
        ],
    }
    spec = select_visualization(cube_query, rows, schema_metadata={})
    assert spec.type == "multi-line"


def test_single_period_top_n_uses_plain_bar_not_blank_grouped_bar():
    """Top-N within a single period (e.g. 'Top 5 countries this quarter') must
    not pick grouped-bar — there's no second axis to group along, and the
    frontend would render blank without a color encoding. Falls back to bar.
    """
    rows = [
        {"Nation__name": "GERMANY", "Orders__order_date": "2026-01-01", "LineItem__revenue": 1_000_000},
        {"Nation__name": "JAPAN",   "Orders__order_date": "2026-01-01", "LineItem__revenue":   900_000},
        {"Nation__name": "FRANCE",  "Orders__order_date": "2026-01-01", "LineItem__revenue":   800_000},
        {"Nation__name": "BRAZIL",  "Orders__order_date": "2026-01-01", "LineItem__revenue":   700_000},
        {"Nation__name": "CHINA",   "Orders__order_date": "2026-01-01", "LineItem__revenue":   600_000},
    ]
    cube_query = {
        "measures": ["LineItem.revenue"],
        "dimensions": ["Nation.name"],
        "timeDimensions": [
            {"dimension": "Orders.order_date", "dateRange": "this quarter", "granularity": "quarter"}
        ],
        "limit": 5,
        "order": {"LineItem.revenue": "desc"},
    }
    spec = select_visualization(cube_query, rows, schema_metadata={})
    assert spec.type == "bar", (
        f"Expected plain bar for top-5-this-quarter (1 period × 5 cats), got {spec.type!r}. "
        f"Rationale: {spec.rationale}"
    )
    assert spec.x is not None and spec.x.field == "Nation__name"
    assert spec.y is not None and spec.y.field == "LineItem__revenue"


def test_grouped_bar_when_picked_always_has_color_encoding():
    """If R11 picks grouped-bar, the chart_spec MUST set both x AND color —
    otherwise the frontend renders blank.
    """
    months = ["2026-02-01", "2026-03-01", "2026-04-01"]
    regions = ["AFRICA", "AMERICA", "ASIA", "EUROPE", "MIDDLE EAST"]
    rows: list[dict] = []
    for i, m in enumerate(months):
        for j, r in enumerate(regions):
            rows.append({"Orders__order_date": m, "Region__name": r, "Orders__count": 100 + i + j})
    cube_query = {
        "measures": ["Orders.count"],
        "dimensions": ["Region.name"],
        "timeDimensions": [
            {"dimension": "Orders.order_date", "dateRange": "last 3 months", "granularity": "month"}
        ],
    }
    spec = select_visualization(cube_query, rows, schema_metadata={})
    assert spec.type == "grouped-bar"
    assert spec.x is not None, "grouped-bar must have an x encoding"
    assert spec.color is not None, (
        "grouped-bar without color encoding renders blank in PlotChart. "
        "When R11 fires for time × dim, color must be the categorical dim."
    )
    # Time goes on X, category goes on color (R11).
    assert spec.x.field == "Orders__order_date"
    assert spec.color.field == "Region__name"


def test_few_periods_many_categories_uses_small_multiples():
    """3 months × 8 regions: too many series for grouped bar → small multiples."""
    rows: list[dict] = []
    regions = [f"R{i}" for i in range(8)]
    for i in range(3):
        for j, r in enumerate(regions):
            rows.append({
                "Orders__order_date": f"2026-{i+2:02d}-01",
                "Region__name": r,
                "Orders__count": 100 + i + j,
            })
    cube_query = {
        "measures": ["Orders.count"],
        "dimensions": ["Region.name"],
        "timeDimensions": [
            {
                "dimension": "Orders.order_date",
                "dateRange": "last 3 months",
                "granularity": "month",
            }
        ],
    }
    spec = select_visualization(cube_query, rows, schema_metadata={})
    assert spec.type == "small-multiples-line"
