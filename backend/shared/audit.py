"""Structured audit log emit.

Every service that performs a user-attributable action calls `audit.emit(...)`.
v1: writes structured JSON to stdout (collected by container runtime → CloudWatch).
v2: ships to Kafka → S3 (replace the sink, not the call sites).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger("audit")


def emit(
    *,
    actor_user_id: str,
    workspace_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a single audit event."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor_user_id": actor_user_id,
        "workspace_id": workspace_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "metadata": metadata or {},
    }
    # Use a distinct logger so audit logs are easy to route in fluentd/vector configs.
    logger.info("audit", **event)
    # Also print as a single JSON line for grep-ability in local dev.
    print(json.dumps({"_audit": True, **event}), flush=True)
