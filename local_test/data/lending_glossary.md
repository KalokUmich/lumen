# Consumer Lending Glossary

Business-term glossary for the AI agent.

## Risk & credit

- **FICO score**: 300–850 scale, ≥740 prime, 670–739 near-prime, 580–669
  sub-prime, below 580 deep sub-prime.
- **Credit tier**: bucketed FICO band on the Customer cube. Use
  `Customer.credit_tier` when the user says "tier", "credit segment",
  "risk band".
- **Grade / Subgrade**: risk bucket assigned at origination by the credit
  model. A is best, G is worst. Subgrade adds 1–5 within each letter.
- **Default rate**: share of loans in `default` or `charged_off`. Use
  `Loan.default_rate`.
- **Delinquency rate**: share of loans 31+ days past due. Includes
  `late_31_120`, `default`, `charged_off`. Use `Loan.delinquency_rate`.

## Origination / funnel

- **Application**: a request to borrow. Outcomes: Approved, Declined,
  Abandoned.
- **Approval rate**: approved / total applications. Use
  `Application.approval_rate`.
- **Origination volume / Originations / Funded**: total $ of loans funded.
  Use `Loan.total_originated`.
- **Decision time**: seconds from submission to final decision. Use
  `Application.avg_decision_time_seconds`.

## Servicing & cashflow

- **Payment / Collection / Cash collected**: synonym for payment receipts.
  Use `Payment.total_received`.
- **Interest income / Interest revenue**: portion of payment classified as
  interest. Use `Payment.total_interest`.
- **Late fee**: fee charged on a late payment. Use `Payment.total_late_fees`.
- **Late payment rate**: share of payments received past the scheduled date.
  Use `Payment.late_payment_rate`.

## Recovery

- **Charge-off / Write-off / Loss**: principal we no longer expect to recover.
  Use `Loan.charged_off_amount` for loan-level, `Collection.total_charged_off`
  for collection-case-level.
- **Recovery rate**: amount_recovered / amount_charged_off in a collection
  case. Use `Collection.recovery_rate`.

## Common synonyms the agent should map

| User says            | Use this measure / dimension              |
|----------------------|-------------------------------------------|
| originations         | `Loan.total_originated`                    |
| approval rate        | `Application.approval_rate`                |
| default rate         | `Loan.default_rate`                        |
| revenue              | `Payment.total_received` (cash collected) |
| risk band / segment  | `Customer.credit_tier`                     |
| late rate            | `Payment.late_payment_rate`                |
| recovery             | `Collection.total_recovered`               |
| FICO / credit score  | `Customer.fico_score`                      |
| sub-prime            | `Customer.subprime` segment OR `Loan.subprime_grade` segment (clarify) |
