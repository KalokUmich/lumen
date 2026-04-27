"""Run a Cube query through the query_service.

In production this calls the query_service over HTTP. For local tests it can
hit Cube directly via env CUBE_API_URL.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from shared.auth import WorkspaceContext, mint_internal_token

QUERY_SERVICE_URL = os.environ.get("QUERY_SERVICE_URL", "http://localhost:8002")
TIMEOUT = httpx.Timeout(30.0, connect=5.0)


async def run_cube_query(query: dict[str, Any], ctx: WorkspaceContext) -> dict[str, Any]:
    """Run a query through query_service. Returns {data: [...], annotation: {...}}."""
    token = mint_internal_token(ctx)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{QUERY_SERVICE_URL}/internal/queries/run",
            headers={"X-Internal-Token": token},
            json={"cube_query": query},
        )
        resp.raise_for_status()
        return resp.json()


def summarize_result_for_tool(result: dict[str, Any], max_rows: int = 30) -> str:
    """Summarize Cube results for inclusion in a tool_result message back to Claude.

    We don't want to send 10k rows back into the prompt. Truncate + describe.
    """
    rows = result.get("data", [])
    n = len(rows)
    if n == 0:
        return "Query returned 0 rows."
    sample = rows[:max_rows]
    truncated_note = f" (showing first {max_rows} of {n})" if n > max_rows else ""
    import json
    return f"Query returned {n} rows{truncated_note}.\n{json.dumps(sample, indent=2, default=str)}"
