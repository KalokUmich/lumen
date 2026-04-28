"""Mock provider — used by local smoke tests when no real provider is available.

Schema-aware: parses the system prompt for `Cube.member` patterns to discover
which measures/dimensions/segments exist in the current workspace, then maps
user keywords to whatever it finds. This way the mock works for any vertical
without code changes.

Stateless but message-aware: detects an existing tool_result in the conversation
to know when to emit a final_answer (vs another run_cube_query).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from .base import (
    GenerationParams,
    LLMProvider,
    ProviderHealth,
    StreamEvent,
    TierName,
    TokenUsage,
)

# ── Concept → keyword groups ──────────────────────────────────────────────────
# Each concept maps to (substrings in user question, member-name fragments to
# match against the schema). The mock picks the first concept whose user-question
# substring matches, then finds a schema member whose name contains any of the
# concept's member fragments.

_MEASURE_CONCEPTS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    # ── Lending vertical (most specific phrases first) ──
    (("default rate", "charge-off rate", "loss rate", "bad rate"),
     ("default_rate",)),
    (("delinquency", "delinquency rate", "dq rate", "past due rate"),
     ("delinquency_rate",)),
    (("approval rate", "approval %", "approval ratio", "approve rate"),
     ("approval_rate",)),
    (("late payment rate", "late rate"),
     ("late_payment_rate",)),
    (("recovery rate", "recovery %"),
     ("recovery_rate",)),
    (("originated", "origination volume", "originations", "funded amount", "principal originated", "loans originated", "loan volume", "origination"),
     ("total_originated",)),
    (("recoveries", "recovered amount", "amount recovered", "recovery"),
     ("total_recovered",)),
    (("charge-offs", "write-offs", "losses", "amount charged off"),
     ("total_charged_off", "charged_off_amount")),
    (("interest income", "interest revenue", "interest collected"),
     ("total_interest",)),
    (("late fees",), ("total_late_fees",)),
    (("cash collected", "payments received", "total payments", "collections"),
     ("total_received",)),
    (("hard inquiries", "hard inquiry count"),
     ("hard_inquiry_count",)),
    (("inquiries", "bureau pulls", "credit inquiries"),
     ("creditinquiry.count",)),
    (("how many loans", "loan count", "number of loans", "loans"),
     ("loan.count",)),
    (("how many applications", "application count", "applications"),
     ("application.count",)),
    (("how many branches", "branches"),
     ("branch.count",)),
    (("officers", "loan officers", "headcount"),
     ("loanofficer.count", "active_count")),
    (("avg fico", "average fico", "average credit score"),
     ("avg_fico",)),
    (("avg loan", "average loan size"),
     ("avg_loan_amount",)),
    (("weighted avg rate", "wac"),
     ("weighted_avg_rate",)),
    (("avg interest rate", "average apr"),
     ("avg_interest_rate",)),
    (("homeowner rate",),
     ("homeowner_rate",)),
    # AOV / average order value
    (("aov", "average order"), ("aov", "avg_total_price", "avg_order")),
    # Late rate (must come before "rate" or generic terms)
    (("late rate", "late percentage", "on-time miss", "delivery delay"),
     ("late_rate",)),
    # Return rate
    (("return rate", "returns rate", "return percentage", "% returned", "return %"),
     ("return_rate",)),
    # Inventory value
    (("inventory value", "stock value", "on-hand value", "supply value"),
     ("total_inventory_value", "inventory_value")),
    # Inventory volume / stock units
    (("inventory", "stock", "available quantity", "on hand"),
     ("total_available_quantity", "available_quantity")),
    # Supply cost
    (("supply cost", "cost per unit", "unit cost", "procurement cost"),
     ("avg_supply_cost", "supply_cost")),
    # Revenue / sales — prefer LineItem.revenue over Orders.revenue if both exist
    (("revenue", "sales", "gmv", "turnover", "top-line"),
     ("revenue", "extended_price")),
    # Order count
    (("how many orders", "order count", "number of orders", "order volume", "orders"),
     ("orders.count", "order_count")),
    # Customer count
    (("how many customers", "customer count", "customers"),
     ("customer.count", "customers.count")),
    # Supplier
    (("how many suppliers", "supplier count", "vendor count", "suppliers", "vendors"),
     ("supplier.count",)),
    # Part / product
    (("how many products", "product count", "parts", "products", "skus"),
     ("part.count", "parts.count")),
    # Line item count
    (("line items", "lineitem", "line item count"), ("lineitem.count",)),
    # Offerings (PartSupp)
    (("offerings", "sourcing", "part-supplier"), ("partsupp.count",)),
    # Quantity
    (("quantity", "units sold"), ("total_quantity", "quantity")),
    # Account balance
    (("account balance", "balance"), ("account_balance",)),
]

_DIMENSION_CONCEPTS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    # ── Lending vertical first ──
    (("grade", "risk grade", "credit grade"), ("loan.grade",)),
    (("subgrade", "sub-grade"), ("loan.subgrade",)),
    (("purpose", "use of funds"), ("loan.purpose",)),
    (("loan status", "servicing status"), ("loan.status",)),
    (("application status",), ("application.status",)),
    (("decline reason", "rejection reason", "denial reason"), ("decline_reason",)),
    (("credit tier", "risk tier", "risk band", "risk segment"), ("credit_tier",)),
    (("acquisition channel",), ("acquisition_channel",)),
    (("payment method", "payment channel"), ("payment_method",)),
    (("product", "product type", "loan type"), ("product_type",)),
    (("specialty",), ("specialty",)),
    (("bureau", "credit bureau"), ("bureau",)),
    (("inquiry type", "pull type"), ("inquiry_type",)),
    (("officer", "loan officer"), ("loanofficer.name", "officer.name")),
    (("branch",), ("branch.name",)),
    # ── TPC / generic fallbacks ──
    (("country", "countries"), ("country", "nation.name")),
    (("nation",), ("nation.name",)),
    (("region",), ("region.name", "branch.region")),
    (("status",), (".status",)),
    (("segment", "market segment", "customer segment"), ("market_segment", "mktsegment")),
    (("priority",), ("priority",)),
    (("ship mode", "shipping mode", "shipment type"), ("ship_mode",)),
    (("brand",), (".brand",)),
    (("type",), (".type",)),
    (("city",), (".city",)),
    (("state",), ("customer.state", ".state",)),
    (("channel",), ("channel",)),
]

_SEGMENT_CONCEPTS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("returned", "returns"), ("returned",)),
    (("late", "late shipment"), ("late",)),
    (("high value", "high-value"), ("high_value",)),
    (("high priority", "urgent"), ("high_priority",)),
    (("paid",), ("paid_only", "paid",)),
    (("finished", "completed"), ("finished",)),
    (("open", "in progress"), ("open",)),
]


# Known time dimension candidates (first one we find in the schema wins).
_TIME_DIMENSION_CANDIDATES = (
    "Loan.origination_date",
    "Application.application_date",
    "Payment.scheduled_date",
    "Collection.opened_date",
    "Customer.signup_date",
    "CreditInquiry.inquiry_date",
    "Orders.order_date", "Orders.created_at",
    "LineItem.ship_date", "LineItem.commit_date",
)


_MEMBER_RE = re.compile(r"\b([A-Z][A-Za-z]+)\.([a-z][a-z0-9_]*)\b")


def _extract_schema(system_blocks: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Extract Cube.member patterns from system text into measure/dimension/segment buckets."""
    text = "\n".join(b.get("text", "") for b in system_blocks if isinstance(b, dict))

    members: set[str] = {f"{m.group(1)}.{m.group(2)}" for m in _MEMBER_RE.finditer(text)}

    # We don't have a reliable in-text discriminator between measures/dimensions/segments.
    # Use heuristic markers from our schema_summary template:
    #   "(count_distinct" / "(sum" / "(avg" → measure
    #   "(time)" → time dim
    # For unknown, treat as candidate dimension.
    measures: set[str] = set()
    dimensions: set[str] = set()
    time_dimensions: set[str] = set()
    segments: set[str] = set()

    # Patterns within bullet lines like "- Foo.bar (...)"
    line_re = re.compile(r"^\s*-\s+([A-Z][A-Za-z]+)\.([a-z][a-z0-9_]*)(.*)$", re.MULTILINE)
    measure_markers = (
        "(sum", "(avg", "(count", "(number", " sum ", " avg ",
        "count_distinct", "currency)", ", currency", " / ",
        "(num ", "(median",
    )
    for m in line_re.finditer(text):
        member = f"{m.group(1)}.{m.group(2)}"
        rest = m.group(3).lower()
        if "(time)" in rest or "time)" in rest:
            time_dimensions.add(member)
            dimensions.add(member)
        elif any(token in rest for token in measure_markers):
            measures.add(member)
        else:
            dimensions.add(member)

    # Pick segments out of `## Cube` blocks containing a `Segments:` line.
    for cube_block in re.split(r"\n## Cube:", text):
        # Find lines like "Segments: Cube.foo, Cube.bar" or list-style
        seg_lines = re.findall(r"Segments?:\s*([A-Za-z0-9_, .]+)", cube_block)
        for line in seg_lines:
            for token in line.split(","):
                token = token.strip()
                if "." in token:
                    segments.add(token)

    # Fallback: every member we saw is a candidate.
    return {
        "members": members,
        "measures": measures or members,
        "dimensions": dimensions or members,
        "time_dimensions": time_dimensions,
        "segments": segments,
    }


def _find_member(
    question: str,
    pool: set[str],
    concepts: list[tuple[tuple[str, ...], tuple[str, ...]]],
    prefer_cube: str | None = None,
) -> str | None:
    """Pick the best-matching pool member for the user question.

    Scoring:
    - Concept order matters (earlier = preferred semantic).
    - Within a concept, prefer EXACT-match (member.lower endswith fragment) over substring.
    - When still tied, prefer SHORTER member names (less specific defaults).
    - Members containing 'paid_' / 'returned' / 'high_' etc. are treated as more
      specific and only chosen when the question explicitly mentions the modifier.
    - When prefer_cube is set (e.g. matching dimensions against the measure's
      cube), members from that cube get sorted first.
    """
    lower = question.lower()

    def _sort_key(m: str) -> tuple[int, int, str]:
        same_cube = 0 if (prefer_cube and m.startswith(prefer_cube + ".")) else 1
        return (same_cube, len(m), m)

    pool_list = sorted(pool, key=_sort_key)  # same-cube first, then shorter

    modifier_markers = ("paid_", "returned", "late", "high_value", "high_priority", "open", "finished")

    for keywords, member_fragments in concepts:
        if not any(k in lower for k in keywords):
            continue
        # Pass 1: exact suffix match
        for frag in member_fragments:
            for member in pool_list:
                ml = member.lower()
                if ml.endswith("." + frag) or ml.endswith(frag):
                    if any(mod in ml and mod.rstrip("_") not in lower for mod in modifier_markers):
                        continue  # skip modifier-laden member if user didn't ask for it
                    return member
        # Pass 2: substring match
        for frag in member_fragments:
            for member in pool_list:
                ml = member.lower()
                if frag in ml:
                    if any(mod in ml and mod.rstrip("_") not in lower for mod in modifier_markers):
                        continue
                    return member
    return None


def _pick_time_dimension(schema: dict[str, set[str]]) -> str | None:
    for candidate in _TIME_DIMENSION_CANDIDATES:
        if candidate in schema["members"]:
            return candidate
    if schema["time_dimensions"]:
        return next(iter(schema["time_dimensions"]))
    return None


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, *, config: dict[str, Any] | None = None, secrets: dict[str, Any] | None = None):
        super().__init__(
            config=config or {"tiers": {"strong": "mock-strong", "medium": "mock-medium", "weak": "mock-weak"}},
            secrets=secrets or {},
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, checked_at=0.0)

    async def stream(
        self,
        *,
        tier: TierName,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        params: GenerationParams,
    ) -> AsyncIterator[StreamEvent]:
        original_question = ""
        for m in messages:
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                original_question = m["content"]
                break

        has_tool_result = any(
            m.get("role") == "user"
            and isinstance(m.get("content"), list)
            and any(c.get("type") == "tool_result" for c in m["content"])
            for m in messages
        )

        schema = _extract_schema(system)
        cube_query = _build_query(original_question, schema)
        chart_spec = _chart_for(cube_query)

        if not tools:
            yield StreamEvent(kind="text", text="[mock] This is a mock LLM response.")
            yield StreamEvent(
                kind="message_stop",
                stop_reason="end_turn",
                usage=TokenUsage(input_tokens=50, output_tokens=10),
            )
            return

        if has_tool_result:
            yield StreamEvent(kind="text", text="[mock] ")
            yield StreamEvent(
                kind="tool_use",
                tool_name="final_answer",
                tool_use_id="mock_final_1",
                tool_input={
                    "text": f"[mock] Result for: {original_question}",
                    "cube_query": cube_query,
                    "chart_spec": chart_spec,
                },
            )
            yield StreamEvent(
                kind="message_stop",
                stop_reason="tool_use",
                usage=TokenUsage(input_tokens=120, output_tokens=40),
            )
            return

        yield StreamEvent(kind="text", text="[mock] Analyzing... ")
        yield StreamEvent(
            kind="tool_use",
            tool_name="run_cube_query",
            tool_use_id="mock_tool_1",
            tool_input=cube_query,
        )
        yield StreamEvent(
            kind="message_stop",
            stop_reason="tool_use",
            usage=TokenUsage(input_tokens=100, output_tokens=20),
        )


def _build_query(question: str, schema: dict[str, set[str]]) -> dict[str, Any]:
    cube_query: dict[str, Any] = {"measures": [], "dimensions": []}

    measure = _find_member(question, schema["measures"], _MEASURE_CONCEPTS)
    if not measure and schema["measures"]:
        # Fallback: prefer headline measures by name match across verticals
        # (e.g. lending → total_originated; generic → revenue), otherwise count.
        for needle in ("total_originated", "revenue"):
            for m in schema["measures"]:
                if needle in m.lower():
                    measure = m
                    break
            if measure:
                break
        if not measure:
            for m in schema["measures"]:
                if ".count" in m.lower():
                    measure = m
                    break
        if not measure:
            measure = next(iter(schema["measures"]))
    if measure:
        cube_query["measures"] = [measure]

    measure_cube = measure.split(".")[0] if measure else None
    dim = _find_member(question, schema["dimensions"], _DIMENSION_CONCEPTS, prefer_cube=measure_cube)
    if dim:
        cube_query["dimensions"] = [dim]

    seg = _find_member(question, schema["segments"], _SEGMENT_CONCEPTS)
    if seg:
        cube_query["segments"] = [seg]

    granularity = None
    for g in ("month", "quarter", "year", "day", "week"):
        if g in question.lower():
            granularity = g
            break
    date_range = None
    # "last 3 months", "last 7 days", "past 6 weeks", etc.
    rel = re.search(
        r"\b(?:last|past|previous)\s+(\d+)\s+(day|week|month|quarter|year)s?\b",
        question.lower(),
    )
    if rel:
        date_range = f"last {rel.group(1)} {rel.group(2)}s"
    else:
        for phrase in (
            "last month", "this month", "last quarter", "this quarter",
            "this year", "last year", "today", "yesterday",
            "month-to-date", "year-to-date", "mtd", "ytd",
        ):
            if phrase in question.lower():
                date_range = phrase
                break
    if granularity or date_range:
        td_dim = _pick_time_dimension(schema)
        if td_dim:
            td: dict[str, Any] = {"dimension": td_dim}
            if granularity:
                td["granularity"] = granularity
            if date_range:
                td["dateRange"] = date_range
            cube_query["timeDimensions"] = [td]

    m = re.search(r"top\s+(\d+)", question.lower())
    if m:
        cube_query["limit"] = int(m.group(1))
        if cube_query["measures"]:
            cube_query["order"] = {cube_query["measures"][0]: "desc"}

    return cube_query


def _chart_for(cube_query: dict[str, Any]) -> dict[str, Any]:
    measures = cube_query.get("measures") or []
    dimensions = cube_query.get("dimensions") or []
    has_time = bool(cube_query.get("timeDimensions"))
    if not measures:
        chart_type = "table"
    elif has_time:
        chart_type = "line"
    elif dimensions:
        chart_type = "bar"
    else:
        chart_type = "big-number"
    return {
        "type": chart_type,
        "y": {"field": measures[0], "format": "currency"} if measures else None,
    }
