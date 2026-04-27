"""In-process Cube-query → SQL runner backed by DuckDB.

This intentionally implements only the small subset of Cube semantics the smoke
test needs. It is NOT a substitute for running real Cube — it exists so that
the local smoke test can validate the AI loop without spinning up Cube containers.

Supported:
- measures: Orders.revenue, Orders.order_count, Orders.paid_order_count, Orders.aov
            Customers.count, Customers.count_with_orders
- dimensions: Orders.country, Orders.status, Customers.country, Customers.tier
- timeDimensions: Orders.created_at (granularity day/week/month/quarter/year, dateRange)
- segments: Orders.high_value, Orders.paid_only, Customers.gold_or_platinum
- order, limit
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

DUCKDB_PATH = Path(
    os.environ.get(
        "LOCAL_DUCKDB_PATH",
        Path(__file__).parent / "data" / "warehouse.duckdb",
    )
)


# --- Measure / dimension translation tables -------------------------------------------

MEASURES_SQL: dict[str, str] = {
    "Orders.revenue": "SUM(CASE WHEN status='paid' THEN amount_usd ELSE 0 END)",
    "Orders.order_count": "COUNT(DISTINCT id)",
    "Orders.paid_order_count": "COUNT(DISTINCT CASE WHEN status='paid' THEN id END)",
    "Orders.aov": (
        "SUM(CASE WHEN status='paid' THEN amount_usd ELSE 0 END) "
        "/ NULLIF(COUNT(DISTINCT CASE WHEN status='paid' THEN id END), 0)"
    ),
    "Customers.count": "COUNT(DISTINCT id)",
    "Customers.count_with_orders": (
        "COUNT(DISTINCT CASE WHEN id IN (SELECT customer_id FROM public.orders WHERE status='paid') THEN id END)"
    ),
}

DIM_SQL: dict[str, str] = {
    "Orders.country": "shipping_country",
    "Orders.status": "status",
    "Orders.customer_id": "customer_id",
    "Orders.created_at": "created_at",
    "Customers.country": "country",
    "Customers.tier": "tier",
    "Customers.signup_date": "created_at",
    "Customers.email": "email",
}

SEGMENTS_SQL: dict[str, str] = {
    "Orders.high_value": "amount_usd > 1000",
    "Orders.paid_only": "status = 'paid'",
    "Customers.gold_or_platinum": "tier IN ('gold','platinum')",
}

CUBE_TO_TABLE: dict[str, str] = {
    "Orders": "public.orders",
    "Customers": "public.customers",
}


def _cube_of(member: str) -> str:
    return member.split(".")[0]


def _resolve_cube(query: dict[str, Any]) -> str:
    members = (
        list(query.get("measures") or [])
        + list(query.get("dimensions") or [])
        + [td["dimension"] for td in (query.get("timeDimensions") or [])]
        + list(query.get("segments") or [])
    )
    cubes = {_cube_of(m) for m in members}
    if len(cubes) > 1:
        # Phase 0 doesn't auto-join. Drop hint into error.
        raise ValueError(
            f"Multi-cube queries not supported in local runner: {cubes}. "
            "Use a single cube per query."
        )
    if not cubes:
        raise ValueError("Query references no cubes")
    return next(iter(cubes))


def _date_range_to_bounds(date_range: str | list[str]) -> tuple[date, date]:
    if isinstance(date_range, list):
        return (
            datetime.fromisoformat(date_range[0]).date(),
            datetime.fromisoformat(date_range[1]).date(),
        )
    today = date.today()
    s = date_range.strip().lower()
    if s == "today":
        return today, today
    if s == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if s == "this year":
        return date(today.year, 1, 1), today
    if s == "last year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if s == "this quarter":
        q = (today.month - 1) // 3
        start = date(today.year, q * 3 + 1, 1)
        return start, today
    if s == "last quarter":
        q = (today.month - 1) // 3
        if q == 0:
            start = date(today.year - 1, 10, 1)
            end = date(today.year - 1, 12, 31)
        else:
            start = date(today.year, (q - 1) * 3 + 1, 1)
            # crude: end = day before this-quarter start
            end_month = q * 3
            end = date(today.year, end_month, 1) - timedelta(days=1)
        return start, end
    if s == "this month":
        return date(today.year, today.month, 1), today
    if s == "last month":
        first_this = date(today.year, today.month, 1)
        last_prev = first_this - timedelta(days=1)
        first_prev = date(last_prev.year, last_prev.month, 1)
        return first_prev, last_prev
    m = re.match(r"last (\d+) (day|days|month|months|year|years)", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2).rstrip("s")
        delta = {"day": timedelta(days=n), "month": timedelta(days=30 * n), "year": timedelta(days=365 * n)}[unit]
        return today - delta, today
    raise ValueError(f"Unsupported dateRange: {date_range!r}")


def _granularity_expr(col: str, granularity: str) -> str:
    return f"DATE_TRUNC('{granularity}', {col})"


def query_to_sql(query: dict[str, Any]) -> str:
    cube_name = _resolve_cube(query)
    table = CUBE_TO_TABLE[cube_name]

    select_parts: list[str] = []
    group_by_parts: list[str] = []

    for d in query.get("dimensions") or []:
        if d not in DIM_SQL:
            raise ValueError(f"Unknown dimension: {d}")
        col = DIM_SQL[d]
        alias = d.replace(".", "__")
        select_parts.append(f'{col} AS "{alias}"')
        group_by_parts.append(col)

    for td in query.get("timeDimensions") or []:
        dim = td["dimension"]
        col = DIM_SQL.get(dim)
        if not col:
            raise ValueError(f"Unknown time dimension: {dim}")
        gran = td.get("granularity")
        if gran:
            expr = _granularity_expr(col, gran)
            alias = dim.replace(".", "__")
            select_parts.append(f'{expr} AS "{alias}"')
            group_by_parts.append(expr)

    for m in query.get("measures") or []:
        if m not in MEASURES_SQL:
            raise ValueError(f"Unknown measure: {m}")
        alias = m.replace(".", "__")
        select_parts.append(f'{MEASURES_SQL[m]} AS "{alias}"')

    if not select_parts:
        raise ValueError("Query has no select columns (no measures or dimensions)")

    where_parts: list[str] = []

    for seg in query.get("segments") or []:
        if seg not in SEGMENTS_SQL:
            raise ValueError(f"Unknown segment: {seg}")
        where_parts.append(f"({SEGMENTS_SQL[seg]})")

    for f in query.get("filters") or []:
        member = f["member"]
        col = DIM_SQL.get(member)
        if not col:
            raise ValueError(f"Cannot filter on unknown member: {member}")
        op = f["operator"]
        vals = f.get("values") or []
        if op == "equals":
            quoted = ", ".join(f"'{v}'" for v in vals)
            where_parts.append(f"{col} IN ({quoted})")
        elif op == "notEquals":
            quoted = ", ".join(f"'{v}'" for v in vals)
            where_parts.append(f"{col} NOT IN ({quoted})")
        elif op == "gt":
            where_parts.append(f"{col} > {vals[0]}")
        elif op == "lt":
            where_parts.append(f"{col} < {vals[0]}")

    for td in query.get("timeDimensions") or []:
        if "dateRange" in td and td["dateRange"]:
            dim = td["dimension"]
            col = DIM_SQL[dim]
            start, end = _date_range_to_bounds(td["dateRange"])
            where_parts.append(f"{col} BETWEEN '{start}' AND '{end} 23:59:59'")

    sql = "SELECT " + ", ".join(select_parts) + f" FROM {table}"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if group_by_parts:
        sql += " GROUP BY " + ", ".join(group_by_parts)

    if query.get("order"):
        order_parts = []
        for member, direction in query["order"].items():
            alias = member.replace(".", "__")
            order_parts.append(f'"{alias}" {direction.upper()}')
        sql += " ORDER BY " + ", ".join(order_parts)

    if query.get("limit"):
        sql += f" LIMIT {int(query['limit'])}"

    return sql


def run_query(query: dict[str, Any]) -> dict[str, Any]:
    sql = query_to_sql(query)
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        cursor = con.execute(sql)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    finally:
        con.close()
    return {"sql": sql, "data": rows, "row_count": len(rows)}
