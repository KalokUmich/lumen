"""Seed a local DuckDB warehouse from the synthetic CSVs.

Also writes:
  - data/schema_summary.txt — Cube schema summarized for AI prompt grounding
  - data/glossary.md — example business glossary
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from local_test import generate_data

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DUCKDB_PATH = Path(os.environ.get("LOCAL_DUCKDB_PATH", DATA_DIR / "warehouse.duckdb"))


SCHEMA_SUMMARY = """\
# Cube Semantic Model Summary

## Cube: Orders
Description: One row per customer order. Used for revenue, order volume, and
customer purchase behavior analysis. Only orders with status='paid' count as revenue.

### Dimensions
- Orders.id (string, primary key)
- Orders.status (string) — Order lifecycle status.
    enum_values: [paid, refunded, cancelled, pending]
    ai_hint: "Filter to status='paid' for revenue queries."
- Orders.created_at (time) — When the order was placed (UTC).
- Orders.country (string) — Country shipped to (ISO 2-letter).
    synonyms: [region, ship_to_country, market]
- Orders.customer_id (string) — Foreign key to Customers.id.

### Measures
- Orders.revenue (sum of amount_usd, filtered to status='paid', currency)
    Description: Total paid order amount in USD. Excludes refunded and cancelled.
    synonyms: [sales, gmv, top-line, turnover, total_sales]
- Orders.order_count (count_distinct id)
    Description: Number of unique orders, any status.
    synonyms: [orders, transactions, num_orders]
- Orders.paid_order_count (count_distinct id, filtered status='paid')
    synonyms: [paid_orders, completed_orders]
- Orders.aov (revenue / paid_order_count, currency)
    Description: Average Order Value — paid revenue per paid order.
    synonyms: [average_order_value, avg_ticket]

### Segments
- Orders.high_value — Orders over $1000.
- Orders.paid_only — Only paid orders.

### Joins
- Orders.customer_id → Customers.id (many_to_one)


## Cube: Customers
Description: One row per customer. Joined to Orders for purchase history.

### Dimensions
- Customers.id (string, primary key)
- Customers.email (string, PII — admin only)
- Customers.signup_date (time) — When the customer signed up.
- Customers.country (string) — Customer's home country (ISO 2-letter).
- Customers.tier (string) — Loyalty tier.
    enum_values: [free, silver, gold, platinum]

### Measures
- Customers.count (count_distinct id) — Total unique customers.
    synonyms: [customer_count, num_customers]
- Customers.count_with_orders (count_distinct id, with at least one paid order)
    synonyms: [active_customers, paying_customers, buyers]

### Segments
- Customers.gold_or_platinum — High-tier customers.
"""

GLOSSARY = """\
# Business Glossary

## Active Customer
A customer who placed at least one paid order in the last 90 days.
Use the Customers.count_with_orders measure with a date filter.

## Fiscal Year
Our fiscal year matches the calendar year. Use Orders.created_at directly.

## Region Mapping
- APAC = JP, KR, SG, HK, TW, AU, NZ
- EMEA = GB, DE, FR + all European countries + ME + Africa
- AMER = US, CA, MX, BR + LATAM
"""


def seed() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    customers_csv = DATA_DIR / "customers.csv"
    orders_csv = DATA_DIR / "orders.csv"

    if not customers_csv.exists() or not orders_csv.exists():
        print("Generating CSVs first…")
        generate_data.main()

    print(f"Opening DuckDB at {DUCKDB_PATH}")
    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
    con = duckdb.connect(str(DUCKDB_PATH))

    con.execute(
        """
        CREATE SCHEMA IF NOT EXISTS public;
        CREATE TABLE public.customers (
            id           VARCHAR PRIMARY KEY,
            email        VARCHAR,
            created_at   TIMESTAMP,
            country      VARCHAR,
            tier         VARCHAR
        );
        CREATE TABLE public.orders (
            id                VARCHAR PRIMARY KEY,
            customer_id       VARCHAR,
            shipping_country  VARCHAR,
            status            VARCHAR,
            amount_usd        DOUBLE,
            created_at        TIMESTAMP
        );
        """
    )

    con.execute(f"COPY public.customers FROM '{customers_csv}' (HEADER, DELIMITER ',')")
    con.execute(f"COPY public.orders FROM '{orders_csv}' (HEADER, DELIMITER ',')")

    con.execute("CREATE INDEX idx_orders_status ON public.orders(status)")
    con.execute("CREATE INDEX idx_orders_country ON public.orders(shipping_country)")
    con.execute("CREATE INDEX idx_orders_created ON public.orders(created_at)")

    cust_count = con.execute("SELECT COUNT(*) FROM public.customers").fetchone()[0]
    ord_count = con.execute("SELECT COUNT(*) FROM public.orders").fetchone()[0]
    paid_revenue = con.execute(
        "SELECT SUM(amount_usd) FROM public.orders WHERE status='paid'"
    ).fetchone()[0]

    con.close()

    schema_path = DATA_DIR / "schema_summary.txt"
    glossary_path = DATA_DIR / "glossary.md"
    schema_path.write_text(SCHEMA_SUMMARY)
    glossary_path.write_text(GLOSSARY)

    print(f"  customers: {cust_count:,}")
    print(f"  orders:    {ord_count:,}")
    print(f"  paid revenue: ${paid_revenue:,.2f}")
    print(f"Wrote schema summary → {schema_path}")
    print(f"Wrote glossary → {glossary_path}")
    print("\nDone. To run the smoke test:  python local_test/run_local_test.py --mock")


if __name__ == "__main__":
    seed()
