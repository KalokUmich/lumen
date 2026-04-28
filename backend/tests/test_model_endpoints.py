"""Integration tests for the model editor endpoints in workspace_service."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    db_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    db_file.close()
    monkeypatch.setenv("LUMEN_APP_DB_URL", f"sqlite+aiosqlite:///{db_file.name}")

    import importlib
    from shared import app_db
    importlib.reload(app_db)
    from services.workspace_service import main as ws_main
    importlib.reload(ws_main)

    import asyncio
    asyncio.run(app_db.init_schema())

    with TestClient(ws_main.app) as c:
        yield c

    os.unlink(db_file.name)


def test_list_model_files_returns_yaml_tree(client):
    r = client.get("/model/files")
    assert r.status_code == 200
    files = r.json()
    assert len(files) > 0
    paths = {f["path"] for f in files}
    # We know the lending vertical ships with the repo.
    assert any("loan.yml" in p for p in paths)
    assert any("verticals/lending" in p for p in paths)
    # Vertical is parsed when applicable.
    lending = [f for f in files if f["path"].startswith("verticals/lending/")]
    assert all(f["vertical"] == "lending" for f in lending)


def test_get_model_file_returns_content(client):
    r = client.get("/model/files/verticals/lending/loan.yml")
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "verticals/lending/loan.yml"
    assert "cubes:" in body["content"]
    assert "name: Loan" in body["content"]


def test_get_model_file_404_for_missing(client):
    r = client.get("/model/files/does/not/exist.yml")
    assert r.status_code == 404


def test_path_traversal_is_blocked(client):
    r = client.get("/model/files/../etc/passwd")
    # FastAPI's path normalization may collapse `..` before reaching us; either
    # 400 or 404 is an acceptable rejection. The forbidden case is 200.
    assert r.status_code in (400, 404)


def test_validate_rejects_invalid_yaml(client):
    # Unbalanced `[` — a real YAML parse error.
    bad = "cubes: [{ name: Foo,"
    r = client.post("/model/validate", json={"content": bad})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert any("YAML" in e["message"] for e in body["errors"])


def test_validate_flags_missing_required_fields(client):
    body = (
        "cubes:\n"
        "  - name: Bar\n"
        "    measures:\n"
        "      - name: m1\n"  # missing type
    )
    r = client.post("/model/validate", json={"content": body})
    assert r.status_code == 200
    out = r.json()
    assert out["valid"] is False
    msgs = " ".join(e["message"] for e in out["errors"])
    assert "missing both `sql_table` and `sql`" in msgs
    assert "missing `type`" in msgs


def test_validate_passes_for_minimal_correct_cube(client):
    body = (
        "cubes:\n"
        "  - name: Foo\n"
        "    sql_table: foo\n"
        "    measures:\n"
        "      - name: count\n"
        "        type: count\n"
        "        description: row count\n"
        "    dimensions:\n"
        "      - name: id\n"
        "        type: number\n"
    )
    r = client.post("/model/validate", json={"content": body})
    assert r.status_code == 200
    out = r.json()
    assert out["valid"] is True
    assert out["errors"] == []


def test_validate_warns_when_measure_lacks_description(client):
    body = (
        "cubes:\n"
        "  - name: Foo\n"
        "    sql_table: foo\n"
        "    measures:\n"
        "      - name: count\n"
        "        type: count\n"
    )
    r = client.post("/model/validate", json={"content": body})
    assert r.status_code == 200
    out = r.json()
    assert out["valid"] is True
    assert any("no description" in w["message"] for w in out["warnings"])


def test_save_round_trips(client, tmp_path):
    # Use an existing schema file. We restore it after.
    path = "verticals/lending/loan.yml"
    original = client.get(f"/model/files/{path}").json()["content"]

    valid_addition = original + "\n# trailing comment added by test\n"
    r = client.put(f"/model/files/{path}", json={"content": valid_addition})
    assert r.status_code == 200
    after = client.get(f"/model/files/{path}").json()["content"]
    assert after == valid_addition

    # Restore.
    client.put(f"/model/files/{path}", json={"content": original})


def test_save_rejects_invalid_yaml(client):
    path = "verticals/lending/loan.yml"
    r = client.put(f"/model/files/{path}", json={"content": "cubes:\n  -\n  bad"})
    assert r.status_code == 400


def test_locate_finds_a_known_member(client):
    # Loan.origination_date is a time dimension in the lending schema.
    r = client.get("/model/locate?member=Loan.origination_date")
    assert r.status_code == 200
    body = r.json()
    assert body["cube"] == "Loan"
    assert body["field"] == "origination_date"
    assert body["path"].endswith("loan.yml")
    assert isinstance(body["line"], int) and body["line"] > 0


def test_locate_404_when_member_unknown(client):
    r = client.get("/model/locate?member=Orders.does_not_exist")
    assert r.status_code == 404


def test_locate_400_when_member_malformed(client):
    r = client.get("/model/locate?member=NoDot")
    assert r.status_code == 400
