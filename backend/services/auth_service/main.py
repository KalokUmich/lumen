"""Auth Service — OIDC + workspace membership.

Phase 0: stub with /health only. Phase 1 sprint 8 wires Authlib OIDC.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.observability import setup_observability


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_observability("auth_service")
    yield


app = FastAPI(title="Omni Auth Service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "phase": "0-stub"}
