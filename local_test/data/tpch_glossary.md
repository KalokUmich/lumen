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
