"""Global application settings (publish rules, thresholds, templates)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import get_current_user, require_admin
from app.models import User
from app.services.app_settings import DEFAULTS, load_app_settings, save_app_settings
from app.services.template_store import (
    create_template,
    delete_template,
    list_templates,
    reset_templates_to_builtin,
    update_template,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AppSettingsOut(BaseModel):
    max_agent_pct: float = 10.0
    max_ai_checker_pct: float = 10.0
    evidence_coverage_min_pct: float = 70.0
    enforce_publish_gate: bool = True
    allow_force_export: bool = True
    default_evidence_mode: bool = True
    default_template_key: str = "blank"
    require_citations_for_publish: bool = True
    humanize_before_export_hint: bool = True
    semantic_scholar_api_key: str = ""
    openalex_api_key: str = ""


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
    semantic_scholar_api_key: str | None = None
    openalex_api_key: str | None = None


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


class TemplateSectionIn(BaseModel):
    title: str
    prompt: str = ""
    seed: str = ""


class TemplateCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    key: str | None = None
    sections: list[str] = Field(default_factory=list)
    section_defs: list[TemplateSectionIn] | None = None


class TemplateUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    sections: list[str] | None = None
    section_defs: list[TemplateSectionIn] | None = None


@router.get("/templates")
def get_templates(_: User = Depends(get_current_user)) -> dict:
    rules = load_app_settings()
    return {
        "templates": list_templates(),
        "default": rules.get("default_template_key") or "blank",
    }


@router.post("/templates", status_code=201)
def post_template(
    body: TemplateCreateIn,
    user: User = Depends(require_admin),
) -> dict:
    try:
        item = create_template(
            title=body.title,
            description=body.description,
            sections=body.sections,
            section_defs=[s.model_dump() for s in body.section_defs]
            if body.section_defs is not None
            else None,
            key=body.key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


@router.put("/templates/{key}")
def put_template(
    key: str,
    body: TemplateUpdateIn,
    user: User = Depends(require_admin),
) -> dict:
    updates = body.model_dump(exclude_unset=True)
    if "section_defs" in updates and updates["section_defs"] is not None:
        updates["section_defs"] = [
            s if isinstance(s, dict) else s for s in updates["section_defs"]
        ]
    try:
        return update_template(key, updates)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/templates/{key}")
def remove_template(key: str, user: User = Depends(require_admin)) -> dict:
    try:
        delete_template(key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "deleted": key}


@router.post("/templates/reset")
def reset_templates(user: User = Depends(require_admin)) -> dict:
    rows = reset_templates_to_builtin()
    return {"ok": True, "templates": rows}
