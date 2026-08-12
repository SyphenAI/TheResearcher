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
        with engine.begin() as conn:
            for stmt in alters:
                conn.execute(text(stmt))
