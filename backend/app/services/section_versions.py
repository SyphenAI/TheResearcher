"""Light section version snippets (keep last N per section)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import SectionVersion
from app.services.timefmt import to_iso_utc

MAX_VERSIONS_PER_SECTION = 12


def record_section_version(
    db: Session,
    *,
    section_id: int,
    project_id: int,
    content_md: str,
    label: str = "snapshot",
    created_by: str = "",
) -> SectionVersion | None:
    text = content_md or ""
    # Skip empty or tiny unchanged spam
    if not text.strip():
        return None
    last = (
        db.query(SectionVersion)
        .filter(SectionVersion.section_id == section_id)
        .order_by(SectionVersion.id.desc())
        .first()
    )
    if last and last.content_md == text:
        return last

    row = SectionVersion(
        section_id=section_id,
        project_id=project_id,
        content_md=text,
        label=(label or "snapshot")[:128],
        char_count=len(text),
        created_by=(created_by or "")[:64],
    )
    db.add(row)
    db.flush()

    # Trim old versions
    ids = (
        db.query(SectionVersion.id)
        .filter(SectionVersion.section_id == section_id)
        .order_by(SectionVersion.id.desc())
        .all()
    )
    keep = {i[0] for i in ids[:MAX_VERSIONS_PER_SECTION]}
    for (vid,) in ids:
        if vid not in keep:
            db.query(SectionVersion).filter(SectionVersion.id == vid).delete(
                synchronize_session=False
            )
    return row


def list_section_versions(db: Session, section_id: int, *, limit: int = 12) -> list[SectionVersion]:
    limit = max(1, min(int(limit or 12), 30))
    return (
        db.query(SectionVersion)
        .filter(SectionVersion.section_id == section_id)
        .order_by(SectionVersion.id.desc())
        .limit(limit)
        .all()
    )


def get_version(db: Session, version_id: int, section_id: int | None = None) -> SectionVersion | None:
    q = db.query(SectionVersion).filter(SectionVersion.id == version_id)
    if section_id is not None:
        q = q.filter(SectionVersion.section_id == section_id)
    return q.first()


def version_to_dict(row: SectionVersion) -> dict:
    snippet = (row.content_md or "").replace("\n", " ").strip()
    if len(snippet) > 160:
        snippet = snippet[:159] + "…"
    return {
        "id": row.id,
        "section_id": row.section_id,
        "project_id": row.project_id,
        "label": row.label,
        "char_count": row.char_count,
        "snippet": snippet,
        "created_by": row.created_by,
        "created_at": to_iso_utc(row.created_at),
    }
