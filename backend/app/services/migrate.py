"""Lightweight SQLite column/table migrations for local installs."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import Base


def ensure_schema(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "projects" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("projects")}
        alters = []
        if "template_key" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN template_key VARCHAR(64) DEFAULT 'blank'")
        if "evidence_mode" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN evidence_mode BOOLEAN DEFAULT 1")
        if "max_agent_pct" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN max_agent_pct FLOAT DEFAULT 10.0")
        if "publish_ready" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN publish_ready BOOLEAN DEFAULT 0")
        if "archived" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN archived BOOLEAN DEFAULT 0")
        if "storage_path" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN storage_path VARCHAR(512) DEFAULT ''")
        if "archived_at" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN archived_at DATETIME")
        if "version_major" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN version_major INTEGER DEFAULT 0")
        if "version_minor" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN version_minor INTEGER DEFAULT 1")
        if "version_patch" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN version_patch INTEGER DEFAULT 1")
        if "primary_major" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN primary_major INTEGER DEFAULT 0")
        if "primary_minor" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN primary_minor INTEGER DEFAULT 0")
        if "primary_patch" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN primary_patch INTEGER DEFAULT 0")
        if "has_primary" not in cols:
            alters.append("ALTER TABLE projects ADD COLUMN has_primary BOOLEAN DEFAULT 0")
        with engine.begin() as conn:
            for stmt in alters:
                conn.execute(text(stmt))

    if "api_tokens" in inspector.get_table_names():
        token_cols = {c["name"] for c in inspector.get_columns("api_tokens")}
        token_alters = []
        if "use_for_research" not in token_cols:
            token_alters.append(
                "ALTER TABLE api_tokens ADD COLUMN use_for_research BOOLEAN DEFAULT 1"
            )
        if "use_for_judge" not in token_cols:
            token_alters.append(
                "ALTER TABLE api_tokens ADD COLUMN use_for_judge BOOLEAN DEFAULT 1"
            )
        if "model" not in token_cols:
            token_alters.append(
                "ALTER TABLE api_tokens ADD COLUMN model VARCHAR(128) DEFAULT ''"
            )
        with engine.begin() as conn:
            for stmt in token_alters:
                conn.execute(text(stmt))
