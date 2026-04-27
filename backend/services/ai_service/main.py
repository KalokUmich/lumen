"""AI Service — FastAPI app.

Endpoints:
    POST /chat/respond                 SSE-streamed AI response
    GET  /health                       basic health
    GET  /providers                    LLM provider health + which tiers each can serve
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared.auth import WorkspaceContext, workspace_ctx_dep
from shared.llm_providers import get_registry
from shared.observability import setup_observability

from .stream import ChatContext, respond


class RespondRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability("ai_service")
    registry = get_registry()
    await registry.startup()
    app.state.registry = registry
    app.state.http = httpx.AsyncClient(timeout=10.0)
    yield
    await app.state.http.aclose()


app = FastAPI(title="Lumen AI Service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/providers")
async def providers() -> dict[str, Any]:
    return get_registry().health_report()


@app.post("/chat/respond")
async def chat_respond(
    body: RespondRequest,
    ctx: WorkspaceContext = Depends(workspace_ctx_dep),
):
    """Stream an AI response as SSE.

    The gateway proxies this directly to the browser.
    """
    schema_summary, glossary, schema_metadata = await _load_schema_bundle(
        ctx.workspace_id, app.state.http
    )
    chat_ctx = ChatContext(
        workspace_ctx=ctx,
        schema_summary=schema_summary,
        glossary=glossary,
        history=body.history,
        schema_metadata=schema_metadata,
    )

    async def event_gen():
        provider = app.state.registry.resolve_provider()
        async for event in respond(body.question, chat_ctx, provider):
            yield event.render()

    return StreamingResponse(event_gen(), media_type="text/event-stream")


async def _load_schema_bundle(
    workspace_id: str, client: httpx.AsyncClient
) -> tuple[str, str, dict]:
    """Fetch the compiled cube schema bundle (summary + glossary + metadata).

    Order of precedence:
    1. WORKSPACE_SERVICE_URL → fetch via HTTP (production path)
    2. In-process schema_bundle module reading the YAML files (Phase 0)
    3. Env-pointed local files (legacy local_test path)
    """
    workspace_url = os.environ.get("WORKSPACE_SERVICE_URL")
    if workspace_url:
        try:
            r = await client.get(f"{workspace_url}/internal/workspaces/{workspace_id}/schema-bundle")
            if r.status_code == 200:
                data = r.json()
                return data["schema_summary"], data.get("glossary", ""), data.get("metadata", {})
        except httpx.HTTPError:
            pass

    # Phase 0 in-process fallback: read straight from YAML by vertical name.
    vertical = os.environ.get("LUMEN_DEFAULT_VERTICAL", "tpch")
    try:
        from shared.schema_bundle import get_bundle
        bundle = get_bundle(vertical)
        if bundle["schema_summary"]:
            return bundle["schema_summary"], bundle.get("glossary", ""), bundle.get("metadata", {})
    except Exception:
        pass

    # Last resort: env-pointed files (legacy)
    schema_path = os.environ.get("LOCAL_SCHEMA_SUMMARY_PATH", "/tmp/schema_summary.txt")
    glossary_path = os.environ.get("LOCAL_GLOSSARY_PATH", "/tmp/glossary.md")
    schema = ""
    glossary = ""
    try:
        with open(schema_path) as f:
            schema = f.read()
    except FileNotFoundError:
        schema = "(no schema available)"
    try:
        with open(glossary_path) as f:
            glossary = f.read()
    except FileNotFoundError:
        glossary = ""
    return schema, glossary, {}
