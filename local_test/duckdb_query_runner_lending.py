"""Consumer-lending Cube query runner.

Translates Cube query JSON into DuckDB SQL for the lending vertical —
Lumen's primary local fixture.

Layout:
  - CUBE_TABLES   : Cube name → (alias, qualified table name)
  - JOINS         : Cube → list of (target_cube, ON clause)
  - DIMENSIONS    : "Cube.dim" → SQL expression
  - MEASURES      : "Cube.measure" → SQL aggregate expression
  - SEGMENTS      : "Cube.segment" → boolean SQL predicate
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
        "LOCAL_LENDING_DUCKDB_PATH",
        Path(__file__).parent / "data" / "lending.duckdb",
    )
)


CUBE_TABLES: dict[str, tuple[str, str]] = {
    "Customer":       ("customer",   "main.customers"),
    "Branch":         ("branch",     "main.branches"),
    "LoanOfficer":    ("officer",    "main.loan_officers"),
    "Application":    ("application","main.applications"),
    "Loan":           ("loan",       "main.loans"),
    "Payment":        ("payment",    "main.payments"),
    "Collection":     ("collection", "main.collections"),
    "CreditInquiry":  ("inquiry",    "main.credit_inquiries"),
}


JOINS: dict[str, list[tuple[str, str]]] = {
    "Application":    [("Customer",    "application.customer_id = customer.customer_id")],
    "Loan":           [("Customer",    "loan.customer_id = customer.customer_id"),
                       ("Branch",      "loan.branch_id = branch.branch_id"),
                       ("LoanOfficer", "loan.officer_id = officer.officer_id"),
                       ("Application", "loan.application_id = application.application_id")],
    "Payment":        [("Loan",        "payment.loan_id = loan.loan_id"),
                       ("Customer",    "payment.customer_id = customer.customer_id")],
    "Collection":     [("Loan",        "collection.loan_id = loan.loan_id"),
                       ("Customer",    "collection.customer_id = customer.customer_id")],
    "CreditInquiry":  [("Customer",    "inquiry.customer_id = customer.customer_id")],
    "LoanOfficer":    [("Branch",      "officer.branch_id = branch.branch_id")],
}


DIMENSIONS: dict[str, str] = {
    # Customer
    "Customer.id":                  "customer.customer_id",
    "Customer.code":                "customer.customer_code",
    "Customer.full_name":           "customer.full_name",
    "Customer.state":               "customer.state",
    "Customer.employment_type":     "customer.employment_type",
    "Customer.annual_income":       "customer.annual_income",
    "Customer.fico_score":          "customer.fico_score",
    "Customer.credit_tier":         "customer.credit_tier",
    "Customer.acquisition_channel": "customer.acquisition_channel",
    "Customer.is_homeowner":        "customer.is_homeowner",
    "Customer.signup_cohort_year":  "customer.signup_cohort_year",
    "Customer.signup_date":         "customer.signup_date",
    "Customer.date_of_birth":       "customer.date_of_birth",
    # Branch
    "Branch.id":           "branch.branch_id",
    "Branch.code":         "branch.branch_code",
    "Branch.name":         "branch.branch_name",
    "Branch.region":       "branch.region",
    "Branch.state":        "branch.state",
    "Branch.opened_date":  "branch.opened_date",
    "Branch.headcount":    "branch.headcount",
    # LoanOfficer
    "LoanOfficer.id":         "officer.officer_id",
    "LoanOfficer.code":       "officer.officer_code",
    "LoanOfficer.name":       "officer.officer_name",
    "LoanOfficer.branch_id":  "officer.branch_id",
    "LoanOfficer.hire_date":  "officer.hire_date",
    "LoanOfficer.specialty":  "officer.specialty",
    "LoanOfficer.status":     "officer.status",
    # Application
    "Application.id":                    "application.application_id",
    "Application.code":                  "application.application_code",
    "Application.customer_id":           "application.customer_id",
    "Application.product_type":          "application.product_type",
    "Application.status":                "application.status",
    "Application.decline_reason":        "application.decline_reason",
    "Application.channel":               "application.channel",
    "Application.requested_amount":      "application.requested_amount",
    "Application.requested_term_months": "application.requested_term_months",
    "Application.manual_review_flag":    "application.manual_review_flag",
    "Application.application_date":      "application.application_date",
    # Loan
    "Loan.id":                "loan.loan_id",
    "Loan.code":              "loan.loan_code",
    "Loan.customer_id":       "loan.customer_id",
    "Loan.branch_id":         "loan.branch_id",
    "Loan.officer_id":        "loan.officer_id",
    "Loan.application_id":    "loan.application_id",
    "Loan.product_type":      "loan.product_type",
    "Loan.grade":             "loan.grade",
    "Loan.subgrade":          "loan.subgrade",
    "Loan.purpose":           "loan.purpose",
    "Loan.status":            "loan.status",
    "Loan.term_months":       "loan.term_months",
    "Loan.loan_amount":       "loan.loan_amount",
    "Loan.interest_rate_pct": "loan.interest_rate_pct",
    "Loan.origination_date":  "loan.origination_date",
    # Payment
    "Payment.id":                  "payment.payment_id",
    "Payment.code":                "payment.payment_code",
    "Payment.loan_id":             "payment.loan_id",
    "Payment.customer_id":         "payment.customer_id",
    "Payment.payment_method":      "payment.payment_method",
    "Payment.is_late":             "payment.is_late",
    "Payment.payment_sequence":    "payment.payment_sequence",
    "Payment.scheduled_date":      "payment.scheduled_date",
    "Payment.actual_payment_date": "payment.actual_payment_date",
    # Collection
    "Collection.id":          "collection.collection_id",
    "Collection.code":        "collection.collection_code",
    "Collection.loan_id":     "collection.loan_id",
    "Collection.customer_id": "collection.customer_id",
    "Collection.channel":     "collection.collection_channel",
    "Collection.status":      "collection.status",
    "Collection.opened_date": "collection.opened_date",
    "Collection.closed_date": "collection.closed_date",
    # CreditInquiry
    "CreditInquiry.id":                "inquiry.inquiry_id",
    "CreditInquiry.code":              "inquiry.inquiry_code",
    "CreditInquiry.customer_id":       "inquiry.customer_id",
    "CreditInquiry.bureau":            "inquiry.bureau",
    "CreditInquiry.inquiry_type":      "inquiry.inquiry_type",
    "CreditInquiry.score_at_inquiry":  "inquiry.score_at_inquiry",
    "CreditInquiry.inquiry_date":      "inquiry.inquiry_date",
}


MEASURES: dict[str, str] = {
    # Customer
    "Customer.count":              "COUNT(DISTINCT customer.customer_id)",
    "Customer.avg_fico":           "AVG(customer.fico_score)",
    "Customer.avg_annual_income":  "AVG(customer.annual_income)",
    "Customer.median_annual_income": "MEDIAN(customer.annual_income)",
    "Customer.prime_count":        "COUNT(DISTINCT CASE WHEN customer.credit_tier = 'Prime' THEN customer.customer_id END)",
    "Customer.subprime_count":     "COUNT(DISTINCT CASE WHEN customer.credit_tier IN ('Sub-prime','Deep sub-prime') THEN customer.customer_id END)",
    "Customer.homeowner_rate":     "AVG(CASE WHEN customer.is_homeowner THEN 1.0 ELSE 0 END)",
    # Branch
    "Branch.count":           "COUNT(DISTINCT branch.branch_id)",
    "Branch.total_headcount": "SUM(branch.headcount)",
    # LoanOfficer
    "LoanOfficer.count":        "COUNT(DISTINCT officer.officer_id)",
    "LoanOfficer.active_count": "COUNT(DISTINCT CASE WHEN officer.status = 'active' THEN officer.officer_id END)",
    # Application
    "Application.count":              "COUNT(DISTINCT application.application_id)",
    "Application.approved_count":     "COUNT(DISTINCT CASE WHEN application.status = 'Approved' THEN application.application_id END)",
    "Application.declined_count":     "COUNT(DISTINCT CASE WHEN application.status = 'Declined' THEN application.application_id END)",
    "Application.abandoned_count":    "COUNT(DISTINCT CASE WHEN application.status = 'Abandoned' THEN application.application_id END)",
    "Application.approval_rate":      "AVG(CASE WHEN application.status = 'Approved' THEN 1.0 ELSE 0 END)",
    "Application.total_requested":    "SUM(application.requested_amount)",
    "Application.avg_requested_amount": "AVG(application.requested_amount)",
    "Application.avg_decision_time_seconds": "AVG(application.decision_time_seconds)",
    "Application.manual_review_rate": "AVG(CASE WHEN application.manual_review_flag THEN 1.0 ELSE 0 END)",
    # Loan
    "Loan.count":              "COUNT(DISTINCT loan.loan_id)",
    "Loan.total_originated":   "SUM(loan.loan_amount)",
    "Loan.avg_loan_amount":    "AVG(loan.loan_amount)",
    "Loan.avg_interest_rate":  "AVG(loan.interest_rate_pct)",
    "Loan.weighted_avg_rate":  "SUM(loan.interest_rate_pct * loan.loan_amount) / NULLIF(SUM(loan.loan_amount), 0)",
    "Loan.default_count":      "COUNT(DISTINCT CASE WHEN loan.status IN ('default','charged_off') THEN loan.loan_id END)",
    "Loan.default_rate":       "AVG(CASE WHEN loan.status IN ('default','charged_off') THEN 1.0 ELSE 0 END)",
    "Loan.delinquency_rate":   "AVG(CASE WHEN loan.status IN ('late_31_120','default','charged_off') THEN 1.0 ELSE 0 END)",
    "Loan.paid_off_count":     "COUNT(DISTINCT CASE WHEN loan.status = 'paid_off' THEN loan.loan_id END)",
    "Loan.charged_off_amount": "SUM(CASE WHEN loan.status = 'charged_off' THEN loan.loan_amount ELSE 0 END)",
    # Payment
    "Payment.count":              "COUNT(DISTINCT payment.payment_id)",
    "Payment.total_received":     "SUM(payment.payment_amount)",
    "Payment.total_principal":    "SUM(payment.principal_amount)",
    "Payment.total_interest":     "SUM(payment.interest_amount)",
    "Payment.total_late_fees":    "SUM(payment.late_fee)",
    "Payment.avg_payment_amount": "AVG(payment.payment_amount)",
    "Payment.late_payment_count": "COUNT(DISTINCT CASE WHEN payment.is_late THEN payment.payment_id END)",
    "Payment.late_payment_rate":  "AVG(CASE WHEN payment.is_late THEN 1.0 ELSE 0 END)",
    # Collection
    "Collection.count":              "COUNT(DISTINCT collection.collection_id)",
    "Collection.total_recovered":    "SUM(collection.amount_recovered)",
    "Collection.total_charged_off":  "SUM(collection.amount_charged_off)",
    "Collection.recovery_rate":      "SUM(collection.amount_recovered) / NULLIF(SUM(collection.amount_charged_off), 0)",
    # CreditInquiry
    "CreditInquiry.count":              "COUNT(DISTINCT inquiry.inquiry_id)",
    "CreditInquiry.hard_inquiry_count": "COUNT(DISTINCT CASE WHEN inquiry.inquiry_type = 'Hard' THEN inquiry.inquiry_id END)",
    "CreditInquiry.avg_score_at_inquiry": "AVG(inquiry.score_at_inquiry)",
}


SEGMENTS: dict[str, str] = {
    "Customer.prime":          "customer.credit_tier = 'Prime'",
    "Customer.subprime":       "customer.credit_tier IN ('Sub-prime','Deep sub-prime')",
    "Customer.high_income":    "customer.annual_income >= 150000",
    "Application.approved":    "application.status = 'Approved'",
    "Application.declined":    "application.status = 'Declined'",
    "Application.high_value":  "application.requested_amount >= 25000",
    "Loan.prime_grade":        "loan.grade IN ('A','B')",
    "Loan.subprime_grade":     "loan.grade IN ('E','F','G')",
    "Loan.delinquent":         "loan.status IN ('late_31_120','default','charged_off')",
    "Loan.performing":         "loan.status IN ('current','paid_off')",
    "Payment.late":            "payment.is_late",
    "Payment.card_payments":   "payment.payment_method = 'Card'",
    "Collection.open_cases":   "collection.status IN ('in_collection','partial_recovery')",
    "Collection.closed_cases": "collection.status IN ('recovered','written_off')",
}


# ── Date range parsing ──
_DATA_ANCHOR = date(2026, 4, 27)


def _data_anchor() -> date:
    return _DATA_ANCHOR


def _date_range_to_bounds(date_range: str | list[str]) -> tuple[date, date]:
    if isinstance(date_range, list):
        return (
            datetime.fromisoformat(date_range[0]).date(),
            datetime.fromisoformat(date_range[1]).date(),
        )
    today = _data_anchor()
    s = date_range.strip().lower()
    aliases = {
        "mtd": "this month", "month-to-date": "this month",
        "ytd": "this year", "year-to-date": "this year",
        "qtd": "this quarter", "quarter-to-date": "this quarter",
        "wtd": "this week", "week-to-date": "this week",
    }
    s = aliases.get(s, s)
    if s == "today":
        return today, today
    if s == "yesterday":
        y = today - timedelta(days=1); return y, y
    if s == "this week":
        start = today - timedelta(days=today.weekday()); return start, today
    if s == "last week":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6); return start, end
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
    if s == "the month before last month":
        first = date(today.year, today.month, 1)
        last_prev = first - timedelta(days=1)
        first_prev = date(last_prev.year, last_prev.month, 1)
        last_prev2 = first_prev - timedelta(days=1)
        return date(last_prev2.year, last_prev2.month, 1), last_prev2
    m = re.match(r"last (\d+) (day|days|week|weeks|month|months|quarter|quarters|year|years)", s)
    if m:
        n = int(m.group(1)); unit = m.group(2).rstrip("s")
        delta = {
            "day": timedelta(days=n), "week": timedelta(days=7 * n),
            "month": timedelta(days=30 * n), "quarter": timedelta(days=91 * n),
            "year": timedelta(days=365 * n),
        }[unit]
        return today - delta, today
    raise ValueError(f"Unsupported dateRange: {date_range!r}")


def _granularity_expr(col: str, gran: str) -> str:
    return f"DATE_TRUNC('{gran}', {col})"


def _build_from(cubes: set[str]) -> tuple[str, set[str]]:
    """Pick a base cube (preferring fact tables) and join the rest in."""
    fact_priority = ["Payment", "Collection", "CreditInquiry", "Loan", "Application", "Customer", "LoanOfficer", "Branch"]
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
        elif op == "notEquals":
            quoted = ", ".join(f"'{v}'" for v in vals)
            where_parts.append(f"{col} NOT IN ({quoted})")
        elif op == "gt":
            where_parts.append(f"{col} > {vals[0]}")
        elif op == "lt":
            where_parts.append(f"{col} < {vals[0]}")
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
    else:
        time_aliases = [
            td["dimension"].replace(".", "__")
            for td in (query.get("timeDimensions") or [])
            if td.get("granularity")
        ]
        if time_aliases:
            sql += " ORDER BY " + ", ".join(f'"{a}" ASC' for a in time_aliases)
        elif query.get("measures"):
            first_alias = query["measures"][0].replace(".", "__")
            sql += f' ORDER BY "{first_alias}" DESC'
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
