"""Lightweight security audit trail.

Research content history lives in git. This log keeps short, human-readable
security and system events without dumping code diffs or long payloads.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.services.timefmt import to_iso_utc

# Keep only a small rolling window of security events.
MAX_AUDIT_ROWS = 50
MAX_DETAIL_LEN = 140

# Friendly labels for the Security page (not raw action keys).
ACTION_LABELS = {
    "login": "Signed in",
    "password_change": "Password changed",
    "user_create": "User account created",
    "token_upsert": "API token saved",
    "token_edit": "API token updated",
    "token_delete": "API token removed",
    "token_enable": "API token enabled",
    "token_disable": "API token disabled",
    "token_disable_all": "All API tokens disabled",
    "token_enable_all": "All API tokens enabled",
    "token_judge_on": "Model enabled for judge",
    "token_judge_off": "Model disabled for judge",
    "token_research_on": "Model enabled for research",
    "token_research_off": "Model disabled for research",
    "token_test_ok": "Token connectivity test passed",
    "token_test_fail": "Token connectivity test failed",
    "global_kill": "Global Kill ran",
    "kill_switch": "Global Kill ran",
    "seed_admin": "Default admin account prepared",
    "seed_project": "Sample research project prepared",
    "startup": "Application started",
    "startup_self_check": "Application started",
}


def humanize_action(action: str) -> str:
    return ACTION_LABELS.get(action or "", (action or "Event").replace("_", " ").capitalize())


def log_security_event(
    db: Session,
    *,
    actor: str,
    action: str,
    detail: str = "",
    commit: bool = False,
) -> None:
    clean_detail = (detail or "").strip().replace("\n", " ")
    if len(clean_detail) > MAX_DETAIL_LEN:
        clean_detail = clean_detail[: MAX_DETAIL_LEN - 1] + "…"

    db.add(
        AuditLog(
            actor=(actor or "system")[:64],
            action=(action or "event")[:128],
            detail=clean_detail,
        )
    )
    _prune(db)
    if commit:
        db.commit()


def serialize_audit_row(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "actor": row.actor,
        "action": row.action,
        "action_label": humanize_action(row.action),
        "detail": row.detail,
        "created_at": to_iso_utc(row.created_at),
    }


def _prune(db: Session) -> None:
    ids = [
        row.id
        for row in db.query(AuditLog.id).order_by(AuditLog.id.desc()).offset(MAX_AUDIT_ROWS).all()
    ]
    if ids:
        db.query(AuditLog).filter(AuditLog.id.in_(ids)).delete(synchronize_session=False)
