"""TPC-H Cube-query → DuckDB SQL translator for local smoke tests.

Implements the subset of Cube semantics needed to drive the TPC-H workspace
end-to-end without spinning up real Cube. Production goes through real Cube;
this exists purely so the AI loop can be validated offline.

Supports:
- All measures defined in backend/cube/schema/verticals/tpch/*.yml
- All dimensions including those reached via the join graph (Orders → Customer → Nation → Region)
- timeDimensions on Orders.order_date, LineItem.ship_date / commit_date / receipt_date
- segments, filters, order, limit
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
        "LOCAL_TPCH_DUCKDB_PATH",
        Path(__file__).parent / "data" / "tpch.duckdb",
    )
)


# ── Schema knowledge tables ───────────────────────────────────────────────────

# Each cube → (table alias, table name).
CUBE_TABLES: dict[str, tuple[str, str]] = {
    "Region":   ("region",   "main.region"),
    "Nation":   ("nation",   "main.nation"),
    "Customer": ("customer", "main.customer"),
    "Orders":   ("orders",   "main.orders"),
    "LineItem": ("lineitem", "main.lineitem"),
    "Supplier": ("supplier", "main.supplier"),
    "Part":     ("part",     "main.part"),
    "PartSupp": ("partsupp", "main.partsupp"),
}

# Join graph: cube → list of (foreign_cube, ON clause). A cube may have
# multiple outgoing joins (e.g. PartSupp links to both Part and Supplier).
JOINS: dict[str, list[tuple[str, str]]] = {
    "Nation":   [("Region",   "nation.n_regionkey = region.r_regionkey")],
    "Customer": [("Nation",   "customer.c_nationkey = nation.n_nationkey")],
    "Orders":   [("Customer", "orders.o_custkey = customer.c_custkey")],
    "LineItem": [("Orders",   "lineitem.l_orderkey = orders.o_orderkey")],
    "Supplier": [("Nation",   "supplier.s_nationkey = nation.n_nationkey")],
    "PartSupp": [
        ("Part",     "partsupp.ps_partkey = part.p_partkey"),
        ("Supplier", "partsupp.ps_suppkey = supplier.s_suppkey"),
    ],
}

# Dimensions: how to render in SELECT/GROUP BY.
DIMENSIONS: dict[str, str] = {
    "Region.name":              "region.r_name",
    "Region.key":               "region.r_regionkey",
    "Nation.name":              "nation.n_name",
    "Nation.key":               "nation.n_nationkey",
    "Customer.name":            "customer.c_name",
    "Customer.market_segment":  "customer.c_mktsegment",
    "Customer.account_balance": "customer.c_acctbal",
    "Customer.key":             "customer.c_custkey",
    "Orders.status":            "orders.o_orderstatus",
    "Orders.order_date":        "orders.o_orderdate",
    "Orders.order_priority":    "orders.o_orderpriority",
    "Orders.ship_priority":     "orders.o_shippriority",
    "Orders.key":               "orders.o_orderkey",
    "LineItem.ship_date":       "lineitem.l_shipdate",
    "LineItem.commit_date":     "lineitem.l_commitdate",
    "LineItem.receipt_date":    "lineitem.l_receiptdate",
    "LineItem.ship_mode":       "lineitem.l_shipmode",
    "LineItem.return_flag":     "lineitem.l_returnflag",
    "LineItem.line_status":     "lineitem.l_linestatus",
    "Supplier.name":            "supplier.s_name",
    "Supplier.account_balance": "supplier.s_acctbal",
    "Part.brand":               "part.p_brand",
    "Part.type":                "part.p_type",
    "Part.size":                "part.p_size",
    "Part.container":           "part.p_container",
    "Part.retail_price":        "part.p_retailprice",
    "PartSupp.available_quantity": "partsupp.ps_availqty",
    "PartSupp.supply_cost":     "partsupp.ps_supplycost",
}

# Measures: SQL expression.
MEASURES: dict[str, str] = {
    "Region.count":                "COUNT(DISTINCT region.r_regionkey)",
    "Nation.count":                "COUNT(DISTINCT nation.n_nationkey)",
    "Customer.count":              "COUNT(DISTINCT customer.c_custkey)",
    "Customer.avg_account_balance":"AVG(customer.c_acctbal)",
    "Customer.total_account_balance":"SUM(customer.c_acctbal)",
    "Customer.positive_balance_count": "COUNT(DISTINCT CASE WHEN customer.c_acctbal > 0 THEN customer.c_custkey END)",
    "Customer.negative_balance_count": "COUNT(DISTINCT CASE WHEN customer.c_acctbal < 0 THEN customer.c_custkey END)",
    "Orders.count":                "COUNT(DISTINCT orders.o_orderkey)",
    "Orders.total_price":          "SUM(orders.o_totalprice)",
    "Orders.avg_total_price":      "AVG(orders.o_totalprice)",
    "LineItem.revenue":            "SUM(lineitem.l_extendedprice * (1 - lineitem.l_discount))",
    "LineItem.revenue_with_tax":   "SUM(lineitem.l_extendedprice * (1 - lineitem.l_discount) * (1 + lineitem.l_tax))",
    "LineItem.discount_amount":    "SUM(lineitem.l_extendedprice * lineitem.l_discount)",
    "LineItem.count":              "COUNT(*)",
    "LineItem.total_quantity":     "SUM(lineitem.l_quantity)",
    "LineItem.avg_extended_price": "AVG(lineitem.l_extendedprice)",
    "LineItem.late_count":         "SUM(CASE WHEN lineitem.l_receiptdate > lineitem.l_commitdate THEN 1 ELSE 0 END)",
    "LineItem.late_rate":          "CAST(SUM(CASE WHEN lineitem.l_receiptdate > lineitem.l_commitdate THEN 1 ELSE 0 END) AS DOUBLE) / NULLIF(COUNT(*), 0)",
    "LineItem.return_rate":        "CAST(SUM(CASE WHEN lineitem.l_returnflag = 'R' THEN 1 ELSE 0 END) AS DOUBLE) / NULLIF(COUNT(*), 0)",
    "Supplier.count":              "COUNT(DISTINCT supplier.s_suppkey)",
    "Supplier.avg_account_balance":"AVG(supplier.s_acctbal)",
    "Part.count":                  "COUNT(DISTINCT part.p_partkey)",
    "Part.avg_retail_price":       "AVG(part.p_retailprice)",
    "PartSupp.count":              "COUNT(*)",
    "PartSupp.total_available_quantity": "SUM(partsupp.ps_availqty)",
    "PartSupp.avg_supply_cost":    "AVG(partsupp.ps_supplycost)",
    "PartSupp.max_supply_cost":    "MAX(partsupp.ps_supplycost)",
    "PartSupp.min_supply_cost":    "MIN(partsupp.ps_supplycost)",
    "PartSupp.total_inventory_value": "SUM(partsupp.ps_availqty * partsupp.ps_supplycost)",
}

SEGMENTS: dict[str, str] = {
    "Orders.open":           "orders.o_orderstatus = 'O'",
    "Orders.finished":       "orders.o_orderstatus = 'F'",
    "Orders.high_priority":  "orders.o_orderpriority IN ('1-URGENT','2-HIGH')",
    "Orders.large_orders":   "orders.o_totalprice > 100000",
    "LineItem.returned":     "lineitem.l_returnflag = 'R'",
    "LineItem.shipped":      "lineitem.l_shipdate IS NOT NULL",
    "LineItem.late":         "lineitem.l_receiptdate > lineitem.l_commitdate",
    "LineItem.by_air":       "lineitem.l_shipmode IN ('AIR', 'REG AIR')",
    "LineItem.heavy_quantity": "lineitem.l_quantity >= 40",
    "Customer.in_debt":      "customer.c_acctbal < 0",
    "Customer.high_balance": "customer.c_acctbal > 5000",
    "PartSupp.low_stock":    "partsupp.ps_availqty < 100",
    "PartSupp.expensive":    "partsupp.ps_supplycost > 500",
}


# ── Date range translation (TPC-H data is around 1992-1998) ───────────────────
# We map "this year" / "last year" relative to the latest data point.

def _data_anchor() -> date:
    """The 'now' anchor for relative date phrases — uses the max order date in the data."""
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        row = con.execute("SELECT MAX(o_orderdate) FROM orders").fetchone()
    finally:
        con.close()
    if row and row[0]:
        v = row[0]
        return v if isinstance(v, date) else datetime.fromisoformat(str(v)).date()
    return date.today()


def _date_range_to_bounds(date_range: str | list[str]) -> tuple[date, date]:
    if isinstance(date_range, list):
        return (
            datetime.fromisoformat(date_range[0]).date(),
            datetime.fromisoformat(date_range[1]).date(),
        )
    today = _data_anchor()
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
            end = date(today.year, q * 3, 1) - timedelta(days=1)
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
        delta = {"day": timedelta(days=n), "month": timedelta(days=30*n), "year": timedelta(days=365*n)}[unit]
        return today - delta, today
    raise ValueError(f"Unsupported dateRange: {date_range!r}")


def _granularity_expr(col: str, granularity: str) -> str:
    return f"DATE_TRUNC('{granularity}', {col})"


# ── Cube graph traversal ──────────────────────────────────────────────────────

def _required_cubes(query: dict[str, Any]) -> set[str]:
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
    return cubes


def _walk_to_root(cube: str) -> set[str]:
    """All cubes reachable from `cube` through the join graph, including itself.

    BFS over the multi-parent join graph; handles cubes like PartSupp that
    have two outgoing joins (Part + Supplier).
    """
    seen = {cube}
    queue = [cube]
    while queue:
        cur = queue.pop(0)
        for target, _ in JOINS.get(cur, []):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _build_from_clause(cubes: set[str]) -> tuple[str, set[str]]:
    """Compute FROM + JOIN clauses needed to satisfy all referenced cubes.

    Picks the most-fact-y cube as the base, then walks the join graph adding
    every intermediate cube needed to connect all requested cubes.
    """
    fact_priority = ["LineItem", "Orders", "Customer", "PartSupp", "Supplier", "Part", "Nation", "Region"]
    base_cube = next((c for c in fact_priority if c in cubes), next(iter(cubes)))

    # Every cube we must include = requested cubes ∪ all intermediates on
    # the union of paths from each requested cube to wherever it can reach.
    must_join: set[str] = set()
    for c in cubes:
        must_join |= _walk_to_root(c)
    must_join.discard(base_cube)

    base_alias, base_table = CUBE_TABLES[base_cube]
    sql = f"FROM {base_table} {base_alias}"
    joined: set[str] = {base_cube}

    # Walk outward from joined set, adding any cube whose join condition can
    # be satisfied by already-joined tables.
    progress = True
    while progress and must_join:
        progress = False
        for cube in list(must_join):
            for target, on_clause in JOINS.get(cube, []):
                if target in joined:
                    alias, table = CUBE_TABLES[cube]
                    sql += f" LEFT JOIN {table} {alias} ON {on_clause}"
                    joined.add(cube)
                    must_join.discard(cube)
                    progress = True
                    break
            if cube in joined:
                continue
            # Or look for any joined cube that points TO this cube
            for source in list(joined):
                for target, on_clause in JOINS.get(source, []):
                    if target == cube:
                        alias, table = CUBE_TABLES[cube]
                        sql += f" LEFT JOIN {table} {alias} ON {on_clause}"
                        joined.add(cube)
                        must_join.discard(cube)
                        progress = True
                        break
                if cube in joined:
                    break

    if must_join:
        raise ValueError(
            f"Cannot build join chain to include cubes {must_join}. "
            f"Joined: {joined}. Add a join in JOINS mapping."
        )

    return sql, joined


def query_to_sql(query: dict[str, Any]) -> str:
    cubes = _required_cubes(query)

    # Validate all members exist in our knowledge tables.
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
    for f in query.get("filters") or []:
        if f["member"] not in DIMENSIONS:
            raise ValueError(f"Unknown filter member: {f['member']}")

    from_clause, _ = _build_from_clause(cubes)

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
        elif op == "notEquals":
            quoted = ", ".join(f"'{v}'" for v in vals)
            where_parts.append(f"{col} NOT IN ({quoted})")
        elif op == "gt":
            where_parts.append(f"{col} > {vals[0]}")
        elif op == "lt":
            where_parts.append(f"{col} < {vals[0]}")
        elif op == "gte":
            where_parts.append(f"{col} >= {vals[0]}")
        elif op == "lte":
            where_parts.append(f"{col} <= {vals[0]}")
        elif op == "contains":
            where_parts.append(f"{col} ILIKE '%{vals[0]}%'")

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
