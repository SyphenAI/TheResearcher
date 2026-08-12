"""Lightweight security audit trail.

Research content history lives in git and project data. This log only keeps a
short, generic trail of security-relevant account and token events so we don't
burn local storage or prompt tokens on verbose activity dumps.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog

# Keep only a small rolling window of security events.
MAX_AUDIT_ROWS = 40
MAX_DETAIL_LEN = 80


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


def _prune(db: Session) -> None:
    ids = [
        row.id
        for row in db.query(AuditLog.id).order_by(AuditLog.id.desc()).offset(MAX_AUDIT_ROWS).all()
    ]
    if ids:
        db.query(AuditLog).filter(AuditLog.id.in_(ids)).delete(synchronize_session=False)
