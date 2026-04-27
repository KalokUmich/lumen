"""Query Service — proxies Cube queries with caching + RLS injection.

Backends:
  - LUMEN_QUERY_BACKEND=cube (default in production) → real Cube
  - LUMEN_QUERY_BACKEND=duckdb_tpch → local DuckDB via local_test/duckdb_query_runner_tpch.py
  - LUMEN_QUERY_BACKEND=duckdb_orders → local DuckDB via local_test/duckdb_query_runner.py
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from shared.auth import WorkspaceContext, workspace_ctx_dep
from shared.errors import CubeQueryFailed
from shared.observability import setup_observability

from . import cube_client


QUERY_BACKEND = os.environ.get("LUMEN_QUERY_BACKEND", "cube")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability("query_service")
    # Optional Redis cache; no-op if not configured.
    try:
        import redis.asyncio as redis  # local import — keeps dep optional in dev
        url = os.environ.get("REDIS_URL")
        app.state.redis = redis.from_url(url, decode_responses=True) if url else None
    except Exception:
        app.state.redis = None
    yield
    if getattr(app.state, "redis", None):
        await app.state.redis.aclose()


app = FastAPI(title="Lumen Query Service", lifespan=lifespan)


class RunQueryBody(BaseModel):
    cube_query: dict[str, Any]


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "backend": QUERY_BACKEND}


def _cache_key(workspace_id: str, query: dict[str, Any], rls_attrs: dict[str, Any]) -> str:
    payload = json.dumps(
        {"wid": workspace_id, "q": query, "rls": rls_attrs}, sort_keys=True, default=str
    )
    return "qcache:" + hashlib.sha256(payload.encode()).hexdigest()


def inject_rls(query: dict[str, Any], ctx: WorkspaceContext) -> dict[str, Any]:
    """Phase 0 stub. Phase 1 sprint 8 wires the policy engine."""
    return query


async def _execute(query: dict[str, Any], ctx: WorkspaceContext) -> dict[str, Any]:
    # In duckdb mode, route by workspace's configured vertical so workspace
    # switching actually changes the data backend.
    if QUERY_BACKEND.startswith("duckdb"):
        import sys
        sys.path.insert(0, str(_repo_root()))
        # Look up the workspace's vertical to pick the right runner.
        vertical = await _vertical_for(ctx.workspace_id)
        if vertical == "saas_finance":
            from local_test import duckdb_query_runner_saas as r
        elif vertical == "orders":
            from local_test import duckdb_query_runner as r
        else:
            from local_test import duckdb_query_runner_tpch as r
        result = r.run_query(query)
        return {"data": result["data"], "annotation": {}, "sql": result.get("sql")}
    # Production: real Cube.
    return await cube_client.run(
        query,
        security_context={
            "workspace_id": ctx.workspace_id,
            "user_id": ctx.user_id,
            "attrs": ctx.user_attrs,
        },
    )


_workspace_vertical_cache: dict[str, str] = {}


async def _vertical_for(workspace_id: str) -> str:
    """Resolve the workspace's vertical via workspace_service. Cached for the
    process lifetime since vertical changes are rare.
    """
    if workspace_id in _workspace_vertical_cache:
        return _workspace_vertical_cache[workspace_id]
    workspace_url = os.environ.get("WORKSPACE_SERVICE_URL")
    if not workspace_url:
        return os.environ.get("LUMEN_DEFAULT_VERTICAL", "tpch")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{workspace_url}/internal/workspaces/{workspace_id}/schema-bundle")
            if r.status_code == 200:
                vertical = r.json().get("vertical", "tpch")
                _workspace_vertical_cache[workspace_id] = vertical
                return vertical
    except Exception:
        pass
    return os.environ.get("LUMEN_DEFAULT_VERTICAL", "tpch")


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[3]


def _coerce_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON-serialize rows: cast Decimal → float, datetime → ISO8601 string."""
    from datetime import date, datetime
    from decimal import Decimal

    out: list[dict[str, Any]] = []
    for row in rows:
        new_row: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, Decimal):
                new_row[k] = float(v)
            elif isinstance(v, (date, datetime)):
                new_row[k] = v.isoformat()
            else:
                new_row[k] = v
        out.append(new_row)
    return out


@app.post("/internal/queries/run")
async def run_query(
    body: RunQueryBody,
    ctx: WorkspaceContext = Depends(workspace_ctx_dep),
) -> dict[str, Any]:
    secured = inject_rls(body.cube_query, ctx)

    redis = getattr(app.state, "redis", None)
    if redis is not None:
        key = _cache_key(ctx.workspace_id, secured, ctx.user_attrs)
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)

    try:
        result = await _execute(secured, ctx)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise CubeQueryFailed(str(e)) from e

    slim = {"data": _coerce_rows(result.get("data", [])), "annotation": result.get("annotation", {})}
    if redis is not None:
        from shared import settings as settings_module
        ttl = settings_module.get("cache.query_result_ttl", 300)
        key = _cache_key(ctx.workspace_id, secured, ctx.user_attrs)
        await redis.setex(key, ttl, json.dumps(slim, default=str))
    return slim
