"""SSE event protocol + the tool-use orchestration loop."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog

from shared import settings as settings_module
from shared.auth import WorkspaceContext
from shared.errors import MaxAIHopsExceeded
from shared.llm_providers import LLMProvider, StreamEvent

from . import cube_runner, query_critic, visualizer
from .prompts import few_shot, system as system_prompt
from .routing import route_text_to_query
from .schemas import CubeQuery, FinalAnswerInput, tool_definitions

logger = structlog.get_logger(__name__)

MAX_HOPS = settings_module.get("ai.max_hops", 6)


@dataclass
class SSEEvent:
    event: str
    data: dict[str, Any]

    def render(self) -> str:
        # SSE wire format
        return f"event: {self.event}\ndata: {json.dumps(self.data, default=str)}\n\n"


@dataclass
class ChatContext:
    workspace_ctx: WorkspaceContext
    schema_summary: str
    glossary: str
    history: list[dict[str, Any]] = field(default_factory=list)
    # Last seen Cube query + rows; used by the visualizer subagent.
    last_cube_query: dict[str, Any] | None = None
    last_rows: list[dict[str, Any]] | None = None
    # Schema metadata indexed by Cube member name (formats, labels, etc.)
    schema_metadata: dict[str, Any] = field(default_factory=dict)


async def respond(
    question: str,
    ctx: ChatContext,
    provider: LLMProvider,
) -> AsyncIterator[SSEEvent]:
    """Drive a tool-use loop. Yield SSE events for the gateway to relay."""
    top_k = settings_module.get("ai.few_shot_top_k", 5)
    examples = few_shot.select_top_k(question, k=top_k)
    examples_str = few_shot.render_examples(examples)

    system_blocks = system_prompt.build_system_blocks(
        schema_summary=ctx.schema_summary,
        glossary=ctx.glossary,
        few_shot_examples=examples_str,
    )

    messages: list[dict[str, Any]] = list(ctx.history) + [
        {"role": "user", "content": question}
    ]

    tier, params = route_text_to_query(
        question,
        workspace_preset=ctx.workspace_ctx.workspace_preset,
    )
    yield SSEEvent("thinking", {"tier": tier, "provider": provider.name})

    tools = tool_definitions()

    for hop in range(MAX_HOPS):
        text_buffer: list[str] = []
        tool_calls: list[StreamEvent] = []
        usage: Any = None
        stop_reason: str | None = None

        async for ev in provider.stream(
            tier=tier,
            system=system_blocks,
            messages=messages,
            tools=tools,
            params=params,
        ):
            if ev.kind == "text" and ev.text:
                text_buffer.append(ev.text)
                yield SSEEvent("token", {"text": ev.text})
            elif ev.kind == "tool_use":
                tool_calls.append(ev)
            elif ev.kind == "message_stop":
                usage = ev.usage
                stop_reason = ev.stop_reason

        if usage is not None:
            yield SSEEvent("usage", {
                "tier": tier,
                "provider": provider.name,
                "hop": hop,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read": usage.cache_read_input_tokens,
                "cache_create": usage.cache_creation_input_tokens,
            })
            # Aggregate into the registry's token stats for /providers reporting.
            try:
                from shared.llm_providers import get_registry as _reg
                _reg().record_usage(
                    provider.name,
                    input_tokens=usage.input_tokens or 0,
                    output_tokens=usage.output_tokens or 0,
                    cache_read=usage.cache_read_input_tokens or 0,
                    cache_create=usage.cache_creation_input_tokens or 0,
                )
            except Exception:
                pass  # never let metric collection break the loop

        if stop_reason != "tool_use" or not tool_calls:
            # Model decided to stop without final_answer — yield whatever text we have.
            yield SSEEvent("final", {
                "text": "".join(text_buffer),
                "cube_query": None,
                "chart_spec": None,
                "incomplete": True,
            })
            return

        # Append the assistant's response (with tool_use blocks) to the conversation.
        assistant_content: list[dict[str, Any]] = []
        if text_buffer:
            assistant_content.append({"type": "text", "text": "".join(text_buffer)})
        for tc in tool_calls:
            assistant_content.append({
                "type": "tool_use",
                "id": tc.tool_use_id,
                "name": tc.tool_name,
                "input": tc.tool_input or {},
            })
        messages.append({"role": "assistant", "content": assistant_content})

        # Process each tool call.
        tool_results: list[dict[str, Any]] = []
        for tc in tool_calls:
            yield SSEEvent("tool_use", {"tool": tc.tool_name, "input": tc.tool_input})

            if tc.tool_name == "run_cube_query":
                # Validate against our Pydantic schema first — if invalid,
                # short-circuit so Claude can self-correct on the next hop.
                try:
                    validated = CubeQuery.model_validate(tc.tool_input or {})
                except Exception as e:
                    err = f"Invalid Cube query: {e}"
                    yield SSEEvent("tool_result", {"error": err})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.tool_use_id,
                        "content": err,
                        "is_error": True,
                    })
                    continue

                # Pre-execution critic: catch query-shape mismatches the
                # warehouse can't (B1: relative-time phrase but no dateRange).
                critique = query_critic.critique_query(
                    question, validated.model_dump(exclude_none=True)
                )
                if critique:
                    yield SSEEvent("tool_result", {"error": critique})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.tool_use_id,
                        "content": critique,
                        "is_error": True,
                    })
                    continue

                try:
                    result = await cube_runner.run_cube_query(
                        validated.model_dump(exclude_none=True),
                        ctx.workspace_ctx,
                    )
                    summary = cube_runner.summarize_result_for_tool(result)
                    rows = result.get("data", [])
                    yield SSEEvent("tool_result", {"rows": len(rows)})
                    # Stash for visualizer fallback path (used when the AI
                    # eventually emits final_answer).
                    ctx.last_cube_query = validated.model_dump(exclude_none=True)
                    ctx.last_rows = rows
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.tool_use_id,
                        "content": summary,
                    })
                except Exception as e:
                    err = f"Query execution failed: {e}"
                    logger.warning("cube_query_failed", error=str(e), query=tc.tool_input)
                    yield SSEEvent("tool_result", {"error": err})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.tool_use_id,
                        "content": err,
                        "is_error": True,
                    })

            elif tc.tool_name == "ask_clarification":
                question_text = (tc.tool_input or {}).get("question", "")
                yield SSEEvent("clarification", {"question": question_text})
                return

            elif tc.tool_name == "final_answer":
                try:
                    final = FinalAnswerInput.model_validate(tc.tool_input or {})
                    payload = final.model_dump(mode="json")

                    # Replace the LLM's chart_spec with the visualizer's
                    # deterministic pick when we have data to profile.
                    # If the AI passed chart_type_override (because the user
                    # explicitly asked for a chart type), respect it on top.
                    if ctx.last_rows is not None and ctx.last_cube_query is not None:
                        try:
                            spec = visualizer.select_visualization(
                                cube_query=ctx.last_cube_query,
                                rows=ctx.last_rows,
                                schema_metadata=ctx.schema_metadata,
                            )
                            override = (tc.tool_input or {}).get("chart_type_override")
                            if override:
                                spec.type = override  # type: ignore[assignment]
                                spec.rationale = (
                                    f"User explicitly requested '{override}'. "
                                    f"(Default would have been: {spec.rationale})"
                                )
                                spec.confidence = 1.0
                            payload["chart_spec"] = spec.to_dict()
                        except Exception as e:
                            logger.warning("visualizer_failed", error=str(e))

                    yield SSEEvent("final", payload)
                except Exception as e:
                    err = f"Invalid final_answer payload: {e}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.tool_use_id,
                        "content": err,
                        "is_error": True,
                    })
                    continue
                return

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    raise MaxAIHopsExceeded()
