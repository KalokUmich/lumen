"""Tests for period-over-period (compare) detection in the visualizer."""

from __future__ import annotations

from services.ai_service.visualizer import select_visualization


def test_big_number_with_relative_period_gets_compare():
    """Big-number queries with 'last month' filter → compare hint set."""
    cube_query = {
        "measures": ["LineItem.revenue"],
        "timeDimensions": [
            {"dimension": "Orders.order_date", "dateRange": "last month"}
        ],
    }
    rows = [{"LineItem__revenue": 2_820_000_000.0}]

    spec = select_visualization(cube_query, rows, schema_metadata={})
    assert spec.type == "big-number"
    assert spec.compare is not None
    assert spec.compare.label == "vs prior month"
    assert spec.compare.time_dimension == "Orders.order_date"
    assert spec.compare.prior_date_range == "the month before last month"


def test_big_number_with_this_year_compares_to_last_year():
    cube_query = {
        "measures": ["LineItem.revenue"],
        "timeDimensions": [
            {"dimension": "Orders.order_date", "dateRange": "this year"}
        ],
    }
    rows = [{"LineItem__revenue": 100.0}]
    spec = select_visualization(cube_query, rows)
    assert spec.compare is not None
    assert spec.compare.prior_date_range == "last year"
    assert spec.compare.label == "vs last year"


def test_big_number_without_relative_period_no_compare():
    """Absolute date range or no timeDim → no compare hint."""
    cube_query = {"measures": ["LineItem.revenue"]}
    rows = [{"LineItem__revenue": 100.0}]
    spec = select_visualization(cube_query, rows)
    assert spec.type == "big-number"
    assert spec.compare is None


def test_bar_chart_does_not_get_compare_hint():
    """Compare is only for big-number / kpi-strip — bar with multiple rows shouldn't."""
    cube_query = {
        "measures": ["LineItem.revenue"],
        "dimensions": ["Region.name"],
        "timeDimensions": [
            {"dimension": "Orders.order_date", "dateRange": "this year"}
        ],
    }
    rows = [
        {"Region__name": "ASIA", "LineItem__revenue": 100.0},
        {"Region__name": "EUROPE", "LineItem__revenue": 200.0},
    ]
    spec = select_visualization(cube_query, rows)
    assert spec.type != "big-number"
    assert spec.compare is None


def test_kpi_strip_with_relative_period_gets_compare():
    """KPI strip (multi-measure single row) — should also get compare."""
    cube_query = {
        "measures": ["LineItem.revenue", "LineItem.count"],
        "timeDimensions": [
            {"dimension": "Orders.order_date", "dateRange": "this quarter"}
        ],
    }
    rows = [{"LineItem__revenue": 100.0, "LineItem__count": 50}]
    spec = select_visualization(cube_query, rows)
    assert spec.type == "kpi-strip"
    assert spec.compare is not None
    assert spec.compare.prior_date_range == "last quarter"
