"""SaaS-finance Cube query runner — same architecture as TPC-H runner.

Translates Cube query JSON into DuckDB SQL for the saas_finance vertical.
Demonstrates that adding a vertical is mostly:
  1. Cube YAML files (in backend/cube/schema/verticals/<vertical>/)
  2. A seed_<vertical>.py
  3. A query runner like this one
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
        "LOCAL_SAAS_DUCKDB_PATH",
        Path(__file__).parent / "data" / "saas_finance.duckdb",
    )
)


CUBE_TABLES: dict[str, tuple[str, str]] = {
    "Accounts":      ("accounts",      "main.accounts"),
    "Subscriptions": ("subscriptions", "main.subscriptions"),
    "Invoices":      ("invoices",      "main.invoices"),
}

JOINS: dict[str, list[tuple[str, str]]] = {
    "Subscriptions": [("Accounts", "subscriptions.account_id = accounts.id")],
    "Invoices":      [("Accounts", "invoices.account_id = accounts.id")],
}


DIMENSIONS: dict[str, str] = {
    "Accounts.id":              "accounts.id",
    "Accounts.company_name":    "accounts.company_name",
    "Accounts.industry":        "accounts.industry",
    "Accounts.country":         "accounts.country",
    "Accounts.signup_date":     "accounts.signup_date",
    "Accounts.plan_tier":       "accounts.plan_tier",
    "Accounts.status":          "accounts.status",
    "Subscriptions.id":         "subscriptions.id",
    "Subscriptions.started_at": "subscriptions.started_at",
    "Subscriptions.ended_at":   "subscriptions.ended_at",
    "Subscriptions.plan_tier":  "subscriptions.plan_tier",
    "Invoices.id":              "invoices.id",
    "Invoices.issued_at":       "invoices.issued_at",
    "Invoices.due_at":          "invoices.due_at",
    "Invoices.paid_at":         "invoices.paid_at",
    "Invoices.status":          "invoices.status",
}


MEASURES: dict[str, str] = {
    "Accounts.count":         "COUNT(DISTINCT accounts.id)",
    "Accounts.active_count":  "COUNT(DISTINCT CASE WHEN accounts.status = 'active' THEN accounts.id END)",
    "Accounts.churned_count": "COUNT(DISTINCT CASE WHEN accounts.status = 'churned' THEN accounts.id END)",
    "Subscriptions.mrr":      "SUM(subscriptions.monthly_amount_usd)",
    "Subscriptions.arr":      "SUM(subscriptions.monthly_amount_usd) * 12",
    "Subscriptions.avg_contract_value": "AVG(subscriptions.monthly_amount_usd) * 12",
    "Subscriptions.count":    "COUNT(DISTINCT subscriptions.id)",
    "Invoices.total_billed":  "SUM(invoices.amount_usd)",
    "Invoices.total_collected": "SUM(CASE WHEN invoices.status = 'paid' THEN invoices.amount_usd ELSE 0 END)",
    "Invoices.total_outstanding": "SUM(CASE WHEN invoices.status IN ('pending','overdue') THEN invoices.amount_usd ELSE 0 END)",
    "Invoices.overdue_count": "COUNT(DISTINCT CASE WHEN invoices.status = 'overdue' THEN invoices.id END)",
    "Invoices.collection_rate": "CAST(SUM(CASE WHEN invoices.status = 'paid' THEN 1 ELSE 0 END) AS DOUBLE) / NULLIF(COUNT(*), 0)",
}


SEGMENTS: dict[str, str] = {
    "Accounts.enterprise":      "accounts.plan_tier = 'Enterprise'",
    "Accounts.paying":          "accounts.plan_tier IN ('Starter','Growth','Enterprise')",
    "Subscriptions.active":     "subscriptions.ended_at IS NULL OR subscriptions.ended_at > CURRENT_DATE",
    "Subscriptions.ended":      "subscriptions.ended_at IS NOT NULL AND subscriptions.ended_at <= CURRENT_DATE",
    "Invoices.paid":            "invoices.status = 'paid'",
    "Invoices.overdue":         "invoices.status = 'overdue'",
}


def _date_range_to_bounds(date_range: str | list[str]) -> tuple[date, date]:
    if isinstance(date_range, list):
        return (datetime.fromisoformat(date_range[0]).date(), datetime.fromisoformat(date_range[1]).date())
    today = date.today()
    s = date_range.strip().lower()
    if s == "this year":
        return date(today.year, 1, 1), today
    if s == "last year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if s == "this quarter":
        q = (today.month - 1) // 3
        return date(today.year, q * 3 + 1, 1), today
    if s == "last quarter":
        q = (today.month - 1) // 3
        if q == 0:
            return date(today.year - 1, 10, 1), date(today.year - 1, 12, 31)
        return date(today.year, (q - 1) * 3 + 1, 1), date(today.year, q * 3, 1) - timedelta(days=1)
    if s == "this month":
        return date(today.year, today.month, 1), today
    if s == "last month":
        first = date(today.year, today.month, 1)
        last_prev = first - timedelta(days=1)
        return date(last_prev.year, last_prev.month, 1), last_prev
    m = re.match(r"last (\d+) (day|days|month|months|year|years)", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2).rstrip("s")
        delta = {"day": timedelta(days=n), "month": timedelta(days=30*n), "year": timedelta(days=365*n)}[unit]
        return today - delta, today
    raise ValueError(f"Unsupported dateRange: {date_range!r}")


def _granularity_expr(col: str, gran: str) -> str:
    return f"DATE_TRUNC('{gran}', {col})"


def _build_from(cubes: set[str]) -> tuple[str, set[str]]:
    fact_priority = ["Invoices", "Subscriptions", "Accounts"]
    base = next((c for c in fact_priority if c in cubes), next(iter(cubes)))
    base_alias, base_table = CUBE_TABLES[base]
    sql = f"FROM {base_table} {base_alias}"
    joined = {base}
    pending = set(cubes) - {base}

    progress = True
    while progress and pending:
        progress = False
        for cube in list(pending):
            for target, on_clause in JOINS.get(cube, []):
                if target in joined:
                    alias, table = CUBE_TABLES[cube]
                    sql += f" LEFT JOIN {table} {alias} ON {on_clause}"
                    joined.add(cube)
                    pending.discard(cube)
                    progress = True
                    break
            if cube not in joined:
                for source in list(joined):
                    for target, on_clause in JOINS.get(source, []):
                        if target == cube:
                            alias, table = CUBE_TABLES[cube]
                            sql += f" LEFT JOIN {table} {alias} ON {on_clause}"
                            joined.add(cube)
                            pending.discard(cube)
                            progress = True
                            break
    if pending:
        raise ValueError(f"Cannot connect cubes {pending} starting from {base}")
    return sql, joined


def query_to_sql(query: dict[str, Any]) -> str:
    members: list[str] = []
    members.extend(query.get("measures") or [])
    members.extend(query.get("dimensions") or [])
    members.extend([td["dimension"] for td in (query.get("timeDimensions") or [])])
    members.extend(query.get("segments") or [])
    for f in query.get("filters") or []:
        members.append(f["member"])
    cubes = {m.split(".")[0] for m in members}
    if not cubes:
        raise ValueError("Query references no cubes")

    for m in query.get("measures") or []:
        if m not in MEASURES:
            raise ValueError(f"Unknown measure: {m}")
    for d in query.get("dimensions") or []:
        if d not in DIMENSIONS:
            raise ValueError(f"Unknown dimension: {d}")
    for td in query.get("timeDimensions") or []:
        if td["dimension"] not in DIMENSIONS:
            raise ValueError(f"Unknown time dimension: {td['dimension']}")
    for s in query.get("segments") or []:
        if s not in SEGMENTS:
            raise ValueError(f"Unknown segment: {s}")

    from_clause, _ = _build_from(cubes)

    select_parts: list[str] = []
    group_by_parts: list[str] = []

    for d in query.get("dimensions") or []:
        col = DIMENSIONS[d]
        alias = d.replace(".", "__")
        select_parts.append(f'{col} AS "{alias}"')
        group_by_parts.append(col)

    for td in query.get("timeDimensions") or []:
        col = DIMENSIONS[td["dimension"]]
        gran = td.get("granularity")
        if gran:
            expr = _granularity_expr(col, gran)
            alias = td["dimension"].replace(".", "__")
            select_parts.append(f'{expr} AS "{alias}"')
            group_by_parts.append(expr)

    for m in query.get("measures") or []:
        alias = m.replace(".", "__")
        select_parts.append(f'{MEASURES[m]} AS "{alias}"')

    if not select_parts:
        raise ValueError("Query has no SELECT columns")

    where_parts: list[str] = []
    for seg in query.get("segments") or []:
        where_parts.append(f"({SEGMENTS[seg]})")
    for f in query.get("filters") or []:
        col = DIMENSIONS[f["member"]]
        op = f["operator"]
        vals = f.get("values") or []
        if op == "equals":
            quoted = ", ".join(f"'{v}'" for v in vals)
            where_parts.append(f"{col} IN ({quoted})")
    for td in query.get("timeDimensions") or []:
        if td.get("dateRange"):
            col = DIMENSIONS[td["dimension"]]
            start, end = _date_range_to_bounds(td["dateRange"])
            where_parts.append(f"{col} BETWEEN '{start}' AND '{end} 23:59:59'")

    sql = "SELECT " + ", ".join(select_parts) + " " + from_clause
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if group_by_parts:
        sql += " GROUP BY " + ", ".join(group_by_parts)
    if query.get("order"):
        order_parts = [f'"{m.replace(".", "__")}" {d.upper()}' for m, d in query["order"].items()]
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
