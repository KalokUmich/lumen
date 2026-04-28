"""Tests that lock in the LLM-facing tool contracts.

Per `.claude/skills/data-transform/SKILL.md` §5, the tool descriptions are
prompt-engineered for routing accuracy. Any change to these strings should
be intentional and re-evaluated against the golden set — failing this test
means someone edited a description without going through the documented
review process.
"""

from __future__ import annotations

from services.ai_service.schemas import tool_definitions


def test_default_tool_set_excludes_dataframe_transform():
    tools = tool_definitions()
    names = [t["name"] for t in tools]
    assert names == ["run_cube_query", "ask_clarification", "final_answer"]


def test_enabling_flag_exposes_dataframe_transform():
    tools = tool_definitions(enable_dataframe_transform=True)
    names = [t["name"] for t in tools]
    assert "run_dataframe_transform" in names


def test_run_cube_query_description_says_default():
    tools = tool_definitions()
    cube = next(t for t in tools if t["name"] == "run_cube_query")
    desc = cube["description"]
    assert "DEFAULT" in desc
    assert "aggregation" in desc.lower()
    assert "do not use the pandas transform" in desc.lower()


def test_dataframe_transform_description_lists_five_intents():
    tools = tool_definitions(enable_dataframe_transform=True)
    transform = next(t for t in tools if t["name"] == "run_dataframe_transform")
    desc = transform["description"]
    # The closed list of allowed intents — see SKILL §3.
    for keyword in [
        "rolling",
        "cohort",
        "reshape",
        "statistics",
        "multi-source",
    ]:
        assert keyword.lower() in desc.lower(), f"description must mention '{keyword}'"
    assert "high" in desc.lower(), "must signal that the bar to use this tool is HIGH"


def test_dataframe_transform_input_schema_requires_intent():
    tools = tool_definitions(enable_dataframe_transform=True)
    transform = next(t for t in tools if t["name"] == "run_dataframe_transform")
    schema = transform["input_schema"]
    assert "intent" in schema["required"]
    assert "cube_query" in schema["required"]
    assert "pandas_code" in schema["required"]
