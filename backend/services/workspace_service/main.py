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
    Dashboard,
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
    vertical: str = "tpch"
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
    """Ensure a demo workspace + user exist for first-run UX."""
    from shared.app_db import get_session_maker

    sm = get_session_maker()
    async with sm() as s:
        existing = (await s.execute(select(Workspace).where(Workspace.slug == "demo"))).scalar_one_or_none()
        if existing:
            return

        ws = Workspace(
            id="ws-demo",
            slug="demo",
            name="Demo (TPC-H)",
            vertical="tpch",
            llm_preset="balanced",
            cube_schema_ref="local",
        )
        user = User(id="user-1", email="dev@local", display_name="Dev User", attributes={})
        membership = WorkspaceMembership(workspace_id="ws-demo", user_id="user-1", role="admin")
        s.add_all([ws, user, membership])
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
