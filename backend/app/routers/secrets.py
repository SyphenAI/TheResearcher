from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import ApiToken, AuditLog, User
from app.schemas import (
    KillSwitchResponse,
    TokenBulkActionResponse,
    TokenCreate,
    TokenOut,
    TokenUpdate,
)
from app.security import decrypt_secret, encrypt_secret, mask_secret
from app.services.audit import MAX_AUDIT_ROWS, log_security_event, serialize_audit_row

router = APIRouter(prefix="/api/security", tags=["security"])

KNOWN_PROVIDERS = [
    "openai",
    "anthropic",
    "google",
    "xai",
    "azure_openai",
    "custom",
]


@router.get("/providers")
def list_providers(_: User = Depends(get_current_user)) -> dict:
    return {"providers": KNOWN_PROVIDERS}


@router.get("/tokens", response_model=list[TokenOut])
def list_tokens(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TokenOut]:
    if user.role not in {"admin", "researcher"}:
        raise HTTPException(status_code=403, detail="Not allowed")
    rows = db.query(ApiToken).order_by(ApiToken.provider.asc(), ApiToken.label.asc()).all()
    return [_to_out(row) for row in rows]


@router.post("/tokens", response_model=TokenOut, status_code=201)
def upsert_token(
    body: TokenCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenOut:
    provider = body.provider.strip().lower()
    label = body.label.strip() or "default"
    if not body.value.strip():
        raise HTTPException(status_code=400, detail="Token value required")

    row = (
        db.query(ApiToken)
        .filter(ApiToken.provider == provider, ApiToken.label == label)
        .first()
    )
    if row:
        row.encrypted_value = encrypt_secret(body.value.strip())
        row.is_active = body.is_active
        row.use_for_research = body.use_for_research
        row.use_for_judge = body.use_for_judge
    else:
        row = ApiToken(
            provider=provider,
            label=label,
            encrypted_value=encrypt_secret(body.value.strip()),
            is_active=body.is_active,
            use_for_research=body.use_for_research,
            use_for_judge=body.use_for_judge,
        )
        db.add(row)

    log_security_event(
        db,
        actor=user.username,
        action="token_upsert",
        detail=f"Saved {provider} token ({label})",
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.patch("/tokens/{token_id}", response_model=TokenOut)
def edit_token(
    token_id: int,
    body: TokenUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenOut:
    row = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")

    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    new_provider = row.provider
    new_label = row.label

    if "provider" in data and data["provider"] is not None:
        new_provider = data["provider"].strip().lower()
    if "label" in data and data["label"] is not None:
        new_label = (data["label"].strip() or "default")

    if new_provider != row.provider or new_label != row.label:
        clash = (
            db.query(ApiToken)
            .filter(
                ApiToken.provider == new_provider,
                ApiToken.label == new_label,
                ApiToken.id != row.id,
            )
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=400,
                detail="Another token already uses that provider/label",
            )
        row.provider = new_provider
        row.label = new_label

    if "value" in data and data["value"] is not None:
        value = data["value"].strip()
        if value:
            row.encrypted_value = encrypt_secret(value)

    if "is_active" in data and data["is_active"] is not None:
        row.is_active = bool(data["is_active"])
    if "use_for_research" in data and data["use_for_research"] is not None:
        row.use_for_research = bool(data["use_for_research"])
    if "use_for_judge" in data and data["use_for_judge"] is not None:
        row.use_for_judge = bool(data["use_for_judge"])

    log_security_event(
        db,
        actor=user.username,
        action="token_edit",
        detail=f"Updated {row.provider} token ({row.label})",
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/tokens/{token_id}/disable", response_model=TokenOut)
def disable_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenOut:
    return _set_active(db, user, token_id, active=False)


@router.post("/tokens/{token_id}/enable", response_model=TokenOut)
def enable_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenOut:
    return _set_active(db, user, token_id, active=True)


@router.post("/tokens/{token_id}/judge", response_model=TokenOut)
def set_judge_usage(
    token_id: int,
    enabled: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenOut:
    row = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    row.use_for_judge = bool(enabled)
    log_security_event(
        db,
        actor=user.username,
        action="token_judge_on" if enabled else "token_judge_off",
        detail=(
            f"{row.provider} ({row.label}) "
            f"{'included in judge panel' if enabled else 'removed from judge panel'}"
        ),
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/tokens/{token_id}/research", response_model=TokenOut)
def set_research_usage(
    token_id: int,
    enabled: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenOut:
    row = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    row.use_for_research = bool(enabled)
    log_security_event(
        db,
        actor=user.username,
        action="token_research_on" if enabled else "token_research_off",
        detail=(
            f"{row.provider} ({row.label}) "
            f"{'included in research assistant' if enabled else 'removed from research assistant'}"
        ),
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/tokens/disable-all", response_model=TokenBulkActionResponse)
def disable_all_tokens(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenBulkActionResponse:
    rows = db.query(ApiToken).filter(ApiToken.is_active.is_(True)).all()
    for row in rows:
        row.is_active = False
    log_security_event(
        db,
        actor=user.username,
        action="token_disable_all",
        detail=f"Disabled {len(rows)} stored token(s). Secrets kept encrypted.",
    )
    db.commit()
    return TokenBulkActionResponse(
        ok=True,
        affected=len(rows),
        message=(
            f"Disabled {len(rows)} token(s). Values stay stored encrypted and can be re-enabled."
        ),
    )


@router.post("/tokens/enable-all", response_model=TokenBulkActionResponse)
def enable_all_tokens(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> TokenBulkActionResponse:
    rows = db.query(ApiToken).filter(ApiToken.is_active.is_(False)).all()
    for row in rows:
        row.is_active = True
    log_security_event(
        db,
        actor=user.username,
        action="token_enable_all",
        detail=f"Re-enabled {len(rows)} stored token(s).",
    )
    db.commit()
    return TokenBulkActionResponse(
        ok=True,
        affected=len(rows),
        message=f"Re-enabled {len(rows)} token(s).",
    )


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Response:
    row = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    provider = row.provider
    db.delete(row)
    log_security_event(
        db,
        actor=user.username,
        action="token_delete",
        detail=f"Removed {provider} token permanently",
    )
    db.commit()
    return Response(status_code=204)


@router.post("/global-kill", response_model=KillSwitchResponse)
@router.post("/kill-switch", response_model=KillSwitchResponse, include_in_schema=False)
def global_kill(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> KillSwitchResponse:
    """Permanently remove all stored tokens. Prefer disable for reversible stop."""
    rows = db.query(ApiToken).all()
    count = len(rows)
    for row in rows:
        db.delete(row)

    settings = get_settings()
    secrets_file = settings.data_dir / "secrets_backup.json"
    if secrets_file.exists():
        secrets_file.unlink()

    log_security_event(
        db,
        actor=user.username,
        action="global_kill",
        detail=f"Permanently wiped {count} token(s) and local secret backups",
    )
    db.commit()
    return KillSwitchResponse(
        ok=True,
        removed_tokens=count,
        message=(
            f"Global Kill removed {count} token(s) and local secret backups permanently. "
            "This cannot be undone from the app."
        ),
    )


@router.get("/audit")
def recent_audit(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    limit: int = 20,
) -> dict:
    """Short security event feed only. Research history belongs in git."""
    cap = min(max(limit, 1), MAX_AUDIT_ROWS)
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(cap).all()
    return {
        "note": (
            "Security and system events only (sign-in, users, tokens, startup). "
            "Research content changes live in git and project storage."
        ),
        "retention": MAX_AUDIT_ROWS,
        "events": [serialize_audit_row(r) for r in rows],
    }


def _set_active(db: Session, user: User, token_id: int, active: bool) -> TokenOut:
    row = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    row.is_active = active
    action = "token_enable" if active else "token_disable"
    log_security_event(
        db,
        actor=user.username,
        action=action,
        detail=(
            f"{row.provider} ({row.label}) "
            f"{'turned on' if active else 'turned off'} for all workflows"
        ),
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


def _to_out(row: ApiToken) -> TokenOut:
    masked = "********"
    try:
        plain = decrypt_secret(row.encrypted_value)
        masked = mask_secret(plain)
    except ValueError:
        masked = "[decrypt-error]"
    return TokenOut(
        id=row.id,
        provider=row.provider,
        label=row.label,
        is_active=row.is_active,
        use_for_research=bool(getattr(row, "use_for_research", True)),
        use_for_judge=bool(getattr(row, "use_for_judge", True)),
        masked_value=masked,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def touch_token_usage(db: Session, provider: str, label: str = "default") -> str | None:
    row = (
        db.query(ApiToken)
        .filter(
            ApiToken.provider == provider,
            ApiToken.label == label,
            ApiToken.is_active.is_(True),
        )
        .first()
    )
    if not row:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return decrypt_secret(row.encrypted_value)
