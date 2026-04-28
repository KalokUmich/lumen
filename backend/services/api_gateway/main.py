"""API Gateway / BFF — entrypoint for the frontend.

Responsibilities:
- Auth (verify external JWT, mint internal JWT for downstream).
- Route requests to the right service.
- Stream SSE from AI service straight through to the browser.
- Emit per-request audit log.
- Apply rate limiting (Redis token bucket) — TODO Phase 0 sprint 3.

Kept thin on purpose: zero business logic.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared import audit
from shared.auth import WorkspaceContext, mint_internal_token
from shared.observability import setup_observability

logger = structlog.get_logger(__name__)

AI_SERVICE_URL = os.environ.get("AI_SERVICE_URL", "http://localhost:8001")
QUERY_SERVICE_URL = os.environ.get("QUERY_SERVICE_URL", "http://localhost:8002")
WORKSPACE_SERVICE_URL = os.environ.get("WORKSPACE_SERVICE_URL", "http://localhost:8004")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability("api_gateway")
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    yield
    await app.state.http.aclose()


app = FastAPI(title="Omni API Gateway", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Generic request-audit middleware (Phase 1 M8 — every authenticated request
# emits a structured audit line, in addition to the action-specific calls
# inside individual handlers).
@app.middleware("http")
async def request_audit_middleware(request: Any, call_next: Any) -> Any:
    import time as _t
    start = _t.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((_t.perf_counter() - start) * 1000, 1)
    # Skip cosmetic noise: CORS preflight, /health, static assets.
    path = str(request.url.path)
    method = request.method
    if method == "OPTIONS" or path in ("/health", "/healthz") or path.startswith("/static"):
        return response
    auth = request.headers.get("authorization", "")
    actor = "anonymous"
    workspace = "-"
    if auth.startswith("Bearer dev:"):
        parts = auth.removeprefix("Bearer dev:").split(":")
        if len(parts) >= 3:
            actor = parts[0]
            workspace = parts[1]
    try:
        audit.emit(
            actor_user_id=actor,
            workspace_id=workspace,
            action=f"{method} {path}",
            resource_type="http_request",
            metadata={"status": response.status_code, "ms": elapsed_ms},
        )
    except Exception:
        pass  # never let auditing break a request
    return response


# ----- Auth dependency (placeholder: will use OIDC in Phase 1, sprint 8) -----


async def current_user(
    authorization: str = Header(...),
) -> WorkspaceContext:
    """In dev we accept a simple bearer token of form `dev:<user_id>:<workspace_id>:<role>`.

    In Phase 1 this is replaced by JWT verification via the auth_service.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization[7:]
    if token.startswith("dev:"):
        parts = token.split(":")
        if len(parts) < 4:
            raise HTTPException(401, "Malformed dev token")
        return WorkspaceContext(
            user_id=parts[1],
            workspace_id=parts[2],
            role=parts[3],
            user_attrs={},
            workspace_preset=parts[4] if len(parts) > 4 else "balanced",
        )
    raise HTTPException(401, "Unsupported token format (Phase 0 dev only accepts dev:* tokens)")


# ----- Routes -----


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/me")
async def me(ctx: WorkspaceContext = Depends(current_user)) -> dict[str, Any]:
    return {
        "user_id": ctx.user_id,
        "workspace_id": ctx.workspace_id,
        "role": ctx.role,
        "preset": ctx.workspace_preset,
    }


class RunQueryRequest(BaseModel):
    cube_query: dict[str, Any]


@app.post("/api/v1/queries/run")
async def run_query(
    body: RunQueryRequest,
    ctx: WorkspaceContext = Depends(current_user),
) -> dict[str, Any]:
    audit.emit(
        actor_user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        action="query.run",
        resource_type="cube_query",
        metadata={"measures": body.cube_query.get("measures")},
    )
    token = mint_internal_token(ctx)
    r = await app.state.http.post(
        f"{QUERY_SERVICE_URL}/internal/queries/run",
        headers={"X-Internal-Token": token},
        json={"cube_query": body.cube_query},
    )
    r.raise_for_status()
    return r.json()


class ChatRespondRequest(BaseModel):
    question: str
    history: list[dict[str, Any]] = []


@app.post("/api/v1/chat/respond")
async def chat_respond(
    body: ChatRespondRequest,
    ctx: WorkspaceContext = Depends(current_user),
):
    """Proxy SSE stream from ai_service straight through to the browser."""
    audit.emit(
        actor_user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        action="ai.chat.respond",
        resource_type="chat",
        metadata={"question_preview": body.question[:120]},
    )
    token = mint_internal_token(ctx)

    async def event_proxy():
        async with app.state.http.stream(
            "POST",
            f"{AI_SERVICE_URL}/chat/respond",
            headers={"X-Internal-Token": token, "Accept": "text/event-stream"},
            json=body.model_dump(),
            timeout=httpx.Timeout(120.0),
        ) as r:
            async for chunk in r.aiter_bytes():
                yield chunk

    return StreamingResponse(event_proxy(), media_type="text/event-stream")


# ── Workspace / workbook proxies ─────────────────────────────────────────────


async def _proxy_get(url: str) -> Any:
    r = await app.state.http.get(url)
    r.raise_for_status()
    return r.json()


async def _proxy_post(url: str, body: dict[str, Any]) -> Any:
    r = await app.state.http.post(url, json=body)
    r.raise_for_status()
    return r.json()


@app.get("/api/v1/workspaces")
async def workspaces(_ctx: WorkspaceContext = Depends(current_user)) -> Any:
    return await _proxy_get(f"{WORKSPACE_SERVICE_URL}/workspaces")


@app.post("/api/v1/workspaces")
async def create_workspace(
    body: dict[str, Any] = Body(...),
    ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    audit.emit(
        actor_user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        action="workspace.create",
        resource_type="workspace",
        metadata={"slug": body.get("slug"), "vertical": body.get("vertical")},
    )
    return await _proxy_post(f"{WORKSPACE_SERVICE_URL}/workspaces", body)


@app.get("/api/v1/workspaces/{workspace_id}/schema-bundle")
async def schema_bundle(
    workspace_id: str,
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_get(
        f"{WORKSPACE_SERVICE_URL}/internal/workspaces/{workspace_id}/schema-bundle"
    )


@app.get("/api/v1/workbooks")
async def workbooks(
    workspace_id: str,
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_get(f"{WORKSPACE_SERVICE_URL}/workbooks?workspace_id={workspace_id}")


@app.post("/api/v1/workbooks")
async def create_workbook(
    body: dict[str, Any] = Body(...),
    ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    audit.emit(
        actor_user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        action="workbook.create",
        resource_type="workbook",
        metadata={"name": body.get("name")},
    )
    return await _proxy_post(f"{WORKSPACE_SERVICE_URL}/workbooks", body)


@app.get("/api/v1/providers")
async def providers(_ctx: WorkspaceContext = Depends(current_user)) -> Any:
    return await _proxy_get(f"{AI_SERVICE_URL}/providers")


# ── Chat session persistence (proxied to workspace_service) ──────────────────


@app.get("/api/v1/chat/sessions")
async def list_chat_sessions(
    workspace_id: str,
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_get(f"{WORKSPACE_SERVICE_URL}/chat/sessions?workspace_id={workspace_id}")


@app.post("/api/v1/chat/sessions")
async def create_chat_session(
    body: dict[str, Any] = Body(...),
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_post(f"{WORKSPACE_SERVICE_URL}/chat/sessions", body)


@app.get("/api/v1/chat/sessions/{session_id}/messages")
async def list_chat_messages(
    session_id: str,
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_get(f"{WORKSPACE_SERVICE_URL}/chat/sessions/{session_id}/messages")


@app.post("/api/v1/chat/sessions/{session_id}/messages")
async def append_chat_message(
    session_id: str,
    body: dict[str, Any] = Body(...),
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_post(f"{WORKSPACE_SERVICE_URL}/chat/sessions/{session_id}/messages", body)


@app.delete("/api/v1/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    r = await app.state.http.delete(f"{WORKSPACE_SERVICE_URL}/chat/sessions/{session_id}")
    r.raise_for_status()
    return r.json()


# ── Model editor (proxied to workspace_service) ──────────────────────────────


@app.get("/api/v1/model/files")
async def list_model_files(_ctx: WorkspaceContext = Depends(current_user)) -> Any:
    return await _proxy_get(f"{WORKSPACE_SERVICE_URL}/model/files")


@app.get("/api/v1/model/files/{path:path}")
async def get_model_file(path: str, _ctx: WorkspaceContext = Depends(current_user)) -> Any:
    return await _proxy_get(f"{WORKSPACE_SERVICE_URL}/model/files/{path}")


@app.put("/api/v1/model/files/{path:path}")
async def save_model_file(
    path: str,
    body: dict[str, Any] = Body(...),
    ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    audit.emit(
        actor_user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        action="model.save",
        resource_type="model_file",
        metadata={"path": path},
    )
    r = await app.state.http.put(f"{WORKSPACE_SERVICE_URL}/model/files/{path}", json=body)
    r.raise_for_status()
    return r.json()


@app.post("/api/v1/model/validate")
async def validate_model(
    body: dict[str, Any] = Body(...),
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_post(f"{WORKSPACE_SERVICE_URL}/model/validate", body)


@app.get("/api/v1/model/locate")
async def locate_member(
    member: str,
    _ctx: WorkspaceContext = Depends(current_user),
) -> Any:
    return await _proxy_get(f"{WORKSPACE_SERVICE_URL}/model/locate?member={member}")
