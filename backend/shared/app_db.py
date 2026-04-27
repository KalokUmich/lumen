"""App DB connection + lightweight schema bootstrap.

Phase 0: SQLite for zero-setup local dev (file at $LUMEN_APP_DB_PATH or
local_test/data/app.db). Phase 1+ swaps to Postgres via the same
SQLAlchemy session — no call-site changes needed.

Uses SQLAlchemy 2.0 async API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared import settings as settings_module


def _resolve_db_url() -> str:
    # Highest priority: explicit env var.
    url = os.environ.get("LUMEN_APP_DB_URL")
    if url:
        return url
    # Otherwise: secrets.databases.app_db.url
    secret_url = settings_module.secret("databases.app_db.url")
    if secret_url:
        return secret_url
    # Local dev fallback: SQLite file inside local_test/data/.
    default_path = (
        Path(__file__).resolve().parents[2] / "local_test" / "data" / "app.db"
    )
    default_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{default_path}"


_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    pass


# ── Models (subset of IMPLEMENTATION_PLAN §2.2) ────────────────────────────────


class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(String, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    vertical = Column(String, nullable=False, default="tpch")  # template the workspace was cloned from
    llm_preset = Column(String, nullable=False, default="balanced")
    cube_schema_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    attributes = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    workspace_id = Column(String, ForeignKey("workspaces.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    role = Column(String, nullable=False)  # admin | editor | viewer


class DataSource(Base):
    __tablename__ = "data_sources"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # postgres | mysql | mongodb | duckdb | sqlite
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    database = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password_secret_arn = Column(String, nullable=True)
    extra = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=False, default="untested")  # untested | ok | failed
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Workbook(Base):
    __tablename__ = "workbooks"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)
    cube_query = Column(JSON, nullable=False)
    chart_spec = Column(JSON, nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Dashboard(Base):
    __tablename__ = "dashboards"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)
    layout = Column(JSON, nullable=False, default=list)
    filters = Column(JSON, nullable=False, default=list)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DashboardTile(Base):
    __tablename__ = "dashboard_tiles"
    id = Column(String, primary_key=True)
    dashboard_id = Column(String, ForeignKey("dashboards.id"), nullable=False)
    workbook_id = Column(String, ForeignKey("workbooks.id"), nullable=False)
    title = Column(String, nullable=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    tier_used = Column(String, nullable=True)
    provider_used = Column(String, nullable=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    tokens_cached = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FailedQueryReview(Base):
    __tablename__ = "failed_query_reviews"
    id = Column(String, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    question = Column(Text, nullable=False)
    ai_query = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="open")
    triaged_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Engine + session management ───────────────────────────────────────────────


def get_engine():
    global _engine, _session_maker
    if _engine is None:
        url = _resolve_db_url()
        _engine = create_async_engine(url, future=True, echo=False)
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_maker is not None
    return _session_maker


async def init_schema() -> None:
    """Create tables if they don't exist. Phase 0 only — Phase 1 uses Alembic."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def session_dep() -> AsyncIterator[AsyncSession]:
    sm = get_session_maker()
    async with sm() as session:
        yield session
