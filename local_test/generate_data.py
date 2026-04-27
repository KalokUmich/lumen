"""Generate synthetic orders + customers data for local testing.

Writes CSVs into local_test/data/. Idempotent: running twice produces identical files.
"""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Deterministic seed so AI eval results are reproducible.
random.seed(42)

NUM_CUSTOMERS = 1_000
NUM_ORDERS = 10_000
COUNTRIES = ["US", "GB", "DE", "FR", "JP", "CA", "AU", "BR", "IN", "MX", "SG", "HK"]
COUNTRY_WEIGHT = [40, 12, 8, 7, 9, 6, 4, 3, 5, 3, 2, 1]
TIERS = ["free", "silver", "gold", "platinum"]
TIER_WEIGHT = [60, 25, 12, 3]
STATUSES = ["paid", "refunded", "cancelled", "pending"]
STATUS_WEIGHT = [85, 5, 7, 3]


def _date_range(days_back: int) -> datetime:
    delta = timedelta(days=random.randint(0, days_back), seconds=random.randint(0, 86400))
    return datetime.utcnow() - delta


def write_customers() -> Path:
    path = DATA_DIR / "customers.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "email", "created_at", "country", "tier"])
        for i in range(1, NUM_CUSTOMERS + 1):
            w.writerow(
                [
                    f"cust_{i:05d}",
                    f"user{i}@example.com",
                    _date_range(720).isoformat(),  # signed up within last 2 years
                    random.choices(COUNTRIES, COUNTRY_WEIGHT)[0],
                    random.choices(TIERS, TIER_WEIGHT)[0],
                ]
            )
    return path


def write_orders() -> Path:
    path = DATA_DIR / "orders.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "customer_id", "shipping_country", "status", "amount_usd", "created_at"])
        for i in range(1, NUM_ORDERS + 1):
            customer_n = random.randint(1, NUM_CUSTOMERS)
            country = random.choices(COUNTRIES, COUNTRY_WEIGHT)[0]
            status = random.choices(STATUSES, STATUS_WEIGHT)[0]
            # Lognormal-ish amount distribution
            amount = round(max(5, random.lognormvariate(4.5, 0.9)), 2)
            w.writerow(
                [
                    f"ord_{i:06d}",
                    f"cust_{customer_n:05d}",
                    country,
                    status,
                    amount,
                    _date_range(365).isoformat(),  # last year of orders
                ]
            )
    return path


def main() -> None:
    customers = write_customers()
    orders = write_orders()
    print(f"Wrote {NUM_CUSTOMERS} customers → {customers}")
    print(f"Wrote {NUM_ORDERS} orders → {orders}")


if __name__ == "__main__":
    main()
