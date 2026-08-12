from __future__ import annotations

import importlib
import platform
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Project, ResearchSection, User
from app.security import hash_password
from app.services.audit import log_security_event


REQUIRED_PACKAGES = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "jose",
    "passlib",
    "cryptography",
    "docx",
    "pypdf",
    "pptx",
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
        log_security_event(db, actor="system", action="seed_admin", detail="default admin")

    project_count = db.query(Project).count()
    if project_count == 0 and admin:
        from app.services.refs_cache import refs_path
        from app.services.template_store import get_template, list_templates

        refs_path()  # ensure offline refs cache exists
        list_templates()  # seed editable templates file
        template = get_template("blank") or {
            "title": "Blank research",
            "description": "General structured research.",
            "sections": ["Overview", "Analysis", "Findings", "Recommendations", "References"],
        }
        project = Project(
            title="Sample research project",
            description=template.get("description", ""),
            status="active",
            owner_id=admin.id,
            agent_contribution_pct=0.0,
            human_contribution_pct=100.0,
            template_key="blank",
            evidence_mode=True,
            max_agent_pct=10.0,
            publish_ready=False,
            archived=False,
        )
        db.add(project)
        db.flush()
        for idx, title in enumerate(template.get("sections") or ["Overview"]):
            db.add(
                ResearchSection(
                    project_id=project.id,
                    title=title,
                    prompt="",
                    content_md=f"# {title}\n\n",
                    sort_order=idx,
                    agent_chars=0,
                    human_chars=0,
                )
            )
        log_security_event(db, actor="system", action="seed_project", detail="sample blank")

    from app.services.storage_paths import project_dir, storage_root

    storage_root()
    # Ensure any active projects have a local topic folder under storage/projects/
    for proj in db.query(Project).filter(Project.archived.is_(False)).all():
        path = project_dir(proj.id, proj.title, create=True)
        if not getattr(proj, "storage_path", None):
            proj.storage_path = str(path)
    db.commit()


def log_startup(db: Session, checks: dict[str, Any]) -> None:
    # Keep startup notes tiny. Full research history is in git, not this table.
    status = "ok" if checks.get("ok") else "degraded"
    log_security_event(
        db,
        actor="system",
        action="startup",
        detail=status,
        commit=True,
    )
