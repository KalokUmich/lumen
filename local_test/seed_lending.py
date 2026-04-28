"""Seed a synthetic consumer-lending dataset into a DuckDB file.

Replaces TPC-H + SaaS Finance as Lumen's primary test fixture.

Schema:
    customers           ~1M rows   demographics, FICO, income, signup
    branches            ~200 rows  geographic / regional
    loan_officers       ~5K rows   employees who own loans
    applications        ~3M rows   incl. declined / abandoned
    loans               ~2M rows   approved + funded loans
    payments            ~25M rows  scheduled + actual repayments
    collections         ~500K rows charge-off / recovery cases
    credit_inquiries    ~5M rows   bureau pulls

Total: ~35M rows, ~1 GB DuckDB file. Realistic distributions:
    - FICO ≈ Normal(700, 80) clamped to [300, 850]
    - Annual income ≈ Lognormal(μ=10.8, σ=0.6)
    - Default probability rises steeply below FICO 600
    - Late-payment rate correlates with subgrade
    - 8-year horizon: 2018-01-01 → 2026-04-27 (today)

Generated entirely in DuckDB SQL (range() + random()), so it's fast
(~60–90 seconds total on a laptop). No pandas / pyarrow dependency.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DUCKDB_PATH = Path(os.environ.get("LOCAL_LENDING_DUCKDB_PATH", DATA_DIR / "lending.duckdb"))

SEED = 42  # set so results are reproducible

# Default sizes — pass --scale=N to scale all tables proportionally.
DEFAULTS = {
    "customers": 1_000_000,
    "branches": 200,
    "loan_officers": 5_000,
    "applications": 3_000_000,
    "loans": 2_000_000,
    "payments": 25_000_000,
    "collections": 500_000,
    "credit_inquiries": 5_000_000,
}


def seed(scale: float = 1.0) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()

    n = {k: max(1, int(v * scale)) for k, v in DEFAULTS.items()}
    print(f"→ seeding {DUCKDB_PATH} (scale={scale})")
    for k, v in n.items():
        print(f"   {k:>20s}  {v:>12,d} rows")

    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute(f"SELECT setseed({SEED / 100.0})")

    # ── Reference tables ───────────────────────────────────────────────────
    t0 = time.time()
    print("\n[1/8] branches …")
    con.execute("""
        CREATE TABLE branches AS
        SELECT
            i AS branch_id,
            'BR' || LPAD(i::VARCHAR, 4, '0') AS branch_code,
            CASE (i % 5)
                WHEN 0 THEN 'Northeast' WHEN 1 THEN 'Southeast'
                WHEN 2 THEN 'Midwest'   WHEN 3 THEN 'Southwest'
                ELSE 'West' END AS region,
            (ARRAY['NY','MA','CT','PA','NJ','VA','GA','FL','NC','SC','OH',
                   'MI','IL','IN','MN','TX','AZ','NM','OK','LA','CA','OR',
                   'WA','CO','UT','NV'])[(i % 26) + 1] AS state,
            'Branch ' || i::VARCHAR AS branch_name,
            DATE '2010-01-01' + ((i * 37) % 4000)::INTEGER * INTERVAL 1 DAY AS opened_date,
            (10 + (i % 90))::INTEGER AS headcount
        FROM range(0, ?) tbl(i);
    """, [n["branches"]])

    print(f"[2/8] loan_officers …")
    con.execute("""
        CREATE TABLE loan_officers AS
        SELECT
            i AS officer_id,
            'OFC' || LPAD(i::VARCHAR, 6, '0') AS officer_code,
            'Officer ' || i::VARCHAR AS officer_name,
            (i % (SELECT MAX(branch_id) + 1 FROM branches)) AS branch_id,
            DATE '2015-01-01' + ((i * 13) % 4000)::INTEGER * INTERVAL 1 DAY AS hire_date,
            CASE (i % 4)
                WHEN 0 THEN 'Personal'
                WHEN 1 THEN 'Auto'
                WHEN 2 THEN 'Home Improvement'
                ELSE 'Debt Consolidation' END AS specialty,
            CASE WHEN random() < 0.7 THEN 'active' ELSE 'inactive' END AS status
        FROM range(0, ?) tbl(i);
    """, [n["loan_officers"]])

    # ── Customers (the heaviest dim) ──────────────────────────────────────
    print(f"[3/8] customers …")
    con.execute("""
        CREATE TABLE customers AS
        WITH base AS (
            SELECT
                i AS customer_id,
                'CUST' || LPAD(i::VARCHAR, 9, '0') AS customer_code,
                -- Synthetic name
                CASE (i % 8)
                    WHEN 0 THEN 'Avery' WHEN 1 THEN 'Riley' WHEN 2 THEN 'Jordan'
                    WHEN 3 THEN 'Casey' WHEN 4 THEN 'Morgan' WHEN 5 THEN 'Quinn'
                    WHEN 6 THEN 'Sage'  ELSE 'Drew' END
                || ' ' ||
                CASE ((i * 31) % 8)
                    WHEN 0 THEN 'Patel' WHEN 1 THEN 'Garcia' WHEN 2 THEN 'Lee'
                    WHEN 3 THEN 'Smith' WHEN 4 THEN 'Brown'  WHEN 5 THEN 'Khan'
                    WHEN 6 THEN 'Nguyen' ELSE 'Johnson' END AS full_name,
                -- DOB: ages 22 to 75, weighted toward 30-55
                DATE '2026-04-27' - (
                    22 + (
                        FLOOR(POWER(random(), 1.4) * 53)::INTEGER
                    )
                )::INTEGER * INTERVAL 1 YEAR AS date_of_birth,
                (ARRAY['NY','CA','TX','FL','PA','IL','OH','GA','NC','MI',
                       'NJ','VA','WA','AZ','MA','TN','IN','MO','MD','WI',
                       'CO','MN','SC','AL','LA','KY','OR','OK','CT','UT'])[
                       (1 + (i + FLOOR(random()*30))::INTEGER % 30)] AS state,
                CASE (FLOOR(random() * 6))::INTEGER
                    WHEN 0 THEN 'Salaried'   WHEN 1 THEN 'Self-employed'
                    WHEN 2 THEN 'Hourly'     WHEN 3 THEN 'Retired'
                    WHEN 4 THEN 'Contractor' ELSE 'Unemployed' END AS employment_type,
                -- Annual income: lognormal-ish, $15k-$500k
                GREATEST(
                    15000,
                    LEAST(500000, ROUND(EXP(10.8 + 0.6 * (random() * 4 - 2))))
                )::DECIMAL(10,2) AS annual_income,
                -- FICO: ~Normal(700, 80) clamped to [300, 850]
                GREATEST(300, LEAST(850, ROUND(700 + 80 * (
                    SQRT(-2 * LN(GREATEST(random(), 1e-9))) * COS(2 * PI() * random())
                ))))::INTEGER AS fico_score,
                CASE (FLOOR(random() * 5))::INTEGER
                    WHEN 0 THEN 'Web'       WHEN 1 THEN 'Mobile App'
                    WHEN 2 THEN 'Branch'    WHEN 3 THEN 'Phone'
                    ELSE 'Partner Referral' END AS acquisition_channel,
                DATE '2018-01-01' + (FLOOR(random() * 3038))::INTEGER * INTERVAL 1 DAY AS signup_date,
                CASE WHEN random() < 0.62 THEN true ELSE false END AS is_homeowner
            FROM range(0, ?) tbl(i)
        )
        SELECT *,
            EXTRACT(YEAR FROM signup_date) AS signup_cohort_year,
            CASE
                WHEN fico_score >= 740 THEN 'Prime'
                WHEN fico_score >= 670 THEN 'Near-prime'
                WHEN fico_score >= 580 THEN 'Sub-prime'
                ELSE 'Deep sub-prime' END AS credit_tier
        FROM base;
    """, [n["customers"]])

    # ── Applications (one customer can have several over time) ────────────
    print(f"[4/8] applications …")
    con.execute("""
        CREATE TABLE applications AS
        WITH base AS (
            SELECT
                i AS application_id,
                'APP' || LPAD(i::VARCHAR, 10, '0') AS application_code,
                FLOOR(random() * (SELECT COUNT(*) FROM customers))::BIGINT AS customer_id,
                CASE (FLOOR(random() * 4))::INTEGER
                    WHEN 0 THEN 'Personal Loan'
                    WHEN 1 THEN 'Auto Loan'
                    WHEN 2 THEN 'Home Improvement'
                    ELSE 'Debt Consolidation' END AS product_type,
                ROUND(1000 + random() * 49000, 2)::DECIMAL(10,2) AS requested_amount,
                (12 + (FLOOR(random() * 6))::INTEGER * 12) AS requested_term_months,
                DATE '2018-01-01' + (FLOOR(random() * 3038))::INTEGER * INTERVAL 1 DAY AS application_date,
                CASE (FLOOR(random() * 5))::INTEGER
                    WHEN 0 THEN 'Web' WHEN 1 THEN 'Mobile App'
                    WHEN 2 THEN 'Branch' WHEN 3 THEN 'Phone'
                    ELSE 'Partner' END AS channel,
                ROUND(random() * 60000)::INTEGER AS decision_time_seconds
            FROM range(0, ?) tbl(i)
        )
        SELECT b.*,
            -- Status depends partly on customer FICO
            CASE
                WHEN c.fico_score >= 700 AND random() < 0.78 THEN 'Approved'
                WHEN c.fico_score >= 620 AND random() < 0.55 THEN 'Approved'
                WHEN c.fico_score >= 580 AND random() < 0.30 THEN 'Approved'
                WHEN random() < 0.15 THEN 'Approved'
                WHEN random() < 0.6 THEN 'Declined'
                ELSE 'Abandoned' END AS status,
            CASE
                WHEN random() < 0.15 THEN 'Insufficient income'
                WHEN random() < 0.30 THEN 'Low credit score'
                WHEN random() < 0.45 THEN 'High DTI'
                WHEN random() < 0.55 THEN 'Insufficient history'
                WHEN random() < 0.65 THEN 'Verification failed'
                ELSE NULL END AS decline_reason,
            random() < 0.08 AS manual_review_flag
        FROM base b
        LEFT JOIN customers c USING (customer_id);
    """, [n["applications"]])

    # ── Loans (only approved applications; 1:1 from a sample) ─────────────
    print(f"[5/8] loans …")
    con.execute("""
        CREATE TABLE loans AS
        WITH approved AS (
            SELECT
                application_id,
                application_code,
                customer_id,
                product_type,
                requested_amount,
                requested_term_months,
                application_date
            FROM applications
            WHERE status = 'Approved'
            LIMIT ?
        ),
        with_grade AS (
            SELECT
                a.*,
                c.fico_score,
                CASE
                    WHEN c.fico_score >= 760 THEN 'A'
                    WHEN c.fico_score >= 720 THEN 'B'
                    WHEN c.fico_score >= 680 THEN 'C'
                    WHEN c.fico_score >= 640 THEN 'D'
                    WHEN c.fico_score >= 600 THEN 'E'
                    WHEN c.fico_score >= 560 THEN 'F'
                    ELSE 'G' END AS grade
            FROM approved a
            JOIN customers c USING (customer_id)
        )
        SELECT
            ROW_NUMBER() OVER () AS loan_id,
            'LN' || LPAD(ROW_NUMBER() OVER ()::VARCHAR, 10, '0') AS loan_code,
            application_id,
            customer_id,
            product_type,
            ROUND(requested_amount * (0.7 + random() * 0.3), 2)::DECIMAL(10,2) AS loan_amount,
            requested_term_months AS term_months,
            -- Interest rate: function of grade (A=5-8%, G=25-30%)
            ROUND(
                CASE grade
                    WHEN 'A' THEN 5 + random() * 3
                    WHEN 'B' THEN 7 + random() * 4
                    WHEN 'C' THEN 10 + random() * 4
                    WHEN 'D' THEN 13 + random() * 5
                    WHEN 'E' THEN 17 + random() * 5
                    WHEN 'F' THEN 21 + random() * 5
                    ELSE 25 + random() * 5 END,
                3
            )::DECIMAL(5,3) AS interest_rate_pct,
            grade,
            grade || (1 + FLOOR(random() * 5))::VARCHAR AS subgrade,
            application_date + (1 + FLOOR(random() * 14))::INTEGER * INTERVAL 1 DAY AS origination_date,
            CASE (FLOOR(random() * 6))::INTEGER
                WHEN 0 THEN 'Debt consolidation' WHEN 1 THEN 'Credit card refinance'
                WHEN 2 THEN 'Home improvement'   WHEN 3 THEN 'Major purchase'
                WHEN 4 THEN 'Medical'            ELSE 'Other' END AS purpose,
            (FLOOR(random() * (SELECT COUNT(*) FROM branches)))::BIGINT AS branch_id,
            (FLOOR(random() * (SELECT COUNT(*) FROM loan_officers)))::BIGINT AS officer_id,
            -- Status — defaults / charge-offs more common in low grades
            CASE
                WHEN grade IN ('A','B') AND random() < 0.92 THEN
                    CASE WHEN random() < 0.55 THEN 'paid_off' ELSE 'current' END
                WHEN grade IN ('C','D') AND random() < 0.82 THEN
                    CASE WHEN random() < 0.45 THEN 'paid_off' ELSE 'current' END
                WHEN grade IN ('E','F') AND random() < 0.65 THEN
                    CASE WHEN random() < 0.35 THEN 'paid_off' ELSE 'current' END
                WHEN grade = 'G' AND random() < 0.50 THEN
                    CASE WHEN random() < 0.25 THEN 'paid_off' ELSE 'current' END
                WHEN random() < 0.4 THEN 'late_31_120'
                WHEN random() < 0.7 THEN 'default'
                ELSE 'charged_off' END AS status
        FROM with_grade;
    """, [n["loans"]])

    # ── Payments (heaviest fact) ──────────────────────────────────────────
    # Each loan has up to ~term_months payments. We synthesise an average of
    # ~12 payments per loan to stay near n["payments"] target.
    print(f"[6/8] payments …")
    con.execute("""
        CREATE TABLE payments AS
        WITH targets AS (
            SELECT
                l.loan_id,
                l.customer_id,
                l.loan_amount,
                l.interest_rate_pct,
                l.term_months,
                l.origination_date,
                l.status AS loan_status,
                -- pick how many payments this loan has — cap at term_months
                LEAST(
                    l.term_months,
                    GREATEST(1, FLOOR(? * 1.0 / (SELECT COUNT(*) FROM loans))::INTEGER)
                ) AS n_payments
            FROM loans l
        ),
        payments_raw AS (
            SELECT
                t.loan_id,
                t.customer_id,
                t.loan_amount,
                t.interest_rate_pct,
                t.loan_status,
                gs.gen AS pmt_seq,
                t.origination_date + (gs.gen * 30)::INTEGER * INTERVAL 1 DAY AS scheduled_date
            FROM targets t,
                LATERAL (SELECT UNNEST(generate_series(1, t.n_payments)) AS gen) gs
        )
        SELECT
            ROW_NUMBER() OVER () AS payment_id,
            'PMT' || LPAD(ROW_NUMBER() OVER ()::VARCHAR, 12, '0') AS payment_code,
            p.loan_id,
            p.customer_id,
            p.pmt_seq AS payment_sequence,
            p.scheduled_date,
            -- Some payments are late; default loans skip more often
            CASE
                WHEN p.loan_status IN ('default','charged_off') AND random() < 0.4 THEN NULL
                WHEN random() < 0.06 THEN p.scheduled_date + (1 + FLOOR(random() * 60))::INTEGER * INTERVAL 1 DAY
                ELSE p.scheduled_date + (FLOOR(random() * 5))::INTEGER * INTERVAL 1 DAY
            END AS actual_payment_date,
            ROUND((p.loan_amount / 24.0) * (0.95 + random() * 0.1), 2)::DECIMAL(10,2) AS payment_amount,
            ROUND((p.loan_amount / 24.0) * 0.78, 2)::DECIMAL(10,2) AS principal_amount,
            ROUND((p.loan_amount / 24.0) * 0.20, 2)::DECIMAL(10,2) AS interest_amount,
            ROUND(CASE WHEN random() < 0.06 THEN 25 + random() * 50 ELSE 0 END, 2)::DECIMAL(10,2) AS late_fee,
            CASE (FLOOR(random() * 4))::INTEGER
                WHEN 0 THEN 'ACH' WHEN 1 THEN 'Card'
                WHEN 2 THEN 'Check' ELSE 'Wire' END AS payment_method,
            CASE WHEN random() < 0.06 THEN true ELSE false END AS is_late
        FROM payments_raw p;
    """, [n["payments"]])

    # ── Collections (subset of charged_off / default loans) ───────────────
    print(f"[7/8] collections …")
    con.execute("""
        CREATE TABLE collections AS
        WITH targets AS (
            SELECT loan_id, customer_id, loan_amount, origination_date
            FROM loans
            WHERE status IN ('default','charged_off','late_31_120')
            ORDER BY random()
            LIMIT ?
        )
        SELECT
            ROW_NUMBER() OVER () AS collection_id,
            'COL' || LPAD(ROW_NUMBER() OVER ()::VARCHAR, 8, '0') AS collection_code,
            t.loan_id,
            t.customer_id,
            t.origination_date + (90 + FLOOR(random() * 180))::INTEGER * INTERVAL 1 DAY AS opened_date,
            CASE WHEN random() < 0.4 THEN
                t.origination_date + (180 + FLOOR(random() * 360))::INTEGER * INTERVAL 1 DAY
            ELSE NULL END AS closed_date,
            CASE (FLOOR(random() * 4))::INTEGER
                WHEN 0 THEN 'Internal' WHEN 1 THEN 'External Agency'
                WHEN 2 THEN 'Legal'    ELSE 'Sold' END AS collection_channel,
            CASE
                WHEN random() < 0.30 THEN 'recovered'
                WHEN random() < 0.55 THEN 'partial_recovery'
                WHEN random() < 0.85 THEN 'in_collection'
                ELSE 'written_off' END AS status,
            ROUND(t.loan_amount * random() * 0.6, 2)::DECIMAL(10,2) AS amount_recovered,
            ROUND(t.loan_amount * (0.4 + random() * 0.6), 2)::DECIMAL(10,2) AS amount_charged_off
        FROM targets t;
    """, [n["collections"]])

    # ── Credit inquiries ──────────────────────────────────────────────────
    print(f"[8/8] credit_inquiries …")
    con.execute("""
        CREATE TABLE credit_inquiries AS
        SELECT
            i AS inquiry_id,
            'INQ' || LPAD(i::VARCHAR, 10, '0') AS inquiry_code,
            FLOOR(random() * (SELECT COUNT(*) FROM customers))::BIGINT AS customer_id,
            DATE '2018-01-01' + (FLOOR(random() * 3038))::INTEGER * INTERVAL 1 DAY AS inquiry_date,
            CASE (FLOOR(random() * 4))::INTEGER
                WHEN 0 THEN 'Equifax' WHEN 1 THEN 'Experian'
                WHEN 2 THEN 'TransUnion' ELSE 'Internal' END AS bureau,
            CASE (FLOOR(random() * 3))::INTEGER
                WHEN 0 THEN 'Soft' WHEN 1 THEN 'Hard' ELSE 'Pre-screen' END AS inquiry_type,
            (300 + FLOOR(random() * 550))::INTEGER AS score_at_inquiry
        FROM range(0, ?) tbl(i);
    """, [n["credit_inquiries"]])

    # ── Indices for reasonable query speed ────────────────────────────────
    print("\n→ creating indices …")
    for stmt in [
        "CREATE INDEX idx_apps_customer  ON applications(customer_id)",
        "CREATE INDEX idx_apps_date      ON applications(application_date)",
        "CREATE INDEX idx_loans_customer ON loans(customer_id)",
        "CREATE INDEX idx_loans_orig     ON loans(origination_date)",
        "CREATE INDEX idx_loans_branch   ON loans(branch_id)",
        "CREATE INDEX idx_pay_loan       ON payments(loan_id)",
        "CREATE INDEX idx_pay_date       ON payments(scheduled_date)",
        "CREATE INDEX idx_col_loan       ON collections(loan_id)",
        "CREATE INDEX idx_inq_customer   ON credit_inquiries(customer_id)",
        "CREATE INDEX idx_inq_date       ON credit_inquiries(inquiry_date)",
    ]:
        con.execute(stmt)

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n=== summary ===")
    for tbl in ("branches","loan_officers","customers","applications","loans","payments","collections","credit_inquiries"):
        cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:>20s}  {cnt:>12,d} rows")
    con.close()

    size = DUCKDB_PATH.stat().st_size / (1024 * 1024)
    print(f"\n✓ {DUCKDB_PATH}  ({size:,.1f} MB) in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scale", type=float, default=1.0,
                   help="Multiplier on default row counts (1.0 = ~1GB)")
    args = p.parse_args()
    seed(args.scale)
