# SaaS Finance Business Glossary

## MRR (Monthly Recurring Revenue)
The canonical SaaS top-line metric. Sum of monthly subscription amounts across
all currently-active subscriptions. Use `Subscriptions.mrr` with the
`Subscriptions.active` segment.

## ARR (Annual Recurring Revenue)
MRR × 12. Use `Subscriptions.arr` directly.

## Active Customer
An account in `status='active'` AND has at least one currently-active
subscription. Default to `Accounts.active_count` for "how many customers" type
questions.

## Churn
An account whose status transitioned from `active` to `churned`. We track this
at the account level (logo churn), not at the dollar level (revenue churn).
For revenue churn, look at MRR loss month-over-month.

## Plan Tiers
- **Free** — non-paying, growth funnel input
- **Starter** — entry paid plan
- **Growth** — mid-tier
- **Enterprise** — top tier; custom pricing

For "paying customers" questions, filter to `paying` segment (excludes Free).

## Collection vs Billed
- **Billed** = invoiced amount (any status)
- **Collected** = paid invoices only
The gap is your accounts receivable (AR balance, aka outstanding amount).

## DSO (Days Sales Outstanding)
v2 metric — needs a calculated diff between `Invoices.issued_at` and
`Invoices.paid_at`. Coming in the next iteration of this vertical.
