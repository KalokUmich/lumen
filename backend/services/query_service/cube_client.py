"""Thin client for the Cube REST API.

Cube's load endpoint is a long-poll: it can return 'continueWait' that we must retry.
We collapse that into a single async call that hides the polling.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import jwt as pyjwt

CUBE_API_URL = os.environ.get("CUBE_API_URL", "http://localhost:4000/cubejs-api/v1")
CUBE_API_SECRET = os.environ.get("CUBE_API_SECRET", "local-dev-secret-change-me")

POLL_INITIAL_DELAY = 0.25
POLL_MAX_DELAY = 2.0
POLL_TIMEOUT_SECONDS = 60


def _mint_cube_token(security_context: dict[str, Any] | None = None) -> str:
    payload = security_context or {}
    return pyjwt.encode(payload, CUBE_API_SECRET, algorithm="HS256")


async def run(
    query: dict[str, Any],
    security_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a Cube query, handling the continueWait poll loop."""
    token = _mint_cube_token(security_context)
    headers = {"Authorization": token}

    async with httpx.AsyncClient(timeout=httpx.Timeout(POLL_TIMEOUT_SECONDS)) as client:
        delay = POLL_INITIAL_DELAY
        elapsed = 0.0
        while True:
            r = await client.post(
                f"{CUBE_API_URL}/load",
                headers=headers,
                json={"query": query},
            )
            r.raise_for_status()
            body = r.json()
            if body.get("error") == "Continue wait":
                await asyncio.sleep(delay)
                elapsed += delay
                if elapsed >= POLL_TIMEOUT_SECONDS:
                    raise TimeoutError("Cube query exceeded poll timeout")
                delay = min(delay * 1.5, POLL_MAX_DELAY)
                continue
            if "error" in body:
                raise RuntimeError(f"Cube error: {body['error']}")
            return body
