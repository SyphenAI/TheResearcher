from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import ApiToken, AuditLog, User
from app.schemas import KillSwitchResponse, TokenCreate, TokenOut
from app.security import decrypt_secret, encrypt_secret, mask_secret

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
    else:
        row = ApiToken(
            provider=provider,
            label=label,
            encrypted_value=encrypt_secret(body.value.strip()),
            is_active=body.is_active,
        )
        db.add(row)

    db.add(
        AuditLog(
            actor=user.username,
            action="token_upsert",
            detail=f"provider={provider} label={label}",
        )
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Response:
    row = db.query(ApiToken).filter(ApiToken.id == token_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    db.delete(row)
    db.add(
        AuditLog(
            actor=user.username,
            action="token_delete",
            detail=f"id={token_id} provider={row.provider}",
        )
    )
    db.commit()
    return Response(status_code=204)


@router.post("/kill-switch", response_model=KillSwitchResponse)
def kill_switch(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> KillSwitchResponse:
    rows = db.query(ApiToken).all()
    count = len(rows)
    for row in rows:
        db.delete(row)

    # Also clear any plaintext env-style secrets file if present inside data dir
    settings = get_settings()
    secrets_file = settings.data_dir / "secrets_backup.json"
    if secrets_file.exists():
        secrets_file.unlink()

    db.add(
        AuditLog(
            actor=user.username,
            action="kill_switch",
            detail=f"Removed {count} API tokens and local secret backup",
        )
    )
    db.commit()
    return KillSwitchResponse(
        ok=True,
        removed_tokens=count,
        message="All stored API tokens and local secret backups were removed.",
    )


@router.get("/audit")
def recent_audit(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    limit: int = 100,
) -> list[dict]:
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500)).all()
    return [
        {
            "id": r.id,
            "actor": r.actor,
            "action": r.action,
            "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


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
