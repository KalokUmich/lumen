"""Seed a local DuckDB warehouse with the TPC-H business dataset.

Uses DuckDB's built-in `tpch` extension — no download required.
SF=1 produces ~1GB of data (1.5M orders, 6M lineitems).
SF=0.1 (~100MB) is the default for fast iteration.

Also writes:
  - data/tpch_schema_summary.txt — Cube schema summarized for AI prompt grounding
  - data/tpch_glossary.md — TPC-H business glossary
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DUCKDB_PATH = Path(os.environ.get("LOCAL_TPCH_DUCKDB_PATH", DATA_DIR / "tpch.duckdb"))


SCHEMA_SUMMARY = """\
# Cube Semantic Model — TPC-H Vertical

This workspace models a wholesale/distribution business with customers, orders, line items, parts, suppliers, and geography.

## Cube: Region
Description: Geographic regions (5: AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST).
- Region.name (string) — region name
- Region.count (count_distinct) — number of regions

## Cube: Nation
Description: Countries (25), grouped under Region.
- Nation.name (string) — nation name (e.g. UNITED STATES, GERMANY, JAPAN)
- Joins to Region via n_regionkey

## Cube: Customer
Description: Customers placing orders, tagged by nation and market segment.
- Customer.market_segment (string) — AUTOMOBILE, BUILDING, FURNITURE, MACHINERY, HOUSEHOLD
    synonyms: [segment, customer segment]
    ai_hint: "When users say 'segment' they usually mean this field"
- Customer.account_balance (number) — account balance (USD), can be negative
- Customer.count (count_distinct id) — total customers
    synonyms: [customers, num_customers]
- Customer.avg_account_balance (avg c_acctbal, currency)
- Customer.total_account_balance (sum c_acctbal, currency)
- Joins to Nation via c_nationkey

## Cube: Orders
Description: One row per customer order. Header-level facts (volume, priority, total_price).
- Orders.status (string) — F=Finished, O=Open, P=Partial
    ai_hint: "F=fully shipped; O=in progress; P=partial. For 'completed' filter status='F'"
- Orders.order_date (time) — date placed
- Orders.order_priority (string) — 1-URGENT, 2-HIGH, 3-MEDIUM, 4-NOT SPECIFIED, 5-LOW
- Orders.count (count_distinct) — number of orders
    synonyms: [orders, transactions, order_count]
- Orders.total_price (sum o_totalprice, currency) — sum of header total_price (NOT canonical revenue; use LineItem.revenue)
- Orders.avg_total_price (avg o_totalprice, currency)
    synonyms: [aov, average order value]
- Joins to Customer via o_custkey
- Segments: Orders.open, Orders.finished, Orders.high_priority

## Cube: LineItem  ← the canonical fact table
Description: One row per item per order. This is where TRUE revenue lives.
- LineItem.ship_date (time) — date the line item shipped
- LineItem.commit_date (time) — committed ship date
- LineItem.receipt_date (time) — date received
- LineItem.ship_mode (string) — AIR, SHIP, RAIL, TRUCK, MAIL, FOB, REG AIR
- LineItem.return_flag (string) — R=returned, N=not yet returned, A=accepted/closed
- LineItem.line_status (string) — F or O
- LineItem.revenue (sum extended_price * (1-discount), currency)
    description: "CANONICAL REVENUE for any sales question"
    synonyms: [sales, gmv, top-line, turnover, total sales, revenue]
    ai_hint: "ALWAYS use this for 'revenue' / 'sales'; never use Orders.total_price for revenue"
- LineItem.revenue_with_tax (sum extended_price * (1-discount) * (1+tax), currency)
- LineItem.discount_amount (sum extended_price * discount, currency)
- LineItem.count (count) — number of line items
- LineItem.total_quantity (sum quantity) — total units
- LineItem.avg_extended_price (avg extended_price, currency)
- Joins to Orders via l_orderkey
- Segments: LineItem.returned, LineItem.shipped, LineItem.late

## Cube: Supplier
- Supplier.name (string)
- Supplier.account_balance (number)
- Supplier.count (count_distinct)
    synonyms: [suppliers, vendors]
- Supplier.avg_account_balance (avg, currency)
- Joins to Nation

## Cube: Part
- Part.brand (string) — brand id like "Brand#13"
- Part.type (string) — multi-word type (e.g. "PROMO POLISHED COPPER")
- Part.size (number)
- Part.container (string)
- Part.retail_price (number)
- Part.count (count_distinct)
    synonyms: [products, parts, sku count]
- Part.avg_retail_price (avg, currency)

## Common queries
- "Revenue by nation" → measures: [LineItem.revenue], dimensions: [Nation.name]
- "Top 5 segments by revenue" → measures: [LineItem.revenue], dimensions: [Customer.market_segment], order desc, limit 5
- "Order count this year" → measures: [Orders.count], timeDimensions: [{Orders.order_date, dateRange: 'this year'}]
- "Returned line items by ship mode" → measures: [LineItem.count], dimensions: [LineItem.ship_mode], segments: [LineItem.returned]
"""


GLOSSARY = """\
# TPC-H Business Glossary

## Revenue
The canonical revenue metric is **LineItem.revenue**, defined as
`SUM(l_extendedprice * (1 - l_discount))`. This is grounded in line-item
facts, accounts for discount, and is the right answer for any "sales" or
"revenue" question.

Do NOT use `Orders.total_price` for revenue questions — that's a header-level
aggregate that ignores discounts and is less authoritative.

## Customer Segment
"Segment" in this business means `Customer.market_segment`, one of:
AUTOMOBILE, BUILDING, FURNITURE, MACHINERY, HOUSEHOLD.

## Order Status
- F = Finished (fully shipped)
- O = Open (in progress)
- P = Partial (some items shipped, some not)

For "completed orders" or "fulfilled orders", filter to `status='F'`.

## Region vs Nation
- 5 regions (continents): AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST
- 25 nations (countries) grouped under regions
- Customers and Suppliers belong to Nations; aggregate up to Region for high-level views.

## Returns
A line item is "returned" when `l_returnflag = 'R'`. The `LineItem.returned`
segment captures this.

## Late Shipments
A line item is "late" when `l_receiptdate > l_commitdate`. The `LineItem.late`
segment captures this.
"""


def seed(scale_factor: float, threads: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()

    print(f"Generating TPC-H scale_factor={scale_factor} into {DUCKDB_PATH}")
    print(f"(For SF=1 expect ~1GB and ~30s on a fast laptop)")

    start = time.monotonic()
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute(f"PRAGMA threads={threads}")
    con.execute("INSTALL tpch")
    con.execute("LOAD tpch")
    con.execute(f"CALL dbgen(sf={scale_factor})")

    # Sanity check
    counts = {}
    for table in ["region", "nation", "supplier", "part", "partsupp",
                  "customer", "orders", "lineitem"]:
        counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    revenue = con.execute(
        "SELECT SUM(l_extendedprice * (1 - l_discount)) FROM lineitem"
    ).fetchone()[0]

    con.close()

    schema_path = DATA_DIR / "tpch_schema_summary.txt"
    glossary_path = DATA_DIR / "tpch_glossary.md"
    schema_path.write_text(SCHEMA_SUMMARY)
    glossary_path.write_text(GLOSSARY)

    elapsed = time.monotonic() - start
    print(f"\nGenerated in {elapsed:.1f}s")
    for table, count in counts.items():
        print(f"  {table:<10}  {count:>12,}")
    print(f"\n  total revenue: ${revenue:,.2f}")
    print(f"\nWrote schema summary → {schema_path}")
    print(f"Wrote glossary       → {glossary_path}")
    print(f"\nDone. To run the smoke test:")
    print(f"  python local_test/run_local_test.py --mock --vertical tpch")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--sf",
        type=float,
        default=float(os.environ.get("LUMEN_TPCH_SF", "0.1")),
        help="Scale factor (0.01 ~ 1MB, 0.1 ~ 100MB, 1 ~ 1GB, 10 ~ 10GB)",
    )
    p.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("LUMEN_TPCH_THREADS", "4")),
        help="DuckDB threads for generation",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    seed(scale_factor=args.sf, threads=args.threads)
    sys.exit(0)
