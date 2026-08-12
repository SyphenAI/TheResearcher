"""Global application settings (publish rules, thresholds)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user, require_admin
from app.models import User
from app.services.app_settings import DEFAULTS, load_app_settings, save_app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AppSettingsOut(BaseModel):
    max_agent_pct: float = 10.0
    max_ai_checker_pct: float = 10.0
    evidence_coverage_min_pct: float = 70.0
    enforce_publish_gate: bool = True
    allow_force_export: bool = True
    default_evidence_mode: bool = True
    default_template_key: str = "gartner_panel"
    require_citations_for_publish: bool = True
    humanize_before_export_hint: bool = True


class AppSettingsUpdate(BaseModel):
    max_agent_pct: float | None = Field(default=None, ge=0, le=100)
    max_ai_checker_pct: float | None = Field(default=None, ge=0, le=100)
    evidence_coverage_min_pct: float | None = Field(default=None, ge=0, le=100)
    enforce_publish_gate: bool | None = None
    allow_force_export: bool | None = None
    default_evidence_mode: bool | None = None
    default_template_key: str | None = None
    require_citations_for_publish: bool | None = None
    humanize_before_export_hint: bool | None = None


@router.get("", response_model=AppSettingsOut)
def get_settings_api(_: User = Depends(get_current_user)) -> dict[str, Any]:
    return load_app_settings()


@router.get("/defaults", response_model=AppSettingsOut)
def get_defaults(_: User = Depends(get_current_user)) -> dict[str, Any]:
    return DEFAULTS.copy()


@router.put("", response_model=AppSettingsOut)
def update_settings_api(
    body: AppSettingsUpdate,
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    updates = body.model_dump(exclude_unset=True)
    return save_app_settings(updates)


@router.post("/reset", response_model=AppSettingsOut)
def reset_settings(user: User = Depends(require_admin)) -> dict[str, Any]:
    return save_app_settings(DEFAULTS.copy())
