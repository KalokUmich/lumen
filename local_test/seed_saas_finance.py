"""Seed a synthetic SaaS-finance dataset into a separate DuckDB file.

Demonstrates the multi-vertical workspace pattern: a customer can have a
TPC-H workspace AND a SaaS-finance workspace, each with its own schema +
data + AI grounding.

Generates ~5,000 accounts, ~12,000 subscriptions, ~80,000 invoices —
small but realistic enough for AI eval testing.
"""

from __future__ import annotations

import argparse
import os
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DUCKDB_PATH = Path(os.environ.get("LOCAL_SAAS_DUCKDB_PATH", DATA_DIR / "saas_finance.duckdb"))

random.seed(7)

INDUSTRIES = ["SaaS", "Finance", "Healthcare", "Retail", "Manufacturing", "Education", "Other"]
COUNTRIES = ["US", "GB", "DE", "FR", "JP", "CA", "AU", "BR", "IN", "MX", "SG", "HK"]
PLAN_TIERS = ["Free", "Starter", "Growth", "Enterprise"]
TIER_WEIGHT = [50, 25, 18, 7]
TIER_MRR_RANGE = {
    "Free": (0, 0),
    "Starter": (50, 200),
    "Growth": (300, 1500),
    "Enterprise": (2000, 25000),
}


def _date_between(start: date, end: date) -> date:
    delta_days = (end - start).days
    if delta_days <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta_days))


def seed(num_accounts: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()

    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("""
        CREATE SCHEMA IF NOT EXISTS main;
        CREATE TABLE main.accounts (
            id            VARCHAR PRIMARY KEY,
            company_name  VARCHAR,
            industry      VARCHAR,
            country       VARCHAR,
            signup_date   TIMESTAMP,
            plan_tier     VARCHAR,
            status        VARCHAR
        );
        CREATE TABLE main.subscriptions (
            id                  VARCHAR PRIMARY KEY,
            account_id          VARCHAR,
            plan_tier           VARCHAR,
            monthly_amount_usd  DOUBLE,
            started_at          TIMESTAMP,
            ended_at            TIMESTAMP
        );
        CREATE TABLE main.invoices (
            id           VARCHAR PRIMARY KEY,
            account_id   VARCHAR,
            amount_usd   DOUBLE,
            issued_at    TIMESTAMP,
            due_at       TIMESTAMP,
            paid_at      TIMESTAMP,
            status       VARCHAR
        );
    """)

    today = date.today()
    two_years_ago = today - timedelta(days=730)

    accounts: list[tuple] = []
    subs: list[tuple] = []
    invoices: list[tuple] = []

    for i in range(num_accounts):
        account_id = f"acct_{i:06d}"
        signup = _date_between(two_years_ago, today)
        plan_tier = random.choices(PLAN_TIERS, TIER_WEIGHT)[0]
        # 12% of accounts churned
        status = "churned" if random.random() < 0.12 else random.choice(["active", "active", "active", "paused"])
        accounts.append((
            account_id,
            f"Company {i:06d}",
            random.choice(INDUSTRIES),
            random.choice(COUNTRIES),
            signup,
            plan_tier,
            status,
        ))

        # Subscriptions: paid tiers always have one; Free might not
        if plan_tier == "Free" and random.random() < 0.3:
            continue

        # The current subscription
        lo, hi = TIER_MRR_RANGE[plan_tier]
        if hi == 0:
            current_mrr = 0
        else:
            current_mrr = round(random.uniform(lo, hi), 2)

        sub_started = signup + timedelta(days=random.randint(0, 30))
        sub_ended: date | None = None
        if status == "churned":
            sub_ended = _date_between(sub_started + timedelta(days=30), today)
        subs.append((
            f"sub_{uuid.uuid4().hex[:10]}",
            account_id,
            plan_tier,
            current_mrr,
            sub_started,
            sub_ended,
        ))

        # Invoices: monthly issuance from sub start to either ended_at or today
        end_billing = sub_ended or today
        cur = sub_started
        invoice_n = 0
        while cur < end_billing and invoice_n < 36:  # cap at 36 invoices
            issued = cur
            due = cur + timedelta(days=30)
            # 92% paid, 5% overdue, 2% pending, 1% written off
            r = random.random()
            if r < 0.92:
                inv_status = "paid"
                paid_at = due - timedelta(days=random.randint(-3, 25))
            elif r < 0.97:
                inv_status = "overdue"
                paid_at = None
            elif r < 0.99:
                inv_status = "pending"
                paid_at = None
            else:
                inv_status = "written_off"
                paid_at = None
            invoices.append((
                f"inv_{uuid.uuid4().hex[:12]}",
                account_id,
                current_mrr,
                issued,
                due,
                paid_at,
                inv_status,
            ))
            cur += timedelta(days=30)
            invoice_n += 1

    # Bulk insert via DuckDB's native arrow integration is fastest, but
    # falling back to staging tables works without extra deps.
    import csv
    import tempfile

    def _bulk(table: str, cols: list[str], rows: list[tuple]) -> None:
        if not rows:
            return
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow(["" if v is None else v for v in r])
            path = f.name
        con.execute(f"COPY main.{table} FROM '{path}' (HEADER, DELIMITER ',', NULLSTR '')")
        os.unlink(path)

    _bulk("accounts", ["id","company_name","industry","country","signup_date","plan_tier","status"], accounts)
    _bulk("subscriptions", ["id","account_id","plan_tier","monthly_amount_usd","started_at","ended_at"], subs)
    _bulk("invoices", ["id","account_id","amount_usd","issued_at","due_at","paid_at","status"], invoices)

    print(f"Seeded {DUCKDB_PATH}")
    counts = {}
    for t in ["accounts", "subscriptions", "invoices"]:
        counts[t] = con.execute(f"SELECT COUNT(*) FROM main.{t}").fetchone()[0]
    mrr = con.execute(
        "SELECT SUM(monthly_amount_usd) FROM main.subscriptions WHERE ended_at IS NULL"
    ).fetchone()[0] or 0
    collected = con.execute(
        "SELECT SUM(amount_usd) FROM main.invoices WHERE status='paid'"
    ).fetchone()[0] or 0

    con.close()

    for t, c in counts.items():
        print(f"  {t:14}  {c:>10,}")
    print(f"  active MRR:    ${mrr:,.2f}")
    print(f"  collected:     ${collected:,.2f}")
    print()
    print("To use this vertical, create a workspace pointing to it:")
    print("  curl -X POST http://localhost:8000/api/v1/workspaces \\")
    print("    -H 'authorization: Bearer dev:user-1:ws-demo:admin:balanced' \\")
    print("    -H 'content-type: application/json' \\")
    print("    -d '{\"slug\":\"saas-demo\",\"name\":\"SaaS Finance\",\"vertical\":\"saas_finance\"}'")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--accounts", type=int, default=5000, help="Number of accounts")
    args = p.parse_args()
    seed(args.accounts)
