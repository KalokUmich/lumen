"""Auth helpers shared by all services.

- JWT verification (external user JWTs minted at the gateway).
- Internal service-to-service JWT minting/verification.
- WorkspaceContext object propagated via FastAPI dependency.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Header, HTTPException, status

INTERNAL_JWT_ALG = "HS512"
INTERNAL_JWT_TTL = timedelta(minutes=5)


def _signing_key() -> str:
    key = os.environ.get("JWT_SIGNING_KEY")
    if not key:
        raise RuntimeError("JWT_SIGNING_KEY must be set")
    return key


@dataclass(frozen=True)
class WorkspaceContext:
    user_id: str
    workspace_id: str
    role: str
    user_attrs: dict[str, Any]
    workspace_preset: str = "balanced"


def mint_internal_token(ctx: WorkspaceContext) -> str:
    """Gateway mints these and passes downstream via X-Internal-Token header."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": ctx.user_id,
        "wid": ctx.workspace_id,
        "role": ctx.role,
        "attrs": ctx.user_attrs,
        "preset": ctx.workspace_preset,
        "iat": int(now.timestamp()),
        "exp": int((now + INTERNAL_JWT_TTL).timestamp()),
    }
    return jwt.encode(payload, _signing_key(), algorithm=INTERNAL_JWT_ALG)


def verify_internal_token(token: str) -> WorkspaceContext:
    try:
        decoded = jwt.decode(token, _signing_key(), algorithms=[INTERNAL_JWT_ALG])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid internal token: {e}") from e
    return WorkspaceContext(
        user_id=decoded["sub"],
        workspace_id=decoded["wid"],
        role=decoded["role"],
        user_attrs=decoded.get("attrs", {}),
        workspace_preset=decoded.get("preset", "balanced"),
    )


async def workspace_ctx_dep(
    x_internal_token: str = Header(..., alias="X-Internal-Token"),
) -> WorkspaceContext:
    """FastAPI dependency for downstream services."""
    return verify_internal_token(x_internal_token)
