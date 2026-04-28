"""Integration tests for chat session persistence in workspace_service.

Spins the FastAPI app with an in-memory SQLite via APP_DB_URL override,
then exercises the full session lifecycle: create → append → list → delete.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    # Use a fresh temp SQLite file per test so tables exist and isolation
    # is real. In-memory `:memory:` won't work because aiosqlite opens a
    # new connection per session and `:memory:` is connection-scoped.
    db_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    db_file.close()
    monkeypatch.setenv("LUMEN_APP_DB_URL", f"sqlite+aiosqlite:///{db_file.name}")

    # Force re-import so the module re-resolves the URL with our env override.
    import importlib
    from shared import app_db
    importlib.reload(app_db)
    from services.workspace_service import main as ws_main
    importlib.reload(ws_main)

    # Initialize schema synchronously through asyncio.run on the lifespan
    # equivalent — easier to call init_schema directly.
    import asyncio
    asyncio.run(app_db.init_schema())

    with TestClient(ws_main.app) as c:
        yield c

    os.unlink(db_file.name)


def test_session_lifecycle(client):
    # 1. List initially empty
    r = client.get("/chat/sessions?workspace_id=ws-test")
    assert r.status_code == 200
    assert r.json() == []

    # 2. Create a session
    r = client.post("/chat/sessions", json={"workspace_id": "ws-test"})
    assert r.status_code == 200
    session_id = r.json()["id"]
    assert session_id.startswith("chat-")

    # 3. List now returns the session, title is None until first message
    r = client.get("/chat/sessions?workspace_id=ws-test")
    listed = r.json()
    assert len(listed) == 1
    assert listed[0]["id"] == session_id
    assert listed[0]["title"] is None

    # 4. Append a user message — title should auto-derive
    r = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"role": "user", "content": {"text": "What was revenue last month?"}},
    )
    assert r.status_code == 200

    r = client.get("/chat/sessions?workspace_id=ws-test")
    assert r.json()[0]["title"] == "What was revenue last month?"

    # 5. Append an assistant message with structured content
    r = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={
            "role": "assistant",
            "content": {
                "text": "Total revenue last month was $2.82B",
                "cube_query": {"measures": ["LineItem.revenue"]},
            },
            "tier_used": "balanced",
            "provider_used": "alibaba",
        },
    )
    assert r.status_code == 200

    # 6. List messages — both come back in insertion order
    r = client.get(f"/chat/sessions/{session_id}/messages")
    msgs = r.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"]["cube_query"]["measures"] == ["LineItem.revenue"]
    assert msgs[1]["tier_used"] == "balanced"

    # 7. Delete the session — messages cascade
    r = client.delete(f"/chat/sessions/{session_id}")
    assert r.status_code == 200

    r = client.get("/chat/sessions?workspace_id=ws-test")
    assert r.json() == []


def test_workspace_isolation(client):
    """Sessions in workspace A must not appear when listing workspace B."""
    a = client.post("/chat/sessions", json={"workspace_id": "ws-a"}).json()["id"]
    client.post("/chat/sessions", json={"workspace_id": "ws-b"})

    listed_a = client.get("/chat/sessions?workspace_id=ws-a").json()
    assert len(listed_a) == 1
    assert listed_a[0]["id"] == a

    listed_b = client.get("/chat/sessions?workspace_id=ws-b").json()
    assert len(listed_b) == 1
    assert listed_b[0]["id"] != a


def test_string_content_is_normalized_to_dict(client):
    """The endpoint accepts content as either dict or string; string gets
    wrapped into {text: ...} so reads always see a structured shape."""
    sid = client.post("/chat/sessions", json={"workspace_id": "ws-test"}).json()["id"]
    r = client.post(
        f"/chat/sessions/{sid}/messages",
        json={"role": "user", "content": "plain string"},
    )
    assert r.status_code == 200

    msgs = client.get(f"/chat/sessions/{sid}/messages").json()
    assert msgs[0]["content"] == {"text": "plain string"}
