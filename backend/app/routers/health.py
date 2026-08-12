from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Project, User
from app.schemas import HealthOut
from app.services.startup import run_self_check

router = APIRouter(tags=["health"])
VERSION = "0.2.0-preprod"


@router.get("/api/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    settings = get_settings()
    checks = run_self_check()
    try:
        checks["users"] = db.query(User).count()
        checks["projects"] = db.query(Project).count()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
        checks["ok"] = False
        checks.setdefault("errors", []).append(str(exc))

    return HealthOut(
        status="ok" if checks.get("ok") else "degraded",
        checks=checks,
        version=VERSION,
        app_env=settings.app_env,
    )


@router.get("/api/version")
def version() -> dict:
    return {"version": VERSION, "app": get_settings().app_name}
