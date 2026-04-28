"""Workspace Service — workspaces, dashboards, workbooks, schema bundles for AI.

Phase 0: SQLite-backed (or whatever databases.app_db.url is configured to).
Schema bundles are derived from backend/cube/schema/verticals/<vertical>/.

Endpoints:
  GET  /health
  GET  /verticals                              — list known vertical templates
  GET  /internal/workspaces/{id}/schema-bundle — schema_summary + glossary for AI
  GET  /workspaces                              — list (workspace memberships honored later)
  POST /workspaces                              — create
  GET  /workspaces/{id}
  PATCH /workspaces/{id}                        — update name / llm_preset
  GET  /workbooks?workspace_id=...
  POST /workbooks
  GET  /workbooks/{id}
  PATCH /workbooks/{id}
  DELETE /workbooks/{id}
  GET  /dashboards?workspace_id=...
  POST /dashboards
  GET  /dashboards/{id}
  PATCH /dashboards/{id}
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.app_db import (
    ChatMessage,
    ChatSession,
    Dashboard,
    Schedule,
    User,
    Workbook,
    Workspace,
    WorkspaceMembership,
    init_schema,
    session_dep,
)
from shared.observability import setup_observability
from shared.schema_bundle import get_bundle, list_verticals


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability("workspace_service")
    await init_schema()
    await _bootstrap_demo_workspace()
    yield


app = FastAPI(title="Lumen Workspace Service", lifespan=lifespan)


# ── Models ────────────────────────────────────────────────────────────────────


class WorkspaceCreate(BaseModel):
    slug: str
    name: str
    vertical: str = "lending"
    llm_preset: str = "balanced"


class WorkspacePatch(BaseModel):
    name: str | None = None
    llm_preset: str | None = None


class WorkbookCreate(BaseModel):
    workspace_id: str
    name: str
    cube_query: dict[str, Any]
    chart_spec: dict[str, Any]


class WorkbookPatch(BaseModel):
    name: str | None = None
    cube_query: dict[str, Any] | None = None
    chart_spec: dict[str, Any] | None = None


class DashboardCreate(BaseModel):
    workspace_id: str
    name: str
    layout: list[dict[str, Any]] = []
    filters: list[dict[str, Any]] = []


# ── Bootstrap demo workspace ──────────────────────────────────────────────────


async def _bootstrap_demo_workspace() -> None:
    """Ensure a demo workspace + user + a few demo workbooks/dashboard exist."""
    from shared.app_db import get_session_maker

    sm = get_session_maker()
    async with sm() as s:
        existing = (await s.execute(select(Workspace).where(Workspace.slug == "demo"))).scalar_one_or_none()
        if existing:
            return

        ws = Workspace(
            id="ws-demo",
            slug="demo",
            name="Demo (Consumer Lending)",
            vertical="lending",
            llm_preset="balanced",
            cube_schema_ref="local",
        )
        user = User(id="user-1", email="dev@local", display_name="Dev User", attributes={})
        membership = WorkspaceMembership(workspace_id="ws-demo", user_id="user-1", role="admin")
        s.add_all([ws, user, membership])

        # Seed a handful of starter workbooks so the dashboard surface shows
        # something on first run (also gives e2e tests a chart to interact with).
        starter_workbooks = [
            ("wb-orig-by-grade", "Origination volume by grade",
             {"measures": ["Loan.total_originated"], "dimensions": ["Loan.grade"]},
             {"type": "bar", "x": {"field": "Loan__grade", "type": "ordinal"}, "y": {"field": "Loan__total_originated", "format": "currency"}}),
            ("wb-default-by-grade", "Default rate by grade",
             {"measures": ["Loan.default_rate"], "dimensions": ["Loan.grade"]},
             {"type": "bar", "x": {"field": "Loan__grade", "type": "ordinal"}, "y": {"field": "Loan__default_rate", "format": "percent"}}),
            ("wb-trend-12m", "Origination volume — last 12 months",
             {"measures": ["Loan.total_originated"],
              "timeDimensions": [{"dimension": "Loan.origination_date", "granularity": "month", "dateRange": "last 12 months"}]},
             {"type": "line", "x": {"field": "Loan__origination_date", "type": "time"}, "y": {"field": "Loan__total_originated", "format": "currency"}}),
            ("wb-approval-by-product", "Approval rate by product type",
             {"measures": ["Application.approval_rate"], "dimensions": ["Application.product_type"]},
             {"type": "bar", "x": {"field": "Application__product_type", "type": "ordinal"}, "y": {"field": "Application__approval_rate", "format": "percent"}}),
            ("wb-recovery-by-channel", "Recovery rate by collection channel",
             {"measures": ["Collection.recovery_rate"], "dimensions": ["Collection.channel"]},
             {"type": "bar", "x": {"field": "Collection__channel", "type": "ordinal"}, "y": {"field": "Collection__recovery_rate", "format": "percent"}}),
        ]
        for wb_id, name, cq, cs in starter_workbooks:
            s.add(Workbook(
                id=wb_id, workspace_id="ws-demo", name=name,
                cube_query=cq, chart_spec=cs, created_by="user-1",
            ))

        # Seed a default dashboard with two of those tiles laid out.
        s.add(Dashboard(
            id="dash-demo",
            workspace_id="ws-demo",
            name="Lending Overview",
            layout=[
                {"i": "wb-orig-by-grade",     "x": 0, "y": 0, "w": 6, "h": 4},
                {"i": "wb-default-by-grade",  "x": 6, "y": 0, "w": 6, "h": 4},
                {"i": "wb-trend-12m",         "x": 0, "y": 4, "w": 12, "h": 4},
                {"i": "wb-approval-by-product","x": 0, "y": 8, "w": 6, "h": 4},
                {"i": "wb-recovery-by-channel","x": 6, "y": 8, "w": 6, "h": 4},
            ],
            filters=[],
            created_by="user-1",
        ))
        await s.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/verticals")
async def verticals() -> dict[str, list[str]]:
    return {"verticals": list_verticals()}


@app.get("/internal/workspaces/{workspace_id}/schema-bundle")
async def schema_bundle(
    workspace_id: str,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    ws = (await s.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404, f"Workspace {workspace_id} not found")
    bundle = get_bundle(ws.vertical)
    return {
        "workspace_id": workspace_id,
        "vertical": ws.vertical,
        "schema_summary": bundle["schema_summary"],
        "glossary": bundle.get("glossary", ""),
        "metadata": bundle.get("metadata", {}),
        "skills": bundle.get("skills", []),
    }


@app.get("/workspaces")
async def list_workspaces(s: AsyncSession = Depends(session_dep)) -> list[dict[str, Any]]:
    result = (await s.execute(select(Workspace))).scalars().all()
    return [
        {
            "id": w.id,
            "slug": w.slug,
            "name": w.name,
            "vertical": w.vertical,
            "llm_preset": w.llm_preset,
        }
        for w in result
    ]


@app.post("/workspaces")
async def create_workspace(
    body: WorkspaceCreate,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    ws = Workspace(
        id=f"ws-{uuid.uuid4().hex[:8]}",
        slug=body.slug,
        name=body.name,
        vertical=body.vertical,
        llm_preset=body.llm_preset,
    )
    s.add(ws)
    await s.commit()
    return {"id": ws.id, "slug": ws.slug}


@app.get("/workspaces/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    ws = (await s.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404)
    return {
        "id": ws.id,
        "slug": ws.slug,
        "name": ws.name,
        "vertical": ws.vertical,
        "llm_preset": ws.llm_preset,
    }


@app.patch("/workspaces/{workspace_id}")
async def patch_workspace(
    workspace_id: str,
    body: WorkspacePatch,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    ws = (await s.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one_or_none()
    if not ws:
        raise HTTPException(404)
    if body.name is not None:
        ws.name = body.name
    if body.llm_preset is not None:
        ws.llm_preset = body.llm_preset
    await s.commit()
    return {"id": ws.id, "name": ws.name, "llm_preset": ws.llm_preset}


# ── Workbooks ─────────────────────────────────────────────────────────────────


@app.get("/workbooks")
async def list_workbooks(
    workspace_id: str,
    s: AsyncSession = Depends(session_dep),
) -> list[dict[str, Any]]:
    rows = (await s.execute(select(Workbook).where(Workbook.workspace_id == workspace_id))).scalars().all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "cube_query": w.cube_query,
            "chart_spec": w.chart_spec,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
        }
        for w in rows
    ]


@app.post("/workbooks")
async def create_workbook(
    body: WorkbookCreate,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    wb = Workbook(
        id=f"wb-{uuid.uuid4().hex[:8]}",
        workspace_id=body.workspace_id,
        name=body.name,
        cube_query=body.cube_query,
        chart_spec=body.chart_spec,
        created_by="user-1",  # dev: replace with real auth in Phase 1
    )
    s.add(wb)
    await s.commit()
    return {"id": wb.id, "name": wb.name}


@app.get("/workbooks/{workbook_id}")
async def get_workbook(
    workbook_id: str,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    wb = (await s.execute(select(Workbook).where(Workbook.id == workbook_id))).scalar_one_or_none()
    if not wb:
        raise HTTPException(404)
    return {
        "id": wb.id,
        "workspace_id": wb.workspace_id,
        "name": wb.name,
        "cube_query": wb.cube_query,
        "chart_spec": wb.chart_spec,
    }


@app.patch("/workbooks/{workbook_id}")
async def patch_workbook(
    workbook_id: str,
    body: WorkbookPatch,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    wb = (await s.execute(select(Workbook).where(Workbook.id == workbook_id))).scalar_one_or_none()
    if not wb:
        raise HTTPException(404)
    if body.name is not None:
        wb.name = body.name
    if body.cube_query is not None:
        wb.cube_query = body.cube_query
    if body.chart_spec is not None:
        wb.chart_spec = body.chart_spec
    await s.commit()
    return {"id": wb.id, "name": wb.name}


@app.delete("/workbooks/{workbook_id}")
async def delete_workbook(
    workbook_id: str,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, str]:
    wb = (await s.execute(select(Workbook).where(Workbook.id == workbook_id))).scalar_one_or_none()
    if not wb:
        raise HTTPException(404)
    await s.delete(wb)
    await s.commit()
    return {"status": "deleted"}


# ── Dashboards ────────────────────────────────────────────────────────────────


@app.get("/dashboards")
async def list_dashboards(
    workspace_id: str,
    s: AsyncSession = Depends(session_dep),
) -> list[dict[str, Any]]:
    rows = (await s.execute(select(Dashboard).where(Dashboard.workspace_id == workspace_id))).scalars().all()
    return [
        {"id": d.id, "name": d.name, "layout": d.layout, "filters": d.filters}
        for d in rows
    ]


@app.post("/dashboards")
async def create_dashboard(
    body: DashboardCreate,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    d = Dashboard(
        id=f"dash-{uuid.uuid4().hex[:8]}",
        workspace_id=body.workspace_id,
        name=body.name,
        layout=body.layout,
        filters=body.filters,
        created_by="user-1",
    )
    s.add(d)
    await s.commit()
    return {"id": d.id, "name": d.name}


# ── Chat sessions + messages ─────────────────────────────────────────────────


class ChatSessionCreate(BaseModel):
    workspace_id: str
    title: str | None = None


class ChatMessageAppend(BaseModel):
    role: str        # "user" | "assistant"
    content: dict[str, Any] | str
    tier_used: str | None = None
    provider_used: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None


@app.get("/chat/sessions")
async def list_chat_sessions(
    workspace_id: str,
    s: AsyncSession = Depends(session_dep),
) -> list[dict[str, Any]]:
    from sqlalchemy import desc
    rows = (
        await s.execute(
            select(ChatSession)
            .where(ChatSession.workspace_id == workspace_id)
            .order_by(desc(ChatSession.created_at))
            .limit(50)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.post("/chat/sessions")
async def create_chat_session(
    body: ChatSessionCreate,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    sess = ChatSession(
        id=f"chat-{uuid.uuid4().hex[:10]}",
        workspace_id=body.workspace_id,
        user_id="user-1",
        title=body.title,
    )
    s.add(sess)
    await s.commit()
    return {"id": sess.id, "title": sess.title}


@app.get("/chat/sessions/{session_id}/messages")
async def list_chat_messages(
    session_id: str,
    s: AsyncSession = Depends(session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await s.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "tier_used": r.tier_used,
            "provider_used": r.provider_used,
            "tokens_input": r.tokens_input,
            "tokens_output": r.tokens_output,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@app.post("/chat/sessions/{session_id}/messages")
async def append_chat_message(
    session_id: str,
    body: ChatMessageAppend,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    msg = ChatMessage(
        id=f"msg-{uuid.uuid4().hex[:10]}",
        session_id=session_id,
        role=body.role,
        content=body.content if isinstance(body.content, dict) else {"text": body.content},
        tier_used=body.tier_used,
        provider_used=body.provider_used,
        tokens_input=body.tokens_input,
        tokens_output=body.tokens_output,
    )
    s.add(msg)
    # If the session has no title yet, derive from the first user message.
    if body.role == "user":
        sess = (await s.execute(select(ChatSession).where(ChatSession.id == session_id))).scalar_one_or_none()
        if sess and not sess.title:
            text = body.content.get("text") if isinstance(body.content, dict) else str(body.content)
            sess.title = (text or "")[:80]
    await s.commit()
    return {"id": msg.id}


@app.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, str]:
    sess = (await s.execute(select(ChatSession).where(ChatSession.id == session_id))).scalar_one_or_none()
    if not sess:
        raise HTTPException(404)
    # Cascade messages
    from sqlalchemy import delete as sql_delete
    await s.execute(sql_delete(ChatMessage).where(ChatMessage.session_id == session_id))
    await s.delete(sess)
    await s.commit()
    return {"status": "deleted"}


# ── Model editor endpoints (Cube schema YAML files) ──────────────────────────
#
# Phase-0 implementation: read/write the YAML files under backend/cube/schema/.
# Phase-1 will swap the read/write side for a git-backed store. The locate
# endpoint powers chat citations (clickable measure → jump to definition).

import re
from pathlib import Path

import yaml as _yaml

from shared.schema_bundle import CUBE_SCHEMA_ROOT


def _resolve_safe(rel: str) -> Path:
    """Resolve `rel` under CUBE_SCHEMA_ROOT, refusing path traversal."""
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise HTTPException(400, "Invalid path")
    p = (CUBE_SCHEMA_ROOT / rel).resolve()
    root = CUBE_SCHEMA_ROOT.resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise HTTPException(400, "Path escapes schema root")
    return p


@app.get("/model/files")
async def list_model_files() -> list[dict[str, Any]]:
    """List every YAML file under backend/cube/schema/ as a flat tree."""
    out: list[dict[str, Any]] = []
    for path in sorted(CUBE_SCHEMA_ROOT.rglob("*.yml")):
        rel = path.relative_to(CUBE_SCHEMA_ROOT)
        out.append(
            {
                "path": str(rel),
                "size": path.stat().st_size,
                "vertical": rel.parts[1] if len(rel.parts) >= 2 and rel.parts[0] == "verticals" else None,
            }
        )
    return out


@app.get("/model/files/{path:path}")
async def get_model_file(path: str) -> dict[str, Any]:
    p = _resolve_safe(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "File not found")
    return {"path": path, "content": p.read_text()}


class ModelFileSave(BaseModel):
    content: str


@app.put("/model/files/{path:path}")
async def save_model_file(path: str, body: ModelFileSave) -> dict[str, Any]:
    p = _resolve_safe(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "File not found")
    # Validate YAML before writing — refuse to save broken syntax.
    try:
        _yaml.safe_load(body.content)
    except _yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")
    p.write_text(body.content)
    return {"path": path, "size": p.stat().st_size}


class ValidateRequest(BaseModel):
    content: str


@app.post("/model/validate")
async def validate_model_file(body: ValidateRequest) -> dict[str, Any]:
    """Validate YAML + minimum Cube schema shape.

    Checks (deliberately limited — Cube itself is the source of truth):
      - YAML parses
      - Top-level `cubes` array
      - Every cube has `name`, `sql_table` or `sql`
      - Every measure has `name` + `type`
      - Every dimension has `name` + `type`
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        doc = _yaml.safe_load(body.content)
    except _yaml.YAMLError as e:
        # PyYAML errors carry a problem_mark with line/col.
        line = getattr(e, "problem_mark", None)
        errors.append(
            {
                "line": (line.line + 1) if line else None,
                "column": (line.column + 1) if line else None,
                "message": f"YAML parse error: {e}",
            }
        )
        return {"errors": errors, "warnings": warnings, "valid": False}

    if not isinstance(doc, dict) or "cubes" not in doc:
        errors.append({"line": 1, "column": 1, "message": "Missing top-level `cubes` array"})
        return {"errors": errors, "warnings": warnings, "valid": False}
    if not isinstance(doc["cubes"], list):
        errors.append({"line": 1, "column": 1, "message": "`cubes` must be a list"})
        return {"errors": errors, "warnings": warnings, "valid": False}

    for cube in doc["cubes"]:
        if not isinstance(cube, dict):
            errors.append({"line": None, "column": None, "message": "cube must be a mapping"})
            continue
        cname = cube.get("name", "<unnamed>")
        if "name" not in cube:
            errors.append({"line": None, "column": None, "message": "cube missing `name`"})
        if "sql_table" not in cube and "sql" not in cube:
            errors.append({"line": None, "column": None, "message": f"cube `{cname}` missing both `sql_table` and `sql`"})
        for m in cube.get("measures", []) or []:
            if "name" not in m:
                errors.append({"line": None, "column": None, "message": f"measure in `{cname}` missing `name`"})
            if "type" not in m:
                errors.append({"line": None, "column": None, "message": f"measure `{cname}.{m.get('name', '?')}` missing `type`"})
            if not m.get("description"):
                warnings.append({"line": None, "column": None, "message": f"measure `{cname}.{m.get('name', '?')}` has no description (hurts AI accuracy)"})
        for d in cube.get("dimensions", []) or []:
            if "name" not in d:
                errors.append({"line": None, "column": None, "message": f"dimension in `{cname}` missing `name`"})
            if "type" not in d:
                errors.append({"line": None, "column": None, "message": f"dimension `{cname}.{d.get('name', '?')}` missing `type`"})

    return {"errors": errors, "warnings": warnings, "valid": len(errors) == 0}


@app.get("/model/locate")
async def locate_member(member: str) -> dict[str, Any]:
    """Find which file + line declares a measure / dimension by `Cube.name`.

    Searches every YAML file under CUBE_SCHEMA_ROOT for a `name: <member>`
    declaration scoped under the cube `Cube`. Returns 404 if not found.
    Powers the chat-citation feature — clicking a measure jumps here.
    """
    if "." not in member:
        raise HTTPException(400, "member must be in `Cube.name` form")
    cube_name, field_name = member.split(".", 1)
    pattern_field = re.compile(rf"^\s*-\s*name:\s*{re.escape(field_name)}\s*$")
    pattern_cube = re.compile(rf"^\s*-?\s*name:\s*{re.escape(cube_name)}\s*$")

    for path in sorted(CUBE_SCHEMA_ROOT.rglob("*.yml")):
        text = path.read_text()
        lines = text.splitlines()
        cube_line = None
        for i, ln in enumerate(lines):
            if pattern_cube.match(ln):
                cube_line = i
                break
        if cube_line is None:
            continue
        # Search for the field declaration after the cube line.
        for i in range(cube_line + 1, len(lines)):
            if pattern_field.match(lines[i]):
                rel = path.relative_to(CUBE_SCHEMA_ROOT)
                return {
                    "path": str(rel),
                    "line": i + 1,
                    "cube": cube_name,
                    "field": field_name,
                }
    raise HTTPException(404, f"member not found: {member}")


# ── Schedules / scheduled deliveries (Phase 1 M5 stub) ──────────────────────


class ScheduleCreate(BaseModel):
    workspace_id: str
    dashboard_id: str | None = None
    workbook_id: str | None = None
    name: str
    cron: str
    timezone: str = "UTC"
    destination_kind: str
    destination_config: dict[str, Any] = {}
    body_template: str | None = None


@app.get("/schedules")
async def list_schedules(
    workspace_id: str,
    s: AsyncSession = Depends(session_dep),
) -> list[dict[str, Any]]:
    rows = (
        await s.execute(select(Schedule).where(Schedule.workspace_id == workspace_id))
    ).scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "cron": r.cron,
            "timezone": r.timezone,
            "destination_kind": r.destination_kind,
            "destination_config": r.destination_config,
            "is_paused": r.is_paused,
            "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
            "last_run_status": r.last_run_status,
            "dashboard_id": r.dashboard_id,
            "workbook_id": r.workbook_id,
        }
        for r in rows
    ]


@app.post("/schedules")
async def create_schedule(
    body: ScheduleCreate,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    sched = Schedule(
        id=f"sch-{uuid.uuid4().hex[:8]}",
        workspace_id=body.workspace_id,
        dashboard_id=body.dashboard_id,
        workbook_id=body.workbook_id,
        name=body.name,
        cron=body.cron,
        timezone=body.timezone,
        destination_kind=body.destination_kind,
        destination_config=body.destination_config,
        body_template=body.body_template,
        created_by="user-1",
    )
    s.add(sched)
    await s.commit()
    return {"id": sched.id, "name": sched.name}


@app.post("/schedules/{schedule_id}/pause")
async def pause_schedule(
    schedule_id: str,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, Any]:
    sched = (await s.execute(select(Schedule).where(Schedule.id == schedule_id))).scalar_one_or_none()
    if not sched:
        raise HTTPException(404, "schedule not found")
    sched.is_paused = True
    await s.commit()
    return {"id": sched.id, "is_paused": sched.is_paused}


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    s: AsyncSession = Depends(session_dep),
) -> dict[str, str]:
    sched = (await s.execute(select(Schedule).where(Schedule.id == schedule_id))).scalar_one_or_none()
    if not sched:
        raise HTTPException(404, "schedule not found")
    await s.delete(sched)
    await s.commit()
    return {"status": "deleted"}
