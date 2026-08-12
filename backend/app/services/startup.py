from __future__ import annotations

import importlib
import platform
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, Project, ResearchSection, User
from app.security import hash_password


REQUIRED_PACKAGES = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "jose",
    "passlib",
    "cryptography",
    "docx",
    "httpx",
]


def run_self_check() -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "data_dir_writable": False,
        "packages": {},
        "disk_free_mb": None,
        "ok": True,
        "errors": [],
    }

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        checks["data_dir_writable"] = True
    except OSError as exc:
        checks["ok"] = False
        checks["errors"].append(f"data_dir not writable: {exc}")

    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            checks["packages"][pkg] = "ok"
        except ImportError:
            checks["packages"][pkg] = "missing"
            checks["ok"] = False
            checks["errors"].append(f"missing package: {pkg}")

    try:
        usage = shutil.disk_usage(str(settings.data_dir))
        checks["disk_free_mb"] = round(usage.free / (1024 * 1024), 1)
    except OSError:
        checks["disk_free_mb"] = None

    return checks


def ensure_seed_data(db: Session) -> None:
    settings = get_settings()
    admin = db.query(User).filter(User.username == settings.default_admin_username).first()
    if not admin:
        admin = User(
            username=settings.default_admin_username,
            display_name="Lead Researcher",
            password_hash=hash_password(settings.default_admin_password),
            role="admin",
            must_change_password=True,
            is_active=True,
        )
        db.add(admin)
        db.flush()
        db.add(
            AuditLog(
                actor="system",
                action="seed_admin",
                detail=f"Created default admin user '{settings.default_admin_username}'",
            )
        )

    project_count = db.query(Project).count()
    if project_count == 0 and admin:
        project = Project(
            title="Sample: Exposure Management Baseline",
            description=(
                "Starter project for Offensive Security, Exposure Management, "
                "and Vulnerability Management research."
            ),
            status="active",
            owner_id=admin.id,
            agent_contribution_pct=0.0,
            human_contribution_pct=100.0,
        )
        db.add(project)
        db.flush()
        defaults = [
            ("Scope and Objectives", 0),
            ("Threat Landscape (MITRE / STRIDE)", 1),
            ("Control and SaaS Tool Review", 2),
            ("Findings and Recommendations", 3),
            ("References", 4),
        ]
        for title, order in defaults:
            db.add(
                ResearchSection(
                    project_id=project.id,
                    title=title,
                    prompt="",
                    content_md=f"# {title}\n\n_Start drafting here._\n",
                    sort_order=order,
                    agent_chars=0,
                    human_chars=0,
                )
            )
        db.add(
            AuditLog(
                actor="system",
                action="seed_project",
                detail="Created sample research project with default sections",
            )
        )

    artifacts_dir = settings.data_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    db.commit()


def log_startup(db: Session, checks: dict[str, Any]) -> None:
    db.add(
        AuditLog(
            actor="system",
            action="startup_self_check",
            detail=str(checks),
        )
    )
    db.commit()
