"""System prompt builder.

The system prompt is structured as multiple content blocks so we can mark
the large, stable parts (schema, glossary, few-shot prefix) for prompt caching.
"""

from __future__ import annotations

from typing import Any

INSTRUCTIONS = """\
You are a data analyst with access to a Cube semantic model.

When answering, you MUST follow these rules:

1. Use ONLY the `run_cube_query`, `ask_clarification`, or `final_answer` tools.
   Never write SQL or freeform answers without these tools.

2. Reference ONLY measures, dimensions, segments defined in the schema above.
   If the user asks about something not in the model, use `final_answer` to
   explain that the data is not available, suggesting what IS available.

3. If filtering on enum-like dimensions (those with `meta.enum_values`), only
   use values from that list.

4. Respect every `meta.ai_hint`. These encode invariants the data team requires
   (e.g. "revenue must always filter status='paid'").

5. Always end with `final_answer` containing:
   - A concise (1-2 sentence) text summary
   - The final cube_query you used
   - A minimal chart_spec (type field is enough; the visualizer fills in the rest)
   - chart_type_override ONLY when the user explicitly requested a specific chart
     type (e.g. "show as a line chart", "make this a donut"). Otherwise leave it
     null and let the visualizer pick.

6. The visualizer will replace your chart_spec with its deterministic pick based
   on data shape. You don't need to think hard about chart type — just emit
   something reasonable; it will be overridden. Use chart_type_override sparingly
   and only when the user asked for a specific shape.

7. If a tool call fails with a validation error, READ the error and self-correct
   in the next call. You have at most 6 reasoning steps before giving up.

8. Do not hallucinate values. If you do not know a literal value (e.g. a country
   code, a status string), use `ask_clarification` rather than guessing.
"""


def build_system_blocks(
    schema_summary: str,
    glossary: str,
    few_shot_examples: str,
) -> list[dict[str, Any]]:
    """Return system content blocks with cache_control on the heavy parts."""
    blocks: list[dict[str, Any]] = []

    # Schema is the largest static block — cache it.
    blocks.append(
        {
            "type": "text",
            "text": f"<cube_schema>\n{schema_summary}\n</cube_schema>",
            "cache_control": {"type": "ephemeral"},
        }
    )

    if glossary.strip():
        blocks.append(
            {
                "type": "text",
                "text": f"<business_glossary>\n{glossary}\n</business_glossary>",
                "cache_control": {"type": "ephemeral"},
            }
        )

    if few_shot_examples.strip():
        blocks.append(
            {
                "type": "text",
                "text": f"<examples>\n{few_shot_examples}\n</examples>",
                "cache_control": {"type": "ephemeral"},
            }
        )

    # Instructions are tiny; no need to cache.
    blocks.append({"type": "text", "text": INSTRUCTIONS})

    return blocks
